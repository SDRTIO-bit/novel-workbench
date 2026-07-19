"""Filesystem boundary and schema validation for Evaluation MCP."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CASE_ID_PATTERN = re.compile(r"^CASE-[0-9]{3}$")
BLIND_FIELDS = {"case_id", "scene_brief", "text_a", "text_b"}
COMPARISON_VALUES = {"A", "B", "tie"}
CONTRACT_VALUES = {"present", "partial", "missing", "contradicted"}
CONTRACT_FIELDS = (
    "visible_trigger",
    "rejected_alternative",
    "character_choice",
    "cost_or_commitment",
    "immediate_consequence",
    "next_constraint",
    "stop_state",
    "must_not_append",
)


class EvaluationValidationError(ValueError):
    """Raised when an MCP request would violate the evaluation boundary."""


class EvaluationStore:
    """Access frozen evidence while permitting result files only under results/."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def list_evaluation_cases(self) -> list[dict[str, Any]]:
        manifest = self._read_json(self.root / "cases_manifest.json")
        cases = manifest.get("cases", [])
        if not isinstance(cases, list):
            raise EvaluationValidationError("cases_manifest.json cases must be a list")
        return cases

    def get_blind_pair(self, case_id: str) -> dict[str, str]:
        payload = self._read_case_json(case_id, "blind_pair.json")
        missing = BLIND_FIELDS.difference(payload)
        if missing:
            raise EvaluationValidationError(f"blind_pair missing fields: {sorted(missing)}")
        result = {field: payload[field] for field in BLIND_FIELDS}
        if result["case_id"] != case_id:
            raise EvaluationValidationError("blind_pair case_id does not match requested case_id")
        if not all(isinstance(value, str) for value in result.values()):
            raise EvaluationValidationError("blind_pair values must be strings")
        return result

    def get_planner_contract(self, case_id: str) -> dict[str, Any]:
        return self._read_case_json(case_id, "planner_contract.json")

    def get_pipeline_evidence(self, case_id: str) -> dict[str, Any]:
        return self._read_case_json(case_id, "pipeline_evidence.json")

    def save_evaluation_result(self, case_id: str, result: dict[str, Any]) -> dict[str, Any]:
        self._validate_case_id(case_id)
        self._validate_result(case_id, result)
        results_dir = self._under_root(self.root / "results")
        results_dir.mkdir(parents=True, exist_ok=True)
        destination = self._under_root(results_dir / f"{case_id}.json")
        destination.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return {"case_id": case_id, "saved_to": f"results/{case_id}.json"}

    def get_evaluation_summary(self) -> dict[str, Any]:
        cases = self.list_evaluation_cases()
        results: list[dict[str, Any]] = []
        for case in cases:
            case_id = case.get("case_id")
            if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
                continue
            result_path = self._under_root(self.root / "results" / f"{case_id}.json")
            if result_path.is_file():
                results.append(self._read_json(result_path))
        return {
            "case_count": len(cases),
            "completed_evaluations": len(results),
            "pending_case_ids": [
                case["case_id"] for case in cases
                if isinstance(case.get("case_id"), str)
                and not (self.root / "results" / f"{case['case_id']}.json").is_file()
            ],
            "results": results,
        }

    def _read_case_json(self, case_id: str, filename: str) -> dict[str, Any]:
        self._validate_case_id(case_id)
        return self._read_json(self._under_root(self.root / "cases" / case_id / filename))

    def _validate_case_id(self, case_id: str) -> None:
        if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
            raise EvaluationValidationError("case_id must match CASE-001 through CASE-999")

    def _under_root(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise EvaluationValidationError("path escapes __evaluation root") from exc
        return resolved

    def _read_json(self, path: Path) -> dict[str, Any]:
        safe_path = self._under_root(path)
        try:
            payload = json.loads(safe_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise EvaluationValidationError(f"evaluation evidence not found: {safe_path.name}") from exc
        except json.JSONDecodeError as exc:
            raise EvaluationValidationError(f"invalid JSON in {safe_path.name}") from exc
        if not isinstance(payload, dict):
            raise EvaluationValidationError(f"{safe_path.name} must contain a JSON object")
        return payload

    def _validate_result(self, case_id: str, result: dict[str, Any]) -> None:
        if not isinstance(result, dict) or result.get("case_id") != case_id:
            raise EvaluationValidationError("result case_id must match requested case_id")
        blind = result.get("blind_pass")
        if not isinstance(blind, dict):
            raise EvaluationValidationError("blind_pass must be an object")
        for field in (
            "preferred", "limited_information", "concrete_problem",
            "choice_and_consequence", "ending_restraint", "prose_naturalness",
        ):
            if blind.get(field) not in COMPARISON_VALUES:
                raise EvaluationValidationError(f"blind_pass.{field} must be A, B, or tie")
        if not isinstance(blind.get("evidence"), list) or not all(
            isinstance(item, str) for item in blind["evidence"]
        ):
            raise EvaluationValidationError("blind_pass.evidence must be a string list")

        contract = result.get("contract_pass")
        if not isinstance(contract, dict):
            raise EvaluationValidationError("contract_pass must be an object")
        for text_key in ("text_a", "text_b"):
            audit = contract.get(text_key)
            if not isinstance(audit, dict):
                raise EvaluationValidationError(f"contract_pass.{text_key} must be an object")
            for field in CONTRACT_FIELDS:
                if audit.get(field) not in CONTRACT_VALUES:
                    raise EvaluationValidationError(
                        f"contract_pass.{text_key}.{field} must be a contract status"
                    )

        pipeline = result.get("pipeline_pass")
        if not isinstance(pipeline, dict):
            raise EvaluationValidationError("pipeline_pass must be an object")
        for field in (
            "critic_diagnosis_correct", "reviser_fixed_confirmed_issues",
            "reviser_added_new_facts", "judge_local_choices_supported",
            "final_regressed_from_writer",
        ):
            if not isinstance(pipeline.get(field), bool):
                raise EvaluationValidationError(f"pipeline_pass.{field} must be boolean")
        if not isinstance(pipeline.get("evidence"), list) or not all(
            isinstance(item, str) for item in pipeline["evidence"]
        ):
            raise EvaluationValidationError("pipeline_pass.evidence must be a string list")

        confidence = result.get("confidence")
        if not isinstance(confidence, (float, int)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise EvaluationValidationError("confidence must be a number from 0 to 1")
        if not isinstance(result.get("notes"), str):
            raise EvaluationValidationError("notes must be a string")
