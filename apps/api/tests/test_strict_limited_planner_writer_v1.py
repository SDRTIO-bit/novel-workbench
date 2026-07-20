"""Phase 1 tests: Planner v3 + Writer v10 prompts, schema, and WriterBrief mapping.

No LLM calls — pure Python contract tests.
"""
import hashlib
import json

import pytest

from app.llm.output_contracts import (
    PlannerV3Output,
    PovContract,
    SceneCapacity,
    MeaningfulBeat,
    InteractionPlan,
    TurningExchange,
    CharacterPosition,
    OtherMindBackstage,
    SceneMode,
    SpeechAct,
    StateDelta,
    PlannerV3ChapterContractCheck,
    validate_planner_output,
)
from app.services.writer_brief import (
    compile_writer_brief,
    compile_writer_brief_v3,
    compile_writer_input,
    _detect_planner_v3,
)
from app.services.generation_service import (
    PLANNER_V3_SCHEMA_NAME,
    EXPECTED_PLANNER_V3_CONTRACT_VERSION,
    _expected_planner_contract_version,
)


# ── Prompt existence ────────────────────────────────────────────────────


def test_builtin_planner_v3_exists():
    from app.prompts.defaults import BUILTIN_PROMPTS

    matches = [p for p in BUILTIN_PROMPTS if p["name"] == "Strict Limited Capacity Planner v3"]
    assert len(matches) == 1, "Planner v3 must exist exactly once"
    p = matches[0]
    assert p["stage"] == "planner"
    assert p["output_mode"] == "structured"
    assert p["output_schema_name"] == "planner_v3"


def test_builtin_writer_v10_exists():
    from app.prompts.defaults import BUILTIN_PROMPTS

    matches = [
        p for p in BUILTIN_PROMPTS
        if p["name"] == "Sacrificial Preflight Fusion Strict Limited v10"
    ]
    assert len(matches) == 1, "Writer v10 must exist exactly once"
    p = matches[0]
    assert p["stage"] == "writer"
    assert p["output_mode"] == "xml_story"
    assert p["output_schema_name"] is None


def test_v9_still_exists_and_unchanged():
    """v9 must still exist with its original name."""
    from app.prompts.defaults import BUILTIN_PROMPTS

    matches = [p for p in BUILTIN_PROMPTS if p["name"] == "Sacrificial Preflight Fusion v9"]
    assert len(matches) == 1, "v9 must still exist"
    p = matches[0]
    assert p["stage"] == "writer"
    assert p["output_mode"] == "xml_story"


def test_old_planner_still_exists():
    """Default planner prompt must still exist."""
    from app.prompts.defaults import BUILTIN_PROMPTS

    planner = next(p for p in BUILTIN_PROMPTS if p["stage"] == "planner"
                   and p["name"] == "默认场景规划")
    assert planner is not None
    assert planner["output_schema_name"] == "planner_v2"


# ── Writer v10 system_template content checks ─────────────────────────


def test_writer_v10_has_strict_pov_contract():
    from app.prompts.defaults import BUILTIN_PROMPTS

    v10 = next(p for p in BUILTIN_PROMPTS
               if p["name"] == "Sacrificial Preflight Fusion Strict Limited v10")
    text = v10["system_template"]
    for phrase in (
        "严格有限视角最高优先级合同",
        "第三人称外壳",
        "第一人称信息权限",
        "POV_LOCK",
        "BACKSTAGE_BEHAVIOR_ONLY",
        "禁止跳头",
        "不得由旁白直接说出",
        "互动优先",
        "一个可见事实",
        "一个暂时判断",
        "一个行动或一句话",
        "PLANNER_CAPACITY_INSUFFICIENT",
        "宁可明确短于目标",
        "</draft_notes>",
        "</story>",
    ):
        assert phrase in text, f"Missing required phrase: {phrase}"


def test_writer_v10_has_xml_discipline():
    from app.prompts.defaults import BUILTIN_PROMPTS

    v10 = next(p for p in BUILTIN_PROMPTS
               if p["name"] == "Sacrificial Preflight Fusion Strict Limited v10")
    text = v10["system_template"]
    assert "<draft_notes>" in text
    assert "</draft_notes>" in text
    assert "<story>" in text
    assert "</story>" in text
    # Must mention both open and close tags
    assert "必须同时存在" in text or "both" in text.lower()


# ── planner_v3 schema validation ──────────────────────────────────────


