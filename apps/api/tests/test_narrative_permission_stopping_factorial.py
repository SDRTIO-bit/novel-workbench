"""Pure-function contract tests for the factorial experiment runner.

No LLM calls — only slot math, override factory, call-order randomization,
blind tokens and the D3 abort rule. Phase 1, tests first.
"""
import importlib.util
from pathlib import Path


def _runner_module():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "narrative_permission_stopping_factorial_v1",
        root / "experiments" / "run_narrative_permission_stopping_factorial_v1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_slot_math():
    runner = _runner_module()
    case_ids = [case[0] for case in runner.SCENES]
    assert len(runner.SCENES) == 8
    slots = runner.expected_slots(case_ids)
    assert len(slots) == 96
    for group in runner.GROUPS:
        assert len([s for s in slots if s[1] == group]) == 24
    for case_id in case_ids:
        assert len([s for s in slots if s[0] == case_id]) == 12
        for group in runner.GROUPS:
            assert len([s for s in slots if s[0] == case_id and s[1] == group]) == 3


def test_writer_override_factory():
    runner = _runner_module()
    a = runner.writer_override_for_group("A")
    # Group A is pure production: no instruction keys at all
    assert "_instruction_block" not in a
    assert "_instruction_hash" not in a
    assert a["writer_input_mode"] == "writer_brief"
    assert "writer_behavior_mode" not in a
    assert "route_policy_version" not in a
    for group in ("B", "C", "D"):
        override = runner.writer_override_for_group(group)
        assert override["_instruction_block"]
        instruction_hash = override["_instruction_hash"]
        assert isinstance(instruction_hash, str) and len(instruction_hash) == 64
        assert override["writer_input_mode"] == "writer_brief"
        assert "writer_behavior_mode" not in override
        assert "route_policy_version" not in override
    # Frozen parameters identical across all four groups
    frozen_keys = (
        "provider_id", "model_id", "prompt_version_id",
        "temperature", "top_p", "max_output_tokens", "timeout_seconds",
        "writer_input_mode",
    )
    for group in ("B", "C", "D"):
        override = runner.writer_override_for_group(group)
        for key in frozen_keys:
            assert override[key] == a[key], key
    # Policy metadata
    assert a["_policy_metadata"]["permission_policy"] == "CURRENT"
    assert a["_policy_metadata"]["stop_policy"] == "CURRENT"
    assert a["_policy_metadata"]["seed"] is None
    assert a["_policy_metadata"]["policy_version"] == "narrative-permission-stop-v1"
    d = runner.writer_override_for_group("D")
    assert d["_policy_metadata"]["permission_policy"] == "STRICT_LIMITED"
    assert d["_policy_metadata"]["stop_policy"] == "STRICT_STOP"


def test_replica_call_order_reproducible_and_stratified():
    runner = _runner_module()
    for case_id in ("AL-01", "NM-04"):
        orders = [runner.replica_call_order(case_id, replica) for replica in (1, 2, 3)]
        assert orders == [
            runner.replica_call_order(case_id, replica) for replica in (1, 2, 3)
        ]
        for order in orders:
            assert sorted(order) == sorted(runner.GROUPS)
        assert len({tuple(order) for order in orders}) > 1


def test_blind_token_deterministic_and_group_sensitive():
    runner = _runner_module()
    token = runner.make_blind_token("AL-01", "A", 1)
    assert token == runner.make_blind_token("AL-01", "A", 1)
    assert len(token) == 12
    assert token != runner.make_blind_token("AL-01", "B", 1)


def test_planner_hard_failure_aborts_entire_run():
    runner = _runner_module()
    assert runner.planner_error_is_fatal("PLANNER_OUTPUT_CONTRACT_INVALID") is True
    assert runner.planner_error_is_fatal("LLM_ERROR") is True
    assert runner.planner_error_is_fatal(None) is False
    assert runner.export_allowed("aborted") is False
    assert runner.export_allowed("completed") is True


def test_scene_coverage_not_single_mechanism():
    runner = _runner_module()
    categories = {case[1] for case in runner.SCENES}
    # Must not be eight identical campus object-grab scenes
    assert len(categories) >= 3
