from datetime import datetime
from pydantic import BaseModel, Field


class ProjectDocumentSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    kind: str
    title: str
    content: str
    sort_order: int
    updated_at: datetime


class ProjectSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    genre: str
    author_note: str
    default_pov: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    documents: list[ProjectDocumentSchema] = []


class ProjectListSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    genre: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    genre: str = ""
    author_note: str = ""
    default_pov: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    genre: str | None = None
    author_note: str | None = None
    default_pov: str | None = None


class DocumentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
