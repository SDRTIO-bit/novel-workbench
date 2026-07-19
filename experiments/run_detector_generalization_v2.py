"""Run DETECTOR_GENERALIZATION_V2 with C-only narrative behaviour guidance."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
from pathlib import Path


_V1_PATH = Path(__file__).with_name("run_detector_generalization_v1.py")
_SPEC = importlib.util.spec_from_file_location("detector_generalization_v1_shared", _V1_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load shared runner: {_V1_PATH}")
_v1 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_v1)

EXPERIMENT = "DETECTOR_GENERALIZATION_V2"
DEFAULT_ROOT = _v1.REPO_ROOT / "__evaluation" / "detector_generalization_v2"
DEFAULT_DATABASE = _v1.REPO_ROOT / "__evaluation" / "detector_generalization_v2.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case-start", type=int, default=0)
    parser.add_argument("--model-id", default=_v1.FROZEN["model_id"])
    args = parser.parse_args()

    _v1.FROZEN["model_id"] = args.model_id
    _v1.FROZEN["planner_max_output_tokens"] = _v1.planner_output_cap(args.model_id)
    asyncio.run(_v1.run(
        args.root,
        args.database,
        args.dry_run,
        args.case_start,
        experiment=EXPERIMENT,
        writer_behavior_mode="narrative_behaviour_v1",
    ))


if __name__ == "__main__":
    main()

