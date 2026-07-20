import json
import time
import re
from hashlib import sha256

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
    validate_planner_contract_validation,
    validate_stage_output,
    validate_tempo_final_line,
)
from app.models.generation import GenerationRun
from app.services.critic_compiler import compile_critic_report, validate_critic_evidence
from app.services.tgbreak_service import (
    load_tgbreak_profile,
    persist_tgbreak_output,
)
from app.services.tgbreak_writer_adapter import (
    build_tgbreak_project_data_from_writer_context,
)
from app.services.writer_brief import compile_writer_input
from app.services.narrative_brief_compiler import compile_narrative_route_input
from app.services.reviser_patches import PatchApplicationError, apply_reviser_patches
from app.tgbreak.models import TgbreakOutput
from app.tgbreak.output import TgbreakOutputError, parse_tgbreak_response
from app.tgbreak.renderer import render_tgbreak


def _save_to_disk(title: str, text: str):
    chapters_dir = DATA_DIR / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*]', '', title).strip()
    filepath = chapters_dir / f"{safe}.txt"
    filepath.write_text(text, encoding="utf-8")


# The current built-in planner v2 template declares its contract via
# output_schema_name on the prompt version row. This is an explicit marker,
# not a heuristic: older versions, custom prompts, and user-edited variants
# of the built-in profile all carry a different (or empty) schema name and
# retain v1 compatibility.
EXPECTED_PLANNER_CONTRACT_VERSION = 2
PLANNER_V2_SCHEMA_NAME = "planner_v2"
EXPECTED_PLANNER_V3_CONTRACT_VERSION = 3
PLANNER_V3_SCHEMA_NAME = "planner_v3"
EXPECTED_CRITIC_CONTRACT_VERSION = 2
CRITIC_V2_SCHEMA_NAME = "critic_v2"
CRITIC_EVIDENCE_V1_SCHEMA_NAME = "critic_evidence_v1"
EXPECTED_CRITIC_EVIDENCE_CONTRACT_VERSION = 1
PLANNER_CONTRACT_VALIDATION_V1_SCHEMA_NAME = "planner_contract_validation_v1"
NARRATIVE_BEHAVIOUR_V1 = (
    "\n\n## 场景行动落地\n"
    "把关键选择落实为人物对现场可见物件、位置或身体动作的处理；"
    "让本可采用的另一条做法在行动中被放弃，不用解释性独白交代；"
    "让承诺或代价体现为时间、空间、资源或关系状态的具体变化；"
    "让关键行动引出他人可观察的反应或反制；"
    "在一个新发生、可验证的事实处结束。不得推翻已给出的事实边界。"
)


def _expected_planner_contract_version(stage: str, prompt_meta: dict | None) -> int | None:
    if stage == "planner":
        schema = (prompt_meta or {}).get("output_schema_name")
        if schema == PLANNER_V2_SCHEMA_NAME:
            return EXPECTED_PLANNER_CONTRACT_VERSION
        if schema == PLANNER_V3_SCHEMA_NAME:
            return EXPECTED_PLANNER_V3_CONTRACT_VERSION
    return None


def _expected_critic_contract_version(stage: str, prompt_meta: dict | None) -> int | None:
    if stage == "critic" and (prompt_meta or {}).get("output_schema_name") == CRITIC_V2_SCHEMA_NAME:
        return EXPECTED_CRITIC_CONTRACT_VERSION
    return None


def _response_format_for_prompt(prompt_meta: dict | None) -> str:
    return (
        "json_object"
        if (prompt_meta or {}).get("output_mode") == "structured"
        else "text"
    )


_STORY_RE = re.compile(r"<story>(.*?)</story>", re.DOTALL | re.IGNORECASE)


