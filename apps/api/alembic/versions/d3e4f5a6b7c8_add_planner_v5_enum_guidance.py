"""add planner v5 machine-enum guidance

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-18 22:00:00.000000

Create Planner v5 only for an untouched official Planner v4.  The v4
template is identified by its released SHA-256 rather than profile name or a
best-effort textual match, so user-edited templates and historical pins stay
unchanged.  The new version keeps the structured planner_v2 contract and
adds only the machine-enum guidance present in ``defaults.py``.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

# sha256(system_template + "\n" + user_template) for the released Planner v4.
OFFICIAL_V4_TEMPLATE_SHA256 = (
    "0f54941707faaa60929b4292ec57d0473cd17e52c1f5398f37ec3b585c5ed4d7"
)
TARGET_SCHEMA = "planner_v2"


def _builtin_planner() -> dict:
    from app.prompts.defaults import BUILTIN_PROMPTS

    return next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == "planner")


def _template_hash(system_template: str, user_template: str) -> str:
    return hashlib.sha256(
        ((system_template or "") + "\n" + (user_template or "")).encode("utf-8")
    ).hexdigest()


def _migration_v5_id(v4_id: str) -> str:
    """Stable ID lets downgrade remove only the row created by this revision."""
    return str(uuid5(NAMESPACE_URL, f"{revision}:{v4_id}"))


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

    profiles_to_upgrade = bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "planner", profiles.c.is_builtin.is_(True))
        .order_by(profiles.c.id)
    ).all()

    for profile in profiles_to_upgrade:
        current = bind.execute(
            sa.select(
                versions.c.id,
                versions.c.version_number,
                versions.c.system_template,
                versions.c.user_template,
                versions.c.output_mode,
                versions.c.output_schema_name,
            )
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
        ).first()
        if not current or current.version_number != 4:
            continue

        current_hash = _template_hash(current.system_template, current.user_template)
        if current_hash != OFFICIAL_V4_TEMPLATE_SHA256:
            log.warning(
                "planner v5 prompt migration skipped: builtin planner version %s "
                "has an unrecognized template hash %s; treating it as user-modified",
                current.id,
                current_hash,
            )
            continue

        v5_id = _migration_v5_id(current.id)
        bind.execute(
            versions.insert().values(
                id=v5_id,
                profile_id=profile.id,
                version_number=5,
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
            .values(prompt_version_id=v5_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
    profiles, versions, workflow_steps = _tables()

    v4_versions = bind.execute(
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
            versions.c.version_number == 4,
        )
    ).all()

    for v4 in v4_versions:
        if _template_hash(v4.system_template, v4.user_template) != OFFICIAL_V4_TEMPLATE_SHA256:
            continue

        v5_id = _migration_v5_id(v4.id)
        v5 = bind.execute(
            sa.select(versions.c.id)
            .where(
                versions.c.id == v5_id,
                versions.c.profile_id == v4.profile_id,
                versions.c.version_number == 5,
            )
        ).first()
        if not v5:
            continue

        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == "planner",
                workflow_steps.c.prompt_version_id == v5_id,
            )
            .values(prompt_version_id=v4.id)
        )
        bind.execute(versions.delete().where(versions.c.id == v5_id))
