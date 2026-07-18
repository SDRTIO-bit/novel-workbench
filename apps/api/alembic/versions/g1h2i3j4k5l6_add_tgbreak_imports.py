"""add private TGbreak imports and profiles

Revision ID: g1h2i3j4k5l6
Revises: f5a6b7c8d9e0
Create Date: 2026-07-19 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tgbreak_output_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=False),
        sa.Column("draft_notes", sa.Text(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("extra_modules_json", sa.Text(), nullable=False),
        sa.Column("source_preset_id", sa.String(length=36), nullable=False),
        sa.Column("source_preset_sha256", sa.String(length=64), nullable=False),
        sa.Column("resolved_entry_identifiers_json", sa.Text(), nullable=False),
        sa.Column("requested_reasoning_mode", sa.String(length=50), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["generation_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sillytavern_presets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_path", sa.String(length=2000), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("source_format_version", sa.String(length=100), nullable=False),
        sa.Column("top_level_keys_json", sa.Text(), nullable=False),
        sa.Column("unsupported_fields_json", sa.Text(), nullable=False),
        sa.Column("parse_mode", sa.String(length=200), nullable=False),
        sa.Column("standard_json_parse_error_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_sha256"),
    )
    op.create_table(
        "sillytavern_prompt_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("preset_id", sa.String(length=36), nullable=False),
        sa.Column("array_index", sa.Integer(), nullable=False),
        sa.Column("identifier", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Boolean(), nullable=False),
        sa.Column("marker", sa.Boolean(), nullable=False),
        sa.Column("injection_position", sa.Integer(), nullable=False),
        sa.Column("injection_depth", sa.Integer(), nullable=False),
        sa.Column("injection_order", sa.Integer(), nullable=False),
        sa.Column("injection_trigger_json", sa.Text(), nullable=False),
        sa.Column("forbid_overrides", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["preset_id"], ["sillytavern_presets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("preset_id", "array_index", name="uq_tgbreak_entry_array_index"),
    )
    op.create_table(
        "tgbreak_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_preset_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("entry_overrides_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_preset_id"], ["sillytavern_presets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("tgbreak_output_records")
    op.drop_table("tgbreak_profiles")
    op.drop_table("sillytavern_prompt_entries")
    op.drop_table("sillytavern_presets")
