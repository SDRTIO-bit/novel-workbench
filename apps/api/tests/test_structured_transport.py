import json

import pytest

import app.models.chapter  # noqa: F401
import app.models.generation  # noqa: F401
import app.models.project  # noqa: F401
import app.models.prompt  # noqa: F401
import app.models.provider  # noqa: F401
import app.models.workflow  # noqa: F401
from app.llm.base import LlmRequest, LlmResponse
from app.llm.openai_compatible import OpenAiCompatibleClient
from app.models.generation import GenerationCandidate
from app.models.project import Project
from app.models.prompt import PromptProfile, PromptVersion
from app.models.workflow import WorkflowProfile, WorkflowStepConfig
from app.services.context_service import ContextService
from app.services.generation_service import GenerationService


class _FakeHttpResponse:
    status_code = 200

    def json(self):
        return {
            "id": "request-1",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"ok": true}'},
            }],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
        }


class _RecordingAsyncClient:
    body = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, _url, *, headers, json):
        type(self).body = json
        return _FakeHttpResponse()


class _NoReasoningHttpResponse(_FakeHttpResponse):
    def json(self):
        data = super().json()
        data["choices"][0]["finish_reason"] = "length"
        data["usage"].pop("completion_tokens_details")
        return data


class _NoReasoningAsyncClient(_RecordingAsyncClient):
    async def post(self, _url, *, headers, json):
        type(self).body = json
        return _NoReasoningHttpResponse()


@pytest.mark.asyncio
async def test_openai_compatible_json_mode_is_transmitted_and_response_metadata_is_preserved(monkeypatch):
    import app.llm.openai_compatible as adapter

    monkeypatch.setattr(adapter.httpx, "AsyncClient", _RecordingAsyncClient)
    client = OpenAiCompatibleClient("https://example.test/v1", "secret")

    response = await client.complete(LlmRequest(
        system_prompt="system",
        user_prompt="user",
        model="model",
        response_format="json_object",
    ))

    assert _RecordingAsyncClient.body["response_format"] == {"type": "json_object"}
    assert response.finish_reason == "stop"
    assert response.reasoning_tokens == 3


@pytest.mark.asyncio
async def test_openai_compatible_text_mode_omits_response_format(monkeypatch):
    import app.llm.openai_compatible as adapter

    monkeypatch.setattr(adapter.httpx, "AsyncClient", _RecordingAsyncClient)
    client = OpenAiCompatibleClient("https://example.test/v1", "secret")

    response = await client.complete(LlmRequest(
        system_prompt="system",
        user_prompt="user",
        model="model",
        response_format="text",
    ))

    assert "response_format" not in _RecordingAsyncClient.body
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_openai_compatible_preserves_length_and_missing_reasoning_metadata(monkeypatch):
    import app.llm.openai_compatible as adapter

    monkeypatch.setattr(adapter.httpx, "AsyncClient", _NoReasoningAsyncClient)
    client = OpenAiCompatibleClient("https://example.test/v1", "secret")
    response = await client.complete(LlmRequest(
        system_prompt="system",
        user_prompt="user",
        model="model",
        response_format="json_object",
    ))

    assert response.finish_reason == "length"
    assert response.reasoning_tokens is None


def test_llm_request_rejects_unsupported_response_format():
    with pytest.raises(ValueError, match="response_format"):
        LlmRequest(system_prompt="system", user_prompt="user", model="model", response_format="yaml")


@pytest.mark.asyncio
async def test_context_prompt_metadata_exposes_output_mode():
    version = PromptVersion(
        profile_id="profile",
        version_number=1,
        output_mode="structured",
        output_schema_name="critic",
    )

    assert await ContextService._prompt_meta(ContextService, version) == {
        "prompt_version_id": version.id,
        "output_schema_name": "critic",
        "output_mode": "structured",
    }


def test_generation_candidate_accepts_transport_observability_fields():
    candidate = GenerationCandidate(
        step_id="step",
        attempt_number=1,
        finish_reason="length",
        reasoning_tokens=42,
    )

    assert candidate.finish_reason == "length"
    assert candidate.reasoning_tokens == 42


