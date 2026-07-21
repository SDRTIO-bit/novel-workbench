"""Quick experiment: Chapter Architect v1 (A1) vs P2, single replica, Zhuque output.

4 scenes × 2 planners × 2 writers × 1 replica = max 24 calls.
"""
import asyncio, hashlib, json, re, sys, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.generation import GenerationRun, GenerationStep, GenerationCandidate
from app.models.project import Project
from app.models.chapter import Chapter
from app.services.generation_service import GenerationService
from app.services.project_service import ProjectService
from app.services.chapter_service import ChapterService
from app.services.writer_brief import compile_writer_input
from app.schemas.project import ProjectCreate, DocumentUpdate
from app.schemas.chapter import ChapterCreate

V9_DB = REPO_ROOT / "__evaluation" / "sacrificial_preflight_fusion_v9_feasibility_v1"
EVIDENCE = REPO_ROOT / "__evaluation" / "chapter_architect_v1_quick"
SEED = 202607220

SCENES = [
    ("NM-03", "洗衣房的滚筒",
     "小区自助洗衣房里，方笛认为自己那台滚筒还没洗完——她记得设定的是一小时，现在才过去四十分钟。旁边等着用机器的老人说机器早停了，里面是他的衣服。方笛不能跟老人争，也不能直接把滚筒门拉开。滚筒玻璃上的水位和面板上的状态会证明谁记错了。她必须用一个可见事实处理这个争执。停在机器状态拆穿其中一方判断的事实。"),
    ("ROMANCE-02", "未读消息",
     "合租屋厨房里，夏知看见韩川的手机亮起自己昨晚的未读消息，韩川却先把手机扣在桌上去洗菜。水已经开了，桌上只有两只碗。夏知不能偷看手机，也不能断言对方为何没回；她需要根据可见事实选择继续帮忙、离开或提出别的行动，并让代价和后果落在现场。"),
    ("CO-04", "操场上错拿的水壶",
     "体育课自由活动时，路远发现自己的蓝色运动水壶被一个不认识的男生拿起来喝了一口。那个男生正往篮球场方向走，手里还拿着水壶。路远不能跑过去抢回来，也不能在操场上喊。他必须用一个现场物件让对方发现。停在水壶回到正确位置的事实。"),
    ("CO-05", "快递架上的同名包裹",
     "小区快递架上，向暖发现一个写着向暖的包裹——但收件地址不是自己的楼栋。真正的收件人可能就在附近。包裹不大，架子上还有其他未取件。向暖不能拆包裹验证，也不能拿错的东西回家。她必须用一个现场物件标记或通知。停在包裹归属出现新事实。"),
]

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "temperature": 0.7, "top_p": 1.0,
    "max_output_tokens": 6000, "timeout_seconds": 300,
}

PLANNERS = {
    "P2": {"name": "默认场景规划", "schema": "planner_v2", "mode": "writer_brief"},
    "A1": {"name": "Chapter Architect v1", "schema": "chapter_architect_v1", "mode": "complete_planner"},
}
WRITERS = {
    "W9": {"name": "Sacrificial Preflight Fusion v9", "mode": "writer_brief"},
    "W10": {"name": "Sacrificial Preflight Fusion Strict Limited v10", "mode": "writer_brief"},
}

def extract_story(xml): return re.search(r"<story>(.*?)</story>", xml, re.DOTALL|re.I)
def extract_notes(xml): return re.search(r"<draft_notes>(.*?)</draft_notes>", xml, re.DOTALL|re.I)


