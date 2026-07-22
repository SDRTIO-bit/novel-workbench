"""Narrative Projection Compiler v1 — Three-Arm Paired Experiment.

Stages:
  Stage 1 (smoke):  4 scenes × 1 replica  = 4 planners, 12 writers
  Stage 2 (formal): 6 scenes × 3 replicas = 18 planners, 54 writers

Arms:
  F = complete_planner (full A1 JSON injected)
  C = chapter_architect (current compiler)
  N = narrative_projection (new compiler)

All arms share the same frozen A1 parsed JSON per replica.
"""
import asyncio
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from app.models.generation import GenerationRun
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.prompt import PromptProfile, PromptVersion
from app.prompts.defaults import BUILTIN_PROMPTS
from app.services.generation_service import GenerationService
from app.services.project_service import ProjectService
from app.services.chapter_service import ChapterService
from app.services.writer_brief import compile_writer_input
from app.schemas.project import ProjectCreate, DocumentUpdate
from app.schemas.chapter import ChapterCreate

EXPERIMENT_NAME = "NARRATIVE_PROJECTION_COMPILER_V1_THREE_ARM"
EVIDENCE = REPO_ROOT / "__evaluation" / "narrative_projection_compiler_v1_three_arm"
V9_DB = REPO_ROOT / "__evaluation" / "sacrificial_preflight_fusion_v9_feasibility_v1"
SEED = 20260721

# ── Scenes ─────────────────────────────────────────────────────────────

SCENES = [
    {
        "case_id": "NM-03",
        "title": "洗衣房的滚筒",
        "focus_character": "方笛",
        "scene_instruction": (
            "小区自助洗衣房里，方笛认为自己那台滚筒还没洗完——她记得设定的是一小时，"
            "现在才过去四十分钟。旁边等着用机器的老人说机器早停了，里面是他的衣服。"
            "方笛不能跟老人争，也不能直接把滚筒门拉开。滚筒玻璃上的水位和面板上的状态"
            "会证明谁记错了。她必须用一个可见事实处理这个争执。停在机器状态拆穿其中一方判断的事实。"
        ),
    },
    {
        "case_id": "ROMANCE-02",
        "title": "未读消息",
        "focus_character": "夏知",
        "scene_instruction": (
            "合租屋厨房里，夏知看见韩川的手机亮起自己昨晚的未读消息，"
            "韩川却先把手机扣在桌上去洗菜。水已经开了，桌上只有两只碗。"
            "夏知不能偷看手机，也不能断言对方为何没回；她需要根据可见事实"
            "选择继续帮忙、离开或提出别的行动，并让代价和后果落在现场。"
        ),
    },
    {
        "case_id": "CO-04",
        "title": "操场上错拿的水壶",
        "focus_character": "路远",
        "scene_instruction": (
            "体育课自由活动时，路远发现自己的蓝色运动水壶被一个不认识的男生"
            "拿起来喝了一口。那个男生正往篮球场方向走，手里还拿着水壶。"
            "路远不能跑过去抢回来，也不能在操场上喊。他必须用一个现场物件让对方发现。"
            "停在水壶回到正确位置的事实。"
        ),
    },
    {
        "case_id": "CO-05",
        "title": "快递架上的同名包裹",
        "focus_character": "向暖",
        "scene_instruction": (
            "小区快递架上，向暖发现一个写着向暖的包裹——但收件地址不是自己的楼栋。"
            "真正的收件人可能就在附近。包裹不大，架子上还有其他未取件。"
            "向暖不能拆包裹验证，也不能拿错的东西回家。"
            "她必须用一个现场物件标记或通知。停在包裹归属出现新事实。"
        ),
    },
    # ── New scenes for Stage 2 ──
    {
        "case_id": "MULTI-01",
        "title": "排练室的迟到",
        "focus_character": "苏瑾",
        "scene_instruction": (
            "学校排练室里，乐队吉他手苏瑾迟到了十五分钟。鼓手老周在调音，"
            "贝斯手小唐靠在墙上刷手机，主唱阿杰坐在音箱上翻谱子。"
            "苏瑾推门进来时所有人都抬了头，但没人说话。苏瑾不知道他们刚才聊了什么，"
            "只能根据每个人的反应和接下来的行动判断气氛。停在苏瑾拿起吉他，第一个和弦响起的事实。"
        ),
    },
    {
        "case_id": "HONEST-01",
        "title": "共享文档的编辑冲突",
        "focus_character": "林子",
        "scene_instruction": (
            "共享办公室里，林子发现下午要交的PPT被同事改了大半——改得不好，"
            "但同事是出于好意，昨晚加班到很晚才改完。同事现在趴在桌上睡着了。"
            "林子不能叫醒同事争论，也不能在deadline前全部重做。"
            "她必须根据可见的修改痕迹决定保留哪些、回退哪些、以及怎么在同事醒来后说这件事。"
            "停在林子打开版本历史，同事翻了个身的事实。"
        ),
    },
]

