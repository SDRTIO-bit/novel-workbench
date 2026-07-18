from __future__ import annotations

from enum import Enum
import re
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# Trailing punctuation stripped before deterministic equality comparisons.
# Covers common CJK and ASCII sentence-final punctuation only; interior
# punctuation is never touched.
_COMPARE_TRAILING_PUNCT = (
    "。，、；：！？…·—～"
    "「」『』（）《》〈〉【】“”‘’"
    ".,;:!?~\"'()[]<>-"
)


def _normalize_for_compare(text: str) -> str:
    """Deterministic normalization for equality comparisons.

    strip → collapse consecutive whitespace → strip trailing common
    punctuation → lowercase (a no-op for CJK). Deliberately simple: no
    embeddings, no synonym handling, no LLM judgment.
    """
    normalized = re.sub(r"\s+", " ", str(text).strip())
    normalized = normalized.rstrip(_COMPARE_TRAILING_PUNCT).strip()
    return normalized.lower()


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


_PARAGRAPH_LABEL_RE = re.compile(r"^P(?!0+$)\d{3,}$")


def _is_paragraph_label(value: str) -> bool:
    return bool(_PARAGRAPH_LABEL_RE.fullmatch(value))


def _sorted_unique_paragraph_labels(values: list[str]) -> list[str]:
    return sorted(set(values), key=lambda label: int(label[1:]))


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
    stop_state_overrun = "stop_state_overrun"
    choice_cost_missing = "choice_cost_missing"
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

    @model_validator(mode="after")
    def check_nonempty_and_different(self):
        if not self.before.strip():
            raise ValueError("state_delta.before must not be empty")
        if not self.after.strip():
            raise ValueError("state_delta.after must not be empty")
        if _normalize_for_compare(self.before) == _normalize_for_compare(self.after):
            raise ValueError("state_delta.before and after must differ")
        return self


class CausalTransition(BaseModel):
    id: str
    kind: CausalTransitionKind
    visible_trigger: str = Field(min_length=1)
    character_interpretation: str = ""
    character_next_action: str = Field(min_length=1)
    rejected_alternative: str = ""
    immediate_consequence: str = Field(min_length=1)
    counterfactual_without_action: str = ""
    consequence_would_still_happen: bool | None = None
    state_delta: StateDelta | None = None
    cost_or_commitment: str = ""
    next_constraint: str = Field(min_length=1)
    reader_must_infer: str = Field(min_length=1)
    narrator_must_not_state: list[str] = Field(min_length=1)

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value):
        if isinstance(value, str):
            value = value.strip()
            # Map Chinese values to English enum values
            chinese_to_english = {
                "证据到行动": "evidence_to_action",
                "约束到选择": "constraint_to_choice",
            }
            if value in chinese_to_english:
                return chinese_to_english[value]
        return value

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
    function_aligned: bool = False
    must_deliver_covered: bool = False
    must_not_deliver_respected: bool = False
    main_change_enabled: bool = False
    main_payoff_prepared: bool = False
    ending_hook_established: bool = False
    causal_transitions_grounded: bool = False
    reader_inference_not_pre_resolved: bool = False
    scene_state_reconstructed: bool = False
    information_sources_legal: bool = False
    character_choice_is_real: bool = False
    consequence_is_counterfactual: bool = False
    state_delta_is_nonempty: bool = False
    next_constraint_is_new: bool = False
    stop_state_is_visible: bool = False
    stop_state_changes_future_actions: bool = False


