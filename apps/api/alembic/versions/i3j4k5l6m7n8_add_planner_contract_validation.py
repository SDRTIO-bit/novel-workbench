"""upgrade unmodified official Critic Evidence v1 to Planner Contract Validation v1

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-07-19 12:00:00.000000

Only an exact released Critic Evidence v1 row is upgraded.  User-customized
prompt templates and workflow steps pinned to historical versions are
deliberately left untouched.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa


revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, Sequence[str], None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OFFICIAL_V9_TEMPLATE_SHA256 = (
    "a33a636481bc4816ae5fac789cbe39963ae9e57161bf65330845d84cc053eff4"
)
V9_SCHEMA = "critic_evidence_v1"
VALIDATION_SCHEMA = "planner_contract_validation_v1"

log = logging.getLogger("alembic.runtime.migration")


def _builtin_critic() -> dict:
    from app.prompts.defaults import BUILTIN_PROMPTS

    return next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == "critic")


def _template_hash(system_template: str, user_template: str) -> str:
    return hashlib.sha256(
        ((system_template or "") + "\n" + (user_template or "")).encode("utf-8")
    ).hexdigest()


def _migration_v10_id(v9_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{revision}:{v9_id}"))


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
    for profile in bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "critic", profiles.c.is_builtin.is_(True))
        .order_by(profiles.c.id)
    ).all():
        current = bind.execute(
            sa.select(
                versions.c.id, versions.c.version_number, versions.c.system_template,
                versions.c.user_template, versions.c.output_schema_name,
            )
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
        ).first()
        if (
            not current
            or current.version_number != 9
            or current.output_schema_name != V9_SCHEMA
            or _template_hash(current.system_template, current.user_template)
            != OFFICIAL_V9_TEMPLATE_SHA256
        ):
            if current and current.version_number == 9 and current.output_schema_name == V9_SCHEMA:
                log.warning("planner contract validation migration skipped: builtin critic v9 %s is user-modified", current.id)
            continue
        v10_id = _migration_v10_id(current.id)
        bind.execute(versions.insert().values(
            id=v10_id,
            profile_id=profile.id,
            version_number=10,
            system_template=critic["system_template"],
            user_template=critic["user_template"],
            output_mode="structured",
            output_schema_name=VALIDATION_SCHEMA,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == "critic",
                workflow_steps.c.prompt_version_id == current.id,
            )
            .values(prompt_version_id=v10_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
    profiles, versions, workflow_steps = _tables()
    for v9 in bind.execute(
        sa.select(
            versions.c.id, versions.c.profile_id, versions.c.system_template,
            versions.c.user_template, versions.c.output_schema_name,
        )
        .select_from(versions.join(profiles, versions.c.profile_id == profiles.c.id))
        .where(
            profiles.c.stage == "critic", profiles.c.is_builtin.is_(True),
            versions.c.version_number == 9,
        )
    ).all():
        if (
            v9.output_schema_name != V9_SCHEMA
            or _template_hash(v9.system_template, v9.user_template)
            != OFFICIAL_V9_TEMPLATE_SHA256
        ):
            continue
        v10_id = _migration_v10_id(v9.id)
        v10 = bind.execute(
            sa.select(versions.c.id).where(
                versions.c.id == v10_id,
                versions.c.profile_id == v9.profile_id,
                versions.c.version_number == 10,
                versions.c.output_schema_name == VALIDATION_SCHEMA,
            )
        ).first()
        if not v10:
            continue
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == "critic",
                workflow_steps.c.prompt_version_id == v10_id,
            )
            .values(prompt_version_id=v9.id)
        )
        bind.execute(versions.delete().where(versions.c.id == v10_id))