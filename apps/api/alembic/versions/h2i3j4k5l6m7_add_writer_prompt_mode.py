"""add optional TGbreak mode to the existing Writer step

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-07-19 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, Sequence[str], None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_step_configs") as batch_op:
        batch_op.add_column(sa.Column(
            "writer_prompt_mode",
            sa.String(length=20),
            nullable=False,
            server_default="builtin",
        ))
        batch_op.add_column(
            sa.Column("tgbreak_profile_id", sa.String(length=36), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_step_configs") as batch_op:
        batch_op.drop_column("tgbreak_profile_id")
        batch_op.drop_column("writer_prompt_mode")
