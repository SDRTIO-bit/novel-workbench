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
        assert len(_mcp_result(resp)["tools"]) == 33


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

        providers = self._call(api_client, headers, sid, "list_providers", {}, 43)
        provider_list = providers["structuredContent"].get("result", providers["structuredContent"])
        if isinstance(provider_list, dict):
            provider_list = [provider_list]
        mock_p = [p for p in provider_list if p.get("provider_type") == "mock"]
        assert mock_p, "No mock provider found — default workflow may use real LLM"
        mock_provider_id = mock_p[0]["id"]

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
                            {"run_id": run_id, "stage": stage, "provider_id": mock_provider_id}, 50 + i)
            assert sr["isError"] is False, f"Stage {stage} failed: {sr}"
            assert sr["structuredContent"]["error_code"] is None, (
                f"Stage {stage}: {sr['structuredContent'].get('error_message')}"
            )

            cand_id = sr["structuredContent"]["candidate_id"]
            self._call(api_client, headers, sid, "select_candidate", {
                "run_id": run_id, "stage": stage, "candidate_id": cand_id,
            }, 60 + i)

            if stage == "critic":
                gs = self._call(api_client, headers, sid, "get_stage_status",
                                {"run_id": run_id, "stage": "critic"}, 70)
                assert gs["isError"] is False
                critic_cand = gs["structuredContent"]["candidates"][0]
                issues = critic_cand.get("parsed_output_json")
                if issues and isinstance(issues, str):
                    import json as _j
                    parsed = _j.loads(issues)
                    issue_ids = [i["issue_id"] for i in parsed.get("issues", [])][:2]
                else:
                    issue_ids = ["I01", "I02"]
                iss_result = self._call(api_client, headers, sid, "select_critic_issues", {
                    "run_id": run_id,
                    "issue_ids": issue_ids,
                }, 71)
                assert iss_result["isError"] is False, f"select_critic_issues failed: {iss_result}"

        final = self._call(api_client, headers, sid, "get_run",
                           {"run_id": run_id}, 80)
        assert final["isError"] is False
        assert final["structuredContent"]["status"] == "completed"
        for step in final["structuredContent"]["steps"]:
            assert step["status"] == "completed", f"Step {step['stage']} status is {step['status']}"

        writer_cand = self._get_stage_candidate(api_client, headers, sid, run_id, "writer")
        critic_cand = self._get_stage_candidate(api_client, headers, sid, run_id, "critic")
        reviser_cand = self._get_stage_candidate(api_client, headers, sid, run_id, "reviser")
        judge_cand = self._get_stage_candidate(api_client, headers, sid, run_id, "judge")

        writer_text = writer_cand["text_output"] or ""
        reviser_text = reviser_cand["text_output"] or ""

        assert writer_text and len(writer_text) > 50, "Writer should produce prose text"
        assert not writer_text.lstrip().startswith("{"), "Writer output must be prose, not JSON"

        if critic_cand:
            critic_user_prompt = critic_cand.get("rendered_user_prompt", "")
            assert writer_text[:80] in critic_user_prompt or any(
                w in critic_user_prompt for w in writer_text.split()[:10]
            ), "Critic must see Writer's draft text in user prompt"

        if reviser_cand:
            reviser_user_prompt = reviser_cand.get("rendered_user_prompt", "")
            assert writer_text[:80] in reviser_user_prompt or any(
                w in reviser_user_prompt for w in writer_text.split()[:10]
            ), "Reviser must see Writer's draft text in user prompt"

        if judge_cand:
            judge_user_prompt = judge_cand.get("rendered_user_prompt", "")
            assert writer_text[:80] in judge_user_prompt or any(
                w in judge_user_prompt for w in writer_text.split()[:10]
            ), "Judge must see Writer's draft text in user prompt"

        acc = self._call(api_client, headers, sid, "accept_final_text", {
            "run_id": run_id,
            "accept_type": "original",
        }, 90)
        assert acc["isError"] is False

        ch_data = self._call(api_client, headers, sid, "get_chapter",
                             {"chapter_id": cid}, 91)
        chapter_text = ch_data["structuredContent"].get("current_text", "")
        assert chapter_text == writer_text, "Chapter text must equal the accepted Writer text"

        second_acc = self._call(api_client, headers, sid, "accept_final_text", {
            "run_id": run_id,
            "accept_type": "revision",
        }, 92)
        assert second_acc["isError"] is True

    def _get_stage_candidate(self, api_client, headers, sid, run_id, stage):
        gs = self._call(api_client, headers, sid, "get_stage_status",
                        {"run_id": run_id, "stage": stage}, 100)
        candidates = gs["structuredContent"].get("candidates", [])
        return candidates[0] if candidates else {}


