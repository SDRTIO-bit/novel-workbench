"""Tests for Chapter Architect v1: schema, prompt, writer_brief mapping."""
import hashlib
import json

import pytest

from app.llm.output_contracts import (
    ChapterArchitectOutput,
    ChapterPosition,
    ContentSummary,
    PlotLines,
    CharacterPlan,
    NarrativeAction,
    NarrationBoundary,
    EndingDesign,
    CapacityCheck,
    validate_planner_output,
)
from app.services.writer_brief import (
    compile_chapter_architect_brief,
    compile_writer_input,
    _detect_chapter_architect,
)


# ── Prompt existence ────────────────────────────────────────────────────

def test_chapter_architect_prompt_exists():
    from app.prompts.defaults import BUILTIN_PROMPTS
    matches = [p for p in BUILTIN_PROMPTS if p["name"] == "Chapter Architect v1"]
    assert len(matches) == 1
    p = matches[0]
    assert p["stage"] == "planner"
    assert p["output_mode"] == "structured"
    assert p["output_schema_name"] == "chapter_architect_v1"


# ── Schema validation: valid sample ────────────────────────────────────

def _valid_architect_plan() -> dict:
    return {
        "architect_contract_version": 1,
        "chapter_position": {
            "type": "日常章",
            "reader_payoff": "笑",
            "hook_requirement": "可弱钩子",
        },
        "content_summary": {
            "cause": "方笛发现自己那台洗衣机的衣服被老人取出来了",
            "development": "方笛查看面板记录，试图确认运行时间",
            "turning_point": "老人指出快洗程序最多四十分钟，方笛的记忆被质疑",
            "climax": "方笛按下详情按钮，面板显示实际运行时长四十分钟",
            "ending": "方笛面对时间记录，意识到自己记错了设定",
        },
        "core_event": "洗衣房里的时间争执：方笛的记忆与机器记录的对决",
        "plot_lines": {
            "main_line": "方笛从确认自己正确到接受自己记错",
            "emotion_line": "从确信→动摇→接受",
            "logic_line": "发现异常→检查证据→证据推翻记忆→接受事实",
            "comedy_line": "",
        },
        "characters": [{
            "name": "方笛",
            "goal": "确认机器运行了多久",
            "known": ["自己设了一小时", "现在才四点二十"],
            "unknown": ["机器实际运行了多久", "老人是否动了机器"],
            "withheld": "",
            "cannot_accept": "",
            "observed_evidence": "面板显示程序已结束",
            "current_assumption": "机器可能被提前停止了",
            "drives_action": "按下详情按钮查看运行记录",
        }],
        "narration_boundary": {
            "reader_must_infer": ["方笛可能本来就没设一小时"],
            "narrator_must_not_state": ["方笛确实记错了", "老人是对的"],
            "viewpoint_note": "全程跟随方笛的视觉和判断",
        },
        "narrative_actions": [
            {
                "goal": "确认机器为什么停了",
                "obstacle": "老人说机器早就停了，衣服已经被取出",
                "action_or_interaction": "方笛查看滚筒和面板，与老人对话",
                "state_change": "从不确定到发现面板显示程序已结束",
            },
            {
                "goal": "查证实际运行时长",
                "obstacle": "老人平静反驳方笛的记忆",
                "action_or_interaction": "方笛按下详情按钮查看运行记录",
                "state_change": "从相信自己正确到面对四十分钟的客观记录",
            },
            {
                "goal": "接受记忆错误的事实",
                "obstacle": "面板数字与记忆冲突",
                "action_or_interaction": "方笛对比时间记录和自己的记忆",
                "state_change": "从坚持到接受自己记错了设定时间",
            },
        ],
        "ending_design": {
            "visible_closing_state": "方笛盯着屏幕上的四十分钟，不再开口",
            "hook_type": "动作定格",
            "hook_detail": "方笛盯着面板，老人继续操作烘干机",
            "hook_strength": "medium",
            "must_not_append": ["心理说明", "老人安慰"],
        },
        "capacity_check": {
            "target_range": "2000-2600",
            "capacity_sufficient": True,
            "capacity_reason": "三个局面变化（发现异常→查证→接受）足以支撑一章节",
            "forbidden_padding": ["反复看手机", "环境描写", "心理独白"],
        },
    }


def test_chapter_architect_valid_parses():
    plan = _valid_architect_plan()
    output = validate_planner_output(plan)
    assert isinstance(output, ChapterArchitectOutput)
    assert output.architect_contract_version == 1
    assert output.core_event
    assert len(output.narrative_actions) == 3
    assert output.capacity_check.capacity_sufficient is True


