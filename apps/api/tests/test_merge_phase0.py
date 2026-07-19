"""Phase 0 merge-readiness fixes: regression tests.

Covers the gaps found in the integration-branch review:
- PatchApplicationError carries a stable code that execute_stage surfaces on
  the failed candidate (instead of a generic LLM_ERROR)
- A valid Reviser patch is applied server-side and traced
- The Writer stage raises WRITER_BRIEF_INVALID (structured 400) when the
  selected Planner candidate cannot compile into a WriterBrief
- AcceptFinalRequest.accept_type is a closed Literal set (no 'judge')
- tgbreak_profile_id existence is validated on workflow step update
- planner_contract_validation_v1 requires issues for unmet contract fields
"""
import json

import pytest
from pydantic import ValidationError

import app.models.chapter  # noqa: F401 - register tables for create_all
import app.models.provider  # noqa: F401 - register tables for create_all
import app.models.tgbreak  # noqa: F401 - register tgbreak tables for create_all
from app.llm.base import LlmResponse
from app.llm.output_contracts import validate_planner_contract_validation
from app.models.generation import GenerationCandidate
from app.models.project import Project
from app.models.prompt import PromptProfile, PromptVersion
from app.models.workflow import STAGES, WorkflowProfile, WorkflowStepConfig
from app.schemas.generation import AcceptFinalRequest
from app.services.generation_service import GenerationService
from app.services.workflow_service import WorkflowService


class RecordingProvider:
    def __init__(self, text):
        self.text = text
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return LlmResponse(
            text=self.text,
            input_tokens=10,
            output_tokens=5,
            latency_ms=1,
            finish_reason="stop",
        )


DRAFT_TEXT = "老陈抬起头看向门口。\n\n铜铃响了一声。"

PLANNER_V2_PAYLOAD = {
    "planner_contract_version": 2,
    "scene_goal": "让小满进店",
    "scene_state": {
        "last_completed_action": "",
        "present_characters": ["老陈"],
        "visible_facts": ["小满在门外"],
        "available_objects": ["铜铃"],
        "unresolved_problem": "小满为什么哭",
        "already_existing_constraints": ["老陈不能离开书店"],
    },
    "concrete_problem": "小满站在门外哭",
    "characters": [
        {
            "name": "老陈",
            "known": ["小满在门外"],
            "unknown": ["她为什么哭"],
            "observed_evidence": ["眼眶红"],
        }
    ],
    "causal_transitions": [
        {
            "id": "CT01",
            "kind": "evidence_to_action",
            "visible_trigger": "铜铃响，小满站在门口",
            "character_interpretation": "老陈判断她需要安全感",
            "character_next_action": "请她进来坐",
            "rejected_alternative": "直接追问",
            "immediate_consequence": "小满跨过门槛",
            "counterfactual_without_action": "不请则她继续站在门外",
            "consequence_would_still_happen": False,
            "state_delta": {"before": "门外", "after": "门内"},
            "cost_or_commitment": "老陈打破不管闲事的习惯",
            "next_constraint": "仍不知道她为什么哭",
            "reader_must_infer": "安抚方式的选择",
            "narrator_must_not_state": ["老陈的判断"],
        }
    ],
    "tempo_guardrails": {
        "entry_pressure": "铜铃响，小满站在门口",
        "dominant_pressure": {"kind": "social_friction", "description": "信任建立"},
        "disclosure_cap": 1,
        "stop_state": {
            "type": "relationship_shift",
            "visible_fact": "小满坐在书店里",
            "what_is_now_different": "庇护关系形成",
        },
    },
}


async def _prompt_version(db_session, stage, output_mode, schema_name=""):
    profile = PromptProfile(name=f"{stage} prompt", stage=stage, description="", is_builtin=True)
    db_session.add(profile)
    await db_session.flush()
    version = PromptVersion(
        profile_id=profile.id,
        version_number=1,
        system_template=f"{stage} SYSTEM",
        user_template=f"{stage} USER {{{{numbered_draft}}}} {{{{draft_text}}}} {{{{scene_instruction}}}}",
        output_mode=output_mode,
        output_schema_name=schema_name,
    )
    db_session.add(version)
    await db_session.flush()
    return version


async def _workflow(db_session, **prompt_by_stage):
    workflow = WorkflowProfile(name="wf", is_default=False)
    db_session.add(workflow)
    await db_session.flush()
    for stage in STAGES:
        prompt = prompt_by_stage.get(stage)
        db_session.add(WorkflowStepConfig(
            workflow_profile_id=workflow.id,
            stage=stage,
            prompt_version_id=prompt.id if prompt else None,
        ))
    await db_session.flush()
    return workflow


