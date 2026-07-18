"""mark existing builtin planner prompt as v2 contract

Revision ID: c2d3e4f5a6b7
Revises: a2b3c4d5e6f7
Create Date: 2026-07-18 20:00:00.000000

The planner v2 contract is now activated by ``output_schema_name = "planner_v2"``
on the PromptVersion row.  New installs get this marker from the seed or from
the earlier migrations (which wrote the current defaults.py template, which
now carries ``"planner_v2"``).

Databases that already ran a2b3c4d5e6f7 or earlier migrations before the
``planner_v2`` marker was introduced still have ``output_schema_name = "planner"``.
This migration patches those in-place — but only when the template content
matches the current official planner template (same sha-256).  User-modified
templates are left untouched and logged.

No new version row is inserted.  Only the existing row's ``output_schema_name``
column is updated.
"""
import hashlib
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

TARGET_SCHEMA = "planner_v2"


def _builtin_planner_templates() -> tuple[str, str]:
    from app.prompts.defaults import BUILTIN_PROMPTS
    entry = next(e for e in BUILTIN_PROMPTS if e["stage"] == "planner")
    return entry["system_template"], entry["user_template"]


def _hash(system_template: str, user_template: str) -> str:
    return hashlib.sha256(
        ((system_template or "") + "\n" + (user_template or "")).encode("utf-8")
    ).hexdigest()


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
        sa.column("output_schema_name", sa.String),
    )
    return profiles, versions


def _latest_builtin_planner(bind, profiles, versions):
    profile = bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "planner", profiles.c.is_builtin.is_(True))
        .order_by(profiles.c.id)
    ).first()
    if not profile:
        return None
    return bind.execute(
        sa.select(
            versions.c.id,
            versions.c.system_template,
            versions.c.user_template,
            versions.c.output_schema_name,
        )
        .where(versions.c.profile_id == profile.id)
        .order_by(versions.c.version_number.desc())
    ).first()


def upgrade() -> None:
    bind = op.get_bind()
    profiles, versions = _tables()

    current = _latest_builtin_planner(bind, profiles, versions)
    if not current:
        return

    current_schema = current.output_schema_name or ""
    if current_schema == TARGET_SCHEMA:
        return

    sys_t, usr_t = _builtin_planner_templates()
    if _hash(current.system_template, current.user_template) != _hash(sys_t, usr_t):
        log.warning(
            "planner v2 schema-marker skipped: latest version %s template "
            "does not match the official v2 template — treating as user-modified",
            current.id,
        )
        return

    bind.execute(
        versions.update()
        .where(versions.c.id == current.id)
        .values(output_schema_name=TARGET_SCHEMA)
    )
    log.info(
        "marked planner version %s output_schema_name=%s",
        current.id,
        TARGET_SCHEMA,
    )


def downgrade() -> None:
    bind = op.get_bind()
    profiles, versions = _tables()

    current = _latest_builtin_planner(bind, profiles, versions)
    if not current:
        return

    if current.output_schema_name != TARGET_SCHEMA:
        return

    sys_t, usr_t = _builtin_planner_templates()
    if _hash(current.system_template, current.user_template) != _hash(sys_t, usr_t):
        return

    bind.execute(
        versions.update()
        .where(versions.c.id == current.id)
        .values(output_schema_name="planner")
    )
