"""SACRIFICIAL_PREFLIGHT_FEASIBILITY_V1 — sacrificial preflight feasibility.

Groups (same frozen Planner, same WriterBrief, same frozen parameters;
the ONLY deltas are prompt version and output_mode):

  A: Writer v6 ("默认场景写作", plain_text) — stable baseline.
  P: Writer v7 ("Sacrificial Preflight v7", xml_story) —
     <draft_notes> sacrificial layer + <story> retained prose.

4 scenes x 2 groups x 3 replicas = 24 Writer calls.  ZERO Planner calls.

Discipline (pre-registered):
  - Reuse frozen Planner outputs from SACRIFICIAL_ERROR_CHANNEL_FEASIBILITY_V1.
  - No Critic/Reviser/Judge. No retry. No filtering.
  - P group: generation_service extracts <story> via xml_story mode;
    raw_response preserved with draft_notes; text_output = story only.
  - Extraction failures preserved as-is; no LLM repair.
  - provider/model does not support seed: recorded as null.
  - Call order (A→P or P→A) stratified-randomized per replica and recorded.

Dry-run mode (--dry-run) prints the full plan without any LLM calls.
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

EXPERIMENT = "SACRIFICIAL_PREFLIGHT_FEASIBILITY_V1"
SEED = 20260720
REPLICAS = 3
GROUPS = ("A", "P")

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "writer_v6_prompt_version_id": "f7760cd8-8048-4f3c-839c-e33333eb96fb",
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

GROUP_A_INSTRUCTION = """
## 篇幅要求（在既有规则之上追加）
正式正文目标为1800—2200个中文字符。不得为了凑字数重复动作、解释意义或延长stop_state后的内容。
""".strip()

# Group P uses the v7 prompt directly — no instruction block needed.
# v7 internally handles: draft_notes 300-600 chars, story 1800-2200 chars.

PREVIOUS_EVAL = REPO_ROOT / "__evaluation" / "sacrificial_error_channel_feasibility_v1"

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


def replica_call_order(case_id: str, replica: int, seed: int = SEED) -> list[str]:
    order = list(GROUPS)
    random.Random(f"{seed}:{case_id}:{replica}").shuffle(order)
    return order


def make_blind_token(
    case_id: str, group: str, replica: int, seed: int = SEED
) -> str:
    return (
        hashlib.sha256(f"{seed}:{case_id}:{group}:{replica}".encode())
        .hexdigest()[:12]
        .upper()
    )


def scene_database(database: Path, case_id: str) -> Path:
    return database.with_name(f"{database.stem}_{case_id}.sqlite3")


def _v7_prompt_entry() -> dict | None:
    for entry in BUILTIN_PROMPTS:
        if entry["stage"] == "writer" and entry["output_mode"] == "xml_story":
            return entry
    return None


async def ensure_writer_v7_exists(session: AsyncSession) -> str:
    """Ensure the Writer v7 prompt profile + version exist in this DB.
    Returns the PromptVersion.id for v7."""
    entry = _v7_prompt_entry()
    if entry is None:
        raise RuntimeError("Writer v7 entry not found in BUILTIN_PROMPTS")

    # Check if v7 profile already exists
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
        # Profile exists; return latest version
        await session.refresh(existing, ["versions"])
        if existing.versions:
            return existing.versions[-1].id
        raise RuntimeError("Writer v7 profile exists but has no versions")

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
    path = PREVIOUS_EVAL / "cases" / case_id / "planner.json"
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
    """Create a completed planner step + candidate in the DB without any LLM call.
    This satisfies the Writer's dependency on a completed planner stage.
    Returns the candidate_id for the seeded planner candidate."""
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    # Find the planner step for this run
    stmt = (
        sa_select(GenerationStep)
        .where(
            GenerationStep.run_id == run_id,
            GenerationStep.stage == "planner",
        )
    )
    result = await session.execute(stmt)
    step = result.scalar_one()

    # Create a fake candidate with the frozen Planner output
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

    # Mark planner step as completed with this candidate selected
    step.status = "completed"
    step.selected_candidate_id = candidate.id
    await session.flush()

    return candidate.id


# ── Recording ──────────────────────────────────────────────────────────


def record(candidate: Any, group: str, replica: int) -> dict[str, Any]:
    params = json.loads(candidate.parameters_json or "{}")
    metadata = params.get("policy_metadata") or {}
    return {
        "candidate_id": candidate.id,
        "attempt_number": candidate.attempt_number,
        "group": group,
        "replica": replica,
        "instruction_hash": metadata.get("instruction_hash")
        or params.get("instruction_hash"),
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


def process_writer_draft(
    root: Path,
    case_dir: Path,
    cr: dict[str, Any],
    *,
    is_xml_story: bool = False,
) -> None:
    """Save raw output and compute character counts.
    For xml_story mode (Group P): text_output is already the extracted <story>.
    For plain_text mode (Group A): text_output is the raw prose.
    """
    text = cr.get("text_output") or cr.get("raw_response") or ""
    stem = f"{cr['group'].lower()}-{cr['replica']}"

    # Always save the raw LLM output (includes draft_notes for Group P)
    raw_path = case_dir / "raw" / f"{stem}.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(text, encoding="utf-8")
    cr["raw_output_path"] = str(raw_path.relative_to(root))

    # For Group P, also save the FULL raw_response (XML with draft_notes)
    # separately for audit, since text_output is just <story>
    if is_xml_story and cr.get("raw_response"):
        full_xml_path = case_dir / "raw" / f"{stem}_full_xml.txt"
        full_xml_path.parent.mkdir(parents=True, exist_ok=True)
        full_xml_path.write_text(cr["raw_response"], encoding="utf-8")
        cr["full_xml_output_path"] = str(full_xml_path.relative_to(root))

    raw_len = len((cr.get("raw_response") or "").strip())
    text_len = len(text.strip())

    # Extract draft_notes character count for Group P
    draft_notes_len = 0
    raw_resp = cr.get("raw_response") or ""
    if is_xml_story and raw_resp:
        dn_match = re.search(
            r"<draft_notes>(.*?)</draft_notes>",
            raw_resp,
            re.DOTALL | re.IGNORECASE,
        )
        if dn_match:
            draft_notes_len = len(dn_match.group(1).strip())

    cr["raw_character_count"] = raw_len
    cr["text_character_count"] = text_len
    cr["draft_notes_character_count"] = draft_notes_len

    shortfall = bool(text.strip()) and text_len < 1800
    cr["validation"] = {
        "text_character_count": text_len,
        "draft_notes_character_count": draft_notes_len,
        "text_length_shortfall": shortfall,
        "validator_codes": (
            ["TEXT_LENGTH_SHORTFALL"] if shortfall else []
        ),
    }

    if text.strip():
        cr["text_path"] = cr["raw_output_path"]
    cr["tempo_final_line_mismatch"] = (
        cr.get("error_code") == "TEMPO_FINAL_LINE_MISMATCH"
    )


# ── Writer overrides ───────────────────────────────────────────────────


def writer_override_for_group(
    group: str, prompt_version_id: str, is_v7: bool
) -> dict[str, Any]:
    """Build Writer execute_stage override for one group."""
    override: dict[str, Any] = {
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
            "prompt": "v7_sacrificial_preflight" if is_v7 else "v6_baseline",
            "seed": None,
        },
    }

    if not is_v7:
        # Group A: add minimal length instruction
        override["_instruction_block"] = GROUP_A_INSTRUCTION
        override["_instruction_hash"] = instruction_hash(GROUP_A_INSTRUCTION)
        override["_policy_metadata"]["instruction_hash"] = instruction_hash(
            GROUP_A_INSTRUCTION
        )

    return override


# ── Slot assertions ────────────────────────────────────────────────────


def slot_assertions(
    exported: list[dict[str, Any]], case_ids: list[str]
) -> dict[str, Any]:
    drafts = [
        (c["case_id"], d) for c in exported for d in c.get("drafts", [])
    ]
    queued = [(cid, d) for cid, d in drafts if d.get("text_path")]
    checks = {
        "writer_slots": len(drafts)
        == len(expected_slots(case_ids)),
        "group_A_texts": len(
            [q for q in queued if q[1]["group"] == "A"]
        )
        == len(case_ids) * REPLICAS,
        "group_P_texts": len(
            [q for q in queued if q[1]["group"] == "P"]
        )
        == len(case_ids) * REPLICAS,
        "per_case_6": all(
            len([q for q in queued if q[0] == cid])
            == len(GROUPS) * REPLICAS
            for cid in case_ids
        ),
        "per_case_group_3": all(
            len(
                [
                    q
                    for q in queued
                    if q[0] == cid and q[1]["group"] == g
                ]
            )
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
        "  A: Writer v6 (plain_text) + minimal length instruction",
        "  P: Writer v7 (xml_story) — Sacrificial Preflight",
        "",
        "── Frozen parameters (identical across both groups) ──",
        *[f"  {k} = {v}" for k, v in FROZEN.items()],
        "",
        "── Seed ──",
        f"  {SEED_NOTE}",
        "",
        "── Group A instruction (verbatim) ──",
        GROUP_A_INSTRUCTION,
        "",
        "── Group P: uses v7 prompt internally (no extra instruction) ──",
        "  v7 handles draft_notes (300-600 chars) + story (1800-2200 chars)",
        "",
        "── Scenes (Planner frozen from previous experiment) ──",
    ]
    for case_id, category, title, instruction in SCENES:
        planner_path = (
            PREVIOUS_EVAL / "cases" / case_id / "planner.json"
        )
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
        "  cases/<CASE>/{planner_frozen.json, result.json, raw/}",
        "  manifest.json | execution_summary.json | validation_summary.json",
        "",
        "── Failure discipline ──",
        "  Frozen Planner missing: abort entire run immediately.",
        "  Writer failures: recorded as-is; no retry; other slots continue.",
        "  Group P xml_story parse failure: error_code recorded; no LLM repair.",
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
    writer_v7_version_id: str,
) -> dict[str, Any]:
    """One scene: 6 Writers (A×3 + P×3, sequential within scene).
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

    # Compile WriterBrief from frozen Planner
    try:
        writer_brief = compile_writer_input(planner_output, "writer_brief")
    except ValueError as exc:
        abort_event.set()
        case_result["fatal"] = f"WriterBrief compilation failed: {exc}"
        _persist_case()
        print(f"  [{case_id}] FATAL: {exc}")
        return case_result

    # Extract tempo_guardrails as a dict (needed by execute_stage)
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

        # Seed a fake completed Planner step so Writer dependency is satisfied
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
                    case_result["skipped"] = (
                        f"aborted_at_{group}-{replica}"
                    )
                    case_result["call_orders"] = call_orders
                    _persist_case()
                    return case_result

                is_v7 = group == "P"
                prompt_version_id = (
                    writer_v7_version_id
                    if is_v7
                    else FROZEN["writer_v6_prompt_version_id"]
                )
                override = writer_override_for_group(
                    group, prompt_version_id, is_v7
                )

                # Pass the frozen Planner output + WriterBrief to Writer
                override["scene_plan"] = planner_output
                override["writer_brief"] = writer_brief
                if tempo_guardrails:
                    override["tempo_guardrails"] = tempo_guardrails

                # Extract chapter contract fields from Planner
                for field in (
                    "scene_goal",
                    "concrete_problem",
                    "pressure",
                ):
                    if field in planner_output and field not in override:
                        override[field] = planner_output[field]

                override["target_length"] = 2000  # 1800-2200 range
                override["write_mode"] = "new_chapter"

                candidate = await generation.execute_stage(
                    run_obj.id, "writer", override
                )
                await session.commit()

                cr = record(candidate, group, replica)
                process_writer_draft(
                    root, case_dir, cr, is_xml_story=is_v7
                )

                stem = f"{group.lower()}-{replica}"
                write_json(case_dir / "raw" / f"{stem}.json", cr)
                case_result["drafts"].append(cr)

                print(
                    f"  [{case_id}] {group}-{replica}: "
                    f"text={cr.get('text_character_count')} "
                    f"dn={cr.get('draft_notes_character_count')} "
                    f"err={cr.get('error_code')}"
                )

        case_result["call_orders"] = call_orders
        _persist_case()
        ok = sum(
            1 for d in case_result["drafts"] if d.get("text_path")
        )
        print(f"  [{case_id}] {ok}/{len(GROUPS) * REPLICAS} final texts")
        return case_result