def _extract_story_from_xml_response(raw_response: str) -> tuple[str, str | None]:
    """Extract <story> content from XML-formatted Writer output.

    Returns (story_text, None) on success, or ("", error_code) on failure.
    Never calls an LLM — deterministic regex extraction only.
    """
    open_pos = raw_response.lower().find("<story>")
    close_pos = raw_response.lower().find("</story>")
    if open_pos == -1:
        return "", "XML_STORY_OPEN_TAG_MISSING"
    if close_pos == -1 or close_pos < open_pos:
        return "", "XML_STORY_CLOSING_TAG_MISSING"
    match = _STORY_RE.search(raw_response)
    if not match:
        return "", "XML_STORY_EXTRACTION_FAILED"
    story_text = match.group(1).strip()
    if not story_text:
        return "", "XML_STORY_EMPTY"
    return story_text, None


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

        step_config = None
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

        writer_prompt_mode = "builtin"
        tgbreak_profile_id = None
        if stage == "writer" and step_config:
            writer_prompt_mode = step_config.writer_prompt_mode or "builtin"
            tgbreak_profile_id = step_config.tgbreak_profile_id
        if writer_prompt_mode == "tgbreak":
            prompt_version_id = None
            params["writer_prompt_mode"] = "tgbreak"
            params["tgbreak_profile_id"] = tgbreak_profile_id
            params["reasoning_mode"] = "disabled"

        override["prompt_version_id"] = prompt_version_id
        ctx_req = await self._build_context_request(run, stage, override)
        ctx_service = ContextService(self.session)
        ctx = await ctx_service.assemble(
            ctx_req, resolve_prompt=writer_prompt_mode != "tgbreak"
        )
        self._append_writer_brief(
            stage,
            writer_prompt_mode,
            ctx,
            override.get("writer_behavior_mode") if stage == "writer" else None,
            instruction_block=override.pop("_instruction_block", ""),
        )
        # Transfer narrative route metadata from override → params for audit persistence
        if "_route_decision" in override:
            params["route_decision"] = override.pop("_route_decision")
        if "_compiled_brief_hash" in override:
            params["compiled_brief_hash"] = override.pop("_compiled_brief_hash")
        if "_instruction_hash" in override:
            params["instruction_hash"] = override.pop("_instruction_hash")
        if "_policy_metadata" in override:
            # Opaque experiment-metadata passthrough: persisted verbatim into
            # candidate params; the service never interprets its content.
            params["policy_metadata"] = override.pop("_policy_metadata")
        await self._append_judge_selection_envelope(run_id, stage, ctx)
        step.input_snapshot_json = ctx["input_snapshot_hash"]

        error_code = None
        error_message = None
        raw_response = ""
        model_parsed_output_json = None
        parsed_output_json = None
        compiler_trace_json = None
        text_output = ""
        input_tokens = 0
        output_tokens = 0
        latency_ms = 0
        finish_reason = None
        reasoning_tokens = None
        tgbreak_rendered = None
        tgbreak_output = None

        try:
            start = time.time()

            ordered_messages = None
            reasoning_mode = "disabled" if model_id == "deepseek-v4-pro" else None
            if reasoning_mode:
                params["thinking"] = reasoning_mode
            if writer_prompt_mode == "tgbreak":
                preset, profile = await load_tgbreak_profile(
                    self.session, tgbreak_profile_id
                )
                planner_candidate_id = await self._selected_candidate_id(
                    run_id, "planner"
                )
                project_data = build_tgbreak_project_data_from_writer_context(
                    ctx["variables"],
                    selected_planner_candidate_id=planner_candidate_id,
                )
                tgbreak_rendered = render_tgbreak(
                    preset,
                    profile,
                    project_data.variables,
                    chat_history=project_data.variables["interaction_record"],
                    user_message=project_data.variables["peip"],
                )
                ordered_messages = [
                    {"role": message.role, "content": message.content}
                    for message in tgbreak_rendered.messages
                ]
                serialized_messages = json.dumps(
                    [message.as_dict() for message in tgbreak_rendered.messages],
                    ensure_ascii=False,
                )
                ctx["rendered_system_prompt"] = serialized_messages
                ctx["rendered_user_prompt"] = project_data.variables["peip"]
                ctx["input_snapshot_hash"] = sha256(
                    json.dumps(ordered_messages, ensure_ascii=False).encode("utf-8")
                ).hexdigest()
                step.input_snapshot_json = ctx["input_snapshot_hash"]
                params.update({
                    "selected_planner_candidate_id": planner_candidate_id,
                    "source_preset_id": tgbreak_rendered.source_preset_id,
                    "source_preset_sha256": tgbreak_rendered.source_preset_sha256,
                    "resolved_entry_identifiers": (
                        tgbreak_rendered.resolved_entry_identifiers
                    ),
                })
                reasoning_mode = "disabled"

            provider = await self._resolve_provider(provider_id)
            llm_request = LlmRequest(
                system_prompt=ctx["rendered_system_prompt"],
                user_prompt=ctx["rendered_user_prompt"],
                model=model_id or "mock-model",
                temperature=params["temperature"],
                top_p=params["top_p"],
                max_output_tokens=params["max_output_tokens"],
                timeout_seconds=params["timeout_seconds"],
                response_format=_response_format_for_prompt(ctx.get("prompt_meta")),
                reasoning_mode=reasoning_mode,
                messages=ordered_messages,
            )
            params["response_format"] = llm_request.response_format

            response = await provider.complete(llm_request)
            raw_response = response.text
            input_tokens = response.input_tokens
            output_tokens = response.output_tokens
            latency_ms = response.latency_ms
            finish_reason = response.finish_reason
            reasoning_tokens = response.reasoning_tokens

            if writer_prompt_mode == "tgbreak":
                try:
                    tgbreak_output = parse_tgbreak_response(
                        raw_response,
                        source_preset_id=tgbreak_rendered.source_preset_id,
                        source_preset_sha256=tgbreak_rendered.source_preset_sha256,
                        resolved_entry_identifiers=(
                            tgbreak_rendered.resolved_entry_identifiers
                        ),
                        reasoning_tokens=reasoning_tokens,
                        requested_reasoning_mode="disabled",
                    )
                except TgbreakOutputError as exc:
                    error_code = "TGBREAK_OUTPUT_FORMAT_INVALID"
                    error_message = str(exc)
                    step.status = "failed"
                    run.status = "completed"
                    tgbreak_output = TgbreakOutput(
                        raw_response=raw_response,
                        draft_notes="",
                        draft_text="",
                        extra_modules=[],
                        source_preset_id=tgbreak_rendered.source_preset_id,
                        source_preset_sha256=tgbreak_rendered.source_preset_sha256,
                        resolved_entry_identifiers=(
                            tgbreak_rendered.resolved_entry_identifiers
                        ),
                        requested_reasoning_mode="disabled",
                        reasoning_tokens=reasoning_tokens,
                    )
                else:
                    text_output = tgbreak_output.draft_text
                    step.status = "completed"
                    run.status = "completed"
            elif llm_request.response_format == "json_object":
                if finish_reason == "length":
                    error_code = "STRUCTURED_OUTPUT_TRUNCATED"
                    error_message = (
                        "模型因达到 max_output_tokens 停止，结构化输出可能不完整"
                    )
                    step.status = "failed"
                    run.status = "completed"
                elif finish_reason not in (None, "stop"):
                    normalized_reason = str(finish_reason).upper()
                    error_code = f"STRUCTURED_OUTPUT_{normalized_reason}"
                    error_message = (
                        f"模型以 finish_reason={finish_reason} 停止，"
                        "结构化输出未进入合同解析"
                    )
                    step.status = "failed"
                    run.status = "completed"
                else:
                    parsed = parse_json(raw_response)
                    if parsed.valid:
                        try:
                            if (
                                stage == "critic"
                                and ctx.get("prompt_meta", {}).get("output_schema_name")
                                == CRITIC_EVIDENCE_V1_SCHEMA_NAME
                            ):
                                evidence = validate_critic_evidence(parsed.data)
                                model_parsed_output_json = json.dumps(
                                    evidence.model_dump(), ensure_ascii=False
                                )
                                numbered_draft = ContextService(self.session)._numbered_text(
                                    ctx_req.draft_text
                                )
                                compilation = compile_critic_report(
                                    evidence, ctx_req.scene_plan or {}, numbered_draft
                                )
                                validated = validate_stage_output(
                                    "critic", compilation.report.model_dump()
                                )
                                compiler_trace_json = json.dumps(
                                    compilation.trace.model_dump(), ensure_ascii=False
                                )
                            elif (
                                stage == "critic"
                                and ctx.get("prompt_meta", {}).get("output_schema_name")
                                == PLANNER_CONTRACT_VALIDATION_V1_SCHEMA_NAME
                            ):
                                validated = validate_planner_contract_validation(parsed.data).model_dump()
                            else:
                                expected_ver = _expected_planner_contract_version(
                                    stage, ctx.get("prompt_meta")
                                ) or _expected_critic_contract_version(
                                    stage, ctx.get("prompt_meta")
                                )
                                validated = validate_stage_output(stage, parsed.data, expected_version=expected_ver)
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
                            error_message = str(ve)
                            if (
                                stage == "critic"
                                and ctx.get("prompt_meta", {}).get("output_schema_name")
                                == CRITIC_EVIDENCE_V1_SCHEMA_NAME
                            ):
                                if error_message.startswith("CRITIC_EVIDENCE_INVALID"):
                                    error_code = "CRITIC_EVIDENCE_INVALID"
                                elif error_message.startswith("CRITIC_OUTPUT_CONTRACT_INVALID"):
                                    error_code = "CRITIC_OUTPUT_CONTRACT_INVALID"
                                else:
                                    error_code = "CRITIC_COMPILATION_FAILED"
                            elif (
                                stage == "critic"
                                and ctx.get("prompt_meta", {}).get("output_schema_name")
                                == PLANNER_CONTRACT_VALIDATION_V1_SCHEMA_NAME
                            ):
                                if error_message.startswith("PLANNER_CONTRACT_VALIDATION_INVALID"):
                                    error_code = "PLANNER_CONTRACT_VALIDATION_INVALID"
                                else:
                                    error_code = "CRITIC_OUTPUT_CONTRACT_INVALID"
                            else:
                                stage_upper = stage.upper()
                                error_code = f"{stage_upper}_OUTPUT_CONTRACT_INVALID"
                            step.status = "failed"
                            run.status = "completed"
                        else:
                            if stage == "reviser":
                                applied = apply_reviser_patches(
                                    ctx_req.draft_text,
                                    validated.get("patches", []),
                                    ctx_req.critic_report,
                                )
                                text_output = applied.text
                                compiler_trace_json = json.dumps({
                                    "patch_application": {
                                        "changed_paragraph_ids": applied.changed_paragraph_ids,
                                        "unchanged_ratio": applied.unchanged_ratio,
                                    }
                                }, ensure_ascii=False)
                            elif stage == "judge":
                                text_output = raw_response
                                judge_decision = validated.get("decision", "")
                                if not judge_decision:
                                    error_code = "JUDGE_OUTPUT_INVALID"
                                    error_message = f"Judge response missing 'decision' field. Got keys: {list(validated.keys())}"
                                    step.status = "failed"
                                    run.status = "completed"
                            else:
                                text_output = raw_response
                    else:
                        error_code = "STRUCTURED_OUTPUT_INVALID"
                        error_message = parsed.error or "无法解析结构化输出"
                        step.status = "failed"
                        run.status = "completed"
            else:
                output_mode = (ctx.get("prompt_meta") or {}).get("output_mode", "plain_text")
                if output_mode == "xml_story":
                    story_text, extract_error = _extract_story_from_xml_response(raw_response)
                    if extract_error:
                        error_code = extract_error
                        error_message = f"Story extraction failed: {extract_error}"
                        step.status = "failed"
                        run.status = "completed"
                        text_output = ""
                    else:
                        text_output = story_text
                        step.status = "completed"
                        run.status = "completed"
                else:
                    text_output = raw_response
                    step.status = "completed"
                    run.status = "completed"

            if not error_code and stage in ("writer", "reviser"):
                try:
                    validate_tempo_final_line(text_output, ctx_req.tempo_guardrails)
                except ValueError as tempo_error:
                    error_message = str(tempo_error)
                    error_code = (
                        "TEMPO_FINAL_LINE_MISMATCH"
                        if error_message.startswith("TEMPO_FINAL_LINE_MISMATCH")
                        else "LLM_ERROR"
                    )
                    step.status = "failed"
                    run.status = "completed"

        except Exception as e:
            error_code = getattr(e, "code", "LLM_ERROR")
            error_message = str(e)
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
            model_parsed_output_json=model_parsed_output_json,
            parsed_output_json=parsed_output_json,
            compiler_trace_json=compiler_trace_json,
            text_output=text_output,
            error_code=error_code,
            error_message=error_message,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            reasoning_tokens=reasoning_tokens,
        )

        if tgbreak_output is not None:
            tgbreak_record = await persist_tgbreak_output(
                self.session, candidate.id, tgbreak_output
            )
            params["tgbreak_output_record_id"] = tgbreak_record.id
            candidate.parameters_json = json.dumps(params)

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

    async def _selected_candidate_id(self, run_id: str, stage: str) -> str | None:
        step = await self.repo.get_step(run_id, stage)
        return step.selected_candidate_id if step else None

    async def select_candidate(self, run_id: str, stage: str, candidate_id: str):
        run = await self.repo.get_run_or_404(run_id)
        step = await self.repo.get_step_or_404(run_id, stage)
        await self.session.refresh(step, ["candidates"])

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
        await self._append_judge_selection_envelope(run_id, stage, ctx)
        max_output_tokens = override.get("max_output_tokens", 4096)
        if run.workflow_profile_id and "max_output_tokens" not in override:
            step_config = await self.repo.get_workflow_step_config(
                run.workflow_profile_id, stage
            )
            if step_config:
                max_output_tokens = step_config.max_output_tokens
        return {
            "sources": ctx["sources"],
            "rendered_system_prompt": ctx["rendered_system_prompt"],
            "rendered_user_prompt": ctx["rendered_user_prompt"],
            "prompt_meta": ctx["prompt_meta"],
            "llm_request_meta": {
                "response_format": _response_format_for_prompt(ctx.get("prompt_meta")),
                "max_output_tokens": max_output_tokens,
            },
            "input_snapshot_hash": ctx["input_snapshot_hash"],
            "total_chars": ctx["total_chars"],
            "truncated": ctx["truncated"],
        }

    async def _append_judge_selection_envelope(self, run_id: str, stage: str, ctx: dict) -> None:
        if stage != "judge":
            return
        critic_step = await self.repo.get_step(run_id, "critic")
        if not critic_step or not critic_step.selected_issue_ids_json:
            return
        selected_issue_ids = json.loads(critic_step.selected_issue_ids_json)
        selected_payload = json.dumps(
            [{"issue_id": issue_id} for issue_id in selected_issue_ids],
            ensure_ascii=False,
        )
        ctx["rendered_user_prompt"] += f"\n<!-- SELECTED_ISSUES_JSON={selected_payload} -->"
        ctx["rendered_user_prompt"] += (
            "\n\n## 固定段落编号（仅供定位；不要抄入 final_text）\n"
            "原稿：\n"
            f"{ctx['variables'].get('numbered_draft', '')}\n\n"
            "修订稿：\n"
            f"{ctx['variables'].get('numbered_revised_text', '')}"
        )
        ctx["input_snapshot_hash"] = sha256(
            (
                ctx["input_snapshot_hash"]
                + selected_payload
                + ctx["variables"].get("numbered_draft", "")
                + ctx["variables"].get("numbered_revised_text", "")
            ).encode("utf-8")
        ).hexdigest()

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
            writer_brief=override.get("writer_brief"),
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
                    if stage == "writer":
                        writer_input_mode = override.get("writer_input_mode", "writer_brief")
                        if writer_input_mode == "narrative_route":
                            try:
                                route_input = compile_narrative_route_input(
                                    ctx_req.scene_plan,
                                    {},
                                    override.get("route_policy_version", "narrative-route-v1"),
                                    planner_candidate_id=prev_candidate.id,
                                )
                                ctx_req.writer_brief = route_input.compiled_brief
                                # Stash route metadata for later use by
                                # _append_writer_brief and candidate params.
                                override["_route_decision"] = route_input.decision.model_dump()
                                override["_instruction_block"] = route_input.instruction_block
                                override["_instruction_hash"] = route_input.instruction_hash
                                override["_compiled_brief_hash"] = route_input.compiled_brief_hash
                            except ValueError as brief_error:
                                raise bad_request(
                                    "WRITER_BRIEF_INVALID",
                                    "所选 Planner 候选无法编译为 Narrative Route 输入"
                                    f"（需要有效的 planner v2 输出）: {brief_error}",
                                ) from brief_error
                        else:
                            try:
                                ctx_req.writer_brief = compile_writer_input(
                                    ctx_req.scene_plan, writer_input_mode
                                )
                            except ValueError as brief_error:
                                raise bad_request(
                                    "WRITER_BRIEF_INVALID",
                                    "所选 Planner 候选无法编译为 Writer 输入"
                                    f"（需要有效的实验输入模式与 planner v2 输出）: {brief_error}",
                                ) from brief_error
                    guardrails = ctx_req.scene_plan.get("tempo_guardrails")
                    # An explicit per-run guardrail is an author decision. The
                    # planner may supply a fallback, but must not silently
                    # weaken or replace it for downstream stages.
                    if isinstance(guardrails, dict) and ctx_req.tempo_guardrails is None:
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

    @staticmethod
    def _append_writer_brief(
        stage: str,
        writer_prompt_mode: str,
        ctx: dict,
        writer_behavior_mode: str | None = None,
        *,
        instruction_block: str = "",
    ):
        """Place the short action brief last, adjacent to the writing order."""
        if stage != "writer" or writer_prompt_mode != "builtin":
            return
        brief = ctx.get("variables", {}).get("writer_brief")
        if not brief:
            return
        # Serialize brief dict to text
        if isinstance(brief, dict):
            brief_lines = [f"{key}: {value}" for key, value in brief.items()
                           if key not in ("v3_blocks", "mode")]
            brief_text = "\n".join(brief_lines)
        else:
            brief_text = str(brief)
        prompt_addition = (
            "\n\n## Writer Brief（只含现场行动信息）\n"
            f"{brief_text}\n\n"
            "只输出场景正文；用可见行动处理这个具体麻烦，并在 stop_state 成立处停止。"
        )
        # Append v3 blocks if present
        if isinstance(brief, dict) and brief.get("v3_blocks"):
            prompt_addition += f"\n\n{brief['v3_blocks']}"
        if writer_behavior_mode == "narrative_behaviour_v1":
            prompt_addition += NARRATIVE_BEHAVIOUR_V1
        if instruction_block:
            prompt_addition += instruction_block
        ctx["rendered_user_prompt"] += prompt_addition
        ctx["input_snapshot_hash"] = sha256(
            (ctx["input_snapshot_hash"] + prompt_addition).encode("utf-8")
        ).hexdigest()

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

        valid_types = {"original", "revision", "manual"}
        if accept_type not in valid_types:
            raise bad_request(
                "INVALID_ACCEPT_TYPE",
                f"accept_type must be one of: {', '.join(sorted(valid_types))}",
            )
        if accept_type == "manual" and not manual_text:
            raise bad_request("MANUAL_TEXT_REQUIRED", "accept_type='manual' requires final_text")

        writer_step = await self.repo.get_step(run_id, "writer")
        reviser_step = await self.repo.get_step(run_id, "reviser")

        writer_text = ""
        reviser_text = ""

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

        if accept_type == "original":
            if not writer_text:
                raise bad_request("NO_ORIGINAL", "初稿不存在，无法选择保留初稿")
            final_text = writer_text
        elif accept_type == "revision":
            if not reviser_text:
                raise bad_request("NO_REVISION", "修订稿不存在，无法选择采用修订稿")
            final_text = reviser_text
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
