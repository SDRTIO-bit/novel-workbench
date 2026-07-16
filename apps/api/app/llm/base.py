from dataclasses import dataclass, field


@dataclass
class LlmRequest:
    system_prompt: str
    user_prompt: str
    model: str
    temperature: float = 0.7
    top_p: float = 1.0
    max_output_tokens: int = 4096
    timeout_seconds: int = 120


@dataclass
class LlmResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0
    provider_request_id: str | None = None


class LlmError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502):
        self.code = code
        self.message = message
        self.status_code = status_code


class BaseLlmClient:
    async def complete(self, request: LlmRequest) -> LlmResponse:
        raise NotImplementedError
