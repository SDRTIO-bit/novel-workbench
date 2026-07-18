import pytest


def _preset(entries):
    from app.tgbreak.models import ImportedPreset, PresetMetadata

    return ImportedPreset(
        metadata=PresetMetadata(
            preset_id="preset-1",
            source_path="fixture.json",
            source_sha256="sha-1",
            file_size=1,
            source_format_version="fixture",
            top_level_keys=["prompts"],
            unsupported_fields=[],
            parse_mode="standard_json",
        ),
        entries=entries,
    )


def test_renderer_executes_macros_comments_and_keeps_assistant_after_user():
    from app.tgbreak.models import CoreProfile, PromptEntry
    from app.tgbreak.renderer import render_tgbreak

    preset = _preset([
        PromptEntry(0, "init", "init", True, "system", "{{setvar::mood::calm}}{{// hidden}}"),
        PromptEntry(1, "rules", "rules", True, "system", "mood={{getvar::mood}} user={{user}} <Story setting>"),
        PromptEntry(2, "chatHistory", "Chat History", True, "system", "", marker=True, system_prompt=True),
        PromptEntry(3, "assistant-tail", "tail", True, "assistant", "<draft_notes>tail instruction</draft_notes>"),
        PromptEntry(4, "post-tail-system", "post", True, "system", "still system"),
    ])
    profile = CoreProfile("preset-1", "sha-1", {})

    rendered = render_tgbreak(
        preset,
        profile,
        {"user": "玩家", "Story setting": "setting"},
        chat_history="history",
        user_message="本轮要求",
    )

    assert [message.role for message in rendered.messages] == [
        "system", "system", "system", "system", "user", "assistant"
    ]
    assert rendered.messages[0].content == ""
    assert "hidden" not in rendered.messages[0].content
    assert rendered.messages[1].content == "mood=calm user=玩家 setting"
    assert rendered.messages[2].source == "chat_history"
    assert rendered.messages[2].content == "history"
    assert rendered.messages[-1].role == "assistant"
    assert rendered.messages[-1].source_identifier == "assistant-tail"
    assert rendered.unresolved_macros == []
    assert rendered.entry_evaluation_order == [
        "init", "rules", "chatHistory", "assistant-tail", "post-tail-system"
    ]


def test_profile_override_can_disable_source_enabled_and_enable_source_disabled():
    from app.tgbreak.models import CoreProfile, PromptEntry
    from app.tgbreak.renderer import render_tgbreak

    preset = _preset([
        PromptEntry(0, "on", "on", True, "system", "on"),
        PromptEntry(1, "off", "off", False, "system", "off"),
    ])
    profile = CoreProfile(
        "preset-1",
        "sha-1",
        {"on": {"enabled": False}, "off": {"enabled": True}},
    )

    rendered = render_tgbreak(preset, profile, {})

    assert [message.content for message in rendered.messages] == ["off"]
    assert rendered.resolved_entry_identifiers == ["off"]


def test_unresolved_getvar_is_a_render_failure():
    from app.tgbreak.models import CoreProfile, PromptEntry
    from app.tgbreak.renderer import TgbreakRenderError, render_tgbreak

    preset = _preset([
        PromptEntry(0, "bad", "bad", True, "system", "{{getvar::missing}}"),
    ])

    with pytest.raises(TgbreakRenderError) as exc_info:
        render_tgbreak(preset, CoreProfile("preset-1", "sha-1", {}), {})

    assert "{{getvar::missing}}" in exc_info.value.unresolved_macros


def test_core_profile_uses_only_present_audited_identifiers():
    from app.tgbreak.models import PromptEntry
    from app.tgbreak.profile import build_tgbreak_core_profile

    preset = _preset([
        PromptEntry(0, "5fde60e9-5a2d-4105-8123-39b5266cf7a8", "head", True, "system", "head"),
        PromptEntry(1, "f57ada5f-4999-426b-b260-f9c0aa0b9ead", "w2g", True, "system", "w2g"),
        PromptEntry(2, "not-in-real-source", "fixture", True, "system", "fixture"),
    ])

    profile = build_tgbreak_core_profile(preset)

    assert profile.entry_overrides == {
        "5fde60e9-5a2d-4105-8123-39b5266cf7a8": {"enabled": True},
        "f57ada5f-4999-426b-b260-f9c0aa0b9ead": {"enabled": False},
    }
