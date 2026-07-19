"""Deterministic narrative route classifier.

No LLM involvement.  Classification uses only Planner v2 fields already
present in the frozen contract — no new Planner fields required.
"""
from __future__ import annotations

from typing import Any

from app.schemas.narrative_route import (
    ROUTE_POLICY_VERSION,
    ROUTE_RULES,
    NarrativeRoute,
    NarrativeRouteDecision,
)


# ── Rule predicates ─────────────────────────────────────────────────


# Physical object verbs: actions that directly manipulate, transfer, hide,
# or verify the state of a concrete object.  Used to distinguish C_OBJECT_CAUSAL
# (object-driven) from A_LITE (information/interpretation-driven) scenes.
_OBJECT_ACTION_VERBS = [
    "抓", "拿", "递", "塞", "换", "搬", "摸", "翻", "找", "拉", "推",
    "挂", "取", "放", "扣", "盖", "掏", "压", "抽", "拆", "包", "绑",
    "装", "卸", "藏", "捡", "提", "拖", "扛", "抬", "摆", "铺", "插",
    "抽出", "塞进", "放进", "挂上", "取下", "翻开",
]


def _has_available_objects(plan: dict[str, Any]) -> bool:
    state = plan.get("scene_state") if isinstance(plan.get("scene_state"), dict) else {}
    objs = state.get("available_objects")
    return isinstance(objs, list) and len(objs) > 0


def _has_counterfactual(plan: dict[str, Any]) -> bool:
    transitions = plan.get("causal_transitions") if isinstance(plan.get("causal_transitions"), list) else []
    for t in transitions:
        if isinstance(t, dict) and t.get("counterfactual_without_action", "").strip():
            return True
    return False


def _has_rejected_alternative(plan: dict[str, Any]) -> bool:
    transitions = plan.get("causal_transitions") if isinstance(plan.get("causal_transitions"), list) else []
    for t in transitions:
        if isinstance(t, dict) and t.get("rejected_alternative", "").strip():
            return True
    return False


def _next_action_is_object_manipulation(plan: dict[str, Any]) -> bool:
    """True if the character_next_action involves physically manipulating,
    transferring, or verifying a concrete object WITHOUT being primarily
    communicative.  If the same action has both object verbs AND communication
    verbs (e.g. '拿起便签...用只有两人能听见的声音说'), the action is
    information-driven, not object-driven — C_OBJECT_CAUSAL should not match."""
    transitions = plan.get("causal_transitions") if isinstance(plan.get("causal_transitions"), list) else []
    for t in transitions:
        if not isinstance(t, dict):
            continue
        action = t.get("character_next_action", "")
        has_object_verb = any(v in action for v in _OBJECT_ACTION_VERBS)
        has_comm_verb = _action_has_communication(action)
        # Must have object verb AND no communication in the same action
        if has_object_verb and not has_comm_verb:
            return True
    return False


def _action_has_communication(action: str) -> bool:
    """True if the action string contains communication/signaling verbs."""
    comm_verbs = ["说", "告诉", "问", "示意", "点头", "摇头", "假装", "暗示",
                  "让对", "叫", "喊", "念", "读", "写便签", "发消息",
                  "听见", "声音", "开口", "解释"]
    return any(v in action for v in comm_verbs)


def _has_multiple_characters(plan: dict[str, Any]) -> bool:
    characters = plan.get("characters")
    return isinstance(characters, list) and len(characters) >= 2


def _second_character_has_goal(plan: dict[str, Any]) -> bool:
    """Second character has known, unknown or observed_evidence — indicating
    an active secondary viewpoint."""
    characters = plan.get("characters")
    if not isinstance(characters, list) or len(characters) < 2:
        return False
    second = characters[1]
    if not isinstance(second, dict):
        return False
    has_known = isinstance(second.get("known"), list) and len(second["known"]) > 0
    has_unknown = isinstance(second.get("unknown"), list) and len(second["unknown"]) > 0
    has_evidence = isinstance(second.get("observed_evidence"), list) and len(second["observed_evidence"]) > 0
    return has_known or has_unknown or has_evidence


