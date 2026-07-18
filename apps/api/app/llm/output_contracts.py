from __future__ import annotations

from enum import Enum
import re
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


def _paragraph_labels(value) -> list[str]:
    values = value if isinstance(value, list) else [value]
    labels: list[str] = []
    for item in values:
        if isinstance(item, int):
            labels.append(f"P{item:03d}")
            continue
        text = str(item).strip().upper().replace("—", "-")
        if "-" in text:
            start_text, end_text = text.split("-", 1)
            start_digits = start_text.removeprefix("P")
            end_digits = end_text.removeprefix("P")
            if start_digits.isdigit() and end_digits.isdigit():
                start, end = int(start_digits), int(end_digits)
                if 0 < start <= end and end - start <= 500:
                    labels.extend(f"P{number:03d}" for number in range(start, end + 1))
                    continue
        digits = text.removeprefix("P")
        labels.append(f"P{int(digits):03d}" if digits.isdigit() else text)
    return labels


# ── Enums ────────────────────────────────────────────────────────────

class CausalTransitionKind(str, Enum):
    evidence_to_action = "evidence_to_action"
    constraint_to_choice = "constraint_to_choice"


class CausalCheckResult(str, Enum):
    pass_ = "pass"
    fail = "fail"
    not_present = "not_present"


class CriticIssueType(str, Enum):
    opening_delay = "opening_delay"
    chapter_goal_unclear = "chapter_goal_unclear"
    protagonist_passive = "protagonist_passive"
    payoff_missing = "payoff_missing"
    fuel_overburn = "fuel_overburn"
    hook_missing = "hook_missing"
    hook_resolved_immediately = "hook_resolved_immediately"
    hook_weak = "hook_weak"
    pacing_drag = "pacing_drag"
    pacing_rush = "pacing_rush"
    dialogue_info_dump = "dialogue_info_dump"
    description_overload = "description_overload"
    tension_release_too_early = "tension_release_too_early"
    character_voice_inconsistent = "character_voice_inconsistent"
    show_vs_tell = "show_vs_tell"
    continuity_break = "continuity_break"
    exposition_clumsy = "exposition_clumsy"
    style_break = "style_break"
    target_length_overshoot = "target_length_overshoot"
    target_length_undershoot = "target_length_undershoot"
    contract_not_delivered = "contract_not_delivered"
    contract_scope_creep = "contract_scope_creep"
    inference_overexplained = "inference_overexplained"
    action_preannounced = "action_preannounced"
    technical_exposition_unconverted = "technical_exposition_unconverted"
    consequence_summarized = "consequence_summarized"
    causal_transition_missing = "causal_transition_missing"
    narrator_character_label = "narrator_character_label"
    clue_conveyor_belt = "clue_conveyor_belt"
    formulaic_escalation = "formulaic_escalation"
    premature_classification = "premature_classification"
    closing_summary_hook = "closing_summary_hook"


class RevisionOperation(str, Enum):
    naturalize = "naturalize"
    tighten = "tighten"
    clarify = "clarify"
    voice_align = "voice_align"
    ground_detail = "ground_detail"
    rhythm_adjust = "rhythm_adjust"
    diction_refine = "diction_refine"
    project_style_align = "project_style_align"
    withhold_inference = "withhold_inference"
    causalize = "causalize"
    de_label = "de_label"
    de_chain = "de_chain"


class ProtectedStrengthType(str, Enum):
    reader_inference_gap = "reader_inference_gap"
    choice_consequence_chain = "choice_consequence_chain"
    character_voice = "character_voice"
    scene_specific_detail = "scene_specific_detail"
    effective_roughness = "effective_roughness"


class JudgeDecision(str, Enum):
    accept_original = "accept_original"
    accept_revision = "accept_revision"
    accept_merged = "accept_merged"
    manual_review = "manual_review"


class PreferredVersion(str, Enum):
    original = "original"
    revision = "revision"
    manual_review = "manual_review"


class IssueStatus(str, Enum):
    resolved = "resolved"
    unresolved = "unresolved"
    revision_worse = "revision_worse"


