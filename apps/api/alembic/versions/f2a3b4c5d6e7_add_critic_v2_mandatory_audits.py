"""add critic v2 mandatory audits

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-19 00:10:00.000000

Create Critic v2 only from the released, unmodified official Critic v6
template.  Custom prompts and workflows pinned to older versions remain
unchanged; only workflow Critic steps that still reference the exact v6 row
are repointed.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

OFFICIAL_V6_TEMPLATE_SHA256 = (
    "9f33d3ecd9a0820c498a78f0b88be647583b41f4ac3a528b9f42c9c8417b24ca"
)
TARGET_SCHEMA = "critic_v2"


def _builtin_critic() -> dict:
    from app.prompts.defaults import BUILTIN_PROMPTS

    return next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == "critic")


def _template_hash(system_template: str, user_template: str) -> str:
    return hashlib.sha256(
        ((system_template or "") + "\n" + (user_template or "")).encode("utf-8")
    ).hexdigest()


def _migration_v7_id(v6_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{revision}:{v6_id}"))


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
    critic = _builtin_critic()

    builtin_profiles = bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "critic", profiles.c.is_builtin.is_(True))
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
        if not current or current.version_number != 6:
            continue

        current_hash = _template_hash(current.system_template, current.user_template)
        if current_hash != OFFICIAL_V6_TEMPLATE_SHA256:
            log.warning(
                "critic v2 prompt migration skipped: builtin critic version %s "
                "has an unrecognized template hash %s; treating it as user-modified",
                current.id,
                current_hash,
            )
            continue

        v7_id = _migration_v7_id(current.id)
        bind.execute(
            versions.insert().values(
                id=v7_id,
                profile_id=profile.id,
                version_number=7,
                system_template=critic["system_template"],
                user_template=current.user_template,
                output_mode="structured",
                output_schema_name=TARGET_SCHEMA,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == "critic",
                workflow_steps.c.prompt_version_id == current.id,
            )
            .values(prompt_version_id=v7_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
    profiles, versions, workflow_steps = _tables()

    v6_versions = bind.execute(
        sa.select(
            versions.c.id,
            versions.c.profile_id,
            versions.c.system_template,
            versions.c.user_template,
        )
        .select_from(versions.join(profiles, versions.c.profile_id == profiles.c.id))
        .where(
            profiles.c.stage == "critic",
            profiles.c.is_builtin.is_(True),
            versions.c.version_number == 6,
        )
    ).all()

    for v6 in v6_versions:
        if _template_hash(v6.system_template, v6.user_template) != OFFICIAL_V6_TEMPLATE_SHA256:
            continue
        v7_id = _migration_v7_id(v6.id)
        v7 = bind.execute(
            sa.select(versions.c.id)
            .where(
                versions.c.id == v7_id,
                versions.c.profile_id == v6.profile_id,
                versions.c.version_number == 7,
                versions.c.output_schema_name == TARGET_SCHEMA,
            )
        ).first()
        if not v7:
            continue
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == "critic",
                workflow_steps.c.prompt_version_id == v7_id,
            )
            .values(prompt_version_id=v6.id)
        )
        bind.execute(versions.delete().where(versions.c.id == v7_id))
