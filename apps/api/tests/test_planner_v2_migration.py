"""Tests for the planner-v2 migration chain.

Covers:
- a2b3c4d5e6f7: upgrade/downgrade of the builtin planner v2 prompt
- b2c3d4e5f6a7: safe duplicate version cleanup with repo repointing
- f8a9b0c1d2e3: downgrade integrity (profiles.c.id typo fix)
- c2d3e4f5a6b7: mark existing builtin planner as planner_v2 contract
"""
import hashlib
import importlib.util
import logging
import os
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations

API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
A2_PATH = os.path.join(
    API_DIR, "alembic", "versions", "a2b3c4d5e6f7_enforce_planner_v2_builtin_prompt.py"
)
B2_PATH = os.path.join(
    API_DIR, "alembic", "versions", "b2c3d4e5f6a7_fix_migration_remove_extra_versions.py"
)
C2_PATH = os.path.join(
    API_DIR, "alembic", "versions", "c2d3e4f5a6b7_mark_builtin_planner_v2_contract.py"
)
D3_PATH = os.path.join(
    API_DIR, "alembic", "versions", "d3e4f5a6b7c8_add_planner_v5_enum_guidance.py"
)
E4_PATH = os.path.join(
    API_DIR, "alembic", "versions", "e4f5a6b7c8d9_add_planner_v6_top_level_shapes.py"
)