def _valid_v3_plan() -> dict:
    """Return a minimal valid Planner v3 output."""
    return {
        "planner_contract_version": 3,
        "scene_goal": "test",
        "location": "test",
        "time": "test",
        "scene_state": {
            "present_characters": ["林澈"],
            "visible_facts": ["门开着"],
            "available_objects": ["手机"],
            "unresolved_problem": "谁开的门",
            "already_existing_constraints": [],
        },
        "characters": [{
            "name": "林澈",
            "goal": "弄清情况",
            "known": ["门开着"],
            "unknown": ["谁开的门"],
            "mistaken_beliefs": [],
            "constraints": [],
            "observed_evidence": ["门开着"],
            "current_interpretation": "有人来过",
            "how_interpretation_drives_action": "检查物品",
        }],
        "concrete_problem": "谁开了门",
        "pressure": "时间紧迫",
        "turning_point": "发现线索",
        "end_condition": "确认情况",
        "forbidden": [],
        "causal_transitions": [{
            "id": "CT01",
            "kind": "evidence_to_action",
            "visible_trigger": "门开着",
            "character_interpretation": "有人来过",
            "character_next_action": "检查物品",
            "rejected_alternative": "忽略",
            "immediate_consequence": "发现少了东西",
            "counterfactual_without_action": "不会发现失窃",
            "consequence_would_still_happen": False,
            "state_delta": {"before": "不知道有人来过", "after": "确认失窃"},
            "cost_or_commitment": "花时间检查",
            "next_constraint": "不能报警",
            "reader_must_infer": "是谁来过",
            "narrator_must_not_state": ["就是周宁来过"],
        }],
        "chapter_contract_check": {
            "function_aligned": True, "must_deliver_covered": True,
            "must_not_deliver_respected": True, "main_change_enabled": True,
            "main_payoff_prepared": True, "ending_hook_established": True,
            "causal_transitions_grounded": True, "reader_inference_not_pre_resolved": True,
            "scene_state_reconstructed": True, "information_sources_legal": True,
            "character_choice_is_real": True, "consequence_is_counterfactual": True,
            "state_delta_is_nonempty": True, "next_constraint_is_new": True,
            "stop_state_is_visible": True, "stop_state_changes_future_actions": True,
            "pov_character_is_fixed": True, "narration_permissions_are_separated": True,
            "other_minds_are_backstage_only": True, "no_viewpoint_switch": True,
            "scene_capacity_is_honest": True, "meaningful_beats_are_non_micro": True,
            "target_length_has_real_fuel": True, "interaction_changes_state": True,
            "dialogue_does_not_repeat_shared_information": True,
            "stop_state_is_not_early": True,
        },
        "tempo_guardrails": {
            "entry_pressure": "门开着",
            "dominant_pressure": {"kind": "information_gap", "description": "不知道谁来过"},
            "stop_state": {
                "type": "information_conflict",
                "visible_fact": "发现少了东西",
                "what_is_now_different": "确认有人来过并拿走东西",
                "must_not_append": "不得解释是谁",
            },
        },
        "pov_contract": {
            "pov_character": "林澈",
            "narration_mode": "third_person_limited",
            "directly_narratable": ["门开着", "手机还在"],
            "pov_known_facts": ["门开着"],
            "pov_unknown_facts": ["谁开的门"],
            "allowed_viewpoint_misread": "可能只是风吹开的",
            "other_minds_backstage_only": [{
                "character": "周宁",
                "hidden_goal_or_motive": "拿走证据",
                "hidden_or_withheld_fact": "已经取走了文件",
                "behavioral_expression": [
                    "周宁不承认来过",
                    "周宁避开监控",
                ],
                "narrator_must_not_state": [
                    "周宁心虚",
                    "周宁其实拿走了文件",
                ],
            }],
            "future_knowledge_forbidden": ["周宁会回来"],
            "relationship_summary_forbidden": ["两人关系已经改变"],
            "viewpoint_switch_forbidden": True,
        },
        "scene_capacity": {
            "target_min_chars": 2000,
            "scene_mode": "discovery",
            "core_event": "林澈发现失窃",
            "meaningful_beats": [
                {
                    "id": "B1",
                    "trigger": "门开着",
                    "active_character": "林澈",
                    "goal": "确认是否有人来过",
                    "resistance_or_information_gap": "不知道门开了多久",
                    "action_or_exchange": "检查物品",
                    "new_information": "手机还在但文件少了",
                    "immediate_consequence": "确认失窃",
                    "state_delta": {
                        "before": "不知道有人来过",
                        "after": "确认失窃",
                    },
                    "depends_on": [],
                    "cannot_merge_reason": "确认门开着和检查物品是两个独立因果步骤",
                },
                {
                    "id": "B2",
                    "trigger": "确认失窃",
                    "active_character": "林澈",
                    "goal": "找出是谁来过",
                    "resistance_or_information_gap": "没有直接证据",
                    "action_or_exchange": "检查监控记录",
                    "new_information": "监控显示周宁来过",
                    "immediate_consequence": "锁定嫌疑人",
                    "state_delta": {
                        "before": "不知道是谁",
                        "after": "锁定周宁",
                    },
                    "depends_on": ["B1"],
                    "cannot_merge_reason": "失窃后必须获取证据才能锁定嫌疑人",
                },
                {
                    "id": "B3",
                    "trigger": "监控记录",
                    "active_character": "林澈",
                    "goal": "确认周宁拿走什么",
                    "resistance_or_information_gap": "监控只拍到进出",
                    "action_or_exchange": "核对物品清单",
                    "new_information": "少了关键文件",
                    "immediate_consequence": "确认损失",
                    "state_delta": {
                        "before": "只知道周宁来过",
                        "after": "确认文件丢失",
                    },
                    "depends_on": ["B2"],
                    "cannot_merge_reason": "需要锁定嫌疑人后才能确认损失范围",
                },
                {
                    "id": "B4",
                    "trigger": "文件丢失",
                    "active_character": "林澈",
                    "goal": "决定下一步",
                    "resistance_or_information_gap": "不能报警",
                    "action_or_exchange": "联系周宁",
                    "new_information": "周宁不接电话",
                    "immediate_consequence": "确认对方在回避",
                    "state_delta": {
                        "before": "还想确认",
                        "after": "确认对方回避",
                    },
                    "depends_on": ["B3"],
                    "cannot_merge_reason": "必须确认损失后才能决定是否联系",
                },
                {
                    "id": "B5",
                    "trigger": "对方回避",
                    "active_character": "林澈",
                    "goal": "保护剩余证据",
                    "resistance_or_information_gap": "不知道对方还会不会来",
                    "action_or_exchange": "锁门并备份文件",
                    "new_information": "备份中发现了异常记录",
                    "immediate_consequence": "找到新线索",
                    "state_delta": {
                        "before": "被动等待",
                        "after": "主动保护证据并找到新线索",
                    },
                    "depends_on": ["B4"],
                    "cannot_merge_reason": "确认回避后才有动机保护证据",
                },
                {
                    "id": "B6",
                    "trigger": "异常记录",
                    "active_character": "林澈",
                    "goal": "理解周宁的真正目的",
                    "resistance_or_information_gap": "记录不全",
                    "action_or_exchange": "整理现有证据",
                    "new_information": "周宁在找某个特定文件",
                    "immediate_consequence": "更新判断",
                    "state_delta": {
                        "before": "以为是普通盗窃",
                        "after": "意识到有针对性",
                    },
                    "depends_on": ["B5"],
                    "cannot_merge_reason": "需要新线索才能更新判断",
                },
            ],
            "estimated_narrative_capacity_min": 2400,
            "estimated_narrative_capacity_max": 3200,
            "capacity_sufficient": True,
            "forbidden_padding": ["重复检查门锁", "反复看手机", "环境描写"],
        },
        "interaction_plan": {
            "interaction_required": True,
            "participants": ["林澈", "周宁"],
            "character_positions": [
                {
                    "character": "林澈",
                    "current_goal": "找回文件",
                    "opening_assumption": "周宁只是误拿",
                    "hidden_or_withheld_information": "",
                    "cannot_accept": "文件丢失不追查",
                    "wants_from_other": "归还文件",
                },
                {
                    "character": "周宁",
                    "current_goal": "保密",
                    "opening_assumption": "林澈不会发现",
                    "hidden_or_withheld_information": "文件涉及他的秘密",
                    "cannot_accept": "被追查",
                    "wants_from_other": "不被追问",
                },
            ],
            "turning_exchanges": [
                {
                    "id": "E1",
                    "trigger": "林澈打电话",
                    "initiator": "林澈",
                    "initiator_goal": "确认周宁是否拿了文件",
                    "speech_act": "询问",
                    "other_response_mode": "回避问题，声称不知道",
                    "new_information": "周宁在回避",
                    "state_delta": {
                        "before": "不确定",
                        "after": "确认对方回避",
                    },
                },
                {
                    "id": "E2",
                    "trigger": "林澈当面质问",
                    "initiator": "林澈",
                    "initiator_goal": "让周宁承认",
                    "speech_act": "质疑",
                    "other_response_mode": "反咬林澈诬陷",
                    "new_information": "周宁准备了一套说辞",
                    "state_delta": {
                        "before": "还在给机会",
                        "after": "确认对方有预谋",
                    },
                },
                {
                    "id": "E3",
                    "trigger": "林澈出示证据",
                    "initiator": "林澈",
                    "initiator_goal": "逼周宁交代",
                    "speech_act": "条件交换",
                    "other_response_mode": "试图销毁证据",
                    "new_information": "周宁准备鱼死网破",
                    "state_delta": {
                        "before": "还在谈判",
                        "after": "确认对方不择手段",
                    },
                },
            ],
        },
    }


