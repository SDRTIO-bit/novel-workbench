import os
import asyncio
import pytest
import shutil

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_workflow_data")


@pytest.fixture(scope="module")
def api_client():
    os.environ["NW_DATA_DIR"] = TEST_DATA_DIR
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)

    import app.models.project  # noqa: F401
    import app.models.chapter  # noqa: F401
    import app.models.prompt  # noqa: F401
    import app.models.provider  # noqa: F401
    import app.models.workflow  # noqa: F401

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.db import Base

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())

    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.services.prompt_service import PromptService
    from app.services.provider_service import ProviderService
    from app.services.workflow_service import WorkflowService

    async def _seed():
        async with sm() as session:
            ps = PromptService(session)
            await ps.init_builtins()
            prs = ProviderService(session)
            await prs.init_builtins()
            ws = WorkflowService(session)
            await ws.init_builtin_default()
            await session.commit()

    asyncio.run(_seed())

    from app.main import app
    from app.db import get_db

    async def _override_get_db():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    from fastapi.testclient import TestClient

    client = TestClient(app)
    yield client

    del app.dependency_overrides[get_db]

    async def _dispose():
        await engine.dispose()

    asyncio.run(_dispose())

    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)


_counter = 0


def _uniq(base: str) -> str:
    global _counter
    _counter += 1
    return f"{base}_{_counter}"


class TestBuiltinWorkflow:
    def test_default_workflow_exists(self, api_client):
        resp = api_client.get("/api/workflows")
        assert resp.status_code == 200
        data = resp.json()
        defaults = [w for w in data if w["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "本地演示"

    def test_default_has_five_steps(self, api_client):
        resp = api_client.get("/api/workflows")
        default = [w for w in resp.json() if w["is_default"]][0]
        resp2 = api_client.get(f"/api/workflows/{default['id']}")
        assert resp2.status_code == 200
        data = resp2.json()
        stages = {s["stage"] for s in data["steps"]}
        assert stages == {"planner", "writer", "critic", "reviser", "judge"}


class TestWorkflowCRUD:
    def test_create_workflow(self, api_client):
        payload = {"name": _uniq("自定义工作流"), "description": "测试描述"}
        resp = api_client.post("/api/workflows", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["description"] == "测试描述"
        assert len(data["steps"]) == 5

    def test_create_workflow_empty_steps(self, api_client):
        payload = {"name": _uniq("空步骤工作流")}
        resp = api_client.post("/api/workflows", json=payload)
        data = resp.json()
        for step in data["steps"]:
            assert step["provider_id"] is None
            assert step["model_id"] is None
            assert step["temperature"] == 0.7

    def test_get_workflow(self, api_client):
        payload = {"name": _uniq("获取测试")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.get(f"/api/workflows/{wid}")
        assert resp2.status_code == 200
        assert resp2.json()["name"] == payload["name"]

    def test_update_workflow(self, api_client):
        payload = {"name": _uniq("更新前")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.patch(f"/api/workflows/{wid}", json={"name": "更新后"})
        assert resp2.status_code == 200
        assert resp2.json()["name"] == "更新后"

    def test_delete_workflow(self, api_client):
        payload = {"name": _uniq("待删除")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.delete(f"/api/workflows/{wid}")
        assert resp2.status_code == 204

        ids = [w["id"] for w in api_client.get("/api/workflows").json()]
        assert wid not in ids

    def test_duplicate_workflow(self, api_client):
        resp = api_client.get("/api/workflows")
        source_id = resp.json()[0]["id"]

        resp2 = api_client.post(f"/api/workflows/{source_id}/duplicate")
        assert resp2.status_code == 201
        data = resp2.json()
        assert "副本" in data["name"]
        assert data["id"] != source_id
        assert len(data["steps"]) == 5

    def test_workflow_not_found(self, api_client):
        resp = api_client.get("/api/workflows/fake-id")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "WORKFLOW_NOT_FOUND"

    def test_set_default(self, api_client):
        payload = {"name": _uniq("设为默认")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.post(f"/api/workflows/{wid}/set-default")
        assert resp2.status_code == 200
        assert resp2.json()["is_default"] is True

        all_profiles = api_client.get("/api/workflows").json()
        defaults = [w for w in all_profiles if w["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == wid


class TestStepConfig:
    def test_update_step_temperature(self, api_client):
        payload = {"name": _uniq("温度测试")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/writer",
            json={"temperature": 0.3},
        )
        assert resp2.status_code == 200
        assert resp2.json()["temperature"] == 0.3

    def test_update_step_temperature_out_of_range(self, api_client):
        payload = {"name": _uniq("温度超限")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/writer",
            json={"temperature": 3.0},
        )
        assert resp2.status_code == 400
        assert resp2.json()["error"]["code"] == "INVALID_TEMPERATURE"

    def test_update_step_top_p(self, api_client):
        payload = {"name": _uniq("top_p测试")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/critic",
            json={"top_p": 0.5},
        )
        assert resp2.status_code == 200
        assert resp2.json()["top_p"] == 0.5

    def test_update_step_top_p_out_of_range(self, api_client):
        payload = {"name": _uniq("top_p超限")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/critic",
            json={"top_p": 1.5},
        )
        assert resp2.status_code == 400
        assert resp2.json()["error"]["code"] == "INVALID_TOP_P"

    def test_update_step_max_tokens_out_of_range(self, api_client):
        payload = {"name": _uniq("tokens超限")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/planner",
            json={"max_output_tokens": 100},
        )
        assert resp2.status_code == 400
        assert resp2.json()["error"]["code"] == "INVALID_MAX_TOKENS"

    def test_update_step_timeout(self, api_client):
        payload = {"name": _uniq("超时测试")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/judge",
            json={"timeout_seconds": 300},
        )
        assert resp2.status_code == 200
        assert resp2.json()["timeout_seconds"] == 300

    def test_update_step_timeout_out_of_range(self, api_client):
        payload = {"name": _uniq("超时超限")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/judge",
            json={"timeout_seconds": 5},
        )
        assert resp2.status_code == 400
        assert resp2.json()["error"]["code"] == "INVALID_TIMEOUT"

    def test_update_step_provider_and_model(self, api_client):
        providers = api_client.get("/api/providers").json()
        mock = [p for p in providers if p["provider_type"] == "mock"][0]

        payload = {"name": _uniq("模型绑定")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/writer",
            json={
                "provider_id": mock["id"],
                "model_id": "mock-model",
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["provider_id"] == mock["id"]
        assert resp2.json()["model_id"] == "mock-model"

    def test_invalid_stage(self, api_client):
        payload = {"name": _uniq("无效阶段")}
        resp = api_client.post("/api/workflows", json=payload)
        wid = resp.json()["id"]

        resp2 = api_client.put(
            f"/api/workflows/{wid}/steps/editor",
            json={"temperature": 0.5},
        )
        assert resp2.status_code == 400
        assert resp2.json()["error"]["code"] == "INVALID_STAGE"
