"""Minimal A1 writer test — one scene, fresh session, direct GenerationService."""
import asyncio, json, re, sys
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
from app.schemas.project import ProjectCreate, DocumentUpdate
from app.schemas.chapter import ChapterCreate

DB = REPO_ROOT / "__evaluation" / "sacrificial_preflight_fusion_v9_feasibility_v1_NM-03.sqlite3"
FROZEN = {"provider_id": "34c14b6b-7231-432a-96b2-8272329b828d", "model_id": "deepseek-v4-pro",
          "temperature": 0.7, "top_p": 1.0, "max_output_tokens": 6000, "timeout_seconds": 300}

SCENE = "小区自助洗衣房里，方笛认为自己那台滚筒还没洗完——她记得设定的是一小时，现在才过去四十分钟。"

async def main():
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        # Setup
        ps, cs = ProjectService(session), ChapterService(session)
        proj = await ps.create_project(ProjectCreate(name="a1_minimal_test", genre="现实场景"))
        chap = await cs.create_chapter(proj.id, ChapterCreate(title="测试", sort_order=1))
        await session.commit()

        # A1 planner prompt
        entry = next(e for e in BUILTIN_PROMPTS if e["name"] == "Chapter Architect v1")
        profile = PromptProfile(stage="planner", name=entry["name"], description=entry["description"], is_builtin=True)
        session.add(profile); await session.flush()
        pv = PromptVersion(profile_id=profile.id, version_number=99, system_template=entry["system_template"],
                          user_template=entry["user_template"], output_mode="structured",
                          output_schema_name="chapter_architect_v1")
        session.add(pv); await session.flush()
        await session.commit()

        # Run planner
        gen = GenerationService(session)
        run_obj = await gen.create_run(proj.id, chap.id, None, SCENE)
        await session.commit()

        planner = await gen.execute_stage(run_obj.id, "planner",
            dict(FROZEN, prompt_version_id=pv.id, target_length=2000))
        await session.flush()
        if not planner.error_code:
            await gen.select_candidate(run_obj.id, "planner", planner.id)
        await session.commit()

        parsed = json.loads(planner.parsed_output_json) if planner.parsed_output_json else None
        ok = parsed is not None and not planner.error_code
        print(f"A1 planner: parsed={ok} err={planner.error_code}")

        if not ok:
            return

        # W10 writer prompt
        w_entry = next(e for e in BUILTIN_PROMPTS if e["name"] == "Sacrificial Preflight Fusion Strict Limited v10")
        w_profile = PromptProfile(stage="writer", name=w_entry["name"], description=w_entry["description"], is_builtin=True)
        session.add(w_profile); await session.flush()
        w_pv = PromptVersion(profile_id=w_profile.id, version_number=99, system_template=w_entry["system_template"],
                            user_template=w_entry["user_template"], output_mode="xml_story", output_schema_name=None)
        session.add(w_pv); await session.flush()
        await session.commit()

        # FRESH GenerationService for writer
        gen2 = GenerationService(session)
        override = dict(FROZEN, prompt_version_id=w_pv.id, target_length=2000,
                       write_mode="new_chapter", writer_input_mode="complete_planner",
                       writer_brief=parsed)
        writer = await gen2.execute_stage(run_obj.id, "writer", override)
        await session.commit()

        raw = writer.raw_response or ""
        story_m = re.search(r"<story>(.*?)</story>", raw, re.DOTALL | re.I)
        story = story_m.group(1).strip() if story_m else ""
        print(f"A1W10: story={len(story)} chars err={writer.error_code}")
        if story:
            print(story[:500])

    await engine.dispose()

asyncio.run(main())
