"""add selected issue operations

Revision ID: b9c5d75f8a31
Revises: e23740fe6a52
Create Date: 2026-07-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c5d75f8a31"
down_revision: Union[str, Sequence[str], None] = "e23740fe6a52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation_steps",
        sa.Column("selected_issue_operations_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generation_steps", "selected_issue_operations_json")
