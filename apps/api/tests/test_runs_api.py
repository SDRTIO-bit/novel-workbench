import asyncio
import json
import os
import shutil

import pytest
from httpx import ASGITransport, AsyncClient

TEST_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_runs_api_data")


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
    import app.models.detector_feedback

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
    return sm


@pytest.fixture(scope="module")
def api_client(_setup):
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_project(client):
    resp = await client.post("/api/projects", json={"name": "E2E测试小说", "genre": "奇幻"})
    assert resp.status_code == 201
    pid = resp.json()["id"]
    await client.put(f"/api/projects/{pid}/documents/characters",
                     json={"content": "主角：艾琳，年轻的调查员"})
    await client.put(f"/api/projects/{pid}/documents/world",
                     json={"content": "近未来都市，腐败盛行"})
    return pid


async def _create_chapter(client, project_id):
    resp = await client.post(
        f"/api/projects/{project_id}/chapters",
        json={"title": "第一章", "text": "夜幕降临。"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _run_to_selected_critic(client):
    project_id = await _create_project(client)
    chapter_id = await _create_chapter(client, project_id)
    response = await client.post("/api/runs", json={
        "project_id": project_id,
        "chapter_id": chapter_id,
        "scene_instruction": "测试局部修订操作",
    })
    assert response.status_code == 201
    run_id = response.json()["id"]

    for stage in ("planner", "writer", "critic"):
        candidate = await client.post(f"/api/runs/{run_id}/steps/{stage}/execute", json={})
        assert candidate.status_code == 200
        selection = await client.post(
            f"/api/runs/{run_id}/steps/{stage}/select/{candidate.json()['id']}"
        )
        assert selection.status_code == 200

    return run_id


class TestFullWorkflow:
    @pytest.mark.asyncio
    async def test_full_five_stage_workflow(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "scene_instruction": "艾琳发现了一个重要线索",
        })
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        # Stage 1: Planner
        resp = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        assert resp.status_code == 200
        planner_cand = resp.json()
        assert planner_cand["error_code"] is None
        planner_data = json.loads(planner_cand["parsed_output_json"])
        assert "scene_goal" in planner_data

        resp = await api_client.post(
            f"/api/runs/{run_id}/steps/planner/select/{planner_cand['id']}"
        )
        assert resp.status_code == 200

        # Stage 2: Writer
        resp = await api_client.post(f"/api/runs/{run_id}/steps/writer/execute", json={})
        assert resp.status_code == 200
        writer_cand = resp.json()
        assert writer_cand["error_code"] is None
        assert len(writer_cand["text_output"]) > 0

        resp = await api_client.post(
            f"/api/runs/{run_id}/steps/writer/select/{writer_cand['id']}"
        )
        assert resp.status_code == 200

        # Stage 3: Critic
        resp = await api_client.post(f"/api/runs/{run_id}/steps/critic/execute", json={})
        assert resp.status_code == 200
        critic_cand = resp.json()
        assert critic_cand["error_code"] is None
        critic_data = json.loads(critic_cand["parsed_output_json"])
        assert "issues" in critic_data
        assert len(critic_data["issues"]) >= 1

        resp = await api_client.post(
            f"/api/runs/{run_id}/steps/critic/select/{critic_cand['id']}"
        )
        assert resp.status_code == 200

        issue_id = critic_data["issues"][0]["issue_id"]
        resp = await api_client.post(
            f"/api/runs/{run_id}/critic/select-issues",
            json={"issue_ids": [issue_id]},
        )
        assert resp.status_code == 200

        # Stage 4: Reviser
        resp = await api_client.post(f"/api/runs/{run_id}/steps/reviser/execute", json={})
        assert resp.status_code == 200
        reviser_cand = resp.json()
        assert reviser_cand["error_code"] is None

        resp = await api_client.post(
            f"/api/runs/{run_id}/steps/reviser/select/{reviser_cand['id']}"
        )
        assert resp.status_code == 200

        # Stage 5: Judge
        resp = await api_client.post(f"/api/runs/{run_id}/steps/judge/execute", json={})
        assert resp.status_code == 200
        judge_cand = resp.json()
        assert judge_cand["error_code"] is None

        resp = await api_client.post(
            f"/api/runs/{run_id}/steps/judge/select/{judge_cand['id']}"
        )
        assert resp.status_code == 200

        # Accept final text — use revision type (reviser has selected candidate)
        resp = await api_client.post(f"/api/runs/{run_id}/accept", json={
            "accept_type": "revision",
        })
        assert resp.status_code == 200
        accept_data = resp.json()
        assert accept_data["status"] == "ok"
        assert accept_data["version_number"] >= 1

        # Check chapter version created
        resp = await api_client.get(f"/api/chapters/{chapter_id}/versions")
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) >= 1
        assert versions[-1]["source"] == "revision"

    @pytest.mark.asyncio
    async def test_stage_preview(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "scene_instruction": "预览测试",
        })
        run_id = resp.json()["id"]

        resp = await api_client.post(
            f"/api/runs/{run_id}/steps/planner/preview", json={}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rendered_system_prompt"]
        assert data["rendered_user_prompt"]
        assert data["input_snapshot_hash"]

    @pytest.mark.asyncio
    async def test_select_issues_requires_critic(self, api_client):
        project_id = await _create_project(api_client)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "scene_instruction": "测试",
        })
        run_id = resp.json()["id"]

        resp = await api_client.post(
            f"/api/runs/{run_id}/critic/select-issues",
            json={"issue_ids": ["I01"]},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_select_issues_uses_critic_recommendation_by_default(self, api_client):
        run_id = await _run_to_selected_critic(api_client)

        response = await api_client.post(
            f"/api/runs/{run_id}/critic/select-issues",
            json={"issue_ids": ["I01"]},
        )

        assert response.status_code == 200
        run = (await api_client.get(f"/api/runs/{run_id}")).json()
        critic = next(step for step in run["steps"] if step["stage"] == "critic")
        assert json.loads(critic["selected_issue_ids_json"]) == ["I01"]
        assert json.loads(critic["selected_issue_operations_json"]) == {"I01": "tighten"}

    @pytest.mark.asyncio
    async def test_select_issues_persists_author_operation_override(self, api_client):
        run_id = await _run_to_selected_critic(api_client)

        response = await api_client.post(
            f"/api/runs/{run_id}/critic/select-issues",
            json={
                "issue_ids": ["I01"],
                "operation_by_issue": {"I01": "voice_align"},
            },
        )

        assert response.status_code == 200
        run = (await api_client.get(f"/api/runs/{run_id}")).json()
        critic = next(step for step in run["steps"] if step["stage"] == "critic")
        assert json.loads(critic["selected_issue_operations_json"]) == {"I01": "voice_align"}

    @pytest.mark.asyncio
    async def test_select_issues_rejects_invalid_or_unselected_operation_mapping(self, api_client):
        run_id = await _run_to_selected_critic(api_client)

        invalid = await api_client.post(
            f"/api/runs/{run_id}/critic/select-issues",
            json={
                "issue_ids": ["I01"],
                "operation_by_issue": {"I01": "rewrite_everything"},
            },
        )
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "INVALID_REVISION_OPERATION"

        unselected = await api_client.post(
            f"/api/runs/{run_id}/critic/select-issues",
            json={
                "issue_ids": ["I01"],
                "operation_by_issue": {"I02": "tighten"},
            },
        )
        assert unselected.status_code == 400
        assert unselected.json()["error"]["code"] == "ISSUE_OPERATION_NOT_SELECTED"

    @pytest.mark.asyncio
    async def test_reviser_context_contains_selected_issue_and_author_operation(self, api_client):
        run_id = await _run_to_selected_critic(api_client)
        selected = await api_client.post(
            f"/api/runs/{run_id}/critic/select-issues",
            json={
                "issue_ids": ["I01"],
                "operation_by_issue": {"I01": "voice_align"},
            },
        )
        assert selected.status_code == 200

        preview = await api_client.post(f"/api/runs/{run_id}/steps/reviser/preview", json={})
        assert preview.status_code == 200
        prompt = preview.json()["rendered_user_prompt"]
        selected_section = prompt.split("## 本次需修改的问题\n", maxsplit=1)[1]
        assert '"issue_id": "I01"' in selected_section
        assert '"selected_operation": "voice_align"' in selected_section
        assert '"issue_id": "I02"' not in selected_section

    @pytest.mark.asyncio
    async def test_accept_creates_chapter_version(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
        })
        run_id = resp.json()["id"]

        resp = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        planner_cand = resp.json()
        await api_client.post(f"/api/runs/{run_id}/steps/planner/select/{planner_cand['id']}")

        resp = await api_client.post(f"/api/runs/{run_id}/steps/writer/execute", json={})
        writer_cand = resp.json()
        await api_client.post(f"/api/runs/{run_id}/steps/writer/select/{writer_cand['id']}")

        writer_text = writer_cand["text_output"]

        resp = await api_client.post(f"/api/runs/{run_id}/accept", json={
            "accept_type": "original",
        })
        assert resp.status_code == 200
        assert resp.json()["source"] == "original"

        resp = await api_client.get(f"/api/chapters/{chapter_id}/versions")
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) >= 1
        assert versions[-1]["text"] == writer_text
        assert versions[-1]["source"] == "original"

        resp = await api_client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["accepted_version_id"] == versions[-1]["id"]

    @pytest.mark.asyncio
    async def test_accept_idempotent(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
        })
        run_id = resp.json()["id"]

        resp = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        await api_client.post(f"/api/runs/{run_id}/steps/planner/select/{resp.json()['id']}")

        resp = await api_client.post(f"/api/runs/{run_id}/steps/writer/execute", json={})
        await api_client.post(f"/api/runs/{run_id}/steps/writer/select/{resp.json()['id']}")

        resp1 = await api_client.post(f"/api/runs/{run_id}/accept", json={
            "accept_type": "original",
        })
        assert resp1.status_code == 200

        resp2 = await api_client.post(f"/api/runs/{run_id}/accept", json={
            "accept_type": "original",
        })
        assert resp2.status_code == 409  # already accepted with this type

        resp = await api_client.get(f"/api/chapters/{chapter_id}/versions")
        versions = resp.json()
        assert len(versions) == 1  # only one version, not duplicated

    @pytest.mark.asyncio
    async def test_accept_without_chapter_fails(self, api_client):
        project_id = await _create_project(api_client)

        resp = await api_client.post("/api/runs", json={
            "project_id": project_id,
        })
        run_id = resp.json()["id"]

        resp = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        await api_client.post(f"/api/runs/{run_id}/steps/planner/select/{resp.json()['id']}")

        resp = await api_client.post(f"/api/runs/{run_id}/steps/writer/execute", json={})
        await api_client.post(f"/api/runs/{run_id}/steps/writer/select/{resp.json()['id']}")

        resp = await api_client.post(f"/api/runs/{run_id}/accept", json={
            "accept_type": "original",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_detector_feedback_accepts_candidate_owned_by_project(self, api_client):
        run_id = await _run_to_selected_critic(api_client)
        run = (await api_client.get(f"/api/runs/{run_id}")).json()
        writer = next(step for step in run["steps"] if step["stage"] == "writer")

        response = await api_client.post(
            "/api/detector-feedbacks",
            json={
                "project_id": run["project_id"],
                "chapter_id": run["chapter_id"],
                "run_id": run_id,
                "candidate_id": writer["selected_candidate_id"],
                "detector_name": "测试检测器",
                "human_ratio": 25,
                "suspected_ai_ratio": 75,
                "ai_ratio": 0,
                "spans": [],
            },
        )

        assert response.status_code == 201
        assert response.json()["candidate_id"] == writer["selected_candidate_id"]

    @pytest.mark.asyncio
    async def test_detector_feedback_rejects_span_beyond_referenced_candidate(self, api_client):
        run_id = await _run_to_selected_critic(api_client)
        run = (await api_client.get(f"/api/runs/{run_id}")).json()
        writer = next(step for step in run["steps"] if step["stage"] == "writer")

        response = await api_client.post(
            "/api/detector-feedbacks",
            json={
                "project_id": run["project_id"],
                "chapter_id": run["chapter_id"],
                "run_id": run_id,
                "candidate_id": writer["selected_candidate_id"],
                "detector_name": "测试检测器",
                "human_ratio": 100,
                "suspected_ai_ratio": 0,
                "ai_ratio": 0,
                "spans": [{"start_paragraph": 99, "end_paragraph": 100}],
            },
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "SPAN_OUT_OF_RANGE"

    @pytest.mark.asyncio
    async def test_detector_feedback_patch_revalidates_merged_ratios(self, api_client):
        run_id = await _run_to_selected_critic(api_client)
        run = (await api_client.get(f"/api/runs/{run_id}")).json()
        writer = next(step for step in run["steps"] if step["stage"] == "writer")
        created = await api_client.post(
            "/api/detector-feedbacks",
            json={
                "project_id": run["project_id"],
                "chapter_id": run["chapter_id"],
                "run_id": run_id,
                "candidate_id": writer["selected_candidate_id"],
                "detector_name": "测试检测器",
                "human_ratio": 50,
                "suspected_ai_ratio": 25,
                "ai_ratio": 25,
                "spans": [],
            },
        )
        assert created.status_code == 201

        response = await api_client.patch(
            f"/api/detector-feedbacks/{created.json()['id']}",
            json={"ai_ratio": 60},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_RATIO_TOTAL"

    @pytest.mark.asyncio
    async def test_detector_feedback_can_be_listed_updated_and_deleted(self, api_client):
        run_id = await _run_to_selected_critic(api_client)
        run = (await api_client.get(f"/api/runs/{run_id}")).json()
        writer = next(step for step in run["steps"] if step["stage"] == "writer")
        created = await api_client.post(
            "/api/detector-feedbacks",
            json={
                "project_id": run["project_id"],
                "chapter_id": run["chapter_id"],
                "run_id": run_id,
                "candidate_id": writer["selected_candidate_id"],
                "detector_name": "初次检测",
                "human_ratio": 0,
                "suspected_ai_ratio": 0,
                "ai_ratio": 100,
                "spans": [],
                "notes": "外部检测原始结果",
            },
        )
        assert created.status_code == 201
        feedback_id = created.json()["id"]

        listed = await api_client.get(
            "/api/detector-feedbacks",
            params={"project_id": run["project_id"], "chapter_id": run["chapter_id"]},
        )
        assert listed.status_code == 200
        assert feedback_id in [item["id"] for item in listed.json()]

        updated = await api_client.patch(
            f"/api/detector-feedbacks/{feedback_id}",
            json={"detector_name": "复核检测", "notes": "已人工复核"},
        )
        assert updated.status_code == 200
        assert updated.json()["detector_name"] == "复核检测"
        assert updated.json()["ai_ratio"] == 100

        deleted = await api_client.delete(f"/api/detector-feedbacks/{feedback_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "ok"}
        listed_after_delete = await api_client.get(
            "/api/detector-feedbacks",
            params={"project_id": run["project_id"], "chapter_id": run["chapter_id"]},
        )
        assert feedback_id not in [item["id"] for item in listed_after_delete.json()]

    @pytest.mark.asyncio
    async def test_detector_feedback_accepts_judge_final_text_span(self, api_client):
        run_id = await _run_to_selected_critic(api_client)
        selected = await api_client.post(
            f"/api/runs/{run_id}/critic/select-issues",
            json={"issue_ids": ["I01"]},
        )
        assert selected.status_code == 200
        reviser = await api_client.post(f"/api/runs/{run_id}/steps/reviser/execute", json={})
        assert reviser.status_code == 200
        assert (await api_client.post(f"/api/runs/{run_id}/steps/reviser/select/{reviser.json()['id']}")).status_code == 200
        judge = await api_client.post(f"/api/runs/{run_id}/steps/judge/execute", json={})
        assert judge.status_code == 200
        assert (await api_client.post(f"/api/runs/{run_id}/steps/judge/select/{judge.json()['id']}")).status_code == 200
        run = (await api_client.get(f"/api/runs/{run_id}")).json()
        judge_step = next(step for step in run["steps"] if step["stage"] == "judge")

        response = await api_client.post(
            "/api/detector-feedbacks",
            json={
                "project_id": run["project_id"],
                "chapter_id": run["chapter_id"],
                "run_id": run_id,
                "candidate_id": judge_step["selected_candidate_id"],
                "detector_name": "测试检测器",
                "human_ratio": 100,
                "suspected_ai_ratio": 0,
                "ai_ratio": 0,
                "spans": [{"start_paragraph": 1, "end_paragraph": 1}],
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_detector_feedback_records_full_ai_result_for_accepted_version(self, api_client):
        project_id = await _create_project(api_client)
        chapter_id = await _create_chapter(api_client, project_id)
        run = await api_client.post("/api/runs", json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "scene_instruction": "生成可采用初稿",
        })
        run_id = run.json()["id"]
        planner = await api_client.post(f"/api/runs/{run_id}/steps/planner/execute", json={})
        await api_client.post(f"/api/runs/{run_id}/steps/planner/select/{planner.json()['id']}")
        writer = await api_client.post(f"/api/runs/{run_id}/steps/writer/execute", json={})
        await api_client.post(f"/api/runs/{run_id}/steps/writer/select/{writer.json()['id']}")
        accepted = await api_client.post(f"/api/runs/{run_id}/accept", json={"accept_type": "original"})
        assert accepted.status_code == 200
        accepted_version_id = (await api_client.get(f"/api/runs/{run_id}")).json()["accepted_version_id"]
        assert accepted_version_id

        recorded = await api_client.post(
            "/api/detector-feedbacks",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "run_id": run_id,
                "chapter_version_id": accepted_version_id,
                "detector_name": "特邀测试",
                "human_ratio": 0,
                "suspected_ai_ratio": 0,
                "ai_ratio": 100,
                "spans": [],
                "notes": "保留外部结果，不触发自动改稿",
            },
        )

        assert recorded.status_code == 201
        assert recorded.json()["chapter_version_id"] == accepted_version_id
        assert recorded.json()["ai_ratio"] == 100
