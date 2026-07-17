import asyncio
import hashlib
import json
import os
import shutil

import pytest
from httpx import ASGITransport, AsyncClient

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_context_data")


@pytest.fixture(scope="module")
def _setup():
    os.environ["NW_DATA_DIR"] = TEST_DATA_DIR
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)

    import app.models.project
    import app.models.chapter
    import app.models.prompt
    import app.models.provider
    import app.models.workflow

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.db import Base

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())

    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _seed():
        async with sm() as session:
            from app.services.prompt_service import PromptService
            psvc = PromptService(session)
            await psvc.init_builtins()

            from app.services.provider_service import ProviderService
            prvsvc = ProviderService(session)
            await prvsvc.init_builtins()

            from app.services.workflow_service import WorkflowService
            wfsvc = WorkflowService(session)
            await wfsvc.init_builtin_default()

            await session.commit()

    asyncio.run(_seed())

    from app.main import app
    from app.db import get_db

    async def _override_get_db():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    return sm


@pytest.fixture(scope="module")
def api_client(_setup):
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_project(client: AsyncClient) -> str:
    resp = await client.post("/api/projects", json={"name": "测试小说", "genre": "奇幻"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_chapter(client: AsyncClient, project_id: str) -> str:
    resp = await client.post(
        f"/api/projects/{project_id}/chapters",
        json={"title": "第一章", "text": "夜幕降临，城市陷入沉睡。"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestContextPreview:
    @pytest.mark.asyncio
    async def test_preview_planner_context(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "planner",
            "scene_instruction": "主角在黑暗中醒来",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["input_snapshot_hash"]
        assert len(data["rendered_system_prompt"]) > 0
        assert len(data["rendered_user_prompt"]) > 0
        assert "主角在黑暗中醒来" in data["rendered_system_prompt"]
        assert data["total_chars"] > 0
        source_names = {s["name"] for s in data["sources"]}
        assert "project_name" in source_names
        assert "chapter_text" in source_names
        assert "scene_instruction" in source_names

    @pytest.mark.asyncio
    async def test_preview_writer_context(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        scene_plan = {"scene_goal": "测试", "location": "房间"}
        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "writer",
            "scene_instruction": "写一段觉醒场景",
            "scene_plan": scene_plan,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "测试" in data["rendered_user_prompt"]

    @pytest.mark.asyncio
    async def test_preview_tracks_tempo_guardrails(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        guardrails = {
            "entry_pressure": "林隅拖着探测车进库。",
            "dominant_disruption": "冷却管传出敲击声。",
            "allowed_viewpoint_misread": "他以为压力阀松了。",
            "disclosure_cap": 1,
            "must_remain_unclassified": ["敲击声来源"],
            "stop_after": "他切断外门电源。",
        }
        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "writer",
            "scene_instruction": "写维修场景",
            "tempo_guardrails": guardrails,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "tempo_guardrails" in {source["name"] for source in data["sources"]}

    @pytest.mark.asyncio
    async def test_preview_critic_context(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        draft = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "critic",
            "scene_instruction": "诊断此场景",
            "draft_text": draft,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "[P001]" in data["rendered_user_prompt"]
        assert "[P002]" in data["rendered_user_prompt"]
        assert "[P003]" in data["rendered_user_prompt"]

    @pytest.mark.asyncio
    async def test_preview_reviser_context(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        draft = "第一段。\n\n第二段。"
        critic_report = {
            "decision": "local_revision",
            "issues": [{"issue_id": "I01", "problem": "节奏太慢"}],
        }
        selected_issues = [{"issue_id": "I01"}]
        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "reviser",
            "scene_instruction": "修复节奏问题",
            "draft_text": draft,
            "critic_report": critic_report,
            "selected_issues": selected_issues,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "I01" in data["rendered_user_prompt"]

    @pytest.mark.asyncio
    async def test_preview_judge_context(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        original = "初稿内容。"
        revised = "修订稿内容。"
        critic_report = {"decision": "local_revision"}
        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "judge",
            "draft_text": original,
            "revised_text": revised,
            "critic_report": critic_report,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "初稿内容" in data["rendered_user_prompt"]
        assert "修订稿内容" in data["rendered_user_prompt"]

    @pytest.mark.asyncio
    async def test_preview_with_explicit_prompt_version(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        wf_resp = await api_client.get("/api/workflows")
        assert wf_resp.status_code == 200
        workflows = wf_resp.json()
        assert len(workflows) > 0
        wf_id = workflows[0]["id"]

        wf_detail = await api_client.get(f"/api/workflows/{wf_id}")
        assert wf_detail.status_code == 200
        wf_data = wf_detail.json()
        planner_step = next(s for s in wf_data["steps"] if s["stage"] == "planner")
        version_id = planner_step["prompt_version_id"]
        assert version_id

        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "planner",
            "scene_instruction": "测试",
            "prompt_version_id": version_id,
        })

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_preview_returns_consistent_hash(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        payload = {
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "planner",
            "scene_instruction": "测试一致性",
        }

        resp1 = await api_client.post("/api/context/preview", json=payload)
        resp2 = await api_client.post("/api/context/preview", json=payload)

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["input_snapshot_hash"] == resp2.json()["input_snapshot_hash"]

    @pytest.mark.asyncio
    async def test_hash_changes_on_input_diff(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        resp1 = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "planner",
            "scene_instruction": "A",
        })
        resp2 = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "stage": "planner",
            "scene_instruction": "B",
        })

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["input_snapshot_hash"] != resp2.json()["input_snapshot_hash"]

    @pytest.mark.asyncio
    async def test_project_not_found(self, api_client):
        resp = await api_client.post("/api/context/preview", json={
            "project_id": "nonexistent",
            "stage": "planner",
            "scene_instruction": "测试",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_chapter_not_found(self, api_client):
        project_id = await _create_project(api_client)

        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "chapter_id": "nonexistent",
            "stage": "planner",
            "scene_instruction": "测试",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_stage(self, api_client):
        project_id = await _create_project(api_client)

        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "stage": "invalid_stage",
            "scene_instruction": "测试",
        })
        assert resp.status_code == 422 or resp.status_code == 400

    @pytest.mark.asyncio
    async def test_truncation_on_large_context(self, api_client):
        project_id = await _create_project(api_client)

        large_text = "长篇内容。" * 50000

        await api_client.put(
            f"/api/projects/{project_id}/documents/world",
            json={"content": large_text},
        )

        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "stage": "planner",
            "scene_instruction": "短指令",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["truncated"] is True
        doc_source = next((s for s in data["sources"] if s["name"] == "project_documents"), None)
        assert doc_source is not None

    @pytest.mark.asyncio
    async def test_empty_inputs_handled(self, api_client):
        project_id = await _create_project(api_client)

        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "stage": "planner",
            "scene_instruction": "",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["input_snapshot_hash"]
        assert data["rendered_system_prompt"]
        assert data["rendered_user_prompt"]

    @pytest.mark.asyncio
    async def test_with_workflow_profile(self, api_client):
        project_id = await _create_project(api_client)

        wf_resp = await api_client.get("/api/workflows")
        assert wf_resp.status_code == 200
        workflows = wf_resp.json()
        assert len(workflows) > 0

        resp = await api_client.post("/api/context/preview", json={
            "project_id": project_id,
            "stage": "planner",
            "scene_instruction": "测试",
            "workflow_profile_id": workflows[0]["id"],
        })

        assert resp.status_code == 200
