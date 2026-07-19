"""Narrative route brief compilers and instruction registry.

Each compiler produces a route-specific Pydantic model from Planner v2 fields
only.  No new Planner fields are required.
"""
from __future__ import annotations

from typing import Any

from app.schemas.narrative_route import (
    ROUTE_POLICY_VERSION,
    NarrativeRoute,
    CompiledNarrativeInput,
    WriterBriefCObjectCausal,
    WriterBriefALite,
    WriterBriefBShort,
    WriterBriefBPhysical,
    WriterBriefDFallible,
)
from app.services.narrative_route_classifier import classify_narrative_route
from app.services.writer_brief import (
    MAX_ACTIVE_PROJECT_FACTS,
    WriterBrief,
    _strings,
    _text,
    _viewpoint_character,
    compile_writer_brief,
)


# ── Instruction registry ────────────────────────────────────────────


def get_instruction_block(route: NarrativeRoute) -> str:
    """Return the route-specific instruction block appended to the Writer prompt."""
    return _INSTRUCTIONS.get(route, _INSTRUCTIONS[NarrativeRoute.B_DEFAULT])


_INSTRUCTIONS: dict[NarrativeRoute, str] = {
    NarrativeRoute.C_OBJECT_CAUSAL: (
        "\n\n## 物件因果执行\n"
        "场景中存在可用因果物件（available_causal_objects）。\n"
        "人物的判断必须可被物件状态验证或拆穿。\n"
        "必须让一个具体替代方案因行动而被放弃（rejected_alternative）。\n"
        "行动产生可见代价或承诺（cost_or_commitment）。\n"
        "他人反应或反事实后果必须在场景中成立（counterfactual_without_action）。\n"
        "禁止抽象关系总结；只处理可见动作与物件变化。"
    ),
    NarrativeRoute.A_LITE_INFORMATION_GAP: (
        "\n\n## 信息缺口执行\n"
        "场景中存在第二人物（secondary actor），该人物掌握视角人物不知道的信息。\n"
        "视角人物的判断基于不完整信息，可能错误。\n"
        "第二人物有自己的行动目标（secondary_actor_goal）。\n"
        "写作时保留至少两个相互竞争的解释（competing_interpretation），\n"
        "不向读者揭示最终正确答案。\n"
        "只描述不能解释的信息（reader_uncertainty_to_preserve），\n"
        "不描述读者应该得出的结论。\n"
        "保持角色信息隔离：每个角色只基于自己观察到的证据行动。"
    ),
    NarrativeRoute.B_SHORT_RELATION: (
        "\n\n## 短篇关系执行\n"
        "目标长度：350到550中文字符。\n"
        "只处理一个请求、接受、拒绝、让步或承诺。\n"
        "不展开消息、信件、回忆的完整内容。\n"
        "最多保留一个感官细节链。\n"
        "第一次关系变化通过可见动作成立后立即停止。\n"
        "禁止停止后追加：双方都没走、空气安静、距离更近、他没有松手、她也没有退开"
        "等第二次确认式收尾。"
    ),
    NarrativeRoute.B_PHYSICAL_PROBLEM: (
        "\n\n## 物理麻烦执行\n"
        "场景核心是一个具体物理问题（漏水、损坏、设备故障等）。\n"
        "人物必须至少尝试一次局部补救（first_attempt），该补救必须因具体原因失败"
        "（why_first_attempt_fails）。\n"
        "失败后执行第二个不同行动（second_action）。\n"
        "必须积累可见代价（accumulated_cost）。\n"
        "结尾保留可见的未解决状态（visible_unresolved_state）。\n"
        "禁止人物连续使用正确方案：至少允许一次局部错误或无效补救。"
    ),
    NarrativeRoute.D_FALLIBLE_TASK: (
        "\n\n## 可错任务执行\n"
        "场景核心是调查、潜入、寻找、包裹或密室等任务。\n"
        "人物必须在场景中犯至少一个局部判断错误（one_local_misjudgment）。\n"
        "人物必须在社会或伦理层面作出至少一次小妥协（one_social_or_ethical_compromise）。\n"
        "每个错误选择必须产生立即可见后果（immediate_visible_consequence）。\n"
        "以下元素不能承担主要戏剧功能：钟表、脚步、灯光闪烁、雨声、阴影、呼吸声、手机震动。\n"
        "它们不是绝对禁用，但不能替代人物选择作为紧张感的来源。"
    ),
    NarrativeRoute.B_DEFAULT: (
        "\n\n只输出场景正文；用可见行动处理这个具体麻烦，并在 stop_state 成立处停止。"
    ),
}


