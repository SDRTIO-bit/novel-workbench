import pytest


def test_parse_tgbreak_response_extracts_notes_text_and_extra_modules():
    from app.tgbreak.output import parse_tgbreak_response

    raw = "<draft_notes>先梳理</draft_notes>\n正文第一段\n<extra_module>选项</extra_module>"

    parsed = parse_tgbreak_response(
        raw,
        source_preset_id="preset-1",
        source_preset_sha256="sha-1",
        resolved_entry_identifiers=["head", "tail"],
        reasoning_tokens=12,
    )

    assert parsed.draft_notes == "先梳理"
    assert parsed.draft_text == "正文第一段"
    assert parsed.extra_modules == ["<extra_module>选项</extra_module>"]
    assert parsed.raw_response == raw
    assert parsed.requested_reasoning_mode == "disabled"
    assert parsed.reasoning_tokens == 12


def test_missing_draft_notes_closing_tag_fails_without_repair():
    from app.tgbreak.output import TgbreakOutputError, parse_tgbreak_response

    with pytest.raises(TgbreakOutputError, match="DRAFT_NOTES_CLOSING_TAG_MISSING"):
        parse_tgbreak_response(
            "<draft_notes>未闭合\n正文",
            source_preset_id="preset-1",
            source_preset_sha256="sha-1",
            resolved_entry_identifiers=[],
        )
