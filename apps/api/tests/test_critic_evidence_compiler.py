import pytest

from app.llm.output_contracts import validate_critic_output
from app.services.critic_compiler import (
    compile_critic_report,
    parse_numbered_draft,
    validate_critic_evidence,
)


NUMBERED_DRAFT = """[P001] 老陈没有锁门，转身整理书架。

[P016] 小满喘得不太匀，像是憋了一路终于慢慢松开了胸腔。

[P024] 阿橘把鼻尖往前递了一寸，碰上了她的手背。湿的，凉的。

[P025] 街上的路灯还没亮。

[P026] 老陈从柜台下面摸出那盏老台灯。

[P027] 他把台灯往旁边转了半圈。"""


def _evidence_payload():
    return {
        "critic_evidence_contract_version": 1,
        "overall_assessment": "转折动作成立，但结尾越界且选择重量不足。",
        "stop_audit": {
            "visible_fact_found": True,
            "first_satisfied_paragraph_id": "P024",
            "quote": "阿橘把鼻尖往前递了一寸，碰上了她的手背。湿的，凉的。",
            "explanation": "该事实完成指定的停止状态。",
        },
        "inference_findings": [{
            "paragraph_id": "P016",
            "quote": "像是憋了一路终于慢慢松开了胸腔",
            "explanation": "比喻替读者确定了人物已经放松。",
            "severity": "high",
        }],
        "transition_audits": [{
            "transition_id": "CT01",
            "trigger": {"visible": True, "evidence": [{
                "paragraph_id": "P001", "quote": "老陈没有锁门",
                "explanation": "门未锁是可见触发。",
            }], "explanation": "触发有逐字证据。"},
            "next_action": {"visible": True, "evidence": [{
                "paragraph_id": "P001", "quote": "转身整理书架",
                "explanation": "人物随后以整理书架回应。",
            }], "explanation": "行动有逐字证据。"},
            "immediate_consequence": {"visible": True, "evidence": [{
                "paragraph_id": "P024", "quote": "碰上了她的手背",
                "explanation": "接触成为即时可见后果。",
            }], "explanation": "后果有逐字证据。"},
            "rejected_alternative": {
                "visible": False, "evidence": [], "explanation": "没有具体离开路线。",
            },
            "cost_or_commitment": {
                "visible": False, "evidence": [], "explanation": "未锁门没有可见代价。",
            },
            "next_constraint": {
                "visible": False, "evidence": [], "explanation": "没有持续行动限制。",
            },
            "reader_inference_withheld": False,
            "forbidden_explanation_evidence": [{
                "paragraph_id": "P016",
                "quote": "像是憋了一路终于慢慢松开了胸腔",
                "explanation": "旁白完成了应由读者推断的结论。",
            }],
        }],
        "general_findings": [{
            "issue_type": "hook_weak", "severity": "low", "paragraph_ids": ["P027"],
            "problem": "普通问题不应挤掉强制问题。",
            "revision_goal": "仅在有名额时处理。", "recommended_operation": "tighten",
        }],
        "strength_candidates": [{
            "paragraph_ids": ["P001", "P016"],
            "reason": "其中一个段落将被问题优先级移除。",
            "strength_type": "reader_inference_gap",
        }],
        "chapter_contract_observations": {
            "chapter_function_delivered": True, "must_deliver_satisfied": True,
            "must_not_deliver_respected": True, "main_change_advanced": True,
            "main_payoff_delivered": True, "ending_hook_set": True,
            "fuel_reserved": True, "target_length_met": True,
        },
        "tempo_observations": {
            "starts_in_motion": True, "disruption_interrupts_action": True,
            "viewpoint_misread_is_actionable": True, "disclosure_cap_respected": True,
            "unclassified_facts_preserved": True, "formulaic_completion_risk": "low",
        },
    }


def _planner_payload():
    return {
        "tempo_guardrails": {
            "stop_state": {
                "visible_fact": "小满的手背轻轻碰到阿橘仰起的鼻尖，没有缩回。",
                "must_not_append": "不得解释她为什么留下。",
            }
        }
    }


def test_compiler_creates_canonical_report_from_evidence_and_trace():
    result = compile_critic_report(
        validate_critic_evidence(_evidence_payload()),
        _planner_payload(),
        NUMBERED_DRAFT,
    )

    report = result.report.model_dump()
    assert [issue["issue_type"] for issue in report["issues"][:3]] == [
        "stop_state_overrun", "inference_overexplained", "choice_cost_missing",
    ]
    assert [issue["issue_id"] for issue in report["issues"][:3]] == ["I01", "I02", "I03"]
    assert report["issues"][0]["paragraph_ids"] == ["P025", "P026", "P027"]
    assert report["tempo_profile_check"]["ending_stops_without_summary"] is False
    assert report["protected_strengths"] == []
    assert result.trace.derived_paragraphs_after_stop == ["P025", "P026", "P027"]
    assert result.trace.protected_paragraphs_removed_due_to_issues == ["P001", "P016"]
    assert validate_critic_output(report).decision == "local_revision"


@pytest.mark.parametrize("paragraph_id, quote", [
    ("P999", "不存在"),
    ("P016", "Planner 写了但正文没有的句子"),
])
def test_evidence_validator_rejects_missing_or_nonverbatim_quotes(paragraph_id, quote):
    payload = _evidence_payload()
    payload["inference_findings"][0].update({"paragraph_id": paragraph_id, "quote": quote})

    with pytest.raises(ValueError, match="CRITIC_EVIDENCE_INVALID"):
        compile_critic_report(validate_critic_evidence(payload), _planner_payload(), NUMBERED_DRAFT)


def test_numbered_draft_parser_rejects_duplicate_or_unlabeled_paragraphs():
    with pytest.raises(ValueError, match="CRITIC_EVIDENCE_INVALID"):
        parse_numbered_draft("[P001] 一段\n\n[P001] 重复")
    with pytest.raises(ValueError, match="CRITIC_EVIDENCE_INVALID"):
        parse_numbered_draft("没有编号的段落")


def test_evidence_contract_requires_evidence_for_true_and_explanation_for_false():
    payload = _evidence_payload()
    payload["transition_audits"][0]["trigger"] = {
        "visible": True, "evidence": [], "explanation": "有证据但漏填。",
    }
    with pytest.raises(ValueError, match="CRITIC_EVIDENCE_INVALID"):
        validate_critic_evidence(payload)

    payload = _evidence_payload()
    payload["issue_id"] = "I01"
    with pytest.raises(ValueError, match="CRITIC_EVIDENCE_INVALID"):
        validate_critic_evidence(payload)

    payload = _evidence_payload()
    payload["general_findings"][0]["issue_id"] = "I01"
    with pytest.raises(ValueError, match="CRITIC_EVIDENCE_INVALID"):
        validate_critic_evidence(payload)

    payload = _evidence_payload()
    payload["transition_audits"][0]["next_constraint"]["explanation"] = ""
    with pytest.raises(ValueError, match="CRITIC_EVIDENCE_INVALID"):
        validate_critic_evidence(payload)


def test_compiler_derives_hook_missing_when_stop_fact_is_not_found():
    payload = _evidence_payload()
    payload["stop_audit"] = {
        "visible_fact_found": False,
        "first_satisfied_paragraph_id": "",
        "quote": "",
        "explanation": "没有找到指定可见事实。",
    }
    report = compile_critic_report(
        validate_critic_evidence(payload), _planner_payload(), NUMBERED_DRAFT
    ).report
    assert report.issues[0].issue_type == "hook_missing"
