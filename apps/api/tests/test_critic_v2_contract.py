import copy

import pytest

from app.llm.output_contracts import validate_critic_output, validate_stage_output
from app.prompts.defaults import BUILTIN_PROMPTS
from app.services.generation_service import _expected_critic_contract_version


def _valid_critic_v2_payload():
    return {
        "critic_contract_version": 2,
        "overall_assessment": "三项强制审计均发现了可定点修复的问题。",
        "decision": "local_revision",
        "strengths": ["开场动作仍然有效"],
        "issues": [
            {
                "issue_id": "I01",
                "severity": "high",
                "issue_type": "stop_state_overrun",
                "paragraph_ids": ["P024", "P025"],
                "problem": "停止事实成立后仍继续追加动作和收束。",
                "revision_goal": "保留停止事实，删除其后的追加段落。",
                "recommended_operation": "tighten",
            },
            {
                "issue_id": "I02",
                "severity": "medium",
                "issue_type": "inference_overexplained",
                "paragraph_ids": ["P022", "P024"],
                "problem": "旁白替读者完成了放松的心理推论。",
                "revision_goal": "保留可见动作，删除确定性心理结论。",
                "recommended_operation": "withhold_inference",
            },
            {
                "issue_id": "I03",
                "severity": "medium",
                "issue_type": "choice_cost_missing",
                "paragraph_ids": ["P006", "P012", "P018"],
                "problem": "行动发生了，但替代路线与延迟关店的代价没有成为现场压力。",
                "revision_goal": "利用已有事实使退路关闭和代价可感。",
                "recommended_operation": "causalize",
            },
        ],
        "protected_strengths": [
            {
                "paragraph_ids": ["P001"],
                "reason": "开场的门板动作提供了有效事实。",
                "strength_type": "reader_inference_gap",
            }
        ],
        "chapter_contract_check": {},
        "causal_transition_check": [],
        "tempo_profile_check": {
            "starts_in_motion": True,
            "disruption_interrupts_action": True,
            "viewpoint_misread_is_actionable": True,
            "disclosure_cap_respected": True,
            "unclassified_facts_preserved": True,
            "ending_stops_without_summary": False,
            "formulaic_completion_risk": "low",
        },
        "stop_state_audit": {
            "visible_fact_found": True,
            "first_satisfied_paragraph_id": "P023",
            "paragraphs_after_stop": ["P024", "P025"],
            "post_stop_new_action_found": True,
            "post_stop_emotional_summary_found": True,
            "issue_id": "I01",
        },
        "inference_audit": {
            "overexplained": True,
            "paragraph_ids": ["P022", "P024"],
            "quoted_phrases": ["像是憋了一路终于慢慢松开了胸腔"],
            "issue_id": "I02",
        },
        "choice_realization_check": [
            {
                "transition_id": "CT01",
                "rejected_alternative_visible": False,
                "cost_or_commitment_visible": False,
                "next_constraint_visible": True,
                "paragraph_ids": ["P006", "P012", "P018"],
                "issue_id": "I03",
                "comment": "替代路线和延迟关店的代价没有成为压力。",
            }
        ],
    }


def test_critic_v2_accepts_complete_self_consistent_audits():
    result = validate_critic_output(_valid_critic_v2_payload(), expected_version=2)

    assert result.critic_contract_version == 2
    assert result.stop_state_audit.issue_id == "I01"


@pytest.mark.parametrize("mutator", [
    lambda payload: (
        payload["issues"].pop(0),
        payload["stop_state_audit"].update({"issue_id": ""}),
    ),
    lambda payload: (
        payload["issues"].pop(1),
        payload["inference_audit"].update({"issue_id": ""}),
    ),
    lambda payload: (
        payload["issues"].pop(2),
        payload["choice_realization_check"][0].update({"issue_id": ""}),
    ),
    lambda payload: payload["protected_strengths"][0].update({"paragraph_ids": ["P024"]}),
    lambda payload: payload["tempo_profile_check"].update({"ending_stops_without_summary": True}),
    lambda payload: payload.pop("critic_contract_version"),
    lambda payload: payload.update({"critic_contract_version": 1}),
])
def test_critic_v2_rejects_inconsistent_required_audits(mutator):
    payload = copy.deepcopy(_valid_critic_v2_payload())
    mutator(payload)

    with pytest.raises(ValueError, match="CRITIC_OUTPUT_CONTRACT_INVALID"):
        validate_stage_output("critic", payload, expected_version=2)


def test_legacy_critic_contract_remains_compatible_without_v2_marker():
    result = validate_critic_output({
        "decision": "pass",
        "issues": [],
        "protected_strengths": [],
    })

    assert result.decision == "pass"


def test_expected_critic_contract_version_uses_explicit_schema_marker():
    assert _expected_critic_contract_version(
        "critic", {"output_schema_name": "critic_v2"}
    ) == 2
    assert _expected_critic_contract_version(
        "critic", {"output_schema_name": "critic"}
    ) is None
    assert _expected_critic_contract_version(
        "planner", {"output_schema_name": "critic_v2"}
    ) is None


def test_official_critic_prompt_requires_audits_before_strength_protection():
    critic = next(entry for entry in BUILTIN_PROMPTS if entry["stage"] == "critic")
    prompt = critic["system_template"]

    assert critic["output_schema_name"] == "critic_v2"

    for required_text in [
        "问题识别优先于亮点保护",
        "issue 段落不得进入 protected_strengths",
        "先找到 stop_state.visible_fact 第一次成立的位置",
        "rejected_alternative",
        "cost_or_commitment",
    ]:
        assert required_text in prompt
