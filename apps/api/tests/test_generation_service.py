import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.generation_service import GenerationService
from app.services.context_service import ContextService


def _valid_planner_output(marker: str = ""):
    return {
        "scene_goal": "推进异常",
        "location": "机库",
        "time": "换班前",
        "characters": [
            {
                "name": "陆衡",
                "current_goal": "查明真相",
                "known_facts": ["工单编号"],
                "unknown_facts": ["敲击声来源"],
                "observed_evidence": ["压力表读数偏高"],
                "stable_mistaken_beliefs": ["阀门只是松了"],
                "situational_assumption": "阀门松了",
                "assumption_basis": ["压力表读数偏高"],
                "constraints": ["不能暴露未来工单"],
            }
        ],
        "scene_state": {
            "viewpoint_character": "陆衡",
            "last_completed_action": "放下工具",
            "active_unfinished_action": "检查阀门",
            "direct_consequence_available": "工具落地后，敲击声突然停止",
            "character_positions": ["陆衡在冷却管旁"],
            "objects_in_play": ["压力表", "扳手"],
            "current_constraints": ["不能暴露未来工单"],
        },
        "pressure": "即将交班",
        "turning_point": "敲击声再次出现",
        "end_condition": "切断电源",
        "forbidden": ["揭晓发送者"],
        "causal_transitions": [
            {
                "id": "CT01",
                "kind": "evidence_to_action",
                "visible_trigger": "接线盒里出现 GR-0713",
                "character_next_action": "陆衡询问许栀父亲的名字",
                "reader_must_infer": "编号与许明远有关",
                "narrator_must_not_state": ["两个编号一致"],
                "immediate_consequence": "陆衡合上机械手册，转身打开人事档案柜",
                "next_constraint": "他不能透露未来工单",
            }
        ],
        "chapter_contract_check": {},
        "tempo_guardrails": {
            "entry_pressure": "林隅正把熄火的探测车拖回仓库。",
            "stop_after": "他切断外门电源。",
            "final_line_must_include": marker or "身份验证通过",
            "disclosure_cap": 1,
            "must_remain_unclassified": ["敲击声来源"],
        },
    }


def _make_run():
    return SimpleNamespace(
        id="run-1",
        project_id="project-1",
        chapter_id=None,
        workflow_profile_id=None,
        scene_instruction="",
        status="running",
    )


def _make_candidate(cid: str, parsed_output: dict | None = None, error_code: str | None = None):
    return SimpleNamespace(
        id=cid,
        parsed_output_json=json.dumps(parsed_output, ensure_ascii=False) if parsed_output else None,
        text_output="",
        raw_response="",
        error_code=error_code,
    )


def _make_step(cid: str, candidates=None, selected_candidate_id: str | None = None, status: str = "pending"):
    return SimpleNamespace(
        id=cid,
        candidates=candidates or [],
        selected_candidate_id=selected_candidate_id,
        status=status,
        selected_issue_ids_json=None,
        selected_issue_operations_json=None,
        input_snapshot_hash=None,
    )


@pytest.fixture
def service(monkeypatch):
    session = MagicMock()
    session.flush = AsyncMock()
    svc = GenerationService(session)

    svc.repo = MagicMock()
    svc.repo.get_run_or_404 = AsyncMock(return_value=_make_run())
    svc.repo.get_step = AsyncMock(return_value=None)
    svc.repo.get_step_or_404 = AsyncMock(return_value=_make_step("step-writer"))
    def _make_created_candidate(**kwargs):
        return SimpleNamespace(
            id=kwargs.get("id", "candidate-1"),
            error_code=kwargs.get("error_code"),
            error_message=kwargs.get("error_message"),
            text_output=kwargs.get("text_output", ""),
            raw_response=kwargs.get("raw_response", ""),
        )

    svc.repo.create_candidate = AsyncMock(side_effect=_make_created_candidate)

    # Ensure the provider resolver is tracked for the not-called assertion.
    svc._resolve_provider = AsyncMock(return_value=MagicMock())

    return svc


@pytest.mark.asyncio
async def test_writer_stage_fails_closed_when_brief_compile_fails(service, monkeypatch):
    """Provider.complete must never be invoked if the WriterBrief compiler fails."""
    import app.services.generation_service as gen_mod

    planner_output = {
        "scene_goal": "推进异常",
        "location": "机库",
        "time": "换班前",
        "characters": [
            {
                "name": "陆衡",
                "current_goal": "查明真相",
                "known_facts": [],
                "unknown_facts": [],
            }
        ],
        "pressure": "即将交班",
        "turning_point": "敲击声再次出现",
        "end_condition": "切断电源",
        "forbidden": [],
        "causal_transitions": [],
        "chapter_contract_check": {},
        "tempo_guardrails": {
            "entry_pressure": "林隅正把熄火的探测车拖回仓库。",
            "stop_after": "他切断外门电源。",
            "disclosure_cap": 0,
        },
    }

    dep_candidate = _make_candidate("cand-planner", parsed_output=planner_output)
    dep_step = _make_step(
        "step-planner",
        candidates=[dep_candidate],
        selected_candidate_id="cand-planner",
        status="completed",
    )
    service.repo.get_step = AsyncMock(return_value=dep_step)

    def _boom(*args, **kwargs):
        raise RuntimeError("compiler exploded")

    monkeypatch.setattr(gen_mod, "compile_writer_brief", _boom)

    # Sanity check: the patch must replace the module-level reference.
    assert gen_mod.compile_writer_brief is _boom

    candidate = await service.execute_stage("run-1", "writer", {})

    # The real repository would create a candidate with the error_code field set.
    # The mock is configured to return a fixed object; inspect the call instead.
    call_kwargs = service.repo.create_candidate.call_args.kwargs
    assert call_kwargs["error_code"] == "WRITER_BRIEF_COMPILE_FAILED"
    assert "compiler exploded" in call_kwargs["error_message"]
    service._resolve_provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_context_request_clears_scene_plan_and_guardrails_for_writer(service):
    """Writer stage must receive the compiled writer_brief, not raw PlannerOutput/tempo_guardrails."""
    marker = "最终标记"
    planner_output = _valid_planner_output(marker=marker)
    dep_candidate = _make_candidate("cand-planner", parsed_output=planner_output)
    dep_step = _make_step(
        "step-planner",
        candidates=[dep_candidate],
        selected_candidate_id="cand-planner",
        status="completed",
    )
    service.repo.get_step = AsyncMock(return_value=dep_step)

    ctx_req = await service._build_context_request(_make_run(), "writer", {})

    assert ctx_req.scene_plan is None
    assert ctx_req.tempo_guardrails is None
    assert ctx_req.writer_brief is not None
    assert ctx_req.writer_brief.get("final_line_must_include") == marker
    assert ctx_req.writer_brief.get("stop_fact") == "他切断外门电源。"


