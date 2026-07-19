import json
from pathlib import Path

import pytest

from app.services.writer_brief import (
    MAX_ACTIVE_PROJECT_FACTS,
    WriterBrief,
    compile_writer_brief,
    validate_writer_brief,
)


def _planner(**overrides):
    plan = {
        "scene_state": {
            "present_characters": ["林澈"],
            "visible_facts": ["周宁的扣子错位", "周宁正走向点名台"],
        },
        "characters": [{
            "name": "林澈",
            "known": ["周宁没有低头检查校服"],
            "unknown": [],
            "observed_evidence": ["周宁的最上面扣眼扣到了第二颗扣子"],
            "current_interpretation": "周宁没有意识到扣错",
        }],
        "causal_transitions": [{
            "visible_trigger": "点名开始前，周宁走向点名台",
            "character_next_action": "林澈递出点名册示意周宁低头",
            "immediate_consequence": "周宁看见扣子错位",
            "next_constraint": "点名已经开始，不能当众解释",
        }],
        "tempo_guardrails": {
            "entry_pressure": "点名即将开始",
            "must_remain_unclassified": ["周宁是否已经发现"],
            "stop_state": {
                "visible_fact": "周宁把扣子重新扣好",
                "must_not_append": "不得解释同学关系",
            },
        },
        "active_project_facts": ["林澈是班长", "晨会公开点名", "林澈是班长"],
    }
    plan.update(overrides)
    return plan


def test_canonical_unknown_facts_exists_and_legacy_name_does_not():
    brief = compile_writer_brief(_planner())
    assert "unknown_facts" in brief
    assert brief["unknown_facts"] == []
    assert "unknown_information" not in brief


def test_empty_assumption_is_valid_when_basis_is_empty():
    brief = compile_writer_brief(_planner(characters=[{
        "name": "林澈", "known": [], "unknown": [], "observed_evidence": [],
        "current_interpretation": "",
    }]))
    assert brief["current_assumption"] == ""
    assert brief["assumption_basis"] == []
    validate_writer_brief(brief)


def test_nonempty_assumption_requires_legal_basis():
    brief = compile_writer_brief(_planner())
    brief["assumption_basis"] = []
    with pytest.raises(ValueError, match="assumption_basis"):
        validate_writer_brief(brief)


def test_assumption_basis_must_be_traceable_to_scene_information():
    brief = compile_writer_brief(_planner())
    brief["assumption_basis"] = ["凭空的后台答案"]
    with pytest.raises(ValueError, match="assumption_basis"):
        validate_writer_brief(brief)


def test_active_project_facts_are_stable_deduplicated_and_capped():
    facts = [f"事实{i}" for i in range(MAX_ACTIVE_PROJECT_FACTS + 3)]
    brief = compile_writer_brief(_planner(active_project_facts=[facts[0], facts[1], facts[0], *facts[2:]]))
    assert brief["active_project_facts"] == facts[:MAX_ACTIVE_PROJECT_FACTS]
    assert len(brief["active_project_facts"]) == MAX_ACTIVE_PROJECT_FACTS


def test_writer_brief_excludes_planner_hidden_answers():
    brief = compile_writer_brief({
        **_planner(),
        "reader_must_infer": "后台答案",
        "chapter_contract_check": {"hidden": True},
        "causal_transitions": [{
            "visible_trigger": "班长点名时看见扣子",
            "character_next_action": "把书递过去遮住胸前",
            "immediate_consequence": "周宁低头",
            "next_constraint": "点名已开始",
            "reader_must_infer": "他怕公开出丑",
            "narrator_must_not_state": ["他很羞愧"],
        }],
    })
    serialized = json.dumps(brief, ensure_ascii=False)
    for forbidden in ("reader_must_infer", "narrator_must_not_state", "chapter_contract_check", "后台答案"):
        assert forbidden not in serialized


def test_writer_brief_model_rejects_backend_fields():
    brief = compile_writer_brief(_planner())
    brief["reader_must_infer"] = "后台答案"
    with pytest.raises(ValueError, match="extra"):
        WriterBrief.model_validate(brief)


def test_builtin_writer_prompt_ends_with_short_brief_not_full_planner():
    from app.services.generation_service import GenerationService

    planner = {
        **_planner(),
        "reader_must_infer": "不能给 Writer 的后台答案",
        "chapter_contract_check": {"hidden": True},
    }
    brief = compile_writer_brief(planner)
    context = {
        "variables": {"writer_brief": json.dumps(brief, ensure_ascii=False)},
        "rendered_user_prompt": "写作指令\n",
        "input_snapshot_hash": "snapshot",
    }

    GenerationService._append_writer_brief("writer", "builtin", context)

    rendered = context["rendered_user_prompt"]
    assert rendered.endswith("只输出场景正文；用可见行动处理这个具体麻烦，并在 stop_state 成立处停止。")
    assert "## Writer Brief（只含现场行动信息）" in rendered
    assert "不能给 Writer 的后台答案" not in rendered
    assert "chapter_contract_check" not in rendered


@pytest.mark.parametrize("case_id", ["CASE-001", "CASE-002", "CASE-003", "CASE-004"])
def test_saved_planner_candidates_compile_to_canonical_brief(case_id):
    root = Path(__file__).resolve().parents[3]
    evidence = json.loads((root / "__evaluation" / "cases" / case_id / "pipeline_evidence.json").read_text(encoding="utf-8"))
    planner_step = evidence["stages"]["planner"]
    planner = next(item for item in planner_step["candidates"] if item["candidate_id"] == planner_step["selected_candidate_id"])
    brief = compile_writer_brief(planner["parsed_output"])
    validate_writer_brief(brief)
    assert set(brief) == {
        "opening_mode", "opening_fact", "viewpoint_character", "known_facts", "unknown_facts",
        "current_assumption", "assumption_basis", "next_action", "immediate_consequence",
        "next_constraint", "active_project_facts", "remain_unclassified", "stop_fact",
        "must_not_append", "final_line_must_include",
    }
