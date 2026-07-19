"""Narrative route decision and compiled-input schemas.

Route classification is deterministic — route_name is a classifier output,
never a client-supplied value.  The only client-facing overrides are
writer_input_mode="narrative_route" and route_policy_version="narrative-route-v1".
"""
from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.writer_brief import MAX_ACTIVE_PROJECT_FACTS


# ── Enums ──────────────────────────────────────────────────────────


class NarrativeRoute(StrEnum):
    C_OBJECT_CAUSAL = "C_OBJECT_CAUSAL"
    A_LITE_INFORMATION_GAP = "A_LITE_INFORMATION_GAP"
    B_SHORT_RELATION = "B_SHORT_RELATION"
    B_PHYSICAL_PROBLEM = "B_PHYSICAL_PROBLEM"
    D_FALLIBLE_TASK = "D_FALLIBLE_TASK"
    B_DEFAULT = "B_DEFAULT"


ROUTE_POLICY_VERSION = "narrative-route-v1"

# Priority order: first match wins.
ROUTE_RULES: list[tuple[str, NarrativeRoute]] = [
    ("RULE_C_OBJECT_CAUSAL", NarrativeRoute.C_OBJECT_CAUSAL),
    ("RULE_A_LITE_INFORMATION_GAP", NarrativeRoute.A_LITE_INFORMATION_GAP),
    ("RULE_B_SHORT_RELATION", NarrativeRoute.B_SHORT_RELATION),
    ("RULE_B_PHYSICAL_PROBLEM", NarrativeRoute.B_PHYSICAL_PROBLEM),
    ("RULE_D_FALLIBLE_TASK", NarrativeRoute.D_FALLIBLE_TASK),
    ("RULE_B_DEFAULT", NarrativeRoute.B_DEFAULT),
]


# ── Decision ────────────────────────────────────────────────────────


class NarrativeRouteDecision(BaseModel):
    """Classified route with audit trail.  Immutable once constructed."""

    model_config = ConfigDict(frozen=True)

    route_name: NarrativeRoute
    classifier_version: str = Field(default=ROUTE_POLICY_VERSION)
    decision_reasons: list[str] = Field(default_factory=list, min_length=1)
    matched_rules: list[str] = Field(default_factory=list, min_length=1)
    rejected_routes: list[NarrativeRoute] = Field(default_factory=list)

    @model_validator(mode="after")
    def _route_not_in_rejected(self):
        if self.route_name in self.rejected_routes:
            raise ValueError(
                f"route_name {self.route_name.value} cannot appear in rejected_routes"
            )
        return self


# ── Compiled input ──────────────────────────────────────────────────


class CompiledNarrativeInput(BaseModel):
    """The full compiled narrative route payload for the Writer stage.

    compiled_brief is the route-specific Pydantic model. instruction_block
    is the human-readable instruction appended to the Writer prompt.
    """

    model_config = ConfigDict(extra="forbid")

    decision: NarrativeRouteDecision
    compiled_brief: dict[str, Any]
    compiled_brief_hash: str = Field(min_length=64, max_length=64)
    instruction_block: str = Field(min_length=1)
    instruction_hash: str = Field(min_length=64, max_length=64)
    planner_candidate_id: str | None = None

    @staticmethod
    def hash_dict(data: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── Route-specific brief schemas ────────────────────────────────────


def _validate_assumption_facts(self: BaseModel) -> BaseModel:
    """Shared assumption validator: basis must come from known_facts or opening_fact."""
    if self.current_assumption and not self.assumption_basis:
        raise ValueError("assumption_basis is required when current_assumption is non-empty")
    if not self.current_assumption and self.assumption_basis:
        raise ValueError("assumption_basis must be empty when current_assumption is empty")
    legal_basis = set(self.known_facts) | {self.opening_fact}
    if any(item not in legal_basis for item in self.assumption_basis):
        raise ValueError("assumption_basis must come from known_facts or opening_fact")
    return self


class WriterBriefCObjectCausal(BaseModel):
    """C route: object-misrecognition / pursuit.  Extends B with four causal fields
    using counterfactual_without_action (NOT counteraction_or_disproof)."""

    model_config = ConfigDict(extra="forbid")

    opening_mode: str
    opening_fact: str = Field(min_length=1)
    viewpoint_character: str = ""
    known_facts: list[str] = Field(default_factory=list)
    unknown_facts: list[str] = Field(default_factory=list)
    current_assumption: str = ""
    assumption_basis: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1)
    immediate_consequence: str = Field(min_length=1)
    next_constraint: str = Field(min_length=1)
    active_project_facts: list[str] = Field(default_factory=list, max_length=MAX_ACTIVE_PROJECT_FACTS)
    remain_unclassified: list[str] = Field(default_factory=list)
    stop_fact: str = Field(min_length=1)
    must_not_append: str = ""
    final_line_must_include: str = ""

    available_causal_objects: list[str] = Field(default_factory=list, max_length=3)
    rejected_alternative: str = ""
    cost_or_commitment: str = ""
    counterfactual_without_action: str = ""

    @model_validator(mode="after")
    def validate_assumption(self):
        return _validate_assumption_facts(self)


