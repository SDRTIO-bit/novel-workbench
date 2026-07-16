from datetime import datetime
from pydantic import BaseModel, Field


class PromptVersionSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    profile_id: str
    version_number: int
    system_template: str
    user_template: str
    output_mode: str
    output_schema_name: str | None
    created_at: datetime


class PromptProfileSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    stage: str
    name: str
    description: str
    is_builtin: bool
    created_at: datetime
    updated_at: datetime
    latest_version: PromptVersionSchema | None = None


class PromptProfileListSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    stage: str
    name: str
    description: str
    is_builtin: bool
    created_at: datetime
    updated_at: datetime


class PromptCreate(BaseModel):
    stage: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    system_template: str = ""
    user_template: str = ""
    output_mode: str = "structured"
    output_schema_name: str | None = None


class PromptVersionCreate(BaseModel):
    system_template: str = ""
    user_template: str = ""
    output_mode: str = "structured"
    output_schema_name: str | None = None


class RenderPreviewRequest(BaseModel):
    system_template: str
    user_template: str
    variables: dict[str, str] = Field(default_factory=dict)


class RenderPreviewResponse(BaseModel):
    system_prompt: str
    user_prompt: str


class PromptExport(BaseModel):
    version: str = "1.0"
    profiles: list[dict]