def _load_migration(path=A2_PATH):
    spec = importlib.util.spec_from_file_location(os.path.basename(path), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_schema(engine):
    from app.db import Base
    import app.models.project  # noqa: F401
    import app.models.chapter  # noqa: F401
    import app.models.prompt  # noqa: F401
    import app.models.provider  # noqa: F401
    import app.models.workflow  # noqa: F401
    import app.models.generation  # noqa: F401
    import app.models.detector_feedback  # noqa: F401

    Base.metadata.create_all(engine)


def _seed_builtin_planner(session, *, system_template, user_template):
    from app.models.prompt import PromptProfile, PromptVersion
    from app.models.workflow import WorkflowProfile, WorkflowStepConfig

    profile = PromptProfile(
        stage="planner", name="默认场景规划", is_builtin=True
    )
    session.add(profile)
    session.flush()
    version = PromptVersion(
        profile_id=profile.id,
        version_number=1,
        system_template=system_template,
        user_template=user_template,
        output_mode="structured",
        output_schema_name="planner",
    )
    session.add(version)
    workflow = WorkflowProfile(name="默认工作流", is_default=True)
    session.add(workflow)
    session.flush()
    step = WorkflowStepConfig(
        workflow_profile_id=workflow.id,
        stage="planner",
        prompt_version_id=version.id,
    )
    session.add(step)
    session.flush()
    return profile, version, step


def _versions_of(session, profile_id):
    from app.models.prompt import PromptVersion

    return list(
        session.execute(
            select(PromptVersion)
            .where(PromptVersion.profile_id == profile_id)
            .order_by(PromptVersion.version_number)
        ).scalars()
    )


def _step_prompt_id(session, step_id):
    from app.models.workflow import WorkflowStepConfig

    return session.get(WorkflowStepConfig, step_id).prompt_version_id


def _current_builtin_planner():
    from app.prompts.defaults import BUILTIN_PROMPTS

    return next(e for e in BUILTIN_PROMPTS if e["stage"] == "planner")


def _run_migration(mig, engine, fn_name):
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(mig, fn_name)()


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    _create_schema(eng)
    yield eng
    eng.dispose()


# ── behavior ──────────────────────────────────────────────────────────


def test_upgrade_replaces_unmodified_old_template(engine, monkeypatch):
    mig = _load_migration()
    fake_old_sys = "旧的规划模板 system"
    fake_old_usr = "旧的规划模板 user"
    fake_hash = hashlib.sha256((fake_old_sys + "\n" + fake_old_usr).encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        mig,
        "KNOWN_OLD_PLANNER_TEMPLATE_SHA256",
        mig.KNOWN_OLD_PLANNER_TEMPLATE_SHA256 | {fake_hash},
    )

    with Session(engine) as session:
        profile, version, step = _seed_builtin_planner(
            session, system_template=fake_old_sys, user_template=fake_old_usr
        )
        session.commit()
        profile_id, old_version_id, step_id = profile.id, version.id, step.id

    _run_migration(mig, engine, "upgrade")

    current = _current_builtin_planner()
    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        assert len(versions) == 2
        newest = versions[-1]
        assert newest.version_number == 2
        assert newest.system_template == current["system_template"]
        assert newest.user_template == current["user_template"]
        assert _step_prompt_id(session, step_id) == newest.id

    _run_migration(mig, engine, "downgrade")

    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        assert len(versions) == 1
        assert versions[0].id == old_version_id
        assert _step_prompt_id(session, step_id) == old_version_id


def test_upgrade_skips_user_modified_template(engine, caplog):
    mig = _load_migration()
    with Session(engine) as session:
        profile, version, step = _seed_builtin_planner(
            session,
            system_template="用户自己改过的规划模板",
            user_template="user customized planner template",
        )
        session.commit()
        profile_id, version_id, step_id = profile.id, version.id, step.id

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_migration(mig, engine, "upgrade")

    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        assert len(versions) == 1
        assert _step_prompt_id(session, step_id) == version_id
    assert any("user-modified" in record.message for record in caplog.records)


def test_upgrade_noop_when_already_current(engine):
    mig = _load_migration()
    current = _current_builtin_planner()
    with Session(engine) as session:
        profile, version, step = _seed_builtin_planner(
            session,
            system_template=current["system_template"],
            user_template=current["user_template"],
        )
        session.commit()
        profile_id, version_id, step_id = profile.id, version.id, step.id

    _run_migration(mig, engine, "upgrade")

    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        assert len(versions) == 1
        assert _step_prompt_id(session, step_id) == version_id


def test_downgrade_keeps_version_not_added_by_this_migration(engine, monkeypatch):
    # newest is the current template but the previous version is NOT a known
    # old release (e.g. the version was created by restore_default or by an
    # earlier migration running with current code): downgrade must not touch it.
    mig = _load_migration()
    current = _current_builtin_planner()
    with Session(engine) as session:
        profile, version, step = _seed_builtin_planner(
            session,
            system_template="some earlier template",
            user_template="earlier user",
        )
        session.flush()
        from app.models.prompt import PromptVersion

        newer = PromptVersion(
            profile_id=profile.id,
            version_number=2,
            system_template=current["system_template"],
            user_template=current["user_template"],
            output_mode="structured",
            output_schema_name="planner",
        )
        session.add(newer)
        session.commit()
        profile_id, newer_id = profile.id, newer.id

    _run_migration(mig, engine, "downgrade")

    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        assert [v.id for v in versions] and versions[-1].id == newer_id
        assert len(versions) == 2


def test_migration_pins_hashes_of_released_old_templates():
    # Regression guard: the fixed old-template hashes must stay in place so
    # databases migrated by previous releases remain recognizable.
    mig = _load_migration()
    assert {
        "e806a339a568b677b2c7e6b35eb2c7b8c8ca3e7ebb22a406cf2fe392584b780d",
        "f74d18629a5d353cf8413139b8e0c1fc3ccc49c41688940780e51d9d8d80cff3",
    } <= set(mig.KNOWN_OLD_PLANNER_TEMPLATE_SHA256)


# ── executability through alembic ─────────────────────────────────────


def test_alembic_upgrade_downgrade_head_executes(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(API_DIR)
    from app.config import settings

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'full.db'}"
    monkeypatch.setattr(settings, "database_url", db_url)

    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")


def test_alembic_multi_step_downgrade_hits_f8a_without_typo(tmp_path, monkeypatch):
    """Downgrade through the full chain to f8a9b0c1d2e3's downgrade().

    f8a's downgrade used ``.order_by(profiles.id)`` (missing ``.c.``) which
    caused an AttributeError.  This test proves the fix by creating DB rows
    that exercise the downgrade path, then downgrading all the way back to
    f8a and asserting it succeeds.
    """
    monkeypatch.syspath_prepend(API_DIR)
    from app.config import settings

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'multi.db'}"
    monkeypatch.setattr(settings, "database_url", db_url)

    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))

    # 1. Apply all migrations to build schema.
    command.upgrade(cfg, "head")

    # 2. Insert profiles + versions that f8a's downgrade will iterate over.
    import sqlite3

    db_path = str(tmp_path / "multi.db")
    conn = sqlite3.connect(db_path)
    for stage in ("planner", "writer", "critic", "reviser", "judge"):
        pid = f"prof-{stage}"
        vid1 = f"ver-{stage}-1"
        vid2 = f"ver-{stage}-2"
        conn.execute(
            "INSERT INTO prompt_profiles (id, stage, name, description, is_builtin, created_at, updated_at)"
            " VALUES (?, ?, ?, '', 1, datetime('now'), datetime('now'))",
            (pid, stage, stage),
        )
        conn.execute(
            "INSERT INTO prompt_versions (id, profile_id, version_number, system_template, user_template,"
            " output_mode, output_schema_name, created_at)"
            " VALUES (?, ?, 1, 'old sys', 'old usr', 'structured', ?, datetime('now'))",
            (vid1, pid, stage),
        )
        conn.execute(
            "INSERT INTO prompt_versions (id, profile_id, version_number, system_template, user_template,"
            " output_mode, output_schema_name, created_at)"
            " VALUES (?, ?, 2, 'new sys', 'new usr', 'structured', ?, datetime('now'))",
            (vid2, pid, stage),
        )
    conn.commit()
    conn.close()

    # 3. Downgrade through the chain: c2→a2, a2→b2→f8a, f8a→e7.
    #    The last step exercises f8a's downgrade() — the function that had
    #    the .order_by(profiles.id) typo.  It must not raise.
    command.downgrade(cfg, "a2b3c4d5e6f7")
    command.downgrade(cfg, "f8a9b0c1d2e3")
    command.downgrade(cfg, "e7f8a9b0c1d2")
    # If we got here without an error, the fix is verified.