class DominantPressure(BaseModel):
    kind: str = "none"
    description: str = Field(min_length=1)

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

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

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

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
    planner_contract_version: int = 1
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
        elif isinstance(characters, dict):
            normalized_characters = []
            for name, character in characters.items():
                if not isinstance(character, dict):
                    raise ValueError(
                        "characters name-map values must be objects; "
                        "cannot safely infer a character from a scalar"
                    )
                normalized_character = dict(character)
                if not str(normalized_character.get("name") or "").strip():
                    normalized_character["name"] = name
                normalized_characters.append(normalized_character)
            normalized["characters"] = normalized_characters
        if isinstance(normalized.get("chapter_contract_check"), str):
            normalized["chapter_contract_check"] = {}
        # Handle scene_state being a string instead of object - convert to minimal object
        scene_state = normalized.get("scene_state")
        if isinstance(scene_state, str) and scene_state.strip():
            # Convert string description to minimal object structure
            normalized["scene_state"] = {
                "last_completed_action": "",
                "present_characters": [],
                "visible_facts": [],
                "available_objects": [],
                "unresolved_problem": scene_state.strip(),
                "already_existing_constraints": [],
            }
        # Handle state_delta being a string instead of object in causal_transitions
        causal_transitions = normalized.get("causal_transitions")
        if isinstance(causal_transitions, list):
            for i, ct in enumerate(causal_transitions):
                if isinstance(ct, dict):
                    state_delta = ct.get("state_delta")
                    if isinstance(state_delta, str) and state_delta.strip():
                        # Try to parse "before -> after" or "before → after" pattern
                        parts = None
                        for sep in [" -> ", " → ", "→", "->"]:
                            if sep in state_delta:
                                parts = state_delta.split(sep, 1)
                                break
                        if parts and len(parts) == 2:
                            ct["state_delta"] = {
                                "before": parts[0].strip().strip("'\""),
                                "after": parts[1].strip().strip("'\""),
                            }
                        else:
                            # Fallback: put the whole string in "after", leave "before" empty
                            ct["state_delta"] = {
                                "before": "",
                                "after": state_delta.strip(),
                            }
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


def validate_planner_output(data: dict, expected_version: int | None = None) -> PlannerOutput:
    # When a workflow declares the contract version it expects, a missing
    # version field is a hard failure instead of a silent default to v1.
    if (
        expected_version is not None
        and isinstance(data, dict)
        and "planner_contract_version" not in data
    ):
        raise ValueError(
            f"PLANNER_OUTPUT_CONTRACT_INVALID: planner_contract_version is required "
            f"(expected planner_contract_version={expected_version})"
        )
    try:
        output = PlannerOutput(**data)
    except Exception as e:
        raise ValueError(f"PLANNER_OUTPUT_CONTRACT_INVALID: {e}") from e

    version = output.planner_contract_version
    
    if expected_version is not None and version != expected_version:
        raise ValueError(
            f"PLANNER_OUTPUT_CONTRACT_INVALID: expected planner_contract_version={expected_version}, "
            f"got {version}"
        )
    
    if version >= 2:
        errors = []
        
        if not output.scene_state:
            errors.append("scene_state is required in v2")
        elif not output.scene_state.present_characters:
            errors.append("scene_state.present_characters must not be empty")
        elif not output.scene_state.visible_facts:
            errors.append("scene_state.visible_facts must not be empty")
        
        if not output.concrete_problem:
            errors.append("concrete_problem is required in v2")
        
        if not output.causal_transitions:
            errors.append("at least one causal_transition is required in v2")
        
        existing_constraints_normalized = set()
        if output.scene_state and output.scene_state.already_existing_constraints:
            for c in output.scene_state.already_existing_constraints:
                normalized = _normalize_for_compare(c)
                if normalized:
                    existing_constraints_normalized.add(normalized)
        
        for i, ct in enumerate(output.causal_transitions):
            if not ct.character_interpretation:
                errors.append(f"causal_transitions[{i}].character_interpretation is required in v2")
            if not ct.rejected_alternative:
                errors.append(f"causal_transitions[{i}].rejected_alternative is required in v2")
            if not ct.counterfactual_without_action:
                errors.append(f"causal_transitions[{i}].counterfactual_without_action is required in v2")
            if ct.consequence_would_still_happen is not False:
                errors.append(f"causal_transitions[{i}].consequence_would_still_happen must be false in v2")
            if not ct.state_delta:
                errors.append(f"causal_transitions[{i}].state_delta is required in v2")
            if not ct.cost_or_commitment:
                errors.append(f"causal_transitions[{i}].cost_or_commitment is required in v2")
            
            next_constraint_normalized = _normalize_for_compare(ct.next_constraint)
            if next_constraint_normalized in existing_constraints_normalized:
                errors.append(
                    f"causal_transitions[{i}].next_constraint duplicates an already_existing_constraint"
                )
        
        if output.tempo_guardrails:
            if not output.tempo_guardrails.stop_state:
                errors.append("tempo_guardrails.stop_state is required when tempo_guardrails present")
        
        contract_check = output.chapter_contract_check
        failing_fields = []
        for field_name in PlannerChapterContractCheck.model_fields:
            if not getattr(contract_check, field_name):
                failing_fields.append(field_name)
        if failing_fields:
            errors.append(f"chapter_contract_check fields must all be true, but these are false: {failing_fields}")
        
        if errors:
            raise ValueError(f"PLANNER_OUTPUT_CONTRACT_INVALID (v2): {'; '.join(errors)}")
    
    return output


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