async def run():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stories = []
    summary = []

    for case_id, title, scene_instruction in SCENES:
        db_path = V9_DB.with_name(f"{V9_DB.name}_{case_id}.sqlite3")
        if not db_path.exists():
            print(f"SKIP {case_id}: no database")
            continue

        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            # Create fresh project + chapter in this database
            ps = ProjectService(session)
            cs = ChapterService(session)
            gen = GenerationService(session)

            proj_name = f"architect_quick_{case_id}"
            existing = (await session.execute(
                select(Project).where(Project.name == proj_name)
            )).scalars().first()
            if existing:
                proj = existing
            else:
                proj = await ps.create_project(ProjectCreate(name=proj_name, genre="现实场景"))
                await ps.update_document(proj.id, "principles", DocumentUpdate(
                    title="冻结评估约束", content="仅执行 Planner→Writer 管线。"
                ))
            chap = (await session.execute(
                select(Chapter).where(Chapter.project_id == proj.id)
            )).scalars().first()
            if not chap:
                chap = await cs.create_chapter(proj.id, ChapterCreate(title=title, sort_order=1))

            for p_key, p_cfg in PLANNERS.items():
                # Find prompt version for this planner
                from app.models.prompt import PromptProfile, PromptVersion
                from app.prompts.defaults import BUILTIN_PROMPTS
                entry = next(e for e in BUILTIN_PROMPTS if e["name"] == p_cfg["name"] and e["stage"] == "planner")
                profile = (await session.execute(
                    select(PromptProfile).where(PromptProfile.name == entry["name"], PromptProfile.is_builtin == True)
                )).scalar_one_or_none()
                if profile is None:
                    profile = PromptProfile(stage="planner", name=entry["name"], description=entry["description"], is_builtin=True)
                    session.add(profile); await session.flush()
                await session.refresh(profile, ["versions"])
                vn = max((v.version_number for v in profile.versions), default=0) + 1
                pv = PromptVersion(profile_id=profile.id, version_number=vn,
                                   system_template=entry["system_template"],
                                   user_template=entry["user_template"],
                                   output_mode="structured",
                                   output_schema_name=p_cfg["schema"])
                session.add(pv); await session.flush()
                pv_id = pv.id

                # Create run and execute planner
                run_obj = await gen.create_run(proj.id, chap.id, None, scene_instruction)
                await session.commit()

                override = dict(FROZEN, prompt_version_id=pv_id, target_length=2000)
                try:
                    planner = await gen.execute_stage(run_obj.id, "planner", override)
                    await session.flush()
                    if not planner.error_code:
                        await gen.select_candidate(run_obj.id, "planner", planner.id)
                    await session.commit()
                    # Save planner data before expire
                    planner_parsed_json = planner.parsed_output_json
                    planner_error_code = planner.error_code
                    planner_latency_ms = planner.latency_ms
                    run_id = run_obj.id
                    # Expire to force fresh loads for writer
                    session.expire_all()
                except Exception as e:
                    print(f"  [{case_id}] {p_key} planner ERROR: {e}")
                    await session.rollback()
                    summary.append({"case": case_id, "planner": p_key, "status": "error", "error": str(e)})
                    continue

                parsed = None
                if planner_parsed_json:
                    try: parsed = json.loads(planner_parsed_json)
                    except: pass

                ok = parsed is not None and not planner_error_code
                print(f"  [{case_id}] {p_key}: parsed={ok} err={planner_error_code} lat={planner_latency_ms}ms")

                if not ok:
                    summary.append({"case": case_id, "planner": p_key, "status": "parse_fail", "error": planner_error_code})
                    continue

                # Compile brief
                brief_mode = p_cfg["mode"]
                brief = compile_writer_input(parsed, brief_mode)
                brief_sha = hashlib.sha256(json.dumps(brief, ensure_ascii=False).encode()).hexdigest()[:12]

                # Run writers
                for w_key, w_cfg in WRITERS.items():
                    w_entry = next(e for e in BUILTIN_PROMPTS if e["name"] == w_cfg["name"] and e["stage"] == "writer")
                    w_profile = (await session.execute(
                        select(PromptProfile).where(PromptProfile.name == w_entry["name"], PromptProfile.is_builtin == True)
                    )).scalar_one_or_none()
                    if w_profile is None:
                        w_profile = PromptProfile(stage="writer", name=w_entry["name"], description=w_entry["description"], is_builtin=True)
                        session.add(w_profile); await session.flush()
                    await session.refresh(w_profile, ["versions"])
                    w_vn = max((v.version_number for v in w_profile.versions), default=0) + 1
                    w_pv = PromptVersion(profile_id=w_profile.id, version_number=w_vn,
                                         system_template=w_entry["system_template"],
                                         user_template=w_entry["user_template"],
                                         output_mode="xml_story", output_schema_name=None)
                    session.add(w_pv); await session.flush()

                    w_override = dict(FROZEN, prompt_version_id=w_pv.id, target_length=2000,
                                      write_mode="new_chapter", writer_input_mode=w_cfg["mode"],
                                      writer_brief=brief)
                    try:
                        # Fresh GenerationService to avoid greenlet issues
                        w_gen = GenerationService(session)
                        writer = await w_gen.execute_stage(run_obj.id, "writer", w_override)
                        await session.commit()
                    except Exception as e:
                        print(f"    {p_key}{w_key}: writer ERROR: {e}")
                        await session.rollback()
                        summary.append({"case": case_id, "planner": p_key, "writer": w_key, "status": "error", "error": str(e)})
                        continue

                    raw = writer.raw_response or ""
                    story_m = extract_story(raw)
                    notes_m = extract_notes(raw)
                    story_text = story_m.group(1).strip() if story_m else ""
                    notes_text = notes_m.group(1).strip() if notes_m else ""

                    label = f"{case_id}_{p_key}{w_key}"
                    stories.append({"label": label, "case": case_id, "planner": p_key, "writer": w_key,
                                    "story": story_text, "notes": notes_text,
                                    "brief_sha": brief_sha, "error": writer.error_code,
                                    "story_chars": len(story_text)})

                    status = "ok" if story_text and not writer.error_code else f"err={writer.error_code}"
                    print(f"    {p_key}{w_key}: story={len(story_text)} chars {status}")

                    summary.append({"case": case_id, "planner": p_key, "writer": w_key,
                                    "status": status, "story_chars": len(story_text),
                                    "brief_sha": brief_sha})

        await engine.dispose()

    # ── Zhuque submission ──
    valid = [s for s in stories if s["story"] and not s["error"]]
    SEP = "\n\n\n\n\n"
    zhuque_parts = [s["story"] for s in valid]
    zhuque_text = SEP.join(zhuque_parts)
    zhuque_path = EVIDENCE / "zhuque_submission_v2.txt"
    zhuque_path.write_text(zhuque_text, encoding="utf-8")
    zhuque_sha = hashlib.sha256(zhuque_text.encode()).hexdigest()

    # ── Report ──
    report_lines = [
        "=== Chapter Architect v1 Quick Experiment ===",
        f"Scenes: {len(SCENES)} | Planners: P2 + A1 | Writers: W9 + W10",
        f"Valid stories in Zhuque: {len(valid)}",
        f"Zhuque SHA256: {zhuque_sha}",
        f"Zhuque path: {zhuque_path}",
        f"Total chars: {sum(len(s['story']) for s in valid)}",
        "",
        "── Per-group stats ──",
    ]
    for pk in ["P2", "A1"]:
        for wk in ["W9", "W10"]:
            group = [s for s in valid if s["planner"] == pk and s["writer"] == wk]
            if group:
                chars = [s["story_chars"] for s in group]
                report_lines.append(f"  {pk}{wk}: n={len(group)} mean={sum(chars)//len(chars)} min={min(chars)} max={max(chars)}")
            else:
                report_lines.append(f"  {pk}{wk}: n=0")
    report_lines.append("")
    report_lines.append("── Zhuque articles ──")
    for i, s in enumerate(valid):
        report_lines.append(f"  {i+1}. [{s['label']}] {s['story_chars']} chars")

    report = "\n".join(report_lines)
    print("\n" + report)
    (EVIDENCE / "report.txt").write_text(report, encoding="utf-8")
    
    # Also save individual stories for inspection
    for s in valid:
        story_dir = EVIDENCE / "stories"
        story_dir.mkdir(exist_ok=True)
        (story_dir / f"{s['label']}.txt").write_text(s["story"], encoding="utf-8")

    print(f"\nDone. Zhuque: {zhuque_path}")

if __name__ == "__main__":
    asyncio.run(run())
