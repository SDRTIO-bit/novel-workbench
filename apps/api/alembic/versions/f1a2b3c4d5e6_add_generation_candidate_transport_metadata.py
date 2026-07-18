"""add generation candidate transport metadata

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-07-18 23:30:00.000000

Persist provider completion metadata for generation candidates without
retaining reasoning content.  These nullable fields support diagnosing
structured-output truncation while keeping historic candidates valid.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generation_candidates") as batch_op:
        batch_op.add_column(sa.Column("finish_reason", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("reasoning_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_candidates") as batch_op:
        batch_op.drop_column("reasoning_tokens")
        batch_op.drop_column("finish_reason")