class WriterBriefALite(BaseModel):
    """A-lite route: partial-message / multi-character misreading.
    Does NOT expose Planner's final answer — only secondary-actor viewpoint."""

    model_config = ConfigDict(extra="forbid")

    opening_mode: str
    opening_fact: str = Field(min_length=1)
    viewpoint_character: str = ""
    known_facts: list[str] = Field(default_factory=list)
    unknown_facts: list[str] = Field(default_factory=list)
    current_assumption: str = ""
    assumption_basis: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1)
    immediate_consequence: str = Field(min_length=1)
    next_constraint: str = Field(min_length=1)
    active_project_facts: list[str] = Field(default_factory=list, max_length=MAX_ACTIVE_PROJECT_FACTS)
    remain_unclassified: list[str] = Field(default_factory=list)
    stop_fact: str = Field(min_length=1)
    must_not_append: str = ""
    final_line_must_include: str = ""

    secondary_actor_goal: str = ""
    secondary_actor_observed_evidence: list[str] = Field(default_factory=list, max_length=5)
    competing_interpretation: list[str] = Field(default_factory=list, max_length=3)
    likely_countermove: str = ""
    reader_uncertainty_to_preserve: str = ""

    @model_validator(mode="after")
    def validate_assumption(self):
        return _validate_assumption_facts(self)

    @model_validator(mode="after")
    def _competing_interpretation_min_count(self):
        if self.competing_interpretation and len(self.competing_interpretation) < 2:
            raise ValueError("competing_interpretation must have at least 2 entries when non-empty")
        return self


class WriterBriefBShort(BaseModel):
    """B-short route: low-conflict romance, 350-550 chars, no second-confirmation tail."""

    model_config = ConfigDict(extra="forbid")

    opening_mode: str
    opening_fact: str = Field(min_length=1)
    viewpoint_character: str = ""
    known_facts: list[str] = Field(default_factory=list)
    unknown_facts: list[str] = Field(default_factory=list)
    current_assumption: str = ""
    assumption_basis: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1)
    immediate_consequence: str = Field(min_length=1)
    next_constraint: str = Field(min_length=1)
    active_project_facts: list[str] = Field(default_factory=list, max_length=MAX_ACTIVE_PROJECT_FACTS)
    remain_unclassified: list[str] = Field(default_factory=list)
    stop_fact: str = Field(min_length=1)
    must_not_append: str = ""
    final_line_must_include: str = ""

    target_length_chars: int = Field(default=450, ge=350, le=550)

    @model_validator(mode="after")
    def validate_assumption(self):
        return _validate_assumption_facts(self)


class WriterBriefBPhysical(BaseModel):
    """B-physical route: equipment/object/space failure, must show failed first attempt."""

    model_config = ConfigDict(extra="forbid")

    opening_mode: str
    opening_fact: str = Field(min_length=1)
    viewpoint_character: str = ""
    known_facts: list[str] = Field(default_factory=list)
    unknown_facts: list[str] = Field(default_factory=list)
    current_assumption: str = ""
    assumption_basis: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1)
    immediate_consequence: str = Field(min_length=1)
    next_constraint: str = Field(min_length=1)
    active_project_facts: list[str] = Field(default_factory=list, max_length=MAX_ACTIVE_PROJECT_FACTS)
    remain_unclassified: list[str] = Field(default_factory=list)
    stop_fact: str = Field(min_length=1)
    must_not_append: str = ""
    final_line_must_include: str = ""

    concrete_problem: str = Field(min_length=1)
    first_attempt: str = Field(min_length=1)
    why_first_attempt_fails: str = Field(min_length=1)
    second_action: str = Field(min_length=1)
    accumulated_cost: str = Field(min_length=1)
    visible_unresolved_state: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assumption(self):
        return _validate_assumption_facts(self)


class WriterBriefDFallible(BaseModel):
    """D route: investigation/infiltration/task — must include local misjudgment
    and ethical compromise.  Suppresses generic suspense clichés."""

    model_config = ConfigDict(extra="forbid")

    opening_mode: str
    opening_fact: str = Field(min_length=1)
    viewpoint_character: str = ""
    known_facts: list[str] = Field(default_factory=list)
    unknown_facts: list[str] = Field(default_factory=list)
    current_assumption: str = ""
    assumption_basis: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1)
    immediate_consequence: str = Field(min_length=1)
    next_constraint: str = Field(min_length=1)
    active_project_facts: list[str] = Field(default_factory=list, max_length=MAX_ACTIVE_PROJECT_FACTS)
    remain_unclassified: list[str] = Field(default_factory=list)
    stop_fact: str = Field(min_length=1)
    must_not_append: str = ""
    final_line_must_include: str = ""

    one_local_misjudgment: str = Field(min_length=1)
    one_social_or_ethical_compromise: str = Field(min_length=1)
    immediate_visible_consequence: str = Field(min_length=1)
    next_constraint_field: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assumption(self):
        return _validate_assumption_facts(self)
