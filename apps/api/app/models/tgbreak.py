import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SillyTavernPreset(Base):
    __tablename__ = "sillytavern_presets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    source_format_version: Mapped[str] = mapped_column(String(100), default="unknown", nullable=False)
    top_level_keys_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    unsupported_fields_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    parse_mode: Mapped[str] = mapped_column(String(200), default="standard_json", nullable=False)
    standard_json_parse_error_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    entries: Mapped[list["SillyTavernPromptEntry"]] = relationship(
        back_populates="preset", cascade="all, delete-orphan", order_by="SillyTavernPromptEntry.array_index"
    )
    profiles: Mapped[list["TgbreakProfile"]] = relationship(
        back_populates="preset", cascade="all, delete-orphan"
    )


class SillyTavernPromptEntry(Base):
    __tablename__ = "sillytavern_prompt_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    preset_id: Mapped[str] = mapped_column(String(36), ForeignKey("sillytavern_presets.id", ondelete="CASCADE"), nullable=False)
    array_index: Mapped[int] = mapped_column(Integer, nullable=False)
    identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="system", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    system_prompt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    marker: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    injection_position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    injection_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    injection_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    injection_trigger_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    forbid_overrides: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    preset: Mapped[SillyTavernPreset] = relationship(back_populates="entries")

    __table_args__ = (
        UniqueConstraint("preset_id", "array_index", name="uq_tgbreak_entry_array_index"),
    )


class TgbreakProfile(Base):
    __tablename__ = "tgbreak_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_preset_id: Mapped[str] = mapped_column(String(36), ForeignKey("sillytavern_presets.id", ondelete="CASCADE"), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_overrides_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    preset: Mapped[SillyTavernPreset] = relationship(back_populates="profiles")


class TgbreakOutputRecord(Base):
    __tablename__ = "tgbreak_output_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("generation_candidates.id", ondelete="CASCADE"), nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, default="", nullable=False)
    draft_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    draft_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extra_modules_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_preset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_preset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_entry_identifiers_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    requested_reasoning_mode: Mapped[str] = mapped_column(String(50), default="disabled", nullable=False)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
