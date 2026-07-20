"""SACRIFICIAL_ERROR_CHANNEL_FEASIBILITY_V1 — sacrificial error channel feasibility.

Groups (same Planner, same WriterBrief, same frozen DB writer prompt v6,
same frozen parameters for both groups; the ONLY delta is the instruction):

  A: length-matched baseline — one minimal length instruction, plain prose.
  E: sacrificial error channel — 5–7 <unit> blocks, each with a deletable
     <discard> and a retained <core>; only concatenated core is kept.

4 scenes x 2 groups x 3 replicas = 24 Writer calls + 4 Planner calls = 28.

Discipline (pre-registered):
  - One frozen Planner per scene; all 6 Writers share it.
  - No Critic/Reviser/Judge. No retry. No filtering. No candidate selection.
  - No LLM repair of broken XML; no silent fallback to raw XML as final text.
  - All failures preserved as-is.
  - Planner hard failure aborts the ENTIRE run immediately; no zhuque files.
  - Scenes run in parallel (one asyncio task per scene, each with its OWN
    isolated SQLite copy); Writers inside a scene stay sequential.
  - The provider/adapter does not support a model seed: recorded as null.
  - Call order (A→E or E→A) is stratified-randomized per replica and recorded.

Dry-run mode (--dry-run) prints the full plan without any LLM calls and
writes dry_run_report.txt. It does NOT write manifest.json.
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
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.models.prompt import PromptVersion
from app.schemas.chapter import ChapterCreate
from app.schemas.project import ProjectCreate
from app.services.chapter_service import ChapterService
from app.services.generation_service import GenerationService
from app.services.project_service import ProjectService
from app.services.writer_brief import compile_writer_input

EXPERIMENT = "SACRIFICIAL_ERROR_CHANNEL_FEASIBILITY_V1"
SEED = 20260720  # Runner-side randomization only. Never enters a model call.
REPLICAS = 3
GROUPS = ("A", "E")

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "planner_prompt_version_id": "f9052f8a-dc4e-5408-b14e-fc1badaf57f8",
    "writer_prompt_version_id": "f7760cd8-8048-4f3c-839c-e33333eb96fb",
    "temperature": 0.7,
    "top_p": 1.0,
    "planner_max_output_tokens": 12288,
    # Experiment-level override (spec V): identical for BOTH groups, sized for
    # Group E's full output (discard 700–1000 + core 1800–2200 + tags).
    # Product defaults are NOT modified.
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
输出一篇可以独立阅读的完整场景正文，保留字数目标为 1800–2200 字。不得通过重复动作、解释含义、或在 stop_state 之后延展内容来凑字数。
""".strip()

SACRIFICIAL_CHANNEL_INSTRUCTION = """
## 献祭式错误通道（在既有规则之上追加的输出格式）
本场景改为按「叙事单元」输出。全文输出 5–7 个叙事单元，严格使用以下 XML 结构：

<unit id="1">
<discard reason="类型">
可删除内容
</discard>
<core>
正式正文
</core>
</unit>

一、discard 的任务：在每个局部叙事时刻，先输出你最容易产生、但不应进入最终正文的低质量表达——直白解释当下人物心理、把其他人物的动机当成事实陈述、未经现场证据证实的推断、氛围概括、关系变化总结、陈词滥调的修辞、重复确认、stop_state 触发后的多余收束。
二、discard 的 reason 只能使用以下八种：mind_explanation / cross_mind / atmosphere_summary / relationship_summary / cliche_expression / unverified_inference / repeated_confirmation / post_stop_coda。
三、discard 禁止：引入新人物、新地点、新物件、新证据；创设新的背景事实；改动时间线；完成关键动作；解决核心问题；发生不可逆事件；创设后续 core 所依赖的信息。discard 只能承载「错误表达候选」，不能承载「故事事实」。
四、core 必须：与同一 unit 的 discard 处理同一个局部叙事时刻；不是把 discard 换一种说法改写；不复用 discard 的错误叙事功能；不依赖 discard 才能被理解；不引用 discard 独有的信息；不假定 discard 中的内容已经发生；通过动作、对话、物件与可见后果推进；完成 Planner 要求的核心事件；全部 core 拼接后构成连续完整的正文；stop_state 触发后停止生成。
五、字数目标：discard 合计 700–1000 字；core 合计 1800–2200 字；XML 标签不计入字数。
六、你展示的不是分析过程。discard 是最终输出格式中可删除的低质量文本，不是思维链。
""".strip()