# ── b2c3d4e5f6a7 (duplicate version cleanup) ──────────────────────────


def _seed_critic_with_workflow(engine, *, system1, user1, system2, user2):
    from app.models.prompt import PromptProfile, PromptVersion
    from app.models.workflow import WorkflowProfile, WorkflowStepConfig

    with Session(engine) as session:
        profile = PromptProfile(stage="critic", name="默认场景诊断", is_builtin=True)
        session.add(profile)
        session.flush()
        profile_id = profile.id
        v1 = PromptVersion(
            profile_id=profile_id, version_number=1,
            system_template=system1, user_template=user1,
            output_mode="structured", output_schema_name="critic",
        )
        session.add(v1)
        session.flush()
        v1_id = v1.id
        v2 = PromptVersion(
            profile_id=profile_id, version_number=2,
            system_template=system2, user_template=user2,
            output_mode="structured", output_schema_name="critic",
        )
        session.add(v2)
        session.flush()
        v2_id = v2.id
        workflow = WorkflowProfile(name="wf", is_default=True)
        session.add(workflow)
        session.flush()
        step = WorkflowStepConfig(
            workflow_profile_id=workflow.id, stage="critic",
            prompt_version_id=v2_id,
        )
        session.add(step)
        session.flush()
        step_id = step.id
        session.commit()
    return profile_id, v1_id, v2_id, step_id


def test_b2_removes_duplicate_critic_version_and_repoints_references(engine):
    mig = _load_migration(B2_PATH)
    profile_id, v1_id, v2_id, step_id = _seed_critic_with_workflow(
        engine,
        system1="critic sys v1", user1="critic usr v1",
        system2="critic sys v1", user2="critic usr v1",  # same = duplicate
    )
    _run_migration(mig, engine, "upgrade")

    from app.models.prompt import PromptVersion
    from app.models.workflow import WorkflowStepConfig

    with Session(engine) as session:
        versions = list(
            session.execute(
                select(PromptVersion)
                .where(PromptVersion.profile_id == profile_id)
                .order_by(PromptVersion.version_number)
            ).scalars()
        )
        step = session.get(WorkflowStepConfig, step_id)
        assert len(versions) == 1, "duplicate version should be deleted"
        assert versions[0].id == v1_id
        assert step.prompt_version_id == v1_id, "workflow step should be repointed"


def test_b2_skips_when_hashes_differ(engine, caplog):
    mig = _load_migration(B2_PATH)
    profile_id, v1_id, v2_id, step_id = _seed_critic_with_workflow(
        engine,
        system1="critic A", user1="critic A",
        system2="critic B", user2="critic B",  # different = user-modified
    )
    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_migration(mig, engine, "upgrade")

    from app.models.prompt import PromptVersion

    with Session(engine) as session:
        versions = list(
            session.execute(
                select(PromptVersion)
                .where(PromptVersion.profile_id == profile_id)
            ).scalars()
        )
        assert len(versions) == 2, "dissimilar versions must not be deleted"
    assert any("user-modified" in record.message for record in caplog.records)


# ── c2d3e4f5a6b7 (mark builtin planner as planner_v2) ────────────────


