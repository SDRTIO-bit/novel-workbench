"""Deterministic, writer-facing projection of a Planner output.

The full Planner output remains the audit source for Critic and Judge.  This
module deliberately exposes only the scene facts a Writer needs to stage the
next actions; it never forwards the Planner's reader-inference or narrator
withholding answers.
"""
from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def compile_writer_brief(scene_plan: dict[str, Any] | None) -> dict[str, Any]:
    """Return a small, deterministic Writer input without hidden answers."""
    plan = scene_plan if isinstance(scene_plan, dict) else {}
    state = plan.get("scene_state") if isinstance(plan.get("scene_state"), dict) else {}
    guardrails = (
        plan.get("tempo_guardrails")
        if isinstance(plan.get("tempo_guardrails"), dict)
        else {}
    )
    stop_state = guardrails.get("stop_state") if isinstance(guardrails.get("stop_state"), dict) else {}
    pressure = guardrails.get("dominant_pressure") if isinstance(guardrails.get("dominant_pressure"), dict) else {}

    transitions: list[dict[str, str]] = []
    for item in plan.get("causal_transitions", []):
        if not isinstance(item, dict):
            continue
        transition = {
            key: _text(item.get(key))
            for key in (
                "id",
                "visible_trigger",
                "character_next_action",
                "rejected_alternative",
                "cost_or_commitment",
                "immediate_consequence",
                "next_constraint",
            )
        }
        transitions.append({key: value for key, value in transition.items() if value})

    return {
        "scene_goal": _text(plan.get("scene_goal")),
        "location": _text(plan.get("location")),
        "time": _text(plan.get("time")),
        "concrete_problem": _text(plan.get("concrete_problem")),
        "pressure": _text(plan.get("pressure")),
        "scene_state": {
            "present_characters": state.get("present_characters", []),
            "visible_facts": state.get("visible_facts", []),
            "available_objects": state.get("available_objects", []),
            "unresolved_problem": _text(state.get("unresolved_problem")),
            "already_existing_constraints": state.get("already_existing_constraints", []),
        },
        "causal_transitions": transitions,
        "entry_pressure": _text(guardrails.get("entry_pressure")),
        "dominant_pressure": _text(pressure.get("description")),
        "stop_state": {
            "visible_fact": _text(stop_state.get("visible_fact")),
            "what_is_now_different": _text(stop_state.get("what_is_now_different")),
            "must_not_append": _text(stop_state.get("must_not_append")),
        },
        "forbidden": [item for item in plan.get("forbidden", []) if isinstance(item, str) and item.strip()],
    }
