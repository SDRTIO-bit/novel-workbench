"""add writer brief builtin prompt versions

Revision ID: 0c5c03bae691
Revises: e7f8a9b0c1d2
Create Date: 2026-07-17 19:16:57.418293

"""
from datetime import datetime
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0c5c03bae691"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
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

    # Only planner and writer changed in this phase; other stages keep their
    # existing builtin versions so user customizations remain untouched.
    for stage in ("planner", "writer"):
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
        if not current:
            continue

        entry = _builtin(stage)
        # If the latest builtin version is already the current default, skip.
        current_template = bind.execute(
            sa.select(versions.c.system_template)
            .where(versions.c.id == current.id)
        ).scalar()
        if current_template == entry["system_template"]:
            continue

        replacement_id = str(uuid4())
        next_number = current.version_number + 1
        bind.execute(
            versions.insert().values(
                id=replacement_id,
                profile_id=profile.id,
                version_number=next_number,
                system_template=entry["system_template"],
                user_template=entry["user_template"],
                output_mode=entry["output_mode"],
                output_schema_name=entry["output_schema_name"],
                created_at=datetime.utcnow(),
            )
        )
        # Existing workflow steps that still point at the previous builtin
        # version should follow the new builtin default. Explicitly changed
        # prompt versions are left intact because their id is different.
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
        sa.column("system_template", sa.Text),
    )
    workflow_steps = sa.table(
        "workflow_step_configs",
        sa.column("prompt_version_id", sa.String),
        sa.column("stage", sa.String),
    )

    for stage in ("planner", "writer"):
        entry = _builtin(stage)
        target_template = entry["system_template"]

        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
            .order_by(profiles.c.id)
        ).first()
        if not profile:
            continue

        # Find the version this migration created by matching its template.
        rows = bind.execute(
            sa.select(versions.c.id, versions.c.version_number)
            .where(
                versions.c.profile_id == profile.id,
                versions.c.system_template == target_template,
            )
            .order_by(versions.c.version_number.desc())
        ).fetchall()
        if not rows:
            continue

        for new in rows:
            old = bind.execute(
                sa.select(versions.c.id)
                .where(
                    versions.c.profile_id == profile.id,
                    versions.c.version_number == new.version_number - 1,
                )
            ).first()
            if not old:
                continue

            bind.execute(
                workflow_steps.update()
                .where(
                    workflow_steps.c.stage == stage,
                    workflow_steps.c.prompt_version_id == new.id,
                )
                .values(prompt_version_id=old.id)
            )
            bind.execute(versions.delete().where(versions.c.id == new.id))
