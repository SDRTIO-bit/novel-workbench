"""Tests for Narrative Projection Compiler v1.

Covers all contracts, error handling, deterministic behaviour,
provenance isolation, and backward compatibility.
"""
import copy
import hashlib
import json

import pytest

from app.services.writer_brief import (
    compile_chapter_architect_brief,
    compile_narrative_projection_brief,
    compile_writer_brief,
    compile_writer_input,
)


# ── Fixtures ────────────────────────────────────────────────────────────

def _valid_a1_plan(**overrides) -> dict:
    """Minimum valid Chapter Architect v1 output for narrative_projection."""
    plan = {
        "architect_contract_version": 1,
        "chapter_position": {
            "type": "日常章",
            "reader_payoff": "糖",
            "hook_requirement": "可弱钩子",
        },
        "content_summary": {
            "cause": "夏知看到韩川的手机亮起自己的未读消息",
            "development": "韩川把手机扣在桌上，去洗菜",
            "turning_point": "水开了，韩川没有提消息",
            "climax": "夏知决定不等了，把碗收走",
            "ending": "韩川发现碗被收走",
        },
        "core_event": "厨房里的未读消息",
        "plot_lines": {
            "main_line": "夏知用行动确认韩川的态度",
            "emotion_line": "等待→决定不等",
            "logic_line": "看到消息未读→等待→决定行动",
            "comedy_line": "",
        },
        "characters": [
            {
                "name": "夏知",
                "goal": "确认韩川是否看了消息，决定今晚待不待",
                "known": ["昨晚发了消息", "韩川手机亮了"],
                "unknown": ["韩川是否看了消息", "韩川为何不回"],
                "withheld": [],
                "cannot_accept": "",
                "observed_evidence": ["韩川先扣手机再去洗菜", "水开了，只有两只碗"],
                "current_assumption": "韩川看了消息但不想回",
                "drives_action": "收走自己那碗，离开厨房",
            },
            {
                "name": "韩川",
                "goal": "不想现在讨论昨晚那条消息",
                "known": ["夏知昨晚发了消息"],
                "unknown": [],
                "withheld": ["他确实看了消息"],
                "cannot_accept": "夏知当面质问为什么不回",
                "observed_evidence": [],
                "current_assumption": "夏知在等回应",
                "drives_action": "用洗菜拖延时间",
            },
        ],
        "narration_boundary": {
            "reader_must_infer": ["韩川的真实心情"],
            "narrator_must_not_state": [
                "韩川为什么不想回",
                "韩川的真实情感状态",
            ],
            "viewpoint_note": "跟随夏知的视觉和判断",
        },
        "narrative_actions": [
            {
                "goal": "夏知判断韩川是否看过消息",
                "obstacle": "韩川不主动提消息，也没有看手机的迹象",
                "action_or_interaction": "夏知观察韩川的动作和桌上的手机",
                "state_change": "从不确定到确认韩川在回避",
            },
            {
                "goal": "夏知决定是否离开",
                "obstacle": "直接问可能让关系更尴尬",
                "action_or_interaction": "夏知收碗，准备离开厨房",
                "state_change": "从等待到用行动结束等待",
            },
        ],
        "ending_design": {
            "visible_closing_state": "夏知端着碗走出厨房",
            "hook_type": "动作定格",
            "hook_detail": "韩川回头看见空位",
            "hook_strength": "medium",
            "must_not_append": ["韩川追出去", "关系总结"],
        },
        "capacity_check": {
            "target_range": "2000-2600",
            "capacity_sufficient": True,
            "capacity_reason": "两个局面变化足以支撑一章节",
            "forbidden_padding": ["环境描写堆砌", "心理独白"],
        },
    }
    plan.update(overrides)
    return plan


# ── Test 1-2: Normal happy paths ────────────────────────────────────────

def test_normal_two_character_scene():
    """Two-character scene compiles to all five blocks in order."""
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    assert result["mode"] == "narrative_projection"
    text = result["architect_brief"]

    # Block order must be stable
    assert "=== NARRATION_ACCESS ===" in text
    assert "=== FOREGROUND_KNOWLEDGE ===" in text
    assert "=== BACKSTAGE_BEHAVIOR_ONLY ===" in text
    assert "=== PLANNED_STATE_DELTAS ===" in text
    assert "=== STOP_STATE ===" in text

    # Verify block order
    pos_na = text.index("=== NARRATION_ACCESS ===")
    pos_fk = text.index("=== FOREGROUND_KNOWLEDGE ===")
    pos_bb = text.index("=== BACKSTAGE_BEHAVIOR_ONLY ===")
    pos_pd = text.index("=== PLANNED_STATE_DELTAS ===")
    pos_ss = text.index("=== STOP_STATE ===")
    assert pos_na < pos_fk < pos_bb < pos_pd < pos_ss


