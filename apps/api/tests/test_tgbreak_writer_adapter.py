import json

import pytest
from sqlalchemy import select

from app.llm.base import LlmResponse
from app.models.generation import GenerationCandidate
from app.models.project import Project, ProjectDocument
from app.models.provider import Provider  # noqa: F401 - register provider table for isolated metadata
from app.models.prompt import PromptProfile, PromptVersion
from app.models.tgbreak import TgbreakOutputRecord
from app.models.workflow import STAGES, WorkflowProfile, WorkflowStepConfig
from app.services.context_service import ContextService
from app.services.generation_service import GenerationService
from app.services.tgbreak_service import persist_core_profile, persist_imported_preset
from app.services.workflow_service import WorkflowService
from app.tgbreak.models import CoreProfile, ImportedPreset, PresetMetadata, PromptEntry


REAL_SOURCE_SHA = "f7aa69ee58503b9b38994fedb532d9cb3794b775fb9ad732ecdc7a69a7c2fa10"
NOVEL_MODE = (
    "当前为作者级小说创作，不是单角色 RP。\n\n"
    "作者要求可以规定任意虚构角色和场景事件；\n"
    "但每个角色在正文中仍只能依据自己已经知道、看到或听到的信息行动。"
)


class RecordingProvider:
    def __init__(self, text):
        self.text = text
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return LlmResponse(
            text=self.text,
            input_tokens=101,
            output_tokens=37,
            latency_ms=4,
            finish_reason="stop",
            reasoning_tokens=0,
        )


def _imported_preset():
    return ImportedPreset(
        metadata=PresetMetadata(
            preset_id="real-tgbreak-preset",
            source_path="imported-private-source.json",
            source_sha256=REAL_SOURCE_SHA,
            file_size=123,
            source_format_version="3.0.5",
            top_level_keys=["prompts"],
            unsupported_fields=[],
            parse_mode="standard_json",
        ),
        entries=[
            PromptEntry(
                0,
                "core-system",
                "Core System",
                True,
                "system",
                "SETTING=<Story setting>\nHISTORY=<interaction_record>\nLAST=<ai_last_output>\nPLAN=<peip>",
            ),
            PromptEntry(
                1,
                "chatHistory",
                "Chat History",
                True,
                "system",
                "",
                marker=True,
                system_prompt=True,
            ),
            PromptEntry(
                2,
                "assistant-tail",
                "Draft Notes Tail",
                True,
                "assistant",
                "Reply with <draft_notes>analysis</draft_notes> and prose.",
            ),
        ],
    )


async def _prompt(db_session, stage, system_template, user_template):
    profile = PromptProfile(
        name=f"{stage} prompt",
        stage=stage,
        description="",
        is_builtin=True,
    )
    db_session.add(profile)
    await db_session.flush()
    version = PromptVersion(
        profile_id=profile.id,
        version_number=1,
        system_template=system_template,
        user_template=user_template,
        output_mode="structured" if stage == "critic" else "plain_text",
        output_schema_name="critic" if stage == "critic" else "",
    )
    db_session.add(version)
    await db_session.flush()
    return version