class _CaptureProvider:
    def __init__(self, *, text: str, finish_reason: str = "stop"):
        self.text = text
        self.finish_reason = finish_reason
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return LlmResponse(
            text=self.text,
            input_tokens=10,
            output_tokens=20,
            latency_ms=1,
            finish_reason=self.finish_reason,
            reasoning_tokens=5,
        )


async def _make_run_with_stage_prompt(db_session, *, stage: str, output_mode: str):
    project = Project(name="传输层测试", genre="测试")
    db_session.add(project)
    await db_session.flush()

    profile = PromptProfile(stage=stage, name=f"{stage} prompt", is_builtin=False)
    db_session.add(profile)
    await db_session.flush()
    version = PromptVersion(
        profile_id=profile.id,
        version_number=1,
        system_template="system",
        user_template="user",
        output_mode=output_mode,
        output_schema_name=stage if output_mode == "structured" else None,
    )
    db_session.add(version)

    workflow = WorkflowProfile(name=f"{stage} workflow", is_default=False)
    db_session.add(workflow)
    await db_session.flush()
    db_session.add(WorkflowStepConfig(
        workflow_profile_id=workflow.id,
        stage=stage,
        prompt_version_id=version.id,
    ))
    await db_session.flush()

    service = GenerationService(db_session)
    run = await service.create_run(project.id, None, workflow.id, "scene")
    return service, run, version


async def test_structured_length_response_is_saved_and_marked_truncated(db_session, monkeypatch):
    service, run, _version = await _make_run_with_stage_prompt(
        db_session, stage="planner", output_mode="structured"
    )
    provider = _CaptureProvider(text='{"planner_contract_version": 2', finish_reason="length")

    async def resolve_provider(_self, _provider_id):
        return provider

    monkeypatch.setattr(GenerationService, "_resolve_provider", resolve_provider)
    candidate = await service.execute_stage(run.id, "planner", {})

    assert provider.requests[0].response_format == "json_object"
    assert candidate.error_code == "STRUCTURED_OUTPUT_TRUNCATED"
    assert "达到 max_output_tokens" in candidate.error_message
    assert candidate.raw_response == '{"planner_contract_version": 2'
    assert candidate.finish_reason == "length"
    assert candidate.reasoning_tokens == 5


async def test_structured_stop_response_enters_normal_contract_validation(db_session, monkeypatch):
    service, run, _version = await _make_run_with_stage_prompt(
        db_session, stage="planner", output_mode="structured"
    )
    provider = _CaptureProvider(text=json.dumps({"scene_goal": "推进场景"}), finish_reason="stop")

    async def resolve_provider(_self, _provider_id):
        return provider

    monkeypatch.setattr(GenerationService, "_resolve_provider", resolve_provider)
    candidate = await service.execute_stage(run.id, "planner", {})

    assert candidate.error_code is None
    assert candidate.finish_reason == "stop"
    assert candidate.parsed_output_json


async def test_writer_plain_text_prompt_uses_text_response_mode(db_session, monkeypatch):
    service, run, _version = await _make_run_with_stage_prompt(
        db_session, stage="writer", output_mode="plain_text"
    )
    planner_step = await service.repo.get_step(run.id, "planner")
    planner_candidate = GenerationCandidate(
        step_id=planner_step.id,
        attempt_number=1,
        parsed_output_json="{}",
        is_selected=True,
    )
    db_session.add(planner_candidate)
    await db_session.flush()
    planner_step.status = "completed"
    planner_step.selected_candidate_id = planner_candidate.id
    await db_session.flush()

    provider = _CaptureProvider(text="正文", finish_reason="stop")

    async def resolve_provider(_self, _provider_id):
        return provider

    monkeypatch.setattr(GenerationService, "_resolve_provider", resolve_provider)
    candidate = await service.execute_stage(run.id, "writer", {})

    assert provider.requests[0].response_format == "text"
    assert candidate.error_code is None
    assert candidate.text_output == "正文"
