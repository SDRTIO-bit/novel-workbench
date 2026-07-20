import os
import asyncio
import pytest
import shutil

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_prompt_data")


@pytest.fixture(scope="module")
def api_client():
    os.environ["NW_DATA_DIR"] = TEST_DATA_DIR
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)

    import app.models.project  # noqa: F401
    import app.models.chapter  # noqa: F401
    import app.models.prompt  # noqa: F401

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.db import Base

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())

    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.services.prompt_service import PromptService

    async def _seed():
        async with sm() as session:
            svc = PromptService(session)
            await svc.init_builtins()
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


def _uniq_name(base: str) -> str:
    global _counter
    _counter += 1
    return f"{base}_{_counter}"


class TestPromptList:
    def test_builtin_planner_v5_documents_tempo_machine_enums(self):
        from app.prompts.defaults import BUILTIN_PROMPTS

        planner = next(item for item in BUILTIN_PROMPTS if item["stage"] == "planner")
        text = planner["system_template"]

        for value in (
            "physical_problem", "social_friction", "resource_constraint",
            "unfinished_commitment", "information_gap", "none",
            "physical_change", "social_commitment", "relationship_shift",
            "information_conflict", "unresolved_problem",
        ):
            assert value in text
        for phrase in ("只能选择一个值", "不得组合多个分类", "其他压力写入 description", "不得填写 situational"):
            assert phrase in text

    def test_builtin_planner_v6_documents_top_level_json_shapes(self):
        from app.prompts.defaults import BUILTIN_PROMPTS

        planner = next(item for item in BUILTIN_PROMPTS if item["stage"] == "planner")
        text = planner["system_template"]

        for phrase in (
            "characters 只能是 JSON 数组",
            "pressure 只能是字符串",
            "end_condition 只能是字符串",
            "不得以角色名作为对象 key",
            '"planner_contract_version": 2',
            '"characters": [',
            '"pressure": "字符串"',
            '"end_condition": "字符串"',
            "上例只规定 JSON 结构和字段类型",
        ):
            assert phrase in text

    def test_builtin_writer_uses_scene_responsiveness_not_four_beat_structure(self):
        from app.prompts.defaults import BUILTIN_PROMPTS

        writer = next(item for item in BUILTIN_PROMPTS if item["stage"] == "writer")
        text = writer["system_template"] + writer["user_template"]
        assert "场景响应规则" in text
        assert "开场钩子：" not in text
        assert "爽点释放：" not in text
        assert "结尾钩子：制造新的" not in text
        assert "{{tempo_guardrails}}" in text
        assert "final_line_must_include" in text

    def test_writer_v6_v7_v8_tiers_coexist(self):
        from app.prompts.defaults import BUILTIN_PROMPTS

        writers = [item for item in BUILTIN_PROMPTS if item["stage"] == "writer"]
        by_name = {item["name"]: item for item in writers}

        assert "默认场景写作" in by_name
        assert "Sacrificial Preflight v7" in by_name
        assert "Sacrificial Preflight Fusion v8" in by_name

        v6 = by_name["默认场景写作"]
        v7 = by_name["Sacrificial Preflight v7"]
        v8 = by_name["Sacrificial Preflight Fusion v8"]

        assert v6["output_mode"] == "plain_text"
        assert v6["output_schema_name"] is None
        assert "场景响应规则" in v6["system_template"]
        assert "<draft_notes>" not in v6["system_template"]
        assert "请写出场景正文。" in v6["user_template"]

        assert v7["output_mode"] == "xml_story"
        assert v7["output_schema_name"] is None
        assert "<draft_notes>" in v7["system_template"]
        assert "<story>" in v7["system_template"]
        assert "正文目标长度：" in v7["system_template"]
        assert "请按上述格式输出 <draft_notes> 和 <story> 两个区块。" in v7["user_template"]
        assert "人物套路淘汰" not in v7["system_template"]
        assert "行动与篇幅骨架" not in v7["system_template"]

        assert v8["stage"] == "writer"
        assert v8["output_mode"] == "xml_story"
        assert v8["output_schema_name"] is None

        sys8 = v8["system_template"]
        for phrase in (
            "<draft_notes>",
            "<story>",
            "{{target_length}}",
            "正文最低字数",
            "2000字只是底线",
            "2400—3200",
            "人物套路淘汰",
            "剧情套路淘汰",
            "句式套路淘汰",
            "信息边界",
            "现状重构",
            "行动与篇幅骨架",
            "不得提前让stop_state成立",
            "stop_state成立后结束",
        ):
            assert phrase in sys8, f"missing in v8 system_template: {phrase}"

        user8 = v8["user_template"]
        for phrase in (
            "<draft_notes>",
            "<story>",
            "{{target_length}}是story的最低正文长度，不是上限",
        ):
            assert phrase in user8, f"missing in v8 user_template: {phrase}"

        # v6/v7 must not be overwritten by v8 content
        assert v6["system_template"] != v8["system_template"]
        assert v7["system_template"] != v8["system_template"]
        assert "融合TGbreak" in v8["description"] or "TGbreak" in v8["description"]

    def test_writer_v8_seeded_as_independent_builtin_profile(self, api_client):
        resp = api_client.get("/api/prompts?stage=writer")
        assert resp.status_code == 200
        data = resp.json()
        builtins = [p for p in data if p["is_builtin"]]
        names = {p["name"] for p in builtins}

        assert "默认场景写作" in names
        assert "Sacrificial Preflight v7" in names
        assert "Sacrificial Preflight Fusion v8" in names

        v8 = next(p for p in builtins if p["name"] == "Sacrificial Preflight Fusion v8")
        versions = api_client.get(f"/api/prompts/{v8['id']}/versions").json()
        assert len(versions) >= 1
        latest = versions[0]
        assert latest["output_mode"] == "xml_story"
        assert latest.get("output_schema_name") in (None, "")
        assert "<draft_notes>" in latest["system_template"]
        assert "<story>" in latest["system_template"]
        assert "正文最低字数" in latest["system_template"]
        assert "{{target_length}}是story的最低正文长度，不是上限" in latest["user_template"]

    def test_editor_prompts_preserve_visible_hook_when_cutting_a_summary(self):
        from app.prompts.defaults import BUILTIN_PROMPTS

        critic = next(item for item in BUILTIN_PROMPTS if item["stage"] == "critic")
        reviser = next(item for item in BUILTIN_PROMPTS if item["stage"] == "reviser")
        judge = next(item for item in BUILTIN_PROMPTS if item["stage"] == "judge")

        assert "四态判断" in critic["system_template"]
        assert "具体可见事实" in reviser["system_template"]
        assert "角色反应" in judge["system_template"]
        assert "final_line_must_include" in reviser["system_template"]

    def test_list_all_prompts(self, api_client):
        resp = api_client.get("/api/prompts")
        assert resp.status_code == 200
        data = resp.json()
        stages = {p["stage"] for p in data}
        expected = {"planner", "writer", "critic", "reviser", "judge"}
        assert stages == expected

    def test_list_prompts_by_stage(self, api_client):
        resp = api_client.get("/api/prompts?stage=critic")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert all(p["stage"] == "critic" for p in data)

    def test_all_builtins_are_present(self, api_client):
        resp = api_client.get("/api/prompts")
        data = resp.json()
        builtins = [p for p in data if p["is_builtin"]]
        assert len(builtins) >= 5
        stages = {p["stage"] for p in builtins}
        assert stages == {"planner", "writer", "critic", "reviser", "judge"}


