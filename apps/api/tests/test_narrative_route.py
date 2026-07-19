"""Failing tests for narrative route classification, compilation, hash stability,
and backward compatibility.

These tests import modules that do not yet exist — they will fail with
ImportError until services/narrative_route_classifier.py and
services/narrative_brief_compiler.py are implemented.
"""
import hashlib
import json

import pytest

from app.services.writer_brief import (
    WriterBrief,
    WriterBriefC,
    compile_writer_brief,
    compile_writer_brief_c,
    compile_writer_input,
    validate_writer_brief,
)
from app.schemas.narrative_route import (
    NarrativeRoute,
    NarrativeRouteDecision,
    CompiledNarrativeInput,
    WriterBriefCObjectCausal,
    WriterBriefALite,
    WriterBriefBShort,
    WriterBriefBPhysical,
    WriterBriefDFallible,
)
from app.services.narrative_route_classifier import classify_narrative_route
from app.services.narrative_brief_compiler import (
    compile_narrative_route_input,
    get_instruction_block,
)


# ── Planner fixtures ──────────────────────────────────────────────


def _base_planner(**overrides):
    """Minimal but valid Planner v2 output."""
    plan = {
        "scene_state": {
            "present_characters": ["林澈"],
            "visible_facts": ["周宁的扣子错位", "周宁正走向点名台"],
        },
        "characters": [{
            "name": "林澈",
            "known": ["周宁没有低头检查校服"],
            "unknown": [],
            "observed_evidence": ["周宁的最上面扣眼扣到了第二颗扣子"],
            "current_interpretation": "周宁没有意识到扣错",
        }],
        "causal_transitions": [{
            "visible_trigger": "点名开始前，周宁走向点名台",
            "character_next_action": "林澈递出点名册示意周宁低头",
            "immediate_consequence": "周宁看见扣子错位",
            "next_constraint": "点名已经开始，不能当众解释",
        }],
        "tempo_guardrails": {
            "entry_pressure": "点名即将开始",
            "must_remain_unclassified": ["周宁是否已经发现"],
            "stop_state": {
                "visible_fact": "周宁把扣子重新扣好",
                "must_not_append": "不得解释同学关系",
            },
        },
        "active_project_facts": ["林澈是班长", "晨会公开点名"],
    }
    plan.update(overrides)
    return plan


def _causal_object_planner():
    """Planner for object-misrecognition / pursuit scene (→ C_OBJECT_CAUSAL)."""
    return _base_planner(
        scene_state={
            "present_characters": ["顾栖", "程野"],
            "visible_facts": ["深蓝外套被穿走", "钥匙在口袋里"],
            "available_objects": ["书包", "水壶", "便签纸"],
        },
        causal_transitions=[{
            "visible_trigger": "放学铃响后，顾栖发现椅背上外套被程野穿走",
            "character_next_action": "顾栖从书包里翻出便签纸写提醒贴在程野桌上",
            "immediate_consequence": "便签纸被风吹到地上",
            "next_constraint": "不能追上去喊名字",
            "rejected_alternative": "不能追出走廊喊人",
            "cost_or_commitment": "顾栖延迟了交钥匙时间",
            "counterfactual_without_action": "程野若不看便签，直接去操场，钥匙就交不成",
        }],
    )


def _information_gap_planner():
    """Planner for partial-message / multi-character misreading (→ A_LITE)."""
    return _base_planner(
        scene_state={
            "present_characters": ["叶舟", "唐闻"],
            "visible_facts": ["黑板槽里有一张便签", "便签上写着'别再……'"],
        },
        characters=[
            {
                "name": "叶舟",
                "known": ["便签上有自己的名字"],
                "unknown": ["便签是谁写的", "后半句是什么"],
                "observed_evidence": ["便签开头是'别再'", "唐闻正从讲台下来"],
                "current_interpretation": "唐闻写的便签",
            },
            {
                "name": "唐闻",
                "known": ["便签上写了完整句子"],
                "unknown": ["叶舟看到了前半句"],
                "observed_evidence": ["叶舟在看黑板槽"],
            },
        ],
        causal_transitions=[{
            "visible_trigger": "课间，叶舟在黑板槽里发现写着自己名字的便签",
            "character_next_action": "叶舟把便签翻过来用磁铁压在黑板角落",
            "immediate_consequence": "唐闻停步看了一眼",
            "next_constraint": "便签后半句未知，不能追问",
        }],
    )