class IssueAction(str, Enum):
    keep_revision = "keep_revision"
    restore_original = "restore_original"
    manual_review = "manual_review"


# ── Planner ───────────────────────────────────────────────────────────

class StateDelta(BaseModel):
    before: str = ""
    after: str = ""


class CausalTransition(BaseModel):
    id: str
    kind: CausalTransitionKind
    visible_trigger: str = Field(min_length=1)
    character_interpretation: str = ""
    character_next_action: str = Field(min_length=1)
    rejected_alternative: str = ""
    immediate_consequence: str = Field(min_length=1)
    counterfactual_without_action: str = ""
    state_delta: StateDelta | None = None
    cost_or_commitment: str = ""
    next_constraint: str = Field(min_length=1)
    reader_must_infer: str = Field(min_length=1)
    narrator_must_not_state: list[str] = Field(min_length=1)

    @field_validator("id", mode="before")
    @classmethod
    def normalize_id(cls, value):
        text = str(value).strip().upper().replace("_", "")
        if text.startswith("CT") and text[2:].isdigit():
            return f"CT{int(text[2:]):02d}"
        return value

    @field_validator("reader_must_infer", mode="before")
    @classmethod
    def normalize_reader_inference(cls, value):
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return "；".join(item.strip() for item in value if item.strip())
        return value

    @field_validator("narrator_must_not_state", mode="before")
    @classmethod
    def normalize_single_withheld_statement(cls, value):
        return [value] if isinstance(value, str) else value


class PlannerChapterContractCheck(BaseModel):
    function_aligned: bool = True
    must_deliver_covered: bool = True
    must_not_deliver_respected: bool = True
    main_change_enabled: bool = True
    main_payoff_prepared: bool = True
    ending_hook_established: bool = True
    causal_transitions_grounded: bool = True
    reader_inference_not_pre_resolved: bool = True
    scene_state_reconstructed: bool = True
    information_sources_legal: bool = True
    character_choice_is_real: bool = True
    consequence_is_counterfactual: bool = True
    state_delta_is_nonempty: bool = True
    next_constraint_is_new: bool = True
    stop_state_is_visible: bool = True
    stop_state_changes_future_actions: bool = True


class DominantPressure(BaseModel):
    kind: str = "none"
    description: str = Field(min_length=1)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value):
        allowed = {"physical_problem", "social_friction", "resource_constraint", "unfinished_commitment", "information_gap", "none"}
        if value not in allowed:
            raise ValueError(f"dominant_pressure.kind must be one of {sorted(allowed)}, got {value!r}")
        return value


class StopState(BaseModel):
    type: str
    visible_fact: str = Field(min_length=1)
    what_is_now_different: str = Field(min_length=1)
    must_not_append: str = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, value):
        allowed = {"physical_change", "social_commitment", "relationship_shift", "information_conflict", "unresolved_problem"}
        if value not in allowed:
            raise ValueError(f"stop_state.type must be one of {sorted(allowed)}, got {value!r}")
        return value


class TempoGuardrails(BaseModel):
    entry_pressure: str = Field(min_length=1)
    dominant_pressure: DominantPressure
    allowed_viewpoint_misread: str = ""
    disclosure_cap: int = Field(default=1, ge=0, le=1)
    must_remain_unclassified: list[str] = Field(default_factory=list)
    stop_state: StopState
    final_line_must_include: str = ""

    @field_validator("must_remain_unclassified", mode="before")
    @classmethod
    def normalize_single_unclassified_fact(cls, value):
        return [value] if isinstance(value, str) else value

    @field_validator("must_remain_unclassified")
    @classmethod
    def require_non_empty_strings(cls, value):
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError("must_remain_unclassified must contain non-empty strings")
        return value


