"""Retry CH2 only."""
import asyncio, hashlib, json, re, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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

V9_DB = REPO_ROOT / "__evaluation" / "sacrificial_preflight_fusion_v9_feasibility_v1"
EVIDENCE = REPO_ROOT / "__evaluation" / "transmigration_magic_city"

CH2_INSTRUCTION = (
    "出院后，林昭被带到城市中心的'天赋管理局'进行强制天赋登记。"
    "所有公民在十八岁时必须测试魔力属性。测试仪器是一个巨大的水晶球，"
    "受试者将手放上去，水晶球会根据体内魔力回路呈现对应颜色。"
    "前面排队的人分别测出了火红、水蓝、风青等标准属性。"
    "轮到林昭时，他犹豫地将手放上去——水晶球先是毫无反应（因为他没有魔力回路），"
    "然后突然爆发出刺眼的金色光芒，光芒中隐约可见旋转的符文图案，"
    "完全不同于任何已记录属性。测试官震惊地记录下'未知变异属性'，并向上级报告。"
    "林昭被单独留下，一位神秘的中年女性出现，自称是'异常天赋研究所'的负责人，"
    "对林昭表现出极大兴趣。本章停在女性说出'你的能量体系……不属于这个世界'的事实。"
)

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "temperature": 0.7, "top_p": 1.0,
    "max_output_tokens": 6000, "timeout_seconds": 300,
}

PLANNER = {"name": "默认场景规划", "schema": "planner_v2", "mode": "writer_brief"}
WRITER = {"name": "Sacrificial Preflight Fusion Strict Limited v10", "mode": "writer_brief"}

def extract_story(xml): return re.search(r"<story>(.*?)</story>", xml, re.DOTALL|re.I)
def extract_notes(xml): return re.search(r"<draft_notes>(.*?)</draft_notes>", xml, re.DOTALL|re.I)


