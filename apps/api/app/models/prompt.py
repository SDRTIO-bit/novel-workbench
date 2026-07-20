import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
from app.models.base import TimestampMixin


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


STAGES = ["planner", "writer", "critic", "reviser", "judge"]
OUTPUT_MODES = ["plain_text", "structured", "xml_story"]


class PromptProfile(Base, TimestampMixin):
    __tablename__ = "prompt_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    versions: Mapped[list["PromptVersion"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan",
        order_by="PromptVersion.version_number"
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_profiles.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    system_template: Mapped[str] = mapped_column(Text, default="")
    user_template: Mapped[str] = mapped_column(Text, default="")
    output_mode: Mapped[str] = mapped_column(String(50), default="structured")
    output_schema_name: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    profile: Mapped["PromptProfile"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("profile_id", "version_number", name="uq_prompt_version_number"),
    )
