"""Experiment: Transmigration + Magic + Modern City — Opening 3 Chapters.
Uses working P2 planner + W10 writer pipeline.
"""
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
from app.db import Base

V9_DB = REPO_ROOT / "__evaluation" / "sacrificial_preflight_fusion_v9_feasibility_v1"
EVIDENCE = REPO_ROOT / "__evaluation" / "transmigration_magic_city"

# Scene instructions for opening 3 chapters
# Each chapter is a separate scene run
CHAPTERS = [
    ("CH1", "第一章：车祸与觉醒",
     "主角林昭是一名普通的大学生，深夜打工回家的路上被一辆失控的货车撞飞。在濒死的瞬间，他感觉到一股奇异的力量撕裂了意识。当他再次睁开眼睛，发现自己躺在一张陌生的病床上，周围是现代化的医院设备，但空气中弥漫着淡淡的蓝色光晕——那是魔力流动的痕迹。一个护士走进来，随手在空中划出一道符文，监护仪的数据立刻更新。林昭意识到，这个世界看起来和现代地球一样有科学体系，但底层逻辑是魔法。每个人体内都有魔力，按照天赋分为五种基础属性（火、水、风、土、雷）以及罕见的变异属性。而林昭作为穿越者，体内没有这个世界的魔力回路，却意外觉醒了一种类似火影忍者查克拉体系的能量——它不受五属性限制，可以模拟任何属性的特性，但代价是消耗极快。本章停在林昭第一次成功凝聚查克拉，指尖冒出淡金色光芒，被进来的医生看到。"),
    ("CH2", "第二章：天赋测试与震惊",
     "出院后，林昭被带到城市中心的'天赋管理局'进行强制天赋登记。所有公民在十八岁时必须测试魔力属性。测试仪器是一个巨大的水晶球，受试者将手放上去，水晶球会根据体内魔力回路呈现对应颜色。前面排队的人分别测出了火红、水蓝、风青等标准属性。轮到林昭时，他犹豫地将手放上去——水晶球先是毫无反应（因为他没有魔力回路），然后突然爆发出刺眼的金色光芒，光芒中隐约可见旋转的符文图案，完全不同于任何已记录属性。测试官震惊地记录下'未知变异属性'，并向上级报告。林昭被单独留下，一位神秘的中年女性出现，自称是'异常天赋研究所'的负责人，对林昭表现出极大兴趣。本章停在女性说出'你的能量体系……不属于这个世界'的事实。"),
    ("CH3", "第三章：查克拉的第一次实战",
     "林昭被安排进入一所特殊的学院——表面上是一所普通高中，实际上是培养异常天赋者的秘密机构。入学第一天，他就被高年级的学生挑衅。对方是一个火属性天赋者，能徒手释放火焰冲击。在训练场上，对方故意将火焰射向林昭，想给这个'走后门进来的未知属性'一个下马威。林昭本能地调动体内查克拉，按照前世看过的火影设定，尝试将能量集中在脚底——他猛地跃起，高度远超常人，躲过了火焰。落地时查克拉耗尽，双腿发软，但他成功避开了攻击。周围一片寂静。本章停在教官走过来，看着林昭脚底下裂开的地面（查克拉爆发造成的痕迹），说出'这种能量运行方式……从未见过'的事实。"),
]

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


async def run_chapter(db_path, ch_id, title, scene_instruction):
    """Run ONE chapter through P2+W10 in a fresh session."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        ps, cs = ProjectService(session), ChapterService(session)
        gen = GenerationService(session)

        proj_name = f"transmigration_{ch_id}"
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
            chap = await cs.create_chapter(proj.id, ChapterCreate(title=title, sort_order=1))
        await session.commit()

        # Planner prompt
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

        # Run planner
        run_obj = await gen.create_run(proj.id, chap.id, None, scene_instruction)
        await session.commit()
        override = dict(FROZEN, prompt_version_id=pv.id, target_length=3000)
        
        try:
            planner = await gen.execute_stage(run_obj.id, "planner", override)
            await session.flush()
            if not planner.error_code:
                await gen.select_candidate(run_obj.id, "planner", planner.id)
            await session.commit()
        except Exception as e:
            print(f"  [{ch_id}] planner ERROR: {e}")
            await engine.dispose()
            return None

        parsed = None
        if planner.parsed_output_json:
            try: parsed = json.loads(planner.parsed_output_json)
            except: pass
        
        ok = parsed is not None and not planner.error_code
        print(f"  [{ch_id}] planner: parsed={ok} err={planner.error_code} lat={planner.latency_ms}ms")
        if not ok:
            await engine.dispose()
            return None

        brief = compile_writer_input(parsed, PLANNER["mode"])
        brief_sha = hashlib.sha256(json.dumps(brief, ensure_ascii=False).encode()).hexdigest()[:12]

        # Writer prompt
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
            print(f"    [{ch_id}] writer ERROR: {e}")
            await engine.dispose()
            return None

        raw = writer.raw_response or ""
        story_m = extract_story(raw)
        notes_m = extract_notes(raw)
        story_text = story_m.group(1).strip() if story_m else ""
        notes_text = notes_m.group(1).strip() if notes_m else ""

        status = "ok" if story_text and not writer.error_code else f"err={writer.error_code}"
        print(f"    [{ch_id}] writer: story={len(story_text)} chars {status}")

    await engine.dispose()
    return {"ch_id": ch_id, "title": title, "story": story_text, "notes": notes_text,
            "brief_sha": brief_sha, "error": writer.error_code, "story_chars": len(story_text)}


async def run():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    db_path = V9_DB.with_name(f"{V9_DB.name}_TRANSMIGRATION.sqlite3")
    
    all_chapters = []
    for ch_id, title, instruction in CHAPTERS:
        result = await run_chapter(db_path, ch_id, title, instruction)
        if result:
            all_chapters.append(result)

    # Assemble opening 3 chapters
    valid = [c for c in all_chapters if c["story"] and not c["error"]]
    SEP = "\n\n" + "="*40 + "\n\n"
    full_text = SEP.join([f"{c['title']}\n\n{c['story']}" for c in valid])
    
    output_path = EVIDENCE / "opening_three_chapters.txt"
    output_path.write_text(full_text, encoding="utf-8")
    sha = hashlib.sha256(full_text.encode()).hexdigest()

    report = f"""=== 穿越魔法都市 · 开篇三章 ===
主题：穿越 + 魔法 + 现代都市
主角：林昭（查克拉体系穿越者）
生成章节：{len(valid)}/3
总字数：{sum(c['story_chars'] for c in valid)}
SHA256: {sha}
输出路径: {output_path}

── 各章详情 ──
"""
    for c in valid:
        report += f"  {c['ch_id']}: {c['title']} | {c['story_chars']} chars | status=ok\n"
    for c in all_chapters:
        if c not in valid:
            report += f"  {c['ch_id']}: {c['title']} | FAILED err={c['error']}\n"

    print("\n" + report)
    (EVIDENCE / "report.txt").write_text(report, encoding="utf-8")
    
    # Save individual chapters
    for c in valid:
        (EVIDENCE / f"{c['ch_id']}.txt").write_text(c["story"], encoding="utf-8")

    print(f"\nDone. Output: {output_path}")


if __name__ == "__main__":
    asyncio.run(run())
