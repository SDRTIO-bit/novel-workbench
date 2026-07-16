from datetime import datetime
from pydantic import BaseModel, Field

STAGES = ["planner", "writer", "critic", "reviser", "judge"]


class ParametersSchema(BaseModel):
    temperature: float = 0.7
    top_p: float = 1.0
    max_output_tokens: int = 4096
    timeout_seconds: int = 120


class CandidateSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    step_id: str
    attempt_number: int
    provider_id: str | None = None
    model_id: str | None = None
    prompt_version_id: str | None = None
    parameters_json: str | None = None
    run_override: str = ""
    rendered_system_prompt: str = ""
    rendered_user_prompt: str = ""
    raw_response: str = ""
    parsed_output_json: str | None = None
    text_output: str = ""
    error_code: str | None = None
    error_message: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    is_selected: bool = False
    created_at: datetime


class StepSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    run_id: str
    stage: str
    status: str
    selected_candidate_id: str | None = None
    selected_issue_ids_json: str | None = None
    input_snapshot_json: str | None = None
    candidates: list[CandidateSchema] = []
    created_at: datetime
    updated_at: datetime


class RunSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    chapter_id: str | None = None
    workflow_profile_id: str | None = None
    scene_instruction: str = ""
    status: str
    steps: list[StepSchema] = []
    created_at: datetime
    updated_at: datetime


class RunListSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    chapter_id: str | None = None
    workflow_profile_id: str | None = None
    scene_instruction: str = ""
    status: str
    created_at: datetime
    updated_at: datetime


class CreateRunRequest(BaseModel):
    project_id: str
    chapter_id: str | None = None
    workflow_profile_id: str | None = None
    scene_instruction: str = ""


class StageOverrideRequest(BaseModel):
    run_override: str = ""
    provider_id: str | None = None
    model_id: str | None = None
    prompt_version_id: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    timeout_seconds: int | None = None


class AcceptFinalRequest(BaseModel):
    accept_type: str = Field(
        description="One of: original, revision, judge, manual"
    )
    final_text: str | None = Field(
        default=None, description="Required when accept_type is 'manual'"
    )


class SelectIssuesRequest(BaseModel):
    issue_ids: list[str] = Field(min_length=1)