def _seed_planner_with_schema(engine, *, system, user, schema="planner"):
    from app.models.prompt import PromptProfile, PromptVersion

    with Session(engine) as session:
        profile = PromptProfile(stage="planner", name="默认场景规划", is_builtin=True)
        session.add(profile)
        session.flush()
        profile_id = profile.id
        version = PromptVersion(
            profile_id=profile_id,
            version_number=1,
            system_template=system,
            user_template=user,
            output_mode="structured",
            output_schema_name=schema,
        )
        session.add(version)
        session.flush()
        vid = version.id
        session.commit()
    return profile_id, vid


def test_c2_marks_existing_planner_as_v2(engine):
    mig = _load_migration(C2_PATH)
    from app.prompts.defaults import BUILTIN_PROMPTS
    entry = next(e for e in BUILTIN_PROMPTS if e["stage"] == "planner")

    pid, vid = _seed_planner_with_schema(
        engine, system=entry["system_template"], user=entry["user_template"],
        schema="planner",
    )
    _run_migration(mig, engine, "upgrade")

    from app.models.prompt import PromptVersion
    with Session(engine) as session:
        v = session.get(PromptVersion, vid)
        assert v.output_schema_name == "planner_v2"


def test_c2_skips_user_modified_template(engine, caplog):
    mig = _load_migration(C2_PATH)

    pid, vid = _seed_planner_with_schema(
        engine, system="用户自定义模板", user="custom template",
        schema="planner",
    )
    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_migration(mig, engine, "upgrade")

    from app.models.prompt import PromptVersion
    with Session(engine) as session:
        v = session.get(PromptVersion, vid)
        assert v.output_schema_name == "planner"
    assert any("user-modified" in record.message for record in caplog.records)


def test_c2_noop_when_already_v2(engine):
    mig = _load_migration(C2_PATH)
    from app.prompts.defaults import BUILTIN_PROMPTS
    entry = next(e for e in BUILTIN_PROMPTS if e["stage"] == "planner")

    pid, vid = _seed_planner_with_schema(
        engine, system=entry["system_template"], user=entry["user_template"],
        schema="planner_v2",
    )
    _run_migration(mig, engine, "upgrade")

    from app.models.prompt import PromptVersion
    with Session(engine) as session:
        v = session.get(PromptVersion, vid)
        assert v.output_schema_name == "planner_v2"


def test_c2_downgrade_restores_planner(engine):
    mig = _load_migration(C2_PATH)
    from app.prompts.defaults import BUILTIN_PROMPTS
    entry = next(e for e in BUILTIN_PROMPTS if e["stage"] == "planner")

    pid, vid = _seed_planner_with_schema(
        engine, system=entry["system_template"], user=entry["user_template"],
        schema="planner",
    )
    _run_migration(mig, engine, "upgrade")
    _run_migration(mig, engine, "downgrade")

    from app.models.prompt import PromptVersion
    with Session(engine) as session:
        v = session.get(PromptVersion, vid)
        assert v.output_schema_name == "planner"


# ── d3e4f5a6b7c8 (planner v5 enum guidance) ─────────────────────────


def _seed_official_v4_with_workflows(engine, monkeypatch, *, system, user):
    mig = _load_migration(D3_PATH)
    monkeypatch.setattr(mig, "OFFICIAL_V4_TEMPLATE_SHA256", mig._template_hash(system, user))

    with Session(engine) as session:
        profile, version, step = _seed_builtin_planner(
            session, system_template=system, user_template=user
        )
        version.version_number = 4
        from app.models.prompt import PromptVersion
        from app.models.workflow import WorkflowStepConfig

        historical = PromptVersion(
            profile_id=profile.id,
            version_number=3,
            system_template="official v3 system",
            user_template="official v3 user",
            output_mode="structured",
            output_schema_name="planner",
        )
        session.add(historical)
        session.flush()
        pinned = WorkflowStepConfig(
            workflow_profile_id=step.workflow_profile_id,
            stage="planner",
            prompt_version_id=historical.id,
        )
        session.add(pinned)
        session.commit()
        return mig, profile.id, version.id, step.id, historical.id, pinned.id


def test_d3_creates_official_v5_and_updates_only_v4_workflow_refs(engine, monkeypatch):
    mig, profile_id, v4_id, step_id, v3_id, pinned_step_id = _seed_official_v4_with_workflows(
        engine, monkeypatch, system="official v4 system", user="official v4 user"
    )

    _run_migration(mig, engine, "upgrade")

    current = _current_builtin_planner()
    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        v5 = next(version for version in versions if version.version_number == 5)
        assert v5.system_template == current["system_template"]
        assert v5.user_template == "official v4 user"
        assert v5.output_mode == "structured"
        assert v5.output_schema_name == "planner_v2"
        assert _step_prompt_id(session, step_id) == v5.id
        assert _step_prompt_id(session, pinned_step_id) == v3_id

    _run_migration(mig, engine, "downgrade")

    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        assert {version.id for version in versions} == {v3_id, v4_id}
        assert _step_prompt_id(session, step_id) == v4_id
        assert _step_prompt_id(session, pinned_step_id) == v3_id