async def run(
    root: Path, database: Path, dry_run: bool
) -> None:
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

    # Verify all frozen Planner outputs exist BEFORE any model calls
    for case_id in case_ids:
        planner_path = PREVIOUS_EVAL / "cases" / case_id / "planner.json"
        if not planner_path.exists():
            raise RuntimeError(
                f"Frozen Planner missing: {planner_path} — "
                f"cannot reconstruct; aborting before any model calls"
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

    # Ensure Writer v7 exists in all isolated DBs and get its version ID
    writer_v7_ids: dict[str, str] = {}
    for case_id in case_ids:
        async with factories[case_id]() as session:
            v7_id = await ensure_writer_v7_exists(session)
            await session.commit()
            writer_v7_ids[case_id] = v7_id

    first_case = case_ids[0]
    writer_v7_version_id = writer_v7_ids[first_case]

    # Collect prompt identities from first isolated DB
    async with factories[first_case]() as session:
        manifest: dict[str, Any] = {
            "experiment": EXPERIMENT,
            "git_commit": git_commit(),
            "seed": SEED,
            "model_seed": None,
            "seed_note": SEED_NOTE,
            "replicas_per_group": REPLICAS,
            "case_ids": case_ids,
            "groups": {
                "A": "Writer v6 baseline (plain_text, minimal length instruction)",
                "P": "Writer v7 Sacrificial Preflight (xml_story, draft_notes + story)",
            },
            "writer_v6_prompt_version_id": FROZEN[
                "writer_v6_prompt_version_id"
            ],
            "writer_v7_prompt_version_id": writer_v7_version_id,
            "frozen_parameters": FROZEN,
            "group_A_instruction_hash": instruction_hash(
                GROUP_A_INSTRUCTION
            ),
            "source_planner_experiment": "SACRIFICIAL_ERROR_CHANNEL_FEASIBILITY_V1",
            "execution_model": (
                "scene-level parallelism (4 concurrent scenes, each with its own "
                "isolated SQLite copy); writers sequential within a scene; "
                "NO Planner calls — frozen Planner reused from previous experiment"
            ),
            "rules": [
                "ZERO Planner calls; frozen Planner outputs reused from SACRIFICIAL_ERROR_CHANNEL_FEASIBILITY_V1.",
                "2 groups x 3 replicas per scene; stratified-random A/P call order per replica.",
                "No Critic/Reviser/Judge. No retry. No filtering. All failures preserved.",
                "Group P: xml_story mode; generation_service extracts <story>; raw_response preserved with <draft_notes>.",
                "Group P xml_story parse failure: error_code recorded; no LLM repair.",
                "seed=null for every model call; other parameters held identical.",
                "max_output_tokens=6000 is an experiment-level override for BOTH groups; product defaults untouched.",
            ],
            "status": "running",
        }

        manifest["writer_v6_prompt_identity"] = await prompt_identity(
            session, FROZEN["writer_v6_prompt_version_id"]
        )
        manifest["writer_v7_prompt_identity"] = await prompt_identity(
            session, writer_v7_version_id
        )
        write_json(root / "manifest.json", manifest)

    # Assert prompt identity requirements
    v6_id = manifest["writer_v6_prompt_identity"]
    v7_id = manifest["writer_v7_prompt_identity"]
    assert v6_id["output_mode"] == "plain_text", (
        f"v6 output_mode must be plain_text, got {v6_id['output_mode']}"
    )
    assert v7_id["output_mode"] == "xml_story", (
        f"v7 output_mode must be xml_story, got {v7_id['output_mode']}"
    )
    assert (
        FROZEN["writer_v6_prompt_version_id"]
        != writer_v7_version_id
    ), "v6 and v7 must be different prompt versions"

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
                    writer_v7_ids.get(
                        case[0], writer_v7_version_id
                    ),
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
                "writer_drafts_expected": len(
                    expected_slots(case_ids)
                ),
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

    # Build validation summary
    all_drafts = [
        d for c in exported for d in c.get("drafts", [])
    ]
    write_json(
        root / "validation_summary.json",
        {
            "experiment": EXPERIMENT,
            "post_generation_assertions": assertions,
            "drafts": [
                {
                    "case_id": case["case_id"],
                    "group": item["group"],
                    "replica": item["replica"],
                    "error_code": item.get("error_code"),
                    "tempo_final_line_mismatch": item.get(
                        "tempo_final_line_mismatch"
                    ),
                    "raw_character_count": item.get(
                        "raw_character_count"
                    ),
                    "text_character_count": item.get(
                        "text_character_count"
                    ),
                    "draft_notes_character_count": item.get(
                        "draft_notes_character_count"
                    ),
                    "instruction_hash": item.get(
                        "instruction_hash"
                    ),
                    "rendered_user_prompt_sha256": item.get(
                        "rendered_user_prompt_sha256"
                    ),
                    **(item.get("validation") or {}),
                }
                for case in exported
                for item in case.get("drafts", [])
            ],
        },
    )

    write_json(
        root / "execution_summary.json",
        {
            "experiment": EXPERIMENT,
            "status": manifest["status"],
            "planner_calls": 0,
            "writer_calls": sum(
                len(c["drafts"]) for c in exported
            ),
            "writer_drafts_expected": len(
                expected_slots(case_ids)
            ),
            "final_texts": sum(
                1
                for c in exported
                for d in c["drafts"]
                if d.get("text_path")
            ),
            "wall_seconds": wall_seconds,
        },
    )

    if not assertions["all_passed"]:
        print(
            f"  ASSERTION GAPS: "
            f"{json.dumps(assertions['checks'], ensure_ascii=False)}"
        )

    make_blind_assets(root, exported)
    package_zhuque_submission(root, exported)


# ── Blind assets ───────────────────────────────────────────────────────


def make_pair_token(case_id: str, replica: int, seed: int = SEED) -> str:
    return hashlib.sha256(
        f"{seed}:pair:{case_id}:{replica}".encode()
    ).hexdigest()[:12].upper()


def make_blind_assets(
    root: Path, exported: list[dict[str, Any]]
) -> None:
    """blind_mapping.private.json (all 24 slots) + blind_review_queue.json
    (anonymized same-scene same-replica A/P pairs, X/Y randomized)."""
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
            pieces[token] = {
                "blind_id": token,
                "case_id": case_id,
                "group": group,
                "replica": replica,
                "text_path": item.get("text_path"),
                "raw_output_path": item.get("raw_output_path"),
                "full_xml_output_path": item.get("full_xml_output_path"),
                "text_character_count": item.get("text_character_count"),
                "draft_notes_character_count": item.get(
                    "draft_notes_character_count"
                ),
                "raw_character_count": item.get("raw_character_count"),
                "candidate_id": item.get("candidate_id"),
                "instruction_hash": item.get("instruction_hash"),
                "error_code": item.get("error_code"),
                "tempo_final_line_mismatch": item.get(
                    "tempo_final_line_mismatch"
                ),
                "rendered_user_prompt_sha256": item.get(
                    "rendered_user_prompt_sha256"
                ),
            }
        for replica in range(1, REPLICAS + 1):
            a = by_key.get(("A", replica))
            p = by_key.get(("P", replica))
            if (
                not a
                or not p
                or not a.get("text_path")
                or not p.get("text_path")
            ):
                continue
            pair_id = make_pair_token(case_id, replica)
            x_group = random.Random(
                f"{SEED}:xy:{case_id}:{replica}"
            ).choice(["A", "P"])
            y_group = "P" if x_group == "A" else "A"
            pair_cards.append(
                {
                    "pair_id": pair_id,
                    "text_x_path": by_key[(x_group, replica)][
                        "text_path"
                    ],
                    "text_y_path": by_key[(y_group, replica)][
                        "text_path"
                    ],
                }
            )
            pairs[pair_id] = {
                "case_id": case_id,
                "replica": replica,
                "x_group": x_group,
                "y_group": y_group,
                "x_blind_id": make_blind_token(
                    case_id, x_group, replica
                ),
                "y_blind_id": make_blind_token(
                    case_id, y_group, replica
                ),
            }
    random.Random(SEED).shuffle(pair_cards)
    write_json(
        root / "blind_mapping.private.json",
        {"pieces": pieces, "pairs": pairs},
    )
    write_json(root / "blind_review_queue.json", pair_cards)


def package_zhuque_submission(
    root: Path, exported: list[dict[str, Any]]
) -> None:
    """Package final retained texts (A prose / P story only) into the
    anonymous Zhuque submission. draft_notes NEVER enters the submission."""
    zhuque_dir = root / "zhuque"
    zhuque_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for case in exported:
        for item in case.get("drafts", []):
            if not item.get("text_path"):
                continue
            cards.append(
                {
                    "blind_id": make_blind_token(
                        case["case_id"],
                        item["group"],
                        item["replica"],
                    ),
                    "text_path": item["text_path"],
                }
            )
    random.Random(SEED).shuffle(cards)
    parts = []
    boundaries = []
    cursor = 0
    SEP = "\n\n\n\n\n"
    for ordinal_zero, card in enumerate(cards):
        ordinal = ordinal_zero + 1
        raw = (root / card["text_path"]).read_text(encoding="utf-8")
        text = raw.strip("\n").strip() or raw
        start = cursor
        parts.append(text)
        cursor += len(text)
        boundaries.append(
            {
                "ordinal": ordinal,
                "blind_id": card["blind_id"],
                "start_char": start,
                "end_char": cursor,
                "character_count": len(text),
                "text_path": card["text_path"],
            }
        )
        cursor += len(SEP)
        if ordinal < len(cards):
            parts.append(SEP)
    submission_text = "".join(parts)
    (zhuque_dir / "zhuque_submission_all.txt").write_text(
        submission_text, encoding="utf-8"
    )
    write_json(
        zhuque_dir / "zhuque_blind_boundaries.json", boundaries
    )
    manifest = json.loads(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    sha = hashlib.sha256(submission_text.encode("utf-8")).hexdigest()
    write_json(
        zhuque_dir / "zhuque_submission_manifest.json",
        {
            "experiment_id": manifest["experiment"],
            "source_commit": manifest.get("git_commit", ""),
            "total_articles": len(boundaries),
            "total_content_characters": sum(
                b["character_count"] for b in boundaries
            ),
            "separator": "five newline characters",
            "submission_sha256": sha,
            "generated_at": subprocess.check_output(
                ["git", "log", "-1", "--format=%aI", "HEAD"],
                cwd=REPO_ROOT,
                text=True,
            ).strip(),
        },
    )
    # Boundary recovery verification
    for b in boundaries:
        recovered = submission_text[
            b["start_char"] : b["end_char"]
        ]
        original = (
            (root / b["text_path"])
            .read_text(encoding="utf-8")
            .strip("\n")
            .strip()
        )
        if not original:
            original = (root / b["text_path"]).read_text(
                encoding="utf-8"
            )
        assert (
            recovered == original
        ), f"Recovery mismatch at {b['blind_id']}"
    assert len(boundaries) == len(cards)
    if boundaries:
        assert boundaries[-1]["end_char"] == len(submission_text)
    assert (
        hashlib.sha256(submission_text.encode("utf-8")).hexdigest()
        == sha
    )
    print(
        f"  Zhuque: {len(boundaries)} articles, "
        f"{len(submission_text)} chars — all tests pass"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT
        / "__evaluation"
        / "sacrificial_preflight_feasibility_v1",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=REPO_ROOT
        / "__evaluation"
        / "sacrificial_preflight_feasibility_v1.sqlite3",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--package-only", action="store_true")
    parser.add_argument(
        "--model-id", default=FROZEN["model_id"]
    )
    args = parser.parse_args()
    FROZEN["model_id"] = args.model_id

    if args.package_only:
        asyncio.run(package_only(args.root))
    else:
        asyncio.run(run(args.root, args.database, args.dry_run))


async def package_only(root: Path) -> None:
    """Re-process existing experiment output to generate blind assets
    and Zhuque submission pack. No model calls."""
    manifest = json.loads(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("status") != "completed":
        raise RuntimeError(
            f"Experiment not completed (status={manifest.get('status')}); "
            "refusing to package"
        )
    case_ids = manifest["case_ids"]
    exported = []
    for cid in case_ids:
        result_path = root / "cases" / cid / "result.json"
        exported.append(
            json.loads(result_path.read_text(encoding="utf-8"))
        )

    make_blind_assets(root, exported)
    package_zhuque_submission(root, exported)
    print("Package complete.")


if __name__ == "__main__":
    main()
