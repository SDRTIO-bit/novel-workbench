from __future__ import annotations

from app.llm.output_contracts import PlannerOutput, PlannerCharacterState, SceneState, WriterBrief, TempoGuardrails


def _find_pov_character(planner_output: PlannerOutput, viewpoint_name: str) -> PlannerCharacterState | None:
    if not viewpoint_name:
        return planner_output.characters[0] if planner_output.characters else None
    for character in planner_output.characters:
        if character.name == viewpoint_name:
            return character
    return planner_output.characters[0] if planner_output.characters else None


def _select_main_transition(planner_output: PlannerOutput):
    transitions = planner_output.causal_transitions
    if not transitions:
        return None
    # Prefer the first transition; it is Planner's ordering of the scene's
    # primary causal turn. Future refinements can score against entry_pressure.
    return transitions[0]


def _determine_opening(planner_output: PlannerOutput, guardrails: TempoGuardrails) -> tuple[str, str]:
    scene_state = planner_output.scene_state or SceneState()

    if scene_state.direct_consequence_available.strip():
        return "direct_consequence", scene_state.direct_consequence_available.strip()

    if scene_state.active_unfinished_action.strip():
        return "unfinished_action", scene_state.active_unfinished_action.strip()

    if guardrails.entry_pressure.strip():
        return "active_pressure", guardrails.entry_pressure.strip()

    fallback_parts = [p for p in (scene_state.location.strip(), scene_state.time_window.strip()) if p]
    if fallback_parts:
        return "new_scene_fact", "，".join(fallback_parts)

    if planner_output.scene_goal.strip():
        return "new_scene_fact", planner_output.scene_goal.strip()

    return "new_scene_fact", "新场景开始"


def compile_writer_brief(planner_output: PlannerOutput, override: dict | None = None) -> WriterBrief:
    """Deterministic, code-only compiler from PlannerOutput to WriterBrief.

    This function does not call an LLM. It extracts only the local state that
    Writer needs to render the next scene: the current concrete problem, the
    POV's known/unknown boundary, the immediate assumption and its basis, the
    next action, its visible consequence, the new constraint, and the stop fact.

    It explicitly strips: reader_must_infer, narrator_must_not_state, the
    author's correct answer, Critic-language, and any Planner free-text
    reasoning.
    """
    override = override or {}
    guardrails = planner_output.tempo_guardrails or TempoGuardrails(entry_pressure="", stop_after="")

    # Apply explicit author overrides to guardrails when provided.
    if "tempo_guardrails" in override and isinstance(override["tempo_guardrails"], dict):
        for key in ("entry_pressure", "dominant_disruption", "allowed_viewpoint_misread",
                    "disclosure_cap", "must_remain_unclassified", "stop_after",
                    "final_line_must_include"):
            if key in override["tempo_guardrails"]:
                setattr(guardrails, key, override["tempo_guardrails"][key])

    scene_state = planner_output.scene_state or SceneState()
    opening_mode, opening_fact = _determine_opening(planner_output, guardrails)
    viewpoint_character = scene_state.viewpoint_character or ""

    pov = _find_pov_character(planner_output, viewpoint_character)

    main_transition = _select_main_transition(planner_output)

    if pov:
        known_facts = list(pov.known_facts) + list(pov.observed_evidence)
        unknown_facts = list(pov.unknown_facts)
        current_assumption = pov.situational_assumption
        assumption_basis = list(pov.assumption_basis)
        next_action = pov.current_goal if not main_transition else main_transition.character_next_action
    else:
        known_facts = []
        unknown_facts = []
        current_assumption = ""
        assumption_basis = []
        next_action = main_transition.character_next_action if main_transition else ""

    immediate_consequence = main_transition.immediate_consequence if main_transition else ""
    next_constraint = main_transition.next_constraint if main_transition else ""

    # Override explicit writer-brief fields.
    if "opening_mode" in override:
        opening_mode = override["opening_mode"]
    if "opening_fact" in override:
        opening_fact = override["opening_fact"]
    if "viewpoint_character" in override:
        viewpoint_character = override["viewpoint_character"]
    if "known_facts" in override:
        known_facts = override["known_facts"]
    if "unknown_facts" in override:
        unknown_facts = override["unknown_facts"]
    if "current_assumption" in override:
        current_assumption = override["current_assumption"]
    if "assumption_basis" in override:
        assumption_basis = override["assumption_basis"]
    if "next_action" in override:
        next_action = override["next_action"]
    if "immediate_consequence" in override:
        immediate_consequence = override["immediate_consequence"]
    if "next_constraint" in override:
        next_constraint = override["next_constraint"]
    if "active_project_facts" in override:
        active_project_facts = override["active_project_facts"]
    else:
        active_project_facts = []
    if "remain_unclassified" in override:
        remain_unclassified = override["remain_unclassified"]
    else:
        remain_unclassified = list(guardrails.must_remain_unclassified)
    if "stop_fact" in override:
        stop_fact = override["stop_fact"]
    else:
        stop_fact = guardrails.stop_after
    if "final_line_must_include" in override:
        final_line = override["final_line_must_include"]
    else:
        final_line = guardrails.final_line_must_include

    # Ensure stop_fact is always present.
    if not stop_fact:
        stop_fact = planner_output.end_condition or planner_output.turning_point or "场景结束"

    # Keep lists compact so the brief stays short.
    known_facts = _limit_strings(known_facts, 10)
    unknown_facts = _limit_strings(unknown_facts, 10)
    assumption_basis = _limit_strings(assumption_basis, 5)
    remain_unclassified = _limit_strings(remain_unclassified, 5)

    return WriterBrief(
        opening_mode=opening_mode,
        opening_fact=opening_fact,
        viewpoint_character=viewpoint_character,
        known_facts=known_facts,
        unknown_facts=unknown_facts,
        current_assumption=current_assumption,
        assumption_basis=assumption_basis,
        next_action=next_action,
        immediate_consequence=immediate_consequence,
        next_constraint=next_constraint,
        active_project_facts=active_project_facts,
        remain_unclassified=remain_unclassified,
        stop_fact=stop_fact,
        final_line_must_include=final_line,
    )


