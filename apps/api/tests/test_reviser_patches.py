import pytest

from app.services.reviser_patches import PatchApplicationError, apply_reviser_patches


def test_server_applies_patch_and_calculates_text():
    result = apply_reviser_patches(
        "甲。\n\n乙。\n\n丙。\n\n丁。\n\n戊。",
        [{"paragraph_id": "P002", "operation": "replace", "replacement": "乙改。"}],
        {},
    )
    assert result.text == "甲。\n\n乙改。\n\n丙。\n\n丁。\n\n戊。"
    assert result.unchanged_ratio >= 0.8


def test_server_rejects_patch_against_protected_strength():
    with pytest.raises(PatchApplicationError, match="REVISER_PATCH_PROTECTED"):
        apply_reviser_patches(
            "甲。\n\n乙。\n\n丙。\n\n丁。\n\n戊。",
            [{"paragraph_id": "P002", "operation": "replace", "replacement": "乙改。"}],
            {"protected_strengths": [{"paragraph_ids": ["P002"]}]},
        )


def test_error_carries_stable_machine_readable_code():
    with pytest.raises(PatchApplicationError) as exc_info:
        apply_reviser_patches(
            "甲。",
            [{"paragraph_id": "P002", "operation": "replace", "replacement": "乙。"}],
            {},
        )
    assert exc_info.value.code == "REVISER_PATCH_INVALID"
    assert str(exc_info.value).startswith("REVISER_PATCH_INVALID: ")


def test_delete_and_insert_after_operations():
    result = apply_reviser_patches(
        "ABCDEFGHIJ\n\nABCDEFGHIJ\n\nABCDEFGHIJ\n\nABCDEFGHIJ\n\nABCDEFGHIJ",
        [{"paragraph_id": "P002", "operation": "delete", "replacement": ""}],
        {},
    )
    assert result.text == "ABCDEFGHIJ\n\nABCDEFGHIJ\n\nABCDEFGHIJ\n\nABCDEFGHIJ"
    assert result.changed_paragraph_ids == ["P002"]

    result = apply_reviser_patches(
        "ABCDEFGHIJ\n\nABCDEFGHIJ",
        [{"paragraph_id": "P001", "operation": "insert_after", "replacement": "KLM"}],
        {},
    )
    assert result.text == "ABCDEFGHIJ\n\nKLM\n\nABCDEFGHIJ"


def test_duplicate_target_rejected():
    with pytest.raises(PatchApplicationError, match="duplicate target"):
        apply_reviser_patches(
            "甲。\n\n乙。",
            [
                {"paragraph_id": "P001", "operation": "replace", "replacement": "甲一。"},
                {"paragraph_id": "P001", "operation": "replace", "replacement": "甲二。"},
            ],
            {},
        )


def test_whole_text_rewrite_fails_unchanged_ratio():
    with pytest.raises(PatchApplicationError) as exc_info:
        apply_reviser_patches(
            "甲。\n\n乙。\n\n丙。\n\n丁。",
            [
                {"paragraph_id": "P001", "operation": "replace", "replacement": "彻底重写的全新第一段，内容完全不一样了。"},
                {"paragraph_id": "P002", "operation": "replace", "replacement": "彻底重写的全新第二段，内容完全不一样了。"},
                {"paragraph_id": "P003", "operation": "replace", "replacement": "彻底重写的全新第三段，内容完全不一样了。"},
                {"paragraph_id": "P004", "operation": "replace", "replacement": "彻底重写的全新第四段，内容完全不一样了。"},
            ],
            {},
        )
    assert exc_info.value.code == "REVISER_PATCH_UNCHANGED_RATIO"


def test_empty_patches_is_byte_identical_noop():
    result = apply_reviser_patches("甲。\n\n乙。", [], {})
    assert result.text == "甲。\n\n乙。"
    assert result.unchanged_ratio == 1.0
    assert result.changed_paragraph_ids == []
