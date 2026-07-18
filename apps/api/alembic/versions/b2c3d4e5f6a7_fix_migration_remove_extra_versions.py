"""fix migration: correct downgrade bug and remove extra prompt versions

Revision ID: b2c3d4e5f6a7
Revises: f8a9b0c1d2e3
Create Date: 2026-07-18 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    
    # Delete extra prompt versions created for critic/reviser/judge by the buggy migration
    # These stages should not have been updated
    profiles = sa.table(
        "prompt_profiles",
        sa.column("id", sa.String),
        sa.column("stage", sa.String),
        sa.column("is_builtin", sa.Boolean),
    )
    versions = sa.table(
        "prompt_versions",
        sa.column("id", sa.String),
        sa.column("profile_id", sa.String),
        sa.column("version_number", sa.Integer),
    )
    
    # Get the profile IDs for critic, reviser, judge
    for stage in ("critic", "reviser", "judge"):
        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
        ).first()
        
        if profile:
            # Delete the latest version that was incorrectly created
            latest = bind.execute(
                sa.select(versions.c.id, versions.c.version_number)
                .where(versions.c.profile_id == profile.id)
                .order_by(versions.c.version_number.desc())
                .limit(1)
            ).first()
            
            if latest:
                bind.execute(
                    versions.delete().where(versions.c.id == latest.id)
                )


def downgrade() -> None:
    # This migration is a fix, no meaningful downgrade
    pass
