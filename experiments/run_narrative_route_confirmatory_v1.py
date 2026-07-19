"""NARRATIVE_ROUTE_CONVERGENCE_V1 — confirmatory experiments.

Two small-scale confirmations:

1. ALITE_VS_A: A-lite vs complete_planner (CAMPUS-02 mechanism)
   - 5 new partial-message / misattribution / information-asymmetry scenes
   - Route: writer_input_mode="narrative_route" → A_LITE_INFORMATION_GAP
   - Baseline: writer_input_mode="complete_planner" (the proven winner for CAMPUS-04)

2. COBJECT_VS_A: C Object vs complete_planner (CAMPUS-04 mechanism)
   - 5 new object-misrecognition / causal-object scenes
   - Route: writer_input_mode="narrative_route" → C_OBJECT_CAUSAL
   - Baseline: writer_input_mode="complete_planner"

Each scene: 3 route replicas + 3 baseline replicas = 6 Writers.
Total: 10 scenes × 6 = 60 articles.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.schemas.chapter import ChapterCreate
from app.schemas.project import ProjectCreate
from app.services.chapter_service import ChapterService
from app.services.generation_service import GenerationService
from app.services.project_service import ProjectService
from app.services.narrative_route_classifier import classify_narrative_route

EXPERIMENT = "NARRATIVE_ROUTE_CONFIRMATORY_V1"
SEED = 20260720
REPLICAS = 3

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

# ── ALITE_VS_A: CAMPUS-02 mechanism (partial message, misattribution, info gap) ──
ALITE_SCENES = (
    ("AL-01", "校园误会", "撤回的作业评语",
     "课间，乔雨发现班主任在企业微信上给自己发了一条评语又撤回了，只看到预览里'你这次的……'四个字。同桌正拿着手机走过来。乔雨不能问班主任，也不能假装没看见。她必须根据这条被撤回的消息做个具体选择。停在新出现的事实。"),
    ("AL-02", "校园误会", "被涂掉的名字",
     "社团招新名单贴在公告栏上，程悦发现自己名字那一行被马克笔涂掉了，涂痕还很新。旁边站着的李沐手里拿着一支黑色马克笔，正跟别人说话。程悦不能直接质问是不是他涂的，也不能把涂痕擦掉。她必须做一个具体行动。停在名字是否恢复的事实。"),
    ("AL-03", "校园误会", "办公室门外的半句",
     "课代表沈珂去办公室送作业，走到门口听见数学老师对年级主任说'沈珂那个孩子其实……'，后半句被关门声截断了。数学老师很快推门出来，手里拿着沈珂上次的试卷。沈珂不能追问，不能偷看试卷。她必须根据这半句话做一个选择。停在新事实。"),
    ("AL-04", "职场日常", "茶水间的简历",
     "午休时，秦蔓去茶水间倒水，发现复印机托盘上有一份打印到一半的简历，名字是自己的——只印了名字和第一行工作经历就被抽走了。简历旁边放着一杯还热着的咖啡。同事林远刚从这里离开。秦蔓不能把简历拿走，也不能问是不是林远打印的。她必须做一个动作。停在可见事实。"),
    ("AL-05", "校园误会", "群聊里的@撤回",
     "晚自习前，齐放发现年级群里有人@了自己然后撤回了——群提示写着'齐放 被@'但消息已经消失。群里还有二十多个人在线。发消息的账号是隔壁班的。齐放不能私聊追问，也不能在群里发问号。他必须根据这个撤回信号做一个行动。停在新事实。"),
)

# ── COBJECT_VS_A: CAMPUS-04 mechanism (object misrecognition, causal object) ──
COBJECT_SCENES = (
    ("CO-01", "校园误会", "错拿的U盘",
     "机房下课后，沈逸发现自己的银色U盘被插在隔壁电脑上，而隔壁座位的赵屿正把那台电脑关机离开。U盘里有明天展示用的PPT。沈逸不能追上去喊人，也不能假定赵屿是故意的。他必须用一个现场可用物件让对方自己发现。停在新事实。"),
    ("CO-02", "校园误会", "更衣室里的手机",
     "游泳课后，何映在更衣室长凳上发现一部和自己同型号的手机，但锁屏壁纸不是自己的。真正的失主正在泳池边找。更衣室里只剩两个人。何映不能把手机拿走，也不能大声问是谁的。她必须用一个现场物件处理。停在手机归属改变的事实。"),
    ("CO-03", "城市日常", "咖啡店错拿的杯子",
     "咖啡店里，方可发现自己点的马克杯被邻座女生端走了——杯沿有自己用纸巾擦过的痕迹。那个女生正拿着杯子往门口走。方可不能追上去说'那是我的杯'，也不能忍了重新买。她必须用一个柜台上的物件发出信号。停在杯子归属被纠正的事实。"),
    ("CO-04", "校园日常", "操场上错拿的水壶",
     "体育课自由活动时，路远发现自己的蓝色运动水壶被一个不认识的男生拿起来喝了一口。那个男生正往篮球场方向走，手里还拿着水壶。路远不能跑过去抢回来，也不能在操场上喊。他必须用一个现场物件让对方发现。停在水壶回到正确位置的事实。"),
    ("CO-05", "日常任务", "快递架上的同名包裹",
     "小区快递架上，向暖发现一个写着'向暖'的包裹——但收件地址不是自己的楼栋。真正的收件人可能就在附近。包裹不大，架子上还有其他未取件。向暖不能拆包裹验证，也不能拿错的东西回家。她必须用一个现场物件标记或通知。停在包裹归属出现新事实。"),
)


def planner_output_cap(model_id: str) -> int:
    return 12288 if model_id == "deepseek-v4-pro" else FROZEN["planner_max_output_tokens"]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def record(candidate: Any) -> dict[str, Any]:
    params = json.loads(candidate.parameters_json or "{}")
    return {
        "candidate_id": candidate.id,
        "attempt_number": candidate.attempt_number,
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


def route_writer_override() -> dict[str, Any]:
    return {
        "provider_id": FROZEN["provider_id"], "model_id": FROZEN["model_id"],
        "prompt_version_id": FROZEN["writer_prompt_version_id"],
        "temperature": FROZEN["temperature"], "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "writer_input_mode": "narrative_route",
        "route_policy_version": "narrative-route-v1",
    }


def baseline_writer_override() -> dict[str, Any]:
    return {
        "provider_id": FROZEN["provider_id"], "model_id": FROZEN["model_id"],
        "prompt_version_id": FROZEN["writer_prompt_version_id"],
        "temperature": FROZEN["temperature"], "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "writer_input_mode": "complete_planner",
    }


def make_blind_queue(root: Path, exported: list[dict[str, Any]]) -> None:
    cards = []
    private = {}
    for case in exported:
        case_id = case["case_id"]
        for item in case.get("drafts", []):
            token = hashlib.sha256(
                f"{SEED}:{case_id}:{item['group']}:{item['replica']}".encode()
            ).hexdigest()[:12].upper()
            cards.append({"blind_id": token, "case_id": case_id, "text_path": item["text_path"]})
            private[token] = {
                "case_id": case_id, "group": item["group"],
                "replica": str(item["replica"]),
                "error_code": item.get("error_code"),
            }
    random.Random(SEED).shuffle(cards)
    write_json(root / "blind_review_queue.json", cards)
    write_json(root / "blind_mapping.private.json", private)


def package_zhuque_submission(root: Path) -> None:
    """Package all drafts into anonymous Zhuque submission."""
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
    # Integrity tests
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


async def run(root: Path, database: Path, dry_run: bool, case_start: int = 0, *, zhuque_only: bool = False) -> None:
    if zhuque_only:
        package_zhuque_submission(root)
        return
    if (root / "manifest.json").exists() and case_start == 0:
        raise RuntimeError(f"{EXPERIMENT} evidence already exists; refusing to rerun")
    if not dry_run and database.exists() and case_start == 0:
        raise RuntimeError(f"isolated database already exists: {database}")

    # Select experiment group
    alite_cases = ALITE_SCENES
    cobject_cases = COBJECT_SCENES
    all_cases = alite_cases + cobject_cases
    selected = all_cases[case_start:]
    if not selected:
        raise ValueError(f"case_start {case_start} >= {len(all_cases)}")

    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "experiment": EXPERIMENT,
        "git_commit": git_commit(),
        "seed": SEED,
        "replicas_per_group": REPLICAS,
        "case_start": case_start,
        "case_ids": [c[0] for c in selected],
        "groups": {"ALITE_VS_A": "A-lite brief vs complete_planner (CAMPUS-02 mechanism)",
                    "COBJECT_VS_A": "C Object brief vs complete_planner (CAMPUS-04 mechanism)"},
        "route_baseline": "complete_planner",
        "writer_input_mode": "narrative_route",
        "route_policy_version": "narrative-route-v1",
        "rules": ["One Planner per scene.", "3 route-brief + 3 baseline-brief Writers per scene.",
                  "No Critic/Reviser/Judge. All failures preserved. No filtering."],
    }
    write_json(root / "manifest.json", manifest)

    if dry_run:
        print(f"\n  {EXPERIMENT} DRY-RUN — {len(selected)} scenes × 6 = {len(selected)*6} articles")
        for sid, cat, title, _ in selected:
            group = "ALITE_VS_A" if sid.startswith("AL-") else "COBJECT_VS_A"
            print(f"    {sid:8s} {group:12s} {cat:8s} {title}")
        print(f"  Total: {len(selected)} Planner + {len(selected)*6} Writer = {len(selected)*7} calls")
        return

    if case_start == 0:
        shutil.copy2(REPO_ROOT / "data" / "novel_workbench.db", database)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    exported: list[dict[str, Any]] = []

    try:
        async with factory() as session:
            projects = ProjectService(session)
            chapters = ChapterService(session)
            generation = GenerationService(session)

            for case_id, category, title, instruction in selected:
                case_dir = root / "cases" / case_id
                group = "ALITE_VS_A" if case_id.startswith("AL-") else "COBJECT_VS_A"

                project = await projects.create_project(
                    ProjectCreate(name=f"{EXPERIMENT} {case_id}", genre=category))
                chapter = await chapters.create_chapter(
                    project.id, ChapterCreate(title=title, sort_order=1))
                run_obj = await generation.create_run(project.id, chapter.id, None, instruction)
                await session.commit()

                planner = await generation.execute_stage(run_obj.id, "planner", {
                    "provider_id": FROZEN["provider_id"], "model_id": FROZEN["model_id"],
                    "prompt_version_id": FROZEN["planner_prompt_version_id"],
                    "temperature": FROZEN["temperature"], "top_p": FROZEN["top_p"],
                    "max_output_tokens": FROZEN["planner_max_output_tokens"],
                    "timeout_seconds": FROZEN["timeout_seconds"],
                })
                await session.commit()

                case_result: dict[str, Any] = {
                    "case_id": case_id, "category": category, "title": title,
                    "group": group, "run_id": run_obj.id,
                    "planner": record(planner), "drafts": [],
                }

                if planner.error_code:
                    write_json(case_dir / "result.json", case_result)
                    exported.append(case_result)
                    print(f"  [{case_id}] PLANNER ERROR: {planner.error_code}")
                    continue

                await generation.select_candidate(run_obj.id, "planner", planner.id)
                await session.commit()
                planner_output = json.loads(planner.parsed_output_json or "{}")
                decision = classify_narrative_route(planner_output)
                case_result["actual_route"] = decision.route_name.value
                case_result["route_decision"] = decision.model_dump()
                write_json(case_dir / "planner.json", planner_output)
                write_json(case_dir / "route_classification.json", {
                    "case_id": case_id, "group": group,
                    "actual_route": decision.route_name.value,
                    "decision": decision.model_dump(),
                })

                # 3 route Writers + 3 baseline Writers (sequential, reliable)
                route_ov = route_writer_override()
                baseline_ov = baseline_writer_override()
                for replica in range(1, REPLICAS + 1):
                    for label, ov in [("ROUTE", route_ov), ("BASELINE", baseline_ov)]:
                        candidate = await generation.execute_stage(run_obj.id, "writer", ov)
                        await session.commit()
                        cr = {"group": f"{label}-{group}", "replica": replica,
                              "mode": ov.get("writer_input_mode", "?"),
                              **record(candidate)}
                        tp = case_dir / "drafts" / f"{label.lower()}-{replica}.txt"
                        tp.parent.mkdir(parents=True, exist_ok=True)
                        tp.write_text(candidate.text_output or candidate.raw_response, encoding="utf-8")
                        cr["text_path"] = str(tp.relative_to(root))
                        write_json(case_dir / "drafts" / f"{label.lower()}-{replica}.json", cr)
                        case_result["drafts"].append(cr)

                write_json(case_dir / "result.json", case_result)
                exported.append(case_result)
                ok = sum(1 for d in case_result["drafts"] if not d.get("error_code"))
                print(f"  [{case_id}] {group} route={decision.route_name.value}  {ok}/{REPLICAS*2} ok")
    finally:
        await engine.dispose()

    make_blind_queue(root, exported)
    package_zhuque_submission(root)
    completed = [d for c in exported for d in c["drafts"] if not d.get("error_code")]
    write_json(root / "execution_summary.json", {
        "experiment": EXPERIMENT,
        "writer_drafts_completed": len(completed),
        "writer_drafts_expected": len(selected) * 6,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=REPO_ROOT / "__evaluation" / "narrative_route_confirmatory_v1")
    parser.add_argument("--database", type=Path,
                        default=REPO_ROOT / "__evaluation" / "narrative_route_confirmatory_v1.sqlite3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--zhuque-only", action="store_true")
    parser.add_argument("--case-start", type=int, default=0)
    parser.add_argument("--model-id", default=FROZEN["model_id"])
    args = parser.parse_args()
    FROZEN["model_id"] = args.model_id
    FROZEN["planner_max_output_tokens"] = planner_output_cap(args.model_id)
    asyncio.run(run(args.root, args.database, args.dry_run, args.case_start, zhuque_only=args.zhuque_only))


if __name__ == "__main__":
    main()