def _has_first_character_assumption(plan: dict[str, Any]) -> bool:
    """First character has a current_interpretation or situational_assumption
    that could be wrong — essential for information gap."""
    characters = plan.get("characters")
    if not isinstance(characters, list) or len(characters) == 0:
        return False
    first = characters[0]
    if not isinstance(first, dict):
        return False
    return bool(
        first.get("current_interpretation", "").strip()
        or first.get("situational_assumption", "").strip()
    )


def _has_incomplete_information(plan: dict[str, Any]) -> bool:
    """Scene has unknown facts for the viewpoint character — the hallmark
    of information asymmetry."""
    characters = plan.get("characters")
    if not isinstance(characters, list) or len(characters) == 0:
        return False
    first = characters[0]
    if not isinstance(first, dict):
        return False
    unknown = first.get("unknown")
    return isinstance(unknown, list) and len(unknown) > 0


def _unknowns_are_about_information_gap(plan: dict[str, Any]) -> bool:
    """True if the first character's unknown facts are about the CONTENT of a
    specific communication (what was written/said/recorded), NOT about another
    person's motives, feelings, or relationship intentions."""
    characters = plan.get("characters")
    if not isinstance(characters, list) or len(characters) == 0:
        return False
    first = characters[0]
    if not isinstance(first, dict):
        return False
    unknown = first.get("unknown")
    if not isinstance(unknown, list) or len(unknown) == 0:
        return False

    unknown_text = " ".join(str(u) for u in unknown)

    # Must mention specific communication content — a note, message, statement,
    # record, or word whose CONTENT is unknown (not just whether it was sent).
    content_keywords = [
        "内容", "后半句", "前半句", "写了什么", "说了什么", "什么意思",
        "便签", "纸条", "文字", "话的", "下半句", "上半句", "完整句子",
        "名单", "记录", "登记", "撤回", "发了什么", "写了什",
    ]
    if not any(k in unknown_text for k in content_keywords):
        return False

    # Exclude unknowns that are primarily about relationship state
    relationship_keywords = [
        "喜欢", "在乎", "心意", "感觉", "感情", "爱",
        "是否为了她", "是否喜欢", "怎么想我", "对自己",
        "真实想法", "真实感受",
    ]
    if any(k in unknown_text for k in relationship_keywords):
        return False

    return True
    """Scene has unknown facts for the viewpoint character — the hallmark
    of information asymmetry."""
    characters = plan.get("characters")
    if not isinstance(characters, list) or len(characters) == 0:
        return False
    first = characters[0]
    if not isinstance(first, dict):
        return False
    unknown = first.get("unknown")
    return isinstance(unknown, list) and len(unknown) > 0


def _is_low_conflict_relation(plan: dict[str, Any]) -> bool:
    """Scene category is romance/relationship, no external physical urgency."""
    # Check category via scene_category or genre in plan
    category = plan.get("scene_category", "")
    if isinstance(category, str) and category.lower() in ("romance", "relationship", "恋爱"):
        return True
    # Check guardrails for absence of physical urgency markers
    guardrails = plan.get("tempo_guardrails") if isinstance(plan.get("tempo_guardrails"), dict) else {}
    # If dominant_pressure is physical_problem, this is NOT low-conflict
    dp = guardrails.get("dominant_pressure") if isinstance(guardrails.get("dominant_pressure"), dict) else {}
    if isinstance(dp, dict) and dp.get("kind") == "physical_problem":
        return False
    # Default: if scene_state doesn't mention equipment/device/leak/damage, consider it low-conflict
    state = plan.get("scene_state") if isinstance(plan.get("scene_state"), dict) else {}
    visible = state.get("visible_facts")
    if isinstance(visible, list):
        physical_keywords = ["漏水", "损坏", "故障", "滴水", "短路", "冒烟", "停电", "锁坏"]
        text = " ".join(str(f) for f in visible)
        if any(kw in text for kw in physical_keywords):
            return False
    # Check if scene facts and actions are about relationship, not a physical crisis.
    # Scan visible_facts, visible_trigger, and character_next_action for romance markers.
    relation_markers = ["消息", "未读", "伞", "蜡烛", "合租", "便利店", "末班车", "手机",
                        "扣在桌上", "豆浆", "便当", "一起走", "生日", "排练"]
    if isinstance(visible, list):
        vt = " ".join(str(f) for f in visible)
        if any(m in vt for m in relation_markers):
            return True
    transitions = plan.get("causal_transitions") if isinstance(plan.get("causal_transitions"), list) else []
    for t in transitions:
        if not isinstance(t, dict):
            continue
        trigger = t.get("visible_trigger", "")
        action = t.get("character_next_action", "")
        combined = str(trigger) + " " + str(action)
        if any(m in combined for m in relation_markers):
            return True
    return False


