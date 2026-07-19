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
