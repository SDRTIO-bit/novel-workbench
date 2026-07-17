import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models.base import TimestampMixin


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DetectorFeedback(Base, TimestampMixin):
    __tablename__ = "detector_feedbacks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chapters.id"))
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("generation_runs.id"))
    candidate_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("generation_candidates.id"))
    chapter_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chapter_versions.id"))
    detector_name: Mapped[str] = mapped_column(String(200), nullable=False)
    human_ratio: Mapped[float | None] = mapped_column(Float)
    suspected_ai_ratio: Mapped[float | None] = mapped_column(Float)
    ai_ratio: Mapped[float | None] = mapped_column(Float)
    spans_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