def _romance_low_conflict_planner():
    """Planner for low-conflict romance scene (→ B_SHORT_RELATION)."""
    return _base_planner(
        scene_state={
            "present_characters": ["夏知", "韩川"],
            "visible_facts": ["手机亮起未读消息", "韩川把手机扣在桌上"],
        },
        characters=[{
            "name": "夏知",
            "known": ["昨晚发了消息"],
            "unknown": ["韩川为什么没回"],
            "observed_evidence": ["韩川先扣手机再去洗菜", "水已经开了"],
            "current_interpretation": "韩川故意不读",
        }],
        causal_transitions=[{
            "visible_trigger": "合租屋厨房里，夏知看见韩川的手机亮起",
            "character_next_action": "夏知把洗好的菜倒进锅里",
            "immediate_consequence": "韩川抬头看了一眼",
            "next_constraint": "只能通过动作试探",
        }],
    )


def _physical_problem_planner():
    """Planner for physical equipment failure (→ B_PHYSICAL_PROBLEM).
    Deliberately omits available_objects and counterfactual — a pure physical
    failure without causal-object dynamics routes to B_PHYSICAL, not C."""
    return _base_planner(
        scene_state={
            "present_characters": ["魏临"],
            "visible_facts": ["机房天花板滴水", "水正往插线板方向流"],
        },
        causal_transitions=[{
            "visible_trigger": "晚自习前，机房天花板开始滴水",
            "character_next_action": "魏临用胶带试图封住漏水点",
            "immediate_consequence": "胶带被水冲开",
            "next_constraint": "维修老师还在另一栋楼",
        }],
    )


def _fallible_task_planner():
    """Planner for investigation/infiltration task (→ D_FALLIBLE_TASK)."""
    return _base_planner(
        scene_state={
            "present_characters": ["陶然"],
            "visible_facts": ["小男孩攥着电影票", "票已经湿了", "保安在处理另一桩纠纷"],
        },
        causal_transitions=[{
            "visible_trigger": "商场服务台旁，小男孩说不清家长在哪层",
            "character_next_action": "陶然按下全场广播按钮",
            "immediate_consequence": "广播覆盖了整个商场",
            "next_constraint": "不能带小孩离开商场",
            "rejected_alternative": "不能凭票面时间直接去影厅找",
        }],
    )


# ── 1. Route classification tests ─────────────────────────────────


def test_classify_c_object_causal():
    """C_OBJECT_CAUSAL: planner has available_objects + counterfactual_without_action."""
    planner = _causal_object_planner()
    decision = classify_narrative_route(planner)
    assert decision.route_name == NarrativeRoute.C_OBJECT_CAUSAL
    assert "RULE_C_OBJECT_CAUSAL" in decision.matched_rules
    assert len(decision.decision_reasons) >= 1


def test_classify_a_lite_information_gap():
    """A_LITE_INFORMATION_GAP: multi-character + incomplete message + competing interpretations."""
    planner = _information_gap_planner()
    decision = classify_narrative_route(planner)
    assert decision.route_name == NarrativeRoute.A_LITE_INFORMATION_GAP
    assert "RULE_A_LITE_INFORMATION_GAP" in decision.matched_rules


def test_classify_b_short_relation():
    """B_SHORT_RELATION: low-conflict relationship, no external urgency."""
    planner = _romance_low_conflict_planner()
    decision = classify_narrative_route(planner)
    assert decision.route_name == NarrativeRoute.B_SHORT_RELATION
    assert "RULE_B_SHORT_RELATION" in decision.matched_rules


def test_classify_b_physical_problem():
    """B_PHYSICAL_PROBLEM: equipment/object/space failure."""
    planner = _physical_problem_planner()
    decision = classify_narrative_route(planner)
    assert decision.route_name == NarrativeRoute.B_PHYSICAL_PROBLEM
    assert "RULE_B_PHYSICAL_PROBLEM" in decision.matched_rules