async def run_chapter(db_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        ps, cs = ProjectService(session), ChapterService(session)
        gen = GenerationService(session)

        proj_name = "transmigration_CH2_retry"
        proj = (await session.execute(
            select(Project).where(Project.name == proj_name)
        )).scalars().first()
        if not proj:
            proj = await ps.create_project(ProjectCreate(name=proj_name, genre="穿越魔法都市"))
            await ps.update_document(proj.id, "principles", DocumentUpdate(
                title="世界观设定", content="""
世界设定：现代都市外观，科学体系完整（有医院、学校、政府），但底层逻辑是魔法。
每个人体内有魔力回路，按天赋分为五种基础属性：火（红）、水（蓝）、风（青）、土（黄）、雷（紫）。
另有罕见变异属性，颜色不固定。
主角林昭是穿越者，没有魔力回路，觉醒的是类似火影查克拉的能量体系：
- 金色光芒，不受五属性限制，可模拟任何属性特性
- 代价：消耗极快，续航差
- 运行方式：集中在特定部位爆发（脚底、指尖等）
- 与魔力完全不同，测试仪器无法识别
"""))
        chap = (await session.execute(
            select(Chapter).where(Chapter.project_id == proj.id)
        )).scalars().first()
        if not chap:
            chap = await cs.create_chapter(proj.id, ChapterCreate(title="第二章：天赋测试与震惊", sort_order=1))
        await session.commit()

        entry = next(e for e in BUILTIN_PROMPTS if e["name"] == PLANNER["name"] and e["stage"] == "planner")
        profile = (await session.execute(
            select(PromptProfile).where(PromptProfile.name == entry["name"], PromptProfile.is_builtin == True)
        )).scalars().first()
        if not profile:
            profile = PromptProfile(stage="planner", name=entry["name"], description=entry["description"], is_builtin=True)
            session.add(profile); await session.flush()
        await session.refresh(profile, ["versions"])
        vn = max((v.version_number for v in profile.versions), default=0) + 1
        pv = PromptVersion(profile_id=profile.id, version_number=vn,
                          system_template=entry["system_template"],
                          user_template=entry["user_template"],
                          output_mode="structured",
                          output_schema_name=PLANNER["schema"])
        session.add(pv); await session.flush()
        await session.commit()

        run_obj = await gen.create_run(proj.id, chap.id, None, CH2_INSTRUCTION)
        await session.commit()
        override = dict(FROZEN, prompt_version_id=pv.id, target_length=3000)
        
        try:
            planner = await gen.execute_stage(run_obj.id, "planner", override)
            await session.flush()
            if not planner.error_code:
                await gen.select_candidate(run_obj.id, "planner", planner.id)
            await session.commit()
        except Exception as e:
            print(f"  planner ERROR: {e}")
            await engine.dispose()
            return None

        parsed = None
        if planner.parsed_output_json:
            try: parsed = json.loads(planner.parsed_output_json)
            except: pass
        
        ok = parsed is not None and not planner.error_code
        print(f"  planner: parsed={ok} err={planner.error_code} lat={planner.latency_ms}ms")
        if not ok:
            await engine.dispose()
            return None

        brief = compile_writer_input(parsed, PLANNER["mode"])

        w_entry = next(e for e in BUILTIN_PROMPTS if e["name"] == WRITER["name"] and e["stage"] == "writer")
        w_profile = (await session.execute(
            select(PromptProfile).where(PromptProfile.name == w_entry["name"], PromptProfile.is_builtin == True)
        )).scalars().first()
        if not w_profile:
            w_profile = PromptProfile(stage="writer", name=w_entry["name"], description=w_entry["description"], is_builtin=True)
            session.add(w_profile); await session.flush()
        await session.refresh(w_profile, ["versions"])
        w_vn = max((v.version_number for v in w_profile.versions), default=0) + 1
        w_pv = PromptVersion(profile_id=w_profile.id, version_number=w_vn,
                            system_template=w_entry["system_template"],
                            user_template=w_entry["user_template"],
                            output_mode="xml_story", output_schema_name=None)
        session.add(w_pv); await session.flush()
        await session.commit()

        w_override = dict(FROZEN, prompt_version_id=w_pv.id, target_length=3000,
                         write_mode="new_chapter", writer_input_mode=WRITER["mode"],
                         writer_brief=brief)
        try:
            writer = await gen.execute_stage(run_obj.id, "writer", w_override)
            await session.commit()
        except Exception as e:
            print(f"    writer ERROR: {e}")
            await engine.dispose()
            return None

        raw = writer.raw_response or ""
        story_m = extract_story(raw)
        notes_m = extract_notes(raw)
        story_text = story_m.group(1).strip() if story_m else ""
        notes_text = notes_m.group(1).strip() if notes_m else ""

        status = "ok" if story_text and not writer.error_code else f"err={writer.error_code}"
        print(f"    writer: story={len(story_text)} chars {status}")

    await engine.dispose()
    return {"story": story_text, "notes": notes_text, "error": writer.error_code, "story_chars": len(story_text)}


async def run():
    db_path = V9_DB.with_name(f"{V9_DB.name}_TRANSMIGRATION.sqlite3")
    result = await run_chapter(db_path)
    if result and result["story"] and not result["error"]:
        path = EVIDENCE / "CH2_retry.txt"
        path.write_text(result["story"], encoding="utf-8")
        print(f"\nCH2 retry SUCCESS: {path}")
        # Also update the combined file
        ch1 = (EVIDENCE / "CH1.txt").read_text(encoding="utf-8") if (EVIDENCE / "CH1.txt").exists() else ""
        ch3 = (EVIDENCE / "CH3.txt").read_text(encoding="utf-8") if (EVIDENCE / "CH3.txt").exists() else ""
        SEP = "\n\n" + "="*40 + "\n\n"
        full = f"第一章：车祸与觉醒\n\n{ch1}{SEP}第二章：天赋测试与震惊\n\n{result['story']}{SEP}第三章：查克拉的第一次实战\n\n{ch3}"
        (EVIDENCE / "opening_three_chapters.txt").write_text(full, encoding="utf-8")
        print("Updated combined file.")
    else:
        print("\nCH2 retry FAILED.")


if __name__ == "__main__":
    asyncio.run(run())
