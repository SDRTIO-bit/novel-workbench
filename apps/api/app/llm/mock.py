import time
import json
from app.llm.base import BaseLlmClient, LlmRequest, LlmResponse, LlmError

MOCK_MODE_NORMAL = "normal"
MOCK_MODE_TIMEOUT = "timeout"
MOCK_MODE_INVALID_JSON = "invalid_json"
MOCK_MODE_RATE_LIMIT = "rate_limit"


class MockClient(BaseLlmClient):
    def __init__(self, mode: str = MOCK_MODE_NORMAL, delay_ms: int = 50):
        self.mode = mode
        self.delay_ms = delay_ms

    async def complete(self, request: LlmRequest) -> LlmResponse:
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000)

        if self.mode == MOCK_MODE_TIMEOUT:
            raise LlmError("LLM_TIMEOUT", "模拟超时", 502)
        if self.mode == MOCK_MODE_RATE_LIMIT:
            raise LlmError("LLM_RATE_LIMIT", "模拟频率限制", 502)

        text = self._build_response(request)

        if self.mode == MOCK_MODE_INVALID_JSON:
            text = "这不是有效的 JSON { broken"

        return LlmResponse(
            text=text,
            input_tokens=len(request.system_prompt + request.user_prompt) // 3,
            output_tokens=len(text) // 3,
            latency_ms=self.delay_ms,
            provider_request_id="mock-request-001",
        )

    def _build_response(self, request: LlmRequest) -> str:
        if "plan" in request.system_prompt.lower():
            return json.dumps({
                "scene_goal": "主角找到关键线索",
                "location": "废弃工厂",
                "start_time": "深夜",
                "characters": [
                    {
                        "name": "主角",
                        "goal": "调查真相",
                        "known": ["有不明失踪事件"],
                        "unknown": ["幕后黑手身份"],
                        "mistaken_beliefs": ["信任的伙伴不会背叛"],
                        "constraints": ["不能引起注意"],
                    }
                ],
                "pressure": "时间紧迫",
                "turning_point": "发现隐藏的监控摄像头",
                "end_condition": "逃离工厂",
                "forbidden": ["不能暴露身份"],
            }, ensure_ascii=False)

        if "critic" in request.system_prompt.lower():
            return json.dumps({
                "decision": "local_revision",
                "issues": [
                    {
                        "issue_id": "I01",
                        "severity": "medium",
                        "issue_type": "character_voice",
                        "paragraph_ids": ["P003"],
                        "problem": "角色语气与设定不符",
                        "revision_goal": "调整为更沉稳的语气",
                    }
                ],
                "protected_strengths": [
                    {
                        "paragraph_ids": ["P006"],
                        "reason": "场景氛围营造出色",
                    }
                ],
            }, ensure_ascii=False)

        if "reviser" in request.system_prompt.lower():
            return json.dumps({
                "patches": [
                    {
                        "issue_id": "I01",
                        "operation": "replace",
                        "target_paragraph_ids": ["P003"],
                        "replacement": "修订后的段落内容",
                    }
                ],
                "revised_text": "完整修订文本",
                "unchanged_ratio": 0.85,
                "introduced_facts": [],
            }, ensure_ascii=False)

        if "judge" in request.system_prompt.lower():
            return json.dumps({
                "decision": "accept_revision",
                "issue_results": [
                    {
                        "issue_id": "I01",
                        "status": "resolved",
                        "action": "keep_revision",
                    }
                ],
                "new_problems": [],
                "final_text": "合并修订文本",
                "state_patch": {
                    "facts_added": [],
                    "relationship_changes": [],
                    "unresolved_threads": [],
                },
            }, ensure_ascii=False)

        return "这是模拟的章节正文内容。故事从这里开始展开..."
