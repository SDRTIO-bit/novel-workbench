"""Deterministic compilation of Critic evidence into the canonical report."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re
from typing import Any

from pydantic import BaseModel, Field

from app.llm.output_contracts import (
    CausalCheckResult,
    ChapterContractCheck,
    CriticEvidenceOutput,
    CriticEvidenceReference,
    CriticIssue,
    CriticOutput,
    ProtectedStrength,
    TempoProfileCheck,
    validate_critic_evidence,
)


_PARAGRAPH_MARKER = re.compile(r"(?m)^\s*\[(P\d{3,})\]\s*")


def normalize_quote(text: str) -> str:
    return re.sub(r"[\s\u3000]+", " ", text.strip())


@dataclass(frozen=True)
class OrderedParagraphMap:
    paragraphs: OrderedDict[str, str]

    def has_paragraph(self, paragraph_id: str) -> bool:
        return paragraph_id in self.paragraphs

    def text(self, paragraph_id: str) -> str:
        return self.paragraphs[paragraph_id]

    def paragraphs_after(self, paragraph_id: str) -> list[str]:
        ids = list(self.paragraphs)
        return ids[ids.index(paragraph_id) + 1:]

    @staticmethod
    def normalize_quote(text: str) -> str:
        return normalize_quote(text)


def parse_numbered_draft(numbered_draft: str) -> OrderedParagraphMap:
    matches = list(_PARAGRAPH_MARKER.finditer(numbered_draft or ""))
    if not matches:
        raise ValueError("CRITIC_EVIDENCE_INVALID: numbered_draft has no labeled paragraphs")
    if numbered_draft[:matches[0].start()].strip():
        raise ValueError("CRITIC_EVIDENCE_INVALID: text exists before the first paragraph label")

    paragraphs: OrderedDict[str, str] = OrderedDict()
    for index, match in enumerate(matches):
        paragraph_id = match.group(1)
        if paragraph_id in paragraphs:
            raise ValueError(f"CRITIC_EVIDENCE_INVALID: duplicate paragraph_id {paragraph_id}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(numbered_draft)
        text = numbered_draft[match.end():end].strip()
        if not text:
            raise ValueError(f"CRITIC_EVIDENCE_INVALID: empty paragraph {paragraph_id}")
        paragraphs[paragraph_id] = text
    return OrderedParagraphMap(paragraphs)


def _reference_context(context: str, reference: CriticEvidenceReference) -> str:
    preview = normalize_quote(reference.quote)[:80]
    return f"{context}; paragraph_id={reference.paragraph_id}; quote={preview!r}"


def _validate_reference(
    paragraph_map: OrderedParagraphMap,
    reference: CriticEvidenceReference,
    context: str,
) -> None:
    if not paragraph_map.has_paragraph(reference.paragraph_id):
        raise ValueError(
            "CRITIC_EVIDENCE_INVALID: reference paragraph does not exist: "
            + _reference_context(context, reference)
        )
    if normalize_quote(reference.quote) not in normalize_quote(paragraph_map.text(reference.paragraph_id)):
        raise ValueError(
            "CRITIC_EVIDENCE_INVALID: reference quote was not found in numbered_draft: "
            + _reference_context(context, reference)
        )


def _planner_stop_state(planner: Any) -> dict[str, str]:
    if isinstance(planner, BaseModel):
        planner = planner.model_dump()
    if not isinstance(planner, dict):
        return {"visible_fact": "", "must_not_append": ""}
    tempo = planner.get("tempo_guardrails") or {}
    stop = tempo.get("stop_state") if isinstance(tempo, dict) else {}
    return {
        "visible_fact": str((stop or {}).get("visible_fact") or ""),
        "must_not_append": str((stop or {}).get("must_not_append") or ""),
    }


def _reference_paragraphs(*reference_lists: list[CriticEvidenceReference]) -> list[str]:
    return sorted(
        {reference.paragraph_id for references in reference_lists for reference in references},
        key=lambda paragraph_id: int(paragraph_id[1:]),
    )


class CriticCompilerTrace(BaseModel):
    evidence_contract_version: int = 1
    resolved_stop_paragraph: str | None = None
    derived_paragraphs_after_stop: list[str] = Field(default_factory=list)
    mandatory_issues_created: list[str] = Field(default_factory=list)
    general_findings_dropped_by_limit: list[str] = Field(default_factory=list)
    protected_paragraphs_removed_due_to_issues: list[str] = Field(default_factory=list)
    assigned_issue_ids: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class CriticCompilationResult:
    report: CriticOutput
    trace: CriticCompilerTrace


def _issue(
    issue_type: str,
    severity: str,
    paragraph_ids: list[str],
    problem: str,
    revision_goal: str,
    operation: str,
    priority: int,
) -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "severity": severity,
        "paragraph_ids": paragraph_ids,
        "problem": problem,
        "revision_goal": revision_goal,
        "recommended_operation": operation,
        "priority": priority,
    }


def compile_critic_report(
    evidence: CriticEvidenceOutput,
    planner: Any,
    numbered_draft: str,
) -> CriticCompilationResult:
    paragraph_map = parse_numbered_draft(numbered_draft)
    trace = CriticCompilerTrace(evidence_contract_version=evidence.critic_evidence_contract_version)

    if evidence.stop_audit.visible_fact_found:
        stop_reference = CriticEvidenceReference(
            paragraph_id=evidence.stop_audit.first_satisfied_paragraph_id,
            quote=evidence.stop_audit.quote,
            explanation=evidence.stop_audit.explanation,
        )
        _validate_reference(paragraph_map, stop_reference, "stop_audit")
        trace.resolved_stop_paragraph = stop_reference.paragraph_id

    for index, finding in enumerate(evidence.inference_findings):
        _validate_reference(paragraph_map, finding, f"inference_findings[{index}]")
    for transition in evidence.transition_audits:
        for name in (
            "trigger", "next_action", "immediate_consequence", "rejected_alternative",
            "cost_or_commitment", "next_constraint",
        ):
            finding = getattr(transition, name)
            for reference in finding.evidence:
                _validate_reference(paragraph_map, reference, f"transition_id={transition.transition_id}.{name}")
        for reference in transition.forbidden_explanation_evidence:
            _validate_reference(
                paragraph_map, reference,
                f"transition_id={transition.transition_id}.forbidden_explanation_evidence",
            )
    for strength in evidence.strength_candidates:
        for paragraph_id in strength.paragraph_ids:
            if not paragraph_map.has_paragraph(paragraph_id):
                raise ValueError(
                    "CRITIC_EVIDENCE_INVALID: strength candidate paragraph does not exist: "
                    f"paragraph_id={paragraph_id}"
                )
    for finding in evidence.general_findings:
        for paragraph_id in finding.paragraph_ids:
            if not paragraph_map.has_paragraph(paragraph_id):
                raise ValueError(
                    "CRITIC_EVIDENCE_INVALID: general finding paragraph does not exist: "
                    f"paragraph_id={paragraph_id}"
                )

    stop_state = _planner_stop_state(planner)
    compiled: list[dict[str, Any]] = []
    if evidence.stop_audit.visible_fact_found:
        after = paragraph_map.paragraphs_after(evidence.stop_audit.first_satisfied_paragraph_id)
        trace.derived_paragraphs_after_stop = after
        if after:
            trace.mandatory_issues_created.append("stop_state_overrun")
            visible_fact = stop_state["visible_fact"] or evidence.stop_audit.quote
            must_not_append = stop_state["must_not_append"] or "不得追加动作、解释或情绪余韵"
            compiled.append(_issue(
                "stop_state_overrun", "high", after,
                f"停止事实已在 {evidence.stop_audit.first_satisfied_paragraph_id} 成立，但其后段落仍继续存在。停止事实：{visible_fact}",
                f"保留 {evidence.stop_audit.first_satisfied_paragraph_id} 的可见停止事实，删除其后的内容；{must_not_append}",
                "tighten", 1,
            ))
    else:
        trace.mandatory_issues_created.append("hook_missing")
        compiled.append(_issue(
            "hook_missing", "high", [],
            "正文未找到 Planner 指定的停止状态可见事实。",
            "补足章节契约要求的停止状态可见事实，不以解释替代可见行动。",
            "clarify", 1,
        ))

    if evidence.inference_findings:
        paragraphs = sorted(
            {finding.paragraph_id for finding in evidence.inference_findings},
            key=lambda paragraph_id: int(paragraph_id[1:]),
        )
        quoted = "；".join(normalize_quote(finding.quote)[:120] for finding in evidence.inference_findings)
        trace.mandatory_issues_created.append("inference_overexplained")
        compiled.append(_issue(
            "inference_overexplained", "high" if any(f.severity == "high" for f in evidence.inference_findings) else "medium",
            paragraphs,
            f"旁白替读者完成了本应由动作推断的结论：{quoted}",
            "保留可见动作和必要信息，删除或改写直接完成心理、关系或主题判断的解释。",
            "withhold_inference", 2,
        ))

    causal_checks = []
    for transition in evidence.transition_audits:
        missing = []
        if not transition.rejected_alternative.visible:
            missing.append("替代路线")
        if not transition.cost_or_commitment.visible:
            missing.append("代价或承诺")
        if not transition.next_constraint.visible:
            missing.append("新约束")
        if missing:
            missing_evidence = _reference_paragraphs(
                transition.rejected_alternative.evidence,
                transition.cost_or_commitment.evidence,
                transition.next_constraint.evidence,
            )
            action_evidence = _reference_paragraphs(
                transition.trigger.evidence,
                transition.next_action.evidence,
                transition.immediate_consequence.evidence,
            )
            paragraphs = missing_evidence or action_evidence
            issue_type = "choice_cost_missing" if any(
                item in missing for item in ("替代路线", "代价或承诺")
            ) else "causal_transition_missing"
            trace.mandatory_issues_created.append(issue_type)
            compiled.append(_issue(
                issue_type, "high" if issue_type == "choice_cost_missing" else "medium", paragraphs,
                f"转折 {transition.transition_id} 已出现人物行动，但正文未让读者感受到：{'、'.join(missing)}。",
                f"在不改变既有场景结果的前提下，用具体行动或局面呈现 {'、'.join(missing)}。",
                "causalize", 3,
            ))

        failed = (
            not transition.trigger.visible
            or not transition.next_action.visible
            or not transition.immediate_consequence.visible
            or not transition.next_constraint.visible
            or not transition.reader_inference_withheld
            or bool(transition.forbidden_explanation_evidence)
        )
        causal_checks.append({
            "transition_id": transition.transition_id,
            "trigger_visible": transition.trigger.visible,
            "next_action_changed": transition.next_action.visible,
            "reader_inference_withheld": transition.reader_inference_withheld,
            "forbidden_explanation_found": [reference.quote for reference in transition.forbidden_explanation_evidence],
            "consequence_visible": transition.immediate_consequence.visible,
            "next_constraint_preserved": transition.next_constraint.visible,
            "paragraph_ids": _reference_paragraphs(
                transition.trigger.evidence, transition.next_action.evidence,
                transition.immediate_consequence.evidence, transition.rejected_alternative.evidence,
                transition.cost_or_commitment.evidence, transition.next_constraint.evidence,
                transition.forbidden_explanation_evidence,
            ),
            "result": CausalCheckResult.fail.value if failed else CausalCheckResult.pass_.value,
            "comment": "由已验证的 Evidence 引用确定。",
        })

    for finding in evidence.general_findings:
        compiled.append(_issue(
            finding.issue_type.value, finding.severity, finding.paragraph_ids,
            finding.problem, finding.revision_goal, finding.recommended_operation.value, 5,
        ))

    compiled.sort(key=lambda issue: (issue["priority"], -{"high": 3, "medium": 2, "low": 1}[issue["severity"]], issue["issue_type"]))
    retained = compiled[:5]
    trace.general_findings_dropped_by_limit = [
        issue["issue_type"] for issue in compiled[5:] if issue["priority"] == 5
    ]
    assigned_issues = []
    for index, issue in enumerate(retained, 1):
        issue_id = f"I{index:02d}"
        trace.assigned_issue_ids[issue_id] = issue["issue_type"]
        assigned_issues.append(CriticIssue(
            issue_id=issue_id,
            severity=issue["severity"],
            issue_type=issue["issue_type"],
            paragraph_ids=issue["paragraph_ids"],
            problem=issue["problem"],
            revision_goal=issue["revision_goal"],
            recommended_operation=issue["recommended_operation"],
        ))

    issue_paragraphs = {paragraph_id for issue in assigned_issues for paragraph_id in issue.paragraph_ids}
    protected_strengths = []
    removed = set()
    for candidate in evidence.strength_candidates:
        kept = [paragraph_id for paragraph_id in candidate.paragraph_ids if paragraph_id not in issue_paragraphs]
        removed.update(set(candidate.paragraph_ids) - set(kept))
        if kept:
            protected_strengths.append(ProtectedStrength(
                paragraph_ids=kept, reason=candidate.reason, strength_type=candidate.strength_type,
            ))
    trace.protected_paragraphs_removed_due_to_issues = sorted(removed, key=lambda paragraph_id: int(paragraph_id[1:]))

    tempo = evidence.tempo_observations
    ending_stops = bool(evidence.stop_audit.visible_fact_found) and not trace.derived_paragraphs_after_stop
    decision = "pass" if not assigned_issues else "local_revision"
    if any(issue.issue_type.value in {"contract_not_delivered", "contract_scope_creep"} for issue in assigned_issues):
        decision = "scene_rewrite"
    report = CriticOutput(
        overall_assessment=evidence.overall_assessment,
        decision=decision,
        strengths=[],
        issues=assigned_issues,
        protected_strengths=protected_strengths,
        chapter_contract_check=ChapterContractCheck(**evidence.chapter_contract_observations.model_dump()),
        causal_transition_check=causal_checks,
        tempo_profile_check=TempoProfileCheck(
            starts_in_motion=tempo.starts_in_motion,
            disruption_interrupts_action=tempo.disruption_interrupts_action,
            viewpoint_misread_is_actionable=tempo.viewpoint_misread_is_actionable,
            disclosure_cap_respected=tempo.disclosure_cap_respected,
            unclassified_facts_preserved=tempo.unclassified_facts_preserved,
            ending_stops_without_summary=ending_stops,
            formulaic_completion_risk=tempo.formulaic_completion_risk,
        ),
    )
    return CriticCompilationResult(report=report, trace=trace)
