"""Portable JSON package builders used by the frozen-batch runner."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


def build_blind_pair(
    *, case_id: str, scene_brief: str, writer_text: str, final_text: str, seed: int
) -> dict[str, str]:
    """Build the only reader-pass payload, with deterministic anonymous ordering."""
    texts = [("writer", writer_text), ("final", final_text)]
    random.Random(f"{seed}:{case_id}").shuffle(texts)
    return {
        "case_id": case_id,
        "scene_brief": scene_brief,
        "text_a": texts[0][1],
        "text_b": texts[1][1],
    }


def blind_mapping(
    *, case_id: str, writer_candidate_id: str | None, final_source: str, seed: int
) -> dict[str, Any]:
    sources = [("writer", writer_candidate_id), (final_source, None)]
    random.Random(f"{seed}:{case_id}").shuffle(sources)
    return {
        "text_a": {"source": sources[0][0], "candidate_id": sources[0][1]},
        "text_b": {"source": sources[1][0], "candidate_id": sources[1][1]},
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