def test_multiple_non_focus_characters():
    """Scene with 3+ characters generates one BACKSTAGE block per non-focus."""
    plan = _valid_a1_plan()
    plan["characters"].append({
        "name": "室友甲",
        "goal": "路过厨房拿水",
        "known": [],
        "unknown": [],
        "withheld": [],
        "cannot_accept": "",
        "observed_evidence": [],
        "current_assumption": "",
        "drives_action": "",
    })
    result = compile_narrative_projection_brief(plan, focus_character="夏知")
    text = result["architect_brief"]
    # Two BACKSTAGE blocks
    assert text.count("=== BACKSTAGE_BEHAVIOR_ONLY ===") == 2
    # Each non-focus character should appear
    assert "CHARACTER:\n韩川" in text
    assert "CHARACTER:\n室友甲" in text


# ── Test 3-8: Error handling ────────────────────────────────────────────

def test_focus_character_missing():
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_FOCUS_MISSING"):
        compile_narrative_projection_brief(_valid_a1_plan(), focus_character=None)


def test_focus_character_empty_string():
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_FOCUS_MISSING"):
        compile_narrative_projection_brief(_valid_a1_plan(), focus_character="")


def test_focus_character_not_found():
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_FOCUS_NOT_FOUND"):
        compile_narrative_projection_brief(
            _valid_a1_plan(), focus_character="不存在的角色"
        )


def test_characters_missing():
    plan = _valid_a1_plan()
    del plan["characters"]
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_CHARACTERS_MISSING"):
        compile_narrative_projection_brief(plan, focus_character="夏知")


def test_characters_empty_list():
    plan = _valid_a1_plan()
    plan["characters"] = []
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_CHARACTERS_MISSING"):
        compile_narrative_projection_brief(plan, focus_character="夏知")


def test_visible_closing_state_missing():
    plan = _valid_a1_plan()
    plan["ending_design"]["visible_closing_state"] = ""
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_STOP_STATE_MISSING"):
        compile_narrative_projection_brief(plan, focus_character="夏知")


# ── Test 9-10: Empty field handling ─────────────────────────────────────

def test_known_unknown_empty_shows_none():
    """Empty known/unknown fields produce '(none)' not random text."""
    plan = _valid_a1_plan()
    plan["characters"][0]["known"] = []
    plan["characters"][0]["unknown"] = []
    plan["characters"][0]["observed_evidence"] = []
    plan["characters"][0]["current_assumption"] = ""
    result = compile_narrative_projection_brief(plan, focus_character="夏知")
    text = result["architect_brief"]
    fk_section = text.split("=== FOREGROUND_KNOWLEDGE ===")[1].split("===")[0]
    assert "(none)" in fk_section
    # Should NOT invent facts
    assert "可能" not in fk_section.split("KNOWN:")[1].split("SUSPECTED")[0]


def test_withheld_empty_shows_none():
    """Empty withheld produces '(none)' not fabricated behaviour."""
    plan = _valid_a1_plan()
    plan["characters"][1]["withheld"] = []
    result = compile_narrative_projection_brief(plan, focus_character="夏知")
    text = result["architect_brief"]
    # Find the backstage block for 韩川
    bb_block = text.split("=== BACKSTAGE_BEHAVIOR_ONLY ===")[1]
    assert "DO_NOT_VOLUNTARILY_DISCLOSE:" in bb_block
    assert "(none)" in bb_block.split("DO_NOT_VOLUNTARILY_DISCLOSE:")[1].split("CANNOT_ACCEPT")[0]


# ── Test 11-12: Narration access boundaries ─────────────────────────────

def test_narrator_must_not_state_in_access():
    """narrator_must_not_state items appear in FORBIDDEN_DIRECT_ACCESS."""
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    assert "韩川为什么不想回" in text
    assert "韩川的真实情感状态" in text
    # Should be in the FORBIDDEN section
    na_section = text.split("=== NARRATION_ACCESS ===")[1].split("===")[0]
    assert "韩川为什么不想回" in na_section


