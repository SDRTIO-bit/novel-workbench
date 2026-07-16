import asyncio
import os
import shutil

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_generation_data")


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
    import app.models.generation

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
    from httpx import ASGITransport, AsyncClient
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_project(client):
    resp = await client.post("/api/projects", json={"name": "测试小说", "genre": "奇幻"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_chapter(client, project_id):
    resp = await client.post(
        f"/api/projects/{project_id}/chapters",
        json={"title": "第一章", "text": "测试内容。"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _step(data, stage):
    return next(s for s in data["steps"] if s["stage"] == stage)


class TestGenerationRunCreation:
    @pytest.mark.asyncio
    async def test_create_run(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "scene_instruction": "测试场景指令",
        })

        assert resp.status_code == 201
        data = resp.json()
        assert data["project_id"] == project_id
        assert data["chapter_id"] == chapter_id
        assert data["scene_instruction"] == "测试场景指令"
        assert data["status"] == "pending"
        assert len(data["steps"]) == 5
        assert data["steps"][0]["stage"] == "planner"

    @pytest.mark.asyncio
    async def test_create_run_uses_default_workflow(self, api_client):
        project_id = await _create_project(api_client)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "scene_instruction": "测试",
        })

        assert resp.status_code == 201
        data = resp.json()
        assert data["workflow_profile_id"] is not None

    @pytest.mark.asyncio
    async def test_create_run_without_chapter(self, api_client):
        project_id = await _create_project(api_client)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "scene_instruction": "无章节测试",
        })

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_list_runs_by_project(self, api_client):
        project_id = await _create_project(api_client)

        await api_client.post("/api/runs", json={
            "project_id": project_id,
            "scene_instruction": "Run 1",
        })
        await api_client.post("/api/runs", json={
            "project_id": project_id,
            "scene_instruction": "Run 2",
        })

        resp = await api_client.get(f"/api/projects/{project_id}/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_get_run_detail(self, api_client):
        project_id = await _create_project(api_client)

        create_resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "scene_instruction": "详细测试",
        })
        run_id = create_resp.json()["id"]

        resp = await api_client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run_id
        assert len(data["steps"]) == 5
        assert all(s["status"] == "pending" for s in data["steps"])


