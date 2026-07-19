"""Deterministic, writer-facing projection of a Planner output.

The full Planner output remains the audit source for Critic and Judge.  The
Writer receives only the canonical ``WriterBrief`` below, never Planner's
reader-inference answers or narrator-withholding instructions.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_ACTIVE_PROJECT_FACTS = 5


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


class WriterBrief(BaseModel):
    """The complete public contract for deterministic Writer input."""

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

    @model_validator(mode="after")
    def validate_assumption(self):
        if self.current_assumption and not self.assumption_basis:
            raise ValueError("assumption_basis is required when current_assumption is non-empty")
        if not self.current_assumption and self.assumption_basis:
            raise ValueError("assumption_basis must be empty when current_assumption is empty")
        legal_basis = set(self.known_facts)
        legal_basis.add(self.opening_fact)
        if any(item not in legal_basis for item in self.assumption_basis):
            raise ValueError("assumption_basis must come from known_facts or opening_fact")
        return self


def validate_writer_brief(data: dict[str, Any]) -> WriterBrief:
    """Validate the shared compiler/preflight contract without duplicate rules."""
    return WriterBrief.model_validate(data)


def _viewpoint_character(plan: dict[str, Any]) -> dict[str, Any]:
    characters = plan.get("characters")
    if not isinstance(characters, list):
        return {}
    return next((item for item in characters if isinstance(item, dict)), {})


def compile_writer_brief(scene_plan: dict[str, Any] | None) -> dict[str, Any]:
    """Return the canonical short WriterBrief from one Planner output.

    Planner v2 stores the current actor's known/unknown facts and observed
    evidence in its first character record.  The compiler keeps those source
    facts distinct from the global ``must_remain_unclassified`` guardrail and
    never derives an assumption where Planner supplied none.
    """
    plan = scene_plan if isinstance(scene_plan, dict) else {}
    state = plan.get("scene_state") if isinstance(plan.get("scene_state"), dict) else {}
    guardrails = plan.get("tempo_guardrails") if isinstance(plan.get("tempo_guardrails"), dict) else {}
    stop_state = guardrails.get("stop_state") if isinstance(guardrails.get("stop_state"), dict) else {}
    character = _viewpoint_character(plan)
    transitions = plan.get("causal_transitions") if isinstance(plan.get("causal_transitions"), list) else []
    transition = next((item for item in transitions if isinstance(item, dict)), {})

    opening_fact = _text(guardrails.get("entry_pressure")) or _text(transition.get("visible_trigger"))
    known_facts = _strings([
        *_strings(state.get("visible_facts")),
        *_strings(character.get("known")),
        *_strings(character.get("observed_evidence")),
    ])
    assumption = _text(character.get("situational_assumption")) or _text(
        character.get("current_interpretation")
    ) or _text(plan.get("current_interpretation"))
    basis = []
    if assumption:
        basis = _strings(character.get("observed_evidence")) or known_facts[:1] or [opening_fact]

    brief = WriterBrief(
        opening_mode="entry_pressure",
        opening_fact=opening_fact,
        viewpoint_character=_text(character.get("name")),
        known_facts=known_facts,
        unknown_facts=_strings(character.get("unknown")),
        current_assumption=assumption,
        assumption_basis=basis,
        next_action=_text(transition.get("character_next_action")),
        immediate_consequence=_text(transition.get("immediate_consequence")),
        next_constraint=_text(transition.get("next_constraint")),
        active_project_facts=_strings(plan.get("active_project_facts"))[:MAX_ACTIVE_PROJECT_FACTS],
        remain_unclassified=_strings(guardrails.get("must_remain_unclassified")),
        stop_fact=_text(stop_state.get("visible_fact")),
        must_not_append=_text(stop_state.get("must_not_append")),
        final_line_must_include=_text(guardrails.get("final_line_must_include")),
    )
    return brief.model_dump()