GROUP_INSTRUCTIONS = {
    "A": GROUP_A_INSTRUCTION,
    "E": SACRIFICIAL_CHANNEL_INSTRUCTION,
}

DISCARD_REASONS = (
    "mind_explanation",
    "cross_mind",
    "atmosphere_summary",
    "relationship_summary",
    "cliche_expression",
    "unverified_inference",
    "repeated_confirmation",
    "post_stop_coda",
)

# Recorded only, never auto-judged as errors (spec IX.6).
CONTEXT_DEPENDENCY_WORDS = (
    "刚才", "方才", "又", "再次", "仍然", "继续", "这才", "先前", "依旧",
)

CORE_MIN_CHARS = 1800
UNIT_COUNT_RANGE = (5, 7)

# ── Scene definitions (verbatim from the factorial runner; spec III.3) ──
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


# ── Pure helpers (unit-tested without LLM) ────────────────────────────


def planner_output_cap(model_id: str) -> int:
    return 12288 if model_id == "deepseek-v4-pro" else FROZEN["planner_max_output_tokens"]


def expected_slots(case_ids: list[str]) -> list[tuple[str, str, int]]:
    """The full 4 x 2 x 3 = 24 (case_id, group, replica) slot registry."""
    return [
        (case_id, group, replica)
        for case_id in case_ids
        for group in GROUPS
        for replica in range(1, REPLICAS + 1)
    ]


def instruction_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def writer_override_for_group(group: str) -> dict[str, Any]:
    """One group's Writer override. Identical frozen parameters for both
    groups; the ONLY delta is the instruction block."""
    block = GROUP_INSTRUCTIONS[group]
    return {
        "provider_id": FROZEN["provider_id"],
        "model_id": FROZEN["model_id"],
        "prompt_version_id": FROZEN["writer_prompt_version_id"],
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "writer_input_mode": "writer_brief",
        "_instruction_block": block,
        "_instruction_hash": instruction_hash(block),
        "_policy_metadata": {
            "experiment": EXPERIMENT,
            "group": group,
            "channel": "plain_length_matched" if group == "A" else "sacrificial_error_channel",
            "instruction_hash": instruction_hash(block),
            "seed": None,
        },
    }


def replica_call_order(case_id: str, replica: int, seed: int = SEED) -> list[str]:
    """Stratified-random A/E order inside one replica block."""
    order = list(GROUPS)
    random.Random(f"{seed}:{case_id}:{replica}").shuffle(order)
    return order


def make_blind_token(case_id: str, group: str, replica: int, seed: int = SEED) -> str:
    return hashlib.sha256(
        f"{seed}:{case_id}:{group}:{replica}".encode()
    ).hexdigest()[:12].upper()


def make_pair_token(case_id: str, replica: int, seed: int = SEED) -> str:
    return hashlib.sha256(
        f"{seed}:pair:{case_id}:{replica}".encode()
    ).hexdigest()[:12].upper()


def planner_error_is_fatal(error_code: str | None) -> bool:
    """Any Planner hard failure aborts the entire run."""
    return error_code is not None


def export_allowed(status: str) -> bool:
    """Zhuque submission files are produced only for a completed run."""
    return status == "completed"


# ── Sacrificial-channel parsing (deterministic; no LLM repair) ────────


def _clean(text: str | None) -> str:
    return (text or "").strip()


