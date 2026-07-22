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


def compile_writer_input(
    scene_plan: dict[str, Any] | None,
    mode: str,
    *,
    focus_character: str | None = None,
) -> dict[str, Any]:
    """Return the sole Writer-visible planning payload for an experiment arm.

    Args:
        scene_plan: The raw planner output dict.
        mode: One of ``complete_planner``, ``writer_brief``, ``writer_brief_v3``,
            ``chapter_architect``, ``narrative_behaviour_brief``, or
            ``narrative_projection``.
        focus_character: Required for ``narrative_projection`` mode.  Ignored for
            all other modes.  Must be an exact match to a ``name`` in
            ``scene_plan["characters"]``.
    """
    plan = scene_plan if isinstance(scene_plan, dict) else {}
    if mode == "complete_planner":
        # focus_character is accepted but deliberately ignored for complete_planner
        return plan
    if mode == "writer_brief":
        return compile_writer_brief(plan)
    if mode == "writer_brief_v3":
        return compile_writer_brief_v3(plan)
    if mode == "chapter_architect":
        return compile_chapter_architect_brief(plan)
    if mode == "narrative_behaviour_brief":
        return compile_writer_brief_c(plan)
    if mode == "narrative_projection":
        return compile_narrative_projection_brief(plan, focus_character=focus_character)
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


def _detect_chapter_architect(plan: dict[str, Any]) -> bool:
    """Return True when the plan carries architect_contract_version."""
    return "architect_contract_version" in plan


