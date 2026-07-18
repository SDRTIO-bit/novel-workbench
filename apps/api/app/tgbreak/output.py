import re

from app.tgbreak.models import TgbreakOutput


_DRAFT_NOTES_RE = re.compile(r"<draft_notes>(.*?)</draft_notes>", re.DOTALL | re.IGNORECASE)
_EXTRA_BLOCK_RE = re.compile(
    r"(?s)(?:^|\n)(?P<block><(?P<tag>[A-Za-z][\w:-]*(?:_module|details|actions?|w2g|catsay|ce|summary|time|location|image|audio|nsfw))\b[^>]*>.*?</(?P=tag)>)\s*$",
    re.IGNORECASE,
)


class TgbreakOutputError(ValueError):
    pass


def parse_tgbreak_response(
    raw_response: str,
    *,
    source_preset_id: str,
    source_preset_sha256: str,
    resolved_entry_identifiers: list[str],
    reasoning_tokens: int | None = None,
    requested_reasoning_mode: str = "disabled",
) -> TgbreakOutput:
    open_pos = raw_response.lower().find("<draft_notes>")
    close_pos = raw_response.lower().find("</draft_notes>")
    if open_pos == -1:
        raise TgbreakOutputError("DRAFT_NOTES_OPEN_TAG_MISSING")
    if close_pos == -1 or close_pos < open_pos:
        raise TgbreakOutputError("DRAFT_NOTES_CLOSING_TAG_MISSING")

    match = _DRAFT_NOTES_RE.search(raw_response)
    if not match:
        raise TgbreakOutputError("DRAFT_NOTES_CLOSING_TAG_MISSING")

    draft_notes = match.group(1).strip()
    tail = raw_response[match.end():].strip()
    extra_modules: list[str] = []
    while tail:
        extra_match = _EXTRA_BLOCK_RE.search(tail)
        if not extra_match:
            break
        extra_modules.insert(0, extra_match.group("block"))
        tail = tail[: extra_match.start()].rstrip()

    return TgbreakOutput(
        raw_response=raw_response,
        draft_notes=draft_notes,
        draft_text=tail,
        extra_modules=extra_modules,
        source_preset_id=source_preset_id,
        source_preset_sha256=source_preset_sha256,
        resolved_entry_identifiers=resolved_entry_identifiers,
        requested_reasoning_mode=requested_reasoning_mode,
        reasoning_tokens=reasoning_tokens,
    )
