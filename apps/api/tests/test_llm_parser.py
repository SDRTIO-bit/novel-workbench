import pytest
from app.llm.parser import parse_json, ParsedOutput


class TestParsePlainJson:
    def test_valid_plain_json(self):
        result = parse_json('{"key": "value"}')
        assert result.valid is True
        assert result.data == {"key": "value"}

    def test_invalid_json(self):
        result = parse_json("{not valid json}")
        assert result.valid is False
        assert result.data is None
        assert "STRUCTURED_OUTPUT_INVALID" in result.error

    def test_array_not_dict(self):
        result = parse_json('[1, 2, 3]')
        assert result.valid is False
        assert result.data is None

    def test_with_bom(self):
        result = parse_json('\ufeff{"status": "ok"}')
        assert result.valid is True
        assert result.data == {"status": "ok"}

    def test_planner_output(self):
        result = parse_json('''{
            "scene_goal": "test",
            "location": "test",
            "start_time": "test",
            "characters": [
                {
                    "name": "A",
                    "goal": "B",
                    "known": [],
                    "unknown": [],
                    "mistaken_beliefs": [],
                    "constraints": []
                }
            ],
            "pressure": "test",
            "turning_point": "test",
            "end_condition": "test",
            "forbidden": []
        }''')
        assert result.valid is True
        assert result.data["scene_goal"] == "test"

    def test_critic_output(self):
        result = parse_json('''{
            "decision": "local_revision",
            "issues": [
                {
                    "issue_id": "I01",
                    "severity": "medium",
                    "issue_type": "character_voice",
                    "paragraph_ids": ["P003"],
                    "problem": "test",
                    "revision_goal": "test"
                }
            ],
            "protected_strengths": [
                {
                    "paragraph_ids": ["P006"],
                    "reason": "good"
                }
            ]
        }''')
        assert result.valid is True
        assert result.data["decision"] == "local_revision"


class TestParseFencedJson:
    def test_fenced_with_json_tag(self):
        text = """这是一些说明文字。
```json
{"key": "value"}
```
这是结尾。"""
        result = parse_json(text)
        assert result.valid is True
        assert result.data == {"key": "value"}

    def test_fenced_without_tag(self):
        text = """前文。
```
{"status": "ok"}
```
后文。"""
        result = parse_json(text)
        assert result.valid is True
        assert result.data == {"status": "ok"}

    def test_fenced_critic_output(self):
        text = """以下是诊断结果：

```json
{
    "decision": "pass",
    "issues": [],
    "protected_strengths": []
}
```

请根据这些结果进行修订。"""
        result = parse_json(text)
        assert result.valid is True
        assert result.data["decision"] == "pass"


class TestParseExtractedJson:
    def test_json_embedded_in_text(self):
        text = "分析的结论是：{\"score\": 8, \"comment\": \"很好\"}，以上就是全部内容。"
        result = parse_json(text)
        assert result.valid is True
        assert result.data == {"score": 8, "comment": "很好"}

    def test_nested_json_extraction(self):
        text = '前文 {"a": {"b": [1, 2, 3]}} 后文'
        result = parse_json(text)
        assert result.valid is True
        assert result.data == {"a": {"b": [1, 2, 3]}}

    def test_only_text_no_json(self):
        result = parse_json("这是一段没有任何JSON的纯文本内容。")
        assert result.valid is False
        assert result.data is None

    def test_incomplete_json(self):
        result = parse_json('{"key": "value')
        assert result.valid is False
        assert result.data is None

    def test_raw_text_preserved(self):
        text = "blah {\"x\": 1} blah"
        result = parse_json(text)
        assert result.valid is True
        assert result.raw_text == text


class TestParseEdgeCases:
    def test_empty_string(self):
        result = parse_json("")
        assert result.valid is False
        assert result.data is None

    def test_braces_in_string_values(self):
        text = '{"text": "包含{大括}号的内容"}'
        result = parse_json(text)
        assert result.valid is True
        assert result.data["text"] == "包含{大括}号的内容"

    def test_multiple_json_objects(self):
        text = '{"first": 1} and {"second": 2}'
        result = parse_json(text)
        assert result.valid is True
        assert result.data == {"first": 1}

    def test_unicode_json(self):
        result = parse_json('{"目标": "完成测试", "优先级": 3}')
        assert result.valid is True
        assert result.data == {"目标": "完成测试", "优先级": 3}
