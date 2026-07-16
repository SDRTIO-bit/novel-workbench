import os
import asyncio
import pytest
import shutil

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_provider_data")


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

    async def _seed():
        async with sm() as session:
            prompt_svc = PromptService(session)
            await prompt_svc.init_builtins()
            provider_svc = ProviderService(session)
            await provider_svc.init_builtins()
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


_class_counter = 0


def _uniq_name(base: str) -> str:
    global _class_counter
    _class_counter += 1
    return f"{base}_{_class_counter}"


class TestBuiltinProvider:
    def test_mock_provider_exists(self, api_client):
        resp = api_client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()
        mock_providers = [p for p in data if p["provider_type"] == "mock"]
        assert len(mock_providers) == 1
        mock = mock_providers[0]
        assert mock["name"] == "本地演示"
        assert mock["is_builtin"] is True

    def test_mock_provider_has_models(self, api_client):
        resp = api_client.get("/api/providers")
        data = resp.json()
        mock = [p for p in data if p["provider_type"] == "mock"][0]
        assert len(mock["models"]) >= 1
        assert any(m["model_id"] == "mock-model" for m in mock["models"])

    def test_mock_provider_cannot_be_deleted(self, api_client):
        resp = api_client.get("/api/providers")
        data = resp.json()
        mock_id = [p["id"] for p in data if p["is_builtin"]][0]
        resp2 = api_client.delete(f"/api/providers/{mock_id}")
        assert resp2.status_code == 400
        err = resp2.json()
        assert err["error"]["code"] == "BUILTIN_PROVIDER"


