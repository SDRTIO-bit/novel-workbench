import importlib.util
from pathlib import Path


def _runner_module(filename="run_detector_generalization_v1.py"):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        f"detector_generalization_{filename}",
        root / "experiments" / filename,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_planner_has_its_own_non_truncating_output_cap():
    runner = _runner_module()

    assert runner.FROZEN["planner_max_output_tokens"] == 4096
    assert runner.FROZEN["max_output_tokens"] == 4000


def test_v4_pro_uses_the_known_non_truncating_planner_cap():
    runner = _runner_module()

    assert runner.planner_output_cap("deepseek-v4-pro") == 12288
    assert runner.planner_output_cap("deepseek-chat") == 4096


def test_v2_routes_behaviour_guidance_to_c_only():
    runner = _runner_module()

    assert "writer_behavior_mode" not in runner.writer_override_for_group(
        "A", "complete_planner"
    )
    assert "writer_behavior_mode" not in runner.writer_override_for_group(
        "B", "writer_brief"
    )
    assert runner.writer_override_for_group(
        "C", "narrative_behaviour_brief", "narrative_behaviour_v1"
    )["writer_behavior_mode"] == "narrative_behaviour_v1"


def test_v2_runner_is_separately_named():
    runner = _runner_module("run_detector_generalization_v2.py")

    assert runner.EXPERIMENT == "DETECTOR_GENERALIZATION_V2"
    assert runner.DEFAULT_ROOT.name == "detector_generalization_v2"
