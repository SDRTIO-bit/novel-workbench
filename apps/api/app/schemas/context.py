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


class ContextPreviewResponse(BaseModel):
    sources: list[ContextSource]
    rendered_system_prompt: str
    rendered_user_prompt: str
    input_snapshot_hash: str
    total_chars: int
    truncated: bool