def test_classify_d_fallible_task():
    """D_FALLIBLE_TASK: investigation/infiltration/task scenario."""
    planner = _fallible_task_planner()
    decision = classify_narrative_route(planner)
    assert decision.route_name == NarrativeRoute.D_FALLIBLE_TASK
    assert "RULE_D_FALLIBLE_TASK" in decision.matched_rules


def test_classify_fallback_b_default():
    """No rule matches → B_DEFAULT."""
    planner = _base_planner()
    decision = classify_narrative_route(planner)
    assert decision.route_name == NarrativeRoute.B_DEFAULT
    assert "RULE_B_DEFAULT" in decision.matched_rules


def test_priority_conflict_object_causal_over_a_lite():
    """When both C and A rules could match, C wins (higher priority)."""
    planner = _base_planner(
        scene_state={
            "present_characters": ["顾栖", "程野"],
            "visible_facts": ["深蓝外套被穿走", "钥匙在口袋里"],
            "available_objects": ["便签纸", "水壶"],
        },
        characters=[
            {
                "name": "顾栖",
                "known": ["钥匙在深蓝外套口袋里"],
                "unknown": ["程野是否故意穿走"],
                "observed_evidence": ["外套被穿走", "程野往操场跑"],
                "current_interpretation": "程野没注意口袋",
            },
            {
                "name": "程野",
                "known": ["穿的是同桌外套"],
                "unknown": ["口袋里有什么"],
                "observed_evidence": [],
            },
        ],
        causal_transitions=[{
            "visible_trigger": "放学铃响后，顾栖发现椅背上外套被程野穿走",
            "character_next_action": "顾栖从书包里翻出便签纸写提醒",
            "immediate_consequence": "便签纸被风吹到地上",
            "next_constraint": "不能追上去喊名字",
            "rejected_alternative": "不能追出走廊喊人",
            "counterfactual_without_action": "程野若不看便签，钥匙就交不成",
        }],
    )
    decision = classify_narrative_route(planner)
    assert decision.route_name == NarrativeRoute.C_OBJECT_CAUSAL
    # C is rule 1 — nothing was rejected before it matched.


def test_decision_includes_rejected_routes():
    """Every decision records routes that were considered and rejected.
    Use a lower-priority planner so rejected_routes is non-empty."""
    # B_DEFAULT planner: all specific rules fail, only B_DEFAULT matches
    planner = _base_planner()
    decision = classify_narrative_route(planner)
    assert len(decision.rejected_routes) >= 1
    assert decision.route_name not in decision.rejected_routes


def test_decision_reasons_are_non_empty():
    """decision_reasons must contain at least one human-readable reason."""
    planner = _information_gap_planner()
    decision = classify_narrative_route(planner)
    assert all(isinstance(r, str) and len(r) > 0 for r in decision.decision_reasons)


# ── 2. Brief compilation tests ────────────────────────────────────


def test_compile_c_object_causal_brief():
    planner = _causal_object_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    WriterBriefCObjectCausal.model_validate(brief)
    assert "available_causal_objects" in brief
    assert "rejected_alternative" in brief
    assert "cost_or_commitment" in brief
    assert "counterfactual_without_action" in brief
    assert len(brief["available_causal_objects"]) <= 3


def test_compile_a_lite_brief():
    planner = _information_gap_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    WriterBriefALite.model_validate(brief)
    assert "secondary_actor_goal" in brief
    assert "secondary_actor_observed_evidence" in brief
    assert "competing_interpretation" in brief
    assert "likely_countermove" in brief
    assert "reader_uncertainty_to_preserve" in brief


def test_compile_b_short_relation_brief():
    planner = _romance_low_conflict_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    WriterBriefBShort.model_validate(brief)
    assert "target_length_chars" in brief


def test_compile_b_physical_problem_brief():
    planner = _physical_problem_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    WriterBriefBPhysical.model_validate(brief)
    assert "concrete_problem" in brief
    assert "first_attempt" in brief
    assert "why_first_attempt_fails" in brief
    assert "second_action" in brief
    assert "accumulated_cost" in brief
    assert "visible_unresolved_state" in brief


