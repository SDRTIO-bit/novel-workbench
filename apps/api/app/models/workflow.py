import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
from app.models.base import TimestampMixin


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


STAGES = ["planner", "writer", "critic", "reviser", "judge"]


class WorkflowProfile(Base, TimestampMixin):
    __tablename__ = "workflow_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    steps: Mapped[list["WorkflowStepConfig"]] = relationship(
        back_populates="workflow_profile", cascade="all, delete-orphan",
        order_by="WorkflowStepConfig.stage"
    )


class WorkflowStepConfig(Base):
    __tablename__ = "workflow_step_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_profiles.id"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("providers.id"))
    model_id: Mapped[str | None] = mapped_column(String(200))
    prompt_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prompt_versions.id"))
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    top_p: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)

    workflow_profile: Mapped["WorkflowProfile"] = relationship(back_populates="steps")
