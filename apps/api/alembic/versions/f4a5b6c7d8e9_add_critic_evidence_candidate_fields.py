"""add Critic Evidence compiler persistence fields

Revision ID: f4a5b6c7d8e9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-19 03:00:00.000000

Keep the raw provider response separate from the parsed Evidence submitted by
the model and from the deterministic compiler trace.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generation_candidates") as batch_op:
        batch_op.add_column(sa.Column("model_parsed_output_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("compiler_trace_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_candidates") as batch_op:
        batch_op.drop_column("compiler_trace_json")
        batch_op.drop_column("model_parsed_output_json")
