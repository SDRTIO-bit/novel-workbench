"""add run accepted_at accepted_type accepted_version_id

Revision ID: e23740fe6a52
Revises: 45661e74932a
Create Date: 2026-07-17 00:54:29.566922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e23740fe6a52'
down_revision: Union[str, Sequence[str], None] = '45661e74932a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('generation_runs', sa.Column('accepted_at', sa.DateTime(), nullable=True))
    op.add_column('generation_runs', sa.Column('accepted_type', sa.String(length=50), nullable=True))
    op.add_column('generation_runs', sa.Column('accepted_version_id', sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column('generation_runs', 'accepted_version_id')
    op.drop_column('generation_runs', 'accepted_type')
    op.drop_column('generation_runs', 'accepted_at')