def _has_physical_failure(plan: dict[str, Any]) -> bool:
    """Scene involves equipment/object/space failure."""
    state = plan.get("scene_state") if isinstance(plan.get("scene_state"), dict) else {}
    visible = state.get("visible_facts")
    if isinstance(visible, list):
        physical_keywords = ["漏水", "损坏", "故障", "滴水", "短路", "冒烟", "停电", "锁坏", "被锁", "反锁", "锁着", "打不开", "卡住"]
        text = " ".join(str(f) for f in visible)
        if any(kw in text for kw in physical_keywords):
            return True
    # Also check entry_pressure
    guardrails = plan.get("tempo_guardrails") if isinstance(plan.get("tempo_guardrails"), dict) else {}
    dp = guardrails.get("dominant_pressure") if isinstance(guardrails.get("dominant_pressure"), dict) else {}
    if isinstance(dp, dict) and dp.get("kind") == "physical_problem":
        return True
    return False


def _is_task_or_investigation(plan: dict[str, Any]) -> bool:
    """Scene type is investigation, infiltration, search, or task."""
    state = plan.get("scene_state") if isinstance(plan.get("scene_state"), dict) else {}
    visible = state.get("visible_facts")
    if isinstance(visible, list):
        task_keywords = ["走失", "丢失", "找回", "寻找", "潜入", "密室", "包裹", "快递", "取错", "广播找", "找人", "说不清"]
        text = " ".join(str(f) for f in visible)
        if any(kw in text for kw in task_keywords):
            return True
    # Check visible_trigger + character_next_action in transitions
    transitions = plan.get("causal_transitions") if isinstance(plan.get("causal_transitions"), list) else []
    for t in transitions:
        if not isinstance(t, dict):
            continue
        trigger = t.get("visible_trigger", "")
        action = t.get("character_next_action", "")
        combined = str(trigger) + " " + str(action)
        if any(kw in combined for kw in ["走失", "丢失", "取错", "找回", "说不清", "广播", "搜寻"]):
            return True
    # Also check unknown_facts for task indicators (e.g., "家长" suggests lost-child task)
    characters = plan.get("characters")
    if isinstance(characters, list) and len(characters) > 0 and isinstance(characters[0], dict):
        unknowns = " ".join(str(u) for u in characters[0].get("unknown", []))
        if any(kw in unknowns for kw in ["家长", "找到", "搜寻", "搜索"]):
            return True
    return False


# ── Classifier ──────────────────────────────────────────────────────


