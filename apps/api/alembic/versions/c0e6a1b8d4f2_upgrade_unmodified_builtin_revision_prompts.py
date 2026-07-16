"""upgrade unmodified builtin prompts

Revision ID: c0e6a1b8d4f2
Revises: b9c5d75f8a31
Create Date: 2026-07-17 12:30:00.000000

"""
from datetime import datetime
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "c0e6a1b8d4f2"
down_revision: Union[str, Sequence[str], None] = "b9c5d75f8a31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _builtin(stage: str) -> dict:
    # Import at migration time so an untouched installation receives the same
    # templates as a new installation. User-created profiles are never changed.
    from app.prompts.defaults import BUILTIN_PROMPTS

    return next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == stage)


def upgrade() -> None:
    bind = op.get_bind()
    profiles = sa.table(
        "prompt_profiles",
        sa.column("id", sa.String),
        sa.column("stage", sa.String),
        sa.column("name", sa.String),
        sa.column("is_builtin", sa.Boolean),
    )
    versions = sa.table(
        "prompt_versions",
        sa.column("id", sa.String),
        sa.column("profile_id", sa.String),
        sa.column("version_number", sa.Integer),
        sa.column("system_template", sa.Text),
        sa.column("user_template", sa.Text),
        sa.column("output_mode", sa.String),
        sa.column("output_schema_name", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    workflow_steps = sa.table(
        "workflow_step_configs",
        sa.column("prompt_version_id", sa.String),
        sa.column("stage", sa.String),
    )

    for stage in ("planner", "writer", "critic", "reviser", "judge"):
        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
            .order_by(profiles.c.id)
        ).first()
        if not profile:
            continue

        current = bind.execute(
            sa.select(versions.c.id, versions.c.version_number)
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
        ).first()
        # A later version is author intent (manual edits or a prior restore),
        # so preserve it. Version 1 is the untouched original builtin.
        if not current or current.version_number != 1:
            continue

        entry = _builtin(stage)
        replacement_id = str(uuid4())
        bind.execute(
            versions.insert().values(
                id=replacement_id,
                profile_id=profile.id,
                version_number=2,
                system_template=entry["system_template"],
                user_template=entry["user_template"],
                output_mode=entry["output_mode"],
                output_schema_name=entry["output_schema_name"],
                created_at=datetime.utcnow(),
            )
        )
        # Existing workflow profiles that still point at the untouched builtin
        # should receive the new contract. Explicitly changed prompt versions
        # are left intact by the version-number guard above.
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == stage,
                workflow_steps.c.prompt_version_id == current.id,
            )
            .values(prompt_version_id=replacement_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
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
    workflow_steps = sa.table(
        "workflow_step_configs",
        sa.column("prompt_version_id", sa.String),
        sa.column("stage", sa.String),
    )

    for stage in ("planner", "writer", "critic", "reviser", "judge"):
        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
            .order_by(profiles.c.id)
        ).first()
        if not profile:
            continue
        old = bind.execute(
            sa.select(versions.c.id)
            .where(versions.c.profile_id == profile.id, versions.c.version_number == 1)
        ).first()
        new = bind.execute(
            sa.select(versions.c.id)
            .where(versions.c.profile_id == profile.id, versions.c.version_number == 2)
        ).first()
        if old and new:
            bind.execute(
                workflow_steps.update()
                .where(
                    workflow_steps.c.stage == stage,
                    workflow_steps.c.prompt_version_id == new.id,
                )
                .values(prompt_version_id=old.id)
            )
            bind.execute(versions.delete().where(versions.c.id == new.id))