# ── Brief compilers ─────────────────────────────────────────────────


def _shared_fields(plan: dict[str, Any]) -> dict[str, Any]:
    """Extract the shared WriterBrief fields from a Planner v2 dict."""
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

    return {
        "opening_mode": "entry_pressure",
        "opening_fact": opening_fact,
        "viewpoint_character": _text(character.get("name")),
        "known_facts": known_facts,
        "unknown_facts": _strings(character.get("unknown")),
        "current_assumption": assumption,
        "assumption_basis": basis,
        "next_action": _text(transition.get("character_next_action")),
        "immediate_consequence": _text(transition.get("immediate_consequence")),
        "next_constraint": _text(transition.get("next_constraint")),
        "active_project_facts": _strings(plan.get("active_project_facts"))[:MAX_ACTIVE_PROJECT_FACTS],
        "remain_unclassified": _strings(guardrails.get("must_remain_unclassified")),
        "stop_fact": _text(stop_state.get("visible_fact")),
        "must_not_append": _text(stop_state.get("must_not_append")),
        "final_line_must_include": _text(guardrails.get("final_line_must_include")),
    }


def _transition_fields(plan: dict[str, Any]) -> dict[str, Any]:
    transitions = plan.get("causal_transitions") if isinstance(plan.get("causal_transitions"), list) else []
    return next((item for item in transitions if isinstance(item, dict)), {})


def _compile_c_object_causal(plan: dict[str, Any]) -> dict[str, Any]:
    state = plan.get("scene_state") if isinstance(plan.get("scene_state"), dict) else {}
    transition = _transition_fields(plan)

    return WriterBriefCObjectCausal(
        **_shared_fields(plan),
        available_causal_objects=_strings(state.get("available_objects"))[:3],
        rejected_alternative=_text(transition.get("rejected_alternative")),
        cost_or_commitment=_text(transition.get("cost_or_commitment")),
        counterfactual_without_action=_text(transition.get("counterfactual_without_action")),
    ).model_dump()


def _compile_a_lite(plan: dict[str, Any]) -> dict[str, Any]:
    shared = _shared_fields(plan)
    characters = plan.get("characters")
    second_char = {}
    if isinstance(characters, list) and len(characters) >= 2:
        second_char = characters[1] if isinstance(characters[1], dict) else {}

    # Build competing interpretations from first character's assumption
    # plus what they DON'T know
    first_char = _viewpoint_character(plan)
    competing = []
    if shared["current_assumption"]:
        competing.append(shared["current_assumption"])
    unknown = _strings(first_char.get("unknown"))
    if unknown:
        competing.append(f"可能不是{unknown[0]}" if unknown else "")

    return WriterBriefALite(
        **shared,
        secondary_actor_goal=_text(second_char.get("current_interpretation"))
        or _text(second_char.get("situational_assumption"))
        or _text(second_char.get("known", [None])[0] if isinstance(second_char.get("known"), list) and second_char.get("known") else ""),
        secondary_actor_observed_evidence=_strings(second_char.get("observed_evidence"))[:5],
        competing_interpretation=[c for c in (competing + ["信息被刻意保留"]) if c.strip()][:3],
        likely_countermove=_text(second_char.get("current_interpretation"))
        or _text(second_char.get("situational_assumption"))
        or "对方可能做出不同反应",
        reader_uncertainty_to_preserve="后半句便签内容未知" if "便签" in shared.get("opening_fact", "")
        else " ".join(shared.get("unknown_facts", ["关键信息"]))
        if shared.get("unknown_facts") else "信息缺口",
    ).model_dump()