class TestProviderCRUD:
    def test_create_provider_with_key(self, api_client):
        payload = {
            "name": _uniq_name("测试服务商"),
            "provider_type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-key-12345",
        }
        resp = api_client.post("/api/providers", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["base_url"] == payload["base_url"]
        assert data["has_api_key"] is True
        assert "api_key" not in data
        assert "encrypted_api_key" not in data

    def test_create_provider_without_key(self, api_client):
        payload = {
            "name": _uniq_name("无密钥服务商"),
            "provider_type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
        }
        resp = api_client.post("/api/providers", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_api_key"] is False

    def test_list_providers_includes_both(self, api_client):
        payload = {
            "name": _uniq_name("列表测试"),
            "provider_type": "openai_compatible",
        }
        api_client.post("/api/providers", json=payload)
        resp = api_client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    def test_create_invalid_provider_type(self, api_client):
        payload = {
            "name": _uniq_name("无效类型"),
            "provider_type": "anthropic",
        }
        resp = api_client.post("/api/providers", json=payload)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_PROVIDER_TYPE"

    def test_update_provider_name(self, api_client):
        payload = {"name": _uniq_name("待更新"), "provider_type": "openai_compatible"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        resp2 = api_client.patch(f"/api/providers/{pid}", json={"name": "已更新名称"})
        assert resp2.status_code == 200
        assert resp2.json()["name"] == "已更新名称"

    def test_update_api_key(self, api_client):
        payload = {"name": _uniq_name("更新密钥"), "provider_type": "openai_compatible"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]
        assert resp.json()["has_api_key"] is False

        resp2 = api_client.patch(f"/api/providers/{pid}", json={"api_key": "sk-new-key"})
        assert resp2.status_code == 200
        assert resp2.json()["has_api_key"] is True

    def test_clear_api_key(self, api_client):
        payload = {
            "name": _uniq_name("清除密钥"),
            "provider_type": "openai_compatible",
            "api_key": "sk-temp",
        }
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]
        assert resp.json()["has_api_key"] is True

        resp2 = api_client.patch(f"/api/providers/{pid}", json={"clear_api_key": True})
        assert resp2.status_code == 200
        assert resp2.json()["has_api_key"] is False

    def test_empty_api_key_no_change(self, api_client):
        payload = {
            "name": _uniq_name("空密钥不变"),
            "provider_type": "openai_compatible",
            "api_key": "sk-existing",
        }
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]
        assert resp.json()["has_api_key"] is True

        resp2 = api_client.patch(f"/api/providers/{pid}", json={"name": "renamed", "api_key": ""})
        assert resp2.status_code == 200
        assert resp2.json()["has_api_key"] is True
        assert resp2.json()["name"] == "renamed"

    def test_delete_custom_provider(self, api_client):
        payload = {"name": _uniq_name("待删除"), "provider_type": "openai_compatible"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        resp2 = api_client.delete(f"/api/providers/{pid}")
        assert resp2.status_code == 204

        resp3 = api_client.get("/api/providers")
        ids = [p["id"] for p in resp3.json()]
        assert pid not in ids

    def test_get_nonexistent_provider(self, api_client):
        resp = api_client.delete("/api/providers/nonexistent-id")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PROVIDER_NOT_FOUND"


class TestModelManagement:
    def test_add_manual_model(self, api_client):
        payload = {"name": _uniq_name("手动模型"), "provider_type": "openai_compatible"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        model_payload = {"model_id": "custom-model-v1", "display_name": "自定义模型"}
        resp2 = api_client.post(f"/api/providers/{pid}/models", json=model_payload)
        assert resp2.status_code == 201
        assert resp2.json()["model_id"] == "custom-model-v1"
        assert resp2.json()["display_name"] == "自定义模型"
        assert resp2.json()["is_manual"] is True

    def test_add_duplicate_model_rejected(self, api_client):
        payload = {"name": _uniq_name("重复模型"), "provider_type": "openai_compatible"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        api_client.post(f"/api/providers/{pid}/models", json={"model_id": "dup-model"})
        resp2 = api_client.post(f"/api/providers/{pid}/models", json={"model_id": "dup-model"})
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "MODEL_EXISTS"

    def test_update_model(self, api_client):
        payload = {"name": _uniq_name("更新模型"), "provider_type": "openai_compatible"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        model_resp = api_client.post(f"/api/providers/{pid}/models", json={"model_id": "m1"})
        mid = model_resp.json()["id"]

        resp2 = api_client.patch(f"/api/providers/{pid}/models/{mid}", json={"display_name": "新名称"})
        assert resp2.status_code == 200
        assert resp2.json()["display_name"] == "新名称"

    def test_disable_model(self, api_client):
        payload = {"name": _uniq_name("禁用模型"), "provider_type": "openai_compatible"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        model_resp = api_client.post(f"/api/providers/{pid}/models", json={"model_id": "m2"})
        mid = model_resp.json()["id"]

        resp2 = api_client.patch(f"/api/providers/{pid}/models/{mid}", json={"enabled": False})
        assert resp2.status_code == 200
        assert resp2.json()["enabled"] is False

    def test_update_nonexistent_model(self, api_client):
        payload = {"name": _uniq_name("不存在模型"), "provider_type": "openai_compatible"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        resp2 = api_client.patch(f"/api/providers/{pid}/models/fake-id", json={"enabled": False})
        assert resp2.status_code == 404


class TestConnectionTest:
    def test_mock_connection(self, api_client):
        resp = api_client.get("/api/providers")
        mock_id = [p["id"] for p in resp.json() if p["provider_type"] == "mock"][0]
        resp2 = api_client.post(f"/api/providers/{mock_id}/test")
        assert resp2.status_code == 200
        result = resp2.json()
        assert result["success"] is True
        assert "Mock" in result["message"]

    def test_no_api_key(self, api_client):
        payload = {"name": _uniq_name("无密钥测试"), "provider_type": "openai_compatible", "base_url": "https://example.com"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        resp2 = api_client.post(f"/api/providers/{pid}/test")
        assert resp2.status_code == 200
        result = resp2.json()
        assert result["success"] is False
        assert "API Key" in result["message"]

    def test_no_base_url(self, api_client):
        payload = {"name": _uniq_name("无URL测试"), "provider_type": "openai_compatible", "api_key": "sk-test"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        resp2 = api_client.post(f"/api/providers/{pid}/test")
        assert resp2.status_code == 200
        result = resp2.json()
        assert result["success"] is False
        assert "Base URL" in result["message"]

    def test_connection_failure(self, api_client):
        payload = {"name": _uniq_name("连接失败"), "provider_type": "openai_compatible", "base_url": "https://127.0.0.1:19999", "api_key": "sk-test"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        resp2 = api_client.post(f"/api/providers/{pid}/test")
        assert resp2.status_code == 200
        result = resp2.json()
        assert result["success"] is False


class TestSyncModels:
    def test_mock_sync_noop(self, api_client):
        resp = api_client.get("/api/providers")
        mock_id = [p["id"] for p in resp.json() if p["provider_type"] == "mock"][0]
        resp2 = api_client.post(f"/api/providers/{mock_id}/sync-models")
        assert resp2.status_code == 200
        data = resp2.json()
        assert len(data["models"]) >= 1

    def test_sync_without_api_key_fails(self, api_client):
        payload = {"name": _uniq_name("无密钥同步"), "provider_type": "openai_compatible", "base_url": "https://example.com"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        resp2 = api_client.post(f"/api/providers/{pid}/sync-models")
        assert resp2.status_code == 400
        assert resp2.json()["error"]["code"] == "NO_API_KEY"

    def test_sync_without_base_url_fails(self, api_client):
        payload = {"name": _uniq_name("无URL同步"), "provider_type": "openai_compatible", "api_key": "sk-test"}
        resp = api_client.post("/api/providers", json=payload)
        pid = resp.json()["id"]

        resp2 = api_client.post(f"/api/providers/{pid}/sync-models")
        assert resp2.status_code == 400
        assert resp2.json()["error"]["code"] == "NO_BASE_URL"