def classify_narrative_route(plan: dict[str, Any] | None) -> NarrativeRouteDecision:
    """Classify the narrative route from a Planner v2 dict.

    Priority:
        1. C_OBJECT_CAUSAL  — causal objects present + counterfactual
        2. A_LITE_INFORMATION_GAP — multi-char + incomplete info + assumption
        3. B_SHORT_RELATION — low-conflict romance, no physical urgency
        4. B_PHYSICAL_PROBLEM — equipment/object/space failure
        5. D_FALLIBLE_TASK — investigation/infiltration/task
        6. B_DEFAULT — fallback
    """
    plan = plan if isinstance(plan, dict) else {}
    rejected: list[NarrativeRoute] = []

    # Pre-filter: task/investigation AND physical-failure scenes skip the
    # interpersonal rules (C_OBJECT_CAUSAL, A_LITE, B_SHORT) because their
    # core mechanism is task completion or physical problem resolution, not
    # object-mediated judgment or interpersonal information asymmetry.
    is_task = _is_task_or_investigation(plan)
    is_physical = _has_physical_failure(plan)
    skip_interpersonal = is_task or is_physical

    if not skip_interpersonal:
        # ── Interpersonal rules (skip for task/investigation scenes) ──

        # Rule 1: C_OBJECT_CAUSAL
        if (
            _has_available_objects(plan)
            and (_has_counterfactual(plan) or _has_rejected_alternative(plan))
            and _next_action_is_object_manipulation(plan)
        ):
            return NarrativeRouteDecision(
                route_name=NarrativeRoute.C_OBJECT_CAUSAL,
                decision_reasons=[
                    "scene_state.available_objects is non-empty",
                    "causal_transitions contains counterfactual_without_action or rejected_alternative",
                    "character_next_action involves physical object manipulation",
                ],
                matched_rules=["RULE_C_OBJECT_CAUSAL"],
                rejected_routes=[],
            )
        rejected.append(NarrativeRoute.C_OBJECT_CAUSAL)

        # Rule 2: A_LITE_INFORMATION_GAP
        if (
            _has_multiple_characters(plan)
            and _has_incomplete_information(plan)
            and _has_first_character_assumption(plan)
            and not _is_low_conflict_relation(plan)
        ):
            return NarrativeRouteDecision(
                route_name=NarrativeRoute.A_LITE_INFORMATION_GAP,
                decision_reasons=[
                    "multiple characters with distinct information",
                    "viewpoint character has unknown facts and an interpretation",
                    "secondary character carries independent knowledge",
                ],
                matched_rules=["RULE_A_LITE_INFORMATION_GAP"],
                rejected_routes=rejected,
            )
        rejected.append(NarrativeRoute.A_LITE_INFORMATION_GAP)

        # Rule 3: B_SHORT_RELATION
        if _is_low_conflict_relation(plan):
            return NarrativeRouteDecision(
                route_name=NarrativeRoute.B_SHORT_RELATION,
                decision_reasons=[
                    "scene is relationship-oriented with no physical urgency",
                    "character action involves relational move (message, gesture, proximity)",
                ],
                matched_rules=["RULE_B_SHORT_RELATION"],
                rejected_routes=rejected,
            )
        rejected.append(NarrativeRoute.B_SHORT_RELATION)

    else:
        # Task scenes: skip rules 1-3 entirely
        rejected.extend([
            NarrativeRoute.C_OBJECT_CAUSAL,
            NarrativeRoute.A_LITE_INFORMATION_GAP,
            NarrativeRoute.B_SHORT_RELATION,
        ])

    # Rule 4: B_PHYSICAL_PROBLEM
    if _has_physical_failure(plan):
        return NarrativeRouteDecision(
            route_name=NarrativeRoute.B_PHYSICAL_PROBLEM,
            decision_reasons=[
                "scene involves equipment failure, leak, damage, or locked access",
                "visible facts contain physical problem keywords",
            ],
            matched_rules=["RULE_B_PHYSICAL_PROBLEM"],
            rejected_routes=rejected,
        )
    rejected.append(NarrativeRoute.B_PHYSICAL_PROBLEM)

    # Rule 5: D_FALLIBLE_TASK
    if _is_task_or_investigation(plan):
        return NarrativeRouteDecision(
            route_name=NarrativeRoute.D_FALLIBLE_TASK,
            decision_reasons=[
                "scene involves search, infiltration, lost item, or task execution",
                "character must make choices under incomplete information",
            ],
            matched_rules=["RULE_D_FALLIBLE_TASK"],
            rejected_routes=rejected,
        )
    rejected.append(NarrativeRoute.D_FALLIBLE_TASK)

    # Rule 6: B_DEFAULT
    return NarrativeRouteDecision(
        route_name=NarrativeRoute.B_DEFAULT,
        decision_reasons=["no specific narrative mechanism detected"],
        matched_rules=["RULE_B_DEFAULT"],
        rejected_routes=rejected,
    )