async def _selected_candidate(db_session, run_id, service, stage, *, parsed=None, text=""):
    step = await service.repo.get_step(run_id, stage)
    candidate = GenerationCandidate(
        step_id=step.id,
        attempt_number=1,
        raw_response=text or json.dumps(parsed or {}, ensure_ascii=False),
        parsed_output_json=json.dumps(parsed, ensure_ascii=False) if parsed is not None else None,
        text_output=text,
        is_selected=True,
    )
    db_session.add(candidate)
    await db_session.flush()
    step.selected_candidate_id = candidate.id
    step.status = "completed"
    await db_session.flush()
    db_session.expire(step, ["candidates"])
    return candidate


async def _run_with_project(db_session, workflow):
    project = Project(name="书店", genre="现实主义", author_note="", default_pov="第三人称")
    db_session.add(project)
    await db_session.flush()
    service = GenerationService(db_session)
    run = await service.repo.create_run(
        project_id=project.id,
        chapter_id=None,
        workflow_profile_id=workflow.id,
        scene_instruction="让小满进店。",
    )
    return service, run


def _recording(service, monkeypatch, text):
    provider = RecordingProvider(text)

    async def fake_resolve(_provider_id):
        return provider

    monkeypatch.setattr(service, "_resolve_provider", fake_resolve)
    return provider


# ── Reviser patch application through execute_stage ─────────────────


async def _reviser_fixture(db_session, critic_report):
    reviser_prompt = await _prompt_version(db_session, "reviser", "structured")
    workflow = await _workflow(db_session, reviser=reviser_prompt)
    service, run = await _run_with_project(db_session, workflow)
    await _selected_candidate(db_session, run.id, service, "planner", parsed=PLANNER_V2_PAYLOAD)
    await _selected_candidate(db_session, run.id, service, "writer", text=DRAFT_TEXT)
    await _selected_candidate(db_session, run.id, service, "critic", parsed=critic_report)
    return service, run


async def test_protected_patch_surfaces_specific_error_code_not_llm_error(db_session, monkeypatch):
    service, run = await _reviser_fixture(
        db_session,
        critic_report={"issues": [], "protected_strengths": [{"paragraph_ids": ["P001"]}]},
    )
    _recording(service, monkeypatch, json.dumps({
        "patches": [{"paragraph_id": "P001", "operation": "replace", "replacement": "老陈没有抬头。"}]
    }, ensure_ascii=False))

    candidate = await service.execute_stage(run.id, "reviser", {
        "draft_text": DRAFT_TEXT,
        "critic_report": {"issues": [], "protected_strengths": [{"paragraph_ids": ["P001"]}]},
    })

    assert candidate.error_code == "REVISER_PATCH_PROTECTED"
    assert "P001" in candidate.error_message
    assert candidate.text_output == ""
    reviser_step = await service.repo.get_step(run.id, "reviser")
    assert reviser_step.status == "failed"


async def test_invalid_patch_range_surfaces_specific_error_code(db_session, monkeypatch):
    service, run = await _reviser_fixture(db_session, critic_report={"issues": []})
    _recording(service, monkeypatch, json.dumps({
        "patches": [{"paragraph_id": "P099", "operation": "replace", "replacement": "不存在的段落。"}]
    }, ensure_ascii=False))

    candidate = await service.execute_stage(run.id, "reviser", {"draft_text": DRAFT_TEXT})

    assert candidate.error_code == "REVISER_PATCH_INVALID"
    assert "P099" in candidate.error_message


async def test_valid_patch_is_applied_server_side_and_traced(db_session, monkeypatch):
    service, run = await _reviser_fixture(db_session, critic_report={"issues": []})
    _recording(service, monkeypatch, json.dumps({
        "patches": [{"paragraph_id": "P002", "operation": "replace", "replacement": "铜铃又响了一声。"}]
    }, ensure_ascii=False))

    candidate = await service.execute_stage(run.id, "reviser", {"draft_text": DRAFT_TEXT})

    assert candidate.error_code is None, f"expected None, got '{candidate.error_code}': {candidate.error_message}"
    assert candidate.text_output == "老陈抬起头看向门口。\n\n铜铃又响了一声。"
    trace = json.loads(candidate.compiler_trace_json)
    assert trace["patch_application"]["changed_paragraph_ids"] == ["P002"]
    assert trace["patch_application"]["unchanged_ratio"] >= 0.8


# ── Writer brief compile failure ────────────────────────────────────


