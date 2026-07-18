import json
from app.mcp_utils import mcp_db
from app.models.prompt import PromptVersion
from app.services.generation_service import (
    CRITIC_V2_SCHEMA_NAME,
    EXPECTED_CRITIC_CONTRACT_VERSION,
    EXPECTED_PLANNER_CONTRACT_VERSION,
    PLANNER_V2_SCHEMA_NAME,
    GenerationService,
)


async def _candidate_contract_meta(session, stage: str, prompt_version_id: str | None) -> dict:
    """Return contract metadata for the exact prompt version recorded on a candidate."""
    output_schema_name = ""
    output_mode = ""
    if prompt_version_id:
        version = await session.get(PromptVersion, prompt_version_id)
        if version:
            output_schema_name = version.output_schema_name or ""
            output_mode = version.output_mode
    return {
        "prompt_version_id": prompt_version_id or "",
        "output_schema_name": output_schema_name,
        "output_mode": output_mode,
        "response_format": (
            "json_object" if output_mode == "structured" else "text"
        ),
        "expected_contract_version": (
            EXPECTED_PLANNER_CONTRACT_VERSION
            if stage == "planner" and output_schema_name == PLANNER_V2_SCHEMA_NAME
            else None
        ),
        "expected_critic_contract_version": (
            EXPECTED_CRITIC_CONTRACT_VERSION
            if stage == "critic" and output_schema_name == CRITIC_V2_SCHEMA_NAME
            else None
        ),
    }


def _candidate_max_output_tokens(candidate) -> int | None:
    try:
        return json.loads(candidate.parameters_json or "{}").get("max_output_tokens")
    except (TypeError, ValueError):
        return None


