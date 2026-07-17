import json
import time
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.errors import conflict, bad_request, not_found
from app.config import DATA_DIR
from app.repositories.generation_repository import GenerationRepository
from app.services.context_service import ContextService
from app.schemas.context import ContextPreviewRequest
from app.schemas.generation import REVISION_OPERATIONS
from app.llm.base import LlmRequest
from app.llm.parser import parse_json
from app.llm.output_contracts import (
    validate_judge_output_for_selected_issues,
    validate_stage_output,
)
from app.models.generation import GenerationRun


def _save_to_disk(title: str, text: str):
    chapters_dir = DATA_DIR / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*]', '', title).strip()
    filepath = chapters_dir / f"{safe}.txt"
    filepath.write_text(text, encoding="utf-8")


class GenerationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = GenerationRepository(session)

    async def create_run(
        self, project_id: str, chapter_id: str | None,
        workflow_profile_id: str | None, scene_instruction: str,
    ) -> GenerationRun:
        if not workflow_profile_id:
            default_wf = await self.repo.get_default_workflow()
            if default_wf:
                workflow_profile_id = default_wf.id

        return await self.repo.create_run(
            project_id=project_id,
            chapter_id=chapter_id,
            workflow_profile_id=workflow_profile_id,
            scene_instruction=scene_instruction,
        )

    async def get_run(self, run_id: str) -> GenerationRun:
        return await self.repo.get_run_or_404(run_id)

    async def list_runs(self, project_id: str) -> list[GenerationRun]:
        return await self.repo.list_runs_by_project(project_id)

    async def execute_stage(self, run_id: str, stage: str, override: dict):
        run = await self.repo.get_run_or_404(run_id)

        required = await self._required_stages(stage, run)
        for dep_stage in required:
            dep_step = await self.repo.get_step(run_id, dep_stage)
            if not dep_step or dep_step.status != "completed":
                raise bad_request("STAGE_DEPENDENCY", f"Please complete '{dep_stage}' first")
            if not dep_step.selected_candidate_id:
                raise bad_request(
                    "STAGE_NO_CANDIDATE",
                    f"Please select a candidate for '{dep_stage}' before executing '{stage}'",
                )
            dep_cand = next(
                (c for c in dep_step.candidates if c.id == dep_step.selected_candidate_id), None
            )
            if dep_cand and dep_cand.error_code:
                raise bad_request(
                    "STAGE_CANDIDATE_ERROR",
                    f"The selected candidate for '{dep_stage}' has an error. Select a valid candidate first.",
                )

        step = await self.repo.get_step_or_404(run_id, stage)

        if step.status == "running":
            raise conflict("STEP_ALREADY_RUNNING", f"阶段 {stage} 正在执行中，请等待完成后再重试")

        run.status = "running"
        step.status = "running"
        await self.session.flush()

        attempt_number = len(step.candidates) + 1

        provider_id = override.get("provider_id")
        model_id = override.get("model_id")
        prompt_version_id = override.get("prompt_version_id")
        run_override = override.get("run_override", "")

        params = {
            "temperature": override.get("temperature", 0.7),
            "top_p": override.get("top_p", 1.0),
            "max_output_tokens": override.get("max_output_tokens", 4096),
            "timeout_seconds": override.get("timeout_seconds", 120),
        }

        if run.workflow_profile_id:
            step_config = await self.repo.get_workflow_step_config(
                run.workflow_profile_id, stage
            )
            if step_config:
                if not provider_id:
                    provider_id = step_config.provider_id
                if not model_id:
                    model_id = step_config.model_id
                if not prompt_version_id:
                    prompt_version_id = step_config.prompt_version_id
                if "temperature" not in override:
                    params["temperature"] = step_config.temperature
                if "top_p" not in override:
                    params["top_p"] = step_config.top_p
                if "max_output_tokens" not in override:
                    params["max_output_tokens"] = step_config.max_output_tokens
                if "timeout_seconds" not in override:
                    params["timeout_seconds"] = step_config.timeout_seconds

        override["prompt_version_id"] = prompt_version_id
        ctx_req = await self._build_context_request(run, stage, override)
        ctx_service = ContextService(self.session)
        ctx = await ctx_service.assemble(ctx_req)
        step.input_snapshot_json = ctx["input_snapshot_hash"]

        error_code = None
        error_message = None
        raw_response = ""
        parsed_output_json = None
        text_output = ""
        input_tokens = 0
        output_tokens = 0
        latency_ms = 0

        try:
            start = time.time()

            provider = await self._resolve_provider(provider_id)
            llm_request = LlmRequest(
                system_prompt=ctx["rendered_system_prompt"],
                user_prompt=ctx["rendered_user_prompt"],
                model=model_id or "mock-model",
                temperature=params["temperature"],
                top_p=params["top_p"],
                max_output_tokens=params["max_output_tokens"],
                timeout_seconds=params["timeout_seconds"],
            )

            response = await provider.complete(llm_request)
            raw_response = response.text
            input_tokens = response.input_tokens
            output_tokens = response.output_tokens
            latency_ms = response.latency_ms

            if stage != "writer":
                parsed = parse_json(raw_response)
                if parsed.valid:
                    try:
                        validated = validate_stage_output(stage, parsed.data)
                        if stage == "judge":
                            critic_step = await self.repo.get_step(run_id, "critic")
                            selected_issue_ids = []
                            if critic_step and critic_step.selected_issue_ids_json:
                                selected_issue_ids = json.loads(
                                    critic_step.selected_issue_ids_json
                                )
                            validated = validate_judge_output_for_selected_issues(
                                parsed.data, selected_issue_ids
                            ).model_dump()
                        parsed_output_json = json.dumps(validated, ensure_ascii=False)
                    except ValueError as ve:
                        stage_upper = stage.upper()
                        error_code = f"{stage_upper}_OUTPUT_CONTRACT_INVALID"
                        error_message = str(ve)
                        step.status = "failed"
                        run.status = "completed"
                    else:
                        text_output = raw_response
                        if stage == "reviser":
                            revised_text = validated.get("revised_text", "")
                            if revised_text and revised_text.strip():
                                text_output = revised_text
                            else:
                                error_code = "REVISER_OUTPUT_INVALID"
                                error_message = "Reviser returned valid JSON but missing or empty 'revised_text'. The candidate cannot be used."
                                step.status = "failed"
                                run.status = "completed"
                        elif stage == "judge":
                            judge_decision = validated.get("decision", "")
                            if not judge_decision:
                                error_code = "JUDGE_OUTPUT_INVALID"
                                error_message = f"Judge response missing 'decision' field. Got keys: {list(validated.keys())}"
                                step.status = "failed"
                                run.status = "completed"
                else:
                    error_code = "STRUCTURED_OUTPUT_INVALID"
                    error_message = parsed.error or "无法解析结构化输出"
                    step.status = "failed"
                    run.status = "completed"
            else:
                text_output = raw_response
                step.status = "completed"
                run.status = "completed"

        except Exception as e:
            error_code = getattr(e, "code", "LLM_ERROR")
            error_message = str(e)
            raw_response = ""
            step.status = "failed"
            run.status = "completed"

        latency_ms = int((time.time() - start) * 1000) if latency_ms == 0 else latency_ms

        candidate = await self.repo.create_candidate(
            step_id=step.id,
            attempt_number=attempt_number,
            provider_id=provider_id,
            model_id=model_id,
            prompt_version_id=prompt_version_id,
            parameters_json=json.dumps(params),
            run_override=run_override,
            rendered_system_prompt=ctx["rendered_system_prompt"],
            rendered_user_prompt=ctx["rendered_user_prompt"],
            raw_response=raw_response,
            parsed_output_json=parsed_output_json,
            text_output=text_output,
            error_code=error_code,
            error_message=error_message,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

        if not error_code:
            step.status = "completed"
            run.status = "completed"

        await self.session.flush()

        if stage == "writer" and text_output and run.chapter_id:
            try:
                from app.models.chapter import Chapter
                ch_stmt = select(Chapter).where(Chapter.id == run.chapter_id)
                ch_result = await self.session.execute(ch_stmt)
                ch = ch_result.scalar_one_or_none()
                if ch:
                    _save_to_disk(ch.title + " (初稿)", text_output)
            except Exception:
                pass

        return candidate

    async def select_candidate(self, run_id: str, stage: str, candidate_id: str):
        run = await self.repo.get_run_or_404(run_id)
        step = await self.repo.get_step_or_404(run_id, stage)

        candidate = next((c for c in step.candidates if c.id == candidate_id), None)
        if not candidate:
            raise bad_request("CANDIDATE_NOT_FOUND", "候选结果不存在")

        if candidate.error_code:
            raise bad_request("CANDIDATE_INVALID", "无法选中执行失败的候选结果")

        await self.repo.select_candidate(step, candidate_id)
        await self.repo.mark_downstream_stale(run, stage)

    async def cancel_run(self, run_id: str):
        run = await self.repo.get_run_or_404(run_id)
        run.status = "cancelled"
        await self.session.flush()

    async def preview_stage(self, run_id: str, stage: str, override: dict):
        run = await self.repo.get_run_or_404(run_id)
        ctx_req = await self._build_context_request(run, stage, override)
        ctx_service = ContextService(self.session)
        ctx = await ctx_service.assemble(ctx_req)
        return {
            "sources": ctx["sources"],
            "rendered_system_prompt": ctx["rendered_system_prompt"],
            "rendered_user_prompt": ctx["rendered_user_prompt"],
            "input_snapshot_hash": ctx["input_snapshot_hash"],
            "total_chars": ctx["total_chars"],
            "truncated": ctx["truncated"],
        }

    async def _build_context_request(self, run, stage: str, override: dict):
        prompt_version_id = override.get("prompt_version_id")
        run_override = override.get("run_override", "")

        ctx_req = ContextPreviewRequest(
            project_id=run.project_id,
            chapter_id=run.chapter_id,
            stage=stage,
            workflow_profile_id=run.workflow_profile_id,
            prompt_version_id=prompt_version_id,
            scene_instruction=run.scene_instruction,
            run_override=run_override,
            scene_plan=override.get("scene_plan"),
            draft_text=override.get("draft_text", ""),
            critic_report=override.get("critic_report"),
            selected_issues=override.get("selected_issues", []),
            revised_text=override.get("revised_text", ""),
            tempo_guardrails=override.get("tempo_guardrails"),
            chapter_function=override.get("chapter_function", ""),
            arc_phase=override.get("arc_phase", ""),
            reader_comes_for=override.get("reader_comes_for", ""),
            must_deliver=override.get("must_deliver", ""),
            must_not_deliver=override.get("must_not_deliver", ""),
            main_change=override.get("main_change", ""),
            main_payoff=override.get("main_payoff", ""),
            ending_hook=override.get("ending_hook", ""),
            hook_type=override.get("hook_type", ""),
            fuel_reserved_for_later=override.get("fuel_reserved_for_later", ""),
            target_length=override.get("target_length", 0),
            write_mode=override.get("write_mode", ""),
            continuation_anchor=override.get("continuation_anchor", ""),
            current_chapter_text=override.get("current_chapter_text", ""),
        )

        for prev_stage in self._previous_stages(stage):
            prev_step = await self.repo.get_step(run.id, prev_stage)
            if not prev_step or not prev_step.selected_candidate_id:
                continue
            prev_candidate = next(
                (c for c in prev_step.candidates if c.id == prev_step.selected_candidate_id), None
            )
            if not prev_candidate:
                continue

            if prev_stage == "planner":
                if prev_candidate.parsed_output_json:
                    ctx_req.scene_plan = json.loads(prev_candidate.parsed_output_json)
                    guardrails = ctx_req.scene_plan.get("tempo_guardrails")
                    if isinstance(guardrails, dict):
                        ctx_req.tempo_guardrails = guardrails
            elif prev_stage == "writer":
                ctx_req.draft_text = prev_candidate.text_output or prev_candidate.raw_response
            elif prev_stage == "critic":
                if prev_candidate.parsed_output_json:
                    ctx_req.critic_report = json.loads(prev_candidate.parsed_output_json)
                if prev_step.selected_issue_ids_json:
                    selected_ids = json.loads(prev_step.selected_issue_ids_json)
                    operation_by_issue = json.loads(
                        prev_step.selected_issue_operations_json or "{}"
                    )
                    issues_by_id = {
                        str(issue.get("issue_id")): {
                            **issue,
                            "issue_id": str(issue.get("issue_id")),
                        }
                        for issue in ctx_req.critic_report.get("issues", [])
                        if issue.get("issue_id") is not None
                    }
                    ctx_req.selected_issues = [
                        {
                            **issues_by_id[issue_id],
                            "selected_operation": operation_by_issue[issue_id],
                        }
                        for issue_id in selected_ids
                        if issue_id in issues_by_id and issue_id in operation_by_issue
                    ]
            elif prev_stage == "reviser":
                ctx_req.revised_text = prev_candidate.text_output or prev_candidate.raw_response

        return ctx_req

    async def select_critic_issues(
        self,
        run_id: str,
        issue_ids: list[str],
        operation_by_issue: dict[str, str] | None = None,
    ):
        run = await self.repo.get_run_or_404(run_id)
        step = await self.repo.get_step_or_404(run_id, "critic")

        if not step.selected_candidate_id:
            raise bad_request("CRITIC_NOT_SELECTED", "请先选择诊断结果")

        selected = next((c for c in step.candidates if c.id == step.selected_candidate_id), None)
        if not selected or not selected.parsed_output_json:
            raise bad_request("CRITIC_INVALID", "诊断结果无效")

        import json as _json
        critic_data = _json.loads(selected.parsed_output_json)
        issues_by_id = {
            str(issue.get("issue_id")): {
                **issue,
                "issue_id": str(issue.get("issue_id")),
            }
            for issue in critic_data.get("issues", [])
            if issue.get("issue_id") is not None
        }
        valid_ids = set(issues_by_id)
        for iid in issue_ids:
            if iid not in valid_ids:
                raise bad_request("ISSUE_NOT_FOUND", f"问题 {iid} 不在诊断报告中")

        operations = operation_by_issue or {}
        for issue_id, operation in operations.items():
            if issue_id not in issue_ids:
                raise bad_request(
                    "ISSUE_OPERATION_NOT_SELECTED",
                    f"问题 {issue_id} 未被选择，不能指定修订操作",
                )
            if operation not in REVISION_OPERATIONS:
                raise bad_request(
                    "INVALID_REVISION_OPERATION",
                    f"不支持的修订操作: {operation}",
                )

        selected_operations = {}
        for issue_id in issue_ids:
            operation = operations.get(issue_id)
            if not operation:
                operation = issues_by_id[issue_id].get("recommended_operation")
            if operation not in REVISION_OPERATIONS:
                raise bad_request(
                    "CRITIC_OPERATION_MISSING",
                    f"问题 {issue_id} 缺少有效的 recommended_operation",
                )
            selected_operations[issue_id] = operation

        step.selected_issue_ids_json = _json.dumps(issue_ids)
        step.selected_issue_operations_json = _json.dumps(selected_operations)
        await self.session.flush()

    async def accept_final_text(self, run_id: str, accept_type: str, manual_text: str | None = None):
        import json as _json
        from datetime import datetime, timezone

        run = await self.repo.get_run_or_404(run_id)
        if run.status not in ("completed", "running"):
            raise bad_request("RUN_NOT_READY", "运行未完成，无法采用")

        if not run.chapter_id:
            raise bad_request("NO_CHAPTER", "运行未关联章节")

        if run.accepted_at is not None:
            raise conflict(
                "ALREADY_ACCEPTED",
                f"This run was already accepted (type: {run.accepted_type}) at {run.accepted_at.isoformat()}."
                " Start a new run to submit a different version.",
            )

        valid_types = {"original", "revision", "judge", "manual"}
        if accept_type not in valid_types:
            raise bad_request(
                "INVALID_ACCEPT_TYPE",
                f"accept_type must be one of: {', '.join(sorted(valid_types))}",
            )
        if accept_type == "manual" and not manual_text:
            raise bad_request("MANUAL_TEXT_REQUIRED", "accept_type='manual' requires final_text")

        writer_step = await self.repo.get_step(run_id, "writer")
        reviser_step = await self.repo.get_step(run_id, "reviser")
        judge_step = await self.repo.get_step(run_id, "judge")

        writer_text = ""
        reviser_text = ""
        judge_final_text = ""

        if writer_step and writer_step.selected_candidate_id:
            candidate = next(
                (c for c in writer_step.candidates if c.id == writer_step.selected_candidate_id), None
            )
            if candidate:
                writer_text = candidate.text_output or candidate.raw_response

        if reviser_step and reviser_step.selected_candidate_id:
            candidate = next(
                (c for c in reviser_step.candidates if c.id == reviser_step.selected_candidate_id), None
            )
            if candidate and candidate.text_output:
                reviser_text = candidate.text_output

        if judge_step and judge_step.selected_candidate_id:
            judge_candidate = next(
                (c for c in judge_step.candidates if c.id == judge_step.selected_candidate_id), None
            )
            if judge_candidate and judge_candidate.parsed_output_json:
                judge_data = _json.loads(judge_candidate.parsed_output_json)
                judge_final_text = judge_data.get("final_text", "")

        if accept_type == "original":
            if not writer_text:
                raise bad_request("NO_ORIGINAL", "初稿不存在，无法选择保留初稿")
            final_text = writer_text
        elif accept_type == "revision":
            if not reviser_text:
                raise bad_request("NO_REVISION", "修订稿不存在，无法选择采用修订稿")
            final_text = reviser_text
        elif accept_type == "judge":
            final_text = judge_final_text or reviser_text or writer_text
            if not final_text:
                raise bad_request("NO_JUDGE_TEXT", "没有可用的审稿合并文本")
        elif accept_type == "manual":
            final_text = manual_text
        else:
            raise bad_request("INVALID_ACCEPT_TYPE", f"Unknown accept_type: {accept_type}")

        if not final_text:
            raise bad_request("NO_CONTENT", "没有可采用的文本")

        from app.models.chapter import Chapter, ChapterVersion
        stmt = select(Chapter).where(Chapter.id == run.chapter_id, Chapter.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        chapter = result.scalar_one_or_none()
        if not chapter:
            raise not_found("CHAPTER_NOT_FOUND", "章节不存在")

        existing_versions = await self.session.execute(
            select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id)
        )
        existing_versions = existing_versions.scalars().all()

        next_version = max((v.version_number for v in existing_versions), default=0) + 1

        candidate_ref = None
        if accept_type == "original":
            candidate_ref = writer_step.selected_candidate_id if writer_step else None
        elif accept_type == "revision":
            candidate_ref = reviser_step.selected_candidate_id if reviser_step else None
        elif accept_type == "judge":
            candidate_ref = judge_step.selected_candidate_id if judge_step else None

        version = ChapterVersion(
            chapter_id=chapter.id,
            version_number=next_version,
            source=accept_type,
            text=final_text,
            note=f"从运行 {run_id[:8]} 采用 ({accept_type})",
            generation_candidate_id=candidate_ref,
        )
        self.session.add(version)
        # SQLAlchemy applies the UUID default during flush, so materialize the
        # version id before storing it on the run record.
        await self.session.flush()
        chapter.current_text = final_text
        chapter.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run.status = "completed"
        run.accepted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run.accepted_type = accept_type
        run.accepted_version_id = version.id
        await self.session.flush()

        try:
            _save_to_disk(chapter.title, final_text)
        except Exception:
            pass

        return {"status": "ok", "source": accept_type, "version_number": next_version}

    def _previous_stages(self, stage: str) -> list[str]:
        stages = ["planner", "writer", "critic", "reviser", "judge"]
        try:
            idx = stages.index(stage)
        except ValueError:
            return []
        return stages[:idx]

    async def _required_stages(self, stage: str, run) -> list[str]:
        """Stages that MUST be completed and have a selected valid candidate
        before executing `stage`. Handles the Critic pass → skip Reviser path."""
        all_stages = self._previous_stages(stage)
        if "reviser" not in all_stages:
            return all_stages

        critic_step = await self.repo.get_step(run.id, "critic")
        critic_passed = False
        if critic_step and critic_step.selected_candidate_id:
            import json as _json
            critic_cand = next(
                (c for c in critic_step.candidates if c.id == critic_step.selected_candidate_id), None
            )
            if critic_cand and critic_cand.parsed_output_json:
                critic_data = _json.loads(critic_cand.parsed_output_json)
                critic_passed = critic_data.get("decision") == "pass"

        if critic_passed and "reviser" in all_stages:
            all_stages.remove("reviser")

        return all_stages

    async def _resolve_provider(self, provider_id: str | None):
        from app.models.provider import Provider
        from app.services.secret_service import decrypt_api_key
        from app.llm.mock import MockClient
        from app.llm.openai_compatible import OpenAiCompatibleClient

        if provider_id:
            stmt = select(Provider).where(Provider.id == provider_id)
            result = await self.session.execute(stmt)
            provider = result.scalar_one_or_none()
        else:
            stmt = select(Provider).where(Provider.is_builtin == True)
            result = await self.session.execute(stmt)
            provider = result.scalar_one_or_none()

        if not provider:
            return MockClient()

        api_key = decrypt_api_key(provider.encrypted_api_key) or ""

        if provider.provider_type == "mock":
            return MockClient()
        else:
            return OpenAiCompatibleClient(
                base_url=provider.base_url or "",
                api_key=api_key,
            )