class TestMCPGenerationObservability:
    def test_generation_tools_expose_resolved_prompt_contract_metadata(self, api_client):
        tools = TestMCPTools()
        headers, sid = tools._do_handshake(api_client)

        project = tools._call(api_client, headers, sid, "create_project", {
            "name": "可观测性测试项目",
        }, 200)
        project_id = project["structuredContent"]["id"]
        chapter = tools._call(api_client, headers, sid, "create_chapter", {
            "project_id": project_id,
            "title": "第一章",
        }, 201)

        workflows = tools._call(api_client, headers, sid, "list_workflows", {}, 202)
        workflow = next(w for w in workflows["structuredContent"]["result"] if w["is_default"])
        planner_step = next(step for step in workflow["steps"] if step["stage"] == "planner")
        assert planner_step["prompt_version_id"]

        profiles = tools._call(api_client, headers, sid, "list_prompt_profiles", {
            "stage": "planner",
        }, 203)
        builtin = next(p for p in profiles["structuredContent"]["result"] if p["is_builtin"])
        planner_v2 = builtin["versions"][-1]
        assert planner_v2["output_schema_name"] == "planner_v2"

        run = tools._call(api_client, headers, sid, "create_run", {
            "project_id": project_id,
            "chapter_id": chapter["structuredContent"]["id"],
            "workflow_profile_id": workflow["id"],
            "scene_instruction": "主角发现了一条新线索。",
        }, 204)
        run_id = run["structuredContent"]["id"]

        run_detail = tools._call(api_client, headers, sid, "get_run", {"run_id": run_id}, 205)
        assert run_detail["structuredContent"]["workflow_profile_id"] == workflow["id"]

        preview = tools._call(api_client, headers, sid, "preview_context", {
            "run_id": run_id,
            "stage": "planner",
            "prompt_version_id": planner_v2["id"],
        }, 206)
        assert preview["structuredContent"]["prompt_meta"] == {
            "prompt_version_id": planner_v2["id"],
            "output_schema_name": "planner_v2",
        }

        provider_list = tools._call(api_client, headers, sid, "list_providers", {}, 207)
        mock_provider = next(
            item for item in provider_list["structuredContent"]["result"]
            if item["provider_type"] == "mock"
        )
        executed = tools._call(api_client, headers, sid, "execute_stage", {
            "run_id": run_id,
            "stage": "planner",
            "provider_id": mock_provider["id"],
            "prompt_version_id": planner_v2["id"],
        }, 208)["structuredContent"]
        assert executed["prompt_version_id"] == planner_v2["id"]
        assert executed["output_schema_name"] == "planner_v2"
        assert executed["expected_contract_version"] == 2
        assert isinstance(executed["parsed_output_json"], str)

        status = tools._call(api_client, headers, sid, "get_stage_status", {
            "run_id": run_id,
            "stage": "planner",
        }, 209)["structuredContent"]
        candidate = status["candidates"][0]
        assert candidate["prompt_version_id"] == planner_v2["id"]
        assert candidate["raw_response"]


def _mcp_result(resp):
    text = resp.text
    data_line = [l for l in text.strip().split("\n") if l.startswith("data: ")][0]
    return json.loads(data_line[6:])["result"]