def test_reader_must_infer_absent():
    """reader_must_infer must NEVER appear in narrative_projection output."""
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    assert "reader_must_infer" not in text
    assert "韩川的真实心情" not in text  # this is reader_must_infer


# ── Test 13-14: Forbidden fields absence ────────────────────────────────

def test_chapter_position_absent():
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    assert "chapter_position" not in text
    assert "READER_PAYOFF" not in text
    assert "CHAPTER_TYPE" not in text


def test_capacity_check_absent():
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    assert "capacity_check" not in text
    assert "CAPACITY" not in text
    assert "SUFFICIENT" not in text
    assert "capacity_reason" not in text


# ── Test 15-16: Narrative actions mapping ───────────────────────────────

def test_narrative_action_maps_to_backstage_target_delta():
    """state_change field becomes BACKSTAGE_TARGET_DELTA."""
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    assert "MOVE 1:" in text
    assert "BACKSTAGE_TARGET_DELTA:" in text
    assert "从不确定到确认韩川在回避" in text


def test_realization_rule_present():
    """Every MOVE must include REALIZATION_RULE."""
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    assert "REALIZATION_RULE:" in text
    assert "只能通过对白、选择、行动或可见后果实现" in text
    assert "不得把TARGET_DELTA原句或同义总结直接写入旁白" in text
    # Both moves should have it
    assert text.count("REALIZATION_RULE:") >= 2


# ── Test 17: Determinism ─────────────────────────────────────────────────

def test_compile_twice_produces_identical_output():
    plan = _valid_a1_plan()
    r1 = compile_narrative_projection_brief(plan, focus_character="夏知")
    r2 = compile_narrative_projection_brief(plan, focus_character="夏知")
    assert r1 == r2
    assert r1["architect_brief"] == r2["architect_brief"]


def test_output_hash_stable():
    """SHA256 of output text must be stable."""
    plan = _valid_a1_plan()
    r1 = compile_narrative_projection_brief(plan, focus_character="夏知")
    r2 = compile_narrative_projection_brief(plan, focus_character="夏知")
    h1 = hashlib.sha256(r1["architect_brief"].encode()).hexdigest()
    h2 = hashlib.sha256(r2["architect_brief"].encode()).hexdigest()
    assert h1 == h2


def test_input_not_mutated():
    """Compiler must not modify the input dict."""
    plan = _valid_a1_plan()
    before = copy.deepcopy(plan)
    compile_narrative_projection_brief(plan, focus_character="夏知")
    assert plan == before


# ── Test 18: No forbidden phrases ───────────────────────────────────────

def test_no_forbidden_behaviour_phrases():
    """Output must not contain fabricated behaviour phrases."""
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    for phrase in ("模糊回答", "转移话题", "眼神回避", "异常停顿", "响应速度异常"):
        assert phrase not in text, f"Forbidden phrase '{phrase}' found in output"


# ── Test 19-20: Backward compatibility ──────────────────────────────────

def test_old_compile_writer_input_modes_unchanged():
    """complete_planner, writer_brief, writer_brief_v3, chapter_architect,
    narrative_behaviour_brief must all still work with old 2-arg signature."""
    from app.services.writer_brief import compile_writer_brief, compile_writer_brief_c
    p2_plan = {
        "planner_contract_version": 2,
        "scene_state": {"visible_facts": ["x"], "present_characters": ["A"]},
        "characters": [{"name": "A", "known": [], "unknown": [], "observed_evidence": []}],
        "causal_transitions": [{
            "visible_trigger": "y",
            "character_next_action": "z",
            "immediate_consequence": "w",
            "next_constraint": "v",
        }],
        "tempo_guardrails": {
            "entry_pressure": "e",
            "stop_state": {"visible_fact": "s", "must_not_append": ""},
        },
    }

    # Old 2-arg positional call must work
    assert compile_writer_input(p2_plan, "complete_planner") == p2_plan
    assert compile_writer_input(p2_plan, "writer_brief") == compile_writer_brief(p2_plan)
    assert compile_writer_input(p2_plan, "narrative_behaviour_brief") == compile_writer_brief_c(p2_plan)

    # chapter_architect must still work
    a1 = _valid_a1_plan()
    r = compile_writer_input(a1, "chapter_architect")
    assert r["mode"] == "chapter_architect"
    assert r == compile_chapter_architect_brief(a1)


