"""Pure-function contract tests for the sacrificial error channel runner.

No LLM calls — slot math, override factory, call-order randomization,
blind tokens, the abort rule, and the deterministic XML/core extraction.
"""
import importlib.util
from pathlib import Path


def _runner_module():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "sacrificial_error_channel_feasibility_v1",
        root / "experiments" / "run_sacrificial_error_channel_feasibility_v1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_slot_math():
    runner = _runner_module()
    case_ids = [case[0] for case in runner.SCENES]
    assert len(runner.SCENES) == 4
    assert case_ids == ["NM-03", "ROMANCE-02", "CO-04", "CO-05"]
    slots = runner.expected_slots(case_ids)
    assert len(slots) == 24
    for group in runner.GROUPS:
        assert len([s for s in slots if s[1] == group]) == 12
    for case_id in case_ids:
        assert len([s for s in slots if s[0] == case_id]) == 6
        for group in runner.GROUPS:
            assert len([s for s in slots if s[0] == case_id and s[1] == group]) == 3


def test_writer_override_factory():
    runner = _runner_module()
    a = runner.writer_override_for_group("A")
    e = runner.writer_override_for_group("E")
    for override in (a, e):
        assert override["writer_input_mode"] == "writer_brief"
        assert "writer_behavior_mode" not in override
        assert override["_instruction_block"]
        assert len(override["_instruction_hash"]) == 64
        assert override["_policy_metadata"]["seed"] is None
    # The ONLY delta between groups is the instruction.
    frozen_keys = (
        "provider_id", "model_id", "prompt_version_id",
        "temperature", "top_p", "max_output_tokens", "timeout_seconds",
        "writer_input_mode",
    )
    for key in frozen_keys:
        assert a[key] == e[key], key
    assert a["_instruction_block"] != e["_instruction_block"]
    assert a["_instruction_hash"] != e["_instruction_hash"]
    # Experiment-level token override, identical for both groups (spec V).
    assert a["max_output_tokens"] == 6000
    # Group E contract facts
    assert "不是思维链" in e["_instruction_block"]
    for reason in runner.DISCARD_REASONS:
        assert reason in e["_instruction_block"]


def test_replica_call_order_reproducible_and_stratified():
    runner = _runner_module()
    orders = [runner.replica_call_order("NM-03", r) for r in (1, 2, 3)]
    assert orders == [runner.replica_call_order("NM-03", r) for r in (1, 2, 3)]
    for order in orders:
        assert sorted(order) == ["A", "E"]
    # Across the whole experiment both orders must appear.
    all_orders = {
        tuple(runner.replica_call_order(c, r))
        for c in ("NM-03", "ROMANCE-02", "CO-04", "CO-05")
        for r in (1, 2, 3)
    }
    assert len(all_orders) == 2


def test_blind_token_deterministic_and_group_sensitive():
    runner = _runner_module()
    token = runner.make_blind_token("CO-04", "A", 1)
    assert token == runner.make_blind_token("CO-04", "A", 1)
    assert len(token) == 12
    assert token != runner.make_blind_token("CO-04", "E", 1)
    assert runner.make_pair_token("CO-04", 1) == runner.make_pair_token("CO-04", 1)


def test_planner_hard_failure_aborts_entire_run():
    runner = _runner_module()
    assert runner.planner_error_is_fatal("PLANNER_OUTPUT_CONTRACT_INVALID") is True
    assert runner.planner_error_is_fatal("LLM_ERROR") is True
    assert runner.planner_error_is_fatal(None) is False
    assert runner.export_allowed("aborted") is False
    assert runner.export_allowed("completed") is True


def _unit_xml(n: int, core_len: int = 400) -> str:
    parts = []
    for i in range(1, n + 1):
        parts.append(
            f'<unit id="{i}">\n'
            f'<discard reason="mind_explanation">{"删" * 120}</discard>\n'
            f'<core>{"正" * core_len}</core>\n'
            f"</unit>"
        )
    return "\n".join(parts)


def test_extract_units_complete_xml():
    runner = _runner_module()
    raw = _unit_xml(6, core_len=250)
    result = runner.extract_units(raw)
    assert result["extract_status"] == "complete"
    assert len(result["units"]) == 6
    assert all(u["discard"] and u["core"] for u in result["units"])
    assert result["units"][0]["discard_reason"] == "mind_explanation"
    # core pieces joined with exactly two newlines, tags excluded
    assert "\n\n" in result["core_text"]
    assert "<core>" not in result["core_text"]
    assert len(result["core_text"]) == 6 * 250 + 5 * 2
    assert len(result["discard_text"]) == 6 * 120 + 5 * 2
    v = runner.validate_units(result)
    assert v["xml_parsable"] is True
    assert v["unit_count"] == 6
    assert "UNIT_COUNT_OUT_OF_RANGE" not in v["validator_codes"]
    assert "UNIT_MISSING_PART" not in v["validator_codes"]
    assert v["core_character_count"] == 1510  # < 1800 → shortfall flagged
    assert v["core_length_shortfall"] is True
    assert "CORE_LENGTH_SHORTFALL" in v["validator_codes"]
    assert "MANUAL_REVIEW_REQUIRED" in v["validator_codes"]


def test_extract_units_recovered_on_broken_xml():
    runner = _runner_module()
    # Stray '&' breaks strict XML; complete <core> blocks survive.
    raw = (
        '<unit id="1"><discard reason="cliche_expression">旧 & 破</discard>'
        "<core>第一段正文。</core></unit>\n"
        "<unit id=\"2\"><discard>第二段删文</discard><core>第二段正文</core>"
    )
    result = runner.extract_units(raw)
    assert result["extract_status"] == "recovered"
    assert result["core_text"].startswith("第一段正文。")
    assert "第二段正文" in result["core_text"]
    v = runner.validate_units(result)
    assert v["xml_parsable"] is False
    assert "XML_RECOVERED" in v["validator_codes"]


def test_extract_units_core_parse_failed():
    runner = _runner_module()
    result = runner.extract_units("没有任何 core 标签的纯文本输出。")
    assert result["extract_status"] == "CORE_PARSE_FAILED"
    assert result["core_text"] == ""
    v = runner.validate_units(result)
    assert "CORE_PARSE_FAILED" in v["validator_codes"]


def test_validate_flags_unit_count_missing_parts_tags_and_context_words():
    runner = _runner_module()
    raw = _unit_xml(3)  # below the 5–7 range
    result = runner.extract_units(raw)
    v = runner.validate_units(result)
    assert "UNIT_COUNT_OUT_OF_RANGE" in v["validator_codes"]

    broken = (
        '<unit id="1"><discard reason="cross_mind">只有删文</discard><core></core></unit>'
    )
    result = runner.extract_units(broken)
    # core empty → strict parse kept (valid XML) but missing core content
    assert result["extract_status"] in ("recovered", "CORE_PARSE_FAILED", "complete")

    tagged = runner.validate_units({
        "extract_status": "complete",
        "units": [{"id": "1", "discard": "x", "core": "正文 <core> 残留"}],
        "core_text": "刚才 方才 又 再次 仍然 继续 这才 先前 依旧 <core> 残留",
        "discard_text": "x",
    })
    assert "XML_TAGS_IN_CORE" in tagged["validator_codes"]
    assert tagged["unit_count"] == 1
    assert set(tagged["context_dependency_words"]) == set(
        runner.CONTEXT_DEPENDENCY_WORDS
    )