# ── Arms ────────────────────────────────────────────────────────────────

ARMS = {
    "F": {"mode": "complete_planner", "label": "Full JSON"},
    "C": {"mode": "chapter_architect", "label": "Chapter Architect Compiler"},
    "N": {"mode": "narrative_projection", "label": "Narrative Projection Compiler"},
}

# ── Frozen params ───────────────────────────────────────────────────────

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "temperature": 0.7,
    "top_p": 1.0,
    "max_output_tokens": 6000,
    "timeout_seconds": 300,
}

PLANNER_CFG = {"name": "Chapter Architect v1", "schema": "chapter_architect_v1", "mode": "complete_planner"}
WRITER_CFG = {"name": "Sacrificial Preflight Fusion v9", "mode": "writer_brief"}

EXECUTION_ORDERS = [
    ["F", "C", "N"], ["F", "N", "C"],
    ["C", "F", "N"], ["C", "N", "F"],
    ["N", "F", "C"], ["N", "C", "F"],
]

# ── Helpers ────────────────────────────────────────────────────────────

def extract_story(xml):
    m = re.search(r"<story>(.*?)</story>", xml, re.DOTALL | re.I)
    return m.group(1).strip() if m else ""

def extract_notes(xml):
    m = re.search(r"<draft_notes>(.*?)</draft_notes>", xml, re.DOTALL | re.I)
    return m.group(1).strip() if m else ""