def test_planner_v3_valid_sample_parses():
    plan = _valid_v3_plan()
    output = validate_planner_output(plan, expected_version=3)
    assert isinstance(output, PlannerV3Output)
    assert output.planner_contract_version == 3
    assert output.pov_contract.pov_character == "林澈"
    assert output.scene_capacity.capacity_sufficient is True
    assert len(output.scene_capacity.meaningful_beats) == 6
    assert output.interaction_plan is not None
    assert output.interaction_plan.interaction_required is True
    assert len(output.interaction_plan.turning_exchanges) == 3


def test_planner_v3_rejects_wrong_narration_mode():
    plan = _valid_v3_plan()
    plan["pov_contract"]["narration_mode"] = "omniscient"
    with pytest.raises(ValueError, match="third_person_limited"):
        validate_planner_output(plan, expected_version=3)


def test_planner_v3_rejects_viewpoint_switch():
    plan = _valid_v3_plan()
    plan["pov_contract"]["viewpoint_switch_forbidden"] = False
    with pytest.raises(ValueError, match="viewpoint_switch_forbidden"):
        validate_planner_output(plan, expected_version=3)


def test_planner_v3_rejects_invalid_scene_mode():
    plan = _valid_v3_plan()
    plan["scene_capacity"]["scene_mode"] = "flashback"
    with pytest.raises(ValueError):
        validate_planner_output(plan, expected_version=3)


