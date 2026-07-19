"""Execute the frozen WRITER_BRIEF_AB_TEST_V1 experiment.

The caller supplies an isolated copy of the evaluation database.  This runner
never calls Planner, Critic, Reviser, Judge, or TGbreak, and it never selects a
new Writer candidate.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(API_ROOT))

from app.models.generation import GenerationCandidate
from app.services.context_service import ContextService
from app.services.generation_service import GenerationService
from app.services.writer_brief import MAX_ACTIVE_PROJECT_FACTS, validate_writer_brief
from scripts.run_generalization_batch import _json
from tools.novel_eval_mcp.export import blind_mapping, build_blind_pair, write_json


SEED = 20260719
CASES = ("CASE-001", "CASE-002", "CASE-003", "CASE-004")
REQUIRED_BRIEF_FIELDS = (
    "opening_fact", "known_facts", "unknown_facts", "current_assumption",
    "assumption_basis", "next_action", "immediate_consequence", "next_constraint",
    "active_project_facts", "stop_fact", "must_not_append",
)


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def _source_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get_path(value: Any, path: tuple[Any, ...]) -> Any:
    current = value
    for part in path:
        if isinstance(part, int):
            if not isinstance(current, list) or len(current) <= part:
                return None
        elif not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _contains_key(value: Any, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return any(key in forbidden or _contains_key(item, forbidden) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, forbidden) for item in value)
    return False


def _estimate_tokens(text: str) -> int:
    # Stable offline estimate for audit comparison; provider usage remains the
    # authoritative count when a Writer call is permitted.
    return max(1, (len(text) + 3) // 4)


def _writer_record(candidate: GenerationCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "attempt_number": candidate.attempt_number,
        "planner_candidate_id": None,
        "prompt_version_id": candidate.prompt_version_id,
        "provider_id": candidate.provider_id,
        "model_id": candidate.model_id,
        "parameters": _json(candidate.parameters_json),
        "raw_response": candidate.raw_response,
        "text_output": candidate.text_output,
        "input_tokens": candidate.input_tokens,
        "output_tokens": candidate.output_tokens,
        "finish_reason": candidate.finish_reason,
        "latency_ms": candidate.latency_ms,
        "error_code": candidate.error_code,
        "error_message": candidate.error_message,
        "is_selected": candidate.is_selected,
    }


def _audit(brief: dict[str, Any], prompt: str, planner: dict[str, Any]) -> dict[str, Any]:
    brief_text = json.dumps(brief, ensure_ascii=False, indent=2)
    errors: list[str] = []
    if brief_text == json.dumps(planner, ensure_ascii=False, indent=2):
        errors.append("WRITER_BRIEF_FULL_PLANNER_JSON")
    forbidden = {
        "reader_must_infer", "narrator_must_not_state", "chapter_contract_check",
        "critic", "judge",
    }
    if _contains_key(brief, forbidden):
        errors.append("WRITER_BRIEF_FORBIDDEN_FIELD")
    if "unknown_information" in brief:
        errors.append("WRITER_BRIEF_NONCANONICAL_UNKNOWN_FIELD")
    for name in REQUIRED_BRIEF_FIELDS:
        if name not in brief:
            errors.append(f"WRITER_BRIEF_REQUIRED_FIELD_MISSING:{name}")
    try:
        validate_writer_brief(brief)
    except ValueError as exc:
        errors.append(f"WRITER_BRIEF_CONTRACT_INVALID:{exc}")
    brief_marker = "## Writer Brief（只含现场行动信息）"
    if not prompt.rstrip().endswith("并在 stop_state 成立处停止。") or brief_marker not in prompt:
        errors.append("WRITER_BRIEF_NOT_AT_PROMPT_END")
    return {
        "passed": not errors,
        "errors": errors,
        "brief_characters": len(brief_text),
        "brief_estimated_tokens": _estimate_tokens(brief_text),
        "prompt_characters": len(prompt),
        "prompt_estimated_tokens": _estimate_tokens(prompt),
        "active_project_facts_count": len(brief.get("active_project_facts", [])),
        "active_project_facts_cap": MAX_ACTIVE_PROJECT_FACTS,
    }


async def run(database: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    existing_executions = [
        root / "cases" / case_id / "execution.json" for case_id in CASES
    ]
    if any(path.is_file() for path in existing_executions):
        raise RuntimeError(
            "WRITER_BRIEF_AB_TEST_V1 evidence already exists; refusing to rerun a Writer stage"
        )
    source_compiler = API_ROOT / "app" / "services" / "writer_brief.py"
    source_generation = API_ROOT / "app" / "services" / "generation_service.py"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    manifest_cases: list[dict[str, Any]] = []
    try:
        async with factory() as session:
            generation = GenerationService(session)
            context = ContextService(session)
            for case_id in CASES:
                source = json.loads((REPO_ROOT / "__evaluation" / "cases" / case_id / "pipeline_evidence.json").read_text(encoding="utf-8"))
                case_dir = root / "cases" / case_id
                write_json(
                    case_dir / "planner_contract.json",
                    json.loads(
                        (REPO_ROOT / "__evaluation" / "cases" / case_id / "planner_contract.json").read_text(encoding="utf-8")
                    ),
                )
                writer_step = source["stages"]["writer"]
                planner_step = source["stages"]["planner"]
                baseline_writer = next(item for item in writer_step["candidates"] if item["candidate_id"] == writer_step["selected_candidate_id"])
                planner = next(item for item in planner_step["candidates"] if item["candidate_id"] == planner_step["selected_candidate_id"])
                override = {
                    "provider_id": baseline_writer["provider_id"],
                    "model_id": baseline_writer["model_id"],
                    "prompt_version_id": baseline_writer["prompt_version_id"],
                    **{key: baseline_writer["parameters"][key] for key in (
                        "temperature", "top_p", "max_output_tokens", "timeout_seconds"
                    ) if key in (baseline_writer["parameters"] or {})},
                }
                run = await generation.get_run(source["run_id"])
                request = await generation._build_context_request(run, "writer", override)
                rendered = await context.assemble(request)
                generation._append_writer_brief("writer", "builtin", rendered)
                brief = request.writer_brief or {}
                planner_output = planner["parsed_output"] or {}
                audit = _audit(brief, rendered["rendered_user_prompt"], planner_output)
                write_json(case_dir / "writer_brief.json", {
                    "case_id": case_id,
                    "planner_candidate_id": planner["candidate_id"],
                    "writer_brief": brief,
                    "audit": audit,
                })
                (case_dir / "rendered_prompt.txt").write_text(rendered["rendered_user_prompt"], encoding="utf-8")
                record: dict[str, Any] = {
                    "case_id": case_id,
                    "planner_candidate_id": planner["candidate_id"],
                    "baseline_writer_candidate_id": baseline_writer["candidate_id"],
                    "baseline_writer_prompt_version_id": baseline_writer["prompt_version_id"],
                    "provider_id": baseline_writer["provider_id"],
                    "model_id": baseline_writer["model_id"],
                    "parameters": baseline_writer["parameters"],
                    "status": "stopped_preflight" if not audit["passed"] else "ready",
                    "preflight": audit,
                }
                if audit["passed"]:
                    candidate = await generation.execute_stage(run.id, "writer", override)
                    await session.commit()
                    record["status"] = "writer_failed" if candidate.error_code else "completed"
                    record["vnext_writer"] = _writer_record(candidate)
                    record["vnext_writer"]["planner_candidate_id"] = planner["candidate_id"]
                    write_json(case_dir / "vnext_writer.json", record["vnext_writer"])
                    if not candidate.error_code:
                        write_json(case_dir / "blind_pair.json", build_blind_pair(
                            case_id=case_id,
                            scene_brief=json.loads((REPO_ROOT / "__evaluation" / "cases" / case_id / "blind_pair.json").read_text(encoding="utf-8"))["scene_brief"],
                            writer_text=baseline_writer["text_output"] or baseline_writer["raw_response"],
                            final_text=candidate.text_output or candidate.raw_response,
                            seed=SEED,
                        ))
                        write_json(case_dir / "source_mapping.private.json", {
                            "blind_mapping": blind_mapping(
                                case_id=case_id,
                                writer_candidate_id=baseline_writer["candidate_id"],
                                final_source="writer_brief_vnext",
                                seed=SEED,
                            ),
                            "vnext_writer_candidate_id": candidate.id,
                        })
                write_json(case_dir / "execution.json", record)
                manifest_cases.append(record)
    finally:
        await engine.dispose()

    write_json(root / "baseline_manifest.json", {
        "batch": "WRITER_BRIEF_AB_TEST_V1",
        "git_commit": _git_commit(),
        "baseline_tag": "evaluation-baseline-v1",
        "baseline_commit": "c99fde116c0d01ff34596cbec3d5ae315caf80a8",
        "writer_brief_compiler": {
            "path": "apps/api/app/services/writer_brief.py",
            "sha256": _source_sha(source_compiler),
        },
        "generation_service": {
            "path": "apps/api/app/services/generation_service.py",
            "sha256": _source_sha(source_generation),
        },
        "isolated_database": str(database),
        "cases": manifest_cases,
        "rule": "No Planner/Critic/Reviser/Judge/TGbreak calls; at most one vNext Writer call per case; no candidate selection.",
    })
    write_json(root / "cases_manifest.json", {
        "batch": "WRITER_BRIEF_AB_TEST_V1",
        "cases": [
            {
                "case_id": item["case_id"],
                "status": item["status"],
                "scene_brief": json.loads(
                    (REPO_ROOT / "__evaluation" / "cases" / item["case_id"] / "blind_pair.json").read_text(encoding="utf-8")
                )["scene_brief"],
            }
            for item in manifest_cases
        ],
    })

    stopped = [item["case_id"] for item in manifest_cases if item["status"] == "stopped_preflight"]
    case_rows = "\n".join(
        "| {case_id} | {planner} | {baseline} | — | {brief_chars} | — | — | {status} |".format(
            case_id=item["case_id"],
            planner=item["planner_candidate_id"],
            baseline=item["baseline_writer_candidate_id"],
            brief_chars=item["preflight"]["brief_characters"],
            status=item["status"],
        )
        for item in manifest_cases
    )
    preflight_rows = "\n".join(
        "| {case_id} | {errors} |".format(
            case_id=item["case_id"],
            errors="; ".join(item["preflight"]["errors"]),
        )
        for item in manifest_cases
    )
    (root / "EVALUATION_REPORT.md").write_text(
        "# WRITER_BRIEF_AB_TEST_V1 Evaluation Report\n\n"
        "## Execution\n\n"
        f"Cases stopped before model invocation: {', '.join(stopped) or 'none'}.\n\n"
        "The first precheck used non-canonical unknown_information and treated conditional assumption values as mandatory non-empty fields. This rerun uses the canonical WriterBrief validator shared with the compiler. No Planner, Critic, Reviser, Judge, or TGbreak call is permitted.\n\n"
        "| Case | Planner Candidate | Baseline Writer Candidate | vNext Writer Candidate | Brief characters | Writer tokens / latency | Anonymous mapping | Status |\n"
        "| --- | --- | --- | --- | ---: | --- | --- | --- |\n"
        f"{case_rows}\n\n"
        "No anonymous mapping exists because a blind pair is only valid after both permitted Writer texts exist.\n\n"
        "## Preflight failures\n\n"
        "| Case | Failed condition |\n| --- | --- |\n"
        f"{preflight_rows}\n\n"
        "## Overall decision\n\n"
        "**NOT PASSED — engineering preflight failed.** The primary, blind, and safety thresholds cannot be evaluated because the required WriterBrief input contract was not satisfied.\n\n"
        "## Evidence supports\n\n"
        "The current implementation deterministically omits full Planner JSON and keeps the WriterBrief at the end of the Writer prompt. It does not yet provide all fields required by this frozen A/B protocol.\n\n"
        "## Evidence does not support\n\n"
        "It does not support either adopting or rejecting WriterBrief as the default based on prose quality or Planner-contract performance: no permitted Writer comparison was run.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--evaluation-root", default=REPO_ROOT / "__evaluation" / "writer_brief_v1", type=Path)
    args = parser.parse_args()
    asyncio.run(run(args.database.resolve(), args.evaluation_root.resolve()))
