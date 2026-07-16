from datetime import datetime
from pydantic import BaseModel, Field


class WorkflowStepSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    workflow_profile_id: str
    stage: str
    provider_id: str | None
    model_id: str | None
    prompt_version_id: str | None
    temperature: float
    top_p: float
    max_output_tokens: int
    timeout_seconds: int


class WorkflowProfileSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepSchema] = []


class WorkflowProfileListSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None


class WorkflowStepUpdate(BaseModel):
    provider_id: str | None = None
    model_id: str | None = None
    prompt_version_id: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    timeout_seconds: int | None = None