def extract_units(raw: str) -> dict[str, Any]:
    """Extract <unit> blocks from Group E raw output.

    Order (spec VIII):
      1. Strict XML parse (wrapped in a synthetic root);
      2. Conservative regex fallback over complete <core>...</core>;
      3. CORE_PARSE_FAILED if no core at all.

    Returns {extract_status, units:[{id, discard, discard_reason, core}],
             core_text, discard_text}.
    """
    units: list[dict[str, Any]] = []
    status = "complete"
    try:
        root_el = ET.fromstring(f"<root>{raw}</root>")
        for unit_el in root_el.iter("unit"):
            discard_el = unit_el.find("discard")
            core_el = unit_el.find("core")
            units.append({
                "id": unit_el.get("id"),
                "discard": _clean(discard_el.text) if discard_el is not None else "",
                "discard_reason": (discard_el.get("reason") if discard_el is not None else None),
                "core": _clean(core_el.text) if core_el is not None else "",
            })
        if not any(u["core"] for u in units):
            raise ET.ParseError("no core content in parsed units")
    except ET.ParseError:
        cores = re.findall(r"<core>(.*?)</core>", raw, re.S)
        discards = re.findall(r"<discard[^>]*>(.*?)</discard>", raw, re.S)
        reasons = re.findall(r'<discard[^>]*reason="([^"]*)"', raw)
        if not cores:
            return {
                "extract_status": "CORE_PARSE_FAILED",
                "units": [],
                "core_text": "",
                "discard_text": "",
            }
        status = "recovered"
        units = [
            {
                "id": str(i + 1),
                "discard": _clean(discards[i]) if i < len(discards) else "",
                "discard_reason": reasons[i] if i < len(reasons) else None,
                "core": _clean(cores[i]),
            }
            for i in range(len(cores))
        ]
    return {
        "extract_status": status,
        "units": units,
        # Spec VIII.3: core pieces joined with two newlines, in unit order.
        "core_text": "\n\n".join(u["core"] for u in units if u["core"]),
        "discard_text": "\n\n".join(u["discard"] for u in units if u["discard"]),
    }


def validate_units(extraction: dict[str, Any]) -> dict[str, Any]:
    """Minimal deterministic checks (spec IX). No semantic judgement."""
    codes: list[str] = []
    units = extraction["units"]
    core_text = extraction["core_text"]
    status = extraction["extract_status"]

    xml_parsable = status == "complete"
    if status == "CORE_PARSE_FAILED":
        codes.append("CORE_PARSE_FAILED")
    if status == "recovered":
        codes.append("XML_RECOVERED")

    unit_count = len(units)
    if status != "CORE_PARSE_FAILED" and not (UNIT_COUNT_RANGE[0] <= unit_count <= UNIT_COUNT_RANGE[1]):
        codes.append("UNIT_COUNT_OUT_OF_RANGE")
    if any(not u["discard"] or not u["core"] for u in units):
        codes.append("UNIT_MISSING_PART")

    core_character_count = len(core_text)
    core_length_shortfall = status != "CORE_PARSE_FAILED" and core_character_count < CORE_MIN_CHARS
    if core_length_shortfall:
        codes.append("CORE_LENGTH_SHORTFALL")

    if re.search(r"</?(?:unit|core|discard)\b", core_text):
        codes.append("XML_TAGS_IN_CORE")

    context_words = [w for w in CONTEXT_DEPENDENCY_WORDS if w in core_text]

    # All semantic questions (mind-reading, causality, persona, true
    # core/discard dependence, stop_state position) are deferred to humans.
    codes.append("MANUAL_REVIEW_REQUIRED")

    return {
        "xml_parsable": xml_parsable,
        "unit_count": unit_count,
        "core_character_count": core_character_count,
        "core_length_shortfall": core_length_shortfall,
        "context_dependency_words": context_words,
        "validator_codes": codes,
    }


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
        "instruction_hash": metadata.get("instruction_hash") or params.get("instruction_hash"),
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


def process_group_e_draft(root: Path, case_dir: Path, cr: dict[str, Any]) -> None:
    """Parse one Group E raw output into raw/discard/core artifacts."""
    raw = cr.get("text_output") or cr.get("raw_response") or ""
    group, replica = cr["group"], cr["replica"]
    stem = f"{group.lower()}-{replica}"

    raw_path = case_dir / "raw" / f"{stem}.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(raw, encoding="utf-8")
    cr["raw_output_path"] = str(raw_path.relative_to(root))

    extraction = extract_units(raw)
    validation = validate_units(extraction)
    cr["extract_status"] = extraction["extract_status"]
    cr["unit_count"] = validation["unit_count"]
    cr["units"] = extraction["units"]
    cr["validation"] = validation

    cr["raw_character_count"] = len(raw.strip())
    cr["discard_character_count"] = len(extraction["discard_text"])
    cr["core_character_count"] = validation["core_character_count"]
    cr["discard_ratio"] = (
        round(cr["discard_character_count"] / cr["raw_character_count"], 4)
        if cr["raw_character_count"] else 0.0
    )

    if extraction["discard_text"]:
        dp = case_dir / "discard" / f"{stem}.txt"
        dp.parent.mkdir(parents=True, exist_ok=True)
        dp.write_text(extraction["discard_text"], encoding="utf-8")
        cr["discard_output_path"] = str(dp.relative_to(root))
    if extraction["core_text"]:
        cp = case_dir / "core" / f"{stem}.txt"
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(extraction["core_text"], encoding="utf-8")
        cr["core_output_path"] = str(cp.relative_to(root))
        # Only concatenated core is ever queued (spec VIII).
        cr["text_path"] = cr["core_output_path"]
    cr["tempo_final_line_mismatch"] = cr.get("error_code") == "TEMPO_FINAL_LINE_MISMATCH"