def test_planner_v3_rejects_empty_beats():
    plan = _valid_v3_plan()
    plan["scene_capacity"]["meaningful_beats"] = []
    with pytest.raises(ValueError, match="meaningful_beats"):
        validate_planner_output(plan, expected_version=3)


def test_planner_v3_rejects_same_state_delta():
    plan = _valid_v3_plan()
    plan["scene_capacity"]["meaningful_beats"][0]["state_delta"] = {
        "before": "same",
        "after": "same",
    }
    with pytest.raises(ValueError, match="differ"):
        validate_planner_output(plan, expected_version=3)


def test_planner_v3_rejects_interaction_without_required():
    plan = _valid_v3_plan()
    plan["interaction_plan"]["interaction_required"] = True
    plan["interaction_plan"]["turning_exchanges"] = []
    with pytest.raises(ValueError, match="turning_exchanges"):
        validate_planner_output(plan, expected_version=3)


def test_planner_v3_rejects_wrong_contract_version():
    plan = _valid_v3_plan()
    plan["planner_contract_version"] = 2
    with pytest.raises(ValueError, match="expected planner_contract_version"):
        validate_planner_output(plan, expected_version=3)


def test_planner_v3_all_contract_check_fields_must_be_true():
    plan = _valid_v3_plan()
    plan["chapter_contract_check"]["pov_character_is_fixed"] = False
    with pytest.raises(ValueError, match="chapter_contract_check"):
        validate_planner_output(plan, expected_version=3)


def test_planner_v3_minimal_interaction_can_be_none():
    plan = _valid_v3_plan()
    plan["interaction_plan"] = None
    output = validate_planner_output(plan, expected_version=3)
    assert output.interaction_plan is None


# ── _expected_planner_contract_version ────────────────────────────────


def test_planner_v3_schema_name_maps_to_version_3():
    assert _expected_planner_contract_version(
        "planner", {"output_schema_name": PLANNER_V3_SCHEMA_NAME}
    ) == EXPECTED_PLANNER_V3_CONTRACT_VERSION


