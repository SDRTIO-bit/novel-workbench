import json
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.errors import conflict, bad_request
from app.repositories.generation_repository import GenerationRepository
from app.services.context_service import ContextService
from app.schemas.context import ContextPreviewRequest
from app.llm.base import LlmRequest
from app.llm.parser import parse_json
from app.models.generation import GenerationRun


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

        ctx_service = ContextService(self.session)
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
        )

        for prev_stage in self._previous_stages(stage):
            prev_step = await self.repo.get_step(run_id, prev_stage)
            if prev_step and prev_step.selected_candidate_id:
                prev_candidate = next(
                    (c for c in prev_step.candidates if c.id == prev_step.selected_candidate_id), None
                )
                if prev_candidate and prev_candidate.parsed_output_json:
                    if prev_stage == "planner":
                        ctx_req.scene_plan = json.loads(prev_candidate.parsed_output_json)
                    elif prev_stage == "critic":
                        ctx_req.critic_report = json.loads(prev_candidate.parsed_output_json)
                    elif prev_stage == "writer":
                        ctx_req.draft_text = prev_candidate.text_output or prev_candidate.raw_response

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
                system_prompt=ctx["system_prompt"],
                user_prompt=ctx["user_prompt"],
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
                    parsed_output_json = json.dumps(parsed.data, ensure_ascii=False)
                    text_output = raw_response
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
            rendered_system_prompt=ctx["system_prompt"],
            rendered_user_prompt=ctx["user_prompt"],
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
        return candidate

    async def select_candidate(self, run_id: str, stage: str, candidate_id: str):
        run = await self.repo.get_run_or_404(run_id)
        step = await self.repo.get_step_or_404(run_id, stage)

        candidate = next((c for c in step.candidates if c.id == candidate_id), None)
        if not candidate:
            raise bad_request("CANDIDATE_NOT_FOUND", "候选结果不存在")

        if candidate.error_code and not candidate.parsed_output_json:
            raise bad_request("CANDIDATE_INVALID", "无法选中错误的候选结果")

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
            "system_prompt": ctx["system_prompt"],
            "user_prompt": ctx["user_prompt"],
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
        )

        for prev_stage in self._previous_stages(stage):
            prev_step = await self.repo.get_step(run.id, prev_stage)
            if prev_step and prev_step.selected_candidate_id:
                prev_candidate = next(
                    (c for c in prev_step.candidates if c.id == prev_step.selected_candidate_id), None
                )
                if prev_candidate and prev_candidate.parsed_output_json:
                    if prev_stage == "planner":
                        ctx_req.scene_plan = json.loads(prev_candidate.parsed_output_json)
                    elif prev_stage == "critic":
                        ctx_req.critic_report = json.loads(prev_candidate.parsed_output_json)
                        if prev_step.selected_issue_ids_json:
                            ctx_req.selected_issues = json.loads(prev_step.selected_issue_ids_json)
                    elif prev_stage == "writer":
                        ctx_req.draft_text = prev_candidate.text_output or prev_candidate.raw_response
                elif prev_stage == "reviser" and prev_candidate and prev_candidate.text_output:
                    ctx_req.revised_text = prev_candidate.text_output

        return ctx_req

    async def select_critic_issues(self, run_id: str, issue_ids: list[str]):
        run = await self.repo.get_run_or_404(run_id)
        step = await self.repo.get_step_or_404(run_id, "critic")

        if not step.selected_candidate_id:
            raise bad_request("CRITIC_NOT_SELECTED", "请先选择诊断结果")

        selected = next((c for c in step.candidates if c.id == step.selected_candidate_id), None)
        if not selected or not selected.parsed_output_json:
            raise bad_request("CRITIC_INVALID", "诊断结果无效")

        import json as _json
        critic_data = _json.loads(selected.parsed_output_json)
        valid_ids = {i.get("issue_id") for i in critic_data.get("issues", [])}
        for iid in issue_ids:
            if iid not in valid_ids:
                raise bad_request("ISSUE_NOT_FOUND", f"问题 {iid} 不在诊断报告中")

        step.selected_issue_ids_json = _json.dumps(issue_ids)
        await self.session.flush()

    async def accept_final_text(self, run_id: str):
        import json as _json
        from datetime import datetime, timezone

        run = await self.repo.get_run_or_404(run_id)
        if run.status not in ("completed", "running"):
            raise bad_request("RUN_NOT_READY", "运行未完成，无法采用")

        if not run.chapter_id:
            raise bad_request("NO_CHAPTER", "运行未关联章节")

        writer_step = await self.repo.get_step(run_id, "writer")
        reviser_step = await self.repo.get_step(run_id, "reviser")

        final_text = ""
        source = "writer"

        if writer_step and writer_step.selected_candidate_id:
            candidate = next(
                (c for c in writer_step.candidates if c.id == writer_step.selected_candidate_id), None
            )
            if candidate:
                final_text = candidate.text_output or candidate.raw_response

        if reviser_step and reviser_step.selected_candidate_id:
            candidate = next(
                (c for c in reviser_step.candidates if c.id == reviser_step.selected_candidate_id), None
            )
            if candidate and candidate.text_output:
                final_text = candidate.text_output
                source = "reviser"

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

        version = ChapterVersion(
            chapter_id=chapter.id,
            version_number=next_version,
            source=source,
            text=final_text,
            note=f"从运行 {run_id[:8]} 采用",
            generation_candidate_id=(
                writer_step.selected_candidate_id
                if source == "writer"
                else reviser_step.selected_candidate_id
                if source == "reviser"
                else None
            ),
        )
        self.session.add(version)
        chapter.current_text = final_text
        chapter.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run.status = "completed"
        await self.session.flush()

        return {"status": "ok", "source": source, "version_number": next_version}

    def _previous_stages(self, stage: str) -> list[str]:
        stages = ["planner", "writer", "critic", "reviser", "judge"]
        try:
            idx = stages.index(stage)
        except ValueError:
            return []
        return stages[:idx]

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
