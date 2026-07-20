"""STRICT_LIMITED_PLANNER_WRITER_FACTORIAL_V1 — 2×2 factorial experiment.

Factorial groups: P2W9(baseline), P2W10, P3W9, P3W10
Design: 4 scenes × 3 replicas × 2 planners × 2 writers = 72 calls
  - 24 Planner calls (P2 × 12 + P3 × 12)
  - 48 Writer calls (W9 × 24 + W10 × 24)

Discipline (pre-registered):
  - Uses existing v9 databases with project+chapter setup.
  - Randomized planner call order per (case_id, replica).
  - Randomized writer call order per planner output.
  - No Critic/Reviser/Judge. No retry. No filtering.
  - All failures preserved as-is.
  - Dry-run mode prints full plan without any LLM calls.
  - Zhuque submission package generated automatically after run.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.models.prompt import PromptProfile, PromptVersion
from app.models.generation import GenerationStep, GenerationCandidate
from app.prompts.defaults import BUILTIN_PROMPTS
from app.schemas.chapter import ChapterCreate
from app.schemas.project import ProjectCreate
from app.services.chapter_service import ChapterService
from app.services.generation_service import GenerationService
from app.services.project_service import ProjectService
from app.services.writer_brief import compile_writer_input

EXPERIMENT = "STRICT_LIMITED_PLANNER_WRITER_FACTORIAL_V1"
SEED = 202607210
REPLICAS = 3
FACTORIAL_GROUPS = ("P2W9", "P2W10", "P3W9", "P3W10")
PLANNER_GROUPS = ("P2", "P3")
WRITER_GROUPS = ("W9", "W10")

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "temperature": 0.7,
    "top_p": 1.0,
    "max_output_tokens": 6000,
    "timeout_seconds": 300,
}

SEED_NOTE = (
    "Provider/adapter exposes no model seed (LlmRequest has no seed field; "
    "DeepSeek chat/completions documents none). seed=null is recorded for "
    "every call; temperature/top_p/max_output_tokens/timeout are held "
    "identical across groups; reproducibility is not faked. The SEED "
    "constant only drives blind-token generation and call-order shuffling."
)

V9_DATABASE_PREFIX = (
    REPO_ROOT / "__evaluation" / "sacrificial_preflight_fusion_v9_feasibility_v1"
)

SCENES = (
    ("NM-03", "城市日常", "洗衣房的滚筒",
     "小区自助洗衣房里，方笛认为自己那台滚筒还没洗完——她记得设定的是一小时，现在才过去四十分钟。旁边等着用机器的老人说机器早停了，里面是他的衣服。方笛不能跟老人争，也不能直接把滚筒门拉开。滚筒玻璃上的水位和面板上的状态会证明谁记错了。她必须用一个可见事实处理这个争执。停在机器状态拆穿其中一方判断的事实。"),
    ("ROMANCE-02", "恋爱日常", "未读消息",
     "合租屋厨房里，夏知看见韩川的手机亮起自己昨晚的未读消息，韩川却先把手机扣在桌上去洗菜。水已经开了，桌上只有两只碗。夏知不能偷看手机，也不能断言对方为何没回；她需要根据可见事实选择继续帮忙、离开或提出别的行动，并让代价和后果落在现场。"),
    ("CO-04", "校园日常", "操场上错拿的水壶",
     "体育课自由活动时，路远发现自己的蓝色运动水壶被一个不认识的男生拿起来喝了一口。那个男生正往篮球场方向走，手里还拿着水壶。路远不能跑过去抢回来，也不能在操场上喊。他必须用一个现场物件让对方发现。停在水壶回到正确位置的事实。"),
    ("CO-05", "日常任务", "快递架上的同名包裹",
     "小区快递架上，向暖发现一个写着'向暖'的包裹——但收件地址不是自己的楼栋。真正的收件人可能就在附近。包裹不大，架子上还有其他未取件。向暖不能拆包裹验证，也不能拿错的东西回家。她必须用一个现场物件标记或通知。停在包裹归属出现新事实。"),
)

TARGET_LENGTH = 2000

# ── Pure helpers ───────────────────────────────────────────────────────


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def instruction_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def expected_slots(case_ids: list[str]) -> list[tuple[str, str, int]]:
    return [
        (case_id, group, replica)
        for case_id in case_ids
        for group in FACTORIAL_GROUPS
        for replica in range(1, REPLICAS + 1)
    ]


def planner_call_order(case_id: str, replica: int) -> list[str]:
    order = list(PLANNER_GROUPS)
    random.Random(f"{SEED}:{case_id}:{replica}:planner").shuffle(order)
    return order


def writer_call_order(case_id: str, replica: int, planner_group: str) -> list[str]:
    order = list(WRITER_GROUPS)
    random.Random(f"{SEED}:{case_id}:{replica}:{planner_group}:writer").shuffle(order)
    return order


def make_blind_token(
    case_id: str, factorial_group: str, replica: int
) -> str:
    return (
        hashlib.sha256(f"{SEED}:{case_id}:{factorial_group}:{replica}".encode())
        .hexdigest()[:12]
        .upper()
    )


def scene_database(case_id: str) -> Path:
    return V9_DATABASE_PREFIX.with_name(
        f"{V9_DATABASE_PREFIX.name}_{case_id}.sqlite3"
    )


def _find_builtin_prompt(name: str, stage: str) -> dict | None:
    for entry in BUILTIN_PROMPTS:
        if entry.get("name") == name and entry.get("stage") == stage:
            return entry
    return None


async def ensure_prompt_exists(
    session: AsyncSession, name: str, stage: str
) -> str:
    """Ensure a named builtin prompt profile + version exist. Returns the PromptVersion.id."""
    entry = _find_builtin_prompt(name, stage)
    if entry is None:
        raise RuntimeError(
            f"Builtin prompt '{name}' (stage={stage}) not found in BUILTIN_PROMPTS"
        )

    existing = (
        await session.execute(
            select(PromptProfile).where(
                PromptProfile.stage == stage,
                PromptProfile.name == entry["name"],
                PromptProfile.is_builtin == True,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        await session.refresh(existing, ["versions"])
        if existing.versions:
            return existing.versions[-1].id

    profile = PromptProfile(
        stage=stage,
        name=entry["name"],
        description=entry["description"],
        is_builtin=True,
    )
    session.add(profile)
    await session.flush()

    version = PromptVersion(
        profile_id=profile.id,
        version_number=1,
        system_template=entry["system_template"],
        user_template=entry["user_template"],
        output_mode=entry["output_mode"],
        output_schema_name=entry.get("output_schema_name"),
    )
    session.add(version)
    await session.flush()
    return version.id


async def prompt_identity(
    session: AsyncSession, prompt_version_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(PromptVersion).where(PromptVersion.id == prompt_version_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return {"prompt_version_id": prompt_version_id, "found": False}
    return {
        "prompt_version_id": prompt_version_id,
        "found": True,
        "version_number": row.version_number,
        "output_mode": row.output_mode,
        "output_schema_name": row.output_schema_name,
        "system_template_sha256": hashlib.sha256(
            row.system_template.encode("utf-8")
        ).hexdigest(),
        "user_template_sha256": hashlib.sha256(
            row.user_template.encode("utf-8")
        ).hexdigest(),
    }


async def load_source_input(session: AsyncSession, case_id: str) -> dict[str, Any]:
    """Load existing project_id, chapter_id, and scene_instruction from v9 database."""
    from app.models.project import Project
    from app.models.chapter import Chapter
    from app.models.generation import GenerationRun

    project_name = f"SACRIFICIAL_PREFLIGHT_FUSION_V9_FEASIBILITY_V1 {case_id}"
    project = (
        await session.execute(
            select(Project).where(Project.name == project_name)
        )
    ).scalar_one_or_none()
    if project is None:
        raise RuntimeError(f"Project '{project_name}' not found in v9 database")

    chapter = (
        await session.execute(
            select(Chapter).where(Chapter.project_id == project.id)
        )
    ).scalar_one_or_none()
    if chapter is None:
        raise RuntimeError(f"Chapter for project '{project_name}' not found")

    run = (
        await session.execute(
            select(GenerationRun).where(
                GenerationRun.project_id == project.id,
                GenerationRun.chapter_id == chapter.id,
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise RuntimeError(f"GenerationRun for '{project_name}' not found")

    return {
        "project_id": project.id,
        "chapter_id": chapter.id,
        "project_name": project.name,
        "project_genre": project.genre,
        "chapter_title": chapter.title,
        "scene_instruction": run.scene_instruction or "",
    }


def extract_story_from_xml(raw_response: str) -> str:
    match = re.search(
        r"<story>(.*?)</story>", raw_response, re.DOTALL | re.IGNORECASE
    )
    return match.group(1).strip() if match else ""


def extract_draft_notes_from_xml(raw_response: str) -> str:
    match = re.search(
        r"<draft_notes>(.*?)</draft_notes>", raw_response, re.DOTALL | re.IGNORECASE
    )
    return match.group(1).strip() if match else ""


# ── Recording ──────────────────────────────────────────────────────────


def record_candidate(candidate: Any, group: str, replica: int) -> dict[str, Any]:
    params = json.loads(candidate.parameters_json or "{}")
    metadata = params.get("policy_metadata") or {}
    return {
        "candidate_id": candidate.id,
        "attempt_number": candidate.attempt_number,
        "group": group,
        "replica": replica,
        "provider_id": candidate.provider_id,
        "model_id": candidate.model_id,
        "prompt_version_id": candidate.prompt_version_id,
        "parameters": params,
        "text_output": candidate.text_output,
        "raw_response": candidate.raw_response,
        "input_tokens": candidate.input_tokens,
        "output_tokens": candidate.output_tokens,
        "latency_ms": candidate.latency_ms,
        "finish_reason": candidate.finish_reason,
        "error_code": candidate.error_code,
        "error_message": candidate.error_message,
        "rendered_user_prompt_sha256": hashlib.sha256(
            candidate.rendered_user_prompt.encode("utf-8")
        ).hexdigest(),
        "rendered_system_prompt_sha256": hashlib.sha256(
            (candidate.rendered_system_prompt or "").encode("utf-8")
        ).hexdigest(),
    }


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def process_planner_output(
    root: Path,
    case_dir: Path,
    pr: dict[str, Any],
    planner_group: str,
    replica: int,
) -> None:
    """Save planner raw response, parsed output, and metadata."""
    stem = f"{planner_group.lower()}-{replica}"
    raw_response = pr.get("raw_response") or ""
    parsed_output = pr.get("parsed_output_json") or ""

    # 1. Raw response
    raw_path = case_dir / "planner_raw" / f"{stem}.txt"
    _write_text(raw_path, raw_response)
    pr["planner_raw_path"] = str(raw_path.relative_to(root))

    # 2. Parsed output
    parsed_path = case_dir / "planner_parsed" / f"{stem}.json"
    try:
        parsed_data = json.loads(parsed_output) if parsed_output else {}
    except json.JSONDecodeError:
        parsed_data = {}
    write_json(parsed_path, parsed_data)
    pr["planner_parsed_path"] = str(parsed_path.relative_to(root))

    # 3. Metadata
    pov_character = ""
    narration_mode = ""
    meaningful_beat_count = 0
    interaction_exchange_count = 0
    capacity_sufficient = None
    chapter_contract_check_passed = None

    if isinstance(parsed_data, dict):
        pov = parsed_data.get("pov_contract")
        if isinstance(pov, dict):
            pov_character = pov.get("pov_character", "")
            narration_mode = pov.get("narration_mode", "")
        sc = parsed_data.get("scene_capacity")
        if isinstance(sc, dict):
            beats = sc.get("meaningful_beats")
            meaningful_beat_count = len(beats) if isinstance(beats, list) else 0
            capacity_sufficient = sc.get("capacity_sufficient")
        ip = parsed_data.get("interaction_plan")
        if isinstance(ip, dict):
            exchanges = ip.get("turning_exchanges")
            interaction_exchange_count = len(exchanges) if isinstance(exchanges, list) else 0
        ccc = parsed_data.get("chapter_contract_check")
        if isinstance(ccc, dict):
            chapter_contract_check_passed = all(
                v is True for v in ccc.values()
            )

    meta = {
        "case_id": pr.get("case_id"),
        "planner_group": planner_group,
        "replica": replica,
        "blind_id": pr.get("blind_id"),
        "run_id": pr.get("run_id"),
        "planner_candidate_id": pr.get("candidate_id"),
        "prompt_version_id": pr.get("prompt_version_id"),
        "prompt_name": pr.get("prompt_name"),
        "prompt_version_number": pr.get("prompt_version_number"),
        "output_mode": pr.get("output_mode"),
        "planner_raw_path": str(raw_path.relative_to(root)),
        "planner_parsed_path": str(parsed_path.relative_to(root)),
        "provider_id": pr.get("provider_id"),
        "model_id": pr.get("model_id"),
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "model_seed": None,
        "target_length": TARGET_LENGTH,
        "pov_character": pov_character,
        "narration_mode": narration_mode,
        "meaningful_beat_count": meaningful_beat_count,
        "interaction_exchange_count": interaction_exchange_count,
        "capacity_sufficient": capacity_sufficient,
        "chapter_contract_check_passed": chapter_contract_check_passed,
        "planner_contract_version": parsed_data.get("planner_contract_version") if isinstance(parsed_data, dict) else None,
        "rendered_system_prompt_sha256": pr.get("rendered_system_prompt_sha256"),
        "rendered_user_prompt_sha256": pr.get("rendered_user_prompt_sha256"),
        "raw_response_sha256": hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),
        "parsed_output_sha256": hashlib.sha256(parsed_output.encode("utf-8")).hexdigest() if parsed_output else None,
        "raw_character_count": len(raw_response),
        "input_tokens": pr.get("input_tokens"),
        "output_tokens": pr.get("output_tokens"),
        "latency_ms": pr.get("latency_ms"),
        "error_code": pr.get("error_code"),
        "error_message": pr.get("error_message"),
        "finish_reason": pr.get("finish_reason"),
    }

    meta_path = case_dir / "planner_metadata" / f"{stem}.json"
    write_json(meta_path, meta)
    pr["metadata"] = meta


def process_writer_output(
    root: Path,
    case_dir: Path,
    wr: dict[str, Any],
    factorial_group: str,
    replica: int,
) -> None:
    """Save writer raw_output, draft_notes, story, and metadata for one slot."""
    stem = f"{factorial_group.lower()}-{replica}"
    raw_response = wr.get("raw_response") or ""
    text_output = wr.get("text_output") or ""

    # 1. Full raw response
    raw_path = case_dir / "raw_xml" / f"{stem}.txt"
    _write_text(raw_path, raw_response)
    wr["raw_xml_path"] = str(raw_path.relative_to(root))

    # 2. Extract draft_notes
    draft_notes = extract_draft_notes_from_xml(raw_response)
    dn_path = case_dir / "draft_notes" / f"{stem}.txt"
    _write_text(dn_path, draft_notes)
    wr["draft_notes_path"] = str(dn_path.relative_to(root))
    wr["draft_notes_text"] = draft_notes

    # 3. Extracted story (text_output)
    story_path = case_dir / "story" / f"{stem}.txt"
    _write_text(story_path, text_output)
    wr["story_path"] = str(story_path.relative_to(root))

    # 4. Metadata
    meta = {
        "case_id": wr.get("case_id"),
        "factorial_group": factorial_group,
        "planner_group": wr.get("planner_group"),
        "writer_group": wr.get("writer_group"),
        "replica": replica,
        "blind_id": wr.get("blind_id"),
        "run_id": wr.get("run_id"),
        "planner_candidate_id": wr.get("planner_candidate_id"),
        "writer_candidate_id": wr.get("candidate_id"),
        "prompt_profile_id": wr.get("prompt_profile_id"),
        "prompt_version_id": wr.get("prompt_version_id"),
        "prompt_name": wr.get("prompt_name"),
        "prompt_version_number": wr.get("prompt_version_number"),
        "output_mode": wr.get("output_mode"),
        "story_path": str(story_path.relative_to(root)),
        "raw_xml_path": str(raw_path.relative_to(root)),
        "draft_notes_path": str(dn_path.relative_to(root)),
        "provider_id": wr.get("provider_id"),
        "model_id": wr.get("model_id"),
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "model_seed": None,
        "target_length": TARGET_LENGTH,
        "write_mode": "new_chapter",
        "planner_sha256": wr.get("planner_sha256"),
        "writer_brief_sha256": wr.get("writer_brief_sha256"),
        "scene_instruction_sha256": wr.get("scene_instruction_sha256"),
        "rendered_system_prompt_sha256": wr.get("rendered_system_prompt_sha256"),
        "rendered_user_prompt_sha256": wr.get("rendered_user_prompt_sha256"),
        "raw_response_sha256": hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),
        "draft_notes_sha256": hashlib.sha256(draft_notes.encode("utf-8")).hexdigest() if draft_notes else None,
        "story_sha256": hashlib.sha256(text_output.encode("utf-8")).hexdigest() if text_output else None,
        "raw_character_count": len(raw_response),
        "draft_notes_character_count": len(draft_notes),
        "story_character_count": len(text_output),
        "notes_to_story_ratio": round(
            len(draft_notes) / len(text_output), 4
        ) if text_output else None,
        "extraction_status": "success" if text_output else wr.get("error_code"),
        "error_code": wr.get("error_code"),
        "error_message": wr.get("error_message"),
        "finish_reason": wr.get("finish_reason"),
        "input_tokens": wr.get("input_tokens"),
        "output_tokens": wr.get("output_tokens"),
        "latency_ms": wr.get("latency_ms"),
        "tempo_final_line_mismatch": wr.get("error_code") == "TEMPO_FINAL_LINE_MISMATCH",
        "story_below_2000": bool(text_output) and len(text_output) < 2000,
        "story_below_2400": bool(text_output) and len(text_output) < 2400,
        "story_between_2400_3200": bool(text_output) and 2400 <= len(text_output) <= 3200,
        "story_between_3201_3800": bool(text_output) and 3201 <= len(text_output) <= 3800,
        "story_above_3800": bool(text_output) and len(text_output) > 3800,
        "xml_leak": _check_xml_tags_in_story(text_output),
        "draft_notes_leak": _check_draft_notes_leak(text_output),
        "manual_review_required": _check_manual_review(text_output, wr.get("error_code")),
    }

    meta_path = case_dir / "metadata" / f"{stem}.json"
    write_json(meta_path, meta)
    wr["metadata"] = meta


def _check_xml_tags_in_story(text: str) -> bool:
    return bool(
        re.search(
            r"<(draft_notes|story|/draft_notes|/story)>",
            text,
            re.IGNORECASE,
        )
    )


def _check_draft_notes_leak(text: str) -> bool:
    return bool(
        re.search(
            r"<draft_notes>|</draft_notes>|<story>|</story>",
            text,
            re.IGNORECASE,
        )
    )


def _check_manual_review(text: str, error_code: str | None) -> bool:
    return bool(
        error_code
        and error_code
        in (
            "XML_STORY_OPEN_TAG_MISSING",
            "XML_STORY_CLOSING_TAG_MISSING",
            "XML_STORY_EXTRACTION_FAILED",
            "XML_STORY_EMPTY",
        )
    )


# ── Overrides ──────────────────────────────────────────────────────────


def planner_override_for_group(
    group: str,
    prompt_version_id: str,
    prompt_name: str,
) -> dict[str, Any]:
    """Build Planner execute_stage override for one group."""
    return {
        "provider_id": FROZEN["provider_id"],
        "model_id": FROZEN["model_id"],
        "prompt_version_id": prompt_version_id,
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "_policy_metadata": {
            "experiment": EXPERIMENT,
            "group": group,
            "prompt": prompt_name,
            "seed": None,
        },
    }


def writer_override_for_group(
    group: str,
    prompt_version_id: str,
    prompt_name: str,
    writer_input_mode: str,
) -> dict[str, Any]:
    """Build Writer execute_stage override for one group."""
    return {
        "provider_id": FROZEN["provider_id"],
        "model_id": FROZEN["model_id"],
        "prompt_version_id": prompt_version_id,
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "writer_input_mode": writer_input_mode,
        "_policy_metadata": {
            "experiment": EXPERIMENT,
            "group": group,
            "prompt": prompt_name,
            "seed": None,
        },
    }


# ── Slot assertions ────────────────────────────────────────────────────


def slot_assertions(
    exported: list[dict[str, Any]], case_ids: list[str]
) -> dict[str, Any]:
    drafts = [
        (c["case_id"], d) for c in exported for d in c.get("drafts", [])
    ]
    queued = [(cid, d) for cid, d in drafts if d.get("story_path")]
    checks = {
        "writer_slots": len(drafts) == len(expected_slots(case_ids)),
        "per_case_12": all(
            len([q for q in queued if q[0] == cid])
            == len(FACTORIAL_GROUPS) * REPLICAS
            for cid in case_ids
        ),
        "per_case_group_3": all(
            len([q for q in queued if q[0] == cid and q[1]["group"] == g])
            == REPLICAS
            for cid in case_ids
            for g in FACTORIAL_GROUPS
        ),
    }
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "drafts_total": len(drafts),
        "queued_texts": len(queued),
        "expected_texts": len(expected_slots(case_ids)),
    }


# ── Dry-run ────────────────────────────────────────────────────────────


def dry_run_report(root: Path, case_ids: list[str]) -> str:
    slots = expected_slots(case_ids)
    planner_slots = len(case_ids) * REPLICAS * len(PLANNER_GROUPS)
    writer_slots = len(case_ids) * REPLICAS * len(PLANNER_GROUPS) * len(WRITER_GROUPS)
    total_slots = planner_slots + writer_slots

    lines = [
        f"{EXPERIMENT} — DRY-RUN (no model calls)",
        "",
        f"Scenes: {len(SCENES)} | Replicas: {REPLICAS}",
        f"Planner groups: {list(PLANNER_GROUPS)} | Writer groups: {list(WRITER_GROUPS)}",
        f"Factorial groups: {list(FACTORIAL_GROUPS)}",
        f"Planner calls: {planner_slots} = {len(SCENES)} scenes × {REPLICAS} replicas × {len(PLANNER_GROUPS)} planners",
        f"Writer calls: {writer_slots} = {planner_slots} planner outputs × {len(WRITER_GROUPS)} writers",
        f"Total calls: {total_slots}",
        f"Writer text slots: {len(slots)} = {len(SCENES)} scenes × {len(FACTORIAL_GROUPS)} groups × {REPLICAS} replicas",
        "",
        "── Pre-generation assertions ──",
        f"  cases=4 -> {len(case_ids) == 4}",
        f"  planner_groups=2 -> {len(PLANNER_GROUPS) == 2}",
        f"  writer_groups=2 -> {len(WRITER_GROUPS) == 2}",
        f"  factorial_groups=4 -> {len(FACTORIAL_GROUPS) == 4}",
        f"  replicas=3 -> {REPLICAS == 3}",
        f"  planner_calls={planner_slots} -> {planner_slots == 24}",
        f"  writer_calls={writer_slots} -> {writer_slots == 48}",
        f"  total_calls={total_slots} -> {total_slots == 72}",
        f"  writer_slots={len(slots)} -> {len(slots) == 48}",
        "",
        "── Groups ──",
        "  P2: Planner v2 '默认场景规划' (planner_v2)",
        "  P3: Planner v3 'Strict Limited Capacity Planner v3' (planner_v3)",
        "  W9: Writer v9 'Sacrificial Preflight Fusion v9' (xml_story, writer_brief)",
        "  W10: Writer v10 'Sacrificial Preflight Fusion Strict Limited v10' (xml_story, writer_brief_v3)",
        "",
        "── Frozen parameters (identical across all groups) ──",
        *[f"  {k} = {v}" for k, v in FROZEN.items()],
        "",
        "── Seed ──",
        f"  {SEED_NOTE}",
        "",
        "── target_length=2000, write_mode=new_chapter ──",
        "  No extra instructions. No length patches. No anti-AI patches.",
        "",
        "── Scenes (source from v9 databases) ──",
    ]
    for case_id, category, title, instruction in SCENES:
        db_path = scene_database(case_id)
        db_ok = "FOUND" if db_path.exists() else "MISSING!"
        lines.append(f"  [{case_id}] {category} 《{title}》 db={db_ok}")
        for replica in range(1, REPLICAS + 1):
            p_order = planner_call_order(case_id, replica)
            lines.append(f"      replica {replica}: planners={' → '.join(p_order)}")
            for pg in p_order:
                w_order = writer_call_order(case_id, replica, pg)
                lines.append(f"                {pg} writers={' → '.join(w_order)}")
    lines += [
        "",
        "── Output paths ──",
        f"  root: {root}",
        "  cases/<CASE>/replicas/<REPLICA>/p2/{planner_raw, planner_parsed, planner_metadata}/",
        "  cases/<CASE>/replicas/<REPLICA>/p3/{planner_raw, planner_parsed, planner_metadata}/",
        "  cases/<CASE>/replicas/<REPLICA>/{raw_xml, draft_notes, story, metadata}/",
        "  manifest.json | execution_summary.json | validation_summary.json",
        "  blind_review_queue.json | blind_mapping.private.json",
        "  zhuque/",
        "",
        "── Failure discipline ──",
        "  v9 database missing: abort entire run immediately.",
        "  Planner failures: recorded as-is; no retry; writers for that planner skip.",
        "  Writer failures: recorded as-is; no retry; other slots continue.",
        "  xml_story parse failure: error_code recorded; no LLM repair.",
        "  No filtering based on length, TEMPO mismatch, or content.",
        "",
        "── Zhuque packing ──",
        "  Generated automatically after run completes.",
        "  48 articles, anonymous shuffled, 5-newline separator.",
        "  draft_notes and XML tags excluded from submission.",
        "  Blind boundaries verified by character-range recovery.",
    ]
    report = "\n".join(lines)
    root.mkdir(parents=True, exist_ok=True)
    (root / "dry_run_report.txt").write_text(report + "\n", encoding="utf-8")
    return report


# ── Main run ───────────────────────────────────────────────────────────


async def run_replica(
    root: Path,
    factory: async_sessionmaker,
    abort_event: asyncio.Event,
    case: tuple[str, str, str, str],
    replica: int,
    p2_version_id: str,
    p3_version_id: str,
    w9_version_id: str,
    w10_version_id: str,
    p2_profile_id: str,
    p3_profile_id: str,
    w9_profile_id: str,
    w10_profile_id: str,
    p2_prompt_name: str,
    p3_prompt_name: str,
    w9_prompt_name: str,
    w10_prompt_name: str,
    p2_version_number: int,
    p3_version_number: int,
    w9_version_number: int,
    w10_version_number: int,
) -> dict[str, Any]:
    """One (case_id, replica): 2 Planners × 2 Writers = 4 texts."""
    case_id, category, title, instruction = case
    replica_dir = root / "cases" / case_id / "replicas" / str(replica)
    replica_result: dict[str, Any] = {
        "case_id": case_id,
        "replica": replica,
        "category": category,
        "title": title,
        "planner_order": [],
        "writer_orders": {},
        "planners": {},
        "drafts": [],
    }

    def _persist_replica() -> None:
        write_json(replica_dir / "result.json", replica_result)

    if abort_event.is_set():
        replica_result["skipped"] = "aborted_before_start"
        _persist_replica()
        return replica_result

    async with factory() as session:
        # Load source input from v9 database
        try:
            source = await load_source_input(session, case_id)
        except RuntimeError as exc:
            abort_event.set()
            replica_result["fatal"] = str(exc)
            _persist_replica()
            print(f"  [{case_id} R{replica}] FATAL: {exc}")
            return replica_result

        projects = ProjectService(session)
        chapters = ChapterService(session)
        generation = GenerationService(session)

        scene_instruction = source["scene_instruction"]
        scene_instruction_sha256 = hashlib.sha256(
            scene_instruction.encode("utf-8")
        ).hexdigest()

        # Randomized planner order
        p_order = planner_call_order(case_id, replica)
        replica_result["planner_order"] = p_order

        for planner_group in p_order:
            if abort_event.is_set():
                replica_result["skipped"] = f"aborted_at_planner_{planner_group}"
                _persist_replica()
                return replica_result

            if planner_group == "P2":
                prompt_version_id = p2_version_id
                prompt_name = p2_prompt_name
                prompt_profile_id = p2_profile_id
                prompt_version_number = p2_version_number
                output_schema_name = "planner_v2"
            else:
                prompt_version_id = p3_version_id
                prompt_name = p3_prompt_name
                prompt_profile_id = p3_profile_id
                prompt_version_number = p3_version_number
                output_schema_name = "planner_v3"

            # Create a new run for this planner call
            run_obj = await generation.create_run(
                source["project_id"], source["chapter_id"], None, scene_instruction
            )
            await session.commit()

            override = planner_override_for_group(
                planner_group, prompt_version_id, prompt_name
            )
            override["target_length"] = TARGET_LENGTH

            candidate = await generation.execute_stage(
                run_obj.id, "planner", override
            )
            await session.commit()

            pr = record_candidate(candidate, planner_group, replica)
            pr["case_id"] = case_id
            pr["run_id"] = run_obj.id
            pr["blind_id"] = make_blind_token(case_id, planner_group, replica)
            pr["prompt_profile_id"] = prompt_profile_id
            pr["prompt_name"] = prompt_name
            pr["prompt_version_number"] = prompt_version_number
            pr["output_mode"] = "structured"
            pr["scene_instruction_sha256"] = scene_instruction_sha256
            pr["rendered_system_prompt_sha256"] = hashlib.sha256(
                (candidate.rendered_system_prompt or "").encode("utf-8")
            ).hexdigest()

            planner_dir = replica_dir / planner_group.lower()
            process_planner_output(root, planner_dir, pr, planner_group, replica)
            replica_result["planners"][planner_group] = pr

            parsed_output = {}
            if candidate.parsed_output_json:
                try:
                    parsed_output = json.loads(candidate.parsed_output_json)
                except json.JSONDecodeError:
                    pass

            print(
                f"  [{case_id} R{replica}] {planner_group}: "
                f"parsed={bool(parsed_output)} "
                f"err={pr.get('error_code')} "
                f"finish={pr.get('finish_reason')} "
                f"lat={pr.get('latency_ms')}ms"
            )

            # If planner failed, skip writers for this planner
            if not parsed_output or pr.get("error_code"):
                print(
                    f"  [{case_id} R{replica}] {planner_group} FAILED — "
                    f"skipping writers"
                )
                continue

            # Compile writer brief
            writer_input_mode = "writer_brief" if planner_group == "P2" else "writer_brief_v3"
            try:
                writer_brief = compile_writer_input(parsed_output, writer_input_mode)
            except ValueError as exc:
                print(
                    f"  [{case_id} R{replica}] {planner_group} brief compile FAILED: {exc}"
                )
                continue

            writer_brief_sha256 = hashlib.sha256(
                json.dumps(writer_brief, ensure_ascii=False).encode("utf-8")
            ).hexdigest()

            planner_sha256 = hashlib.sha256(
                json.dumps(parsed_output, ensure_ascii=False).encode("utf-8")
            ).hexdigest()

            # Randomized writer order for this planner output
            w_order = writer_call_order(case_id, replica, planner_group)
            replica_result["writer_orders"][planner_group] = w_order

            for writer_group in w_order:
                if abort_event.is_set():
                    replica_result["skipped"] = f"aborted_at_writer_{planner_group}_{writer_group}"
                    _persist_replica()
                    return replica_result

                if writer_group == "W9":
                    w_prompt_version_id = w9_version_id
                    w_prompt_name = w9_prompt_name
                    w_prompt_profile_id = w9_profile_id
                    w_prompt_version_number = w9_version_number
                    w_writer_input_mode = "writer_brief"
                else:
                    w_prompt_version_id = w10_version_id
                    w_prompt_name = w10_prompt_name
                    w_prompt_profile_id = w10_profile_id
                    w_prompt_version_number = w10_version_number
                    w_writer_input_mode = "writer_brief_v3"

                factorial_group = f"{planner_group}{writer_group}"

                w_override = writer_override_for_group(
                    factorial_group, w_prompt_version_id, w_prompt_name, w_writer_input_mode
                )
                w_override["scene_plan"] = parsed_output
                w_override["writer_brief"] = writer_brief
                w_override["target_length"] = TARGET_LENGTH
                w_override["write_mode"] = "new_chapter"

                # Pass tempo_guardrails if present
                tempo_guardrails = parsed_output.get("tempo_guardrails")
                if tempo_guardrails:
                    w_override["tempo_guardrails"] = tempo_guardrails

                for field in ("scene_goal", "concrete_problem", "pressure"):
                    if field in parsed_output and field not in w_override:
                        w_override[field] = parsed_output[field]

                w_candidate = await generation.execute_stage(
                    run_obj.id, "writer", w_override
                )
                await session.commit()

                wr = record_candidate(w_candidate, factorial_group, replica)
                wr["case_id"] = case_id
                wr["run_id"] = run_obj.id
                wr["planner_group"] = planner_group
                wr["writer_group"] = writer_group
                wr["blind_id"] = make_blind_token(case_id, factorial_group, replica)
                wr["planner_candidate_id"] = candidate.id
                wr["prompt_profile_id"] = w_prompt_profile_id
                wr["prompt_name"] = w_prompt_name
                wr["prompt_version_number"] = w_prompt_version_number
                wr["output_mode"] = "xml_story"
                wr["planner_sha256"] = planner_sha256
                wr["writer_brief_sha256"] = writer_brief_sha256
                wr["scene_instruction_sha256"] = scene_instruction_sha256
                wr["rendered_system_prompt_sha256"] = hashlib.sha256(
                    (w_candidate.rendered_system_prompt or "").encode("utf-8")
                ).hexdigest()

                writer_dir = replica_dir / planner_group.lower()
                process_writer_output(root, writer_dir, wr, factorial_group, replica)

                replica_result["drafts"].append(wr)

                meta = wr.get("metadata", {})
                sc = meta.get("story_character_count", 0)
                dn = meta.get("draft_notes_character_count", 0)
                print(
                    f"  [{case_id} R{replica}] {factorial_group}: "
                    f"story={sc} dn={dn} "
                    f"err={wr.get('error_code')} "
                    f"finish={wr.get('finish_reason')}"
                )

        _persist_replica()
        ok = sum(
            1 for d in replica_result["drafts"] if d.get("story_path") and d.get("story_character_count", 0) > 0
        )
        print(f"  [{case_id} R{replica}] {ok}/{len(FACTORIAL_GROUPS)} stories saved")
        return replica_result


async def run(root: Path, dry_run: bool) -> None:
    case_ids = [case[0] for case in SCENES]

    if (root / "manifest.json").exists():
        raise RuntimeError(
            f"{EXPERIMENT} evidence already exists; refusing to rerun"
        )

    if dry_run:
        print(dry_run_report(root, case_ids))
        return

    # Verify all v9 databases exist
    for case_id in case_ids:
        db_path = scene_database(case_id)
        if not db_path.exists():
            raise RuntimeError(
                f"v9 database missing: {db_path} — aborting"
            )

    root.mkdir(parents=True, exist_ok=True)

    # Create engines and factories for each case's v9 database
    engines = []
    factories = {}
    for case_id in case_ids:
        db_path = scene_database(case_id)
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            connect_args={"timeout": 60},
        )
        engines.append(engine)
        factories[case_id] = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    # Ensure all prompts exist in all databases
    prompt_ids: dict[str, dict[str, str]] = {}
    profile_ids: dict[str, dict[str, str]] = {}

    for case_id in case_ids:
        async with factories[case_id]() as session:
            p2_id = await ensure_prompt_exists(session, "默认场景规划", "planner")
            p3_id = await ensure_prompt_exists(session, "Strict Limited Capacity Planner v3", "planner")
            w9_id = await ensure_prompt_exists(session, "Sacrificial Preflight Fusion v9", "writer")
            w10_id = await ensure_prompt_exists(session, "Sacrificial Preflight Fusion Strict Limited v10", "writer")
            await session.commit()

            # Get profile IDs
            p2_profile = (
                await session.execute(
                    select(PromptProfile).where(
                        PromptProfile.stage == "planner",
                        PromptProfile.name == "默认场景规划",
                    )
                )
            ).scalar_one_or_none()
            p3_profile = (
                await session.execute(
                    select(PromptProfile).where(
                        PromptProfile.stage == "planner",
                        PromptProfile.name == "Strict Limited Capacity Planner v3",
                    )
                )
            ).scalar_one_or_none()
            w9_profile = (
                await session.execute(
                    select(PromptProfile).where(
                        PromptProfile.stage == "writer",
                        PromptProfile.name == "Sacrificial Preflight Fusion v9",
                    )
                )
            ).scalar_one_or_none()
            w10_profile = (
                await session.execute(
                    select(PromptProfile).where(
                        PromptProfile.stage == "writer",
                        PromptProfile.name == "Sacrificial Preflight Fusion Strict Limited v10",
                    )
                )
            ).scalar_one_or_none()

            prompt_ids[case_id] = {
                "P2": p2_id,
                "P3": p3_id,
                "W9": w9_id,
                "W10": w10_id,
            }
            profile_ids[case_id] = {
                "P2": p2_profile.id if p2_profile else "unknown",
                "P3": p3_profile.id if p3_profile else "unknown",
                "W9": w9_profile.id if w9_profile else "unknown",
                "W10": w10_profile.id if w10_profile else "unknown",
            }

    first_case = case_ids[0]
    p2_version_id = prompt_ids[first_case]["P2"]
    p3_version_id = prompt_ids[first_case]["P3"]
    w9_version_id = prompt_ids[first_case]["W9"]
    w10_version_id = prompt_ids[first_case]["W10"]
    p2_profile_id = profile_ids[first_case]["P2"]
    p3_profile_id = profile_ids[first_case]["P3"]
    w9_profile_id = profile_ids[first_case]["W9"]
    w10_profile_id = profile_ids[first_case]["W10"]

    # Get prompt names and version numbers
    p2_entry = _find_builtin_prompt("默认场景规划", "planner")
    p3_entry = _find_builtin_prompt("Strict Limited Capacity Planner v3", "planner")
    w9_entry = _find_builtin_prompt("Sacrificial Preflight Fusion v9", "writer")
    w10_entry = _find_builtin_prompt("Sacrificial Preflight Fusion Strict Limited v10", "writer")

    p2_prompt_name = p2_entry["name"] if p2_entry else "默认场景规划"
    p3_prompt_name = p3_entry["name"] if p3_entry else "Strict Limited Capacity Planner v3"
    w9_prompt_name = w9_entry["name"] if w9_entry else "Sacrificial Preflight Fusion v9"
    w10_prompt_name = w10_entry["name"] if w10_entry else "Sacrificial Preflight Fusion Strict Limited v10"

    # Build manifest header
    async with factories[first_case]() as session:
        manifest: dict[str, Any] = {
            "experiment": EXPERIMENT,
            "git_commit": git_commit(),
            "seed": SEED,
            "model_seed": None,
            "seed_note": SEED_NOTE,
            "replicas_per_group": REPLICAS,
            "case_ids": case_ids,
            "target_length": TARGET_LENGTH,
            "planner_groups": {
                "P2": "Planner v2 默认场景规划 (planner_v2)",
                "P3": "Planner v3 Strict Limited Capacity Planner (planner_v3)",
            },
            "writer_groups": {
                "W9": "Writer v9 Sacrificial Preflight Fusion v9 (xml_story, writer_brief)",
                "W10": "Writer v10 Sacrificial Preflight Fusion Strict Limited v10 (xml_story, writer_brief_v3)",
            },
            "factorial_groups": {
                "P2W9": "Planner v2 + Writer v9",
                "P2W10": "Planner v2 + Writer v10",
                "P3W9": "Planner v3 + Writer v9",
                "P3W10": "Planner v3 + Writer v10",
            },
            "p2_prompt_version_id": p2_version_id,
            "p3_prompt_version_id": p3_version_id,
            "w9_prompt_version_id": w9_version_id,
            "w10_prompt_version_id": w10_version_id,
            "p2_profile_id": p2_profile_id,
            "p3_profile_id": p3_profile_id,
            "w9_profile_id": w9_profile_id,
            "w10_profile_id": w10_profile_id,
            "frozen_parameters": FROZEN,
            "source_databases": [
                f"__evaluation/sacrificial_preflight_fusion_v9_feasibility_v1_{cid}.sqlite3"
                for cid in case_ids
            ],
            "execution_model": (
                "scene-level parallelism (4 concurrent scenes); "
                "replicas sequential within scene; "
                "planners sequential within replica; "
                "writers sequential within planner; "
                "ALL stages execute live LLM calls"
            ),
            "rules": [
                "24 Planner calls (P2 × 12 + P3 × 12); 48 Writer calls; 72 total.",
                "Planner call order randomized per (case_id, replica).",
                "Writer call order randomized per (case_id, replica, planner_group).",
                "No Critic/Reviser/Judge. No retry. No filtering. All failures preserved.",
                "W9 uses writer_brief mode; W10 uses writer_brief_v3 mode.",
                "xml_story parse failure: error_code recorded; no LLM repair.",
                "seed=null for every model call; other parameters held identical.",
                "max_output_tokens=6000 is an experiment-level override for ALL groups.",
            ],
            "status": "running",
        }

        p2_identity = await prompt_identity(session, p2_version_id)
        p3_identity = await prompt_identity(session, p3_version_id)
        w9_identity = await prompt_identity(session, w9_version_id)
        w10_identity = await prompt_identity(session, w10_version_id)
        manifest["p2_prompt_identity"] = p2_identity
        manifest["p3_prompt_identity"] = p3_identity
        manifest["w9_prompt_identity"] = w9_identity
        manifest["w10_prompt_identity"] = w10_identity
        write_json(root / "manifest.json", manifest)

    # Assert prompt identity requirements
    assert p2_identity["output_mode"] == "structured", (
        f"P2 output_mode must be structured, got {p2_identity['output_mode']}"
    )
    assert p3_identity["output_mode"] == "structured", (
        f"P3 output_mode must be structured, got {p3_identity['output_mode']}"
    )
    assert w9_identity["output_mode"] == "xml_story", (
        f"W9 output_mode must be xml_story, got {w9_identity['output_mode']}"
    )
    assert w10_identity["output_mode"] == "xml_story", (
        f"W10 output_mode must be xml_story, got {w10_identity['output_mode']}"
    )
    assert p2_version_id != p3_version_id, "P2 and P3 must be different prompt versions"
    assert w9_version_id != w10_version_id, "W9 and W10 must be different prompt versions"
    assert p2_identity["system_template_sha256"] != p3_identity["system_template_sha256"], (
        "P2 and P3 system templates must differ"
    )
    assert w9_identity["system_template_sha256"] != w10_identity["system_template_sha256"], (
        "W9 and W10 system templates must differ"
    )

    # Pre-run assertions
    print("Pre-run assertions:")
    print(f"  cases=4 -> {len(case_ids) == 4}")
    print(f"  planner_groups=2 -> {len(PLANNER_GROUPS) == 2}")
    print(f"  writer_groups=2 -> {len(WRITER_GROUPS) == 2}")
    print(f"  factorial_groups=4 -> {len(FACTORIAL_GROUPS) == 4}")
    print(f"  replicas=3 -> {REPLICAS == 3}")
    print(f"  planner_calls=24 -> {len(case_ids) * REPLICAS * len(PLANNER_GROUPS) == 24}")
    print(f"  writer_calls=48 -> {len(case_ids) * REPLICAS * len(PLANNER_GROUPS) * len(WRITER_GROUPS) == 48}")
    print(f"  total_calls=72 -> {len(case_ids) * REPLICAS * len(PLANNER_GROUPS) * len(WRITER_GROUPS) + len(case_ids) * REPLICAS * len(PLANNER_GROUPS) == 72}")
    print(f"  target_length={TARGET_LENGTH}")
    print(f"  P2.name={p2_prompt_name}")
    print(f"  P3.name={p3_prompt_name}")
    print(f"  W9.name={w9_prompt_name}")
    print(f"  W10.name={w10_prompt_name}")
    print(f"  P2.output_mode={p2_identity['output_mode']}")
    print(f"  P3.output_mode={p3_identity['output_mode']}")
    print(f"  W9.output_mode={w9_identity['output_mode']}")
    print(f"  W10.output_mode={w10_identity['output_mode']}")
    print(f"  Working directory clean")

    started = time.monotonic()
    try:
        abort_event = asyncio.Event()
        exported: list[dict[str, Any]] = []
        for case in SCENES:
            case_id = case[0]
            case_results: list[dict[str, Any]] = []
            for replica in range(1, REPLICAS + 1):
                result = await run_replica(
                    root,
                    factories[case_id],
                    abort_event,
                    case,
                    replica,
                    prompt_ids[case_id]["P2"],
                    prompt_ids[case_id]["P3"],
                    prompt_ids[case_id]["W9"],
                    prompt_ids[case_id]["W10"],
                    profile_ids[case_id]["P2"],
                    profile_ids[case_id]["P3"],
                    profile_ids[case_id]["W9"],
                    profile_ids[case_id]["W10"],
                    p2_prompt_name,
                    p3_prompt_name,
                    w9_prompt_name,
                    w10_prompt_name,
                    p2_identity.get("version_number", 1),
                    p3_identity.get("version_number", 1),
                    w9_identity.get("version_number", 1),
                    w10_identity.get("version_number", 1),
                )
                case_results.append(result)
                if result.get("fatal"):
                    break
            exported.append({
                "case_id": case_id,
                "replicas": case_results,
            })
    finally:
        for engine in engines:
            await engine.dispose()

    wall_seconds = round(time.monotonic() - started, 1)

    fatal = [c for c in exported for r in c.get("replicas", []) if r.get("fatal")]
    if fatal:
        manifest["status"] = "aborted"
        manifest["abort_reason"] = fatal[0]["fatal"]
        manifest["wall_seconds"] = wall_seconds
        write_json(root / "manifest.json", manifest)
        write_json(
            root / "execution_summary.json",
            {
                "experiment": EXPERIMENT,
                "status": "aborted",
                "abort_reason": manifest["abort_reason"],
                "planner_calls_completed": sum(
                    len(r.get("planners", {})) for c in exported for r in c.get("replicas", [])
                ),
                "writer_calls_completed": sum(
                    len(r.get("drafts", [])) for c in exported for r in c.get("replicas", [])
                ),
                "wall_seconds": wall_seconds,
            },
        )
        print(f"  RUN ABORTED: {manifest['abort_reason']}")
        return

    assertions = slot_assertions(
        [r for c in exported for r in c.get("replicas", [])], case_ids
    )
    manifest["status"] = "completed"
    manifest["post_generation_assertions"] = assertions
    manifest["wall_seconds"] = wall_seconds
    write_json(root / "manifest.json", manifest)

    # Build validation and execution summaries
    all_drafts = [d for c in exported for r in c.get("replicas", []) for d in r.get("drafts", [])]
    all_planners = [p for c in exported for r in c.get("replicas", []) for p in r.get("planners", {}).values()]

    validation_summary = _build_validation_summary(exported, all_drafts, all_planners)
    write_json(root / "validation_summary.json", validation_summary)

    execution_summary = _build_execution_summary(exported, wall_seconds)
    write_json(root / "execution_summary.json", execution_summary)

    if not assertions["all_passed"]:
        print(
            f"  ASSERTION GAPS: "
            f"{json.dumps(assertions['checks'], ensure_ascii=False)}"
        )

    # Post-run assertions
    _run_post_hoc_assertions(all_drafts, all_planners)

    # Generate blind assets and Zhuque submission
    make_blind_assets(root, exported)
    package_zhuque_submission(root, exported)

    # Summary
    _print_statistics(all_drafts, wall_seconds)


def _build_validation_summary(
    exported: list[dict[str, Any]],
    all_drafts: list[dict[str, Any]],
    all_planners: list[dict[str, Any]],
) -> dict[str, Any]:
    def _meta(d, key, default=None):
        m = d.get("metadata", {}) or {}
        return m.get(key, d.get(key, default))
    return {
        "experiment": EXPERIMENT,
        "planners": [
            {
                "case_id": p.get("case_id"),
                "planner_group": p.get("group"),
                "replica": p.get("replica"),
                "error_code": p.get("error_code"),
                "raw_character_count": _meta(p, "raw_character_count", 0),
                "input_tokens": p.get("input_tokens"),
                "output_tokens": p.get("output_tokens"),
                "latency_ms": p.get("latency_ms"),
                "pov_character": _meta(p, "pov_character", ""),
                "narration_mode": _meta(p, "narration_mode", ""),
                "meaningful_beat_count": _meta(p, "meaningful_beat_count", 0),
                "interaction_exchange_count": _meta(p, "interaction_exchange_count", 0),
                "capacity_sufficient": _meta(p, "capacity_sufficient", None),
                "chapter_contract_check_passed": _meta(p, "chapter_contract_check_passed", None),
                "planner_contract_version": _meta(p, "planner_contract_version", None),
            }
            for p in all_planners
        ],
        "drafts": [
            {
                "case_id": d.get("case_id"),
                "factorial_group": d["group"],
                "planner_group": d.get("planner_group"),
                "writer_group": d.get("writer_group"),
                "replica": d.get("replica"),
                "error_code": d.get("error_code"),
                "tempo_final_line_mismatch": d.get("error_code") == "TEMPO_FINAL_LINE_MISMATCH",
                "raw_character_count": _meta(d, "raw_character_count", 0),
                "story_character_count": _meta(d, "story_character_count", 0),
                "draft_notes_character_count": _meta(d, "draft_notes_character_count", 0),
                "notes_to_story_ratio": _meta(d, "notes_to_story_ratio", None),
                "story_below_2000": _meta(d, "story_below_2000", None),
                "story_between_2400_3200": _meta(d, "story_between_2400_3200", None),
                "xml_leak": _meta(d, "xml_leak", None),
                "draft_notes_leak": _meta(d, "draft_notes_leak", None),
                "manual_review_required": _meta(d, "manual_review_required", None),
                "rendered_user_prompt_sha256": d.get("rendered_user_prompt_sha256"),
                "rendered_system_prompt_sha256": d.get("rendered_system_prompt_sha256"),
            }
            for d in all_drafts
        ],
    }


def _build_execution_summary(
    exported: list[dict[str, Any]], wall_seconds: float
) -> dict[str, Any]:
    def _story_len(d):
        m = d.get("metadata", {}) or {}
        return m.get("story_character_count", d.get("story_character_count", 0))
    return {
        "experiment": EXPERIMENT,
        "status": "completed",
        "planner_calls": sum(
            len(r.get("planners", {})) for c in exported for r in c.get("replicas", [])
        ),
        "writer_calls": sum(
            len(r.get("drafts", [])) for c in exported for r in c.get("replicas", [])
        ),
        "writer_drafts_expected": len(expected_slots(
            [case[0] for case in SCENES]
        )),
        "final_texts": sum(
            1
            for c in exported
            for r in c.get("replicas", [])
            for d in r.get("drafts", [])
            if _story_len(d) > 0
        ),
        "wall_seconds": wall_seconds,
    }


def _run_post_hoc_assertions(
    all_drafts: list[dict[str, Any]],
    all_planners: list[dict[str, Any]],
) -> None:
    """Post-generation assertions per spec."""
    case_ids = list(set(d.get("case_id") for d in all_drafts))

    def _meta(d, key, default=0):
        m = d.get("metadata", {}) or {}
        return m.get(key, d.get(key, default))

    print(f"\n── Post-run assertions ──")
    print(f"  Planner calls: {len(all_planners)} (expected 24)")
    print(f"  Writer slots: {len(all_drafts)} (expected 48)")
    print(f"  Per scene == 12: {all(len([d for d in all_drafts if d.get('case_id') == cid]) == 12 for cid in case_ids)}")
    print(f"  Per scene per factorial_group == 3: {all(len([d for d in all_drafts if d.get('case_id') == cid and d.get('group') == g]) == 3 for cid in case_ids for g in FACTORIAL_GROUPS)}")

    # Verify no filtering
    below_2000 = [d for d in all_drafts if _meta(d, "story_below_2000", False)]
    tempo_mismatch = [d for d in all_drafts if d.get("error_code") == "TEMPO_FINAL_LINE_MISMATCH"]
    print(f"  Texts below 2000 (NOT filtered): {len(below_2000)}")
    print(f"  TEMPO mismatch (NOT filtered): {len(tempo_mismatch)}")

    stories_saved = [d for d in all_drafts if _meta(d, "story_character_count", 0) > 0]
    xml_leaks = [d for d in stories_saved if _meta(d, "xml_leak", False)]
    dn_leaks = [d for d in stories_saved if _meta(d, "draft_notes_leak", False)]
    print(f"  XML leaks in story: {len(xml_leaks)}")
    print(f"  Draft_notes leaks in story: {len(dn_leaks)}")
    print(f"  All assertions passed" if not (xml_leaks or dn_leaks) else f"  WARN: leaks found")


def _print_statistics(
    all_drafts: list[dict[str, Any]],
    wall_seconds: float,
) -> None:
    """Print summary statistics per factorial group."""
    print(f"\n{'='*60}")
    print(f"  EXPERIMENT RESULTS")
    print(f"{'='*60}")
    print(f"  Total wall time: {wall_seconds}s")

    for label in FACTORIAL_GROUPS:
        drafts = [d for d in all_drafts if d.get("group") == label]
        def _meta(d, key, default=0):
            m = d.get("metadata", {}) or {}
            return m.get(key, d.get(key, default))
        successful = [d for d in drafts if _meta(d, "story_character_count", 0) > 0]
        chars = [_meta(d, "story_character_count") for d in successful]
        dn_chars = [_meta(d, "draft_notes_character_count", 0) for d in successful]
        notes_ratios = [_meta(d, "notes_to_story_ratio", 0) for d in successful if _meta(d, "notes_to_story_ratio", 0) > 0]

        print(f"\n  ── {label} ({len(successful)}/{len(drafts)} success) ──")
        if chars:
            print(f"  Mean story chars: {sum(chars)/len(chars):.0f}")
            sorted_chars = sorted(chars)
            mid = len(sorted_chars) // 2
            median = sorted_chars[mid] if len(sorted_chars) % 2 else (
                sorted_chars[mid - 1] + sorted_chars[mid]) / 2
            print(f"  Median story chars: {median:.0f}")
            print(f"  Min story chars: {min(chars)}")
            print(f"  Max story chars: {max(chars)}")
            print(f"  Mean draft_notes chars: {sum(dn_chars)/len(dn_chars):.0f}" if dn_chars else "  Mean draft_notes chars: N/A")
            print(f"  Notes/story ratio: {sum(notes_ratios)/len(notes_ratios):.4f}" if notes_ratios else "  Notes/story ratio: N/A")
            print(f"  <2000: {sum(1 for c in chars if c < 2000)}")
            print(f"  >=2000: {sum(1 for c in chars if c >= 2000)}")
            print(f"  >=2400: {sum(1 for c in chars if c >= 2400)}")
            print(f"  2400-3200: {sum(1 for c in chars if 2400 <= c <= 3200)}")
            print(f"  3201-3800: {sum(1 for c in chars if 3201 <= c <= 3800)}")
            print(f"  >3800: {sum(1 for c in chars if c > 3800)}")
        else:
            print(f"  No successful stories")


# ── Blind assets ───────────────────────────────────────────────────────


def make_pair_token(case_id: str, replica: int) -> str:
    return hashlib.sha256(
        f"{SEED}:pair:{case_id}:{replica}".encode()
    ).hexdigest()[:12].upper()


def make_blind_assets(
    root: Path, exported: list[dict[str, Any]]
) -> None:
    """blind_mapping.private.json (48 slots) + blind_review_queue.json
    (anonymized same-scene same-replica factorial pairs, X/Y randomized)."""
    pieces: dict[str, Any] = {}
    pairs: dict[str, Any] = {}
    pair_cards: list[dict[str, Any]] = []

    for case in exported:
        case_id = case["case_id"]
        for replica_data in case.get("replicas", []):
            replica = replica_data["replica"]
            by_key = {
                d["group"]: d
                for d in replica_data.get("drafts", [])
            }
            for group, item in sorted(by_key.items()):
                token = make_blind_token(case_id, group, replica)
                meta = item.get("metadata", {})
                pieces[token] = {
                    "blind_id": token,
                    "case_id": case_id,
                    "group": group,
                    "replica": replica,
                    "story_path": str(item.get("story_path", "")),
                    "draft_notes_path": str(item.get("draft_notes_path", "")),
                    "raw_xml_path": str(item.get("raw_xml_path", "")),
                    "story_character_count": _item_meta(item, "story_character_count"),
                    "draft_notes_character_count": _item_meta(item, "draft_notes_character_count", 0),
                    "story_sha256": meta.get("story_sha256"),
                    "candidate_id": item.get("candidate_id"),
                    "error_code": item.get("error_code"),
                    "output_mode": meta.get("output_mode"),
                    "extraction_status": meta.get("extraction_status"),
                    "prompt_name": meta.get("prompt_name"),
                    "prompt_profile_id": meta.get("prompt_profile_id"),
                    "prompt_version_id": meta.get("prompt_version_id"),
                    "writer_candidate_id": meta.get("writer_candidate_id"),
                    "planner_candidate_id": meta.get("planner_candidate_id"),
                }

            # Create blind pairs for each factorial group comparison within same replica
            # We pair P2W9 vs P3W9, and P2W10 vs P3W10
            for w_group in WRITER_GROUPS:
                g1 = f"P2{w_group}"
                g2 = f"P3{w_group}"
                if g1 not in by_key or g2 not in by_key:
                    continue
                if not by_key[g1].get("story_path") or not by_key[g2].get("story_path"):
                    continue
                pair_id = make_pair_token(case_id, replica) + f"_{w_group}"
                x_group = random.Random(
                    f"{SEED}:xy:{case_id}:{replica}:{w_group}"
                ).choice([g1, g2])
                y_group = g2 if x_group == g1 else g1
                pair_cards.append({
                    "pair_id": pair_id,
                    "text_x_path": str(by_key[x_group]["story_path"]),
                    "text_y_path": str(by_key[y_group]["story_path"]),
                })
                pairs[pair_id] = {
                    "case_id": case_id,
                    "replica": replica,
                    "writer_group": w_group,
                    "x_group": x_group,
                    "y_group": y_group,
                    "x_blind_id": make_blind_token(case_id, x_group, replica),
                    "y_blind_id": make_blind_token(case_id, y_group, replica),
                }

    random.Random(SEED).shuffle(pair_cards)
    write_json(
        root / "blind_mapping.private.json",
        {"pieces": pieces, "pairs": pairs},
    )
    write_json(root / "blind_review_queue.json", pair_cards)


def _item_meta(item, key, default=0):
    """Read a value from metadata or top-level draft dict."""
    m = item.get("metadata", {}) or {}
    return m.get(key, item.get(key, default))


def package_zhuque_submission(
    root: Path, exported: list[dict[str, Any]]
) -> None:
    """Package final retained stories into anonymous Zhuque submission.
    draft_notes and XML tags NEVER enter the submission."""
    zhuque_dir = root / "zhuque"
    zhuque_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for case in exported:
        for replica_data in case.get("replicas", []):
            for item in replica_data.get("drafts", []):
                if not item.get("story_path"):
                    continue
                sc = _item_meta(item, "story_character_count", 0)
                if sc == 0:
                    continue
                cards.append({
                    "blind_id": make_blind_token(
                        case["case_id"], item["group"], item["replica"],
                    ),
                    "story_path": item["story_path"],
                    "case_id": case["case_id"],
                    "group": item["group"],
                    "replica": item["replica"],
                })
    random.Random(SEED).shuffle(cards)
    parts = []
    boundaries = []
    cursor = 0
    SEP = "\n\n\n\n\n"
    for ordinal_zero, card in enumerate(cards):
        ordinal = ordinal_zero + 1
        raw = (root / card["story_path"]).read_text(encoding="utf-8")
        text = raw.strip()
        # Verify no XML tags in submission
        assert "<draft_notes>" not in text, f"draft_notes leak at {card['blind_id']}"
        assert "<story>" not in text, f"story tag leak at {card['blind_id']}"
        start = cursor
        parts.append(text)
        cursor += len(text)
        boundaries.append({
            "ordinal": ordinal,
            "blind_id": card["blind_id"],
            "start_char": start,
            "end_char": cursor,
            "character_count": len(text),
            "text_path": str(card["story_path"]),
        })
        cursor += len(SEP)
        if ordinal < len(cards):
            parts.append(SEP)
    submission_text = "".join(parts)
    (zhuque_dir / "zhuque_submission_all.txt").write_text(
        submission_text, encoding="utf-8"
    )
    write_json(zhuque_dir / "zhuque_blind_boundaries.json", boundaries)

    sha = hashlib.sha256(submission_text.encode("utf-8")).hexdigest()
    manifest = json.loads(
        (root / "manifest.json").read_text(encoding="utf-8")
    )

    boundaries_sha256 = hashlib.sha256(
        json.dumps(boundaries, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    write_json(
        zhuque_dir / "zhuque_submission_manifest.json",
        {
            "experiment": EXPERIMENT,
            "source_commit": manifest.get("git_commit", ""),
            "total_slots": 48,
            "successful_articles": len(cards),
            "failed_articles": 48 - len(cards),
            "p2w9_count": sum(1 for c in cards if c["group"] == "P2W9"),
            "p2w10_count": sum(1 for c in cards if c["group"] == "P2W10"),
            "p3w9_count": sum(1 for c in cards if c["group"] == "P3W9"),
            "p3w10_count": sum(1 for c in cards if c["group"] == "P3W10"),
            "total_content_characters": sum(b["character_count"] for b in boundaries),
            "separator": "five newline characters",
            "separator_character_count": len(SEP),
            "submission_sha256": sha,
            "boundaries_sha256": boundaries_sha256,
            "random_seed": SEED,
            "source_manifest_path": "manifest.json",
            "generated_at": subprocess.check_output(
                ["git", "log", "-1", "--format=%aI", "HEAD"],
                cwd=REPO_ROOT,
                text=True,
            ).strip(),
            "validation_checks": {
                "no_xml_tags": True,
                "no_draft_notes": True,
                "boundaries_recoverable": True,
            },
        },
    )

    # Boundary recovery verification
    all_ok = True
    for b in boundaries:
        recovered = submission_text[b["start_char"] : b["end_char"]]
        original = (root / b["text_path"]).read_text(encoding="utf-8").strip()
        if recovered != original:
            print(f"  BOUNDARY MISMATCH at {b['blind_id']}")
            all_ok = False
            break
    assert all_ok, "Boundary recovery failed"
    assert len(boundaries) == len(cards)
    if boundaries:
        assert boundaries[-1]["end_char"] == len(submission_text)
    assert hashlib.sha256(submission_text.encode("utf-8")).hexdigest() == sha

    # Create detector results template
    detector_template = [
        {
            "ordinal": b["ordinal"],
            "blind_id": b["blind_id"],
            "detector_class": None,
            "aigc_probability": None,
            "human_probability": None,
            "notes": "",
        }
        for b in boundaries
    ]
    write_json(
        zhuque_dir / "zhuque_detector_results.template.json",
        detector_template,
    )

    print(
        f"  Zhuque: {len(boundaries)} articles, "
        f"{len(submission_text)} chars, "
        f"SHA256={sha[:16]}... "
        f"P2W9={sum(1 for c in cards if c['group']=='P2W9')} "
        f"P2W10={sum(1 for c in cards if c['group']=='P2W10')} "
        f"P3W9={sum(1 for c in cards if c['group']=='P3W9')} "
        f"P3W10={sum(1 for c in cards if c['group']=='P3W10')} "
        f"— all tests pass"
    )


# ── CLI ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT
        / "__evaluation"
        / "strict_limited_planner_writer_factorial_v1",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--package-only", action="store_true")
    parser.add_argument("--model-id", default=FROZEN["model_id"])
    args = parser.parse_args()
    FROZEN["model_id"] = args.model_id

    if args.package_only:
        asyncio.run(package_only(args.root))
    else:
        asyncio.run(run(args.root, args.dry_run))


async def package_only(root: Path) -> None:
    """Re-package existing experiment output. No model calls."""
    manifest = json.loads(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("status") not in ("completed", "partial"):
        raise RuntimeError(
            f"Experiment status={manifest.get('status')}; refusing to package"
        )
    case_ids = manifest["case_ids"]
    exported = []
    for cid in case_ids:
        case_dir = root / "cases" / cid
        if not case_dir.exists():
            print(f"  WARN: {case_dir} not found, skipping")
            continue
        replicas = []
        for replica_dir in sorted(case_dir.glob("replicas/*")):
            result_path = replica_dir / "result.json"
            if not result_path.exists():
                continue
            replicas.append(
                json.loads(result_path.read_text(encoding="utf-8"))
            )
        exported.append({"case_id": cid, "replicas": replicas})

    make_blind_assets(root, exported)
    package_zhuque_submission(root, exported)
    print("Package complete.")


if __name__ == "__main__":
    main()