def test_d3_skips_user_modified_v4_template(engine, monkeypatch, caplog):
    mig = _load_migration(D3_PATH)
    with Session(engine) as session:
        profile, version, step = _seed_builtin_planner(
            session, system_template="user modified v4", user_template="user modified user"
        )
        version.version_number = 4
        session.commit()
        profile_id, version_id, step_id = profile.id, version.id, step.id

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_migration(mig, engine, "upgrade")

    with Session(engine) as session:
        assert [v.id for v in _versions_of(session, profile_id)] == [version_id]
        assert _step_prompt_id(session, step_id) == version_id
    assert any("user-modified" in record.message for record in caplog.records)


def test_d3_pins_the_released_official_v4_hash():
    mig = _load_migration(D3_PATH)
    assert mig.OFFICIAL_V4_TEMPLATE_SHA256 == (
        "0f54941707faaa60929b4292ec57d0473cd17e52c1f5398f37ec3b585c5ed4d7"
    )


# ── e4f5a6b7c8d9 (planner v6 top-level shapes) ──────────────────────


def _seed_official_v5_with_workflows(engine, monkeypatch, *, system, user):
    mig = _load_migration(E4_PATH)
    monkeypatch.setattr(mig, "OFFICIAL_V5_TEMPLATE_SHA256", mig._template_hash(system, user))

    with Session(engine) as session:
        profile, version, step = _seed_builtin_planner(
            session, system_template=system, user_template=user
        )
        version.version_number = 5
        version.output_schema_name = "planner_v2"
        from app.models.prompt import PromptVersion
        from app.models.workflow import WorkflowStepConfig

        historical = PromptVersion(
            profile_id=profile.id,
            version_number=4,
            system_template="official v4 system",
            user_template="official v4 user",
            output_mode="structured",
            output_schema_name="planner_v2",
        )
        session.add(historical)
        session.flush()
        pinned = WorkflowStepConfig(
            workflow_profile_id=step.workflow_profile_id,
            stage="planner",
            prompt_version_id=historical.id,
        )
        session.add(pinned)
        session.commit()
        return mig, profile.id, version.id, step.id, historical.id, pinned.id


def test_e4_creates_official_v6_and_updates_only_v5_workflow_refs(engine, monkeypatch):
    mig, profile_id, v5_id, step_id, v4_id, pinned_step_id = _seed_official_v5_with_workflows(
        engine, monkeypatch, system="official v5 system", user="official v5 user"
    )

    _run_migration(mig, engine, "upgrade")

    current = _current_builtin_planner()
    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        v6 = next(version for version in versions if version.version_number == 6)
        assert v6.system_template == current["system_template"]
        assert v6.user_template == "official v5 user"
        assert v6.output_mode == "structured"
        assert v6.output_schema_name == "planner_v2"
        assert _step_prompt_id(session, step_id) == v6.id
        assert _step_prompt_id(session, pinned_step_id) == v4_id

    _run_migration(mig, engine, "downgrade")

    with Session(engine) as session:
        versions = _versions_of(session, profile_id)
        assert {version.id for version in versions} == {v4_id, v5_id}
        assert _step_prompt_id(session, step_id) == v5_id
        assert _step_prompt_id(session, pinned_step_id) == v4_id


def test_e4_skips_user_modified_v5_template(engine, caplog):
    mig = _load_migration(E4_PATH)
    with Session(engine) as session:
        profile, version, step = _seed_builtin_planner(
            session, system_template="user modified v5", user_template="user modified user"
        )
        version.version_number = 5
        version.output_schema_name = "planner_v2"
        session.commit()
        profile_id, version_id, step_id = profile.id, version.id, step.id

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_migration(mig, engine, "upgrade")

    with Session(engine) as session:
        assert [v.id for v in _versions_of(session, profile_id)] == [version_id]
        assert _step_prompt_id(session, step_id) == version_id
    assert any("user-modified" in record.message for record in caplog.records)


def test_e4_pins_the_released_official_v5_hash():
    mig = _load_migration(E4_PATH)
    assert mig.OFFICIAL_V5_TEMPLATE_SHA256 == (
        "3ede12f48e9864b054e1bd80636ba50d1605e0695a1ec23ceef100db07a7c327"
    )
