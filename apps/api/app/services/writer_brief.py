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


class WriterBriefC(BaseModel):
    """Narrative-behaviour-enhanced brief — same skeleton as WriterBrief plus
    four fields that carry causal weight without leaking Planner answers."""

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

    available_causal_objects: list[str] = Field(default_factory=list)
    rejected_alternative: str = ""
    cost_or_commitment: str = ""
    counteraction_or_disproof: str = ""

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


def compile_writer_brief_c(scene_plan: dict[str, Any] | None) -> dict[str, Any]:
    """Same projection as compile_writer_brief but adds four narrative-behaviour
    fields: causal objects, rejected alternative, cost, and counteraction."""
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

    return WriterBriefC(
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
        available_causal_objects=_strings(state.get("available_objects")),
        rejected_alternative=_text(transition.get("rejected_alternative")),
        cost_or_commitment=_text(transition.get("cost_or_commitment")),
        counteraction_or_disproof=_text(transition.get("counterfactual_without_action")),
    ).model_dump()


def validate_writer_brief(data: dict[str, Any]) -> WriterBrief:
    """Validate the shared compiler/preflight contract without duplicate rules."""
    return WriterBrief.model_validate(data)


def compile_writer_input(scene_plan: dict[str, Any] | None, mode: str) -> dict[str, Any]:
    """Return the sole Writer-visible planning payload for an experiment arm."""
    plan = scene_plan if isinstance(scene_plan, dict) else {}
    if mode == "complete_planner":
        return plan
    if mode == "writer_brief":
        return compile_writer_brief(plan)
    if mode == "writer_brief_v3":
        return compile_writer_brief_v3(plan)
    if mode == "narrative_behaviour_brief":
        return compile_writer_brief_c(plan)
    raise ValueError(f"unsupported writer input mode: {mode}")


def _detect_planner_v3(plan: dict[str, Any]) -> bool:
    """Return True when the plan carries planner_contract_version=3."""
    return plan.get("planner_contract_version") == 3