# ── Schema rejects ──────────────────────────────────────────────────────

def test_rejects_empty_content_summary():
    plan = _valid_architect_plan()
    plan["content_summary"]["cause"] = ""
    with pytest.raises(ValueError, match="cause"):
        validate_planner_output(plan)


def test_rejects_too_few_actions():
    plan = _valid_architect_plan()
    plan["narrative_actions"] = [plan["narrative_actions"][0]]
    with pytest.raises(ValueError, match="at least 2"):
        validate_planner_output(plan)


def test_rejects_too_many_actions():
    plan = _valid_architect_plan()
    a = plan["narrative_actions"][0]
    plan["narrative_actions"] = [a] * 5
    with pytest.raises(ValueError, match="at most 4"):
        validate_planner_output(plan)


def test_rejects_empty_hook_type():
    plan = _valid_architect_plan()
    plan["ending_design"]["hook_type"] = ""
    with pytest.raises(ValueError, match="hook_type"):
        validate_planner_output(plan)


# ── Content length limits ──────────────────────────────────────────────

def test_content_summary_field_max_length():
    """Fields have max_length=80."""
    plan = _valid_architect_plan()
    plan["content_summary"]["cause"] = "x" * 81
    with pytest.raises(ValueError, match="String should have at most 80"):
        validate_planner_output(plan)


def test_narrative_action_field_max_length():
    plan = _valid_architect_plan()
    plan["narrative_actions"][0]["goal"] = "x" * 81
    with pytest.raises(ValueError, match="String should have at most 80"):
        validate_planner_output(plan)


# ── Detect architect ────────────────────────────────────────────────────

def test_detect_chapter_architect():
    assert _detect_chapter_architect({"architect_contract_version": 1}) is True
    assert _detect_chapter_architect({"planner_contract_version": 3}) is False
    assert _detect_chapter_architect({}) is False


# ── Writer brief mapping ───────────────────────────────────────────────

def test_compile_chapter_architect_brief():
    brief = compile_chapter_architect_brief(_valid_architect_plan())
    assert brief["mode"] == "chapter_architect"
    text = brief["architect_brief"]
    assert "=== CHAPTER_STORY ===" in text
    assert "=== NARRATIVE_ACTIONS ===" in text
    assert "=== CHARACTERS ===" in text
    assert "=== NARRATION_BOUNDARY ===" in text
    assert "=== ENDING_DESIGN ===" in text
    assert "=== CAPACITY ===" in text
    assert "方笛" in text
    assert "前台只写POV人物能感知的内容" in text


def test_compile_writer_input_chapter_architect_mode():
    result = compile_writer_input(_valid_architect_plan(), "chapter_architect")
    assert result["mode"] == "chapter_architect"
    assert "architect_brief" in result


def test_compile_brief_deterministic():
    plan = _valid_architect_plan()
    b1 = compile_chapter_architect_brief(plan)
    b2 = compile_chapter_architect_brief(plan)
    assert b1 == b2


def test_compile_brief_p2_still_works():
    """Old P2 planner output still compiles without architect fields."""
    p2_plan = {
        "planner_contract_version": 2,
        "scene_state": {"visible_facts": ["x"]},
        "characters": [{"name": "A", "known": []}],
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
    result = compile_writer_input(p2_plan, "writer_brief")
    assert "opening_fact" in result


def test_capacity_insufficient_brief():
    plan = _valid_architect_plan()
    plan["capacity_check"]["capacity_sufficient"] = False
    plan["capacity_check"]["capacity_reason"] = "事件不足以支撑目标篇幅"
    brief = compile_chapter_architect_brief(plan)
    text = brief["architect_brief"]
    assert "SUFFICIENT: false" in text
    assert "宁可短于目标" in text


# ── Model construction ─────────────────────────────────────────────────

def test_chapter_position_model():
    cp = ChapterPosition(type="日常章", reader_payoff="笑")
    assert cp.type == "日常章"

def test_content_summary_model():
    cs = ContentSummary(cause="a", development="b", turning_point="c", climax="d", ending="e")
    assert cs.cause == "a"

def test_narrative_action_model():
    na = NarrativeAction(goal="g", obstacle="o", action_or_interaction="a", state_change="s")
    assert na.goal == "g"

def test_ending_design_model():
    ed = EndingDesign(visible_closing_state="s", hook_type="笑点收束")
    assert ed.hook_strength == "medium"
