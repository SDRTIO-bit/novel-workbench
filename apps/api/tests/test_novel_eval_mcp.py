import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tools.novel_eval_mcp.storage import EvaluationStore, EvaluationValidationError
from tools.novel_eval_mcp.export import build_blind_pair


def _write_case(root: Path, case_id: str = "CASE-002") -> None:
    case_dir = root / "cases" / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "blind_pair.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "scene_brief": "公开点名前，班长看见同学校服扣错。",
                "text_a": "甲文",
                "text_b": "乙文",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (case_dir / "planner_contract.json").write_text("{}", encoding="utf-8")
    (case_dir / "pipeline_evidence.json").write_text("{}", encoding="utf-8")
    (root / "cases_manifest.json").write_text(
        json.dumps({"cases": [{"case_id": case_id, "status": "completed"}]}),
        encoding="utf-8",
    )


def _valid_result(case_id: str = "CASE-002") -> dict:
    complete_audit = {
        "visible_trigger": "present",
        "rejected_alternative": "present",
        "character_choice": "present",
        "cost_or_commitment": "present",
        "immediate_consequence": "present",
        "next_constraint": "present",
        "stop_state": "present",
        "must_not_append": "present",
    }
    return {
        "case_id": case_id,
        "blind_pass": {
            "preferred": "A",
            "limited_information": "A",
            "concrete_problem": "B",
            "choice_and_consequence": "A",
            "ending_restraint": "tie",
            "prose_naturalness": "A",
            "evidence": ["‘甲文’呈现具体动作。"],
        },
        "contract_pass": {
            "text_a": complete_audit,
            "text_b": {**complete_audit, "visible_trigger": "partial"},
        },
        "pipeline_pass": {
            "critic_diagnosis_correct": True,
            "reviser_fixed_confirmed_issues": True,
            "reviser_added_new_facts": False,
            "judge_local_choices_supported": True,
            "final_regressed_from_writer": False,
            "evidence": [],
        },
        "confidence": 0.8,
        "notes": "可观察证据充分。",
    }


def test_blind_pair_is_limited_to_anonymous_reader_material(tmp_path: Path):
    _write_case(tmp_path)
    store = EvaluationStore(tmp_path)

    result = store.get_blind_pair("CASE-002")

    assert result == {
        "case_id": "CASE-002",
        "scene_brief": "公开点名前，班长看见同学校服扣错。",
        "text_a": "甲文",
        "text_b": "乙文",
    }


@pytest.mark.parametrize("case_id", ["../CASE-002", "CASE-002/../../baseline_manifest", ""])
def test_case_paths_cannot_escape_evaluation_root(tmp_path: Path, case_id: str):
    _write_case(tmp_path)
    store = EvaluationStore(tmp_path)

    with pytest.raises(EvaluationValidationError, match="case_id"):
        store.get_blind_pair(case_id)


def test_save_result_validates_schema_and_writes_only_results(tmp_path: Path):
    _write_case(tmp_path)
    store = EvaluationStore(tmp_path)

    saved = store.save_evaluation_result("CASE-002", _valid_result())

    assert saved["case_id"] == "CASE-002"
    assert (tmp_path / "results" / "CASE-002.json").exists()
    assert not (tmp_path / "cases" / "CASE-002" / "result.json").exists()

    invalid = _valid_result()
    invalid["blind_pass"]["preferred"] = "writer"
    with pytest.raises(EvaluationValidationError, match="preferred"):
        store.save_evaluation_result("CASE-002", invalid)


def test_pipeline_evidence_is_available_only_after_explicit_call(tmp_path: Path):
    _write_case(tmp_path)
    store = EvaluationStore(tmp_path)

    blind = store.get_blind_pair("CASE-002")
    evidence = store.get_pipeline_evidence("CASE-002")

    assert "pipeline_evidence" not in blind
    assert evidence == {}


def test_blind_pair_uses_seeded_order_and_never_serializes_source_metadata():
    first = build_blind_pair(
        case_id="CASE-003",
        scene_brief="只听到半段电话后作出选择。",
        writer_text="原稿",
        final_text="最终稿",
        seed=20260719,
    )
    second = build_blind_pair(
        case_id="CASE-003",
        scene_brief="只听到半段电话后作出选择。",
        writer_text="原稿",
        final_text="最终稿",
        seed=20260719,
    )

    assert first == second
    assert set(first) == {"case_id", "scene_brief", "text_a", "text_b"}
    assert {first["text_a"], first["text_b"]} == {"原稿", "最终稿"}
