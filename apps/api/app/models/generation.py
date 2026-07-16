import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
from app.models.base import TimestampMixin


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


RUN_STATUSES = ["pending", "running", "completed", "cancelled", "failed"]
STEP_STATUSES = ["pending", "running", "completed", "stale", "failed", "skipped"]
STAGES = ["planner", "writer", "critic", "reviser", "judge"]


class GenerationRun(Base, TimestampMixin):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chapters.id"))
    workflow_profile_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workflow_profiles.id"))
    scene_instruction: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    accepted_type: Mapped[str | None] = mapped_column(String(50))
    accepted_version_id: Mapped[str | None] = mapped_column(String(36))

    steps: Mapped[list["GenerationStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
        order_by="GenerationStep.stage"
    )


class GenerationStep(Base, TimestampMixin):
    __tablename__ = "generation_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("generation_runs.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    selected_candidate_id: Mapped[str | None] = mapped_column(String(36))
    selected_issue_ids_json: Mapped[str | None] = mapped_column(Text)
    input_snapshot_json: Mapped[str | None] = mapped_column(Text)

    run: Mapped["GenerationRun"] = relationship(back_populates="steps")
    candidates: Mapped[list["GenerationCandidate"]] = relationship(
        back_populates="step", cascade="all, delete-orphan",
        order_by="GenerationCandidate.attempt_number"
    )


class GenerationCandidate(Base):
    __tablename__ = "generation_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("generation_steps.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provider_id: Mapped[str | None] = mapped_column(String(36))
    model_id: Mapped[str | None] = mapped_column(String(200))
    prompt_version_id: Mapped[str | None] = mapped_column(String(36))
    parameters_json: Mapped[str | None] = mapped_column(Text)
    run_override: Mapped[str] = mapped_column(Text, default="")
    rendered_system_prompt: Mapped[str] = mapped_column(Text, default="")
    rendered_user_prompt: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    parsed_output_json: Mapped[str | None] = mapped_column(Text)
    text_output: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    step: Mapped["GenerationStep"] = relationship(back_populates="candidates")