async def _fixture(db_session, *, mode="tgbreak"):
    project = Project(
        name="书店故事",
        genre="现实主义",
        author_note="保持克制",
        default_pov="第三人称限知",
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add_all([
        ProjectDocument(
            project_id=project.id,
            kind="characters",
            title="人物",
            content="老陈守书店；小满站在门外；猫叫阿橘。",
        ),
        ProjectDocument(
            project_id=project.id,
            kind="world",
            title="场景",
            content="老街书店临近打烊。",
        ),
    ])

    writer_prompt = await _prompt(
        db_session,
        "writer",
        "BUILTIN SYSTEM {{project_documents}}",
        "BUILTIN USER {{scene_plan}} {{scene_instruction}}",
    )
    critic_prompt = await _prompt(
        db_session,
        "critic",
        "CRITIC SYSTEM",
        "CRITIC DRAFT={{draft_text}}",
    )

    imported = _imported_preset()
    await persist_imported_preset(db_session, imported)
    profile_row = await persist_core_profile(
        db_session,
        CoreProfile(imported.preset_id, imported.source_sha256, {}),
    )

    workflow = WorkflowProfile(name="原管线", is_default=False)
    db_session.add(workflow)
    await db_session.flush()
    for stage in STAGES:
        db_session.add(WorkflowStepConfig(
            workflow_profile_id=workflow.id,
            stage=stage,
            prompt_version_id=(
                writer_prompt.id if stage == "writer"
                else critic_prompt.id if stage == "critic"
                else None
            ),
            writer_prompt_mode=mode if stage == "writer" else "builtin",
            tgbreak_profile_id=profile_row.id if stage == "writer" and mode == "tgbreak" else None,
        ))
    await db_session.flush()

    service = GenerationService(db_session)
    run = await service.repo.create_run(
        project_id=project.id,
        chapter_id=None,
        workflow_profile_id=workflow.id,
        scene_instruction="让小满进店并接近阿橘。",
    )
    planner_step = await service.repo.get_step(run.id, "planner")
    planner_payload = {
        "scene_goal": "小满跨过门槛并接近猫",
        "characters": [
            {"name": "老陈", "known": ["小满在门外"]},
            {"name": "小满", "known": ["书店里有猫"]},
        ],
        "forbidden": ["新增人物"],
    }
    planner_candidate = GenerationCandidate(
        step_id=planner_step.id,
        attempt_number=1,
        raw_response=json.dumps(planner_payload, ensure_ascii=False),
        parsed_output_json=json.dumps(planner_payload, ensure_ascii=False),
        text_output=json.dumps(planner_payload, ensure_ascii=False),
        is_selected=True,
    )
    db_session.add(planner_candidate)
    await db_session.flush()
    planner_step.selected_candidate_id = planner_candidate.id
    planner_step.status = "completed"
    await db_session.flush()
    return service, run, planner_candidate, profile_row, writer_prompt


def test_workflow_writer_mode_defaults_to_builtin_and_stage_graph_is_unchanged():
    column = WorkflowStepConfig.__table__.c.writer_prompt_mode
    assert column.default.arg == "builtin"
    assert column.server_default.arg == "builtin"
    assert STAGES == ["planner", "writer", "critic", "reviser", "judge"]


async def test_workflow_copy_preserves_writer_mode_and_non_writer_rejects_tgbreak(db_session):
    source = WorkflowProfile(name="source", is_default=False)
    db_session.add(source)
    await db_session.flush()
    db_session.add_all([
        WorkflowStepConfig(
            workflow_profile_id=source.id,
            stage="writer",
            writer_prompt_mode="tgbreak",
            tgbreak_profile_id="profile-id",
        ),
        WorkflowStepConfig(workflow_profile_id=source.id, stage="critic"),
    ])
    await db_session.flush()

    service = WorkflowService(db_session)
    duplicate = await service.duplicate_profile(source.id)
    copied_writer = next(step for step in duplicate.steps if step.stage == "writer")
    assert copied_writer.writer_prompt_mode == "tgbreak"
    assert copied_writer.tgbreak_profile_id == "profile-id"

    with pytest.raises(Exception) as exc_info:
        await service.update_step(source.id, "critic", {"writer_prompt_mode": "tgbreak"})
    assert getattr(exc_info.value, "code", None) == "INVALID_WRITER_PROMPT_MODE"


def test_adapter_maps_only_existing_writer_context_and_retains_planner_candidate_id():
    from app.services.tgbreak_writer_adapter import build_tgbreak_project_data_from_writer_context

    data = build_tgbreak_project_data_from_writer_context({
        "project_name": "书店故事",
        "project_genre": "现实主义",
        "author_note": "保持克制",
        "default_pov": "第三人称限知",
        "project_documents": "人物与世界观",
        "recent_chapters": "此前小满曾在街角看见书店",
        "current_chapter_text": "老陈把手放在门锁上。",
        "continuation_anchor": "手停在门锁上。",
        "scene_plan": '{"scene_goal":"进入书店"}',
        "scene_instruction": "小满最终进入书店。",
        "run_override": "不要新增人物。",
    }, selected_planner_candidate_id="planner-candidate-1")

    assert "人物与世界观" in data.variables["Story setting"]
    assert NOVEL_MODE in data.variables["Story setting"]
    assert data.variables["interaction_record"] == "此前小满曾在街角看见书店"
    assert data.variables["ai_last_output"] == "老陈把手放在门锁上。"
    assert '"scene_goal":"进入书店"' in data.variables["peip"]
    assert "小满最终进入书店。" in data.variables["peip"]
    assert "不要新增人物。" in data.variables["peip"]
    assert data.selected_planner_candidate_id == "planner-candidate-1"
    assert "critic" not in json.dumps(data.variables).lower()
    assert "judge" not in json.dumps(data.variables).lower()


async def test_builtin_writer_path_does_not_load_or_render_tgbreak(db_session, monkeypatch):
    service, run, _, _, writer_prompt = await _fixture(db_session, mode="builtin")
    provider = RecordingProvider("builtin prose")

    async def fake_resolve(_provider_id):
        return provider

    async def forbidden_loader(*_args, **_kwargs):
        raise AssertionError("builtin Writer must not load TGbreak")

    monkeypatch.setattr(service, "_resolve_provider", fake_resolve)
    monkeypatch.setattr("app.services.generation_service.load_tgbreak_profile", forbidden_loader)

    candidate = await service.execute_stage(run.id, "writer", {})

    assert candidate.error_code is None
    assert candidate.text_output == "builtin prose"
    assert candidate.prompt_version_id == writer_prompt.id
    assert candidate.rendered_system_prompt.startswith("BUILTIN SYSTEM")
    assert len(provider.requests) == 1
    assert provider.requests[0].messages is None
    assert provider.requests[0].reasoning_mode is None
    params = json.loads(candidate.parameters_json)
    assert "writer_prompt_mode" not in params
    assert "reasoning_mode" not in params
    assert not (await db_session.scalars(select(TgbreakOutputRecord))).all()


async def test_tgbreak_writer_uses_original_stage_candidate_and_critic_contract(db_session, monkeypatch):
    service, run, planner_candidate, profile_row, _ = await _fixture(db_session)
    raw = (
        "<draft_notes>重构现状；性格分析；灵魂注入；剧情推理；防全知；字数和文风检查。</draft_notes>\n"
        "小满跨过门槛，走到阿橘面前。阿橘抬头碰了碰她的手。"
    )
    provider = RecordingProvider(raw)

    async def fake_resolve(_provider_id):
        return provider

    monkeypatch.setattr(service, "_resolve_provider", fake_resolve)

    candidate = await service.execute_stage(run.id, "writer", {})

    assert candidate.error_code is None
    assert candidate.text_output == "小满跨过门槛，走到阿橘面前。阿橘抬头碰了碰她的手。"
    assert candidate.raw_response == raw
    assert candidate.prompt_version_id is None
    assert candidate.input_tokens == 101
    assert candidate.output_tokens == 37
    assert candidate.reasoning_tokens == 0
    assert candidate.finish_reason == "stop"
    params = json.loads(candidate.parameters_json)
    assert params["writer_prompt_mode"] == "tgbreak"
    assert params["tgbreak_profile_id"] == profile_row.id
    assert params["selected_planner_candidate_id"] == planner_candidate.id
    assert params["source_preset_sha256"] == REAL_SOURCE_SHA
    assert params["reasoning_mode"] == "disabled"

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.reasoning_mode == "disabled"
    assert request.response_format == "text"
    assert [message["role"] for message in request.messages] == [
        "system", "system", "user", "assistant"
    ]
    joined_messages = json.dumps(request.messages, ensure_ascii=False)
    assert NOVEL_MODE in request.messages[0]["content"]
    assert planner_candidate.id in joined_messages
    assert "让小满进店并接近阿橘" in joined_messages

    record = await db_session.scalar(
        select(TgbreakOutputRecord).where(TgbreakOutputRecord.candidate_id == candidate.id)
    )
    assert record is not None
    assert params["tgbreak_output_record_id"] == record.id
    assert record.draft_notes.startswith("重构现状")
    assert record.draft_text == candidate.text_output
    assert record.source_preset_sha256 == REAL_SOURCE_SHA
    assert json.loads(record.resolved_entry_identifiers_json) == [
        "core-system", "chatHistory", "assistant-tail"
    ]

    await db_session.refresh(run)
    await service.select_candidate(run.id, "writer", candidate.id)
    writer_step = await service.repo.get_step(run.id, "writer")
    assert writer_step.selected_candidate_id == candidate.id

    critic_request = await service._build_context_request(run, "critic", {})
    assert critic_request.draft_text == candidate.text_output
    critic_context = await ContextService(db_session).assemble(critic_request)
    assert candidate.text_output in critic_context["rendered_user_prompt"]
    assert "<draft_notes>" not in critic_context["rendered_user_prompt"]
    assert "重构现状" not in critic_context["rendered_user_prompt"]
    assert raw not in critic_context["rendered_user_prompt"]


async def test_tgbreak_format_failure_creates_failed_standard_candidate_without_retry(db_session, monkeypatch):
    service, run, _, _, _ = await _fixture(db_session)
    provider = RecordingProvider("<draft_notes>missing closing tag\nprose")

    async def fake_resolve(_provider_id):
        return provider

    monkeypatch.setattr(service, "_resolve_provider", fake_resolve)

    candidate = await service.execute_stage(run.id, "writer", {})

    assert len(provider.requests) == 1
    assert candidate.error_code == "TGBREAK_OUTPUT_FORMAT_INVALID"
    assert candidate.text_output == ""
    assert candidate.raw_response == "<draft_notes>missing closing tag\nprose"
    writer_step = await service.repo.get_step(run.id, "writer")
    assert writer_step.status == "failed"
    with pytest.raises(Exception) as exc_info:
        await service.select_candidate(run.id, "writer", candidate.id)
    assert getattr(exc_info.value, "code", None) == "CANDIDATE_INVALID"


def test_writer_prompt_mode_migration_follows_tgbreak_import_revision():
    from pathlib import Path

    migration = Path(__file__).parents[1] / "alembic" / "versions" / "h2i3j4k5l6m7_add_writer_prompt_mode.py"
    text = migration.read_text(encoding="utf-8")
    assert 'down_revision: Union[str, Sequence[str], None] = "g1h2i3j4k5l6"' in text
    assert 'server_default="builtin"' in text