def test_narrative_projection_via_compile_writer_input():
    """narrative_projection mode accessible via compile_writer_input with focus_character kwarg."""
    result = compile_writer_input(
        _valid_a1_plan(), "narrative_projection", focus_character="夏知"
    )
    assert result["mode"] == "narrative_projection"
    assert "architect_brief" in result
    assert "=== NARRATION_ACCESS ===" in result["architect_brief"]


def test_narrative_projection_without_focus_raises():
    """Calling narrative_projection without focus_character via compile_writer_input raises."""
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_FOCUS_MISSING"):
        compile_writer_input(_valid_a1_plan(), "narrative_projection")


def test_plan_missing():
    """None or empty plan raises NARRATIVE_PROJECTION_PLAN_MISSING."""
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_PLAN_MISSING"):
        compile_narrative_projection_brief(None, focus_character="夏知")
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_PLAN_MISSING"):
        compile_narrative_projection_brief({}, focus_character="夏知")


def test_narrative_actions_missing():
    plan = _valid_a1_plan()
    plan["narrative_actions"] = []
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_ACTIONS_MISSING"):
        compile_narrative_projection_brief(plan, focus_character="夏知")


# ── Test: Character ordering preserved ──────────────────────────────────

def test_character_order_preserved():
    """Non-focus characters appear in the same order as A1 input."""
    plan = _valid_a1_plan()
    plan["characters"].append({
        "name": "路人丙",
        "goal": "",
        "known": [],
        "unknown": [],
        "withheld": [],
        "cannot_accept": "",
        "observed_evidence": [],
        "current_assumption": "",
        "drives_action": "",
    })
    result = compile_narrative_projection_brief(plan, focus_character="夏知")
    text = result["architect_brief"]
    # 韩川 should appear before 路人丙 in backstage blocks
    pos_hc = text.index("韩川")
    pos_pass = text.index("路人丙")
    assert pos_hc < pos_pass


# ── Test: No active props ───────────────────────────────────────────────

def test_no_active_props_in_output():
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    assert "ACTIVE_PROPS" not in text


# ── Test: Focus character not in FORBIDDEN list ─────────────────────────

def test_focus_character_has_correct_access():
    """Focus character should be in DIRECT_INTERNAL_ACCESS not OBSERVABLE_ONLY."""
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="夏知"
    )
    text = result["architect_brief"]
    na_section = text.split("=== NARRATION_ACCESS ===")[1].split("=== FOREGROUND")[0]
    # 夏知 must NOT be in OBSERVABLE_ONLY
    obs_section = na_section.split("OBSERVABLE_ONLY:")[1].split("FORBIDDEN")[0]
    assert "夏知" not in obs_section


# ── Test: Focus must be exact match ─────────────────────────────────────

def test_focus_character_exact_match_required():
    """Partial/whitespace-only matches should fail; exact match with surrounding whitespace is ok after strip."""
    with pytest.raises(ValueError, match="NARRATIVE_PROJECTION_FOCUS_NOT_FOUND"):
        compile_narrative_projection_brief(
            _valid_a1_plan(), focus_character="夏"  # partial
        )
    # Whitespace around exact name is stripped and should succeed
    result = compile_narrative_projection_brief(
        _valid_a1_plan(), focus_character="  夏知  "
    )
    assert "夏知" in result["architect_brief"]


# ── Test: Non-focus character with no hidden info ──────────────────────

def test_non_focus_without_hidden_info():
    """Character with no withheld/goal/assumption still gets clean backstage block."""
    plan = _valid_a1_plan()
    plan["characters"][1] = {
        "name": "路人丁",
        "goal": "",
        "known": [],
        "unknown": [],
        "withheld": [],
        "cannot_accept": "",
        "observed_evidence": [],
        "current_assumption": "",
        "drives_action": "",
    }
    result = compile_narrative_projection_brief(plan, focus_character="夏知")
    text = result["architect_brief"]
    # Should have "(none)" for empty fields, not fabricated content
    assert "CHARACTER:\n路人丁" in text
    for forbidden in ("模糊回答", "转移话题", "眼神回避", "嫌疑人"):
        assert forbidden not in text
