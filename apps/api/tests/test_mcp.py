import asyncio
import json
import os
import shutil
import secrets

import pytest
from starlette.testclient import TestClient

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_mcp_data")
TEST_TOKEN = secrets.token_urlsafe(32)


@pytest.fixture(scope="module")
def app_and_sm():
    os.environ["NW_DATA_DIR"] = TEST_DATA_DIR
    os.environ["NW_MCP_ACCESS_TOKEN"] = TEST_TOKEN

    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)

    import app.models.project  # noqa: F401
    import app.models.chapter  # noqa: F401
    import app.models.prompt  # noqa: F401
    import app.models.provider  # noqa: F401
    import app.models.workflow  # noqa: F401
    import app.models.generation  # noqa: F401

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
            await PromptService(session).init_builtins()
            from app.services.provider_service import ProviderService
            await ProviderService(session).init_builtins()
            from app.services.workflow_service import WorkflowService
            await WorkflowService(session).init_builtin_default()
            await session.commit()

    asyncio.run(_seed())

    from app.main import app
    from app.db import get_db

    async def _override_get_db():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    from app.config import settings
    settings.mcp_access_token = TEST_TOKEN

    return app, sm


@pytest.fixture(scope="module")
def api_client(app_and_sm):
    app, _ = app_and_sm
    with TestClient(app) as client:
        yield client


def _auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


class TestMCPAuth:
    def test_no_token_returns_401(self, api_client):
        resp = api_client.post("/mcp/", content="{}")
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, api_client):
        resp = api_client.post(
            "/mcp/",
            content="{}",
            headers={"Authorization": "Bearer wrong-token-value"},
        )
        assert resp.status_code == 401

    def test_correct_token_passes_auth(self, api_client):
        resp = api_client.post(
            "/mcp/",
            content="{}",
            headers=_auth_headers(),
        )
        assert resp.status_code != 401


class TestMCPHandshake:
    def test_initialize(self, api_client):
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }
        resp = api_client.post(
            "/mcp/",
            json=body,
            headers={**_auth_headers(), "Accept": "application/json, text/event-stream"},
        )
        assert resp.status_code == 200
        assert "novel-workbench" in resp.text
        assert '"result"' in resp.text

    def test_initialize_then_tools_list(self, api_client):
        headers = {**_auth_headers(), "Accept": "application/json, text/event-stream"}
        resp = api_client.post("/mcp/", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1.0"}},
        }, headers=headers)
        session_id = resp.headers.get("mcp-session-id")
        assert session_id is not None

        resp = api_client.post("/mcp/",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={**headers, "mcp-session-id": session_id})
        assert resp.status_code == 202

        resp = api_client.post("/mcp/",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={**headers, "mcp-session-id": session_id})
        assert resp.status_code == 200
        tool_names = [t["name"] for t in _mcp_result(resp)["tools"]]
        assert "restore_project" in tool_names
        assert "restore_chapter" in tool_names
        assert "reorder_chapters" in tool_names
        assert "restore_chapter_version" in tool_names
        assert "execute_stage" in tool_names

    def test_tools_list_count(self, api_client):
        headers = {**_auth_headers(), "Accept": "application/json, text/event-stream"}
        resp = api_client.post("/mcp/", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1.0"}},
        }, headers=headers)
        sid = resp.headers.get("mcp-session-id")
        api_client.post("/mcp/",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={**headers, "mcp-session-id": sid})
        resp = api_client.post("/mcp/",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={**headers, "mcp-session-id": sid})
        assert len(_mcp_result(resp)["tools"]) == 31