def _limit_strings(values: list[str], limit: int) -> list[str]:
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    return cleaned[:limit]


def format_writer_brief(brief: WriterBrief) -> str:
    """Render a WriterBrief as the last block of the Writer user prompt."""
    lines: list[str] = []
    lines.append(f"【起笔模式】{brief.opening_mode}")
    lines.append(f"【进入事实】{brief.opening_fact}")
    if brief.viewpoint_character:
        lines.append(f"【当前视角】{brief.viewpoint_character}")

    if brief.known_facts:
        lines.append("【当前已知】")
        for fact in brief.known_facts:
            lines.append(f"- {fact}")

    if brief.unknown_facts:
        lines.append("【当前未知】")
        for fact in brief.unknown_facts:
            lines.append(f"- {fact}")

    if brief.current_assumption:
        lines.append(f"【即时判断】{brief.current_assumption}")
        if brief.assumption_basis:
            lines.append("【判断依据】")
            for basis in brief.assumption_basis:
                lines.append(f"- {basis}")

    if brief.next_action:
        lines.append(f"【下一行动】{brief.next_action}")
    if brief.immediate_consequence:
        lines.append(f"【可见后果】{brief.immediate_consequence}")
    if brief.next_constraint:
        lines.append(f"【新限制】{brief.next_constraint}")

    if brief.active_project_facts:
        lines.append("【本场设定】")
        for fact in brief.active_project_facts:
            lines.append(f"- {fact}")

    if brief.remain_unclassified:
        lines.append("【保持未分类】")
        for fact in brief.remain_unclassified:
            lines.append(f"- {fact}")

    lines.append(f"【停止事实】{brief.stop_fact}")
    if brief.final_line_must_include:
        lines.append(f"【末行必须包含】{brief.final_line_must_include}")

    return "\n".join(lines)
