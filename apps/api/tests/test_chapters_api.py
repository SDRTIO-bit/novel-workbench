import os
import asyncio
import pytest
import shutil

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_chapter_data")


@pytest.fixture(scope="module")
def api_client():
    os.environ["NW_DATA_DIR"] = TEST_DATA_DIR
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)

    import app.models.project  # noqa: F401
    import app.models.chapter  # noqa: F401
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


def _create_test_project(client):
    resp = client.post("/api/projects", json={"name": "章节测试项目"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_list_chapters_empty(api_client):
    pid = _create_test_project(api_client)
    resp = api_client.get(f"/api/projects/{pid}/chapters")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_chapter(api_client):
    pid = _create_test_project(api_client)
    resp = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "第一章", "current_text": "开端"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "第一章"
    assert data["current_text"] == "开端"
    assert data["project_id"] == pid
    assert data["sort_order"] == 1


def test_list_chapters(api_client):
    pid = _create_test_project(api_client)
    api_client.post(f"/api/projects/{pid}/chapters", json={"title": "A"})
    api_client.post(f"/api/projects/{pid}/chapters", json={"title": "B"})
    resp = api_client.get(f"/api/projects/{pid}/chapters")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_chapter_not_found(api_client):
    resp = api_client.patch(
        "/api/chapters/nonexistent-id",
        json={"expected_updated_at": "2020-01-01T00:00:00"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CHAPTER_NOT_FOUND"


def test_update_chapter(api_client):
    pid = _create_test_project(api_client)
    create_resp = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "待修改"})
    chapter = create_resp.json()

    resp = api_client.patch(
        f"/api/chapters/{chapter['id']}",
        json={
            "title": "已修改",
            "current_text": "新内容",
            "expected_updated_at": chapter["updated_at"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "已修改"
    assert data["current_text"] == "新内容"


def test_update_chapter_conflict(api_client):
    pid = _create_test_project(api_client)
    create_resp = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "冲突测试"})
    chapter = create_resp.json()

    update1 = api_client.patch(
        f"/api/chapters/{chapter['id']}",
        json={
            "title": "先改",
            "expected_updated_at": chapter["updated_at"],
        },
    )
    assert update1.status_code == 200

    resp = api_client.patch(
        f"/api/chapters/{chapter['id']}",
        json={
            "title": "后改",
            "expected_updated_at": chapter["updated_at"],
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CHAPTER_EDIT_CONFLICT"
    assert "server_current_text" in resp.json()["error"]["details"]


def test_delete_chapter(api_client):
    pid = _create_test_project(api_client)
    create_resp = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "待删除"})
    cid = create_resp.json()["id"]

    resp = api_client.delete(f"/api/chapters/{cid}")
    assert resp.status_code == 204

    list_resp = api_client.get(f"/api/projects/{pid}/chapters")
    ids = [c["id"] for c in list_resp.json()]
    assert cid not in ids


def test_restore_chapter(api_client):
    pid = _create_test_project(api_client)
    create_resp = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "待恢复"})
    cid = create_resp.json()["id"]

    api_client.delete(f"/api/chapters/{cid}")
    resp = api_client.post(f"/api/chapters/{cid}/restore")
    assert resp.status_code == 200
    assert resp.json()["deleted_at"] is None


def test_reorder_chapters(api_client):
    pid = _create_test_project(api_client)
    a = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "A"}).json()
    b = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "B"}).json()

    resp = api_client.post(
        "/api/chapters/reorder",
        json={"items": [{"id": a["id"], "sort_order": 2}, {"id": b["id"], "sort_order": 1}]},
    )
    assert resp.status_code == 200

    chapters = api_client.get(f"/api/projects/{pid}/chapters").json()
    titles = [c["title"] for c in chapters]
    assert titles == ["B", "A"]


def test_create_version(api_client):
    pid = _create_test_project(api_client)
    create_resp = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "版本测试", "current_text": "v0"})
    cid = create_resp.json()["id"]

    resp = api_client.post(f"/api/chapters/{cid}/versions?note=首次保存")
    assert resp.status_code == 201
    data = resp.json()
    assert data["version_number"] == 1
    assert data["text"] == "v0"
    assert data["source"] == "manual"
    assert data["note"] == "首次保存"


def test_get_versions(api_client):
    pid = _create_test_project(api_client)
    create_resp = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "多版本测试", "current_text": "v0"})
    cid = create_resp.json()["id"]

    api_client.post(f"/api/chapters/{cid}/versions?note=版本1")
    # Update text then create another version
    chapter = api_client.get(f"/api/projects/{pid}/chapters").json()[0]
    api_client.patch(
        f"/api/chapters/{cid}",
        json={"current_text": "v1", "expected_updated_at": chapter["updated_at"]},
    )
    api_client.post(f"/api/chapters/{cid}/versions?note=版本2")

    resp = api_client.get(f"/api/chapters/{cid}/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1


def test_restore_version(api_client):
    pid = _create_test_project(api_client)
    create_resp = api_client.post(f"/api/projects/{pid}/chapters", json={"title": "恢复测试", "current_text": "v0"})
    cid = create_resp.json()["id"]

    v1 = api_client.post(f"/api/chapters/{cid}/versions?note=v0保存").json()

    chapter = api_client.get(f"/api/projects/{pid}/chapters").json()[0]
    api_client.patch(
        f"/api/chapters/{cid}",
        json={"current_text": "v1", "expected_updated_at": chapter["updated_at"]},
    )

    resp = api_client.post(f"/api/chapters/{cid}/restore-version/{v1['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_text"] == "v0"

    # Check that a restore_backup version was created
    versions = api_client.get(f"/api/chapters/{cid}/versions").json()
    sources = [v["source"] for v in versions]
    assert "restore_backup" in sources
