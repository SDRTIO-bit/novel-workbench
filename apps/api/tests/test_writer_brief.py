import pytest

from app.llm.output_contracts import PlannerOutput
from app.prompts.writer_brief import compile_writer_brief, format_writer_brief


def _planner_output(**overrides) -> PlannerOutput:
    data = {
        "scene_goal": "推进异常",
        "location": "机库",
        "time": "换班前",
        "characters": [
            {
                "name": "陆衡",
                "current_goal": "查明真相",
                "known_facts": ["工单编号", "冷却管有异响"],
                "unknown_facts": ["敲击声来源"],
                "observed_evidence": ["压力表读数偏高"],
                "stable_mistaken_beliefs": ["阀门只是松了"],
                "situational_assumption": "阀门松了",
                "assumption_basis": ["压力表读数偏高", "昨夜大风"],
                "constraints": ["不能暴露未来工单"],
            },
        ],
        "scene_state": {
            "viewpoint_character": "陆衡",
            "last_completed_action": "放下工具",
            "active_unfinished_action": "检查阀门",
            "direct_consequence_available": "工具落地后，敲击声突然停止",
            "character_positions": ["陆衡在冷却管旁"],
            "objects_in_play": ["压力表", "扳手"],
            "current_constraints": ["不能暴露未来工单"],
        },
        "pressure": "即将交班",
        "turning_point": "敲击声再次出现",
        "end_condition": "切断电源",
        "forbidden": ["揭晓发送者"],
        "causal_transitions": [
            {
                "id": "CT01",
                "kind": "evidence_to_action",
                "visible_trigger": "接线盒里出现 GR-0713",
                "character_next_action": "陆衡询问许栀父亲的名字",
                "reader_must_infer": "编号与许明远有关",
                "narrator_must_not_state": ["两个编号一致"],
                "immediate_consequence": "陆衡改变调查方向",
                "next_constraint": "他不能透露未来工单",
            },
        ],
        "chapter_contract_check": {},
        "tempo_guardrails": {
            "entry_pressure": "林隅正把熄火的探测车拖回仓库。",
            "dominant_disruption": "冷却管里传出敲击声。",
            "allowed_viewpoint_misread": "他以为压力阀松了。",
            "disclosure_cap": 1,
            "must_remain_unclassified": ["敲击声来源"],
            "stop_after": "他切断外门电源。",
            "final_line_must_include": "身份验证通过",
        },
    }
    data.update(overrides)
    return PlannerOutput(**data)


def test_compile_prefers_direct_consequence_opening():
    brief = compile_writer_brief(_planner_output())

    assert brief.opening_mode == "direct_consequence"
    assert brief.opening_fact == "工具落地后，敲击声突然停止"


def test_compile_uses_active_unfinished_action_when_no_consequence():
    planner = _planner_output()
    planner.scene_state.direct_consequence_available = ""

    brief = compile_writer_brief(planner)

    assert brief.opening_mode == "unfinished_action"
    assert brief.opening_fact == "检查阀门"


def test_compile_collects_pov_known_unknown_and_assumption():
    brief = compile_writer_brief(_planner_output())

    assert brief.viewpoint_character == "陆衡"
    assert "工单编号" in brief.known_facts
    assert "压力表读数偏高" in brief.known_facts
    assert "敲击声来源" in brief.unknown_facts
    assert brief.current_assumption == "阀门松了"
    assert "压力表读数偏高" in brief.assumption_basis


def test_compile_extracts_transition_action_consequence_and_constraint():
    brief = compile_writer_brief(_planner_output())

    assert brief.next_action == "陆衡询问许栀父亲的名字"
    assert brief.immediate_consequence == "陆衡改变调查方向"
    assert brief.next_constraint == "他不能透露未来工单"


def test_compile_uses_tempo_guardrails_for_stop_and_final_line():
    brief = compile_writer_brief(_planner_output())

    assert brief.stop_fact == "他切断外门电源。"
    assert brief.final_line_must_include == "身份验证通过"
    assert "敲击声来源" in brief.remain_unclassified


def test_compile_filters_private_planner_content():
    brief = compile_writer_brief(_planner_output())
    rendered = format_writer_brief(brief)

    assert "reader_must_infer" not in rendered
    assert "narrator_must_not_state" not in rendered
    assert "chapter_contract_check" not in rendered
    assert "两个编号一致" not in rendered
    assert "编号与许明远有关" not in rendered


def test_compile_applies_explicit_guardrail_override():
    override = {
        "tempo_guardrails": {
            "stop_after": "他关闭总闸。",
            "final_line_must_include": "系统离线",
        }
    }
    brief = compile_writer_brief(_planner_output(), override=override)

    assert brief.stop_fact == "他关闭总闸。"
    assert brief.final_line_must_include == "系统离线"


def test_compile_limits_list_lengths():
    planner = _planner_output()
    planner.characters[0].known_facts = [f"事实{i}" for i in range(20)]

    brief = compile_writer_brief(planner)

    assert len(brief.known_facts) <= 10


def test_format_writer_brief_renders_all_sections():
    brief = compile_writer_brief(_planner_output())
    rendered = format_writer_brief(brief)

    assert "【起笔模式】" in rendered
    assert brief.opening_fact in rendered
    assert "【当前视角】陆衡" in rendered
    assert "【当前已知】" in rendered
    assert "【当前未知】" in rendered
    assert "【即时判断】阀门松了" in rendered
    assert "【判断依据】" in rendered
    assert "【下一行动】" in rendered
    assert "【可见后果】" in rendered
    assert "【新限制】" in rendered
    assert "【保持未分类】" in rendered
    assert "【停止事实】" in rendered
    assert "【末行必须包含】身份验证通过" in rendered


def test_compile_falls_back_to_end_condition_when_stop_after_missing():
    planner = _planner_output()
    planner.tempo_guardrails.stop_after = ""

    brief = compile_writer_brief(planner)

    assert brief.stop_fact == "切断电源"


def test_compile_requires_opening_fact_fallback_to_goal():
    planner = _planner_output()
    planner.scene_state.direct_consequence_available = ""
    planner.scene_state.active_unfinished_action = ""
    planner.tempo_guardrails.entry_pressure = ""
    planner.scene_state.location = ""
    planner.scene_state.time_window = ""

    brief = compile_writer_brief(planner)

    assert brief.opening_mode == "new_scene_fact"
    assert brief.opening_fact == "推进异常"
