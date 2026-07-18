"""Boundary tests: the planner v2 contract is enforced only for the *current*
built-in planner workflow (latest version of the built-in planner profile),
never silently downgraded, and never forced onto custom prompts.
"""
import json

import pytest

import app.models.chapter  # noqa: F401  (register tables for db_session create_all)
import app.models.detector_feedback  # noqa: F401
import app.models.generation  # noqa: F401
import app.models.project  # noqa: F401
import app.models.prompt  # noqa: F401
import app.models.provider  # noqa: F401
import app.models.workflow  # noqa: F401
from app.llm.base import LlmResponse
from app.models.project import Project
from app.models.prompt import PromptProfile, PromptVersion
from app.models.workflow import WorkflowProfile, WorkflowStepConfig
from app.services.context_service import ContextService
from app.services.generation_service import (
    GenerationService,
    _expected_planner_contract_version,
)


class _StaticProvider:
    def __init__(self, text: str):
        self._text = text

    async def complete(self, request):
        return LlmResponse(text=self._text, input_tokens=1, output_tokens=1, latency_ms=1)


def _planner_v1_payload() -> str:
    # v1-shaped output: no version field, no scene_state, empty transitions.
    return json.dumps({
        "scene_goal": "推进异常",
        "location": "机库",
        "time": "换班前",
        "characters": [],
        "pressure": "即将交班",
        "turning_point": "敲击声再次出现",
        "end_condition": "切断电源",
        "forbidden": [],
        "causal_transitions": [],
        "chapter_contract_check": {},
    }, ensure_ascii=False)


def _planner_v2_payload() -> str:
    return json.dumps({
        "planner_contract_version": 2,
        "scene_goal": "推进异常",
        "location": "机库",
        "time": "换班前",
        "scene_state": {
            "last_completed_action": "上一班巡查结束",
            "present_characters": ["林隅"],
            "visible_facts": ["探测车熄火"],
            "available_objects": ["备用电池"],
            "unresolved_problem": "敲击声来源不明",
            "already_existing_constraints": ["不能暴露身份"],
        },
        "concrete_problem": "敲击声来源是什么",
        "characters": [],
        "pressure": "即将交班",
        "turning_point": "敲击声再次出现",
        "end_condition": "切断电源",
        "forbidden": [],
        "causal_transitions": [{
            "id": "CT01",
            "kind": "evidence_to_action",
            "visible_trigger": "冷却管里传出敲击声",
            "character_interpretation": "林隅认为敲击声来自管内活物",
            "character_next_action": "林隅切断外门电源隔离仓库",
            "rejected_alternative": "按原工单流程上报后继续巡查",
            "immediate_consequence": "仓库与外部完全断电隔离",
            "counterfactual_without_action": "如果不切断电源，敲击声会引来夜班保安",
            "consequence_would_still_happen": False,
            "state_delta": {"before": "仓库正常供电", "after": "仓库完全断电"},
            "cost_or_commitment": "林隅承担了擅自断电的责任",
            "next_constraint": "必须在备用电源耗尽前查明来源",
            "reader_must_infer": "敲击声不是普通故障",
            "narrator_must_not_state": ["敲击声的真实来源"],
        }],
        "chapter_contract_check": {
            "function_aligned": True,
            "must_deliver_covered": True,
            "must_not_deliver_respected": True,
            "main_change_enabled": True,
            "main_payoff_prepared": True,
            "ending_hook_established": True,
            "causal_transitions_grounded": True,
            "reader_inference_not_pre_resolved": True,
            "scene_state_reconstructed": True,
            "information_sources_legal": True,
            "character_choice_is_real": True,
            "consequence_is_counterfactual": True,
            "state_delta_is_nonempty": True,
            "next_constraint_is_new": True,
            "stop_state_is_visible": True,
            "stop_state_changes_future_actions": True,
        },
    }, ensure_ascii=False)


async def _make_profile(db_session, stage, *, builtin, name, template_marks):
    profile = PromptProfile(stage=stage, name=name, is_builtin=builtin)
    db_session.add(profile)
    await db_session.flush()
    versions = []
    for i, mark in enumerate(template_marks, start=1):
        version = PromptVersion(
            profile_id=profile.id,
            version_number=i,
            system_template=f"{mark} system",
            user_template=f"{mark} user",
            output_mode="structured",
            output_schema_name=stage,
        )
        db_session.add(version)
        versions.append(version)
    await db_session.flush()
    return profile, versions


async def _make_workflow(db_session, planner_prompt_version_id):
    workflow = WorkflowProfile(name="wf", is_default=False)
    db_session.add(workflow)
    await db_session.flush()
    step = WorkflowStepConfig(
        workflow_profile_id=workflow.id,
        stage="planner",
        prompt_version_id=planner_prompt_version_id,
    )
    db_session.add(step)
    await db_session.flush()
    return workflow


# ── pure boundary function ────────────────────────────────────────────


def test_expected_version_only_for_latest_builtin_planner():
    assert _expected_planner_contract_version("planner", {"is_builtin_latest": True}) == 2
    assert _expected_planner_contract_version("planner", {"is_builtin_latest": False}) is None
    assert _expected_planner_contract_version("planner", None) is None
    assert _expected_planner_contract_version("critic", {"is_builtin_latest": True}) is None
    assert _expected_planner_contract_version("writer", {"is_builtin_latest": True}) is None


