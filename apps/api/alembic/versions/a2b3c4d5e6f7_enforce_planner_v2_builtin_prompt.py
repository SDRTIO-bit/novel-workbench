"""enforce planner v2 contract on unmodified builtin planner prompt

Revision ID: a2b3c4d5e6f7
Revises: b2c3d4e5f6a7
Create Date: 2026-07-18 16:00:00.000000

Adds a new version to the built-in planner profile so its template matches
the planner v2 output contract (planner_contract_version=2,
consequence_would_still_happen, strict state_delta / next_constraint rules).

Only the planner stage is touched. Writer/Critic/Reviser/Judge profiles are
left alone. Whether the stored template is "unmodified" is decided by
comparing its SHA-256 against a fixed set of hashes of the previously
released built-in planner templates — never by comparing against the new
template. If the latest version matches neither the new template nor a known
old one, the profile is treated as user-modified: skipped and logged, never
overwritten.
"""
import hashlib
import logging
from datetime import datetime
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

# Fixed hashes of previously released built-in planner templates
# (sha256 of system_template + "\n" + user_template, UTF-8):
#   e806a339…  decision-state model template (commit c8bbdcd)
#   f74d1862…  v2 contract wording template (commit 8354286)
KNOWN_OLD_PLANNER_TEMPLATE_SHA256 = frozenset({
    "e806a339a568b677b2c7e6b35eb2c7b8c8ca3e7ebb22a406cf2fe392584b780d",
    "f74d18629a5d353cf8413139b8e0c1fc3ccc49c41688940780e51d9d8d80cff3",
})


def _builtin(stage: str) -> dict:
    # Import at migration time so an untouched installation receives the same
    # template as a fresh seed. User-created profiles are never changed.
    from app.prompts.defaults import BUILTIN_PROMPTS

    return next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == stage)


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
        sa.column("output_mode", sa.String),
        sa.column("output_schema_name", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    workflow_steps = sa.table(
        "workflow_step_configs",
        sa.column("prompt_version_id", sa.String),
        sa.column("stage", sa.String),
    )

    profile = bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "planner", profiles.c.is_builtin.is_(True))
        .order_by(profiles.c.id)
    ).first()
    if not profile:
        return

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
    if not current:
        return

    entry = _builtin("planner")
    new_hash = _template_hash(entry["system_template"], entry["user_template"])
    current_hash = _template_hash(current.system_template, current.user_template)

    if current_hash == new_hash:
        # Already on the v2 template (e.g. seeded by current code, or the
        # earlier migrations ran with current code). Nothing to do.
        return

    if current_hash not in KNOWN_OLD_PLANNER_TEMPLATE_SHA256:
        # Cannot prove the template is an unmodified release; it may carry
        # user edits. Skip rather than overwrite.
        log.warning(
            "planner v2 prompt migration skipped: latest built-in planner "
            "version %s has an unrecognized template hash %s; treating it as "
            "user-modified and leaving it untouched",
            current.id,
            current_hash,
        )
        return

    replacement_id = str(uuid4())
    bind.execute(
        versions.insert().values(
            id=replacement_id,
            profile_id=profile.id,
            version_number=current.version_number + 1,
            system_template=entry["system_template"],
            user_template=entry["user_template"],
            output_mode=entry["output_mode"],
            output_schema_name=entry["output_schema_name"],
            created_at=datetime.utcnow(),
        )
    )
    # Workflow steps that still reference the unmodified old version follow
    # the built-in profile to the new one. Steps pinned to any other version
    # are explicit user choices and are left intact.
    bind.execute(
        workflow_steps.update()
        .where(
            workflow_steps.c.stage == "planner",
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
        sa.column("user_template", sa.Text),
    )
    workflow_steps = sa.table(
        "workflow_step_configs",
        sa.column("prompt_version_id", sa.String),
        sa.column("stage", sa.String),
    )

    profile = bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "planner", profiles.c.is_builtin.is_(True))
        .order_by(profiles.c.id)
    ).first()
    if not profile:
        return

    all_versions = bind.execute(
        sa.select(
            versions.c.id,
            versions.c.version_number,
            versions.c.system_template,
            versions.c.user_template,
        )
        .where(versions.c.profile_id == profile.id)
        .order_by(versions.c.version_number.desc())
    ).all()
    if len(all_versions) < 2:
        return

    entry = _builtin("planner")
    new_hash = _template_hash(entry["system_template"], entry["user_template"])
    newest, prev = all_versions[0], all_versions[1]

    # Only remove the exact version this migration added. Two conditions must
    # hold: the newest version is the current built-in template, AND the
    # version before it is a known old release. Without the second condition
    # a downgrade would wrongly delete versions created by earlier migrations
    # or by restore_default, which can also hold the current template.
    if _template_hash(newest.system_template, newest.user_template) != new_hash:
        return
    if _template_hash(prev.system_template, prev.user_template) not in KNOWN_OLD_PLANNER_TEMPLATE_SHA256:
        return

    bind.execute(
        workflow_steps.update()
        .where(
            workflow_steps.c.stage == "planner",
            workflow_steps.c.prompt_version_id == newest.id,
        )
        .values(prompt_version_id=prev.id)
    )
    bind.execute(versions.delete().where(versions.c.id == newest.id))
