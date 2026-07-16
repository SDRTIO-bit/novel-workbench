from datetime import datetime
from pydantic import BaseModel, Field


class ProviderModelSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    provider_id: str
    model_id: str
    display_name: str
    is_manual: bool
    enabled: bool


class ProviderSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    provider_type: str
    base_url: str
    has_api_key: bool
    extra_headers_json: str
    enabled: bool
    is_builtin: bool
    created_at: datetime
    updated_at: datetime
    models: list[ProviderModelSchema] = []


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider_type: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    extra_headers_json: str = "{}"
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    provider_type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    extra_headers_json: str | None = None
    enabled: bool | None = None


class ProviderModelCreate(BaseModel):
    model_id: str = Field(min_length=1, max_length=200)
    display_name: str = ""


class ProviderModelUpdate(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