def process_group_a_draft(root: Path, case_dir: Path, cr: dict[str, Any]) -> None:
    """Group A: plain prose; raw text IS the final text."""
    text = cr.get("text_output") or cr.get("raw_response") or ""
    stem = f"{cr['group'].lower()}-{cr['replica']}"
    raw_path = case_dir / "raw" / f"{stem}.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(text, encoding="utf-8")
    cr["raw_output_path"] = str(raw_path.relative_to(root))
    cr["raw_character_count"] = len(text.strip())
    cr["discard_character_count"] = 0
    cr["discard_ratio"] = 0.0
    cr["core_character_count"] = cr["raw_character_count"]
    cr["unit_count"] = None
    cr["extract_status"] = "plain_text"
    core_short = bool(text.strip()) and cr["raw_character_count"] < CORE_MIN_CHARS
    cr["validation"] = {
        "xml_parsable": None,
        "unit_count": None,
        "core_character_count": cr["raw_character_count"],
        "core_length_shortfall": core_short,
        "context_dependency_words": [
            w for w in CONTEXT_DEPENDENCY_WORDS if w in text
        ],
        "validator_codes": (["CORE_LENGTH_SHORTFALL"] if core_short else [])
        + ["MANUAL_REVIEW_REQUIRED"],
    }
    if text.strip():
        cr["text_path"] = cr["raw_output_path"]
    cr["tempo_final_line_mismatch"] = cr.get("error_code") == "TEMPO_FINAL_LINE_MISMATCH"


# ── Blind assets ──────────────────────────────────────────────────────


