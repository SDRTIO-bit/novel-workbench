"""Run the single authorized CASE-004 Judge contract supplement.

It reuses the frozen Planner/Writer/Critic/Reviser candidates from the original
CASE-004 run and records a new Judge attempt in a separate evidence directory.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(API_ROOT))

from app.services.generation_service import GenerationService
from scripts.run_generalization_batch import _candidate_record, _load_run
from tools.novel_eval_mcp.export import write_json


SUPPLEMENT_ID = "CASE-004-JUDGE-CONTRACT-FIX"


async def run(database: Path, run_id: str, evaluation_root: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            service = GenerationService(session)
            run = await _load_run(session, run_id)
            judge_step = next(step for step in run.steps if step.stage == "judge")
            previous = judge_step.candidates[-1]
            parameters = json.loads(previous.parameters_json or "{}")
            override = {
                key: parameters[key]
                for key in ("temperature", "top_p", "max_output_tokens", "timeout_seconds")
                if key in parameters
            }
            override.update({
                "provider_id": previous.provider_id,
                "model_id": previous.model_id,
                "prompt_version_id": previous.prompt_version_id,
            })
            candidate = await service.execute_stage(run_id, "judge", override)
            if candidate.error_code:
                await session.commit()
                raise RuntimeError(f"Judge supplement failed: {candidate.error_code}: {candidate.error_message}")
            await service.select_candidate(run_id, "judge", candidate.id)
            await session.commit()

            run = await _load_run(session, run_id)
            case_dir = evaluation_root / "supplemental" / SUPPLEMENT_ID
            records = {
                step.stage: {
                    "status": step.status,
                    "selected_candidate_id": step.selected_candidate_id,
                    "candidates": [_candidate_record(item) for item in step.candidates],
                }
                for step in run.steps
            }
            write_json(case_dir / "pipeline_evidence.json", {
                "supplement_id": SUPPLEMENT_ID,
                "original_case_id": "CASE-004",
                "run_id": run.id,
                "scope": "Judge only; original frozen evidence is not overwritten.",
                "stages": records,
            })
            write_json(case_dir / "manifest.json", {
                "supplement_id": SUPPLEMENT_ID,
                "original_case_id": "CASE-004",
                "stage_calls": {"judge": 1},
                "baseline_judge_candidate_id": previous.id,
                "supplement_judge_candidate_id": candidate.id,
                "prompt_version_id": candidate.prompt_version_id,
                "provider_id": candidate.provider_id,
                "model_id": candidate.model_id,
                "result": "completed",
            })
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--evaluation-root", type=Path, default=REPO_ROOT / "__evaluation")
    args = parser.parse_args()
    asyncio.run(run(args.database.resolve(), args.run_id, args.evaluation_root.resolve()))
