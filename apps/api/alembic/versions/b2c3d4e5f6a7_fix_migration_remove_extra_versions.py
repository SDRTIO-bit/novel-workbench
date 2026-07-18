"""fix migration: safely remove only verifiable duplicate critic/reviser/judge versions

Revision ID: b2c3d4e5f6a7
Revises: f8a9b0c1d2e3
Create Date: 2026-07-18 15:00:00.000000

The previous migration (f8a9b0c1d2e3) was intended to be planner-only but
touched all five stages.  For critic / reviser / judge — whose templates
did not change — this created an extra version with the same template as
the immediately preceding one.

This migration safely deletes those duplicate versions, but only when
the template-content hash of the latest version matches the previous
version exactly.  Before deletion any workflow-step references are
repointed to the previous legitimate version.  Mismatched hashes are
treated as intentional user edits and skipped with a warning.
"""
import hashlib
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

# Only critic / reviser / judge were updated in error.  Planner and writer
# received an intentional template change; their extra version should stay.
_AFFECTED_STAGES = ("critic", "reviser", "judge")


def _template_hash(system_template: str, user_template: str) -> str:
    payload = (system_template or "") + "\n" + (user_template or "")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    )
    workflow_steps = sa.table(
        "workflow_step_configs",
        sa.column("id", sa.String),
        sa.column("stage", sa.String),
        sa.column("prompt_version_id", sa.String),
    )

    for stage in _AFFECTED_STAGES:
        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
            .order_by(profiles.c.id)
        ).first()
        if not profile:
            continue

        recent = bind.execute(
            sa.select(
                versions.c.id,
                versions.c.version_number,
                versions.c.system_template,
                versions.c.user_template,
            )
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
            .limit(2)
        ).all()

        if len(recent) < 2:
            log.info(
                "skip %s: only %d version(s) present — "
                "the erroneous migration may not have run yet",
                stage,
                len(recent),
            )
            continue

        latest, prev = recent[0], recent[1]
        latest_hash = _template_hash(latest.system_template, latest.user_template)
        prev_hash = _template_hash(prev.system_template, prev.user_template)

        if latest_hash != prev_hash:
            log.warning(
                "skip %s: latest version %s template differs from previous "
                "— treating as user-modified and keeping it",
                stage,
                latest.id,
            )
            continue

        # Repoint any workflow steps that reference the duplicate before
        # deleting it so no dangling foreign key remains.
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == stage,
                workflow_steps.c.prompt_version_id == latest.id,
            )
            .values(prompt_version_id=prev.id)
        )
        bind.execute(versions.delete().where(versions.c.id == latest.id))
        log.info(
            "removed duplicate %s version %d (id=%s); "
            "repointed workflow steps to version %d (id=%s)",
            stage,
            latest.version_number,
            latest.id,
            prev.version_number,
            prev.id,
        )


def downgrade() -> None:
    # The versions deleted by upgrade() were erroneous duplicates that
    # carried the same template as their immediate predecessor.  There
    # is no meaningful data to restore.  If a full rollback across this
    # migration is needed, re-run f8a9b0c1d2e3's upgrade first — it
    # will re-create the affected version from the current built-in
    # template.
    pass