class TestMCPTools:
    def _do_handshake(self, api_client):
        headers = {**_auth_headers(), "Accept": "application/json, text/event-stream"}
        resp = api_client.post("/mcp/", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1.0"}},
        }, headers=headers)
        sid = resp.headers.get("mcp-session-id")
        api_client.post("/mcp/",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={**headers, "mcp-session-id": sid})
        return headers, sid

    def _call(self, api_client, headers, sid, name, args, req_id):
        resp = api_client.post("/mcp/", json={
            "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }, headers={**headers, "mcp-session-id": sid})
        return _mcp_result(resp)

    def test_create_and_list_projects(self, api_client):
        headers, sid = self._do_handshake(api_client)

        r = self._call(api_client, headers, sid, "create_project",
                       {"name": "MCP测试项目", "genre": "科幻"}, 10)
        pid = r["structuredContent"]["id"]
        assert r["isError"] is False

        r = self._call(api_client, headers, sid, "list_projects", {}, 11)
        assert r["isError"] is False
        assert len(r["structuredContent"]["result"]) >= 1

        r = self._call(api_client, headers, sid, "get_project",
                       {"project_id": pid}, 12)
        assert r["structuredContent"]["name"] == "MCP测试项目"

    def test_restore_project(self, api_client):
        headers, sid = self._do_handshake(api_client)

        r = self._call(api_client, headers, sid, "create_project",
                       {"name": "恢复测试"}, 14)
        pid = r["structuredContent"]["id"]

        r = self._call(api_client, headers, sid, "delete_project",
                       {"project_id": pid}, 15)
        assert r["structuredContent"]["status"] == "deleted"

        r = self._call(api_client, headers, sid, "restore_project",
                       {"project_id": pid}, 16)
        assert r["isError"] is False
        assert r["structuredContent"]["status"] == "restored"

    def test_chapter_crud_and_restore(self, api_client):
        headers, sid = self._do_handshake(api_client)

        proj = self._call(api_client, headers, sid, "create_project",
                          {"name": "章节CRUD测试"}, 20)
        pid = proj["structuredContent"]["id"]

        ch = self._call(api_client, headers, sid, "create_chapter",
                        {"project_id": pid, "title": "第1章"}, 21)
        cid = ch["structuredContent"]["id"]

        lst = self._call(api_client, headers, sid, "list_chapters",
                         {"project_id": pid}, 22)
        assert len(lst["structuredContent"]["result"]) == 1

        d = self._call(api_client, headers, sid, "delete_chapter",
                       {"chapter_id": cid}, 23)
        assert d["structuredContent"]["status"] == "deleted"

        r = self._call(api_client, headers, sid, "restore_chapter",
                       {"chapter_id": cid}, 24)
        assert r["structuredContent"]["status"] == "restored"

    def test_reorder_chapters(self, api_client):
        headers, sid = self._do_handshake(api_client)

        proj = self._call(api_client, headers, sid, "create_project",
                          {"name": "排序测试"}, 30)
        pid = proj["structuredContent"]["id"]

        c1 = self._call(api_client, headers, sid, "create_chapter",
                        {"project_id": pid, "title": "A章"}, 31)
        c2 = self._call(api_client, headers, sid, "create_chapter",
                        {"project_id": pid, "title": "B章"}, 32)

        cid1 = c1["structuredContent"]["id"]
        cid2 = c2["structuredContent"]["id"]

        reorder = self._call(api_client, headers, sid, "reorder_chapters", {
            "reorder_items": [{"id": cid2, "sort_order": 1}, {"id": cid1, "sort_order": 2}],
        }, 33)
        assert reorder["isError"] is False
        assert reorder["structuredContent"]["reordered"] == 2

    def test_full_five_stage_via_mcp(self, api_client):
        headers, sid = self._do_handshake(api_client)

        proj = self._call(api_client, headers, sid, "create_project",
                          {"name": "E2E MCP测试"}, 40)
        pid = proj["structuredContent"]["id"]

        ch = self._call(api_client, headers, sid, "create_chapter",
                        {"project_id": pid, "title": "第一章"}, 41)
        cid = ch["structuredContent"]["id"]

        run = self._call(api_client, headers, sid, "create_run", {
            "project_id": pid,
            "chapter_id": cid,
            "scene_instruction": "主角在废弃工厂发现隐藏线索",
        }, 42)
        assert run["isError"] is False
        run_id = run["structuredContent"]["id"]
        assert run["structuredContent"]["status"] == "pending"

        for i, stage in enumerate(["planner", "writer", "critic", "reviser", "judge"]):
            sr = self._call(api_client, headers, sid, "execute_stage",
                            {"run_id": run_id, "stage": stage}, 50 + i)
            assert sr["isError"] is False, f"Stage {stage} failed: {sr}"
            assert sr["structuredContent"]["error_code"] is None, (
                f"Stage {stage}: {sr['structuredContent'].get('error_message')}"
            )

        final = self._call(api_client, headers, sid, "get_run",
                           {"run_id": run_id}, 60)
        assert final["isError"] is False
        assert final["structuredContent"]["status"] == "completed"
        for step in final["structuredContent"]["steps"]:
            assert step["status"] == "completed"


def _mcp_result(resp):
    text = resp.text
    data_line = [l for l in text.strip().split("\n") if l.startswith("data: ")][0]
    return json.loads(data_line[6:])["result"]