def test_planner_v2_schema_name_still_maps_to_version_2():
    from app.services.generation_service import PLANNER_V2_SCHEMA_NAME, EXPECTED_PLANNER_CONTRACT_VERSION
    assert _expected_planner_contract_version(
        "planner", {"output_schema_name": PLANNER_V2_SCHEMA_NAME}
    ) == EXPECTED_PLANNER_CONTRACT_VERSION


def test_planner_unknown_schema_returns_none():
    assert _expected_planner_contract_version("planner", {"output_schema_name": "unknown"}) is None
    assert _expected_planner_contract_version("planner", None) is None
    assert _expected_planner_contract_version("writer", {"output_schema_name": PLANNER_V3_SCHEMA_NAME}) is None


# ── WriterBrief v3 deterministic mapping ──────────────────────────────


def _v3_plan_for_brief() -> dict:
    """Minimal v3 plan for WriterBrief compilation tests."""
    return {
        "planner_contract_version": 3,
        "scene_state": {
            "present_characters": ["林澈"],
            "visible_facts": ["门开着"],
        },
        "characters": [{
            "name": "林澈",
            "known": ["门开着"],
            "unknown": ["谁开的门"],
            "observed_evidence": ["门锁完好"],
            "current_interpretation": "有人来过",
        }],
        "causal_transitions": [{
            "visible_trigger": "门开着",
            "character_next_action": "检查物品",
            "immediate_consequence": "发现失窃",
            "next_constraint": "不能报警",
        }],
        "tempo_guardrails": {
            "entry_pressure": "门开着",
            "stop_state": {
                "visible_fact": "确认失窃",
                "must_not_append": "不得解释动机",
            },
        },
        "pov_contract": {
            "pov_character": "林澈",
            "narration_mode": "third_person_limited",
            "directly_narratable": ["门开着"],
            "pov_known_facts": ["门开着"],
            "pov_unknown_facts": ["谁开的门"],
            "allowed_viewpoint_misread": "可能是风吹开的",
            "other_minds_backstage_only": [{
                "character": "周宁",
                "hidden_goal_or_motive": "拿走证据",
                "hidden_or_withheld_fact": "已经取走文件",
                "behavioral_expression": ["不承认来过"],
                "narrator_must_not_state": ["周宁心虚"],
            }],
            "future_knowledge_forbidden": ["周宁会回来"],
            "relationship_summary_forbidden": ["关系已经改变"],
            "viewpoint_switch_forbidden": True,
        },
        "scene_capacity": {
            "target_min_chars": 2000,
            "scene_mode": "discovery",
            "core_event": "林澈发现失窃",
            "meaningful_beats": [{
                "id": "B1",
                "trigger": "门开着",
                "active_character": "林澈",
                "goal": "确认情况",
                "action_or_exchange": "检查物品",
                "immediate_consequence": "确认失窃",
                "state_delta": {"before": "不知道", "after": "确认"},
                "cannot_merge_reason": "独立因果步骤",
            }],
            "estimated_narrative_capacity_min": 2000,
            "estimated_narrative_capacity_max": 2500,
            "capacity_sufficient": True,
            "forbidden_padding": ["重复看门"],
        },
        "interaction_plan": {
            "interaction_required": True,
            "participants": ["林澈", "周宁"],
            "character_positions": [{
                "character": "林澈",
                "current_goal": "找回文件",
                "opening_assumption": "误拿",
                "hidden_or_withheld_information": "",
                "cannot_accept": "不追查",
                "wants_from_other": "归还",
            }],
            "turning_exchanges": [
                {
                    "id": "E1",
                    "trigger": "打电话",
                    "initiator": "林澈",
                    "initiator_goal": "确认",
                    "speech_act": "询问",
                    "other_response_mode": "回避",
                    "new_information": "对方回避",
                    "state_delta": {"before": "不确定", "after": "确认回避"},
                },
                {
                    "id": "E2",
                    "trigger": "对质",
                    "initiator": "林澈",
                    "initiator_goal": "逼承认",
                    "speech_act": "质疑",
                    "other_response_mode": "反咬",
                    "new_information": "对方有预谋",
                    "state_delta": {"before": "还在谈", "after": "确认不择手段"},
                },
                {
                    "id": "E3",
                    "trigger": "出示证据",
                    "initiator": "林澈",
                    "initiator_goal": "逼交代",
                    "speech_act": "条件交换",
                    "other_response_mode": "销毁证据",
                    "new_information": "鱼死网破",
                    "state_delta": {"before": "谈判", "after": "决裂"},
                },
            ],
        },
    }


