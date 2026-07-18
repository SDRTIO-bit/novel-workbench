"""add planner v6 top-level JSON shape guidance

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-18 23:00:00.000000

Create Planner v6 only when the current built-in Planner v5 still has the
released v5 template hash.  The replacement keeps the v5 user template and
the structured planner_v2 contract while updating only the system template.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

# sha256(system_template + "\n" + user_template) for released Planner v5.
OFFICIAL_V5_TEMPLATE_SHA256 = (
    "3ede12f48e9864b054e1bd80636ba50d1605e0695a1ec23ceef100db07a7c327"
)
TARGET_SCHEMA = "planner_v2"


def _builtin_planner() -> dict:
    from app.prompts.defaults import BUILTIN_PROMPTS

    return next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == "planner")


def _template_hash(system_template: str, user_template: str) -> str:
    return hashlib.sha256(
        ((system_template or "") + "\n" + (user_template or "")).encode("utf-8")
    ).hexdigest()


def _migration_v6_id(v5_id: str) -> str:
    """Stable ID lets downgrade delete only this migration's row."""
    return str(uuid5(NAMESPACE_URL, f"{revision}:{v5_id}"))


def _tables():
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
    return profiles, versions, workflow_steps


def upgrade() -> None:
    bind = op.get_bind()
    profiles, versions, workflow_steps = _tables()
    planner = _builtin_planner()

    builtin_profiles = bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "planner", profiles.c.is_builtin.is_(True))
        .order_by(profiles.c.id)
    ).all()

    for profile in builtin_profiles:
        current = bind.execute(
            sa.select(
                versions.c.id,
                versions.c.version_number,
                versions.c.system_template,
                versions.c.user_template,
            )
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
        ).first()
        if not current or current.version_number != 5:
            continue

        current_hash = _template_hash(current.system_template, current.user_template)
        if current_hash != OFFICIAL_V5_TEMPLATE_SHA256:
            log.warning(
                "planner v6 prompt migration skipped: builtin planner version %s "
                "has an unrecognized template hash %s; treating it as user-modified",
                current.id,
                current_hash,
            )
            continue

        v6_id = _migration_v6_id(current.id)
        bind.execute(
            versions.insert().values(
                id=v6_id,
                profile_id=profile.id,
                version_number=6,
                system_template=planner["system_template"],
                user_template=current.user_template,
                output_mode="structured",
                output_schema_name=TARGET_SCHEMA,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == "planner",
                workflow_steps.c.prompt_version_id == current.id,
            )
            .values(prompt_version_id=v6_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
    profiles, versions, workflow_steps = _tables()

    v5_versions = bind.execute(
        sa.select(
            versions.c.id,
            versions.c.profile_id,
            versions.c.system_template,
            versions.c.user_template,
        )
        .select_from(versions.join(profiles, versions.c.profile_id == profiles.c.id))
        .where(
            profiles.c.stage == "planner",
            profiles.c.is_builtin.is_(True),
            versions.c.version_number == 5,
        )
    ).all()

    for v5 in v5_versions:
        if _template_hash(v5.system_template, v5.user_template) != OFFICIAL_V5_TEMPLATE_SHA256:
            continue

        v6_id = _migration_v6_id(v5.id)
        v6 = bind.execute(
            sa.select(versions.c.id)
            .where(
                versions.c.id == v6_id,
                versions.c.profile_id == v5.profile_id,
                versions.c.version_number == 6,
            )
        ).first()
        if not v6:
            continue

        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == "planner",
                workflow_steps.c.prompt_version_id == v6_id,
            )
            .values(prompt_version_id=v5.id)
        )
        bind.execute(versions.delete().where(versions.c.id == v6_id))
