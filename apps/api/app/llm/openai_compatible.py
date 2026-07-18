import json
import time
import httpx
from app.llm.base import BaseLlmClient, LlmRequest, LlmResponse, LlmError


class OpenAiCompatibleClient(BaseLlmClient):
    def __init__(self, base_url: str, api_key: str, extra_headers: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = extra_headers or {}

    async def complete(self, request: LlmRequest) -> LlmResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        body = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_output_tokens,
            "reasoning_mode": request.reasoning_mode,
        }
        if request.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )

            latency_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code == 401:
                raise LlmError("LLM_AUTH_FAILED", "认证失败，请检查 API Key", 502)
            if resp.status_code == 429:
                raise LlmError("LLM_RATE_LIMIT", "请求频率超限，请稍后重试", 502)
            if resp.status_code == 404:
                raise LlmError("LLM_MODEL_NOT_FOUND", f"模型 {request.model} 不存在", 502)

            data = resp.json()

            if resp.status_code >= 400:
                error_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                raise LlmError(
                    "LLM_CONNECTION_FAILED",
                    f"模型服务返回错误: {error_msg}",
                    502,
                )

            choice = data["choices"][0]
            return LlmResponse(
                text=choice["message"]["content"],
                input_tokens=data.get("usage", {}).get("prompt_tokens"),
                output_tokens=data.get("usage", {}).get("completion_tokens"),
                latency_ms=latency_ms,
                provider_request_id=data.get("id"),
                finish_reason=choice.get("finish_reason"),
                reasoning_tokens=(
                    data.get("usage", {})
                    .get("completion_tokens_details", {})
                    .get("reasoning_tokens")
                ),
            )

        except httpx.TimeoutException:
            raise LlmError("LLM_TIMEOUT", f"请求超时 ({request.timeout_seconds}s)", 502)
        except httpx.ConnectError:
            raise LlmError("LLM_CONNECTION_FAILED", "无法连接到模型服务，请检查 Base URL", 502)
        except LlmError:
            raise
        except Exception as e:
            raise LlmError("LLM_CONNECTION_FAILED", f"请求异常: {str(e)}", 502)
