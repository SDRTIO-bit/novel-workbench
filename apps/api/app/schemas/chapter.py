from datetime import datetime
from pydantic import BaseModel, Field


class ChapterCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    sort_order: int = Field(default=0, ge=0)
    current_text: str = ""


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    current_text: str | None = None
    expected_updated_at: datetime


class ChapterReorderItem(BaseModel):
    id: str
    sort_order: int


class ChapterReorder(BaseModel):
    items: list[ChapterReorderItem]


class ChapterVersionSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    chapter_id: str
    version_number: int
    source: str
    text: str
    note: str
    generation_candidate_id: str | None
    created_at: datetime


class ChapterSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    title: str
    sort_order: int
    current_text: str
    status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ChapterListSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    title: str
    sort_order: int
    status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