def compile_writer_brief_v3(scene_plan: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic WriterBrief for Planner v3.

    Identical base brief as v2, plus four v3 text blocks:
    POV_LOCK, BACKSTAGE_BEHAVIOR_ONLY, SCENE_CAPACITY, INTERACTION_PLAN.
    """
    base = compile_writer_brief(scene_plan)
    plan = scene_plan if isinstance(scene_plan, dict) else {}

    pov = plan.get("pov_contract")
    sc = plan.get("scene_capacity")
    ip = plan.get("interaction_plan")

    blocks: list[str] = []

    # ── POV_LOCK ──
    if isinstance(pov, dict):
        lines = ["=== POV_LOCK ===", ""]
        lines.append(f"POV_CHARACTER:")
        lines.append(f"{_text(pov.get('pov_character'))}")
        lines.append("")
        lines.append("NARRATION_MODE:")
        lines.append("third_person_limited")
        lines.append("")

        directly = _strings(pov.get("directly_narratable"))
        if directly:
            lines.append("DIRECTLY_NARRATABLE:")
            for item in directly:
                lines.append(f"- {item}")
            lines.append("")

        pov_known = _strings(pov.get("pov_known_facts"))
        if pov_known:
            lines.append("POV_KNOWN:")
            for item in pov_known:
                lines.append(f"- {item}")
            lines.append("")

        pov_unknown = _strings(pov.get("pov_unknown_facts"))
        if pov_unknown:
            lines.append("POV_UNKNOWN:")
            for item in pov_unknown:
                lines.append(f"- {item}")
            lines.append("")

        lines.append("ALLOWED_VIEWPOINT_MISREAD:")
        lines.append(f"{_text(pov.get('allowed_viewpoint_misread'))}")
        lines.append("")
        lines.append("VIEWPOINT_SWITCH_FORBIDDEN:")
        lines.append("true")
        lines.append("")

        future_forbidden = _strings(pov.get("future_knowledge_forbidden"))
        if future_forbidden:
            lines.append("FUTURE_KNOWLEDGE_FORBIDDEN:")
            for item in future_forbidden:
                lines.append(f"- {item}")
            lines.append("")

        rel_forbidden = _strings(pov.get("relationship_summary_forbidden"))
        if rel_forbidden:
            lines.append("RELATIONSHIP_SUMMARY_FORBIDDEN:")
            for item in rel_forbidden:
                lines.append(f"- {item}")
            lines.append("")

        blocks.append("\n".join(lines))

    # ── BACKSTAGE_BEHAVIOR_ONLY ──
    other_minds = pov.get("other_minds_backstage_only", []) if isinstance(pov, dict) else []
    if other_minds:
        for om in other_minds:
            if not isinstance(om, dict):
                continue
            lines = [
                "=== BACKSTAGE_BEHAVIOR_ONLY ===",
                "",
                "后台行为信息只用于控制角色选择。",
                "不得由旁白直接陈述。",
                "不得作为POV已知事实。",
                "",
                f"CHARACTER:",
                f"{_text(om.get('character'))}",
                "",
                f"HIDDEN_GOAL_OR_MOTIVE:",
                f"{_text(om.get('hidden_goal_or_motive'))}",
                "",
                f"HIDDEN_OR_WITHHELD_FACT:",
                f"{_text(om.get('hidden_or_withheld_fact'))}",
                "",
                "BEHAVIORAL_EXPRESSION:",
            ]
            for expr in _strings(om.get("behavioral_expression")):
                lines.append(f"- {expr}")
            lines.append("")
            lines.append("NARRATOR_MUST_NOT_STATE:")
            for ns in _strings(om.get("narrator_must_not_state")):
                lines.append(f"- {ns}")
            lines.append("")
            blocks.append("\n".join(lines))

    # ── SCENE_CAPACITY ──
    if isinstance(sc, dict):
        lines = ["=== SCENE_CAPACITY ===", ""]
        lines.append("TARGET_MIN_CHARS:")
        lines.append(f"{sc.get('target_min_chars', '')}")
        lines.append("")
        lines.append("SCENE_MODE:")
        lines.append(f"{_text(sc.get('scene_mode'))}")
        lines.append("")
        lines.append("CORE_EVENT:")
        lines.append(f"{_text(sc.get('core_event'))}")
        lines.append("")
        lines.append("CAPACITY_SUFFICIENT:")
        lines.append(f"{'true' if sc.get('capacity_sufficient') else 'false'}")
        lines.append("")
        lines.append("ESTIMATED_CAPACITY:")
        lines.append(f"{sc.get('estimated_narrative_capacity_min', '')}-{sc.get('estimated_narrative_capacity_max', '')}")
        lines.append("")
        lines.append("MEANINGFUL_BEATS:")
        for beat in sc.get("meaningful_beats", []) or []:
            if not isinstance(beat, dict):
                continue
            bid = beat.get("id", "?")
            lines.append(f"{bid}:")
            lines.append(f"- trigger: {_text(beat.get('trigger'))}")
            lines.append(f"- active_character: {_text(beat.get('active_character'))}")
            lines.append(f"- goal: {_text(beat.get('goal'))}")
            lines.append(f"- resistance_or_information_gap: {_text(beat.get('resistance_or_information_gap'))}")
            lines.append(f"- action_or_exchange: {_text(beat.get('action_or_exchange'))}")
            lines.append(f"- new_information: {_text(beat.get('new_information'))}")
            lines.append(f"- immediate_consequence: {_text(beat.get('immediate_consequence'))}")
            sd = beat.get("state_delta")
            if isinstance(sd, dict):
                lines.append(f"- state_delta: {_text(sd.get('before'))} → {_text(sd.get('after'))}")
            lines.append(f"- cannot_merge_reason: {_text(beat.get('cannot_merge_reason'))}")
            lines.append("")

        forbidden_padding = _strings(sc.get("forbidden_padding"))
        if forbidden_padding:
            lines.append("FORBIDDEN_PADDING:")
            for item in forbidden_padding:
                lines.append(f"- {item}")
            lines.append("")

        blocks.append("\n".join(lines))

    # ── INTERACTION_PLAN ──
    if isinstance(ip, dict) and ip:
        lines = ["=== INTERACTION_PLAN ===", ""]
        lines.append("INTERACTION_REQUIRED:")
        lines.append(f"{'true' if ip.get('interaction_required') else 'false'}")
        lines.append("")

        participants = _strings(ip.get("participants"))
        if participants:
            lines.append("PARTICIPANTS:")
            for p in participants:
                lines.append(f"- {p}")
            lines.append("")

        char_positions = ip.get("character_positions", []) or []
        if char_positions:
            lines.append("CHARACTER_POSITIONS:")
            for cp in char_positions:
                if not isinstance(cp, dict):
                    continue
                lines.append(f"  {_text(cp.get('character'))}:")
                lines.append(f"    - current_goal: {_text(cp.get('current_goal'))}")
                lines.append(f"    - opening_assumption: {_text(cp.get('opening_assumption'))}")
                lines.append(f"    - hidden_or_withheld: {_text(cp.get('hidden_or_withheld_information'))}")
                lines.append(f"    - cannot_accept: {_text(cp.get('cannot_accept'))}")
                lines.append(f"    - wants_from_other: {_text(cp.get('wants_from_other'))}")
            lines.append("")

        exchanges = ip.get("turning_exchanges", []) or []
        if exchanges:
            lines.append("TURNING_EXCHANGES:")
            for ex in exchanges:
                if not isinstance(ex, dict):
                    continue
                eid = ex.get("id", "?")
                lines.append(f"{eid}:")
                lines.append(f"- trigger: {_text(ex.get('trigger'))}")
                lines.append(f"- initiator: {_text(ex.get('initiator'))}")
                lines.append(f"- initiator_goal: {_text(ex.get('initiator_goal'))}")
                lines.append(f"- speech_act: {_text(ex.get('speech_act'))}")
                lines.append(f"- other_response_mode: {_text(ex.get('other_response_mode'))}")
                lines.append(f"- new_information: {_text(ex.get('new_information'))}")
                sd = ex.get("state_delta")
                if isinstance(sd, dict):
                    lines.append(f"- state_delta: {_text(sd.get('before'))} → {_text(sd.get('after'))}")
            lines.append("")

        blocks.append("\n".join(lines))

    v3_text = "\n\n".join(blocks) if blocks else ""
    return {**base, "v3_blocks": v3_text, "mode": "writer_brief_v3"}


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