def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def sha256_json(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Main runner ─────────────────────────────────────────────────────────

async def run_stage(stage_name: str, scenes, replicas: int):
    """Run one stage of the experiment."""
    rng = random.Random(SEED)
    all_triplets = []

    for scene_idx, scene in enumerate(scenes):
        case_id = scene["case_id"]
        title = scene["title"]
        focus = scene["focus_character"]
        instruction = scene["scene_instruction"]

        for replica in range(1, replicas + 1):
            print(f"\n{'='*60}")
            print(f"[{stage_name}] {case_id} replica {replica}/{replicas}")
            print(f"{'='*60}")

            db_path = V9_DB.with_name(f"{V9_DB.name}_{case_id}.sqlite3")
            if not db_path.exists():
                print(f"  SKIP: no database at {db_path}")
                continue

            # ── Run A1 Planner once ──
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with factory() as session:
                ps, cs = ProjectService(session), ChapterService(session)
                gen = GenerationService(session)

                proj_name = f"np_v1_{case_id}_r{replica}"
                proj = (await session.execute(
                    select(Project).where(Project.name == proj_name)
                )).scalars().first()
                if not proj:
                    proj = await ps.create_project(ProjectCreate(name=proj_name, genre="现实场景"))
                    await ps.update_document(proj.id, "principles", DocumentUpdate(
                        title="Narrative Projection Experiment", content="三臂配对实验"))
                chap = (await session.execute(
                    select(Chapter).where(Chapter.project_id == proj.id)
                )).scalars().first()
                if not chap:
                    chap = await cs.create_chapter(proj.id, ChapterCreate(title=title, sort_order=1))
                await session.commit()

                # Planner prompt version
                from app.prompts.defaults import BUILTIN_PROMPTS
                entry = next(e for e in BUILTIN_PROMPTS
                           if e["name"] == PLANNER_CFG["name"] and e["stage"] == "planner")
                profile = (await session.execute(
                    select(PromptProfile).where(
                        PromptProfile.name == entry["name"],
                        PromptProfile.is_builtin == True
                    )
                )).scalars().first()
                if not profile:
                    profile = PromptProfile(stage="planner", name=entry["name"],
                                           description=entry["description"], is_builtin=True)
                    session.add(profile); await session.flush()
                await session.refresh(profile, ["versions"])
                vn = max((v.version_number for v in profile.versions), default=0) + 1
                pv = PromptVersion(
                    profile_id=profile.id, version_number=vn,
                    system_template=entry["system_template"],
                    user_template=entry["user_template"],
                    output_mode="structured",
                    output_schema_name=PLANNER_CFG["schema"],
                )
                session.add(pv); await session.flush()
                await session.commit()

                run_obj = await gen.create_run(proj.id, chap.id, None, instruction)
                await session.commit()
                override = dict(FROZEN, prompt_version_id=pv.id, target_length=2000)

                try:
                    planner = await gen.execute_stage(run_obj.id, "planner", override)
                    await session.flush()
                    if not planner.error_code:
                        await gen.select_candidate(run_obj.id, "planner", planner.id)
                    await session.commit()
                except Exception as e:
                    print(f"  [{case_id}] Planner ERROR: {e}")
                    await session.rollback()
                    await engine.dispose()
                    continue

                # Save planner data
                planner_parsed_json = planner.parsed_output_json
                planner_error_code = planner.error_code
                planner_latency_ms = planner.latency_ms
                planner_raw = planner.raw_response or ""
                run_id = run_obj.id

                parsed = None
                if planner_parsed_json:
                    try:
                        parsed = json.loads(planner_parsed_json)
                    except Exception:
                        pass

                ok = parsed is not None and not planner_error_code
                print(f"  Planner: parsed={ok} err={planner_error_code} lat={planner_latency_ms}ms")
                if not ok:
                    await engine.dispose()
                    continue

                planner_sha = sha256_json(parsed)

                # ── Evidential directory ──
                replica_dir = EVIDENCE / "cases" / case_id / "replicas" / f"r{replica}"
                planner_dir = replica_dir / "planner"
                planner_dir.mkdir(parents=True, exist_ok=True)
                (planner_dir / "raw_response.txt").write_text(planner_raw, encoding="utf-8")
                (planner_dir / "parsed.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                (planner_dir / "sha256.txt").write_text(planner_sha + "\n", encoding="utf-8")
                metadata = {
                    "case_id": case_id, "replica": replica, "stage": stage_name,
                    "actual_head": get_git_head(),
                    "planner_output_sha256": planner_sha,
                    "planner_latency_ms": planner_latency_ms,
                    "run_id": run_id,
                }
                (planner_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

            await engine.dispose()

            # ── Determine execution order ──
            order_idx = (scene_idx * replicas + (replica - 1)) % len(EXECUTION_ORDERS)
            arm_order = EXECUTION_ORDERS[order_idx]
            print(f"  Execution order: {'→'.join(arm_order)}")

            # ── Fan out to 3 Writer arms ──
            arm_results = {}
            triplet_data = {
                "case_id": case_id, "replica": replica, "stage": stage_name,
                "planner_output_sha256": planner_sha,
                "execution_order": arm_order,
                "arms": {},
            }

            for arm_key in arm_order:
                arm_cfg = ARMS[arm_key]
                print(f"  Arm {arm_key} ({arm_cfg['label']})...", end=" ", flush=True)

                # Compile writer input
                compile_kwargs = {}
                if arm_key == "N":
                    compile_kwargs["focus_character"] = focus
                writer_input = compile_writer_input(parsed, arm_cfg["mode"], **compile_kwargs)
                writer_input_sha = sha256_json(writer_input)
                writer_input_rendered = json.dumps(writer_input, ensure_ascii=False, indent=2)

                # Run Writer in fresh session
                w_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
                w_factory = async_sessionmaker(w_engine, class_=AsyncSession, expire_on_commit=False)
                w_result = None

                try:
                    async with w_factory() as w_session:
                        w_entry = next(e for e in BUILTIN_PROMPTS
                                      if e["name"] == WRITER_CFG["name"] and e["stage"] == "writer")
                        w_profile = (await w_session.execute(
                            select(PromptProfile).where(
                                PromptProfile.name == w_entry["name"],
                                PromptProfile.is_builtin == True
                            )
                        )).scalars().first()
                        if not w_profile:
                            w_profile = PromptProfile(stage="writer", name=w_entry["name"],
                                                     description=w_entry["description"], is_builtin=True)
                            w_session.add(w_profile); await w_session.flush()
                        await w_session.refresh(w_profile, ["versions"])
                        w_vn = max((v.version_number for v in w_profile.versions), default=0) + 1
                        w_pv = PromptVersion(
                            profile_id=w_profile.id, version_number=w_vn,
                            system_template=w_entry["system_template"],
                            user_template=w_entry["user_template"],
                            output_mode="xml_story", output_schema_name=None,
                        )
                        w_session.add(w_pv); await w_session.flush()
                        await w_session.commit()

                        w_override = dict(
                            FROZEN,
                            prompt_version_id=w_pv.id,
                            target_length=2000,
                            write_mode="new_chapter",
                            writer_input_mode=arm_cfg["mode"],
                            writer_brief=writer_input,
                        )
                        if arm_key == "N":
                            w_override["focus_character"] = focus

                        w_gen = GenerationService(w_session)
                        writer = await w_gen.execute_stage(run_id, "writer", w_override)
                        await w_session.commit()

                        raw = writer.raw_response or ""
                        story_text = extract_story(raw)
                        notes_text = extract_notes(raw)

                        w_result = {
                            "arm": arm_key,
                            "story": story_text,
                            "notes": notes_text,
                            "raw_response": raw,
                            "error": writer.error_code,
                            "story_chars": len(story_text),
                            "finish_reason": writer.finish_reason,
                            "latency_ms": writer.latency_ms,
                            "run_id": writer.id,
                        }
                        arm_results[arm_key] = w_result

                        status = "ok" if story_text and not writer.error_code else f"err={writer.error_code}"
                        print(f"story={len(story_text)} chars {status}")

                except Exception as e:
                    print(f"ERROR: {e}")
                    w_result = {"arm": arm_key, "error": str(e), "story": "", "notes": "", "story_chars": 0, "raw_response": ""}
                    arm_results[arm_key] = w_result
                finally:
                    await w_engine.dispose()

                # ── Save arm evidence ──
                arm_dir = replica_dir / "arms" / arm_key
                arm_dir.mkdir(parents=True, exist_ok=True)
                (arm_dir / "writer_input.json").write_text(writer_input_rendered, encoding="utf-8")
                if arm_key == "N":
                    (arm_dir / "writer_input_rendered.txt").write_text(
                        writer_input.get("architect_brief", ""), encoding="utf-8")
                if w_result:
                    (arm_dir / "raw_response.txt").write_text(
                        w_result.get("raw_response", ""), encoding="utf-8")
                    (arm_dir / "story.txt").write_text(w_result.get("story", ""), encoding="utf-8")
                    (arm_dir / "draft_notes.txt").write_text(w_result.get("notes", ""), encoding="utf-8")
                    arm_meta = {
                        "arm": arm_key, "mode": arm_cfg["mode"],
                        "writer_input_sha256": writer_input_sha,
                        "raw_response_sha256": sha256_hex(w_result.get("raw_response", "")),
                        "story_sha256": sha256_hex(w_result.get("story", "")),
                        "story_chars": w_result.get("story_chars", 0),
                        "draft_notes_chars": len(w_result.get("notes", "")),
                        "error_code": w_result.get("error"),
                        "finish_reason": w_result.get("finish_reason"),
                        "latency_ms": w_result.get("latency_ms"),
                    }
                    (arm_dir / "metadata.json").write_text(
                        json.dumps(arm_meta, ensure_ascii=False, indent=2), encoding="utf-8")

                triplet_data["arms"][arm_key] = {
                    "writer_input_sha256": writer_input_sha,
                    "error": w_result.get("error") if w_result else "COMPILE_FAILED",
                    "story_chars": w_result.get("story_chars", 0) if w_result else 0,
                }

            # ── Verify triplet integrity ──
            arm_shas = {k: v["writer_input_sha256"] for k, v in triplet_data["arms"].items()}
            # All three arms MUST have the same planner output
            triplet_data["planner_sha_consistent"] = True  # Same parsed JSON used for all
            triplet_data["valid"] = all(
                triplet_data["arms"].get(a, {}).get("error") is None
                and triplet_data["arms"].get(a, {}).get("story_chars", 0) > 0
                for a in ["F", "C", "N"]
            )

            (replica_dir / "triplet_metadata.json").write_text(
                json.dumps(triplet_data, ensure_ascii=False, indent=2), encoding="utf-8")
            all_triplets.append(triplet_data)

    return all_triplets


def get_git_head() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


# ── Blind pack generator ────────────────────────────────────────────────

def generate_blind_pack(triplets):
    """Generate anonymized blind evaluation pack."""
    blind_dir = EVIDENCE / "blind"
    blind_dir.mkdir(parents=True, exist_ok=True)
    items_dir = blind_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED + 1)
    mapping = {}  # blind_id -> {case, replica, arm}
    queue = []

    valid_triplets = [t for t in triplets if t.get("valid")]
    for t in valid_triplets:
        labels = list("XYZ")
        rng.shuffle(labels)
        for arm_key, label in zip(["F", "C", "N"], labels):
            blind_id = f"{t['case_id']}_r{t['replica']}_{label}"
            mapping[blind_id] = {
                "case_id": t["case_id"],
                "replica": t["replica"],
                "arm": arm_key,
                "label": label,
            }
            queue.append({
                "id": blind_id,
                "case_id": t["case_id"],
                "replica": t["replica"],
                "label": label,
            })

            # Copy story text
            arm_dir = EVIDENCE / "cases" / t["case_id"] / "replicas" / f"r{t['replica']}" / "arms" / arm_key
            story_path = arm_dir / "story.txt"
            if story_path.exists():
                (items_dir / f"{blind_id}.txt").write_text(story_path.read_text(encoding="utf-8"), encoding="utf-8")

    rng.shuffle(queue)
    (blind_dir / "queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    (blind_dir / "private_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    # Zhuque
    zhuque_dir = EVIDENCE / "zhuque"
    zhuque_dir.mkdir(parents=True, exist_ok=True)
    SEP = "\n\n\n\n\n"

    for arm_key, arm_label in [("F", "F"), ("C", "C"), ("N", "N")]:
        stories = []
        boundaries = []
        offset = 0
        for t in valid_triplets:
            arm_dir = EVIDENCE / "cases" / t["case_id"] / "replicas" / f"r{t['replica']}" / "arms" / arm_key
            story_path = arm_dir / "story.txt"
            if story_path.exists():
                text = story_path.read_text(encoding="utf-8")
                stories.append(text)
                boundaries.append({"case_id": t["case_id"], "replica": t["replica"],
                                   "start": offset, "end": offset + len(text)})
                offset += len(text) + len(SEP)

        combined = SEP.join(stories)
        (zhuque_dir / f"{arm_label}.txt").write_text(combined, encoding="utf-8")
        (zhuque_dir / f"{arm_label}_boundaries.json").write_text(
            json.dumps(boundaries, ensure_ascii=False, indent=2), encoding="utf-8")

    # All randomized
    all_stories = []
    all_boundaries = []
    offset = 0
    for item in queue:
        story_path = items_dir / f"{item['id']}.txt"
        if story_path.exists():
            text = story_path.read_text(encoding="utf-8")
            all_stories.append(text)
            all_boundaries.append({"id": item["id"], "case_id": item["case_id"],
                                   "replica": item["replica"], "label": item["label"],
                                   "start": offset, "end": offset + len(text)})
            offset += len(text) + len(SEP)

    (zhuque_dir / "all_randomized.txt").write_text(SEP.join(all_stories), encoding="utf-8")
    (zhuque_dir / "all_boundaries.json").write_text(
        json.dumps(all_boundaries, ensure_ascii=False, indent=2), encoding="utf-8")

    submission_manifest = {
        "experiment": EXPERIMENT_NAME,
        "zhuque_files": {
            "F": str(zhuque_dir / "F.txt"),
            "C": str(zhuque_dir / "C.txt"),
            "N": str(zhuque_dir / "N.txt"),
            "all_randomized": str(zhuque_dir / "all_randomized.txt"),
        },
    }
    (zhuque_dir / "submission_manifest.json").write_text(
        json.dumps(submission_manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Report generator ────────────────────────────────────────────────────

def generate_report(stage_name: str, triplets):
    valid = [t for t in triplets if t.get("valid")]
    invalid = [t for t in triplets if not t.get("valid")]

    lines = [
        f"=== {EXPERIMENT_NAME} — {stage_name} ===",
        f"HEAD: {get_git_head()}",
        f"Total triplets: {len(triplets)}",
        f"Valid complete triplets: {len(valid)}",
        f"Invalid/incomplete: {len(invalid)}",
        "",
        "── Per-arm stats ──",
    ]

    for arm_key in ["F", "C", "N"]:
        arm_label = ARMS[arm_key]["label"]
        chars = [t["arms"].get(arm_key, {}).get("story_chars", 0) for t in valid
                 if t["arms"].get(arm_key, {}).get("story_chars", 0) > 0]
        errors = sum(1 for t in valid if t["arms"].get(arm_key, {}).get("error"))
        if chars:
            lines.append(
                f"  {arm_key} ({arm_label}): n={len(chars)} "
                f"mean={sum(chars)//len(chars)} min={min(chars)} max={max(chars)} "
                f"errors={errors}"
            )
        else:
            lines.append(f"  {arm_key} ({arm_label}): n=0 errors={errors}")
    lines.append("")

    if valid:
        lines.append("── Valid triplets ──")
        for t in valid:
            f_chars = t["arms"].get("F", {}).get("story_chars", 0)
            c_chars = t["arms"].get("C", {}).get("story_chars", 0)
            n_chars = t["arms"].get("N", {}).get("story_chars", 0)
            lines.append(
                f"  {t['case_id']} r{t['replica']}: "
                f"F={f_chars} C={c_chars} N={n_chars} "
                f"order={'→'.join(t['execution_order'])}"
            )

    if invalid:
        lines.append("")
        lines.append("── Invalid/incomplete triplets ──")
        for t in invalid:
            lines.append(f"  {t['case_id']} r{t['replica']}: valid={t.get('valid')}")

    report = "\n".join(lines)
    print("\n" + report)
    (EVIDENCE / f"report_{stage_name.lower()}.txt").write_text(report, encoding="utf-8")
    return report


# ── Main ────────────────────────────────────────────────────────────────

async def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    head = get_git_head()
    print(f"HEAD: {head}")
    print(f"Evidence: {EVIDENCE}")

    # ── Stage 1: Smoke ──
    print("\n" + "="*60)
    print("STAGE 1: SMOKE TEST (4 scenes × 1 replica)")
    print("="*60)
    stage1_triplets = await run_stage("stage1", SCENES[:4], replicas=1)
    generate_blind_pack(stage1_triplets)
    generate_report("stage1", stage1_triplets)

    valid_s1 = [t for t in stage1_triplets if t.get("valid")]
    planners_ok = len({(t["case_id"], t["replica"]) for t in stage1_triplets
                       if t.get("planner_output_sha256")})

    print(f"\nStage 1 summary: {len(valid_s1)}/{len(stage1_triplets)} valid triplets, "
          f"{planners_ok} planners succeeded")

    if len(valid_s1) < 4:
        print("Stage 1 INCOMPLETE — stopping before Stage 2.")
        return

    # ── Stage 2: Formal ──
    print("\n" + "="*60)
    print("STAGE 2: FORMAL EXPERIMENT (6 scenes × 3 replicas)")
    print("="*60)
    stage2_triplets = await run_stage("stage2", SCENES, replicas=3)
    generate_blind_pack(stage2_triplets)
    generate_report("stage2", stage2_triplets)

    valid_s2 = [t for t in stage2_triplets if t.get("valid")]
    print(f"\nStage 2 summary: {len(valid_s2)}/{len(stage2_triplets)} valid triplets")

    # ── Compile execution_summary.json ──
    summary = {
        "experiment": EXPERIMENT_NAME,
        "head": head,
        "stage1": {
            "total_triplets": len(stage1_triplets),
            "valid_triplets": len(valid_s1),
        },
        "stage2": {
            "total_triplets": len(stage2_triplets),
            "valid_triplets": len(valid_s2),
        },
    }
    (EVIDENCE / "execution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Create manifest.json ──
    manifest = {
        "experiment": EXPERIMENT_NAME,
        "head": head,
        "seed": SEED,
        "frozen_params": FROZEN,
        "scenes": [{"case_id": s["case_id"], "focus_character": s.get("focus_character")}
                    for s in SCENES],
        "arms": ARMS,
        "planner_cfg": PLANNER_CFG,
        "writer_cfg": WRITER_CFG,
        "stage1_valid_triplets": len(valid_s1),
        "stage2_valid_triplets": len(valid_s2),
        "execution_orders_used": EXECUTION_ORDERS,
    }
    (EVIDENCE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone. Evidence: {EVIDENCE}")


if __name__ == "__main__":
    asyncio.run(main())
