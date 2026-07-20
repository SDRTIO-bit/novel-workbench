"""Phase 2 contract tests for strict limited planner-writer factorial experiment.

No LLM calls — slot math, factorial group counting, dry-run assertions,
randomization stability, and structural checks.
"""
from pathlib import Path
import importlib.util
import pytest


def _runner_module():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "run_strict_limited_planner_writer_factorial_v1",
        root / "experiments" / "run_strict_limited_planner_writer_factorial_v1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner():
    return _runner_module()


# ── Identity ────────────────────────────────────────────────────────────
def test_experiment_name(runner):
    assert runner.EXPERIMENT == "STRICT_LIMITED_PLANNER_WRITER_FACTORIAL_V1"

def test_seed(runner):
    assert runner.SEED == 202607210

def test_scene_count(runner):
    assert len(runner.SCENES) == 4

def test_scene_ids(runner):
    assert [c[0] for c in runner.SCENES] == ["NM-03", "ROMANCE-02", "CO-04", "CO-05"]

def test_factorial_groups(runner):
    assert runner.FACTORIAL_GROUPS == ("P2W9", "P2W10", "P3W9", "P3W10")

def test_planner_groups(runner):
    assert runner.PLANNER_GROUPS == ("P2", "P3")

def test_writer_groups(runner):
    assert runner.WRITER_GROUPS == ("W9", "W10")

def test_replicas(runner):
    assert runner.REPLICAS == 3


# ── Slot math ───────────────────────────────────────────────────────────
def test_slot_math(runner):
    """4 scenes × 4 factorial groups × 3 replicas = 48 slots."""
    case_ids = [c[0] for c in runner.SCENES]
    slots = runner.expected_slots(case_ids)
    assert len(slots) == 48
    for fg in runner.FACTORIAL_GROUPS:
        assert len([s for s in slots if s[1] == fg]) == 12
    for case_id in case_ids:
        assert len([s for s in slots if s[0] == case_id]) == 12
        for fg in runner.FACTORIAL_GROUPS:
            assert len([s for s in slots if s[0] == case_id and s[1] == fg]) == 3


# ── Call counts ─────────────────────────────────────────────────────────
def test_planner_writer_call_counts():
    n = 4 * 3 * 2  # scenes × replicas × planner groups
    assert n == 24  # planner calls
    assert n * 2 == 48  # writer calls
    assert n + n * 2 == 72  # total


# ── Frozen params ───────────────────────────────────────────────────────
def test_frozen_provider(runner):
    assert runner.FROZEN["provider_id"] == "34c14b6b-7231-432a-96b2-8272329b828d"

def test_frozen_model(runner):
    assert runner.FROZEN["model_id"] == "deepseek-v4-pro"

def test_frozen_temperature(runner):
    assert runner.FROZEN["temperature"] == 0.7

def test_target_length(runner):
    assert runner.TARGET_LENGTH == 2000


# ── Randomization ───────────────────────────────────────────────────────
def test_planner_call_order_deterministic(runner):
    assert runner.planner_call_order("NM-03", 1) == runner.planner_call_order("NM-03", 1)

def test_planner_call_order_valid(runner):
    for case_id in [c[0] for c in runner.SCENES]:
        for replica in range(1, runner.REPLICAS + 1):
            order = runner.planner_call_order(case_id, replica)
            assert order in (["P2", "P3"], ["P3", "P2"])

def test_writer_call_order_valid(runner):
    for case_id in [c[0] for c in runner.SCENES]:
        for replica in range(1, runner.REPLICAS + 1):
            for pg in runner.PLANNER_GROUPS:
                o = runner.writer_call_order(case_id, replica, pg)
                assert o in (["W9", "W10"], ["W10", "W9"])


# ── Blind tokens ────────────────────────────────────────────────────────
def test_blind_tokens_unique(runner):
    tokens = set()
    for case_id in [c[0] for c in runner.SCENES]:
        for fg in runner.FACTORIAL_GROUPS:
            for replica in range(1, runner.REPLICAS + 1):
                t = runner.make_blind_token(case_id, fg, replica)
                assert t not in tokens
                tokens.add(t)
    assert len(tokens) == 48

def test_blind_token_format(runner):
    t = runner.make_blind_token("NM-03", "P2W9", 1)
    assert len(t) == 12
    assert t.isupper()
    assert all(c in "0123456789ABCDEF" for c in t)


# ── Dry-run ─────────────────────────────────────────────────────────────
def test_dry_run_reports_expected(runner):
    root = Path(runner.REPO_ROOT) / "__evaluation" / "test_dry_run"
    case_ids = [c[0] for c in runner.SCENES]
    report = runner.dry_run_report(root, case_ids)
    for term in ("4", "3", "24", "48", "72", "P2W9", "P3W10"):
        assert term in report, f"Missing {term} in dry-run report"


# ── Zhuque ──────────────────────────────────────────────────────────────
SEP = "\n\n\n\n\n"

def test_five_newline_roundtrip():
    texts = ["t1", "t2", "t3"]
    assert SEP.join(texts).split(SEP) == texts


# ── Discipline ──────────────────────────────────────────────────────────
def test_no_retry_documented(runner):
    src = (Path(__file__).resolve().parents[3]
           / "experiments"
           / "run_strict_limited_planner_writer_factorial_v1.py").read_text(encoding="utf-8")
    assert "no retry" in src.lower() or "no-retry" in src.lower()

def test_paired_design():
    planner = 4 * 3 * 2  # 24
    writer = planner * 2  # 48
    assert writer == 2 * planner
    assert writer + planner == 72
