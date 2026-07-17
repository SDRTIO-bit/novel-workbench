from pydantic import BaseModel, Field


STAGES = ["planner", "writer", "critic", "reviser", "judge"]


class ContextSource(BaseModel):
    name: str
    char_count: int
    truncated: bool


class ContextPreviewRequest(BaseModel):
    project_id: str
    chapter_id: str | None = None
    stage: str = Field(..., description="planner/writer/critic/reviser/judge")
    workflow_profile_id: str | None = None
    prompt_version_id: str | None = None
    scene_instruction: str = ""
    run_override: str = ""
    scene_plan: dict | None = None
    draft_text: str = ""
    critic_report: dict | None = None
    selected_issues: list[dict] = []
    revised_text: str = ""
    tempo_guardrails: dict | None = None
    writer_brief: dict | None = None

    chapter_function: str = ""
    arc_phase: str = ""
    reader_comes_for: str = ""
    must_deliver: str = ""
    must_not_deliver: str = ""
    main_change: str = ""
    main_payoff: str = ""
    ending_hook: str = ""
    hook_type: str = ""
    fuel_reserved_for_later: str = ""
    target_length: int = 0

    write_mode: str = ""
    continuation_anchor: str = ""
    current_chapter_text: str = ""


class ContextPreviewResponse(BaseModel):
    sources: list[ContextSource]
    rendered_system_prompt: str
    rendered_user_prompt: str
    input_snapshot_hash: str
    total_chars: int
    truncated: bool
