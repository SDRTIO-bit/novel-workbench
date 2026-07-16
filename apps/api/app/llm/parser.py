import json
import re
from dataclasses import dataclass


@dataclass
class ParsedOutput:
    data: dict | None
    raw_text: str
    valid: bool
    error: str | None = None


def parse_json(text: str) -> ParsedOutput:
    stripped = text.strip()

    result = _try_parse(stripped)
    if result is not None:
        return ParsedOutput(data=result, raw_text=text, valid=True)

    fenced = _extract_fenced_json(stripped)
    if fenced is not None:
        result = _try_parse(fenced)
        if result is not None:
            return ParsedOutput(data=result, raw_text=text, valid=True)

    extracted = _extract_first_json(stripped)
    if extracted is not None:
        result = _try_parse(extracted)
        if result is not None:
            return ParsedOutput(data=result, raw_text=text, valid=True)

    return ParsedOutput(
        data=None,
        raw_text=text,
        valid=False,
        error="STRUCTURED_OUTPUT_INVALID: 无法从输出中提取有效的 JSON",
    )


def _try_parse(text: str) -> dict | None:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _extract_fenced_json(text: str) -> str | None:
    pattern = r"```(?:json)?\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _extract_first_json(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None