@pytest.mark.asyncio
async def test_build_context_request_keeps_guardrails_for_reviser(service):
    """Reviser stage must continue to receive the original tempo_guardrails dict."""
    guardrails = {"entry_pressure": "x", "stop_after": "y", "final_line_must_include": "z"}
    writer_candidate = _make_candidate("cand-writer", parsed_output=None)
    writer_candidate.text_output = "初稿内容。"
    writer_step = _make_step(
        "step-writer",
        candidates=[writer_candidate],
        selected_candidate_id="cand-writer",
        status="completed",
    )
    critic_candidate = _make_candidate("cand-critic", parsed_output={"decision": "local_revision"})
    critic_step = _make_step(
        "step-critic",
        candidates=[critic_candidate],
        selected_candidate_id="cand-critic",
        status="completed",
    )

    def _step_for_stage(run_id, stage):
        if stage == "writer":
            return writer_step
        if stage == "critic":
            return critic_step
        return None

    service.repo.get_step = AsyncMock(side_effect=_step_for_stage)

    ctx_req = await service._build_context_request(
        _make_run(), "reviser", {"tempo_guardrails": guardrails}
    )

    assert ctx_req.tempo_guardrails == guardrails
    assert ctx_req.writer_brief is None


@pytest.mark.asyncio
async def test_writer_validation_uses_writer_brief_marker(service, monkeypatch):
    """Writer final-line validation must read the marker from ctx_req.writer_brief."""
    import app.services.generation_service as gen_mod

    marker = "最终标记"
    planner_output = _valid_planner_output(marker=marker)
    dep_candidate = _make_candidate("cand-planner", parsed_output=planner_output)
    dep_step = _make_step(
        "step-planner",
        candidates=[dep_candidate],
        selected_candidate_id="cand-planner",
        status="completed",
    )
    service.repo.get_step = AsyncMock(return_value=dep_step)

    async def _mock_assemble(self, ctx_req):
        return {
            "rendered_system_prompt": "sys",
            "rendered_user_prompt": "user",
            "input_snapshot_hash": "hash",
        }

    monkeypatch.setattr(ContextService, "assemble", _mock_assemble)

    provider_mock = MagicMock()
    provider_mock.complete = AsyncMock(
        return_value=SimpleNamespace(
            text=f"正文第一段。\n\n第二段。\n\n包含{marker}的结尾段。",
            input_tokens=10,
            output_tokens=10,
            latency_ms=100,
        )
    )
    service._resolve_provider = AsyncMock(return_value=provider_mock)

    captured = []
    original_validate = gen_mod.validate_tempo_final_line

    def _capture_validate(text, guardrails):
        captured.append((text, guardrails))
        return original_validate(text, guardrails)

    monkeypatch.setattr(gen_mod, "validate_tempo_final_line", _capture_validate)

    candidate = await service.execute_stage("run-1", "writer", {})

    assert candidate.error_code is None
    assert len(captured) == 1
    _, guardrails = captured[0]
    assert guardrails is not None
    assert guardrails.get("final_line_must_include") == marker


@pytest.mark.asyncio
async def test_writer_validation_fails_when_marker_missing(service, monkeypatch):
    """Writer candidate must be marked with TEMPO_FINAL_LINE_MISMATCH when marker is missing."""
    import app.services.generation_service as gen_mod

    marker = "最终标记"
    planner_output = _valid_planner_output(marker=marker)
    dep_candidate = _make_candidate("cand-planner", parsed_output=planner_output)
    dep_step = _make_step(
        "step-planner",
        candidates=[dep_candidate],
        selected_candidate_id="cand-planner",
        status="completed",
    )
    service.repo.get_step = AsyncMock(return_value=dep_step)

    async def _mock_assemble(self, ctx_req):
        return {
            "rendered_system_prompt": "sys",
            "rendered_user_prompt": "user",
            "input_snapshot_hash": "hash",
        }

    monkeypatch.setattr(ContextService, "assemble", _mock_assemble)

    provider_mock = MagicMock()
    provider_mock.complete = AsyncMock(
        return_value=SimpleNamespace(
            text="正文第一段。\n\n第二段。\n\n没有标记的结尾段。",
            input_tokens=10,
            output_tokens=10,
            latency_ms=100,
        )
    )
    service._resolve_provider = AsyncMock(return_value=provider_mock)

    candidate = await service.execute_stage("run-1", "writer", {})

    assert candidate.error_code == "TEMPO_FINAL_LINE_MISMATCH"
