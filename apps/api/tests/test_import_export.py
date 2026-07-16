import os
import json
import asyncio
import pytest
import shutil

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_import_data")


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


def _create_project(client, name="导入导出测试"):
    resp = client.post("/api/projects", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


SAMPLE_TXT = """第一章 开端
这是第一章的内容。
测试正文第二行。

第二章 发展
这是第二章的内容。
第二章第二行。"""

SAMPLE_MD = """# 第一章 开端

这是第一章的内容。
测试正文第二行。

# 第二章 发展

这是第二章的内容。
第二章第二行。"""


def test_preview_txt(api_client):
    resp = api_client.post(
        "/api/import/preview",
        files={"file": ("test.txt", SAMPLE_TXT.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["preview"]["total_chapters"] == 2
    assert data["preview"]["total_chars"] == len(SAMPLE_TXT)


def test_preview_markdown(api_client):
    resp = api_client.post(
        "/api/import/preview",
        files={"file": ("test.md", SAMPLE_MD.encode("utf-8"), "text/markdown")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["preview"]["total_chapters"] == 2


def test_preview_no_chapter_heading(api_client):
    resp = api_client.post(
        "/api/import/preview",
        files={"file": ("plain.txt", "这是一段普通的文本，没有任何章节标题。".encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["preview"]["total_chapters"] == 1


def test_commit_import(api_client):
    pid = _create_project(api_client, "提交导入测试")

    preview_resp = api_client.post(
        "/api/import/preview",
        files={"file": ("chapters.txt", SAMPLE_TXT.encode("utf-8"), "text/plain")},
    )
    chapters = preview_resp.json()["chapters"]

    resp = api_client.post(
        f"/api/projects/{pid}/import/commit",
        data={"chapters": json.dumps(chapters)},
    )
    assert resp.status_code == 200
    created = resp.json()["chapters"]
    assert len(created) == 2

    list_resp = api_client.get(f"/api/projects/{pid}/chapters")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2


def test_export_txt(api_client):
    pid = _create_project(api_client, "导出TXT测试")

    preview = api_client.post(
        "/api/import/preview",
        files={"file": ("chapters.txt", SAMPLE_TXT.encode("utf-8"), "text/plain")},
    )
    chapters = preview.json()["chapters"]
    api_client.post(
        f"/api/projects/{pid}/import/commit",
        data={"chapters": json.dumps(chapters)},
    )

    resp = api_client.get(f"/api/projects/{pid}/export?format=txt")
    assert resp.status_code == 200
    assert "第一章 开端" in resp.text
    assert "第二章 发展" in resp.text


def test_export_markdown(api_client):
    pid = _create_project(api_client, "导出MD测试")

    preview = api_client.post(
        "/api/import/preview",
        files={"file": ("chapters.md", SAMPLE_MD.encode("utf-8"), "text/markdown")},
    )
    chapters = preview.json()["chapters"]
    api_client.post(
        f"/api/projects/{pid}/import/commit",
        data={"chapters": json.dumps(chapters)},
    )

    resp = api_client.get(f"/api/projects/{pid}/export?format=md")
    assert resp.status_code == 200
    assert "# 第一章 开端" in resp.text


def test_export_json(api_client):
    pid = _create_project(api_client, "导出JSON测试")

    preview = api_client.post(
        "/api/import/preview",
        files={"file": ("chapters.txt", SAMPLE_TXT.encode("utf-8"), "text/plain")},
    )
    chapters = preview.json()["chapters"]
    api_client.post(
        f"/api/projects/{pid}/import/commit",
        data={"chapters": json.dumps(chapters)},
    )

    resp = api_client.get(f"/api/projects/{pid}/export?format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "1.0"
    assert "project" in data
    assert "documents" in data
    assert "chapters" in data
    assert len(data["chapters"]) == 2


def test_json_roundtrip(api_client):
    pid = _create_project(api_client, "往返测试")

    preview = api_client.post(
        "/api/import/preview",
        files={"file": ("chapters.txt", SAMPLE_TXT.encode("utf-8"), "text/plain")},
    )
    chapters = preview.json()["chapters"]
    api_client.post(
        f"/api/projects/{pid}/import/commit",
        data={"chapters": json.dumps(chapters)},
    )

    export_resp = api_client.get(f"/api/projects/{pid}/export?format=json")
    bundle = export_resp.json()

    resp = api_client.post(
        "/api/import/project-bundle",
        files={"file": ("project.json", json.dumps(bundle, ensure_ascii=False).encode("utf-8"), "application/json")},
    )
    assert resp.status_code == 201
    imported = resp.json()
    assert imported["chapters_imported"] == 2

    imported_project = api_client.get(f"/api/projects/{imported['project_id']}")
    assert imported_project.status_code == 200
    assert imported_project.json()["name"] == "往返测试"


def test_import_invalid_json(api_client):
    resp = api_client.post(
        "/api/import/project-bundle",
        files={"file": ("bad.json", b"not json", "application/json")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_JSON"


def test_file_too_large(api_client):
    big_content = "x" * (21 * 1024 * 1024)
    resp = api_client.post(
        "/api/import/preview",
        files={"file": ("big.txt", big_content.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"