def test_compile_d_fallible_task_brief():
    planner = _fallible_task_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    WriterBriefDFallible.model_validate(brief)
    assert "one_local_misjudgment" in brief
    assert "one_social_or_ethical_compromise" in brief
    assert "immediate_visible_consequence" in brief


def test_compiled_narrative_input_structure():
    """CompiledNarrativeInput has all required fields."""
    planner = _causal_object_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    assert isinstance(result, CompiledNarrativeInput)
    assert isinstance(result.decision, NarrativeRouteDecision)
    assert isinstance(result.compiled_brief, dict)
    assert isinstance(result.compiled_brief_hash, str)
    assert len(result.compiled_brief_hash) == 64  # SHA-256 hex
    assert isinstance(result.instruction_block, str)
    assert len(result.instruction_block) > 0
    assert isinstance(result.instruction_hash, str)
    assert len(result.instruction_hash) == 64


def test_instruction_block_differs_by_route():
    """Each route has a distinct instruction block."""
    instructions = set()
    for planner_factory in [
        _causal_object_planner,
        _information_gap_planner,
        _romance_low_conflict_planner,
        _physical_problem_planner,
        _fallible_task_planner,
    ]:
        result = compile_narrative_route_input(planner_factory(), {}, "narrative-route-v1")
        instructions.add(result.instruction_hash)
    assert len(instructions) == 5  # All five differ


# ── 3. Hash stability tests ───────────────────────────────────────


def test_same_planner_produces_identical_compiled_narrative_input():
    """Deterministic: same input twice → identical hash + brief."""
    planner = _causal_object_planner()
    r1 = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    r2 = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    assert r1.compiled_brief_hash == r2.compiled_brief_hash
    assert r1.instruction_hash == r2.instruction_hash
    assert r1.compiled_brief == r2.compiled_brief
    assert r1.instruction_block == r2.instruction_block


def test_compiled_brief_is_json_serializable():
    planner = _causal_object_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    serialized = json.dumps(result.compiled_brief, ensure_ascii=False)
    assert len(serialized) > 0


def test_route_decision_is_json_serializable():
    planner = _information_gap_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    serialized = json.dumps(result.decision.model_dump(), ensure_ascii=False)
    assert "route_name" in serialized


# ── 4. Specific route contracts ───────────────────────────────────


def test_a_lite_does_not_leak_correct_answer():
    """A_LITE brief must not include 'reader_must_infer' or 'narrator_must_not_state'."""
    planner = _information_gap_planner()
    planner["reader_must_infer"] = "唐闻本来想道歉"
    planner["causal_transitions"][0]["narrator_must_not_state"] = ["叶舟错了"]
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    serialized = json.dumps(result.compiled_brief, ensure_ascii=False)
    assert "reader_must_infer" not in serialized
    assert "narrator_must_not_state" not in serialized
    assert "唐闻本来想道歉" not in serialized


def test_a_lite_preserves_secondary_character_goal():
    """A_LITE brief has a non-empty secondary_actor_goal."""
    planner = _information_gap_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    assert len(brief["secondary_actor_goal"]) > 0


def test_c_fields_only_from_planner_existing_facts():
    """C_OBJECT_CAUSAL: all extra fields come from existing Planner fields,
    not from synthetic generation."""
    planner = _causal_object_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    # available_causal_objects must be subset of scene_state.available_objects
    expected = set(planner["scene_state"]["available_objects"])
    actual = set(brief["available_causal_objects"])
    assert actual <= expected, f"fields {actual - expected} not in Planner"
    # counterfactual_without_action must come from causal_transitions
    assert brief["counterfactual_without_action"] == planner["causal_transitions"][0]["counterfactual_without_action"]


def test_b_short_length_constraint_in_instruction():
    """B_SHORT_RELATION instruction mentions target length range."""
    planner = _romance_low_conflict_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    assert "350" in result.instruction_block.lower() or "550" in result.instruction_block.lower()


def test_b_short_stop_constraint_in_instruction():
    """B_SHORT_RELATION instruction forbids second-confirmation append."""
    planner = _romance_low_conflict_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    block = result.instruction_block
    # Must forbid at least one of the second-confirmation patterns
    forbidden_patterns = ["空气安静", "距离更近", "他没有松手", "她也没有退开", "双方都没走"]
    assert any(p in block for p in forbidden_patterns) or "追加" in block


