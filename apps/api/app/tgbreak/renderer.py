import re
from collections.abc import Mapping

from app.tgbreak.models import (
    CoreProfile,
    ImportedPreset,
    RenderedMessage,
    RenderedPreset,
)


_SETVAR_RE = re.compile(r"\{\{setvar::([^:}]+)::(.*?)\}\}", re.DOTALL)
_GETVAR_RE = re.compile(r"\{\{getvar::([^}]+)\}\}")
_COMMENT_RE = re.compile(r"\{\{//.*?\}\}", re.DOTALL)
_UNRESOLVED_RE = re.compile(r"\{\{(?:getvar|setvar)::[^}]*")


class TgbreakRenderError(ValueError):
    def __init__(self, message: str, unresolved_macros: list[str] | None = None):
        self.unresolved_macros = unresolved_macros or []
        super().__init__(message)


def adapt_project_variables(
    *,
    project_documents: str = "",
    session_summary: str = "",
    recent_chapters: str = "",
    current_chapter_text: str = "",
    previous_writer_output: str = "",
    scene_instruction: str = "",
    user: str = "",
    char: str = "",
    scenario: str = "",
    personality: str = "",
) -> dict[str, str]:
    interaction_record = "\n\n".join(value for value in (session_summary, recent_chapters) if value)
    ai_last_output = current_chapter_text or previous_writer_output
    return {
        "Story setting": project_documents,
        "story_setting": project_documents,
        "project_documents": project_documents,
        "interaction_record": interaction_record,
        "ai_last_output": ai_last_output,
        "current_chapter_text": current_chapter_text,
        "previous_writer_output": previous_writer_output,
        "peip": scene_instruction,
        "scene_instruction": scene_instruction,
        "user": user,
        "char": char,
        "scenario": scenario,
        "personality": personality,
    }


def _external_replace(content: str, variables: Mapping[str, object]) -> str:
    aliases = {
        "Story setting": ("Story setting", "story_setting", "project_documents"),
        "interaction_record": ("interaction_record",),
        "ai_last_output": ("ai_last_output", "current_chapter_text", "previous_writer_output"),
        "peip": ("peip", "scene_instruction"),
        "user": ("user",),
        "char": ("char",),
        "scenario": ("scenario",),
        "personality": ("personality",),
    }
    result = content
    for token, names in aliases.items():
        value = next((variables[name] for name in names if name in variables), "")
        value = "" if value is None else str(value)
        for placeholder in (f"<{token}>", f"{{{{{token}}}}}"):
            result = result.replace(placeholder, value)
    for name, value in variables.items():
        if isinstance(name, str) and isinstance(value, (str, int, float)):
            result = result.replace("{{" + name + "}}", str(value))
    return result


def _render_entry(content: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    working = _external_replace(content, variables)

    def write_variable(match: re.Match[str]) -> str:
        variables[match.group(1).strip()] = _external_replace(match.group(2), variables)
        return ""

    working = _SETVAR_RE.sub(write_variable, working)
    working = _COMMENT_RE.sub("", working)
    unresolved: list[str] = []

    def read_variable(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if name in variables:
            return variables[name]
        token = match.group(0)
        unresolved.append(token)
        return token

    working = _GETVAR_RE.sub(read_variable, working)
    working = _external_replace(working, variables)
    unresolved.extend(_UNRESOLVED_RE.findall(working))
    return working, list(dict.fromkeys(unresolved))


def render_tgbreak(
    preset: ImportedPreset,
    profile: CoreProfile,
    variables: Mapping[str, object],
    *,
    chat_history: str = "",
    user_message: str | None = None,
) -> RenderedPreset:
    if profile.source_preset_id != preset.preset_id or profile.source_sha256 != preset.source_sha256:
        raise TgbreakRenderError("PROFILE_SOURCE_MISMATCH: profile does not belong to this preset")

    resolved_variables = {
        str(key): "" if value is None else str(value) for key, value in variables.items()
    }
    selected_entries = []
    unresolved: list[str] = []
    evaluation_order: list[str] = []
    resolved_identifiers: list[str] = []
    draft_notes_required = False

    for entry in preset.entries:
        override = profile.entry_overrides.get(entry.identifier, {})
        enabled = override.get("enabled", entry.enabled)
        if not enabled:
            continue
        rendered_content, entry_unresolved = _render_entry(entry.content, resolved_variables)
        unresolved.extend(entry_unresolved)
        evaluation_order.append(entry.identifier)
        resolved_identifiers.append(entry.identifier)
        draft_notes_required = draft_notes_required or "draft_notes" in entry.content.lower()
        selected_entries.append((entry, rendered_content))

    if unresolved:
        raise TgbreakRenderError(
            "UNRESOLVED_MACRO: TGbreak rendering left unresolved macros",
            list(dict.fromkeys(unresolved)),
        )

    pre_user: list[RenderedMessage] = []
    assistants: list[RenderedMessage] = []
    for entry, content in selected_entries:
        if entry.identifier == "chatHistory" or entry.name == "Chat History":
            pre_user.append(
                RenderedMessage(
                    role="system",
                    source="chat_history",
                    source_identifier=entry.identifier,
                    content=chat_history,
                )
            )
            continue
        message = RenderedMessage(
            role=entry.role,
            source_identifier=entry.identifier,
            content=content,
        )
        if entry.role == "assistant" and "draft_notes" in entry.content.lower():
            assistants.append(message)
        else:
            pre_user.append(message)

    messages = list(pre_user)
    if user_message is not None:
        messages.append(RenderedMessage(role="user", source="user_input", content=user_message))
    messages.extend(assistants)
    return RenderedPreset(
        messages=messages,
        unresolved_macros=[],
        resolved_variables=dict(resolved_variables),
        entry_evaluation_order=evaluation_order,
        source_preset_id=preset.preset_id,
        source_preset_sha256=preset.source_sha256,
        resolved_entry_identifiers=resolved_identifiers,
        draft_notes_required=draft_notes_required,
    )
