import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.generation_service import GenerationService


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
    svc.repo.create_candidate = AsyncMock(
        return_value=SimpleNamespace(id="candidate-1", error_code=None)
    )

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
