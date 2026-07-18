import json
from app.mcp_utils import mcp_db
from app.services.generation_service import GenerationService
from app.models.workflow import WorkflowProfile
from app.models.provider import Provider
from sqlalchemy import select
from sqlalchemy.orm import selectinload


async def preview_context(
    run_id: str,
    stage: str,
    provider_id: str | None = None,
    model_id: str | None = None,
    prompt_version_id: str | None = None,
    max_output_tokens: int | None = None,
    run_override: str = "",
    scene_plan: str = "",
    draft_text: str = "",
    critic_report: str = "",
    selected_issues: str = "",
    revised_text: str = "",
) -> dict:
    """Preview the assembled prompt context for a stage without executing the LLM.

    Returns the full system_prompt, user_prompt, source breakdown, and hash.
    Use this to inspect what the LLM will receive before running execute_stage.
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
        ctx = await svc.preview_stage(run_id, stage, override)
        return {
            "sources": [s.model_dump() for s in ctx["sources"]],
            "system_prompt": ctx["rendered_system_prompt"],
            "user_prompt": ctx["rendered_user_prompt"],
            "prompt_meta": ctx["prompt_meta"],
            "llm_request_meta": ctx["llm_request_meta"],
            "input_snapshot_hash": ctx["input_snapshot_hash"],
            "total_chars": ctx["total_chars"],
            "truncated": ctx["truncated"],
        }


async def list_workflows() -> list[dict]:
    """List all workflow profiles available for generation runs."""
    async with mcp_db() as session:
        stmt = select(WorkflowProfile).options(selectinload(WorkflowProfile.steps))
        result = await session.execute(stmt)
        workflows = result.scalars().all()
        return [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "is_default": w.is_default,
                "steps": [
                    {
                        "stage": s.stage,
                        "provider_id": s.provider_id,
                        "model_id": s.model_id,
                        "prompt_version_id": s.prompt_version_id,
                    }
                    for s in w.steps
                ],
            }
            for w in workflows
        ]


async def list_providers() -> list[dict]:
    """List all configured LLM providers."""
    async with mcp_db() as session:
        stmt = select(Provider).options(selectinload(Provider.models))
        result = await session.execute(stmt)
        providers = result.scalars().all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "provider_type": p.provider_type,
                "base_url": p.base_url,
                "enabled": p.enabled,
                "models": [
                    {"model_id": m.model_id, "display_name": m.display_name, "enabled": m.enabled}
                    for m in p.models
                ],
            }
            for p in providers
        ]


async def create_provider(
    name: str,
    provider_type: str = "openai_compatible",
    base_url: str = "",
    api_key: str = "",
) -> dict:
    """Create a new LLM provider. For OpenAI-compatible APIs, set provider_type='openai_compatible' and provide base_url."""
    async with mcp_db() as session:
        from app.services.provider_service import ProviderService
        from app.services.secret_service import encrypt_api_key
        svc = ProviderService(session)
        provider = await svc.create_provider({
            "name": name,
            "provider_type": provider_type,
            "base_url": base_url,
            "api_key": api_key,
        })
        await session.commit()
        return {"id": provider.id, "name": provider.name, "provider_type": provider.provider_type, "enabled": provider.enabled}


async def create_provider_model(provider_id: str, model_id: str, display_name: str = "") -> dict:
    """Add a model to an existing provider."""
    async with mcp_db() as session:
        from app.services.provider_service import ProviderService
        svc = ProviderService(session)
        model = await svc.add_model(provider_id, {"model_id": model_id, "display_name": display_name or model_id})
        await session.commit()
        return {"id": model.id, "model_id": model.model_id, "display_name": model.display_name}


async def list_prompt_profiles(stage: str | None = None) -> list[dict]:
    """List prompt profiles, optionally filtered by pipeline stage."""
    async with mcp_db() as session:
        from app.models.prompt import PromptProfile
        stmt = select(PromptProfile).options(selectinload(PromptProfile.versions))
        if stage:
            stmt = stmt.where(PromptProfile.stage == stage)
        result = await session.execute(stmt)
        profiles = result.scalars().all()
        return [
            {
                "id": p.id,
                "stage": p.stage,
                "name": p.name,
                "description": p.description,
                "is_builtin": p.is_builtin,
                "versions": [
                    {
                        "id": v.id,
                        "version_number": v.version_number,
                        "output_mode": v.output_mode,
                        "output_schema_name": v.output_schema_name or "",
                    }
                    for v in p.versions
                ],
            }
            for p in profiles
        ]
