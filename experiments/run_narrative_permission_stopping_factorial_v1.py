"""NARRATIVE_PERMISSION_STOPPING_FACTORIAL_V1 — 2x2 factorial experiment.

Groups (all on the production writer path: writer_input_mode="writer_brief",
frozen DB writer prompt v6, identical frozen parameters):

  A: CURRENT permission      + CURRENT stop   (pure production, no instruction)
  B: STRICT_LIMITED          + CURRENT stop
  C: CURRENT permission      + STRICT_STOP
  D: STRICT_LIMITED          + STRICT_STOP

8 scenes x 4 groups x 3 replicas = 96 Writer calls + 8 Planner calls = 104.

Discipline (pre-registered):
  - One frozen Planner per scene; all 12 Writers share it.
  - No Critic/Reviser/Judge. No retry. No filtering. No candidate selection.
  - All failures preserved; any existing text enters the blind queue,
    including TEMPO_FINAL_LINE_MISMATCH drafts.
  - D3: a Planner hard failure aborts the ENTIRE run immediately. The failed
    run is saved; no zhuque submission files are produced; no per-scene
    makeup runs. To continue, restart the full experiment in a new run dir.
  - Scenes run in parallel (one asyncio task per scene, each with its OWN
    isolated SQLite copy — GenerationService holds a write transaction
    across the LLM call, so a shared SQLite file would serialize or lock
    all concurrent calls); Writers inside a scene stay sequential. Every
    hash/boundary/blind artifact is derived per slot, so concurrency
    changes wall time only, never the evidence.
  - The provider/adapter does not support a model seed: recorded as null,
    other parameters held identical, reproducibility is never faked.
  - Call order is stratified-randomized per replica block and recorded.

Dry-run mode (--dry-run) prints the full plan without any LLM calls and
writes dry_run_report.txt. It does NOT write manifest.json, so a real run
can follow in the same directory.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.models.prompt import PromptVersion
from app.schemas.chapter import ChapterCreate
from app.schemas.narrative_generation_policy import (
    POLICY_VERSION,
    NarrativeGenerationPolicy,
    NarrativePermissionPolicy,
    StopDisciplinePolicy,
)
from app.schemas.project import ProjectCreate
from app.services.chapter_service import ChapterService
from app.services.generation_service import GenerationService
from app.services.narrative_generation_policy import (
    STRICT_LIMITED_INSTRUCTION,
    STRICT_STOP_INSTRUCTION,
    compile_generation_policy,
)
from app.services.narrative_permission_stop_validator import (
    validate_permission_stop,
)
from app.services.project_service import ProjectService
from app.services.writer_brief import compile_writer_input

EXPERIMENT = "NARRATIVE_PERMISSION_STOPPING_FACTORIAL_V1"
SEED = 20260721  # Runner-side randomization only. Never enters a model call.
REPLICAS = 3
GROUPS = ("A", "B", "C", "D")

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "planner_prompt_version_id": "f9052f8a-dc4e-5408-b14e-fc1badaf57f8",
    "writer_prompt_version_id": "f7760cd8-8048-4f3c-839c-e33333eb96fb",
    "temperature": 0.7,
    "top_p": 1.0,
    "planner_max_output_tokens": 12288,
    "max_output_tokens": 4000,
    "timeout_seconds": 300,
}

GROUP_POLICIES = {
    "A": NarrativeGenerationPolicy(
        permission=NarrativePermissionPolicy.CURRENT,
        stop=StopDisciplinePolicy.CURRENT,
    ),
    "B": NarrativeGenerationPolicy(
        permission=NarrativePermissionPolicy.STRICT_LIMITED,
        stop=StopDisciplinePolicy.CURRENT,
    ),
    "C": NarrativeGenerationPolicy(
        permission=NarrativePermissionPolicy.CURRENT,
        stop=StopDisciplinePolicy.STRICT_STOP,
    ),
    "D": NarrativeGenerationPolicy(
        permission=NarrativePermissionPolicy.STRICT_LIMITED,
        stop=StopDisciplinePolicy.STRICT_STOP,
    ),
}

OVERLAP_NOTICE = (
    "Frozen DB writer prompt v6 section 5 already contains a strong stop "
    "rule (stop at the stop fact; no coda, no psychological explanation, no "
    "relationship summary, no theme elevation). STRICT_STOP is therefore a "
    "small-delta treatment: a weak C-group main effect is an attribute of "
    "the variable, and must NOT be read as an instruction-injection failure."
)

SEED_NOTE = (
    "Provider/adapter exposes no model seed (LlmRequest has no seed field; "
    "DeepSeek chat/completions documents none). seed=null is recorded for "
    "every call; temperature/top_p/max_output_tokens/timeout/thinking are "
    "held identical across groups; reproducibility is not faked. The SEED "
    "constant only drives blind-token generation and call-order shuffling."
)

# ── Scene definitions: (case_id, category, title, scene_instruction) ──
# 4 old high-variance mechanism anchors (verbatim instructions) + 4 new
# matched scenes. Confirmed at the Phase 2 dry-run gate before any real call.
SCENES = (
    # ── Old anchors (mechanism reuse) ──
    ("AL-01", "校园误会", "撤回的作业评语",
     "课间，乔雨发现班主任在企业微信上给自己发了一条评语又撤回了，只看到预览里'你这次的……'四个字。同桌正拿着手机走过来。乔雨不能问班主任，也不能假装没看见。她必须根据这条被撤回的消息做个具体选择。停在新出现的事实。"),
    ("CO-04", "校园日常", "操场上错拿的水壶",
     "体育课自由活动时，路远发现自己的蓝色运动水壶被一个不认识的男生拿起来喝了一口。那个男生正往篮球场方向走，手里还拿着水壶。路远不能跑过去抢回来，也不能在操场上喊。他必须用一个现场物件让对方发现。停在水壶回到正确位置的事实。"),
    ("CO-05", "日常任务", "快递架上的同名包裹",
     "小区快递架上，向暖发现一个写着'向暖'的包裹——但收件地址不是自己的楼栋。真正的收件人可能就在附近。包裹不大，架子上还有其他未取件。向暖不能拆包裹验证，也不能拿错的东西回家。她必须用一个现场物件标记或通知。停在包裹归属出现新事实。"),
    ("ROMANCE-02", "恋爱日常", "未读消息",
     "合租屋厨房里，夏知看见韩川的手机亮起自己昨晚的未读消息，韩川却先把手机扣在桌上去洗菜。水已经开了，桌上只有两只碗。夏知不能偷看手机，也不能断言对方为何没回；她需要根据可见事实选择继续帮忙、离开或提出别的行动，并让代价和后果落在现场。"),
    # ── New matched scenes ──
    ("NM-01", "城市日常", "半截语音",
     "下班地铁上，林悄收到合租室友发来的一条语音，外放只听到前半句'你桌上那个蓝色文件夹我……'就被进站噪声盖过去，再听时语音已被对方撤回。蓝色文件夹里有她明天投标要用的文件。室友的电话正在占线。林悄不能假定对方动了文件夹，也不能等到家再确认。她必须在两站路之内做一个具体行动。停在新出现的事实。"),
    ("NM-02", "校园日常", "自习区错收的书",
     "图书馆自习区，周淇去接水回来，发现自己摊在桌上的考研单词书被邻座男生收进了他的书包——那本书里夹着她手写的租房合同草稿。男生还在低头做题，没有要走的意思。周淇不能当众翻他书包，也不能喊管理员。她必须用桌上的一个物件让对方自己发现收错了。停在单词书归属出现新事实。"),
    ("NM-03", "城市日常", "洗衣房的滚筒",
     "小区自助洗衣房里，方笛认为自己那台滚筒还没洗完——她记得设定的是一小时，现在才过去四十分钟。旁边等着用机器的老人说机器早停了，里面是他的衣服。方笛不能跟老人争，也不能直接把滚筒门拉开。滚筒玻璃上的水位和面板上的状态会证明谁记错了。她必须用一个可见事实处理这个争执。停在机器状态拆穿其中一方判断的事实。"),
    ("NM-04", "恋爱日常", "掉链子的自行车",
     "周日早上，合租的苏叶发现自己自行车的链条掉了，而室友沈一凡正蹲在门口修他自己的车。工具箱就摊在两人中间。苏叶从来没开口请他帮过忙，也不能把车子一推说'你顺便看看'。她必须提出一个具体的请求。停在请求被接受或被拒绝的可见事实。"),
)


# ── Pure helpers (unit-tested without LLM) ────────────────────────────


def planner_output_cap(model_id: str) -> int:
    return 12288 if model_id == "deepseek-v4-pro" else FROZEN["planner_max_output_tokens"]


def expected_slots(case_ids: list[str]) -> list[tuple[str, str, int]]:
    """The full 8 x 4 x 3 = 96 (case_id, group, replica) slot registry."""
    return [
        (case_id, group, replica)
        for case_id in case_ids
        for group in GROUPS
        for replica in range(1, REPLICAS + 1)
    ]


def writer_override_for_group(group: str) -> dict[str, Any]:
    """One group's Writer override. Group A carries no instruction keys at
    all — it is byte-identical to a production writer_brief call apart from
    the metadata passthrough."""
    policy = GROUP_POLICIES[group]
    compiled = compile_generation_policy(policy)
    override: dict[str, Any] = {
        "provider_id": FROZEN["provider_id"],
        "model_id": FROZEN["model_id"],
        "prompt_version_id": FROZEN["writer_prompt_version_id"],
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "writer_input_mode": "writer_brief",
        "_policy_metadata": {
            "group": group,
            "permission_policy": policy.permission.value,
            "stop_policy": policy.stop.value,
            "policy_version": policy.policy_version,
            "policy_hash": compiled.policy_hash,
            "instruction_hash": compiled.instruction_hash,
            "permission_instruction_hash": compiled.permission_instruction_hash,
            "stop_instruction_hash": compiled.stop_instruction_hash,
            "seed": None,
        },
    }
    if compiled.instruction_block:
        override["_instruction_block"] = compiled.instruction_block
        override["_instruction_hash"] = compiled.instruction_hash
    return override


def replica_call_order(case_id: str, replica: int, seed: int = SEED) -> list[str]:
    """Stratified-random group order inside one replica block."""
    order = list(GROUPS)
    random.Random(f"{seed}:{case_id}:{replica}").shuffle(order)
    return order


def make_blind_token(case_id: str, group: str, replica: int, seed: int = SEED) -> str:
    return hashlib.sha256(
        f"{seed}:{case_id}:{group}:{replica}".encode()
    ).hexdigest()[:12].upper()


def planner_error_is_fatal(error_code: str | None) -> bool:
    """D3: any Planner hard failure aborts the entire run."""
    return error_code is not None


def export_allowed(status: str) -> bool:
    """Zhuque submission files are produced only for a completed run."""
    return status == "completed"


# ── IO helpers ────────────────────────────────────────────────────────


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


# ── Recording ─────────────────────────────────────────────────────────


def record(candidate: Any, group: str, replica: int) -> dict[str, Any]:
    params = json.loads(candidate.parameters_json or "{}")
    metadata = params.get("policy_metadata") or {}
    return {
        "candidate_id": candidate.id,
        "attempt_number": candidate.attempt_number,
        "group": group,
        "replica": replica,
        "permission_policy": metadata.get("permission_policy"),
        "stop_policy": metadata.get("stop_policy"),
        "instruction_hash": metadata.get("instruction_hash"),
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


def make_blind_queue(root: Path, exported: list[dict[str, Any]]) -> None:
    cards = []
    private = {}
    for case in exported:
        case_id = case["case_id"]
        for item in case.get("drafts", []):
            if not item.get("text_output"):
                continue  # Hard failure without text: recorded, never queued.
            token = make_blind_token(case_id, item["group"], item["replica"])
            cards.append({"blind_id": token, "case_id": case_id, "text_path": item["text_path"]})
            private[token] = {
                "case_id": case_id,
                "group": item["group"],
                "permission_policy": item["permission_policy"],
                "stop_policy": item["stop_policy"],
                "policy_version": POLICY_VERSION,
                "replica": str(item["replica"]),
                "seed": None,
                "text_path": item["text_path"],
                "candidate_id": item["candidate_id"],
                "planner_candidate_id": case["planner"].get("candidate_id"),
                "error_code": item.get("error_code"),
                "tempo_final_line_mismatch": item["validation"]["tempo_final_line_mismatch"],
                "validator_codes": item["validation"]["validator_codes"],
                "rendered_user_prompt_sha256": item["rendered_user_prompt_sha256"],
                "instruction_hash": item["instruction_hash"],
            }
    random.Random(SEED).shuffle(cards)
    write_json(root / "blind_review_queue.json", cards)
    write_json(root / "blind_mapping.private.json", private)


def package_zhuque_submission(root: Path) -> None:
    """Package all drafts into the anonymous Zhuque submission."""
    queue_path = root / "blind_review_queue.json"
    if not queue_path.exists():
        raise FileNotFoundError(f"blind_review_queue.json not found in {root}")
    zhuque_dir = root / "zhuque"
    zhuque_dir.mkdir(parents=True, exist_ok=True)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    parts = []
    boundaries = []
    cursor = 0
    SEP = "\n\n\n\n\n"
    for ordinal_zero, card in enumerate(queue):
        ordinal = ordinal_zero + 1
        text_path = root / card["text_path"]
        raw = text_path.read_text(encoding="utf-8")
        text = raw.strip("\n").strip() or raw
        start = cursor
        parts.append(text)
        cursor += len(text)
        boundaries.append({
            "ordinal": ordinal, "blind_id": card["blind_id"],
            "start_char": start, "end_char": cursor,
            "character_count": len(text), "text_path": card["text_path"],
        })
        cursor += len(SEP)
        if ordinal < len(queue):
            parts.append(SEP)
    submission_text = "".join(parts)
    (zhuque_dir / "zhuque_submission_all.txt").write_text(submission_text, encoding="utf-8")
    write_json(zhuque_dir / "zhuque_blind_boundaries.json", boundaries)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    sha = hashlib.sha256(submission_text.encode("utf-8")).hexdigest()
    write_json(zhuque_dir / "zhuque_submission_manifest.json", {
        "experiment_id": manifest["experiment"],
        "source_commit": manifest.get("git_commit", ""),
        "total_articles": len(boundaries),
        "total_content_characters": sum(b["character_count"] for b in boundaries),
        "separator": "five newline characters",
        "submission_sha256": sha,
        "generated_at": subprocess.check_output(
            ["git", "log", "-1", "--format=%aI", "HEAD"], cwd=REPO_ROOT, text=True,
        ).strip(),
    })
    # Integrity assertions
    for b in boundaries:
        recovered = submission_text[b["start_char"]:b["end_char"]]
        original = (root / b["text_path"]).read_text(encoding="utf-8").strip("\n").strip()
        if not original:
            original = (root / b["text_path"]).read_text(encoding="utf-8")
        assert recovered == original, f"Recovery mismatch at {b['blind_id']}"
    assert len(boundaries) == len(queue)
    assert boundaries[-1]["end_char"] == len(submission_text)
    assert hashlib.sha256(submission_text.encode("utf-8")).hexdigest() == sha
    print(f"  Zhuque: {len(boundaries)} articles, {len(submission_text)} chars — all tests pass")


# ── Export assertions ─────────────────────────────────────────────────


def export_problems(root: Path, exported: list[dict[str, Any]], case_ids: list[str]) -> list[str]:
    """Pre-export slot assertions. Any problem blocks the zhuque packaging."""
    problems: list[str] = []
    queued = [
        (case["case_id"], item)
        for case in exported
        for item in case.get("drafts", [])
        if item.get("text_output")
    ]
    expected = expected_slots(case_ids)
    if len(queued) != len(expected):
        problems.append(f"blind queue would hold {len(queued)} texts, expected {len(expected)}")
    for group in GROUPS:
        count = len([q for q in queued if q[1]["group"] == group])
        if count != len(case_ids) * REPLICAS:
            problems.append(f"group {group} has {count} texts, expected {len(case_ids) * REPLICAS}")
    for case_id in case_ids:
        case_texts = [q for q in queued if q[0] == case_id]
        if len(case_texts) != len(GROUPS) * REPLICAS:
            problems.append(f"case {case_id} has {len(case_texts)} texts, expected {len(GROUPS) * REPLICAS}")
        for group in GROUPS:
            count = len([q for q in case_texts if q[1]["group"] == group])
            if count != REPLICAS:
                problems.append(f"case {case_id} group {group} has {count} texts, expected {REPLICAS}")
    for case_id, item in queued:
        if not (root / item["text_path"]).exists():
            problems.append(f"missing text file for {case_id} {item['group']}-{item['replica']}")
    return problems


# ── Prompt identity (frozen prompt facts) ─────────────────────────────


async def prompt_identity(session: AsyncSession, prompt_version_id: str) -> dict[str, Any]:
    row = (
        await session.execute(select(PromptVersion).where(PromptVersion.id == prompt_version_id))
    ).scalar_one_or_none()
    if row is None:
        return {"prompt_version_id": prompt_version_id, "found": False}
    return {
        "prompt_version_id": prompt_version_id,
        "found": True,
        "version_number": row.version_number,
        "output_mode": row.output_mode,
        "output_schema_name": row.output_schema_name,
        "system_template_sha256": hashlib.sha256(row.system_template.encode("utf-8")).hexdigest(),
        "user_template_sha256": hashlib.sha256(row.user_template.encode("utf-8")).hexdigest(),
    }


# ── Dry-run ───────────────────────────────────────────────────────────


def dry_run_report(root: Path, case_ids: list[str]) -> str:
    lines = [
        f"{EXPERIMENT} — DRY-RUN (no model calls)",
        "",
        f"Scenes: {len(SCENES)} | Groups: {list(GROUPS)} | Replicas: {REPLICAS}",
        f"Slots: {len(expected_slots(case_ids))} texts = {len(SCENES)} scenes x 4 groups x 3 replicas",
        f"Model calls: {len(SCENES)} Planner + {len(expected_slots(case_ids))} Writer = {len(SCENES) + len(expected_slots(case_ids))}",
        "",
        "── Frozen parameters (identical across all groups) ──",
        *[f"  {k} = {v}" for k, v in FROZEN.items()],
        "  writer_input_mode = writer_brief   writer_behavior_mode = None",
        "",
        "── Seed ──",
        f"  {SEED_NOTE}",
        "",
        "── Pre-registered overlap notice ──",
        f"  {OVERLAP_NOTICE}",
        "",
        "── Group deltas (the ONLY differences between groups) ──",
        "  A: no instruction block (pure production)",
        f"  B: STRICT_LIMITED instruction  sha256={compile_generation_policy(GROUP_POLICIES['B']).instruction_hash}",
        f"  C: STRICT_STOP instruction     sha256={compile_generation_policy(GROUP_POLICIES['C']).instruction_hash}",
        f"  D: STRICT_LIMITED + STRICT_STOP sha256={compile_generation_policy(GROUP_POLICIES['D']).instruction_hash}",
        "",
        "── STRICT_LIMITED instruction (verbatim) ──",
        STRICT_LIMITED_INSTRUCTION.strip(),
        "",
        "── STRICT_STOP instruction (verbatim) ──",
        STRICT_STOP_INSTRUCTION.strip(),
        "",
        "── Scenes and per-replica call orders ──",
    ]
    for case_id, category, title, instruction in SCENES:
        lines.append(f"  [{case_id}] {category} 《{title}》")
        lines.append(f"      instruction: {instruction}")
        for replica in range(1, REPLICAS + 1):
            lines.append(f"      replica {replica}: {' → '.join(replica_call_order(case_id, replica))}")
    lines += [
        "",
        "── Output paths ──",
        f"  root: {root}",
        "  cases/<CASE>/{planner.json, result.json, drafts/*.txt|json}",
        "  blind_review_queue.json | blind_mapping.private.json | manifest.json",
        "  generation_policy_summary.json | validation_summary.json | execution_summary.json",
        "  zhuque/{zhuque_submission_all.txt, zhuque_blind_boundaries.json, zhuque_submission_manifest.json}",
        "",
        "── Hash strategy ──",
        "  instruction_hash: sha256 of the exact instruction block appended to the prompt",
        "  rendered_user_prompt_sha256: sha256 of the final user prompt per candidate",
        "  zhuque_submission_all.txt: whole-file sha256 in zhuque_submission_manifest.json",
        "  prompt identity: version_number + template sha256 of planner/writer prompt rows",
        "",
        "── Cost upper bound ──",
        f"  Planner: {len(SCENES)} x max {FROZEN['planner_max_output_tokens']} output tokens = {len(SCENES) * FROZEN['planner_max_output_tokens']}",
        f"  Writer: {len(expected_slots(case_ids))} x max {FROZEN['max_output_tokens']} output tokens = {len(expected_slots(case_ids)) * FROZEN['max_output_tokens']}",
        f"  Total output-token ceiling ≈ {len(SCENES) * FROZEN['planner_max_output_tokens'] + len(expected_slots(case_ids)) * FROZEN['max_output_tokens']}",
        "",
        "── Failure discipline ──",
        "  Planner hard failure: abort entire run (D3), status=aborted, no zhuque files.",
        "  Writer/provider failures: recorded; any existing text (incl. TEMPO_FINAL_LINE_MISMATCH) queued.",
        "  Export blocked unless: queue=96, mapping=96, boundaries=96, texts=96,",
        "  per-group=24, per-case=12, per-case-group=3.",
        "",
        "── Execution ──",
        "  Scene-level parallelism: 8 concurrent scenes, sequential writers within a scene.",
        "  Each scene writes to its own isolated SQLite copy (the service holds a write",
        "  transaction across the LLM call; a shared file would serialize all calls).",
        "  All hash/boundary/blind artifacts are per-slot deterministic and order-independent.",
    ]
    report = "\n".join(lines)
    root.mkdir(parents=True, exist_ok=True)
    (root / "dry_run_report.txt").write_text(report + "\n", encoding="utf-8")
    return report


# ── Main run ──────────────────────────────────────────────────────────


async def run_case(
    root: Path,
    factory: async_sessionmaker,
    abort_event: asyncio.Event,
    case: tuple[str, str, str, str],
) -> dict[str, Any]:
    """One scene: 1 Planner + 12 Writers (sequential within the scene).

    Scenes are independent asyncio tasks sharing only the isolated SQLite
    file and the abort_event. The abort event is checked before every model
    call so a fatal Planner failure (D3) stops all remaining calls.
    """
    case_id, category, title, instruction = case
    case_dir = root / "cases" / case_id
    case_result: dict[str, Any] = {
        "case_id": case_id, "category": category, "title": title,
        "run_id": None,
        "planner": {},
        "drafts": [],
    }

    def _persist_case() -> None:
        write_json(case_dir / "result.json", case_result)

    async with factory() as session:
        projects = ProjectService(session)
        chapters = ChapterService(session)
        generation = GenerationService(session)

        if abort_event.is_set():
            case_result["skipped"] = "aborted_before_start"
            _persist_case()
            return case_result

        project = await projects.create_project(
            ProjectCreate(name=f"{EXPERIMENT} {case_id}", genre=category))
        chapter = await chapters.create_chapter(
            project.id, ChapterCreate(title=title, sort_order=1))
        run_obj = await generation.create_run(project.id, chapter.id, None, instruction)
        await session.commit()
        case_result["run_id"] = run_obj.id

        if abort_event.is_set():
            case_result["skipped"] = "aborted_before_planner"
            _persist_case()
            return case_result

        planner = await generation.execute_stage(run_obj.id, "planner", {
            "provider_id": FROZEN["provider_id"], "model_id": FROZEN["model_id"],
            "prompt_version_id": FROZEN["planner_prompt_version_id"],
            "temperature": FROZEN["temperature"], "top_p": FROZEN["top_p"],
            "max_output_tokens": FROZEN["planner_max_output_tokens"],
            "timeout_seconds": FROZEN["timeout_seconds"],
        })
        await session.commit()
        case_result["planner"] = {
            "candidate_id": planner.id,
            "error_code": planner.error_code,
            "error_message": planner.error_message,
        }

        if planner_error_is_fatal(planner.error_code):
            # D3: signal every other scene to stop before its next model call.
            abort_event.set()
            case_result["fatal"] = planner.error_code
            _persist_case()
            print(f"  [{case_id}] PLANNER FATAL: {planner.error_code} — aborting run (D3)")
            return case_result

        await generation.select_candidate(run_obj.id, "planner", planner.id)
        await session.commit()
        planner_output = json.loads(planner.parsed_output_json or "{}")
        write_json(case_dir / "planner.json", planner_output)

        try:
            writer_brief = compile_writer_input(planner_output, "writer_brief")
            stop_marker = str(writer_brief.get("stop_fact") or "")
        except ValueError:
            stop_marker = ""

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
                candidate = await generation.execute_stage(
                    run_obj.id, "writer", writer_override_for_group(group)
                )
                await session.commit()
                cr = record(candidate, group, replica)
                text = candidate.text_output or candidate.raw_response
                cr["validation"] = dataclasses.asdict(validate_permission_stop(
                    text,
                    stop_marker=stop_marker,
                    tempo_final_line_mismatch=(
                        candidate.error_code == "TEMPO_FINAL_LINE_MISMATCH"
                    ),
                ))
                if text:
                    tp = case_dir / "drafts" / f"{group.lower()}-{replica}.txt"
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    tp.write_text(text, encoding="utf-8")
                    cr["text_path"] = str(tp.relative_to(root))
                write_json(case_dir / "drafts" / f"{group.lower()}-{replica}.json", cr)
                case_result["drafts"].append(cr)

        case_result["call_orders"] = call_orders
        _persist_case()
        ok = sum(1 for d in case_result["drafts"] if not d.get("error_code"))
        print(f"  [{case_id}] {ok}/{len(GROUPS) * REPLICAS} ok")
        return case_result


def scene_database(database: Path, case_id: str) -> Path:
    """Each scene gets its own isolated SQLite copy.

    GenerationService.execute_stage flushes (write-locking the DB) before
    the LLM call and commits only after it returns, so a shared SQLite file
    would hold the write lock across entire model calls — serializing or
    locking every concurrent scene. Per-scene copies remove all contention;
    the JSON/txt artifacts remain the canonical evidence.
    """
    return database.with_name(f"{database.stem}_{case_id}.sqlite3")


async def run(root: Path, database: Path, dry_run: bool, *, zhuque_only: bool = False) -> None:
    import time

    case_ids = [case[0] for case in SCENES]

    if zhuque_only:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if not export_allowed(manifest.get("status", "")):
            raise RuntimeError(f"Refusing to package: manifest status is {manifest.get('status')!r}")
        package_zhuque_submission(root)
        return

    if (root / "manifest.json").exists():
        raise RuntimeError(f"{EXPERIMENT} evidence already exists; refusing to rerun")
    if not dry_run and any(scene_database(database, c).exists() for c in case_ids):
        raise RuntimeError(f"isolated database already exists under prefix: {database}")

    if dry_run:
        print(dry_run_report(root, case_ids))
        return

    root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "experiment": EXPERIMENT,
        "git_commit": git_commit(),
        "seed": SEED,
        "model_seed": None,
        "seed_note": SEED_NOTE,
        "replicas_per_group": REPLICAS,
        "case_ids": case_ids,
        "groups": {
            "A": "CURRENT permission + CURRENT stop (pure production, no instruction)",
            "B": "STRICT_LIMITED + CURRENT stop",
            "C": "CURRENT permission + STRICT_STOP",
            "D": "STRICT_LIMITED + STRICT_STOP",
        },
        "writer_input_mode": "writer_brief",
        "writer_behavior_mode": None,
        "policy_version": POLICY_VERSION,
        "writer_prompt_version_id": FROZEN["writer_prompt_version_id"],
        "planner_prompt_version_id": FROZEN["planner_prompt_version_id"],
        "frozen_parameters": FROZEN,
        "overlap_notice": OVERLAP_NOTICE,
        "execution_model": (
            "scene-level parallelism (8 concurrent scenes, each with its own "
            "isolated SQLite copy); writers sequential within a scene; all "
            "hash/boundary/blind artifacts are per-slot deterministic and "
            "order-independent"
        ),
        "rules": [
            "One Planner call per scene; all 12 Writers share the frozen Planner output.",
            "4 groups x 3 replicas per scene; stratified-random call order per replica block.",
            "No Critic/Reviser/Judge. No retry. No filtering. All failures preserved.",
            "Any existing text enters the blind queue, including TEMPO_FINAL_LINE_MISMATCH drafts.",
            "Planner hard failure aborts the entire run (D3); no per-scene makeup runs.",
            "All groups use third person; no first-person arms; no narrative_route modes.",
            "seed=null for every model call; other parameters held identical.",
        ],
        "status": "running",
    }
    write_json(root / "manifest.json", manifest)

    engines = []
    started = time.monotonic()
    try:
        factories = {}
        for case_id in case_ids:
            case_db = scene_database(database, case_id)
            shutil.copy2(REPO_ROOT / "data" / "novel_workbench.db", case_db)
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{case_db}",
                connect_args={"timeout": 60},
            )
            engines.append(engine)
            factories[case_id] = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

        async with factories[case_ids[0]]() as session:
            manifest["writer_prompt_identity"] = await prompt_identity(
                session, FROZEN["writer_prompt_version_id"]
            )
            manifest["planner_prompt_identity"] = await prompt_identity(
                session, FROZEN["planner_prompt_version_id"]
            )
            write_json(root / "manifest.json", manifest)

        abort_event = asyncio.Event()
        # asyncio.gather preserves submission order, so `exported` stays in
        # SCENES order regardless of actual completion order.
        exported: list[dict[str, Any]] = await asyncio.gather(
            *(
                run_case(root, factories[case[0]], abort_event, case)
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
        manifest["abort_reason"] = (
            f"Planner hard failure in case {fatal[0]['case_id']}: "
            f"{fatal[0]['planner'].get('error_code')} — "
            f"{fatal[0]['planner'].get('error_message')}"
        )
        manifest["wall_seconds"] = wall_seconds
        write_json(root / "manifest.json", manifest)
        write_json(root / "execution_summary.json", {
            "experiment": EXPERIMENT,
            "status": "aborted",
            "abort_reason": manifest["abort_reason"],
            "writer_drafts_completed": sum(len(c["drafts"]) for c in exported),
            "writer_drafts_expected": len(expected_slots(case_ids)),
            "wall_seconds": wall_seconds,
        })
        print(f"  RUN ABORTED (D3): {manifest['abort_reason']}")
        return

    # Export gate: all slot assertions must pass, otherwise no zhuque files.
    problems = export_problems(root, exported, case_ids)
    manifest["status"] = "completed" if not problems else "export_blocked"
    manifest["export_problems"] = problems
    manifest["wall_seconds"] = wall_seconds
    write_json(root / "manifest.json", manifest)

    make_blind_queue(root, exported)
    if not problems:
        package_zhuque_submission(root)

    write_json(root / "generation_policy_summary.json", {
        "experiment": EXPERIMENT,
        "policy_version": POLICY_VERSION,
        "groups": {
            group: {
                "permission_policy": GROUP_POLICIES[group].permission.value,
                "stop_policy": GROUP_POLICIES[group].stop.value,
                "instruction_block": compile_generation_policy(GROUP_POLICIES[group]).instruction_block,
                "instruction_hash": compile_generation_policy(GROUP_POLICIES[group]).instruction_hash,
                "policy_hash": compile_generation_policy(GROUP_POLICIES[group]).policy_hash,
            }
            for group in GROUPS
        },
        "instruction_texts": {
            "STRICT_LIMITED": STRICT_LIMITED_INSTRUCTION,
            "STRICT_STOP": STRICT_STOP_INSTRUCTION,
        },
        "writer_prompt_identity": manifest.get("writer_prompt_identity"),
        "planner_prompt_identity": manifest.get("planner_prompt_identity"),
        "frozen_parameters": FROZEN,
        "model_seed": None,
        "seed_note": SEED_NOTE,
        "overlap_notice": OVERLAP_NOTICE,
    })

    write_json(root / "validation_summary.json", {
        "experiment": EXPERIMENT,
        "drafts": [
            {
                "case_id": case["case_id"],
                "group": item["group"],
                "replica": item["replica"],
                **item["validation"],
            }
            for case in exported
            for item in case["drafts"]
        ],
    })

    write_json(root / "execution_summary.json", {
        "experiment": EXPERIMENT,
        "status": manifest["status"],
        "writer_drafts_completed": sum(
            1 for c in exported for d in c["drafts"] if not d.get("error_code")
        ),
        "writer_drafts_expected": len(expected_slots(case_ids)),
        "export_problems": problems,
    })
    if problems:
        print(f"  EXPORT BLOCKED: {len(problems)} problem(s); no zhuque files produced")
        for problem in problems:
            print(f"    - {problem}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=REPO_ROOT / "__evaluation" / "narrative_permission_stopping_factorial_v1")
    parser.add_argument("--database", type=Path,
                        default=REPO_ROOT / "__evaluation" / "narrative_permission_stopping_factorial_v1.sqlite3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--zhuque-only", action="store_true")
    parser.add_argument("--model-id", default=FROZEN["model_id"])
    args = parser.parse_args()
    FROZEN["model_id"] = args.model_id
    FROZEN["planner_max_output_tokens"] = planner_output_cap(args.model_id)
    asyncio.run(run(args.root, args.database, args.dry_run, zhuque_only=args.zhuque_only))


if __name__ == "__main__":
    main()
