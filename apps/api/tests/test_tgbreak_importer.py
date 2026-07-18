import hashlib
import json

import pytest


def _write_fixture(tmp_path, payload: str) -> str:
    path = tmp_path / "preset.json"
    path.write_text(payload, encoding="utf-8")
    return str(path)


def test_import_preserves_prompt_order_roles_and_source_sha(tmp_path):
    from app.tgbreak.importer import import_sillytavern_preset

    payload = {
        "version": "fixture-1",
        "temperature": 0.7,
        "prompts": [
            {
                "identifier": "first",
                "name": "First",
                "enabled": True,
                "role": "system",
                "content": "alpha",
                "system_prompt": True,
                "marker": False,
                "injection_position": 0,
                "injection_depth": 4,
                "injection_order": 100,
                "injection_trigger": [],
                "forbid_overrides": False,
            },
            {
                "identifier": "tail",
                "name": "Tail",
                "enabled": True,
                "role": "assistant",
                "content": "omega",
                "system_prompt": False,
                "marker": False,
                "injection_position": 0,
                "injection_depth": 4,
                "injection_order": 100,
                "injection_trigger": [],
                "forbid_overrides": False,
            },
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path = tmp_path / "preset.json"
    path.write_bytes(raw)

    imported = import_sillytavern_preset(path)

    assert imported.entries[0].identifier == "first"
    assert imported.entries[1].role == "assistant"
    assert [entry.array_index for entry in imported.entries] == [0, 1]
    assert imported.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert imported.metadata.source_format_version == "fixture-1"
    assert "temperature" in imported.metadata.unsupported_fields


def test_import_repairs_only_truncated_container_in_memory_and_leaves_source_unchanged(tmp_path):
    from app.tgbreak.importer import import_sillytavern_preset

    raw_text = '{"prompts": [{"identifier": "only", "name": "Only", "enabled": true, "role": "system", "content": "x"},\n'
    path = tmp_path / "truncated.json"
    path.write_text(raw_text, encoding="utf-8")
    before = path.read_bytes()

    imported = import_sillytavern_preset(path)

    assert imported.entries[0].identifier == "only"
    assert imported.metadata.parse_mode == "in_memory_remove_terminal_array_comma_append_missing_array_and_object_closers"
    assert path.read_bytes() == before


def test_import_reports_unsupported_prompt_fields_without_dropping_supported_fields(tmp_path):
    from app.tgbreak.importer import import_sillytavern_preset

    payload = {"prompts": [{
        "identifier": "entry",
        "name": "Entry",
        "enabled": True,
        "role": "system",
        "content": "body",
        "system_prompt": False,
        "marker": False,
        "injection_position": 0,
        "injection_depth": 4,
        "injection_order": 100,
        "injection_trigger": [],
        "forbid_overrides": False,
        "future_field": "preserve as unsupported",
    }]}
    path = tmp_path / "fields.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    imported = import_sillytavern_preset(path)

    assert imported.entries[0].content == "body"
    assert "prompts[0].future_field" in imported.metadata.unsupported_fields
