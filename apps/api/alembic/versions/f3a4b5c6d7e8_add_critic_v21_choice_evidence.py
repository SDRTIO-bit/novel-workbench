"""add critic v2.1 choice evidence

Revision ID: f3a4b5c6d7e8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-19 01:15:00.000000

Create Critic v2.1 only from the released, unmodified official Critic v7
template. Custom prompts and workflows pinned to older versions remain
unchanged; only workflow Critic steps that still reference the exact v7 row
are repointed.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

OFFICIAL_V7_TEMPLATE_SHA256 = (
    "4ddbe591035c66a8d990911b4a8343c9d578df82053372f0fb92f6339eaf6c72"
)
TARGET_SCHEMA = "critic_v2"


def _builtin_critic() -> dict:
    from app.prompts.defaults import BUILTIN_PROMPTS

    return next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == "critic")


def _template_hash(system_template: str, user_template: str) -> str:
    return hashlib.sha256(
        ((system_template or "") + "\n" + (user_template or "")).encode("utf-8")
    ).hexdigest()


def _migration_v8_id(v7_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{revision}:{v7_id}"))


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
                versions.c.output_schema_name,
            )
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
        ).first()
        if (
            not current
            or current.version_number != 7
            or current.output_schema_name != TARGET_SCHEMA
        ):
            continue

        current_hash = _template_hash(current.system_template, current.user_template)
        if current_hash != OFFICIAL_V7_TEMPLATE_SHA256:
            log.warning(
                "critic v2.1 prompt migration skipped: builtin critic version %s "
                "has an unrecognized template hash %s; treating it as user-modified",
                current.id,
                current_hash,
            )
            continue

        v8_id = _migration_v8_id(current.id)
        bind.execute(
            versions.insert().values(
                id=v8_id,
                profile_id=profile.id,
                version_number=8,
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
            .values(prompt_version_id=v8_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
    profiles, versions, workflow_steps = _tables()

    v7_versions = bind.execute(
        sa.select(
            versions.c.id,
            versions.c.profile_id,
            versions.c.system_template,
            versions.c.user_template,
            versions.c.output_schema_name,
        )
        .select_from(versions.join(profiles, versions.c.profile_id == profiles.c.id))
        .where(
            profiles.c.stage == "critic",
            profiles.c.is_builtin.is_(True),
            versions.c.version_number == 7,
        )
    ).all()

    for v7 in v7_versions:
        if (
            v7.output_schema_name != TARGET_SCHEMA
            or _template_hash(v7.system_template, v7.user_template)
            != OFFICIAL_V7_TEMPLATE_SHA256
        ):
            continue
        v8_id = _migration_v8_id(v7.id)
        v8 = bind.execute(
            sa.select(versions.c.id)
            .where(
                versions.c.id == v8_id,
                versions.c.profile_id == v7.profile_id,
                versions.c.version_number == 8,
                versions.c.output_schema_name == TARGET_SCHEMA,
            )
        ).first()
        if not v8:
            continue
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == "critic",
                workflow_steps.c.prompt_version_id == v8_id,
            )
            .values(prompt_version_id=v7.id)
        )
        bind.execute(versions.delete().where(versions.c.id == v8_id))