# ── prompt resolution metadata ────────────────────────────────────────


async def test_resolve_prompt_marks_only_latest_builtin_version(db_session):
    _, versions = await _make_profile(
        db_session, "planner", builtin=True, name="默认场景规划",
        template_marks=["old", "new"],
    )
    svc = ContextService(db_session)

    _, _, meta_old = await svc._resolve_prompt("planner", None, versions[0].id)
    assert meta_old["is_builtin_latest"] is False

    _, _, meta_new = await svc._resolve_prompt("planner", None, versions[1].id)
    assert meta_new["is_builtin_latest"] is True


async def test_resolve_prompt_custom_profile_is_never_builtin_latest(db_session):
    _, versions = await _make_profile(
        db_session, "planner", builtin=False, name="我的自定义规划",
        template_marks=["custom"],
    )
    svc = ContextService(db_session)
    _, _, meta = await svc._resolve_prompt("planner", None, versions[0].id)
    assert meta["is_builtin_latest"] is False


async def test_resolve_prompt_via_workflow_step(db_session):
    _, versions = await _make_profile(
        db_session, "planner", builtin=True, name="默认场景规划",
        template_marks=["old", "new"],
    )
    wf_old = await _make_workflow(db_session, versions[0].id)
    wf_new = await _make_workflow(db_session, versions[1].id)
    svc = ContextService(db_session)

    _, _, meta_old = await svc._resolve_prompt("planner", wf_old.id, None)
    assert meta_old["is_builtin_latest"] is False

    _, _, meta_new = await svc._resolve_prompt("planner", wf_new.id, None)
    assert meta_new["is_builtin_latest"] is True


async def test_resolve_prompt_builtin_fallback_is_latest(db_session):
    await _make_profile(
        db_session, "planner", builtin=True, name="默认场景规划",
        template_marks=["only"],
    )
    svc = ContextService(db_session)
    _, _, meta = await svc._resolve_prompt("planner", None, None)
    assert meta["is_builtin_latest"] is True


# ── execute_stage wiring ──────────────────────────────────────────────


async def _run_planner(db_session, monkeypatch, *, prompt_version_id, provider_text):
    project = Project(name="测试项目", genre="科幻")
    db_session.add(project)
    await db_session.flush()
    workflow = await _make_workflow(db_session, prompt_version_id)

    async def _fake_resolve(self, provider_id):
        return _StaticProvider(provider_text)

    monkeypatch.setattr(GenerationService, "_resolve_provider", _fake_resolve)

    svc = GenerationService(db_session)
    run = await svc.repo.create_run(
        project_id=project.id,
        chapter_id=None,
        workflow_profile_id=workflow.id,
        scene_instruction="写第一章",
    )
    return await svc.execute_stage(run.id, "planner", {})


async def test_builtin_planner_rejects_output_missing_version(db_session, monkeypatch):
    _, versions = await _make_profile(
        db_session, "planner", builtin=True, name="默认场景规划",
        template_marks=["builtin-v2"],
    )
    candidate = await _run_planner(
        db_session, monkeypatch,
        prompt_version_id=versions[-1].id,
        provider_text=_planner_v1_payload(),
    )
    assert candidate.error_code == "PLANNER_OUTPUT_CONTRACT_INVALID"
    assert "planner_contract_version is required" in candidate.error_message


async def test_builtin_planner_rejects_explicit_v1_output(db_session, monkeypatch):
    _, versions = await _make_profile(
        db_session, "planner", builtin=True, name="默认场景规划",
        template_marks=["builtin-v2"],
    )
    payload = json.dumps(
        {**json.loads(_planner_v1_payload()), "planner_contract_version": 1},
        ensure_ascii=False,
    )
    candidate = await _run_planner(
        db_session, monkeypatch,
        prompt_version_id=versions[-1].id,
        provider_text=payload,
    )
    assert candidate.error_code == "PLANNER_OUTPUT_CONTRACT_INVALID"
    assert "expected planner_contract_version=2" in candidate.error_message


async def test_builtin_planner_accepts_valid_v2_output(db_session, monkeypatch):
    _, versions = await _make_profile(
        db_session, "planner", builtin=True, name="默认场景规划",
        template_marks=["builtin-v2"],
    )
    candidate = await _run_planner(
        db_session, monkeypatch,
        prompt_version_id=versions[-1].id,
        provider_text=_planner_v2_payload(),
    )
    assert candidate.error_code is None
    parsed = json.loads(candidate.parsed_output_json)
    assert parsed["planner_contract_version"] == 2


async def test_custom_planner_prompt_keeps_v1_compatibility(db_session, monkeypatch):
    _, versions = await _make_profile(
        db_session, "planner", builtin=False, name="自定义规划",
        template_marks=["custom"],
    )
    candidate = await _run_planner(
        db_session, monkeypatch,
        prompt_version_id=versions[-1].id,
        provider_text=_planner_v1_payload(),
    )
    assert candidate.error_code is None


async def test_pinned_old_builtin_version_is_not_forced_to_v2(db_session, monkeypatch):
    _, versions = await _make_profile(
        db_session, "planner", builtin=True, name="默认场景规划",
        template_marks=["old", "new"],
    )
    candidate = await _run_planner(
        db_session, monkeypatch,
        prompt_version_id=versions[0].id,
        provider_text=_planner_v1_payload(),
    )
    assert candidate.error_code is None