class TestCandidateLifecycle:
    @pytest.mark.asyncio
    async def test_candidate_attempt_number_increments(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        create_resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
        })
        run_id = create_resp.json()["id"]

        resp1 = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        assert resp1.status_code == 200
        c1 = resp1.json()
        assert c1["error_code"] is None

        resp2 = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        assert resp2.status_code == 200
        c2 = resp2.json()
        assert c2["error_code"] is None

        run_detail = await api_client.get(f"/api/runs/{run_id}")
        planner_step = next(s for s in run_detail.json()["steps"] if s["stage"] == "planner")
        candidates = sorted(planner_step["candidates"], key=lambda c: c["attempt_number"])
        assert len(candidates) == 2
        assert candidates[0]["attempt_number"] == 1
        assert candidates[1]["attempt_number"] == 2

    @pytest.mark.asyncio
    async def test_select_candidate(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        create_resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
        })
        run_id = create_resp.json()["id"]

        resp = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        assert resp.status_code == 200

        run_detail = await api_client.get(f"/api/runs/{run_id}")
        candidate_id = next(
            s for s in run_detail.json()["steps"] if s["stage"] == "planner"
        )["candidates"][0]["id"]

        select_resp = await api_client.post(
            f"/api/runs/{run_id}/steps/planner/select/{candidate_id}"
        )
        assert select_resp.status_code == 200

        run_detail = await api_client.get(f"/api/runs/{run_id}")
        planner_step = next(s for s in run_detail.json()["steps"] if s["stage"] == "planner")
        assert planner_step["status"] == "completed"
        assert planner_step["selected_candidate_id"] == candidate_id

    @pytest.mark.asyncio
    async def test_downstream_stale_on_upstream_change(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        create_resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
        })
        run_id = create_resp.json()["id"]

        await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        run_detail = await api_client.get(f"/api/runs/{run_id}")
        candidate_id = next(
            s for s in run_detail.json()["steps"] if s["stage"] == "planner"
        )["candidates"][0]["id"]
        await api_client.post(f"/api/runs/{run_id}/steps/planner/select/{candidate_id}")

        await api_client.post(f"/api/runs/{run_id}/steps/writer/execute", json={})
        run_detail = await api_client.get(f"/api/runs/{run_id}")
        writer_candidate_id = next(
            s for s in run_detail.json()["steps"] if s["stage"] == "writer"
        )["candidates"][0]["id"]
        await api_client.post(f"/api/runs/{run_id}/steps/writer/select/{writer_candidate_id}")

        await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        run_detail = await api_client.get(f"/api/runs/{run_id}")
        new_planner_candidate_id = next(
            s for s in run_detail.json()["steps"] if s["stage"] == "planner"
        )["candidates"][1]["id"]
        await api_client.post(f"/api/runs/{run_id}/steps/planner/select/{new_planner_candidate_id}")

        run_detail = await api_client.get(f"/api/runs/{run_id}")
        writer_step = next(s for s in run_detail.json()["steps"] if s["stage"] == "writer")
        assert writer_step["status"] == "stale"
        critic_step = next(s for s in run_detail.json()["steps"] if s["stage"] == "critic")
        assert critic_step["status"] == "pending"

    @pytest.mark.asyncio
    async def test_old_candidates_still_accessible(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        create_resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
        })
        run_id = create_resp.json()["id"]

        await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})

        run_detail = await api_client.get(f"/api/runs/{run_id}")
        candidates = next(
            s for s in run_detail.json()["steps"] if s["stage"] == "planner"
        )["candidates"]
        assert len(candidates) == 3
        for i, c in enumerate(candidates):
            assert c["attempt_number"] == i + 1
            assert "parsed_output_json" in c
            assert "raw_response" in c
            assert "input_tokens" in c
            assert "output_tokens" in c
            assert "latency_ms" in c

    @pytest.mark.asyncio
    async def test_failed_candidate_can_be_retried(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        create_resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
        })
        run_id = create_resp.json()["id"]

        resp1 = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        assert resp1.status_code == 200
        assert resp1.json()["error_code"] is None

        resp2 = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        assert resp2.status_code == 200

        run_detail = await api_client.get(f"/api/runs/{run_id}")
        candidates = next(
            s for s in run_detail.json()["steps"] if s["stage"] == "planner"
        )["candidates"]
        assert len(candidates) == 2
        assert candidates[0]["parsed_output_json"] is not None
        assert candidates[1]["parsed_output_json"] is not None

    @pytest.mark.asyncio
    async def test_cannot_execute_running_step(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        create_resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
        })
        run_id = create_resp.json()["id"]

        await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        resp = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_run_workflow_produces_correct_step_order(self, api_client):
        project_id = await _create_project(api_client)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "scene_instruction": "步骤顺序测试",
        })

        assert resp.status_code == 201
        steps = resp.json()["steps"]
        assert [s["stage"] for s in steps] == ["planner", "writer", "critic", "reviser", "judge"]

    @pytest.mark.asyncio
    async def test_get_run_with_full_details(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        create_resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "scene_instruction": "完整测试",
        })
        run_id = create_resp.json()["id"]

        await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        run_detail = await api_client.get(f"/api/runs/{run_id}")

        assert run_detail.status_code == 200
        data = run_detail.json()
        planner = next(s for s in data["steps"] if s["stage"] == "planner")
        assert "rendered_system_prompt" in planner["candidates"][0]
        assert "rendered_user_prompt" in planner["candidates"][0]
        assert "parameters_json" in planner["candidates"][0]