def compile_chapter_architect_brief(scene_plan: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic WriterBrief from Chapter Architect output.

    Formats the nine architect blocks into Writer-readable text:
    chapter story, narrative actions, character info, narration boundary,
    ending design, and capacity check.  No LLM — pure string formatting.
    """
    plan = scene_plan if isinstance(scene_plan, dict) else {}

    cs = plan.get("content_summary", {}) or {}
    pl = plan.get("plot_lines", {}) or {}
    chars = plan.get("characters", []) or []
    nb = plan.get("narration_boundary", {}) or {}
    na = plan.get("narrative_actions", []) or []
    ed = plan.get("ending_design", {}) or {}
    cap = plan.get("capacity_check", {}) or {}
    cp = plan.get("chapter_position", {}) or {}

    blocks: list[str] = []

    # ── Chapter Story ──
    lines = ["=== CHAPTER_STORY ===", ""]
    lines.append(f"CHAPTER_TYPE: {_text(cp.get('type'))}")
    lines.append(f"READER_PAYOFF: {_text(cp.get('reader_payoff'))}")
    lines.append("")
    lines.append(f"CORE_EVENT: {_text(plan.get('core_event'))}")
    lines.append("")
    lines.append("CONTENT_SUMMARY:")
    lines.append(f"  cause: {_text(cs.get('cause'))}")
    lines.append(f"  development: {_text(cs.get('development'))}")
    lines.append(f"  turning_point: {_text(cs.get('turning_point'))}")
    lines.append(f"  climax: {_text(cs.get('climax'))}")
    lines.append(f"  ending: {_text(cs.get('ending'))}")
    lines.append("")
    lines.append("PLOT_LINES:")
    lines.append(f"  main: {_text(pl.get('main_line'))}")
    lines.append(f"  emotion: {_text(pl.get('emotion_line'))}")
    if pl.get("logic_line"):
        lines.append(f"  logic: {_text(pl.get('logic_line'))}")
    if pl.get("comedy_line"):
        lines.append(f"  comedy: {_text(pl.get('comedy_line'))}")
    blocks.append("\n".join(lines))

    # ── Narrative Actions ──
    if na:
        lines = ["=== NARRATIVE_ACTIONS ===", ""]
        for i, action in enumerate(na):
            if not isinstance(action, dict):
                continue
            lines.append(f"A{i+1}:")
            lines.append(f"  goal: {_text(action.get('goal'))}")
            lines.append(f"  obstacle: {_text(action.get('obstacle'))}")
            lines.append(f"  action: {_text(action.get('action_or_interaction'))}")
            lines.append(f"  state_change: {_text(action.get('state_change'))}")
            lines.append("")
        blocks.append("\n".join(lines))

    # ── Characters ──
    if chars:
        lines = ["=== CHARACTERS ===", ""]
        for c in chars:
            if not isinstance(c, dict):
                continue
            lines.append(f"{_text(c.get('name'))}:")
            lines.append(f"  goal: {_text(c.get('goal'))}")
            known = _strings(c.get("known"))
            if known:
                lines.append(f"  known: {'; '.join(known)}")
            unknown = _strings(c.get("unknown"))
            if unknown:
                lines.append(f"  unknown: {'; '.join(unknown)}")
            withheld = _strings(c.get("withheld"))
            if withheld:
                lines.append(f"  withheld: {'; '.join(withheld)}")
            if c.get("cannot_accept"):
                lines.append(f"  cannot_accept: {_text(c.get('cannot_accept'))}")
            # P2 transplant: observation → assumption → action chain
            oe = _strings(c.get("observed_evidence"))
            ca = _text(c.get("current_assumption"))
            da = _text(c.get("drives_action"))
            if oe or ca or da:
                if oe:
                    lines.append(f"  observed: {'; '.join(oe)}")
                if ca:
                    lines.append(f"  assumes: {ca}")
                if da:
                    lines.append(f"  therefore: {da}")
            lines.append("")
        blocks.append("\n".join(lines))

    # ── Narration Boundary ──
    lines = ["=== NARRATION_BOUNDARY ===", ""]
    reader_infer = _strings(nb.get("reader_must_infer"))
    if reader_infer:
        lines.append("READER_MUST_INFER:")
        for item in reader_infer:
            lines.append(f"  - {item}")
        lines.append("")
    narrator_not = _strings(nb.get("narrator_must_not_state"))
    if narrator_not:
        lines.append("NARRATOR_MUST_NOT_STATE:")
        for item in narrator_not:
            lines.append(f"  - {item}")
        lines.append("")
    vn = _text(nb.get("viewpoint_note"))
    if vn:
        lines.append(f"VIEWPOINT: {vn}")
    lines.append("")
    lines.append("前台只写POV人物能感知的内容。后台信息只用于控制角色行为，不得由旁白直接说出。")
    blocks.append("\n".join(lines))

    # ── Ending Design ──
    lines = ["=== ENDING_DESIGN ===", ""]
    lines.append(f"STOP_WHEN: {_text(ed.get('visible_closing_state'))}")
    lines.append(f"HOOK_TYPE: {_text(ed.get('hook_type'))}")
    if ed.get("hook_detail"):
        lines.append(f"HOOK: {_text(ed.get('hook_detail'))}")
    must_not = _strings(ed.get("must_not_append"))
    if must_not:
        lines.append("MUST_NOT_APPEND:")
        for item in must_not:
            lines.append(f"  - {item}")
    blocks.append("\n".join(lines))

    # ── Capacity ──
    lines = ["=== CAPACITY ===", ""]
    lines.append(f"SUFFICIENT: {'true' if cap.get('capacity_sufficient') else 'false'}")
    if cap.get("capacity_reason"):
        lines.append(f"REASON: {_text(cap.get('capacity_reason'))}")
    fp = _strings(cap.get("forbidden_padding"))
    if fp:
        lines.append("FORBIDDEN_PADDING:")
        for item in fp:
            lines.append(f"  - {item}")
    if not cap.get("capacity_sufficient"):
        lines.append("")
        lines.append("容量不足：只写完真实事件。宁可短于目标，不写水文。")
    blocks.append("\n".join(lines))

    architect_text = "\n\n".join(blocks)
    return {"mode": "chapter_architect", "architect_brief": architect_text}


# ── Narrative Projection Compiler v1 ───────────────────────────────────

_NP_FORBIDDEN_FIELDS: set[str] = {
    "chapter_position",
    "reader_payoff",
    "hook_requirement",
    "content_summary",
    "plot_lines",
    "reader_must_infer",
    "hook_detail",
    "hook_strength",
    "capacity_check",
    "capacity_reason",
    "forbidden_padding",
    "architect_contract_version",
}

_NP_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "模糊回答",
    "转移话题",
    "眼神回避",
    "异常停顿",
    "响应速度异常",
)


def _np_find_character(
    characters: list[dict[str, Any]],
    focus_name: str,
) -> dict[str, Any]:
    """Find a character by exact name match."""
    for c in characters:
        if isinstance(c, dict) and _text(c.get("name")) == focus_name:
            return c
    raise ValueError("NARRATIVE_PROJECTION_FOCUS_NOT_FOUND")


def compile_narrative_projection_brief(
    scene_plan: dict[str, Any] | None,
    *,
    focus_character: str | None = None,
) -> dict[str, Any]:
    """Deterministic Narrative Projection compiler for Chapter Architect v1 output.

    Re-organises A1 fields into five blocks: NARRATION_ACCESS,
    FOREGROUND_KNOWLEDGE, BACKSTAGE_BEHAVIOR_ONLY,
    PLANNED_STATE_DELTAS, and STOP_STATE.

    Raises ValueError with a ``NARRATIVE_PROJECTION_*`` error code on
    invalid input.  Never calls an LLM, never invents facts.
    """
    plan = scene_plan if isinstance(scene_plan, dict) else {}

    # ── Input validation ──
    if not plan:
        raise ValueError("NARRATIVE_PROJECTION_PLAN_MISSING")

    characters: list[dict[str, Any]] = plan.get("characters", []) or []
    if not isinstance(characters, list):
        characters = []
    if not characters:
        raise ValueError("NARRATIVE_PROJECTION_CHARACTERS_MISSING")

    if not focus_character or not focus_character.strip():
        raise ValueError("NARRATIVE_PROJECTION_FOCUS_MISSING")

    focus_char = _np_find_character(characters, focus_character.strip())

    narrative_actions: list[dict[str, Any]] = (
        plan.get("narrative_actions", []) or []
    )
    if not isinstance(narrative_actions, list) or not narrative_actions:
        raise ValueError("NARRATIVE_PROJECTION_ACTIONS_MISSING")

    ending_design: dict[str, Any] = plan.get("ending_design", {}) or {}
    visible_closing = _text(ending_design.get("visible_closing_state"))
    if not visible_closing:
        raise ValueError("NARRATIVE_PROJECTION_STOP_STATE_MISSING")

    nb: dict[str, Any] = plan.get("narration_boundary", {}) or {}

    # ── Build blocks ──
    blocks: list[str] = []

    # ── 1. NARRATION_ACCESS ──
    lines = ["=== NARRATION_ACCESS ===", ""]
    lines.append("CURRENT_FOCUS:")
    lines.append(f"{focus_character}")
    lines.append("")

    lines.append("DIRECT_INTERNAL_ACCESS:")
    lines.append(f"- {focus_character}当前明确意识到的感受、判断与猜测")
    lines.append(f"- {focus_character}基于已有证据形成的暂时判断或误判")
    lines.append("")

    lines.append("OBSERVABLE_ONLY:")
    for c in characters:
        if not isinstance(c, dict):
            continue
        name = _text(c.get("name"))
        if name and name != focus_character:
            lines.append(f"- {name}")
    lines.append("")

    lines.append("FORBIDDEN_DIRECT_ACCESS:")
    lines.append("- 其他人物未说出口的心理与真实动机")
    lines.append("- 多人共同感受")
    lines.append("- 关系意义总结")
    narrator_not = _strings(nb.get("narrator_must_not_state"))
    for item in narrator_not:
        lines.append(f"- {item}")
    blocks.append("\n".join(lines))

    # ── 2. FOREGROUND_KNOWLEDGE ──
    lines = ["=== FOREGROUND_KNOWLEDGE ===", ""]

    known = _strings(focus_char.get("known"))
    lines.append("KNOWN:")
    if known:
        for item in known:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")

    assumption = _text(focus_char.get("current_assumption"))
    lines.append("SUSPECTED_OR_MISTAKEN:")
    if assumption:
        lines.append(f"- {assumption}")
    else:
        lines.append("- (none)")
    lines.append("")

    unknown = _strings(focus_char.get("unknown"))
    lines.append("UNKNOWN:")
    if unknown:
        for item in unknown:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")

    evidence = _strings(focus_char.get("observed_evidence"))
    lines.append("EVIDENCE:")
    if evidence:
        for item in evidence:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    blocks.append("\n".join(lines))

    # ── 3. BACKSTAGE_BEHAVIOR_ONLY ──
    other_chars = [
        c for c in characters
        if isinstance(c, dict) and _text(c.get("name")) != focus_character
    ]
    if other_chars:
        for oc in other_chars:
            name = _text(oc.get("name"))
            goal = _text(oc.get("goal"))
            withheld = _strings(oc.get("withheld"))
            cannot_accept = _text(oc.get("cannot_accept"))
            current_assumption = _text(oc.get("current_assumption"))
            drives_action = _text(oc.get("drives_action"))

            lines = ["=== BACKSTAGE_BEHAVIOR_ONLY ===", ""]
            lines.append("CHARACTER:")
            lines.append(f"{name}")
            lines.append("")

            lines.append("BEHAVIOR_OBJECTIVE:")
            lines.append(f"{goal}" if goal else "(none)")
            lines.append("")

            lines.append("DO_NOT_VOLUNTARILY_DISCLOSE:")
            if withheld:
                for item in withheld:
                    lines.append(f"- {item}")
            else:
                lines.append("- (none)")
            lines.append("")

            lines.append("CANNOT_ACCEPT:")
            lines.append(f"{cannot_accept}" if cannot_accept else "(none)")
            lines.append("")

            lines.append("PRIVATE_ASSUMPTION_FOR_BEHAVIOR_ONLY:")
            lines.append(f"{current_assumption}" if current_assumption else "(none)")
            lines.append("")

            lines.append("BEHAVIOR_DIRECTION:")
            lines.append(f"{drives_action}" if drives_action else "(none)")
            lines.append("")

            lines.append("EXECUTION_RULE:")
            lines.append("- 上述内容只用于控制该角色的选择、回答和行动。")
            lines.append("- 不得由旁白直接宣布。")
            lines.append("- 不得把隐藏目标或内部判断同义改写成心理解释。")
            blocks.append("\n".join(lines))

    # ── 4. PLANNED_STATE_DELTAS ──
    lines = ["=== PLANNED_STATE_DELTAS ===", ""]
    for i, action in enumerate(narrative_actions):
        if not isinstance(action, dict):
            continue
        lines.append(f"MOVE {i+1}:")
        lines.append(f"- GOAL: {_text(action.get('goal'))}")
        lines.append(f"- RESISTANCE: {_text(action.get('obstacle'))}")
        lines.append(f"- CHOICE_OR_INTERACTION: {_text(action.get('action_or_interaction'))}")
        lines.append(f"- BACKSTAGE_TARGET_DELTA: {_text(action.get('state_change'))}")
        lines.append(f"- REALIZATION_RULE:")
        lines.append(f"  只能通过对白、选择、行动或可见后果实现。")
        lines.append(f"  不得把TARGET_DELTA原句或同义总结直接写入旁白。")
        lines.append("")
    blocks.append("\n".join(lines))

    # ── 5. STOP_STATE ──
    must_not = _strings(ending_design.get("must_not_append"))
    lines = ["=== STOP_STATE ===", ""]
    lines.append("STOP_WHEN:")
    lines.append(f"{visible_closing}")
    lines.append("")
    lines.append("MUST_NOT_APPEND:")
    for item in must_not:
        lines.append(f"- {item}")
    lines.append("- 不总结人物关系意义")
    lines.append("- 不在停止事实成立后追加无关生活流程")
    blocks.append("\n".join(lines))

    projection_text = "\n\n".join(blocks)
    return {"mode": "narrative_projection", "architect_brief": projection_text}

