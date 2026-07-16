import pytest
from app.llm.base import LlmRequest, LlmResponse, LlmError
from app.llm.mock import MockClient, MOCK_MODE_NORMAL, MOCK_MODE_TIMEOUT, MOCK_MODE_INVALID_JSON, MOCK_MODE_RATE_LIMIT


class TestMockClient:
    async def test_normal_response(self):
        client = MockClient(mode=MOCK_MODE_NORMAL, delay_ms=0)
        request = LlmRequest(
            system_prompt="你是一个小说作家助手",
            user_prompt="写一段内容",
            model="mock-model",
        )
        response = await client.complete(request)
        assert isinstance(response, LlmResponse)
        assert len(response.text) > 0
        assert response.input_tokens is not None
        assert response.output_tokens is not None

    async def test_timeout_mode(self):
        client = MockClient(mode=MOCK_MODE_TIMEOUT, delay_ms=0)
        request = LlmRequest(system_prompt="test", user_prompt="test", model="mock-model")
        with pytest.raises(LlmError) as exc:
            await client.complete(request)
        assert exc.value.code == "LLM_TIMEOUT"

    async def test_rate_limit_mode(self):
        client = MockClient(mode=MOCK_MODE_RATE_LIMIT, delay_ms=0)
        request = LlmRequest(system_prompt="test", user_prompt="test", model="mock-model")
        with pytest.raises(LlmError) as exc:
            await client.complete(request)
        assert exc.value.code == "LLM_RATE_LIMIT"

    async def test_planner_response_format(self):
        client = MockClient(mode=MOCK_MODE_NORMAL, delay_ms=0)
        request = LlmRequest(
            system_prompt="你是一个小说规划助手 plan",
            user_prompt="规划一个场景",
            model="mock-model",
        )
        response = await client.complete(request)
        import json
        data = json.loads(response.text)
        assert "scene_goal" in data
        assert "characters" in data

    async def test_critic_response_format(self):
        client = MockClient(mode=MOCK_MODE_NORMAL, delay_ms=0)
        request = LlmRequest(
            system_prompt="你是一个严格的 critic 评审",
            user_prompt="评审这段文字",
            model="mock-model",
        )
        response = await client.complete(request)
        import json
        data = json.loads(response.text)
        assert "recommendation" in data
        assert "issues" in data

    async def test_reviser_response_format(self):
        client = MockClient(mode=MOCK_MODE_NORMAL, delay_ms=0)
        request = LlmRequest(
            system_prompt="你是一个 revision 专家 reviser",
            user_prompt="修订这段文字",
            model="mock-model",
        )
        response = await client.complete(request)
        import json
        data = json.loads(response.text)
        assert "patches" in data
        assert "revised_text" in data

    async def test_judge_response_format(self):
        client = MockClient(mode=MOCK_MODE_NORMAL, delay_ms=0)
        request = LlmRequest(
            system_prompt="你是一个小说质量 judge",
            user_prompt="评估修订结果",
            model="mock-model",
        )
        response = await client.complete(request)
        import json
        data = json.loads(response.text)
        assert "decision" in data
        assert "issue_results" in data

    async def test_writer_plain_text(self):
        client = MockClient(mode=MOCK_MODE_NORMAL, delay_ms=0)
        request = LlmRequest(
            system_prompt="你是一个小说作家",
            user_prompt="写一段内容",
            model="mock-model",
        )
        response = await client.complete(request)
        assert "章节正文" in response.text
        import json
        try:
            json.loads(response.text)
            is_json = True
        except (json.JSONDecodeError, ValueError):
            is_json = False
        assert not is_json, "Writer should return plain text"


class TestLlmRequest:
    def test_defaults(self):
        req = LlmRequest(system_prompt="test", user_prompt="test", model="test-model")
        assert req.temperature == 0.7
        assert req.top_p == 1.0
        assert req.max_output_tokens == 4096
        assert req.timeout_seconds == 120

    def test_custom_values(self):
        req = LlmRequest(
            system_prompt="test", user_prompt="test", model="test-model",
            temperature=0.3, top_p=0.9, max_output_tokens=2048, timeout_seconds=60,
        )
        assert req.temperature == 0.3
        assert req.max_output_tokens == 2048


class TestLlmResponse:
    def test_response_fields(self):
        resp = LlmResponse(text="hello", input_tokens=10, output_tokens=5, latency_ms=100, provider_request_id="req-123")
        assert resp.text == "hello"
        assert resp.input_tokens == 10

    def test_response_defaults(self):
        resp = LlmResponse(text="hello")
        assert resp.latency_ms == 0
        assert resp.provider_request_id is None


class TestLlmError:
    def test_error_fields(self):
        error = LlmError("LLM_TIMEOUT", "请求超时", 502)
        assert error.code == "LLM_TIMEOUT"
        assert error.message == "请求超时"
        assert error.status_code == 502