async def list_runs(project_id: str) -> list[dict]:
    """List all generation runs for a project."""
    async with mcp_db() as session:
        svc = GenerationService(session)
        runs = await svc.list_runs(project_id)
        return [
            {
                "id": r.id,
                "project_id": r.project_id,
                "chapter_id": r.chapter_id,
                "status": r.status,
                "scene_instruction": r.scene_instruction,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in runs
        ]


async def create_run(
    project_id: str,
    scene_instruction: str,
    chapter_id: str | None = None,
    workflow_profile_id: str | None = None,
) -> dict:
    """Create a new generation run. A run goes through the 5-stage pipeline: planner → writer → critic → reviser → judge."""
    async with mcp_db() as session:
        svc = GenerationService(session)
        run = await svc.create_run(
            project_id=project_id,
            chapter_id=chapter_id,
            workflow_profile_id=workflow_profile_id,
            scene_instruction=scene_instruction,
        )
        await session.commit()
        steps = [
            {"stage": s.stage, "status": s.status}
            for s in run.steps
        ] if hasattr(run, 'steps') else []
        return {
            "id": run.id,
            "status": run.status,
            "steps": steps,
        }


async def get_run(run_id: str) -> dict:
    """Get generation run detail including all step statuses and candidate summaries."""
    async with mcp_db() as session:
        svc = GenerationService(session)
        run = await svc.get_run(run_id)
        steps_data = []
        for step in run.steps:
            candidates = [
                {
                    "id": c.id,
                    "attempt": c.attempt_number,
                    "model": c.model_id,
                    "is_selected": c.is_selected,
                    "has_error": bool(c.error_code),
                    "text_preview": (c.text_output or c.raw_response or "")[:200],
                }
                for c in step.candidates
            ]
            steps_data.append({
                "stage": step.stage,
                "status": step.status,
                "selected_candidate_id": step.selected_candidate_id,
                "candidates": candidates,
            })
        return {
            "id": run.id,
            "project_id": run.project_id,
            "chapter_id": run.chapter_id,
            "workflow_profile_id": run.workflow_profile_id,
            "status": run.status,
            "scene_instruction": run.scene_instruction,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "steps": steps_data,
        }


async def execute_stage(
    run_id: str,
    stage: str,
    provider_id: str | None = None,
    model_id: str | None = None,
    prompt_version_id: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_output_tokens: int | None = None,
    run_override: str = "",
    scene_plan: str = "",
    draft_text: str = "",
    critic_report: str = "",
    selected_issues: str = "",
    revised_text: str = "",
) -> dict:
    """Execute a single stage (planner/writer/critic/reviser/judge) in a generation run.

    The stage parameter must be one of: 'planner', 'writer', 'critic', 'reviser', 'judge'.
    Pipeline order matters — you cannot execute later stages before earlier ones complete.
    Each stage consumes outputs from previous stages automatically.

    Override fields (scene_plan, draft_text, critic_report, selected_issues, revised_text)
    should be provided as JSON strings. They override auto-collected prior-stage outputs.
    selected_issues expects a JSON array of issue_id strings like '["issue-1","issue-2"]'.
    """
    async with mcp_db() as session:
        svc = GenerationService(session)
        override = {"run_override": run_override}
        if provider_id is not None:
            override["provider_id"] = provider_id
        if model_id is not None:
            override["model_id"] = model_id
        if prompt_version_id is not None:
            override["prompt_version_id"] = prompt_version_id
        if temperature is not None:
            override["temperature"] = temperature
        if top_p is not None:
            override["top_p"] = top_p
        if max_output_tokens is not None:
            override["max_output_tokens"] = max_output_tokens
        if scene_plan:
            override["scene_plan"] = json.loads(scene_plan)
        if draft_text:
            override["draft_text"] = draft_text
        if critic_report:
            override["critic_report"] = json.loads(critic_report)
        if selected_issues:
            override["selected_issues"] = json.loads(selected_issues)
        if revised_text:
            override["revised_text"] = revised_text
        candidate = await svc.execute_stage(run_id, stage, override)
        await session.commit()
        contract_meta = await _candidate_contract_meta(session, stage, candidate.prompt_version_id)
        return {
            "candidate_id": candidate.id,
            "attempt": candidate.attempt_number,
            "stage": stage,
            "error_code": candidate.error_code,
            "error_message": candidate.error_message,
            "text_output": candidate.text_output,
            "text_preview": (candidate.text_output or "")[:500],
            "input_tokens": candidate.input_tokens,
            "output_tokens": candidate.output_tokens,
            "latency_ms": candidate.latency_ms,
            "finish_reason": candidate.finish_reason,
            "reasoning_tokens": candidate.reasoning_tokens,
            "response_format": contract_meta["response_format"],
            "max_output_tokens": _candidate_max_output_tokens(candidate),
            "prompt_version_id": contract_meta["prompt_version_id"],
            "output_schema_name": contract_meta["output_schema_name"],
            "expected_contract_version": contract_meta["expected_contract_version"],
            "expected_critic_contract_version": contract_meta["expected_critic_contract_version"],
            "parsed_output_json": candidate.parsed_output_json,
        }


async def select_candidate(run_id: str, stage: str, candidate_id: str) -> dict:
    """Select a candidate output for a stage. This makes it the official result used by downstream stages."""
    async with mcp_db() as session:
        svc = GenerationService(session)
        await svc.select_candidate(run_id, stage, candidate_id)
        await session.commit()
        return {"status": "selected", "run_id": run_id, "stage": stage, "candidate_id": candidate_id}


async def select_critic_issues(
    run_id: str, issue_ids: list[str], operation_by_issue: str = ""
) -> dict:
    """After critic stage, select issues and optionally pass a JSON issue-to-operation mapping."""
    async with mcp_db() as session:
        svc = GenerationService(session)
        operations = json.loads(operation_by_issue) if operation_by_issue else {}
        await svc.select_critic_issues(run_id, issue_ids, operations)
        await session.commit()
        return {"status": "ok", "selected_count": len(issue_ids)}


async def cancel_run(run_id: str) -> dict:
    """Cancel a running generation run."""
    async with mcp_db() as session:
        svc = GenerationService(session)
        await svc.cancel_run(run_id)
        await session.commit()
        return {"status": "cancelled"}


async def accept_final_text(run_id: str, accept_type: str = "revision", final_text: str | None = None) -> dict:
    """Accept the generated text and write it back to the chapter.

    accept_type must be one of:
    - 'original': keep the writer's first draft
    - 'revision': use the reviser's revised text
    - 'judge': use the judge's merged final_text
    - 'manual': use the final_text parameter directly

    The Judge's recommendation is just a suggestion — YOU make the final decision.
    This creates a chapter version snapshot and saves to disk.
    """
    async with mcp_db() as session:
        svc = GenerationService(session)
        result = await svc.accept_final_text(run_id, accept_type, final_text)
        await session.commit()
        return result


async def get_stage_status(run_id: str, stage: str) -> dict:
    """Get detailed status of a specific stage including all candidates."""
    async with mcp_db() as session:
        svc = GenerationService(session)
        run = await svc.get_run(run_id)
        step = None
        for s in run.steps:
            if s.stage == stage:
                step = s
                break
        if not step:
            return {"error": f"Stage '{stage}' not found in run"}
        candidates = []
        for c in step.candidates:
            contract_meta = await _candidate_contract_meta(session, step.stage, c.prompt_version_id)
            candidates.append({
                "id": c.id,
                "attempt": c.attempt_number,
                "model": c.model_id,
                "is_selected": c.is_selected,
                "has_error": bool(c.error_code),
                "error_message": c.error_message,
                "text_output": c.text_output or "",
                "prompt_version_id": c.prompt_version_id or "",
                "raw_response": c.raw_response or "",
                "parsed_output_json": c.parsed_output_json,
                "rendered_user_prompt": c.rendered_user_prompt or "",
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "latency_ms": c.latency_ms,
                "finish_reason": c.finish_reason,
                "reasoning_tokens": c.reasoning_tokens,
                "response_format": contract_meta["response_format"],
                "max_output_tokens": _candidate_max_output_tokens(c),
                "expected_critic_contract_version": contract_meta["expected_critic_contract_version"],
            })
        return {
            "stage": step.stage,
            "status": step.status,
            "selected_candidate_id": step.selected_candidate_id,
            "candidates": candidates,
        }
