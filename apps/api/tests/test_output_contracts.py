import pytest

from app.llm.output_contracts import (
    validate_critic_output,
    validate_planner_output,
    validate_reviser_output,
)


def _transition():
    return {
        "id": "CT01",
        "kind": "evidence_to_action",
        "visible_trigger": "接线盒里出现GR-0713",
        "character_next_action": "陆衡询问许栀父亲的名字",
        "reader_must_infer": "编号与许明远有关",
        "narrator_must_not_state": ["两个编号一致"],
        "immediate_consequence": "陆衡改变调查方向",
        "next_constraint": "他不能透露未来工单",
    }


def _tempo_guardrails():
    return {
        "entry_pressure": "林隅正把熄火的探测车拖回仓库。",
        "dominant_disruption": "冷却管里传出敲击声。",
        "allowed_viewpoint_misread": "他以为压力阀松了。",
        "disclosure_cap": 1,
        "must_remain_unclassified": ["敲击声来源"],
        "stop_after": "他切断外门电源。",
    }


def _planner_data():
    return {
        "scene_goal": "推进异常", "location": "机库", "time": "换班前",
        "characters": [], "pressure": "即将交班", "turning_point": "敲击声再次出现",
        "end_condition": "切断电源", "forbidden": [],
        "causal_transitions": [], "chapter_contract_check": {},
    }


def test_planner_accepts_tempo_guardrails():
    result = validate_planner_output({**_planner_data(), "tempo_guardrails": _tempo_guardrails()})

    assert result.tempo_guardrails.disclosure_cap == 1


def test_planner_normalizes_single_unclassified_fact():
    guardrails = {**_tempo_guardrails(), "must_remain_unclassified": "敲击声来源"}

    result = validate_planner_output({**_planner_data(), "tempo_guardrails": guardrails})

    assert result.tempo_guardrails.must_remain_unclassified == ["敲击声来源"]


@pytest.mark.parametrize("guardrails", [
    {**_tempo_guardrails(), "disclosure_cap": 2},
    {key: value for key, value in _tempo_guardrails().items() if key != "stop_after"},
])
def test_planner_rejects_invalid_tempo_guardrails(guardrails):
    with pytest.raises(ValueError, match="PLANNER_OUTPUT_CONTRACT_INVALID"):
        validate_planner_output({**_planner_data(), "tempo_guardrails": guardrails})


def test_planner_normalizes_common_real_llm_shape_variants():
    data = {
        **_planner_data(),
        "characters": ["首席维修员林隅", {"name": "门控系统", "goal": "维持门禁"}],
        "causal_transitions": [{
            **_transition(),
            "id": "ct_01",
            "reader_must_infer": ["敲击声不是普通故障", "林隅不愿深究"],
            "narrator_must_not_state": "敲击声的真实来源。",
        }],
        "chapter_contract_check": "本章完成异常发现并留下后续问题",
    }

    result = validate_planner_output(data)

    assert result.characters[0] == {"name": "首席维修员林隅"}
    assert result.causal_transitions[0].id == "CT01"
    assert result.causal_transitions[0].reader_must_infer == "敲击声不是普通故障；林隅不愿深究"
    assert result.causal_transitions[0].narrator_must_not_state == ["敲击声的真实来源。"]
    assert result.chapter_contract_check.function_aligned is True


def test_planner_normalizes_grouped_forbidden_values():
    data = {
        "scene_goal": "推进线索",
        "location": "悬空步道",
        "time": "深夜",
        "characters": [],
        "pressure": ["重力即将失效", "许栀悬在步道外侧"],
        "turning_point": "陆衡开始追查",
        "end_condition": "未来时间戳出现",
        "forbidden": {
            "must_not_deliver": ["不解释编号关系"],
            "fuel_reserved": ["不揭晓发送者"],
        },
        "causal_transitions": [_transition()],
        "chapter_contract_check": {},
    }

    result = validate_planner_output(data)

    assert result.forbidden == ["不解释编号关系", "不揭晓发送者"]
    assert result.pressure == "重力即将失效；许栀悬在步道外侧"


def test_critic_causal_check_accepts_numbered_paragraph_labels():
    data = {
        "overall_assessment": "因果转折成立",
        "decision": "pass",
        "strengths": ["失重危机场景的物理描写准确。"],
        "issues": [
            {
                "issue_id": "I01",
                "severity": "high",
                "issue_type": "inference_overexplained",
                "paragraph_ids": [71],
                "problem": "旁白提前解释方案。",
                "revision_goal": "删除解释，保留选择。",
                "recommended_operation": "withhold_inference",
            }
        ],
        "protected_strengths": [
            {
                "paragraph_id": "P001-P002",
                "reason": "证据后直接改变行动",
                "strength_type": "reader_inference_gap",
            }
        ],
        "chapter_contract_check": {},
        "causal_transition_check": [
            {
                "transition_id": "CT01",
                "trigger_visible": True,
                "next_action_changed": True,
                "reader_inference_withheld": True,
                "forbidden_explanation_found": True,
                "consequence_visible": True,
                "next_constraint_preserved": True,
                "paragraph_ids": ["P001", "P002"],
                "result": "fail",
                "comment": "发现解释",
            }
        ],
    }

    result = validate_critic_output(data)

    assert result.strengths == ["失重危机场景的物理描写准确。"]
    assert result.issues[0].paragraph_ids == ["P071"]
    assert result.protected_strengths[0].paragraph_ids == ["P001", "P002"]
    assert result.causal_transition_check[0].paragraph_ids == ["P001", "P002"]
    assert result.causal_transition_check[0].forbidden_explanation_found


def test_reviser_patch_accepts_integer_paragraph_ids():
    data = {
        "patches": [
            {
                "issue_id": "I01",
                "operation": "replace",
                "target_paragraph_ids": [71, 72],
                "replacement": "修改后的段落。",
            }
        ],
        "revised_text": "修改后的完整正文。",
        "unchanged_ratio": 0.9,
        "introduced_facts": [],
        "contract_verification": {},
    }

    result = validate_reviser_output(data)

    assert result.patches[0].target_paragraph_ids == ["P071", "P072"]


@pytest.mark.parametrize("issue_type, operation", [
    ("narrator_character_label", "de_label"),
    ("clue_conveyor_belt", "de_chain"),
    ("formulaic_escalation", "de_chain"),
    ("premature_classification", "de_chain"),
    ("closing_summary_hook", "tighten"),
])
def test_critic_accepts_tempo_issue_types(issue_type, operation):
    result = validate_critic_output({
        "overall_assessment": "x", "decision": "local_revision", "strengths": [],
        "protected_strengths": [], "chapter_contract_check": {}, "causal_transition_check": [],
        "issues": [{
            "issue_id": "I01", "severity": "medium", "issue_type": issue_type,
            "paragraph_ids": [1], "problem": "x", "revision_goal": "x",
            "recommended_operation": operation,
        }],
    })
    assert result.issues[0].issue_type.value == issue_type