class StopStateAudit(BaseModel):
    visible_fact_found: bool
    first_satisfied_paragraph_id: str
    paragraphs_after_stop: list[str]
    post_stop_new_action_found: bool
    post_stop_emotional_summary_found: bool
    issue_id: str

    @field_validator("paragraphs_after_stop", mode="before")
    @classmethod
    def normalize_paragraph_ids(cls, value):
        return _paragraph_labels(value)

    @field_validator("paragraphs_after_stop")
    @classmethod
    def require_legal_paragraph_ids(cls, value):
        if any(not _is_paragraph_label(label) for label in value):
            raise ValueError("paragraphs_after_stop must contain legal paragraph IDs")
        return value


class InferenceAudit(BaseModel):
    overexplained: bool
    paragraph_ids: list[str]
    quoted_phrases: list[str]
    issue_id: str

    @field_validator("paragraph_ids", mode="before")
    @classmethod
    def normalize_paragraph_ids(cls, value):
        return _paragraph_labels(value)


class ChoiceEvidence(BaseModel):
    paragraph_id: str
    quote: str
    explanation: str

    @field_validator("paragraph_id", mode="before")
    @classmethod
    def normalize_paragraph_id(cls, value):
        labels = _paragraph_labels(value)
        if len(labels) != 1 or not _is_paragraph_label(labels[0]):
            raise ValueError("paragraph_id must be a legal paragraph ID")
        return labels[0]

    @model_validator(mode="after")
    def require_nonempty_fields(self):
        if not self.paragraph_id.strip() or not self.quote.strip() or not self.explanation.strip():
            raise ValueError("choice evidence fields must be non-empty strings")
        return self


class ChoiceRealizationCheck(BaseModel):
    transition_id: str
    rejected_alternative_visible: bool
    cost_or_commitment_visible: bool
    next_constraint_visible: bool
    paragraph_ids: list[str]
    rejected_alternative_evidence: list[ChoiceEvidence]
    cost_or_commitment_evidence: list[ChoiceEvidence]
    next_constraint_evidence: list[ChoiceEvidence]
    issue_id: str
    comment: str = ""

    @field_validator("paragraph_ids", mode="before")
    @classmethod
    def normalize_paragraph_ids(cls, value):
        return _paragraph_labels(value)