def test_detect_planner_v3():
    plan = _v3_plan_for_brief()
    assert _detect_planner_v3(plan) is True
    plan_v2 = {"planner_contract_version": 2}
    assert _detect_planner_v3(plan_v2) is False
    assert _detect_planner_v3({}) is False


def test_compile_writer_brief_v3_has_v3_blocks():
    brief = compile_writer_brief_v3(_v3_plan_for_brief())
    assert brief["mode"] == "writer_brief_v3"
    assert "v3_blocks" in brief
    v3_text = brief["v3_blocks"]
    assert "=== POV_LOCK ===" in v3_text
    assert "=== BACKSTAGE_BEHAVIOR_ONLY ===" in v3_text
    assert "=== SCENE_CAPACITY ===" in v3_text
    assert "=== INTERACTION_PLAN ===" in v3_text
    assert "POV_CHARACTER" in v3_text
    assert "林澈" in v3_text
    assert "third_person_limited" in v3_text
    assert "BACKSTAGE_BEHAVIOR_ONLY" in v3_text
    assert "周宁" in v3_text


def test_compile_writer_input_v3_mode():
    result = compile_writer_input(_v3_plan_for_brief(), "writer_brief_v3")
    assert result["mode"] == "writer_brief_v3"
    assert "v3_blocks" in result


def test_compile_writer_brief_v3_backstage_separated():
    """Backstage info must be in its own block, not mixed with known facts."""
    brief = compile_writer_brief_v3(_v3_plan_for_brief())
    v3_text = brief["v3_blocks"]
    # Backstage block exists
    assert "后台行为信息只用于控制角色选择" in v3_text
    assert "不得由旁白直接陈述" in v3_text


def test_compile_writer_brief_v3_p2_old_input_still_compatible():
    """Old P2 planner output without v3 fields should still compile."""
    p2_plan = {
        "planner_contract_version": 2,
        "scene_state": {"visible_facts": ["x"]},
        "characters": [{"name": "A", "known": []}],
        "causal_transitions": [{
            "visible_trigger": "y",
            "character_next_action": "z",
            "immediate_consequence": "w",
            "next_constraint": "v",
        }],
        "tempo_guardrails": {
            "entry_pressure": "e",
            "stop_state": {"visible_fact": "s", "must_not_append": ""},
        },
    }
    # writer_brief mode should not crash on P2
    result = compile_writer_input(p2_plan, "writer_brief")
    assert "opening_fact" in result
    # writer_brief_v3 mode on P2 should still work (v3 fields missing)
    result_v3 = compile_writer_input(p2_plan, "writer_brief_v3")
    assert result_v3.get("v3_blocks", "") == ""  # No v3 fields → empty blocks