async def test_unbriefable_planner_candidate_fails_in_context_build(db_session):
    writer_prompt = await _prompt_version(db_session, "writer", "plain_text")
    workflow = await _workflow(db_session, writer=writer_prompt)
    service, run = await _run_with_project(db_session, workflow)
    await _selected_candidate(
        db_session, run.id, service, "planner",
        parsed={"scene_goal": "旧版 v1 的 payload", "characters": [{"name": "老陈"}], "forbidden": []},
    )

    # sanity: the step was updated in the same session
    step = await service.repo.get_step(run.id, "planner")
    assert step.selected_candidate_id is not None, "planner step must have selected_candidate_id"
    assert step.status == "completed", f"planner step status={step.status!r}"
    assert any(step.candidates), "planner step must have at least one candidate"
    cand = next(c for c in step.candidates if c.id == step.selected_candidate_id)
    assert cand.parsed_output_json is not None, "planner candidate must have parsed_output_json"

    got_code = None
    try:
        await service._build_context_request(run, "writer", {})
    except Exception as e:
        got_code = getattr(e, "code", None)
    assert got_code == "WRITER_BRIEF_INVALID", f"expected WRITER_BRIEF_INVALID, got code={got_code!r}"


# ── accept_type closed set ──────────────────────────────────────────


def test_accept_final_request_accept_type_is_closed_set():
    with pytest.raises(ValidationError):
        AcceptFinalRequest(accept_type="judge")
    AcceptFinalRequest(accept_type="original")
    AcceptFinalRequest(accept_type="revision")
    AcceptFinalRequest(accept_type="manual", final_text="正文")


# ── tgbreak_profile_id existence validation ─────────────────────────


async def test_update_step_rejects_dangling_tgbreak_profile_id(db_session):
    workflow = WorkflowProfile(name="wf", is_default=False)
    db_session.add(workflow)
    await db_session.flush()
    db_session.add(WorkflowStepConfig(workflow_profile_id=workflow.id, stage="writer"))
    await db_session.flush()

    service = WorkflowService(db_session)
    with pytest.raises(Exception) as exc_info:
        await service.update_step(workflow.id, "writer", {"tgbreak_profile_id": "missing-profile"})
    assert getattr(exc_info.value, "code", None) == "TGBREAK_PROFILE_NOT_FOUND"


# ── planner_contract_validation_v1 issue-emission rule ──────────────


def _field(status, with_evidence=True):
    field = {
        "status": status,
        "evidence": (
            [{"paragraph_id": "P001", "quote": "原文句子", "explanation": "证据。"}]
            if with_evidence else []
        ),
        "explanation": "说明。",
    }
    return field


def _issue(issue_id="I01"):
    return {
        "issue_id": issue_id,
        "severity": "high",
        "issue_type": "contract_not_delivered",
        "paragraph_ids": ["P001"],
        "problem": "问题。",
        "revision_goal": "目标。",
        "recommended_operation": "tighten",
    }


def _validation_output(*, rejected_status="present", issues=None):
    rejected_with_evidence = rejected_status in ("present", "partial")
    return {
        "planner_contract_validation_version": 1,
        "overall_assessment": "评估。",
        "stop_state": {
            "visible_fact": _field("present"),
            "must_not_append": _field("present"),
        },
        "transitions": [
            {
                "transition_id": "CT01",
                "visible_trigger": _field("present"),
                "rejected_alternative": _field(rejected_status, with_evidence=rejected_with_evidence),
                "character_next_action": _field("present"),
                "cost_or_commitment": _field("present"),
                "immediate_consequence": _field("present"),
                "next_constraint": _field("present"),
            }
        ],
        "general_findings": [],
        "strength_candidates": [],
        "issues": issues if issues is not None else [_issue()],
    }


def test_all_present_fields_allow_empty_issues():
    output = validate_planner_contract_validation(_validation_output(issues=[]))
    assert output.issues == []


def test_missing_field_without_issues_is_rejected():
    with pytest.raises(ValueError, match="issues must not be empty"):
        validate_planner_contract_validation(
            _validation_output(rejected_status="missing", issues=[])
        )


def test_partial_field_without_issues_is_rejected():
    with pytest.raises(ValueError, match="issues must not be empty"):
        validate_planner_contract_validation(
            _validation_output(rejected_status="partial", issues=[])
        )


def test_missing_field_with_issue_is_accepted():
    output = validate_planner_contract_validation(
        _validation_output(rejected_status="missing")
    )
    assert [issue.issue_id for issue in output.issues] == ["I01"]