class CriticOutputV2(CriticOutput):
    critic_contract_version: Literal[2]
    stop_state_audit: StopStateAudit
    inference_audit: InferenceAudit
    choice_realization_check: list[ChoiceRealizationCheck]

    @model_validator(mode="before")
    @classmethod
    def normalize_stop_overrun_issue_coverage(cls, data):
        if not isinstance(data, dict):
            return data

        stop = data.get("stop_state_audit")
        issues = data.get("issues")
        if not isinstance(stop, dict) or not isinstance(issues, list):
            return data
        if not (
            stop.get("visible_fact_found") is True
            and bool(stop.get("paragraphs_after_stop"))
            and (
                stop.get("post_stop_new_action_found") is True
                or stop.get("post_stop_emotional_summary_found") is True
            )
            and isinstance(stop.get("issue_id"), str)
            and stop["issue_id"].strip()
        ):
            return data

        audit_paragraphs = _paragraph_labels(stop["paragraphs_after_stop"])
        if any(not _is_paragraph_label(label) for label in audit_paragraphs):
            return data

        issue_id = stop["issue_id"].strip()
        normalized_issues = list(issues)
        for index, issue in enumerate(issues):
            if not isinstance(issue, dict) or issue.get("issue_id") != issue_id:
                continue
            if issue.get("issue_type") != CriticIssueType.stop_state_overrun.value:
                return data

            issue_paragraphs = _paragraph_labels(issue.get("paragraph_ids", []))
            if any(not _is_paragraph_label(label) for label in issue_paragraphs):
                return data
            normalized_issue = dict(issue)
            normalized_issue["paragraph_ids"] = _sorted_unique_paragraph_labels(
                issue_paragraphs + audit_paragraphs
            )
            normalized_issues[index] = normalized_issue
            normalized = dict(data)
            normalized["issues"] = normalized_issues
            return normalized
        return data

    @model_validator(mode="after")
    def check_v2_audit_consistency(self):
        issues_by_id = {issue.issue_id: issue for issue in self.issues}
        issue_paragraphs = {
            paragraph_id
            for issue in self.issues
            for paragraph_id in issue.paragraph_ids
        }
        protected_paragraphs = {
            paragraph_id
            for strength in self.protected_strengths
            for paragraph_id in strength.paragraph_ids
        }
        overlap = issue_paragraphs & protected_paragraphs
        if overlap:
            raise ValueError(
                "CRITIC_OUTPUT_CONTRACT_INVALID: issue paragraph_ids overlap "
                f"protected_strengths: {sorted(overlap)}"
            )

        stop = self.stop_state_audit
        has_stop_overrun = bool(stop.paragraphs_after_stop) and (
            stop.post_stop_new_action_found
            or stop.post_stop_emotional_summary_found
        )
        if has_stop_overrun:
            issue = issues_by_id.get(stop.issue_id)
            if not issue or issue.issue_type != CriticIssueType.stop_state_overrun:
                raise ValueError(
                    "CRITIC_OUTPUT_CONTRACT_INVALID: stop overrun requires "
                    "a stop_state_overrun issue"
                )
            if not set(stop.paragraphs_after_stop).issubset(issue.paragraph_ids):
                raise ValueError(
                    "CRITIC_OUTPUT_CONTRACT_INVALID: stop_state_overrun issue "
                    "must cover paragraphs_after_stop"
                )
        elif stop.issue_id:
            raise ValueError(
                "CRITIC_OUTPUT_CONTRACT_INVALID: stop_state_audit.issue_id "
                "must be empty when no stop overrun is present"
            )

        if self.tempo_profile_check:
            if has_stop_overrun and self.tempo_profile_check.ending_stops_without_summary:
                raise ValueError(
                    "CRITIC_OUTPUT_CONTRACT_INVALID: tempo_profile_check "
                    "contradicts stop_state_audit overrun"
                )
            if (
                not stop.visible_fact_found
                and self.tempo_profile_check.ending_stops_without_summary
            ):
                raise ValueError(
                    "CRITIC_OUTPUT_CONTRACT_INVALID: ending_stops_without_summary "
                    "cannot be true when stop_state.visible_fact was not found"
                )

        inference = self.inference_audit
        if inference.overexplained:
            if not inference.quoted_phrases:
                raise ValueError(
                    "CRITIC_OUTPUT_CONTRACT_INVALID: overexplained inference "
                    "requires quoted_phrases"
                )
            issue = issues_by_id.get(inference.issue_id)
            if not issue or issue.issue_type != CriticIssueType.inference_overexplained:
                raise ValueError(
                    "CRITIC_OUTPUT_CONTRACT_INVALID: overexplained inference "
                    "requires an inference_overexplained issue"
                )
            if not set(inference.paragraph_ids).issubset(issue.paragraph_ids):
                raise ValueError(
                    "CRITIC_OUTPUT_CONTRACT_INVALID: inference issue must cover "
                    "inference_audit paragraph_ids"
                )
        elif inference.issue_id:
            raise ValueError(
                "CRITIC_OUTPUT_CONTRACT_INVALID: inference_audit.issue_id "
                "must be empty when overexplained is false"
            )

        for choice in self.choice_realization_check:
            evidence_by_visibility = (
                (choice.rejected_alternative_visible, choice.rejected_alternative_evidence),
                (choice.cost_or_commitment_visible, choice.cost_or_commitment_evidence),
                (choice.next_constraint_visible, choice.next_constraint_evidence),
            )
            for visible, evidence in evidence_by_visibility:
                if visible and not evidence:
                    raise ValueError(
                        "CRITIC_OUTPUT_CONTRACT_INVALID: visible choice finding "
                        "requires evidence"
                    )
                if not {item.paragraph_id for item in evidence}.issubset(choice.paragraph_ids):
                    raise ValueError(
                        "CRITIC_OUTPUT_CONTRACT_INVALID: choice evidence paragraph_id "
                        "must be included in choice_realization_check paragraph_ids"
                    )

            missing_choice_weight = not all([
                choice.rejected_alternative_visible,
                choice.cost_or_commitment_visible,
                choice.next_constraint_visible,
            ])
            if missing_choice_weight:
                issue = issues_by_id.get(choice.issue_id)
                if not issue or issue.issue_type != CriticIssueType.choice_cost_missing:
                    raise ValueError(
                        "CRITIC_OUTPUT_CONTRACT_INVALID: missing choice weight "
                        "requires a choice_cost_missing issue"
                    )
                if not set(choice.paragraph_ids).issubset(issue.paragraph_ids):
                    raise ValueError(
                        "CRITIC_OUTPUT_CONTRACT_INVALID: choice_cost_missing issue "
                        "must cover choice_realization_check paragraph_ids"
                    )
            elif choice.issue_id:
                raise ValueError(
                    "CRITIC_OUTPUT_CONTRACT_INVALID: choice_realization_check.issue_id "
                    "must be empty when choice weight is visible"
                )
        return self


def validate_critic_output(
    data: dict, expected_version: int | None = None
) -> CriticOutput | CriticOutputV2:
    try:
        if expected_version == 2:
            return CriticOutputV2(**data)
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

    @field_validator("original_status", "revision_status", mode="before")
    @classmethod
    def normalize_partial_status(cls, value):
        if isinstance(value, str):
            v = value.strip().lower().replace("-", "_")
            if v in ("partial_pass", "partial"):
                return "pass"
            if v in ("partial_fail",):
                return "fail"
        return value


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

def validate_stage_output(stage: str, data: dict, expected_version: int | None = None) -> dict:
    """Validate stage output and return normalized data.
    Raises ValueError with stage-specific error code on failure.
    """
    if stage == "planner":
        return validate_planner_output(data, expected_version=expected_version).model_dump()
    elif stage == "critic":
        return validate_critic_output(data, expected_version=expected_version).model_dump()
    elif stage == "reviser":
        return validate_reviser_output(data).model_dump()
    elif stage == "judge":
        return validate_judge_output(data).model_dump()
    else:
        return data
