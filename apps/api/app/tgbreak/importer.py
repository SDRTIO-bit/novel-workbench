import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from app.tgbreak.models import ImportedPreset, PresetMetadata, PromptEntry, source_path_value


SUPPORTED_TOP_LEVEL_FIELDS = {"prompts", "version", "preset_version", "format_version"}
SUPPORTED_PROMPT_FIELDS = {
    "identifier",
    "name",
    "enabled",
    "role",
    "content",
    "system_prompt",
    "marker",
    "injection_position",
    "injection_depth",
    "injection_order",
    "injection_trigger",
    "forbid_overrides",
}


class SillyTavernImportError(ValueError):
    pass


def _parse_json(raw_text: str) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    try:
        return json.loads(raw_text), "standard_json", None
    except json.JSONDecodeError as exc:
        error = {
            "message": exc.msg,
            "line": exc.lineno,
            "column": exc.colno,
            "char": exc.pos,
        }

        # The supplied local preset is truncated after the final prompt object.
        # This repair is deliberately narrow and remains in memory only.
        candidate = re.sub(r",\s*$", "", raw_text) + "\n]}"
        try:
            return (
                json.loads(candidate),
                "in_memory_remove_terminal_array_comma_append_missing_array_and_object_closers",
                error,
            )
        except json.JSONDecodeError as repair_exc:
            raise SillyTavernImportError(
                "PRESET_JSON_INVALID: "
                f"standard parse failed at line {exc.lineno}, column {exc.colno}; "
                f"in-memory repair failed at line {repair_exc.lineno}, column {repair_exc.colno}"
            ) from repair_exc


def _string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


def import_sillytavern_preset(source_path: str | Path) -> ImportedPreset:
    path = Path(source_path).expanduser()
    if not path.exists():
        raise SillyTavernImportError(f"PRESET_SOURCE_NOT_FOUND: {path}")
    if not path.is_file():
        raise SillyTavernImportError(f"PRESET_SOURCE_NOT_FILE: {path}")

    raw = path.read_bytes()
    if not raw:
        raise SillyTavernImportError(f"PRESET_SOURCE_EMPTY: {path}")

    source_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        raw_text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SillyTavernImportError(f"PRESET_ENCODING_INVALID: {path}") from exc

    payload, parse_mode, standard_error = _parse_json(raw_text)
    if not isinstance(payload, dict) or not payload:
        raise SillyTavernImportError("PRESET_ROOT_INVALID: expected a non-empty object")
    prompts = payload.get("prompts")
    if not isinstance(prompts, list):
        raise SillyTavernImportError("PRESET_PROMPTS_INVALID: top-level prompts must be an array")

    unsupported_fields = [
        key for key in payload.keys() if key not in SUPPORTED_TOP_LEVEL_FIELDS
    ]
    entries: list[PromptEntry] = []
    for index, item in enumerate(prompts):
        if not isinstance(item, dict):
            raise SillyTavernImportError(f"PRESET_PROMPT_INVALID: prompts[{index}] must be an object")
        unsupported_fields.extend(
            f"prompts[{index}].{key}"
            for key in item.keys()
            if key not in SUPPORTED_PROMPT_FIELDS
        )
        entries.append(
            PromptEntry(
                array_index=index,
                identifier=_string(item.get("identifier")),
                name=_string(item.get("name")),
                enabled=item.get("enabled") is True,
                role=_string(item.get("role"), "system"),
                content=_string(item.get("content")),
                system_prompt=item.get("system_prompt") is True,
                marker=item.get("marker") is True,
                injection_position=int(item.get("injection_position", 0) or 0),
                injection_depth=int(item.get("injection_depth", 0) or 0),
                injection_order=int(item.get("injection_order", 0) or 0),
                injection_trigger=item.get("injection_trigger", []),
                forbid_overrides=item.get("forbid_overrides") is True,
            )
        )

    source_format_version = _string(
        payload.get("version", payload.get("preset_version", payload.get("format_version", "unknown"))),
        "unknown",
    )
    preset_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"novel-workbench:tgbreak:{source_sha256}"))
    metadata = PresetMetadata(
        preset_id=preset_id,
        source_path=source_path_value(path),
        source_sha256=source_sha256,
        file_size=len(raw),
        source_format_version=source_format_version,
        top_level_keys=list(payload.keys()),
        unsupported_fields=unsupported_fields,
        parse_mode=parse_mode,
        standard_json_parse_error=standard_error,
    )
    return ImportedPreset(metadata=metadata, entries=entries)