def _compile_b_short(plan: dict[str, Any]) -> dict[str, Any]:
    return WriterBriefBShort(
        **_shared_fields(plan),
        target_length_chars=450,
    ).model_dump()


def _compile_b_physical(plan: dict[str, Any]) -> dict[str, Any]:
    shared = _shared_fields(plan)
    transition = _transition_fields(plan)

    return WriterBriefBPhysical(
        **shared,
        concrete_problem=shared["opening_fact"],
        first_attempt=shared["next_action"],
        why_first_attempt_fails=_text(transition.get("immediate_consequence"))
        or "第一次尝试因外部条件失败",
        second_action=_text(transition.get("next_constraint"))
        or "采取不同的补救方案",
        accumulated_cost=_text(transition.get("cost_or_commitment"))
        or "付出了时间代价",
        visible_unresolved_state=shared["stop_fact"],
    ).model_dump()


def _compile_d_fallible(plan: dict[str, Any]) -> dict[str, Any]:
    shared = _shared_fields(plan)
    transition = _transition_fields(plan)

    return WriterBriefDFallible(
        **shared,
        one_local_misjudgment=_text(transition.get("rejected_alternative"))
        or "基于不完整信息做了错误判断",
        one_social_or_ethical_compromise=_text(transition.get("cost_or_commitment"))
        or "在行动中做出了社会层面的小妥协",
        immediate_visible_consequence=shared["immediate_consequence"],
        next_constraint_field=shared["next_constraint"],
    ).model_dump()


_COMPILERS: dict[NarrativeRoute, Any] = {
    NarrativeRoute.C_OBJECT_CAUSAL: _compile_c_object_causal,
    NarrativeRoute.A_LITE_INFORMATION_GAP: _compile_a_lite,
    NarrativeRoute.B_SHORT_RELATION: _compile_b_short,
    NarrativeRoute.B_PHYSICAL_PROBLEM: _compile_b_physical,
    NarrativeRoute.D_FALLIBLE_TASK: _compile_d_fallible,
    NarrativeRoute.B_DEFAULT: compile_writer_brief,
}


# ── Main entry point ────────────────────────────────────────────────


def compile_narrative_route_input(
    planner_dict: dict[str, Any] | None,
    scene_metadata: dict[str, Any] | None = None,
    policy_version: str = ROUTE_POLICY_VERSION,
    *,
    planner_candidate_id: str | None = None,
) -> CompiledNarrativeInput:
    """Classify and compile a narrative route input from a Planner v2 dict.

    Accepts ``planner_candidate_id`` as a keyword argument for direct call from
    GenerationService._build_context_request().

    Returns a CompiledNarrativeInput with the route decision, compiled brief,
    and instruction block — all deterministically derived from the Planner output.
    """
    plan = planner_dict if isinstance(planner_dict, dict) else {}

    # Classify
    decision = classify_narrative_route(plan)

    # Compile the route-specific brief
    compiler = _COMPILERS.get(decision.route_name, compile_writer_brief)
    compiled_brief = compiler(plan)

    # Get the instruction block
    instruction_block = get_instruction_block(decision.route_name)

    # Hash everything
    compiled_brief_hash = CompiledNarrativeInput.hash_dict(compiled_brief)
    instruction_hash = CompiledNarrativeInput.hash_text(instruction_block)

    # Resolve planner_candidate_id: explicit kwarg > scene_metadata dict
    pcid = planner_candidate_id
    if pcid is None and scene_metadata:
        pcid = scene_metadata.get("planner_candidate_id")

    return CompiledNarrativeInput(
        decision=decision,
        compiled_brief=compiled_brief,
        compiled_brief_hash=compiled_brief_hash,
        instruction_block=instruction_block,
        instruction_hash=instruction_hash,
        planner_candidate_id=pcid,
    )
