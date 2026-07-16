"""initial schema (placeholder — real tables in the next revision)

Revision ID: a824f766c793
Revises: 
Create Date: 2026-07-16 13:44:39.620251

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a824f766c793'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
