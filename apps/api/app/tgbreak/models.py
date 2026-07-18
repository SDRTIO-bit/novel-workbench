from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptEntry:
    array_index: int
    identifier: str
    name: str
    enabled: bool
    role: str
    content: str
    system_prompt: bool = False
    marker: bool = False
    injection_position: int = 0
    injection_depth: int = 0
    injection_order: int = 0
    injection_trigger: Any = field(default_factory=list)
    forbid_overrides: bool = False


@dataclass(frozen=True)
class PresetMetadata:
    preset_id: str
    source_path: str
    source_sha256: str
    file_size: int
    source_format_version: str
    top_level_keys: list[str]
    unsupported_fields: list[str]
    parse_mode: str
    standard_json_parse_error: dict[str, Any] | None = None


@dataclass(frozen=True)
class ImportedPreset:
    metadata: PresetMetadata
    entries: list[PromptEntry]

    @property
    def preset_id(self) -> str:
        return self.metadata.preset_id

    @property
    def source_sha256(self) -> str:
        return self.metadata.source_sha256


@dataclass(frozen=True)
class CoreProfile:
    source_preset_id: str
    source_sha256: str
    entry_overrides: dict[str, dict[str, bool]]


@dataclass(frozen=True)
class RenderedMessage:
    role: str
    content: str
    source_identifier: str | None = None
    source: str | None = None

    def as_dict(self) -> dict[str, str]:
        result = {"role": self.role, "content": self.content}
        if self.source_identifier is not None:
            result["source_identifier"] = self.source_identifier
        if self.source is not None:
            result["source"] = self.source
        return result


@dataclass(frozen=True)
class RenderedPreset:
    messages: list[RenderedMessage]
    unresolved_macros: list[str]
    resolved_variables: dict[str, str]
    entry_evaluation_order: list[str]
    source_preset_id: str
    source_preset_sha256: str
    resolved_entry_identifiers: list[str]
    draft_notes_required: bool

    @property
    def debug(self) -> dict[str, Any]:
        return {
            "unresolved_macros": self.unresolved_macros,
            "resolved_variables": self.resolved_variables,
            "entry_evaluation_order": self.entry_evaluation_order,
        }


@dataclass(frozen=True)
class TgbreakOutput:
    raw_response: str
    draft_notes: str
    draft_text: str
    extra_modules: list[str]
    source_preset_id: str
    source_preset_sha256: str
    resolved_entry_identifiers: list[str]
    requested_reasoning_mode: str = "disabled"
    reasoning_tokens: int | None = None


def source_path_value(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())
