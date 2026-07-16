import os
import asyncio
import pytest
import shutil

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_api_data")


@pytest.fixture(scope="module")
def api_client():
    os.environ["NW_DATA_DIR"] = TEST_DATA_DIR
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)

    import app.models.project  # noqa: F401
    from app.db import engine, Base

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())

    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    yield client

    async def _dispose():
        await engine.dispose()

    asyncio.run(_dispose())

    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)


def test_create_project(api_client):
    resp = api_client.post("/api/projects", json={"name": "测试小说"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试小说"
    assert len(data["documents"]) == 8
    kinds = {d["kind"] for d in data["documents"]}
    assert kinds == {"synopsis", "outline", "characters", "world", "style", "principles", "summary", "notes"}


def test_list_projects(api_client):
    resp = api_client.get("/api/projects")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1


def test_get_project(api_client):
    create_resp = api_client.post("/api/projects", json={"name": "查看测试"})
    pid = create_resp.json()["id"]
    resp = api_client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "查看测试"


def test_get_project_not_found(api_client):
    resp = api_client.get("/api/projects/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_update_project(api_client):
    create_resp = api_client.post("/api/projects", json={"name": "待修改"})
    pid = create_resp.json()["id"]
    resp = api_client.patch(f"/api/projects/{pid}", json={"name": "已修改", "genre": "科幻"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "已修改"
    assert data["genre"] == "科幻"


def test_delete_project(api_client):
    create_resp = api_client.post("/api/projects", json={"name": "待删除"})
    pid = create_resp.json()["id"]
    resp = api_client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 204
    list_resp = api_client.get("/api/projects")
    ids = [p["id"] for p in list_resp.json()]
    assert pid not in ids


def test_restore_project(api_client):
    create_resp = api_client.post("/api/projects", json={"name": "待恢复"})
    pid = create_resp.json()["id"]
    api_client.delete(f"/api/projects/{pid}")
    resp = api_client.post(f"/api/projects/{pid}/restore")
    assert resp.status_code == 200
    assert resp.json()["deleted_at"] is None


def test_duplicate_project(api_client):
    create_resp = api_client.post("/api/projects", json={"name": "原项目"})
    pid = create_resp.json()["id"]
    resp = api_client.post(f"/api/projects/{pid}/duplicate")
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] != pid
    assert data["name"] == "副本"
    assert len(data["documents"]) == 8


def test_get_documents(api_client):
    create_resp = api_client.post("/api/projects", json={"name": "资料测试"})
    pid = create_resp.json()["id"]
    resp = api_client.get(f"/api/projects/{pid}/documents")
    assert resp.status_code == 200
    assert len(resp.json()) == 8


def test_update_document(api_client):
    create_resp = api_client.post("/api/projects", json={"name": "文档更新测试"})
    pid = create_resp.json()["id"]
    resp = api_client.put(
        f"/api/projects/{pid}/documents/characters",
        json={"title": "人物设定", "content": "张三，25岁"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "人物设定"
    assert data["content"] == "张三，25岁"
