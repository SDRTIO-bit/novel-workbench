from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class DetectorSpan(BaseModel):
    label: str = "human"
    start_paragraph: int = Field(ge=1)
    end_paragraph: int = Field(ge=1)
    transition_ids: list[str] = Field(default_factory=list)
    excerpt: str = ""

    @model_validator(mode="after")
    def check_order(self):
        if self.start_paragraph > self.end_paragraph:
            raise ValueError("start_paragraph 不能大于 end_paragraph")
        return self


class DetectorFeedbackCreate(BaseModel):
    project_id: str
    chapter_id: str | None = None
    run_id: str | None = None
    candidate_id: str | None = None
    chapter_version_id: str | None = None
    detector_name: str = Field(min_length=1)
    human_ratio: float | None = Field(default=None, ge=0, le=100)
    suspected_ai_ratio: float | None = Field(default=None, ge=0, le=100)
    ai_ratio: float | None = Field(default=None, ge=0, le=100)
    spans: list[DetectorSpan] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def check_ratios(self):
        ratios = [self.human_ratio, self.suspected_ai_ratio, self.ai_ratio]
        if all(r is not None for r in ratios):
            total = sum(ratios)  # type: ignore
            if total < 99.5 or total > 100.5:
                raise ValueError(
                    f"检测比例总和必须在 99.5-100.5 之间，当前为 {total}"
                )
        return self

    @model_validator(mode="after")
    def check_references(self):
        if not self.candidate_id and not self.chapter_version_id:
            raise ValueError("candidate_id 和 chapter_version_id 至少提供一个")
        return self


class DetectorFeedbackUpdate(BaseModel):
    detector_name: str | None = None
    human_ratio: float | None = Field(default=None, ge=0, le=100)
    suspected_ai_ratio: float | None = Field(default=None, ge=0, le=100)
    ai_ratio: float | None = Field(default=None, ge=0, le=100)
    spans: list[DetectorSpan] | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check_ratios(self):
        ratios = [self.human_ratio, self.suspected_ai_ratio, self.ai_ratio]
        if all(r is not None for r in ratios):
            total = sum(ratios)  # type: ignore
            if total < 99.5 or total > 100.5:
                raise ValueError(
                    f"检测比例总和必须在 99.5-100.5 之间，当前为 {total}"
                )
        return self


class DetectorFeedbackSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    chapter_id: str | None = None
    run_id: str | None = None
    candidate_id: str | None = None
    chapter_version_id: str | None = None
    detector_name: str
    human_ratio: float | None = None
    suspected_ai_ratio: float | None = None
    ai_ratio: float | None = None
    spans_json: str = "[]"
    notes: str = ""
    created_at: datetime
    updated_at: datetime