class SceneState(BaseModel):
    last_completed_action: str = ""
    present_characters: list[str] = Field(default_factory=list)
    visible_facts: list[str] = Field(default_factory=list)
    available_objects: list[str] = Field(default_factory=list)
    unresolved_problem: str = ""
    already_existing_constraints: list[str] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    scene_goal: str = ""
    location: str = ""
    time: str = ""
    scene_state: SceneState | None = None
    characters: list[dict[str, Any]] = []
    concrete_problem: str = ""
    pressure: str = ""
    turning_point: str = ""
    end_condition: str = ""
    forbidden: list[str] = []
    causal_transitions: list[CausalTransition] = Field(default_factory=list, max_length=3)
    chapter_contract_check: PlannerChapterContractCheck = Field(default_factory=PlannerChapterContractCheck)
    tempo_guardrails: TempoGuardrails | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_common_llm_shapes(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        characters = normalized.get("characters")
        if isinstance(characters, list):
            normalized["characters"] = [
                {"name": item} if isinstance(item, str) else item
                for item in characters
            ]
        if isinstance(normalized.get("chapter_contract_check"), str):
            normalized["chapter_contract_check"] = {}
        return normalized

    @field_validator("forbidden", mode="before")
    @classmethod
    def normalize_grouped_forbidden(cls, value):
        if not isinstance(value, dict):
            return value
        flattened: list[str] = []
        for group in value.values():
            if isinstance(group, list):
                flattened.extend(str(item) for item in group)
            elif group is not None:
                flattened.append(str(group))
        return flattened

    @field_validator("pressure", mode="before")
    @classmethod
    def normalize_pressure_list(cls, value):
        if isinstance(value, list):
            return "；".join(str(item) for item in value)
        return value

    @model_validator(mode="after")
    def check_transition_ids(self):
        ids = [ct.id for ct in self.causal_transitions]
        if len(ids) != len(set(ids)):
            raise ValueError("PLANNER_OUTPUT_CONTRACT_INVALID: causal_transitions ids must be unique")
        for ct in self.causal_transitions:
            if not ct.id.startswith("CT") or not ct.id[2:].isdigit():
                raise ValueError(
                    f"PLANNER_OUTPUT_CONTRACT_INVALID: causal_transition id '{ct.id}' "
                    f"must follow format CT01, CT02, CT03"
                )
        return self


def validate_planner_output(data: dict) -> PlannerOutput:
    try:
        return PlannerOutput(**data)
    except Exception as e:
        raise ValueError(f"PLANNER_OUTPUT_CONTRACT_INVALID: {e}") from e


def validate_tempo_final_line(text: str, tempo_guardrails: dict | None) -> None:
    """Require an explicit author-supplied hook marker to survive at the end.

    This is intentionally opt-in. It does not rewrite prose or infer a meaning
    from a detector score; it only prevents a revision from deleting the
    concrete final fact the author marked as non-negotiable.
    """
    marker = (tempo_guardrails or {}).get("final_line_must_include", "")
    marker = str(marker).strip()
    if not marker:
        return
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    final_paragraph = paragraphs[-1] if paragraphs else ""
    if marker not in final_paragraph:
        raise ValueError(
            "TEMPO_FINAL_LINE_MISMATCH: final paragraph must include "
            f"the required marker {marker!r}"
        )


# ── Critic ────────────────────────────────────────────────────────────

class CriticIssue(BaseModel):
    issue_id: str = Field(min_length=1)
    severity: str = "low"
    issue_type: CriticIssueType
    paragraph_ids: list[str] = Field(default_factory=list)
    problem: str = ""
    revision_goal: str = ""
    recommended_operation: RevisionOperation

    @field_validator("paragraph_ids", mode="before")
    @classmethod
    def normalize_paragraph_ids(cls, value):
        return _paragraph_labels(value)


class ProtectedStrength(BaseModel):
    paragraph_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    strength_type: ProtectedStrengthType | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_singular_paragraph_id(cls, value):
        if isinstance(value, dict) and "paragraph_ids" not in value and "paragraph_id" in value:
            value = {**value, "paragraph_ids": value["paragraph_id"]}
        return value

    @field_validator("paragraph_ids", mode="before")
    @classmethod
    def normalize_paragraph_ids(cls, value):
        return _paragraph_labels(value)


class CausalTransitionCheck(BaseModel):
    transition_id: str
    trigger_visible: bool = True
    next_action_changed: bool = True
    reader_inference_withheld: bool = True
    forbidden_explanation_found: list[str] = Field(default_factory=list)
    consequence_visible: bool = True
    next_constraint_preserved: bool = True
    paragraph_ids: list[str] = Field(default_factory=list)
    result: CausalCheckResult = CausalCheckResult.pass_
    comment: str = ""

    @field_validator("paragraph_ids", mode="before")
    @classmethod
    def normalize_paragraph_ids(cls, value):
        return _paragraph_labels(value)

    @field_validator("forbidden_explanation_found", mode="before")
    @classmethod
    def normalize_forbidden_explanations(cls, value):
        if value is False or value is None:
            return []
        if value is True:
            return ["存在禁止解释（模型未提供摘录）"]
        if isinstance(value, str):
            return [value]
        return value


class ChapterContractCheck(BaseModel):
    chapter_function_delivered: bool = True
    must_deliver_satisfied: bool = True
    must_not_deliver_respected: bool = True
    main_change_advanced: bool = True
    main_payoff_delivered: bool = True
    ending_hook_set: bool = True
    fuel_reserved: bool = True
    target_length_met: bool = True


class TempoProfileCheck(BaseModel):
    starts_in_motion: bool = True
    disruption_interrupts_action: bool = True
    viewpoint_misread_is_actionable: bool = True
    disclosure_cap_respected: bool = True
    unclassified_facts_preserved: bool = True
    ending_stops_without_summary: bool = True
    formulaic_completion_risk: Literal["low", "medium", "high"] = "low"


class CriticOutput(BaseModel):
    overall_assessment: str = ""
    decision: str = ""
    strengths: list[Any] = Field(default_factory=list)
    issues: list[CriticIssue] = Field(default_factory=list)
    protected_strengths: list[ProtectedStrength] = Field(default_factory=list)
    chapter_contract_check: ChapterContractCheck = Field(default_factory=ChapterContractCheck)
    causal_transition_check: list[CausalTransitionCheck] = Field(default_factory=list)
    tempo_profile_check: TempoProfileCheck | None = None

    @model_validator(mode="after")
    def check_result_consistency(self):
        for ct in self.causal_transition_check:
            any_false = not all([
                ct.trigger_visible, ct.next_action_changed,
                ct.reader_inference_withheld, ct.consequence_visible,
                ct.next_constraint_preserved,
            ]) or bool(ct.forbidden_explanation_found)
            if any_false and ct.result == CausalCheckResult.pass_:
                raise ValueError(
                    f"CRITIC_OUTPUT_CONTRACT_INVALID: {ct.transition_id} has failed checks "
                    f"but result is 'pass'"
                )
        return self


def validate_critic_output(data: dict) -> CriticOutput:
    try:
        return CriticOutput(**data)
    except Exception as e:
        raise ValueError(f"CRITIC_OUTPUT_CONTRACT_INVALID: {e}") from e


# ── Reviser ───────────────────────────────────────────────────────────

class Patch(BaseModel):
    issue_id: str = ""
    operation: str = "replace"
    target_paragraph_ids: list[str] = Field(default_factory=list)
    replacement: str = ""

    @field_validator("target_paragraph_ids", mode="before")
    @classmethod
    def normalize_target_paragraph_ids(cls, value):
        return _paragraph_labels(value)


class ContractVerification(BaseModel):
    chapter_function_preserved: bool = True
    must_deliver_preserved: bool = True
    must_not_deliver_respected: bool = True
    main_change_preserved: bool = True
    main_payoff_preserved: bool = True
    ending_hook_preserved: bool = True
    fuel_remains_reserved: bool = True


class ReviserOutput(BaseModel):
    patches: list[Patch] = Field(default_factory=list)
    revised_text: str = Field(min_length=1)
    unchanged_ratio: float = Field(ge=0.0, le=1.0)
    introduced_facts: list[str] = Field(default_factory=list)
    contract_verification: ContractVerification = Field(default_factory=ContractVerification)


def validate_reviser_output(data: dict) -> ReviserOutput:
    try:
        return ReviserOutput(**data)
    except Exception as e:
        raise ValueError(f"REVISER_OUTPUT_CONTRACT_INVALID: {e}") from e


# ── Judge ─────────────────────────────────────────────────────────────

class CausalTransitionResult(BaseModel):
    transition_id: str
    original_status: CausalCheckResult = CausalCheckResult.pass_
    revision_status: CausalCheckResult = CausalCheckResult.pass_
    preferred_version: PreferredVersion = PreferredVersion.original
    comment: str = ""


class IssueResult(BaseModel):
    issue_id: str
    status: IssueStatus = IssueStatus.resolved
    action: IssueAction = IssueAction.keep_revision
    comment: str = ""


class JudgeOutput(BaseModel):
    decision: JudgeDecision = JudgeDecision.manual_review
    issue_results: list[IssueResult] = Field(default_factory=list)
    new_problems: list[dict[str, Any]] = Field(default_factory=list)
    revision_became_cleaner_but_flatter: bool = False
    author_intent_preserved: bool = True
    chapter_contract_completed: bool = True
    main_payoff_preserved: bool = True
    final_text: str = ""
    quality_score: int = Field(ge=0, le=100)
    state_patch: dict[str, Any] = Field(default_factory=dict)
    reader_inference_preserved: bool = True
    decision_consequence_preserved: bool = True
    narrator_management_reduced: bool = True
    necessary_information_lost: bool = False
    causal_transition_results: list[CausalTransitionResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_information_lost_blocks_accept(self):
        if self.necessary_information_lost and self.decision == JudgeDecision.accept_revision:
            raise ValueError(
                "JUDGE_OUTPUT_CONTRACT_INVALID: necessary_information_lost=true "
                "but decision is accept_revision"
            )
        if self.decision == JudgeDecision.accept_merged and not self.final_text.strip():
            raise ValueError(
                "JUDGE_OUTPUT_CONTRACT_INVALID: decision is accept_merged "
                "but final_text is empty"
            )
        return self


def validate_judge_output(data: dict) -> JudgeOutput:
    try:
        return JudgeOutput(**data)
    except Exception as e:
        raise ValueError(f"JUDGE_OUTPUT_CONTRACT_INVALID: {e}") from e


def validate_judge_output_for_selected_issues(
    data: dict,
    selected_issue_ids: list[str],
) -> JudgeOutput:
    """Validate a judge result against the issues actually sent to Reviser.

    A judge may report new problems, but it cannot claim to have resolved an
    issue that was not selected for revision. This keeps the merge decision
    tethered to the user's chosen edit scope instead of trusting an LLM's
    self-assessment.
    """
    output = validate_judge_output(data)
    if selected_issue_ids:
        selected = set(selected_issue_ids)
        reported = [result.issue_id for result in output.issue_results]
        unexpected = set(reported) - selected
        missing = selected - set(reported)
        if unexpected or missing:
            details = []
            if unexpected:
                details.append(f"unexpected issue_results: {sorted(unexpected)}")
            if missing:
                details.append(f"missing issue_results: {sorted(missing)}")
            raise ValueError("JUDGE_OUTPUT_CONTRACT_INVALID: " + "; ".join(details))

    if output.decision in (JudgeDecision.accept_revision, JudgeDecision.accept_merged):
        if not output.chapter_contract_completed or not output.main_payoff_preserved:
            raise ValueError(
                "JUDGE_OUTPUT_CONTRACT_INVALID: accepting a revision requires "
                "chapter_contract_completed and main_payoff_preserved"
            )

    if output.decision == JudgeDecision.accept_merged and re.search(r"(?m)^\s*\[P\d{3}\]", output.final_text):
        raise ValueError(
            "JUDGE_OUTPUT_CONTRACT_INVALID: merged final_text must not contain paragraph labels"
        )
    return output


# ── Stage-level dispatch ──────────────────────────────────────────────

def validate_stage_output(stage: str, data: dict) -> dict:
    """Validate stage output and return normalized data.
    Raises ValueError with stage-specific error code on failure.
    """
    if stage == "planner":
        return validate_planner_output(data).model_dump()
    elif stage == "critic":
        return validate_critic_output(data).model_dump()
    elif stage == "reviser":
        return validate_reviser_output(data).model_dump()
    elif stage == "judge":
        return validate_judge_output(data).model_dump()
    else:
        return data