def make_blind_assets(root: Path, exported: list[dict[str, Any]]) -> None:
    """blind_mapping.private.json (all 24 slots) + blind_review_queue.json
    (anonymized same-scene same-replica A/E pairs, X/Y randomized)."""
    pieces: dict[str, Any] = {}
    pairs: dict[str, Any] = {}
    pair_cards: list[dict[str, Any]] = []
    for case in exported:
        case_id = case["case_id"]
        by_key = {(d["group"], d["replica"]): d for d in case.get("drafts", [])}
        for (group, replica), item in sorted(by_key.items()):
            token = make_blind_token(case_id, group, replica)
            pieces[token] = {
                "blind_id": token,
                "case_id": case_id,
                "group": group,
                "replica": replica,
                "text_path": item.get("text_path"),
                "raw_output_path": item.get("raw_output_path"),
                "discard_output_path": item.get("discard_output_path"),
                "core_output_path": item.get("core_output_path"),
                "core_character_count": item.get("core_character_count"),
                "discard_character_count": item.get("discard_character_count"),
                "extract_status": item.get("extract_status"),
                "validator_codes": (item.get("validation") or {}).get("validator_codes"),
                "candidate_id": item.get("candidate_id"),
                "planner_candidate_id": case["planner"].get("candidate_id"),
                "instruction_hash": item.get("instruction_hash"),
                "error_code": item.get("error_code"),
                "tempo_final_line_mismatch": item.get("tempo_final_line_mismatch"),
                "rendered_user_prompt_sha256": item.get("rendered_user_prompt_sha256"),
            }
        for replica in range(1, REPLICAS + 1):
            a = by_key.get(("A", replica))
            e = by_key.get(("E", replica))
            if not a or not e or not a.get("text_path") or not e.get("text_path"):
                continue
            pair_id = make_pair_token(case_id, replica)
            x_group = random.Random(f"{SEED}:xy:{case_id}:{replica}").choice(["A", "E"])
            y_group = "E" if x_group == "A" else "A"
            pair_cards.append({
                "pair_id": pair_id,
                "text_x_path": by_key[(x_group, replica)]["text_path"],
                "text_y_path": by_key[(y_group, replica)]["text_path"],
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
    write_json(root / "blind_mapping.private.json", {"pieces": pieces, "pairs": pairs})
    write_json(root / "blind_review_queue.json", pair_cards)


def package_zhuque_submission(root: Path, exported: list[dict[str, Any]]) -> None:
    """Package final retained texts (A prose / E core only) into the
    anonymous Zhuque submission. discard NEVER enters the submission."""
    zhuque_dir = root / "zhuque"
    zhuque_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for case in exported:
        for item in case.get("drafts", []):
            if not item.get("text_path"):
                continue  # Failure without final text: recorded, never queued.
            cards.append({
                "blind_id": make_blind_token(case["case_id"], item["group"], item["replica"]),
                "text_path": item["text_path"],
            })
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
        boundaries.append({
            "ordinal": ordinal, "blind_id": card["blind_id"],
            "start_char": start, "end_char": cursor,
            "character_count": len(text), "text_path": card["text_path"],
        })
        cursor += len(SEP)
        if ordinal < len(cards):
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
    for b in boundaries:
        recovered = submission_text[b["start_char"]:b["end_char"]]
        original = (root / b["text_path"]).read_text(encoding="utf-8").strip("\n").strip()
        if not original:
            original = (root / b["text_path"]).read_text(encoding="utf-8")
        assert recovered == original, f"Recovery mismatch at {b['blind_id']}"
    assert len(boundaries) == len(cards)
    if boundaries:
        assert boundaries[-1]["end_char"] == len(submission_text)
    assert hashlib.sha256(submission_text.encode("utf-8")).hexdigest() == sha
    print(f"  Zhuque: {len(boundaries)} articles, {len(submission_text)} chars — all tests pass")


# ── Slot assertions ───────────────────────────────────────────────────


def slot_assertions(exported: list[dict[str, Any]], case_ids: list[str]) -> dict[str, Any]:
    """Post-generation assertions (spec X). Writer failures are recorded,
    not retried — assertions report the as-is state and never block."""
    drafts = [(c["case_id"], d) for c in exported for d in c.get("drafts", [])]
    queued = [(cid, d) for cid, d in drafts if d.get("text_path")]
    checks = {
        "writer_slots": len(drafts) == len(expected_slots(case_ids)),
        "planner_slots": len([c for c in exported if c.get("planner", {}).get("candidate_id")]) == len(case_ids),
        "group_A_texts": len([q for q in queued if q[1]["group"] == "A"]) == len(case_ids) * REPLICAS,
        "group_E_texts": len([q for q in queued if q[1]["group"] == "E"]) == len(case_ids) * REPLICAS,
        "per_case_6": all(
            len([q for q in queued if q[0] == cid]) == len(GROUPS) * REPLICAS for cid in case_ids
        ),
        "per_case_group_3": all(
            len([q for q in queued if q[0] == cid and q[1]["group"] == g]) == REPLICAS
            for cid in case_ids for g in GROUPS
        ),
        "private_mapping_slots": len(drafts) == 24,
    }
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "drafts_total": len(drafts),
        "queued_texts": len(queued),
        "expected_texts": len(expected_slots(case_ids)),
    }


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
    slots = expected_slots(case_ids)
    lines = [
        f"{EXPERIMENT} — DRY-RUN (no model calls)",
        "",
        f"Scenes: {len(SCENES)} | Groups: {list(GROUPS)} | Replicas: {REPLICAS}",
        f"Slots: {len(slots)} texts = {len(SCENES)} scenes x 2 groups x 3 replicas",
        f"Model calls: {len(SCENES)} Planner + {len(slots)} Writer = {len(SCENES) + len(slots)} (hard cap 28)",
        "",
        "── Pre-generation assertions ──",
        f"  cases=4 -> {len(case_ids) == 4}",
        f"  groups=2 -> {len(GROUPS) == 2}",
        f"  replicas=3 -> {REPLICAS == 3}",
        f"  writer_slots=24 -> {len(slots) == 24}",
        f"  planner_slots=4 -> {len(case_ids) == 4}",
        "",
        "── Frozen parameters (identical across both groups) ──",
        *[f"  {k} = {v}" for k, v in FROZEN.items()],
        "  writer_input_mode = writer_brief   writer_behavior_mode = None",
        "",
        "── Seed ──",
        f"  {SEED_NOTE}",
        "",
        "── Group deltas (the ONLY differences between groups) ──",
        f"  A: length-matched instruction  sha256={instruction_hash(GROUP_A_INSTRUCTION)}",
        f"  E: sacrificial channel instruction sha256={instruction_hash(SACRIFICIAL_CHANNEL_INSTRUCTION)}",
        "",
        "── Group A instruction (verbatim) ──",
        GROUP_A_INSTRUCTION,
        "",
        "── Group E instruction (verbatim) ──",
        SACRIFICIAL_CHANNEL_INSTRUCTION,
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
        "  cases/<CASE>/{planner.json, result.json, raw/, discard/, core/}",
        "  blind_review_queue.json | blind_mapping.private.json | manifest.json",
        "  validation_summary.json | execution_summary.json | dry_run_report.txt",
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
        f"  Writer: {len(slots)} x max {FROZEN['max_output_tokens']} output tokens = {len(slots) * FROZEN['max_output_tokens']}",
        f"  Total output-token ceiling ≈ {len(SCENES) * FROZEN['planner_max_output_tokens'] + len(slots) * FROZEN['max_output_tokens']}",
        "",
        "── Failure discipline ──",
        "  Planner hard failure: abort entire run, status=aborted, no zhuque files.",
        "  Writer failures: recorded as-is; no retry; other slots continue.",
        "  Group E with no extractable core: CORE_PARSE_FAILED; raw XML is NEVER",
        "  silently used as final prose; no LLM repair; no regeneration.",
        "",
        "── Execution ──",
        "  Scene-level parallelism: 4 concurrent scenes, sequential writers within a scene.",
        "  Each scene writes to its own isolated SQLite copy.",
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
    """One scene: 1 Planner + 6 Writers (sequential within the scene)."""
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
            abort_event.set()
            case_result["fatal"] = planner.error_code
            _persist_case()
            print(f"  [{case_id}] PLANNER FATAL: {planner.error_code} — aborting run")
            return case_result

        await generation.select_candidate(run_obj.id, "planner", planner.id)
        await session.commit()
        planner_output = json.loads(planner.parsed_output_json or "{}")
        write_json(case_dir / "planner.json", planner_output)

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
                if group == "E":
                    process_group_e_draft(root, case_dir, cr)
                else:
                    process_group_a_draft(root, case_dir, cr)
                stem = f"{group.lower()}-{replica}"
                write_json(case_dir / "raw" / f"{stem}.json", cr)
                case_result["drafts"].append(cr)
                status = cr.get("extract_status")
                print(f"  [{case_id}] {group}-{replica}: "
                      f"{status} core={cr.get('core_character_count')} "
                      f"discard={cr.get('discard_character_count')} err={cr.get('error_code')}")

        case_result["call_orders"] = call_orders
        _persist_case()
        ok = sum(1 for d in case_result["drafts"] if d.get("text_path"))
        print(f"  [{case_id}] {ok}/{len(GROUPS) * REPLICAS} final texts")
        return case_result


def scene_database(database: Path, case_id: str) -> Path:
    """Each scene gets its own isolated SQLite copy (see factorial runner)."""
    return database.with_name(f"{database.stem}_{case_id}.sqlite3")


async def run(root: Path, database: Path, dry_run: bool, *, zhuque_only: bool = False) -> None:
    import time

    case_ids = [case[0] for case in SCENES]

    if zhuque_only:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if not export_allowed(manifest.get("status", "")):
            raise RuntimeError(f"Refusing to package: manifest status is {manifest.get('status')!r}")
        exported = [
            json.loads((root / "cases" / cid / "result.json").read_text(encoding="utf-8"))
            for cid in manifest["case_ids"]
        ]
        package_zhuque_submission(root, exported)
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
            "A": "length-matched baseline (minimal length instruction, plain prose)",
            "E": "sacrificial error channel (5–7 units; only concatenated core retained)",
        },
        "writer_input_mode": "writer_brief",
        "writer_behavior_mode": None,
        "writer_prompt_version_id": FROZEN["writer_prompt_version_id"],
        "planner_prompt_version_id": FROZEN["planner_prompt_version_id"],
        "frozen_parameters": FROZEN,
        "instruction_hashes": {
            group: instruction_hash(GROUP_INSTRUCTIONS[group]) for group in GROUPS
        },
        "execution_model": (
            "scene-level parallelism (4 concurrent scenes, each with its own "
            "isolated SQLite copy); writers sequential within a scene; all "
            "hash/boundary/blind artifacts are per-slot deterministic and "
            "order-independent"
        ),
        "rules": [
            "One Planner call per scene; all 6 Writers share the frozen Planner output.",
            "2 groups x 3 replicas per scene; stratified-random A/E call order per replica.",
            "No Critic/Reviser/Judge. No retry. No filtering. All failures preserved.",
            "Group E: no LLM XML repair; no silent raw-XML fallback; CORE_PARSE_FAILED recorded.",
            "Planner hard failure aborts the entire run; no per-scene makeup runs.",
            "seed=null for every model call; other parameters held identical.",
            "max_output_tokens=6000 is an experiment-level override for BOTH groups; product defaults untouched.",
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
        print(f"  RUN ABORTED: {manifest['abort_reason']}")
        return

    assertions = slot_assertions(exported, case_ids)
    manifest["status"] = "completed"
    manifest["post_generation_assertions"] = assertions
    manifest["wall_seconds"] = wall_seconds
    write_json(root / "manifest.json", manifest)

    make_blind_assets(root, exported)
    package_zhuque_submission(root, exported)

    e_drafts = [d for c in exported for d in c["drafts"] if d["group"] == "E"]
    write_json(root / "validation_summary.json", {
        "experiment": EXPERIMENT,
        "post_generation_assertions": assertions,
        "group_E_extract_status": {
            status: len([d for d in e_drafts if d.get("extract_status") == status])
            for status in ("complete", "recovered", "CORE_PARSE_FAILED")
        },
        "drafts": [
            {
                "case_id": case["case_id"],
                "group": item["group"],
                "replica": item["replica"],
                "extract_status": item.get("extract_status"),
                "raw_character_count": item.get("raw_character_count"),
                "discard_character_count": item.get("discard_character_count"),
                "core_character_count": item.get("core_character_count"),
                "discard_ratio": item.get("discard_ratio"),
                "unit_count": item.get("unit_count"),
                "instruction_hash": item.get("instruction_hash"),
                "rendered_user_prompt_sha256": item.get("rendered_user_prompt_sha256"),
                "error_code": item.get("error_code"),
                "tempo_final_line_mismatch": item.get("tempo_final_line_mismatch"),
                **(item.get("validation") or {}),
            }
            for case in exported
            for item in case["drafts"]
        ],
    })

    write_json(root / "execution_summary.json", {
        "experiment": EXPERIMENT,
        "status": manifest["status"],
        "planner_calls": len([c for c in exported if c.get("planner", {}).get("candidate_id")]),
        "writer_calls": sum(len(c["drafts"]) for c in exported),
        "writer_drafts_expected": len(expected_slots(case_ids)),
        "final_texts": sum(1 for c in exported for d in c["drafts"] if d.get("text_path")),
        "wall_seconds": wall_seconds,
    })
    if not assertions["all_passed"]:
        print(f"  ASSERTION GAPS: {json.dumps(assertions['checks'], ensure_ascii=False)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=REPO_ROOT / "__evaluation" / "sacrificial_error_channel_feasibility_v1")
    parser.add_argument("--database", type=Path,
                        default=REPO_ROOT / "__evaluation" / "sacrificial_error_channel_feasibility_v1.sqlite3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--zhuque-only", action="store_true")
    parser.add_argument("--model-id", default=FROZEN["model_id"])
    args = parser.parse_args()
    FROZEN["model_id"] = args.model_id
    FROZEN["planner_max_output_tokens"] = planner_output_cap(args.model_id)
    asyncio.run(run(args.root, args.database, args.dry_run, zhuque_only=args.zhuque_only))


if __name__ == "__main__":
    main()
