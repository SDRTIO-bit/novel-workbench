"""upgrade unmodified builtin planner+writer prompts to decision-state model

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-07-18 10:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STAGES_UPDATED = ("planner", "writer")


def _builtin(stage: str) -> dict:
    from app.prompts.defaults import BUILTIN_PROMPTS
    return next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == stage)


def upgrade() -> None:
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

    for stage in STAGES_UPDATED:
        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
            .order_by(profiles.c.id)
        ).first()
        if not profile:
            continue

        current = bind.execute(
            sa.select(versions.c.id, versions.c.version_number, versions.c.system_template)
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
        ).first()
        if not current:
            continue

        builtin_entry = _builtin(stage)
        if current.system_template != builtin_entry["system_template"]:
            continue

        new_version = current.version_number + 1
        replacement_id = str(uuid4())
        bind.execute(
            versions.insert().values(
                id=replacement_id,
                profile_id=profile.id,
                version_number=new_version,
                system_template=builtin_entry["system_template"],
                user_template=builtin_entry["user_template"],
                output_mode=builtin_entry["output_mode"],
                output_schema_name=builtin_entry["output_schema_name"],
                created_at=datetime.utcnow(),
            )
        )
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

    for stage in STAGES_UPDATED:
        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
            .order_by(profiles.c.id)
        ).first()
        if not profile:
            continue
        all_versions = bind.execute(
            sa.select(versions.c.id, versions.c.version_number)
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
        ).all()
        if len(all_versions) < 2:
            continue
        newest = all_versions[0]
        prev = all_versions[1]
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == stage,
                workflow_steps.c.prompt_version_id == newest.id,
            )
            .values(prompt_version_id=prev.id)
        )
        bind.execute(versions.delete().where(versions.c.id == newest.id))