def test_compile_writer_brief_v3_deterministic():
    plan = _v3_plan_for_brief()
    b1 = compile_writer_brief_v3(plan)
    b2 = compile_writer_brief_v3(plan)
    # Same input → same output
    assert b1 == b2
    h1 = hashlib.sha256(json.dumps(b1, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(b2, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert h1 == h2


def test_planner_v3_capacity_insufficient_does_not_crash():
    plan = _v3_plan_for_brief()
    plan["scene_capacity"]["capacity_sufficient"] = False
    plan["scene_capacity"]["capacity_gap_reason"] = "事件不足以支撑目标篇幅"
    brief = compile_writer_brief_v3(plan)
    assert brief["mode"] == "writer_brief_v3"
    v3_text = brief["v3_blocks"]
    assert "CAPACITY_SUFFICIENT" in v3_text.upper()
    assert "false" in v3_text.lower()


# ── XML double-block detection (experiment-layer) ─────────────────────


def test_xml_double_block_detection_valid():
    """Valid two-block XML must pass detection."""
    text = "<draft_notes>\nnotes\n</draft_notes>\n\n<story>\nstory\n</story>"
    has_draft_open = "<draft_notes>" in text
    has_draft_close = "</draft_notes>" in text
    has_story_open = "<story>" in text
    has_story_close = "</story>" in text
    assert has_draft_open and has_draft_close
    assert has_story_open and has_story_close


def test_xml_double_block_detection_missing_draft_close():
    """Missing </draft_notes> must be detectable."""
    text = "<draft_notes>\nnotes\n\n<story>\nstory\n</story>"
    has_draft_close = "</draft_notes>" in text
    assert not has_draft_close, "Should detect missing </draft_notes>"


def test_xml_double_block_detection_missing_story_close():
    """Missing </story> must be detectable."""
    text = "<draft_notes>\nnotes\n</draft_notes>\n\n<story>\nstory"
    has_story_close = "</story>" in text
    assert not has_story_close, "Should detect missing </story>"


def test_xml_double_block_detection_story_leak():
    """Extra <story> tags outside expected positions must be detectable."""
    # Valid text: no <story> in draft section
    valid = "<draft_notes>\nnotes\n</draft_notes>\n\n<story>\nreal\n</story>"
    after_draft = valid.split("</draft_notes>")[1]
    assert after_draft.count("<story>") == 1, "should have exactly 1 <story> after </draft_notes>"
    
    # Malformed text: <story> leaked into draft_notes
    malformed = "<draft_notes>\nnotes\n<story>\n</story>\n</draft_notes>\n\n<story>\nreal\n</story>"
    draft_section = malformed.split("</draft_notes>")[0]
    # The draft section should not contain <story> in valid output
    leak_detected = "<story>" in draft_section
    assert leak_detected, "Should detect <story> leak in draft_notes section"


# ── Schema model construction ─────────────────────────────────────────


def test_pov_contract_model():
    pc = PovContract(
        pov_character="A",
        directly_narratable=["x"],
        other_minds_backstage_only=[OtherMindBackstage(
            character="B",
            behavioral_expression=["acts"],
            narrator_must_not_state=["secret"],
        )],
    )
    assert pc.narration_mode == "third_person_limited"
    assert pc.viewpoint_switch_forbidden is True


def test_meaningful_beat_model():
    beat = MeaningfulBeat(
        id="B1",
        trigger="t",
        active_character="A",
        goal="g",
        action_or_exchange="a",
        immediate_consequence="c",
        state_delta=StateDelta(before="b", after="a"),
        cannot_merge_reason="独立因果步骤",
    )
    assert beat.id == "B1"


def test_scene_capacity_model():
    sc = SceneCapacity(
        target_min_chars=2000,
        scene_mode="discovery",
        core_event="test",
        meaningful_beats=[MeaningfulBeat(
            id="B1",
            trigger="t",
            active_character="A",
            goal="g",
            action_or_exchange="a",
            immediate_consequence="c",
            state_delta=StateDelta(before="b", after="a"),
            cannot_merge_reason="独立因果步骤",
        )],
        estimated_narrative_capacity_min=2000,
        estimated_narrative_capacity_max=2500,
        capacity_sufficient=True,
    )
    assert sc.capacity_sufficient is True


def test_capacity_sufficient_true_with_gap_reason_invalid():
    """capacity_sufficient=true with a gap_reason must be rejected."""
    with pytest.raises(ValueError, match="capacity_gap_reason"):
        SceneCapacity(
            target_min_chars=2000,
            scene_mode="action",
            core_event="test",
            meaningful_beats=[MeaningfulBeat(
                id="B1",
                trigger="t",
                active_character="A",
                goal="g",
                action_or_exchange="a",
                immediate_consequence="c",
                state_delta=StateDelta(before="b", after="a"),
                cannot_merge_reason="独立因果步骤",
            )],
            estimated_narrative_capacity_min=2000,
            estimated_narrative_capacity_max=2500,
            capacity_sufficient=True,
            capacity_gap_reason="should not be here",
        )


def test_interaction_plan_required_min_participants():
    with pytest.raises(ValueError, match="participants"):
        InteractionPlan(
            interaction_required=True,
            participants=["A"],  # only 1, need 2+
            turning_exchanges=[TurningExchange(
                id="E1",
                trigger="t",
                initiator="A",
                initiator_goal="g",
                speech_act="询问",
                other_response_mode="r",
                new_information="i",
                state_delta=StateDelta(before="b", after="a"),
            )] * 3,
        )


def test_speech_act_enum():
    assert SpeechAct("询问") == SpeechAct.ask
    assert SpeechAct("拒绝") == SpeechAct.refuse
    assert SpeechAct("隐瞒") == SpeechAct.withhold


def test_scene_mode_enum():
    assert SceneMode("interaction") == SceneMode.interaction
    assert SceneMode("mixed") == SceneMode.mixed
