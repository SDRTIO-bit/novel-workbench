"""Run the frozen DETECTOR_GENERALIZATION_V1 Writer-input experiment.

This runner creates an isolated copy of the application database.  Each case
has exactly one Planner result; only the Writer-visible planning payload varies:
complete Planner JSON (A), WriterBrief (B), or the four-field narrative
behaviour extension (C).  It never invokes Critic, Reviser, Judge, TGbreak,
candidate selection, or detector-driven rewriting.
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
from app.services.writer_brief import (
    WriterBriefC,
    compile_writer_brief,
    compile_writer_brief_c,
)


EXPERIMENT = "DETECTOR_GENERALIZATION_V1"
SEED = 20260719
REPLICAS = 2
GROUPS = {
    "A": "complete_planner",
    "B": "writer_brief",
    "C": "narrative_behaviour_brief",
}
EXTRA_C_FIELDS = {
    "available_causal_objects",
    "rejected_alternative",
    "cost_or_commitment",
    "counteraction_or_disproof",
}

# These are the validated real-model IDs used by CASE-002 through CASE-004.
# They are frozen here rather than inferred from the default (mock) workflow.
FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-chat",
    "planner_prompt_version_id": "f9052f8a-dc4e-5408-b14e-fc1badaf57f8",
    "writer_prompt_version_id": "f7760cd8-8048-4f3c-839c-e33333eb96fb",
    "temperature": 0.7,
    "top_p": 1.0,
    "planner_max_output_tokens": 4096,
    "max_output_tokens": 4000,
    "timeout_seconds": 300,
}

CASE_SPECS = (
    ("CAMPUS-01", "校园尴尬与误会", "忘带学生证", "午间进图书馆前，纪律委员陆祈发现同学沈晚把借书证夹在自己的习题册里。门禁队伍正往前挪，沈晚以为证丢了，准备向管理员解释。陆祈不能当众揭穿她早晨借过自己的册子，只能依据眼前信息，用一个具体动作让她自己发现。写放弃直接说明、选择的代价和可见后果，停在新的可见事实。"),
    ("CAMPUS-02", "校园尴尬与误会", "社团名单", "校园广播站门口，许澄看见自己名字被贴在迟到名单上，误以为好友周弈忘了替她登记。周弈正抱着器材从走廊另一头过来，值班老师在旁边。许澄必须只凭名单和现场动作作出判断，放弃当面追问，做一件会带来具体麻烦的事；不要解释周弈的真实安排。"),
    ("CAMPUS-03", "校园尴尬与误会", "错拿外套", "放学铃响后，顾栖发现椅背上挂着的深蓝外套被同桌程野穿走，而程野正往操场跑。外套口袋里有今天必须交的社团钥匙。顾栖不能在满走廊里喊对方名字，也不能凭空知道程野是否故意，必须用现场可用物件处理这个具体麻烦。写选择、代价、后果，停在钥匙去向出现新事实的位置。"),
    ("CAMPUS-04", "校园尴尬与误会", "被听见的便签", "课间，班长叶舟在黑板槽里发现一张写着自己名字的便签，只看见“别再……”三个字。写便签的唐闻正从讲台下来，其他同学围着收作业。叶舟不能把便签内容念出来，也不能直接追问；她要根据有限信息做一个会改变现场局面的动作，并承担被误解的代价。结尾保留便签后半句未知。"),
    ("ROMANCE-01", "恋爱日常与关系试探", "多买的一杯", "下雨傍晚的便利店门口，姜禾看见程砚把第二杯热豆浆放到窗边，却没有叫她。姜禾只知道两人上午因为一句玩笑僵住，不能替程砚解释心意。她必须在店员和排队顾客面前，放弃一种更直接的问法，做一个具体选择并承担关系上的小风险。停在一个可见的接收或拒绝动作。"),
    ("ROMANCE-02", "恋爱日常与关系试探", "未读消息", "合租屋厨房里，夏知看见韩川的手机亮起自己昨晚的未读消息，韩川却先把手机扣在桌上去洗菜。水已经开了，桌上只有两只碗。夏知不能偷看手机，也不能断言对方为何没回；她需要根据可见事实选择继续帮忙、离开或提出别的行动，并让代价和后果落在现场。"),
    ("ROMANCE-03", "恋爱日常与关系试探", "错过末班车", "演出散场后，陆青发现末班车已经开走，同行的方予把自己的伞递过来却没有说要不要一起走。两人刚因工作安排产生过分歧。陆青不能用旁白解释关系，也不知道方予的真实打算；他必须用一个具体行动试探，同时放弃另一种路线并承担时间或位置代价。停在雨里出现的新事实。"),
    ("ROMANCE-04", "恋爱日常与关系试探", "生日蜡烛", "朋友聚餐结束，许岚发现桌角留着一小盒没点过的生日蜡烛，而陈述正替大家收盘子。今天不是许岚生日，但她知道陈述记得她上周随口说过的日期。她不能直接问“是不是给我准备的”，必须以可见物件处理尴尬，并让一次选择有可见的承诺或退路。不要解释蜡烛原本用途。"),
    ("TASK-01", "危机或具体任务", "漏水的机房", "晚自习前，机房天花板开始滴水，水正往插线板方向流。值班的魏临只有一把拖把、一卷胶带和门口的总闸提示牌；维修老师还在另一栋楼。魏临不能假装没看见，也不能冒险碰湿插线板，必须放弃一个看似更快的做法，作出可见选择并承担时间代价。停在新的安全状态或更具体的风险上。"),
    ("TASK-02", "危机或具体任务", "丢失的快递", "小区驿站快关门时，周默发现自己取错了一只同款纸箱，真正的收件人正在门外找箱子。箱内露出一角写着“今晚使用”的说明书，柜台只剩一部固定电话和一辆推车。周默不能拆箱确认，也不能假定里面是什么；他必须在关门前处理可见的错领问题，写出选择、反事实风险和立即后果。"),
    ("TASK-03", "危机或具体任务", "被锁的排练室", "学校演出前二十分钟，舞台助理安梨发现排练室钥匙被反锁在里面，里面放着唯一一套备用麦克风线。走廊尽头有消防箱、保洁推车和一扇半开的窗，负责人正在台上点名。安梨不能砸门或擅自破坏设备，必须根据现场条件选择一条路线并放弃另一条，代价和结果都要可见。"),
    ("TASK-04", "危机或具体任务", "走失的孩子", "商场服务台旁，一个小男孩攥着一张被雨打湿的电影票，说不清家长在哪层。保安正在处理另一桩纠纷，电梯口人流很快。志愿者陶然只能依据票面时间、孩子指向和现场广播按钮行动；她不能带孩子离开商场，也不能替他编出父母信息。写她如何作出可检验的选择、承担延误代价，并停在一个新的可见线索上。"),
)


def planner_output_cap(model_id: str) -> int:
    """Use the known non-truncating structured-output cap for each model."""
    return 12288 if model_id == "deepseek-v4-pro" else FROZEN["planner_max_output_tokens"]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def record(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "attempt_number": candidate.attempt_number,
        "provider_id": candidate.provider_id,
        "model_id": candidate.model_id,
        "prompt_version_id": candidate.prompt_version_id,
        "parameters": json.loads(candidate.parameters_json or "{}"),
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


def audit_payloads(planner: dict[str, Any]) -> dict[str, Any]:
    b = compile_writer_brief(planner)
    c = compile_writer_brief_c(planner)
    WriterBriefC.model_validate(c)
    if set(c) - set(b) != EXTRA_C_FIELDS or set(b) - set(c):
        raise RuntimeError("C must differ from B by exactly the approved four fields")
    return {
        "A": {"payload_kind": "complete_planner", "payload_sha256": hashlib.sha256(json.dumps(planner, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "field_count": len(planner)},
        "B": {"payload_kind": "writer_brief", "payload_sha256": hashlib.sha256(json.dumps(b, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "field_count": len(b), "fields": list(b)},
        "C": {"payload_kind": "narrative_behaviour_brief", "payload_sha256": hashlib.sha256(json.dumps(c, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "field_count": len(c), "added_fields": sorted(set(c) - set(b))},
    }


def make_blind_queue(root: Path, exported: list[dict[str, Any]]) -> None:
    cards: list[dict[str, str]] = []
    private: dict[str, dict[str, str]] = {}
    for case in exported:
        case_id = case["case_id"]
        for item in case.get("drafts", []):
            if item.get("error_code"):
                continue
            token = hashlib.sha256(f"{SEED}:{case_id}:{item['group']}:{item['replica']}".encode()).hexdigest()[:10].upper()
            cards.append({"blind_id": token, "case_id": case_id, "text_path": item["text_path"]})
            private[token] = {"case_id": case_id, "group": item["group"], "replica": str(item["replica"])}
    random.Random(SEED).shuffle(cards)
    write_json(root / "blind_review_queue.json", cards)
    write_json(root / "blind_mapping.private.json", private)


async def run(root: Path, database: Path, dry_run: bool, case_start: int = 0) -> None:
    if (root / "manifest.json").exists():
        raise RuntimeError(f"{EXPERIMENT} evidence already exists; refusing to rerun")
    if database.exists():
        raise RuntimeError(f"isolated database already exists: {database}")
    selected_cases = CASE_SPECS[case_start:]
    if not selected_cases:
        raise ValueError(f"case_start must select at least one case (got {case_start})")
    root.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        shutil.copy2(REPO_ROOT / "data" / "novel_workbench.db", database)
    manifest = {
        "experiment": EXPERIMENT,
        "git_commit": git_commit(),
        "seed": SEED,
        "groups": GROUPS,
        "replicas_per_group": REPLICAS,
        "case_start": case_start,
        "case_ids": [case[0] for case in selected_cases],
        "writer_drafts_expected": len(selected_cases) * len(GROUPS) * REPLICAS,
        "frozen_writer": {key: value for key, value in FROZEN.items() if not key.startswith("planner_")},
        "frozen_planner": {"provider_id": FROZEN["provider_id"], "model_id": FROZEN["model_id"], "prompt_version_id": FROZEN["planner_prompt_version_id"], "temperature": FROZEN["temperature"], "top_p": FROZEN["top_p"], "max_output_tokens": FROZEN["planner_max_output_tokens"], "timeout_seconds": FROZEN["timeout_seconds"]},
        "rules": ["One Planner call per scenario.", "Two Writer calls per group per scenario.", "No Critic, Reviser, Judge, TGbreak, retry, or candidate selection.", "Detector feedback is observational and never enters a Writer prompt."],
        "detector_status": "pending_external_measurement",
    }
    write_json(root / "manifest.json", manifest)
    write_json(root / "cases.json", [{"case_id": c[0], "category": c[1], "title": c[2], "scene_instruction": c[3]} for c in selected_cases])
    if dry_run:
        return

    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    exported: list[dict[str, Any]] = []
    try:
        async with factory() as session:
            projects = ProjectService(session)
            chapters = ChapterService(session)
            generation = GenerationService(session)
            for case_id, category, title, instruction in selected_cases:
                case_dir = root / "cases" / case_id
                project = await projects.create_project(ProjectCreate(name=f"{EXPERIMENT} {case_id}", genre=category))
                chapter = await chapters.create_chapter(project.id, ChapterCreate(title=title, sort_order=1))
                run_obj = await generation.create_run(project.id, chapter.id, None, instruction)
                await session.commit()
                planner_override = {
                    "provider_id": FROZEN["provider_id"], "model_id": FROZEN["model_id"],
                    "prompt_version_id": FROZEN["planner_prompt_version_id"],
                    "temperature": FROZEN["temperature"], "top_p": FROZEN["top_p"],
                    "max_output_tokens": FROZEN["planner_max_output_tokens"], "timeout_seconds": FROZEN["timeout_seconds"],
                }
                planner = await generation.execute_stage(run_obj.id, "planner", planner_override)
                await session.commit()
                case_result: dict[str, Any] = {"case_id": case_id, "category": category, "title": title, "run_id": run_obj.id, "planner": record(planner), "drafts": []}
                if planner.error_code:
                    write_json(case_dir / "result.json", case_result)
                    exported.append(case_result)
                    continue
                await generation.select_candidate(run_obj.id, "planner", planner.id)
                await session.commit()
                planner_output = json.loads(planner.parsed_output_json or "{}")
                payload_audit = audit_payloads(planner_output)
                write_json(case_dir / "planner.json", planner_output)
                write_json(case_dir / "payload_audit.json", payload_audit)
                for group, input_mode in GROUPS.items():
                    for replica in range(1, REPLICAS + 1):
                        writer_override = {
                            "provider_id": FROZEN["provider_id"], "model_id": FROZEN["model_id"],
                            "prompt_version_id": FROZEN["writer_prompt_version_id"],
                            "temperature": FROZEN["temperature"], "top_p": FROZEN["top_p"],
                            "max_output_tokens": FROZEN["max_output_tokens"], "timeout_seconds": FROZEN["timeout_seconds"],
                            "writer_input_mode": input_mode,
                        }
                        candidate = await generation.execute_stage(run_obj.id, "writer", writer_override)
                        await session.commit()
                        candidate_record = {"group": group, "replica": replica, **record(candidate)}
                        text_path = case_dir / "drafts" / f"{group}-{replica}.txt"
                        text_path.parent.mkdir(parents=True, exist_ok=True)
                        text_path.write_text(candidate.text_output or candidate.raw_response, encoding="utf-8")
                        candidate_record["text_path"] = str(text_path.relative_to(root))
                        write_json(case_dir / "drafts" / f"{group}-{replica}.json", candidate_record)
                        case_result["drafts"].append(candidate_record)
                write_json(case_dir / "result.json", case_result)
                exported.append(case_result)
    finally:
        await engine.dispose()
    make_blind_queue(root, exported)
    completed = [d for case in exported for d in case["drafts"] if not d["error_code"]]
    write_json(root / "execution_summary.json", {"experiment": EXPERIMENT, "writer_drafts_completed": len(completed), "writer_drafts_expected": len(selected_cases) * 6, "planner_failures": [case["case_id"] for case in exported if case["planner"].get("error_code")]})
    (root / "DETECTOR_RESULTS_TEMPLATE.md").write_text("""# DETECTOR_GENERALIZATION_V1 results\n\nFor every blind ID in `blind_review_queue.json`, record the external detector's three character ratios, each orange span (start/end paragraph or character offset), and the largest continuous orange length. Do not alter draft text or group mappings.\n\nDecision gates: B or C median human ratio ≥ 60%; at least 8 of 12 scenarios better than A; blind human review not below A; and no increase in Planner-external facts.\n""", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPO_ROOT / "__evaluation" / "detector_generalization_v1")
    parser.add_argument("--database", type=Path, default=REPO_ROOT / "__evaluation" / "detector_generalization_v1.sqlite3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case-start", type=int, default=0)
    parser.add_argument("--model-id", default=FROZEN["model_id"])
    args = parser.parse_args()
    FROZEN["model_id"] = args.model_id
    FROZEN["planner_max_output_tokens"] = planner_output_cap(args.model_id)
    asyncio.run(run(args.root, args.database, args.dry_run, args.case_start))


if __name__ == "__main__":
    main()
