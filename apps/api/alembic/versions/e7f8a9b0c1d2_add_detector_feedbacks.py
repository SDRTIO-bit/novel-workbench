"""add detector_feedbacks table

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-07-17 18:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "detector_feedbacks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("chapter_id", sa.String(36), nullable=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("candidate_id", sa.String(36), nullable=True),
        sa.Column("chapter_version_id", sa.String(36), nullable=True),
        sa.Column("detector_name", sa.String(200), nullable=False),
        sa.Column("human_ratio", sa.Float(), nullable=True),
        sa.Column("suspected_ai_ratio", sa.Float(), nullable=True),
        sa.Column("ai_ratio", sa.Float(), nullable=True),
        sa.Column("spans_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["generation_runs.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["generation_candidates.id"]),
        sa.ForeignKeyConstraint(["chapter_version_id"], ["chapter_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("detector_feedbacks")