def test_b_physical_must_contain_failure_remedy_fields():
    """B_PHYSICAL_PROBLEM: first_attempt and why_first_attempt_fails are non-empty."""
    planner = _physical_problem_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    assert len(brief["first_attempt"]) > 0
    assert len(brief["why_first_attempt_fails"]) > 0
    assert len(brief["second_action"]) > 0


def test_d_must_include_misjudgment_and_compromise():
    """D_FALLIBLE_TASK: one_local_misjudgment and one_social_or_ethical_compromise
    are non-empty."""
    planner = _fallible_task_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    brief = result.compiled_brief
    assert len(brief["one_local_misjudgment"]) > 0
    assert len(brief["one_social_or_ethical_compromise"]) > 0


def test_d_instruction_suppresses_generic_suspense():
    """D_FALLIBLE_TASK instruction warns against cliché suspense signals."""
    planner = _fallible_task_planner()
    result = compile_narrative_route_input(planner, {}, "narrative-route-v1")
    block = result.instruction_block
    cliché_count = sum(1 for w in ["钟表", "脚步", "灯光闪烁", "雨声", "阴影", "呼吸声", "手机震动"] if w in block)
    assert cliché_count >= 2  # Must mention at least 2 to suppress


# ── 5. Old B / C backward compatibility ────────────────────────────


def test_old_b_still_compiles():
    """compile_writer_brief must still work and produce WriterBrief."""
    planner = _base_planner()
    brief = compile_writer_brief(planner)
    WriterBrief.model_validate(brief)
    assert "opening_fact" in brief


def test_old_c_still_compiles():
    """compile_writer_brief_c must still work and produce WriterBriefC."""
    planner = _base_planner(
        scene_state={
            "present_characters": ["林澈"],
            "visible_facts": ["扣子错位"],
            "available_objects": ["点名册"],
        },
        causal_transitions=[{
            "visible_trigger": "点名开始",
            "character_next_action": "递点名册",
            "immediate_consequence": "看见扣子",
            "next_constraint": "不能当众说",
            "rejected_alternative": "不能喊她",
            "cost_or_commitment": "当着全班递册子",
            "counterfactual_without_action": "她不接就落空",
        }],
    )
    brief = compile_writer_brief_c(planner)
    WriterBriefC.model_validate(brief)


def test_old_compile_writer_input_still_works():
    """compile_writer_input with old modes must still work."""
    planner = _base_planner()
    assert compile_writer_input(planner, "complete_planner") == planner
    assert isinstance(compile_writer_input(planner, "writer_brief"), dict)
    assert isinstance(compile_writer_input(planner, "narrative_behaviour_brief"), dict)
    with pytest.raises(ValueError):
        compile_writer_input(planner, "nonsense_mode")


# ── 6. Existing regression tests pass ──────────────────────────────

# These re-run the original test_writer_brief.py cases to ensure nothing broke.

def test_regression_canonical_unknown_facts():
    brief = compile_writer_brief(_base_planner())
    assert "unknown_facts" in brief
    assert "unknown_information" not in brief


def test_regression_empty_assumption():
    planner = _base_planner(characters=[{
        "name": "林澈", "known": [], "unknown": [], "observed_evidence": [],
        "current_interpretation": "",
    }])
    brief = compile_writer_brief(planner)
    assert brief["current_assumption"] == ""
    assert brief["assumption_basis"] == []


def test_regression_writer_brief_rejects_backend_fields():
    brief = compile_writer_brief(_base_planner())
    brief["reader_must_infer"] = "后台答案"
    with pytest.raises(ValueError):
        WriterBrief.model_validate(brief)


def test_regression_active_project_facts_capped():
    from app.services.writer_brief import MAX_ACTIVE_PROJECT_FACTS
    facts = [f"事实{i}" for i in range(MAX_ACTIVE_PROJECT_FACTS + 3)]
    brief = compile_writer_brief(_base_planner(active_project_facts=facts))
    assert len(brief["active_project_facts"]) == MAX_ACTIVE_PROJECT_FACTS
