import importlib.util
from pathlib import Path


def _runner_module():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "detector_generalization_runner",
        root / "experiments" / "run_detector_generalization_v1.py",
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