class TestPromptVersions:
    def test_get_versions(self, api_client):
        resp = api_client.get("/api/prompts")
        data = resp.json()
        profile_id = data[0]["id"]
        resp2 = api_client.get(f"/api/prompts/{profile_id}/versions")
        assert resp2.status_code == 200
        versions = resp2.json()
        assert len(versions) >= 1
        v = versions[0]
        assert "version_number" in v
        assert "system_template" in v
        assert "user_template" in v

    def test_add_version(self, api_client):
        resp = api_client.get("/api/prompts")
        data = resp.json()
        profile_id = data[0]["id"]
        resp2 = api_client.post(
            f"/api/prompts/{profile_id}/versions",
            json={"system_template": "新 system", "user_template": "新 user", "output_mode": "structured"},
        )
        assert resp2.status_code == 201
        v = resp2.json()
        assert v["system_template"] == "新 system"
        assert v["version_number"] > 1

    def test_cannot_add_version_nonexistent(self, api_client):
        resp = api_client.post(
            "/api/prompts/not-an-id/versions",
            json={"system_template": "x", "user_template": "y"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PROMPT_PROFILE_NOT_FOUND"


class TestPromptCreate:
    def test_create_custom_prompt(self, api_client):
        name = _uniq_name("自定义规划")
        resp = api_client.post(
            "/api/prompts",
            json={
                "stage": "planner",
                "name": name,
                "description": "测试用",
                "system_template": "自定义 system",
                "user_template": "自定义 user {{project_name}}",
                "output_mode": "structured",
                "output_schema_name": "planner",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == name
        assert data["is_builtin"] is False

    def test_create_invalid_stage(self, api_client):
        resp = api_client.post(
            "/api/prompts",
            json={"stage": "invalid", "name": _uniq_name("测试"), "system_template": "x", "user_template": "y"},
        )
        assert resp.status_code == 400

    def test_create_invalid_output_mode(self, api_client):
        resp = api_client.post(
            "/api/prompts",
            json={
                "stage": "writer", "name": _uniq_name("测试模式"), "system_template": "x", "user_template": "y",
                "output_mode": "invalid",
            },
        )
        assert resp.status_code == 400


class TestPromptDuplicate:
    def test_duplicate_prompt(self, api_client):
        resp = api_client.get("/api/prompts")
        data = resp.json()
        builtins = [p for p in data if p["is_builtin"]]
        assert builtins, "no builtin prompts found"
        profile_id = builtins[0]["id"]
        resp2 = api_client.post(f"/api/prompts/{profile_id}/duplicate")
        assert resp2.status_code == 201
        dup = resp2.json()
        assert dup["name"].endswith("副本")
        assert dup["id"] != profile_id


class TestRestoreDefault:
    def test_restore_default_builtin(self, api_client):
        resp = api_client.get("/api/prompts")
        data = resp.json()
        builtin = next(p for p in data if p["is_builtin"])
        resp2 = api_client.post(f"/api/prompts/{builtin['id']}/restore-default")
        assert resp2.status_code == 200

    def test_cannot_restore_custom(self, api_client):
        create_resp = api_client.post(
            "/api/prompts",
            json={
                "stage": "writer", "name": _uniq_name("不能恢复"), "system_template": "x",
                "user_template": "y", "output_mode": "plain_text",
            },
        )
        pid = create_resp.json()["id"]
        resp = api_client.post(f"/api/prompts/{pid}/restore-default")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "NOT_BUILTIN"


class TestRenderPreview:
    def test_render_preview_success(self, api_client):
        resp = api_client.post(
            "/api/prompts/render-preview",
            json={
                "system_template": "你是 {{project_genre}} 小说的助手",
                "user_template": "项目：{{project_name}}，类型：{{project_genre}}",
                "variables": {"project_name": "测试小说", "project_genre": "科幻"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["system_prompt"] == "你是 科幻 小说的助手"
        assert data["user_prompt"] == "项目：测试小说，类型：科幻"

    def test_render_preview_undefined_variable(self, api_client):
        resp = api_client.post(
            "/api/prompts/render-preview",
            json={
                "system_template": "{{unknown_variable}}",
                "user_template": "ok",
                "variables": {},
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "RENDER_ERROR"


class TestExportImport:
    def test_export_prompts(self, api_client):
        resp = api_client.get("/api/prompts/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0"
        assert isinstance(data["profiles"], list)

    def test_import_profiles(self, api_client):
        name = _uniq_name("导入的规划")
        import_data = {
            "version": "1.0",
            "profiles": [
                {
                    "stage": "planner",
                    "name": name,
                    "system_template": "导入 system",
                    "user_template": "导入 user",
                    "output_mode": "structured",
                }
            ],
        }
        resp = api_client.post("/api/prompts/import", json=import_data)
        assert resp.status_code == 201
        assert resp.json()["imported"] == 1


class TestViewIndividualPrompt:
    def test_view_prompt_detail_with_latest_version(self, api_client):
        name = _uniq_name("详细查看测试")
        create_resp = api_client.post(
            "/api/prompts",
            json={
                "stage": "judge",
                "name": name,
                "system_template": "sys",
                "user_template": "usr {{project_name}}",
                "output_mode": "structured",
                "output_schema_name": "judge",
            },
        )
        pid = create_resp.json()["id"]

        api_client.post(
            f"/api/prompts/{pid}/versions",
            json={"system_template": "v2 sys", "user_template": "v2 usr {{project_genre}}"},
        )

        resp = api_client.get("/api/prompts")
        profiles = resp.json()
        target = next(p for p in profiles if p["id"] == pid)
        assert target["name"] == name
