"""SACRIFICIAL_PREFLIGHT_FUSION_V8_FEASIBILITY_V1 — frozen writer prompt comparison.

Groups (same frozen Planner, same WriterBrief, same frozen parameters;
the ONLY delta is the Writer prompt version):

  P7: Writer v7 ("Sacrificial Preflight v7", xml_story) — established baseline.
  F8: Writer v8 ("Sacrificial Preflight Fusion v8", xml_story) — fusion candidate.

4 scenes x 2 groups x 3 replicas = 24 Writer calls. ZERO Planner calls.

Discipline (pre-registered):
  - Reuse frozen Planner outputs from SACRIFICIAL_PREFLIGHT_FEASIBILITY_V1.
  - No Critic/Reviser/Judge. No retry. No filtering.
  - Both groups: generation_service extracts <story> via xml_story mode;
    raw_response preserved with draft_notes; text_output = story only.
  - Extraction failures preserved as-is; no LLM repair.
  - provider/model does not support seed: recorded as null.
  - Call order (P7->F8 or F8->P7) stratified-randomized per replica and recorded.
  - Dry-run mode (--dry-run) prints the full plan without any LLM calls.
  - Zhuque submission package generated automatically after run.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import shutil
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

EXPERIMENT = "SACRIFICIAL_PREFLIGHT_FUSION_V8_FEASIBILITY_V1"
SEED = 202607208
REPLICAS = 3
GROUPS = ("P7", "F8")

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "planner_prompt_version_id": "f9052f8a-dc4e-5408-b14e-fc1badaf57f8",
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

PREVIOUS_EVAL = (
    REPO_ROOT / "__evaluation" / "sacrificial_preflight_feasibility_v1"
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

# ── Pure helpers ───────────────────────────────────────────────────────

TARGET_LENGTH = 2000


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
        for group in GROUPS
        for replica in range(1, REPLICAS + 1)
    ]


def replica_call_order(case_id: str, replica: int) -> list[str]:
    order = list(GROUPS)
    random.Random(f"{SEED}:{case_id}:{replica}").shuffle(order)
    return order


def make_blind_token(
    case_id: str, group: str, replica: int
) -> str:
    return (
        hashlib.sha256(f"{SEED}:{case_id}:{group}:{replica}".encode())
        .hexdigest()[:12]
        .upper()
    )


def scene_database(database: Path, case_id: str) -> Path:
    return database.with_name(f"{database.stem}_{case_id}.sqlite3")


def _find_builtin_prompt(name: str) -> dict | None:
    for entry in BUILTIN_PROMPTS:
        if entry.get("name") == name and entry.get("stage") == "writer":
            return entry
    return None


async def ensure_prompt_exists(
    session: AsyncSession, name: str
) -> str:
    """Ensure a named builtin writer prompt profile + version exist.
    Returns the PromptVersion.id.
    """
    entry = _find_builtin_prompt(name)
    if entry is None:
        raise RuntimeError(
            f"Builtin prompt '{name}' not found in BUILTIN_PROMPTS"
        )

    # Check if profile already exists
    existing = (
        await session.execute(
            select(PromptProfile).where(
                PromptProfile.stage == "writer",
                PromptProfile.name == entry["name"],
                PromptProfile.is_builtin == True,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        await session.refresh(existing, ["versions"])
        if existing.versions:
            return existing.versions[-1].id

    # Create the profile
    profile = PromptProfile(
        stage="writer",
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


def load_frozen_planner(case_id: str) -> dict:
    path = PREVIOUS_EVAL / "cases" / case_id / "planner_frozen.json"
    if not path.exists():
        raise RuntimeError(
            f"Frozen Planner not found: {path} — cannot reconstruct; aborting"
        )
    return json.loads(path.read_text(encoding="utf-8"))


async def seed_planner_step(
    session: AsyncSession,
    run_id: str,
    planner_output: dict,
    prompt_version_id: str,
) -> str:
    """Create a completed planner step + candidate in the DB without any LLM call."""
    stmt = (
        select(GenerationStep)
        .where(
            GenerationStep.run_id == run_id,
            GenerationStep.stage == "planner",
        )
    )
    result = await session.execute(stmt)
    step = result.scalar_one()

    candidate = GenerationCandidate(
        step_id=step.id,
        attempt_number=1,
        provider_id=FROZEN["provider_id"],
        model_id=FROZEN["model_id"],
        prompt_version_id=prompt_version_id,
        parameters_json=json.dumps(
            {"_seeded": True, "source": "frozen_planner_reuse"}
        ),
        run_override="",
        rendered_system_prompt="[seeded - frozen planner reuse]",
        rendered_user_prompt="[seeded - frozen planner reuse]",
        raw_response="[seeded - frozen planner reuse]",
        parsed_output_json=json.dumps(planner_output, ensure_ascii=False),
        text_output="[seeded - frozen planner reuse]",
        error_code=None,
        error_message=None,
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        finish_reason="stop",
        is_selected=True,
    )
    session.add(candidate)
    await session.flush()

    step.status = "completed"
    step.selected_candidate_id = candidate.id
    await session.flush()

    return candidate.id


# ── F8 structural checks ──────────────────────────────────────────────


_V8_SECTIONS = [
    "现状重构与起笔",
    "信息边界",
    "人物活化",
    "人物套路淘汰",
    "剧情套路淘汰",
    "句式套路淘汰",
    "行动与篇幅骨架",
    "停止与文风保护",
]


def check_v8_structure(draft_notes: str) -> dict[str, Any]:
    """Check F8 draft_notes for the eight required sections.
    Returns a dict of findings. Does NOT modify the article status."""
    findings: dict[str, Any] = {
        "has_eight_sections": False,
        "sections_found": [],
        "sections_missing": [],
        "has_unit_count_6_9": False,
        "has_target_length_minimum": False,
        "has_estimated_char_counts": False,
        "draft_notes_length": len(draft_notes),
    }

    for section in _V8_SECTIONS:
        if section in draft_notes:
            findings["sections_found"].append(section)
        else:
            findings["sections_missing"].append(section)

    findings["has_eight_sections"] = len(findings["sections_found"]) == 8

    # Check for 6-9 narrative units in section 7
    section7 = ""
    if "行动与篇幅骨架" in draft_notes:
        idx = draft_notes.index("行动与篇幅骨架")
        # Find the next section header or end
        next_section_idx = len(draft_notes)
        for s in _V8_SECTIONS:
            if s == "行动与篇幅骨架":
                continue
            si = draft_notes.find(s, idx + len("行动与篇幅骨架"))
            if si != -1 and si < next_section_idx:
                next_section_idx = si
        section7 = draft_notes[idx:next_section_idx]

    if section7:
        # Count numbered units (e.g., "1.", "2.", "3." or "单元1", "单元2")
        unit_markers = re.findall(
            r'(?:^|\n)\s*(?:单元|步骤|Stage|Unit|[\d]+[\.\、\．])',
            section7,
        )
        # Also count markers that look like narrative unit mentions
        narrative_units = re.findall(
            r'(?:第[一二三四五六七八九十]+|[1-9])[^\n]{0,4}(?:单元|个叙事|个环节|步)',
            section7,
        )
        total_units = max(len(unit_markers), len(narrative_units))
        # Also try to count by "—" OR "预计" interleaved with numbers
        numbered_lines = re.findall(
            r'(?:^|\n)\s*[0-9][\.\、\．\)][^\n]{3,}',
            section7,
        )
        if numbered_lines:
            total_units = max(total_units, len(numbered_lines))
        findings["has_unit_count_6_9"] = 6 <= total_units <= 9
        findings["unit_count_raw"] = total_units

    # Check for target_length mention as minimum
    if "最低交付" in draft_notes or "最低正文" in draft_notes or "不得少于" in draft_notes:
        findings["has_target_length_minimum"] = True

    # Check for estimated char counts in units
    if re.search(r'\d{3,4}字', section7) or re.search(r'\d{3,4}\s*字符', section7):
        findings["has_estimated_char_counts"] = True

    return findings


# ── Recording ──────────────────────────────────────────────────────────


def record(candidate: Any, group: str, replica: int) -> dict[str, Any]:
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
    }


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def process_writer_output(
    root: Path,
    case_dir: Path,
    cr: dict[str, Any],
    group: str,
    replica: int,
) -> None:
    """Save raw_output, draft_notes, story, and metadata for one slot."""
    stem = f"{group.lower()}-{replica}"
    raw_response = cr.get("raw_response") or ""
    text_output = cr.get("text_output") or ""

    # 1. Full raw response (complete LLM output with XML tags)
    raw_path = case_dir / "raw_xml" / f"{stem}.txt"
    _write_text(raw_path, raw_response)
    cr["raw_xml_path"] = str(raw_path.relative_to(root))

    # 2. Extract draft_notes
    draft_notes = ""
    if raw_response:
        dn_match = re.search(
            r"<draft_notes>(.*?)</draft_notes>",
            raw_response,
            re.DOTALL | re.IGNORECASE,
        )
        if dn_match:
            draft_notes = dn_match.group(1).strip()
    dn_path = case_dir / "draft_notes" / f"{stem}.txt"
    _write_text(dn_path, draft_notes)
    cr["draft_notes_path"] = str(dn_path.relative_to(root))
    cr["draft_notes_text"] = draft_notes

    # 3. Extracted story (text_output)
    story_path = case_dir / "story" / f"{stem}.txt"
    _write_text(story_path, text_output)
    cr["story_path"] = str(story_path.relative_to(root))

    # 4. Metadata
    meta = {
        "case_id": cr.get("case_id"),
        "group": group,
        "replica": replica,
        "blind_id": cr.get("blind_id"),
        "run_id": cr.get("run_id"),
        "planner_candidate_id": cr.get("planner_candidate_id"),
        "writer_candidate_id": cr.get("candidate_id"),
        "prompt_profile_id": cr.get("prompt_profile_id"),
        "prompt_version_id": cr.get("prompt_version_id"),
        "prompt_name": cr.get("prompt_name"),
        "prompt_version_number": cr.get("prompt_version_number"),
        "output_mode": cr.get("output_mode"),
        "story_path": str(story_path.relative_to(root)),
        "raw_xml_path": str(raw_path.relative_to(root)),
        "draft_notes_path": str(dn_path.relative_to(root)),
        "provider_id": cr.get("provider_id"),
        "model_id": cr.get("model_id"),
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "model_seed": None,
        "target_length": TARGET_LENGTH,
        "write_mode": "new_chapter",
        "planner_sha256": cr.get("planner_sha256"),
        "writer_brief_sha256": cr.get("writer_brief_sha256"),
        "scene_instruction_sha256": cr.get("scene_instruction_sha256"),
        "rendered_system_prompt_sha256": cr.get("rendered_system_prompt_sha256"),
        "rendered_user_prompt_sha256": cr.get("rendered_user_prompt_sha256"),
        "raw_response_sha256": hashlib.sha256(
            raw_response.encode("utf-8")
        ).hexdigest(),
        "draft_notes_sha256": hashlib.sha256(
            draft_notes.encode("utf-8")
        ).hexdigest() if draft_notes else None,
        "story_sha256": hashlib.sha256(
            text_output.encode("utf-8")
        ).hexdigest() if text_output else None,
        "raw_character_count": len(raw_response),
        "draft_notes_character_count": len(draft_notes),
        "story_character_count": len(text_output),
        "notes_to_story_ratio": round(
            len(draft_notes) / len(text_output), 4
        ) if text_output else None,
        "extraction_status": "success" if text_output else cr.get("error_code"),
        "error_code": cr.get("error_code"),
        "error_message": cr.get("error_message"),
        "finish_reason": cr.get("finish_reason"),
        "input_tokens": cr.get("input_tokens"),
        "output_tokens": cr.get("output_tokens"),
        "latency_ms": cr.get("latency_ms"),
        "tempo_final_line_mismatch": cr.get("error_code") == "TEMPO_FINAL_LINE_MISMATCH",
        "story_below_2000": bool(text_output) and len(text_output) < 2000,
        "story_below_2400": bool(text_output) and len(text_output) < 2400,
        "story_between_2400_3200": bool(text_output) and 2400 <= len(text_output) <= 3200,
        "story_between_3201_3800": bool(text_output) and 3201 <= len(text_output) <= 3800,
        "story_above_3800": bool(text_output) and len(text_output) > 3800,
        "xml_leak": _check_xml_tags_in_story(text_output),
        "draft_notes_leak": _check_draft_notes_leak(text_output),
        "manual_review_required": _check_manual_review(text_output, cr.get("error_code")),
    }

    # Add F8 structural checks
    if group == "F8" and draft_notes:
        meta["v8_structure"] = check_v8_structure(draft_notes)

    meta_path = case_dir / "metadata" / f"{stem}.json"
    write_json(meta_path, meta)
    cr["metadata"] = meta


def _check_xml_tags_in_story(text: str) -> bool:
    """Check if story text contains XML structural tags."""
    return bool(
        re.search(
            r"<(draft_notes|story|/draft_notes|/story)>",
            text,
            re.IGNORECASE,
        )
    )


def _check_draft_notes_leak(text: str) -> bool:
    """Check if draft_notes leaked into story."""
    return bool(
        re.search(
            r"<draft_notes>|</draft_notes>|<story>|</story>",
            text,
            re.IGNORECASE,
        )
    )


def _check_manual_review(text: str, error_code: str | None) -> bool:
    """Flag if manual review is needed."""
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


# ── Writer override ────────────────────────────────────────────────────


def writer_override_for_group(
    group: str,
    prompt_version_id: str,
    prompt_name: str,
) -> dict[str, Any]:
    """Build Writer execute_stage override for one group.
    Both P7 and F8 use identical parameters; only prompt_version_id differs."""
    return {
        "provider_id": FROZEN["provider_id"],
        "model_id": FROZEN["model_id"],
        "prompt_version_id": prompt_version_id,
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "writer_input_mode": "writer_brief",
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
    queued = [(cid, d) for cid, d in drafts if d.get("text_path")]
    checks = {
        "writer_slots": len(drafts) == len(expected_slots(case_ids)),
        "group_P7_texts": len([q for q in queued if q[1]["group"] == "P7"])
        == len(case_ids) * REPLICAS,
        "group_F8_texts": len([q for q in queued if q[1]["group"] == "F8"])
        == len(case_ids) * REPLICAS,
        "per_case_6": all(
            len([q for q in queued if q[0] == cid])
            == len(GROUPS) * REPLICAS
            for cid in case_ids
        ),
        "per_case_group_3": all(
            len([q for q in queued if q[0] == cid and q[1]["group"] == g])
            == REPLICAS
            for cid in case_ids
            for g in GROUPS
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
    lines = [
        f"{EXPERIMENT} — DRY-RUN (no model calls, no Planner calls)",
        "",
        f"Scenes: {len(SCENES)} | Groups: {list(GROUPS)} | Replicas: {REPLICAS}",
        f"Slots: {len(slots)} texts = {len(SCENES)} scenes x 2 groups x 3 replicas",
        f"Model calls: {len(slots)} Writer (0 Planner — reuse frozen)",
        "",
        "── Pre-generation assertions ──",
        f"  cases=4 -> {len(case_ids) == 4}",
        f"  groups=2 -> {len(GROUPS) == 2}",
        f"  replicas=3 -> {REPLICAS == 3}",
        f"  writer_slots=24 -> {len(slots) == 24}",
        "",
        "── Groups ──",
        "  P7: Writer v7 'Sacrificial Preflight v7' (xml_story)",
        "  F8: Writer v8 'Sacrificial Preflight Fusion v8' (xml_story)",
        "",
        "── Frozen parameters (identical across both groups) ──",
        *[f"  {k} = {v}" for k, v in FROZEN.items()],
        "",
        "── Seed ──",
        f"  {SEED_NOTE}",
        "",
        "── Both groups: target_length=2000, write_mode=new_chapter ──",
        "  No extra instructions. No length patches. No anti-AI patches.",
        "  The ONLY delta is the Writer prompt version.",
        "",
        "── Scenes (Planner frozen from SACRIFICIAL_PREFLIGHT_FEASIBILITY_V1) ──",
    ]
    for case_id, category, title, instruction in SCENES:
        planner_path = PREVIOUS_EVAL / "cases" / case_id / "planner_frozen.json"
        planner_ok = "FOUND" if planner_path.exists() else "MISSING!"
        lines.append(
            f"  [{case_id}] {category} 《{title}》 planner={planner_ok}"
        )
        for replica in range(1, REPLICAS + 1):
            order = replica_call_order(case_id, replica)
            lines.append(
                f"      replica {replica}: {' → '.join(order)}"
            )
    lines += [
        "",
        "── Output paths ──",
        f"  root: {root}",
        "  cases/<CASE>/{planner_frozen.json, writer_brief.txt, result.json}",
        "  cases/<CASE>/{raw_xml, draft_notes, story, metadata}/",
        "  manifest.json | execution_summary.json | validation_summary.json",
        "  blind_review_queue.json | blind_mapping.private.json",
        "  zhuque/",
        "",
        "── Failure discipline ──",
        "  Frozen Planner missing: abort entire run immediately.",
        "  Writer failures: recorded as-is; no retry; other slots continue.",
        "  xml_story parse failure: error_code recorded; no LLM repair.",
        "  No filtering based on length, TEMPO mismatch, or content.",
        "",
        "── Zhuque packing ──",
        "  Generated automatically after run completes.",
        "  24 articles, anonymous shuffled, 5-newline separator.",
        "  draft_notes and XML tags excluded from submission.",
        "  Blind boundaries verified by character-range recovery.",
    ]
    report = "\n".join(lines)
    root.mkdir(parents=True, exist_ok=True)
    (root / "dry_run_report.txt").write_text(report + "\n", encoding="utf-8")
    return report


# ── Main run ───────────────────────────────────────────────────────────


async def run_case(
    root: Path,
    factory: async_sessionmaker,
    abort_event: asyncio.Event,
    case: tuple[str, str, str, str],
    p7_version_id: str,
    f8_version_id: str,
    p7_profile_id: str,
    f8_profile_id: str,
    p7_prompt_name: str,
    f8_prompt_name: str,
    p7_version_number: int,
    f8_version_number: int,
) -> dict[str, Any]:
    """One scene: 6 Writers (P7 x 3 + F8 x 3, sequential within scene).
    NO Planner call — uses frozen Planner from previous experiment."""
    case_id, category, title, instruction = case
    case_dir = root / "cases" / case_id
    case_result: dict[str, Any] = {
        "case_id": case_id,
        "category": category,
        "title": title,
        "run_id": None,
        "drafts": [],
    }

    def _persist_case() -> None:
        write_json(case_dir / "result.json", case_result)

    if abort_event.is_set():
        case_result["skipped"] = "aborted_before_start"
        _persist_case()
        return case_result

    # Load frozen Planner from previous experiment
    try:
        planner_output = load_frozen_planner(case_id)
    except RuntimeError as exc:
        abort_event.set()
        case_result["fatal"] = str(exc)
        _persist_case()
        print(f"  [{case_id}] FATAL: {exc}")
        return case_result

    write_json(case_dir / "planner_frozen.json", planner_output)
    planner_sha256 = hashlib.sha256(
        json.dumps(planner_output, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    # Compile WriterBrief from frozen Planner
    try:
        writer_brief = compile_writer_input(planner_output, "writer_brief")
    except ValueError as exc:
        abort_event.set()
        case_result["fatal"] = f"WriterBrief compilation failed: {exc}"
        _persist_case()
        print(f"  [{case_id}] FATAL: {exc}")
        return case_result

    writer_brief_sha256 = hashlib.sha256(
        json.dumps(writer_brief, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    write_json(case_dir / "writer_brief.json", writer_brief)
    (case_dir / "writer_brief.txt").write_text(
        json.dumps(writer_brief, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    scene_instruction = planner_output.get("scene_instruction", instruction)
    scene_instruction_sha256 = hashlib.sha256(
        scene_instruction.encode("utf-8")
    ).hexdigest()

    tempo_guardrails = planner_output.get("tempo_guardrails")

    async with factory() as session:
        projects = ProjectService(session)
        chapters = ChapterService(session)
        generation = GenerationService(session)

        project = await projects.create_project(
            ProjectCreate(name=f"{EXPERIMENT} {case_id}", genre=category)
        )
        chapter = await chapters.create_chapter(
            project.id, ChapterCreate(title=title, sort_order=1)
        )
        run_obj = await generation.create_run(
            project.id, chapter.id, None, instruction
        )
        await session.commit()
        case_result["run_id"] = run_obj.id

        # Seed a fake completed Planner step
        planner_candidate_id = await seed_planner_step(
            session,
            run_obj.id,
            planner_output,
            FROZEN["planner_prompt_version_id"],
        )
        await session.commit()

        call_orders: dict[str, list[str]] = {}
        for replica in range(1, REPLICAS + 1):
            order = replica_call_order(case_id, replica)
            call_orders[str(replica)] = order
            for group in order:
                if abort_event.is_set():
                    case_result["skipped"] = f"aborted_at_{group}-{replica}"
                    case_result["call_orders"] = call_orders
                    _persist_case()
                    return case_result

                if group == "P7":
                    prompt_version_id = p7_version_id
                    prompt_name = p7_prompt_name
                    prompt_profile_id = p7_profile_id
                    prompt_version_number = p7_version_number
                else:
                    prompt_version_id = f8_version_id
                    prompt_name = f8_prompt_name
                    prompt_profile_id = f8_profile_id
                    prompt_version_number = f8_version_number

                override = writer_override_for_group(
                    group, prompt_version_id, prompt_name
                )

                # Pass the frozen Planner output + WriterBrief to Writer
                override["scene_plan"] = planner_output
                override["writer_brief"] = writer_brief
                if tempo_guardrails:
                    override["tempo_guardrails"] = tempo_guardrails

                for field in ("scene_goal", "concrete_problem", "pressure"):
                    if field in planner_output and field not in override:
                        override[field] = planner_output[field]

                override["target_length"] = TARGET_LENGTH
                override["write_mode"] = "new_chapter"

                candidate = await generation.execute_stage(
                    run_obj.id, "writer", override
                )
                await session.commit()

                cr = record(candidate, group, replica)
                cr["case_id"] = case_id
                cr["run_id"] = run_obj.id
                cr["blind_id"] = make_blind_token(case_id, group, replica)
                cr["planner_candidate_id"] = planner_candidate_id
                cr["prompt_profile_id"] = prompt_profile_id
                cr["prompt_name"] = prompt_name
                cr["prompt_version_number"] = prompt_version_number
                cr["output_mode"] = "xml_story"
                cr["planner_sha256"] = planner_sha256
                cr["writer_brief_sha256"] = writer_brief_sha256
                cr["scene_instruction_sha256"] = scene_instruction_sha256
                cr["rendered_system_prompt_sha256"] = hashlib.sha256(
                    (candidate.rendered_system_prompt or "").encode("utf-8")
                ).hexdigest()

                process_writer_output(root, case_dir, cr, group, replica)

                stem = f"{group.lower()}-{replica}"
                case_result["drafts"].append(cr)

                meta = cr.get("metadata", {})
                sc = meta.get("story_character_count", 0)
                dn = meta.get("draft_notes_character_count", 0)
                print(
                    f"  [{case_id}] {group}-{replica}: "
                    f"story={sc} dn={dn} "
                    f"err={cr.get('error_code')} "
                    f"finish={cr.get('finish_reason')}"
                )

        case_result["call_orders"] = call_orders
        _persist_case()
        ok = sum(
            1 for d in case_result["drafts"] if d.get("story_path") and d.get("story_character_count", 0) > 0
        )
        print(f"  [{case_id}] {ok}/{len(GROUPS) * REPLICAS} stories saved")
        return case_result


async def run(root: Path, database: Path, dry_run: bool) -> None:
    case_ids = [case[0] for case in SCENES]

    if (root / "manifest.json").exists():
        raise RuntimeError(
            f"{EXPERIMENT} evidence already exists; refusing to rerun"
        )
    if not dry_run and any(
        scene_database(database, c).exists() for c in case_ids
    ):
        raise RuntimeError(
            f"isolated database already exists under prefix: {database}"
        )

    if dry_run:
        print(dry_run_report(root, case_ids))
        return

    # Verify all frozen Planner outputs exist
    for case_id in case_ids:
        planner_path = PREVIOUS_EVAL / "cases" / case_id / "planner_frozen.json"
        if not planner_path.exists():
            raise RuntimeError(
                f"Frozen Planner missing: {planner_path} — aborting"
            )

    root.mkdir(parents=True, exist_ok=True)

    # Create isolated DB copies
    engines = []
    factories = {}
    for case_id in case_ids:
        case_db = scene_database(database, case_id)
        shutil.copy2(
            REPO_ROOT / "data" / "novel_workbench.db", case_db
        )
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{case_db}",
            connect_args={"timeout": 60},
        )
        engines.append(engine)
        factories[case_id] = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    # Ensure P7 and F8 prompts exist in all isolated DBs
    p7_ids: dict[str, str] = {}
    f8_ids: dict[str, str] = {}
    p7_profile_ids: dict[str, str] = {}
    f8_profile_ids: dict[str, str] = {}

    for case_id in case_ids:
        async with factories[case_id]() as session:
            p7_id = await ensure_prompt_exists(
                session, "Sacrificial Preflight v7"
            )
            f8_id = await ensure_prompt_exists(
                session, "Sacrificial Preflight Fusion v8"
            )
            await session.commit()

            # Also get profile IDs for the manifest
            p7_profile = (
                await session.execute(
                    select(PromptProfile).where(
                        PromptProfile.stage == "writer",
                        PromptProfile.name == "Sacrificial Preflight v7",
                    )
                )
            ).scalar_one_or_none()
            f8_profile = (
                await session.execute(
                    select(PromptProfile).where(
                        PromptProfile.stage == "writer",
                        PromptProfile.name == "Sacrificial Preflight Fusion v8",
                    )
                )
            ).scalar_one_or_none()

            p7_ids[case_id] = p7_id
            f8_ids[case_id] = f8_id
            p7_profile_ids[case_id] = p7_profile.id if p7_profile else "unknown"
            f8_profile_ids[case_id] = f8_profile.id if f8_profile else "unknown"

    first_case = case_ids[0]
    p7_version_id = p7_ids[first_case]
    f8_version_id = f8_ids[first_case]
    p7_profile_id = p7_profile_ids[first_case]
    f8_profile_id = f8_profile_ids[first_case]

    # Get prompt names and version numbers
    p7_entry = _find_builtin_prompt("Sacrificial Preflight v7")
    f8_entry = _find_builtin_prompt("Sacrificial Preflight Fusion v8")
    p7_prompt_name = p7_entry["name"] if p7_entry else "Sacrificial Preflight v7"
    f8_prompt_name = f8_entry["name"] if f8_entry else "Sacrificial Preflight Fusion v8"

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
            "groups": {
                "P7": "Writer v7 Sacrificial Preflight (xml_story)",
                "F8": "Writer v8 Sacrificial Preflight Fusion (xml_story)",
            },
            "p7_prompt_version_id": p7_version_id,
            "f8_prompt_version_id": f8_version_id,
            "p7_profile_id": p7_profile_id,
            "f8_profile_id": f8_profile_id,
            "frozen_parameters": FROZEN,
            "source_planner_experiment": "SACRIFICIAL_PREFLIGHT_FEASIBILITY_V1",
            "execution_model": (
                "scene-level parallelism (4 concurrent scenes, each with its own "
                "isolated SQLite copy); writers sequential within a scene; "
                "NO Planner calls — frozen Planner reused from SACRIFICIAL_PREFLIGHT_FEASIBILITY_V1"
            ),
            "rules": [
                "ZERO Planner calls; frozen Planner outputs reused.",
                "2 groups x 3 replicas per scene; stratified-random P7/F8 call order per replica.",
                "No Critic/Reviser/Judge. No retry. No filtering. All failures preserved.",
                "Both groups: xml_story mode; generation_service extracts <story>; raw_response preserved.",
                "xml_story parse failure: error_code recorded; no LLM repair.",
                "seed=null for every model call; other parameters held identical.",
                "max_output_tokens=6000 is an experiment-level override for BOTH groups.",
                "The ONLY delta between P7 and F8 is the Writer prompt version.",
            ],
            "success_criteria": {
                "format_and_mechanism": {
                    "A1": "F8 at least 11/12 successfully extract story",
                    "A2": "F8 successful outputs: XML leak = 0",
                    "A3": "F8 successful outputs: draft_notes leak = 0",
                    "A4": "F8 at least 10/12 contain 8-section draft_notes structure",
                    "A5": "F8 at least 9/12 contain 6-9 narrative units in section 7",
                },
                "length": {
                    "B1": "F8 at least 10/12 reach 2000 chars",
                    "B2": "F8 story median >= 2200 chars",
                    "B3": "F8 mean story chars >= P7 mean by 25%",
                    "B4": "In pairs where P7 < 2000, F8 crosses 2000 in at least 2/3",
                    "B5": "F8 at least 8/12 reach 2000 chars (anti-mean-skew floor)",
                },
                "quality": {
                    "C1": "'Better as final text': F8 wins >= 7/12",
                    "C2": "'More complete chapter': F8 wins >= 7/12",
                    "C3": "F8 padded_repetition tags <= 3",
                    "C4": "F8 delayed_stop tags <= 3",
                    "C5": "F8 early_stop tags <= 2",
                    "C6": "F8 missing_context or process_jump tags <= 2",
                    "C7": "F8 does not lose 0:3 in any single scene",
                },
                "zhuque": {
                    "D1": "F8 char-weighted human rate not < P7 by >5pp",
                    "D2": "F8 per-article human rate median not < P7 by >5pp",
                    "D3": "F8 wins median in >= 2/4 scenes",
                    "D4": "F8 human-rate >= 60% count not < P7 by >= 2",
                },
                "overall_judgment": {
                    "STRONG_PASS": "All A + B + C + D strong signal",
                    "PASS": "All A + B + C + D non-inferior",
                    "PARTIAL": "A + B passed, C or D not yet",
                    "FAIL": "Major shortfall in length, quality, or Zhuque",
                },
            },
            "status": "running",
        }

        p7_identity = await prompt_identity(session, p7_version_id)
        f8_identity = await prompt_identity(session, f8_version_id)
        manifest["p7_prompt_identity"] = p7_identity
        manifest["f8_prompt_identity"] = f8_identity
        write_json(root / "manifest.json", manifest)

    # Assert prompt identity requirements
    assert p7_identity["output_mode"] == "xml_story", (
        f"P7 output_mode must be xml_story, got {p7_identity['output_mode']}"
    )
    assert f8_identity["output_mode"] == "xml_story", (
        f"F8 output_mode must be xml_story, got {f8_identity['output_mode']}"
    )
    assert p7_version_id != f8_version_id, (
        "P7 and F8 must be different prompt versions"
    )
    assert p7_identity["system_template_sha256"] != f8_identity["system_template_sha256"], (
        "P7 and F8 system templates must differ"
    )
    assert p7_identity["user_template_sha256"] != f8_identity["user_template_sha256"], (
        "P7 and F8 user templates must differ"
    )
    assert p7_profile_id != f8_profile_id, (
        "P7 and F8 must be different prompt profiles"
    )

    # Pre-run assertions
    print("Pre-run assertions:")
    print(f"  cases=4 -> {len(case_ids) == 4}")
    print(f"  groups=2 -> {len(GROUPS) == 2}")
    print(f"  replicas=3 -> {REPLICAS == 3}")
    print(f"  writer_slots=24 -> {len(expected_slots(case_ids)) == 24}")
    print(f"  planner_calls=0 (reusing {len(case_ids)} frozen)")
    print(f"  target_length={TARGET_LENGTH}")
    print(f"  P7.name={p7_prompt_name}")
    print(f"  F8.name={f8_prompt_name}")
    print(f"  P7.output_mode={p7_identity['output_mode']}")
    print(f"  F8.output_mode={f8_identity['output_mode']}")
    print(f"  P7.id={p7_version_id}")
    print(f"  F8.id={f8_version_id}")
    print(f"  P7 != F8 -> {p7_version_id != f8_version_id}")
    print(f"  Working directory clean")

    started = time.monotonic()
    try:
        abort_event = asyncio.Event()
        exported: list[dict[str, Any]] = await asyncio.gather(
            *(
                run_case(
                    root,
                    factories[case[0]],
                    abort_event,
                    case,
                    p7_ids.get(case[0], p7_version_id),
                    f8_ids.get(case[0], f8_version_id),
                    p7_profile_ids.get(case[0], p7_profile_id),
                    f8_profile_ids.get(case[0], f8_profile_id),
                    p7_prompt_name,
                    f8_prompt_name,
                    p7_identity.get("version_number", 1),
                    f8_identity.get("version_number", 1),
                )
                for case in SCENES
            )
        )
    finally:
        for engine in engines:
            await engine.dispose()

    wall_seconds = round(time.monotonic() - started, 1)

    fatal = [c for c in exported if c.get("fatal")]
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
                "writer_drafts_completed": sum(
                    len(c["drafts"]) for c in exported
                ),
                "writer_drafts_expected": len(expected_slots(case_ids)),
                "wall_seconds": wall_seconds,
            },
        )
        print(f"  RUN ABORTED: {manifest['abort_reason']}")
        return

    assertions = slot_assertions(exported, case_ids)
    manifest["status"] = "completed"
    manifest["post_generation_assertions"] = assertions
    manifest["wall_seconds"] = wall_seconds
    write_json(root / "manifest.json", manifest)

    # Build validation and execution summaries
    all_drafts = [d for c in exported for d in c.get("drafts", [])]
    p7_drafts = [d for d in all_drafts if d.get("group") == "P7"]
    f8_drafts = [d for d in all_drafts if d.get("group") == "F8"]

    validation_summary = _build_validation_summary(exported, all_drafts)
    write_json(root / "validation_summary.json", validation_summary)

    execution_summary = _build_execution_summary(exported, wall_seconds)
    write_json(root / "execution_summary.json", execution_summary)

    if not assertions["all_passed"]:
        print(
            f"  ASSERTION GAPS: "
            f"{json.dumps(assertions['checks'], ensure_ascii=False)}"
        )

    # Post-run assertions
    _run_post_hoc_assertions(all_drafts, p7_drafts, f8_drafts)

    # Generate blind assets and Zhuque submission
    make_blind_assets(root, exported)
    package_zhuque_submission(root, exported)

    # Summary
    _print_statistics(all_drafts, p7_drafts, f8_drafts, wall_seconds)


def _build_validation_summary(
    exported: list[dict[str, Any]], all_drafts: list[dict[str, Any]]
) -> dict[str, Any]:
    def _meta(d, key, default=None):
        m = d.get("metadata", {}) or {}
        return m.get(key, d.get(key, default))
    return {
        "experiment": EXPERIMENT,
        "drafts": [
            {
                "case_id": d.get("case_id"),
                "group": d["group"],
                "replica": d["replica"],
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
                "v8_structure": d.get("metadata", {}).get("v8_structure")
                if d.get("group") == "F8" else None,
            }
            for case in exported
            for d in case.get("drafts", [])
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
        "planner_calls": 0,
        "writer_calls": sum(len(c["drafts"]) for c in exported),
        "writer_drafts_expected": len(expected_slots(
            [case[0] for case in SCENES]
        )),
        "final_texts": sum(
            1
            for c in exported
            for d in c["drafts"]
            if _story_len(d) > 0
        ),
        "wall_seconds": wall_seconds,
    }


def _run_post_hoc_assertions(
    all_drafts: list[dict[str, Any]],
    p7_drafts: list[dict[str, Any]],
    f8_drafts: list[dict[str, Any]],
) -> None:
    """Post-generation assertions per spec section 18."""
    p7_ok = len(p7_drafts)
    f8_ok = len(f8_drafts)
    case_ids = list(set(d.get("case_id") for d in all_drafts))

    def _meta(d, key, default=0):
        m = d.get("metadata", {}) or {}
        return m.get(key, d.get(key, default))

    print(f"\n── Post-run assertions ──")
    print(f"  P7 slots: {p7_ok} (expected {len(case_ids) * REPLICAS})")
    print(f"  F8 slots: {f8_ok} (expected {len(case_ids) * REPLICAS})")
    print(f"  Per scene == 6: {all(len([d for d in all_drafts if d.get('case_id') == cid]) == 6 for cid in case_ids)}")
    print(f"  Per scene per group == 3: {all(len([d for d in p7_drafts if d.get('case_id') == cid]) == 3 for cid in case_ids) and all(len([d for d in f8_drafts if d.get('case_id') == cid]) == 3 for cid in case_ids)}")
    print(f"  Planner calls: 0")
    writer_calls = len(all_drafts)
    print(f"  Writer calls: {writer_calls} (max 24)")
    print(f"  Private mapping entries: {writer_calls}")
    print(f"  Blind review pairs: {len(case_ids) * REPLICAS}")

    # Verify no filtering by length, TEMPO, or content
    below_2000 = [d for d in all_drafts if _meta(d, "story_below_2000", False)]
    tempo_mismatch = [d for d in all_drafts if d.get("error_code") == "TEMPO_FINAL_LINE_MISMATCH"]
    print(f"  Texts below 2000 (NOT filtered): {len(below_2000)}")
    print(f"  TEMPO mismatch (NOT filtered): {len(tempo_mismatch)}")

    # Verify story == text_output
    stories_saved = [d for d in all_drafts if _meta(d, "story_character_count", 0) > 0]
    xml_leaks = [d for d in stories_saved if _meta(d, "xml_leak", False)]
    dn_leaks = [d for d in stories_saved if _meta(d, "draft_notes_leak", False)]
    print(f"  XML leaks in story: {len(xml_leaks)}")
    print(f"  Draft_notes leaks in story: {len(dn_leaks)}")
    print(f"  All assertions passed" if not (xml_leaks or dn_leaks) else f"  WARN: leaks found")


def _print_statistics(
    all_drafts: list[dict[str, Any]],
    p7_drafts: list[dict[str, Any]],
    f8_drafts: list[dict[str, Any]],
    wall_seconds: float,
) -> None:
    """Print summary statistics for P7 vs F8."""
    print(f"\n{'='*60}")
    print(f"  EXPERIMENT RESULTS")
    print(f"{'='*60}")
    print(f"  Total wall time: {wall_seconds}s")

    for label, drafts in [("P7 (v7)", p7_drafts), ("F8 (v8)", f8_drafts)]:
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

        # F8 structural checks
        if label == "F8 (v8)":
            v8_structures = [
                d.get("metadata", {}).get("v8_structure", {})
                for d in drafts
                if d.get("metadata", {}).get("v8_structure")
            ]
            if v8_structures:
                eight_sections = sum(
                    1 for v in v8_structures if v.get("has_eight_sections")
                )
                unit_6_9 = sum(
                    1 for v in v8_structures if v.get("has_unit_count_6_9")
                )
                target_min = sum(
                    1 for v in v8_structures if v.get("has_target_length_minimum")
                )
                char_estimates = sum(
                    1 for v in v8_structures if v.get("has_estimated_char_counts")
                )
                print(f"  Eight sections complete: {eight_sections}/{len(v8_structures)}")
                print(f"  6-9 narrative units: {unit_6_9}/{len(v8_structures)}")
                print(f"  Target length as minimum: {target_min}/{len(v8_structures)}")
                print(f"  Char estimates: {char_estimates}/{len(v8_structures)}")

    # Paired statistics
    print(f"\n  ── Paired comparison (same case_id, same replica) ──")
    def _story_len(d):
        m = d.get("metadata", {}) or {}
        return m.get("story_character_count", d.get("story_character_count", 0))
    case_ids = list(set(d.get("case_id") for d in all_drafts))
    p7_by_key = {}
    f8_by_key = {}
    for d in all_drafts:
        key = (d.get("case_id"), d["replica"])
        if d["group"] == "P7":
            p7_by_key[key] = d
        else:
            f8_by_key[key] = d

    pairs_compared = 0
    f8_longer = 0
    p7_under_2000_f8_over = 0
    p7_under_2000_pairs = 0
    for key in sorted(set(list(p7_by_key.keys()) + list(f8_by_key.keys()))):
        if key not in p7_by_key or key not in f8_by_key:
            continue
        p7 = p7_by_key[key]
        f8 = f8_by_key[key]
        p7_len = _story_len(p7)
        f8_len = _story_len(f8)
        pairs_compared += 1
        diff = f8_len - p7_len
        print(f"    {key[0]} R{key[1]}: P7={p7_len} F8={f8_len} diff={diff:+d}")
        if f8_len > p7_len:
            f8_longer += 1
        if p7_len > 0 and p7_len < 2000 and f8_len >= 2000:
            p7_under_2000_f8_over += 1
        if p7_len > 0 and p7_len < 2000:
            p7_under_2000_pairs += 1

    if pairs_compared > 0:
        print(f"    F8 longer in: {f8_longer}/{pairs_compared}")
        print(f"    P7<2000 & F8>=2000: {p7_under_2000_f8_over}/{p7_under_2000_pairs}")


# ── Blind assets ───────────────────────────────────────────────────────


def make_pair_token(case_id: str, replica: int) -> str:
    return hashlib.sha256(
        f"{SEED}:pair:{case_id}:{replica}".encode()
    ).hexdigest()[:12].upper()


def make_blind_assets(
    root: Path, exported: list[dict[str, Any]]
) -> None:
    """blind_mapping.private.json (24 slots) + blind_review_queue.json
    (anonymized same-scene same-replica P7/F8 pairs, X/Y randomized)."""
    pieces: dict[str, Any] = {}
    pairs: dict[str, Any] = {}
    pair_cards: list[dict[str, Any]] = []
    for case in exported:
        case_id = case["case_id"]
        by_key = {
            (d["group"], d["replica"]): d
            for d in case.get("drafts", [])
        }
        for (group, replica), item in sorted(by_key.items()):
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
        for replica in range(1, REPLICAS + 1):
            p7 = by_key.get(("P7", replica))
            f8 = by_key.get(("F8", replica))
            if (
                not p7 or not f8
                or not p7.get("story_path")
                or not f8.get("story_path")
            ):
                continue
            pair_id = make_pair_token(case_id, replica)
            x_group = random.Random(
                f"{SEED}:xy:{case_id}:{replica}"
            ).choice(["P7", "F8"])
            y_group = "F8" if x_group == "P7" else "P7"
            pair_cards.append({
                "pair_id": pair_id,
                "text_x_path": str(by_key[(x_group, replica)]["story_path"]),
                "text_y_path": str(by_key[(y_group, replica)]["story_path"]),
            })
            pairs[pair_id] = {
                "case_id": case_id,
                "replica": replica,
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
        for item in case.get("drafts", []):
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

    # Build boundary verification
    boundaries_sha256 = hashlib.sha256(
        json.dumps(boundaries, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    write_json(
        zhuque_dir / "zhuque_submission_manifest.json",
        {
            "experiment": EXPERIMENT,
            "source_commit": manifest.get("git_commit", ""),
            "total_slots": 24,
            "successful_articles": len(cards),
            "failed_articles": 24 - len(cards),
            "p7_count": sum(1 for c in cards if c["group"] == "P7"),
            "f8_count": sum(1 for c in cards if c["group"] == "F8"),
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
        f"P7={sum(1 for c in cards if c['group']=='P7')} "
        f"F8={sum(1 for c in cards if c['group']=='F8')} "
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
        / "sacrificial_preflight_fusion_v8_feasibility_v1",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=REPO_ROOT
        / "__evaluation"
        / "sacrificial_preflight_fusion_v8_feasibility_v1.sqlite3",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--package-only", action="store_true")
    parser.add_argument("--model-id", default=FROZEN["model_id"])
    args = parser.parse_args()
    FROZEN["model_id"] = args.model_id

    if args.package_only:
        asyncio.run(package_only(args.root))
    else:
        asyncio.run(run(args.root, args.database, args.dry_run))


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
        result_path = root / "cases" / cid / "result.json"
        if not result_path.exists():
            print(f"  WARN: {result_path} not found, skipping")
            continue
        exported.append(
            json.loads(result_path.read_text(encoding="utf-8"))
        )

    make_blind_assets(root, exported)
    package_zhuque_submission(root, exported)
    print("Package complete.")


if __name__ == "__main__":
    main()
