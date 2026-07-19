"""Server-side application of constrained Reviser patches."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


class PatchApplicationError(ValueError):
    """Reviser patch rejected by deterministic server-side validation.

    ``code`` carries the stable machine-readable error code so the pipeline
    can surface it on the failed candidate instead of a generic ``LLM_ERROR``.
    The string form stays ``"CODE: message"`` for backward-compatible matching.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class AppliedRevision:
    text: str
    unchanged_ratio: float
    changed_paragraph_ids: list[str]


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.strip().split("\n\n") if paragraph.strip()]


def _protected_ids(critic_report: dict[str, Any] | None) -> set[str]:
    report = critic_report if isinstance(critic_report, dict) else {}
    protected: set[str] = set()
    for strength in report.get("protected_strengths", []):
        if not isinstance(strength, dict):
            continue
        values = strength.get("paragraph_ids", strength.get("paragraph_id", []))
        if not isinstance(values, list):
            values = [values]
        protected.update(str(value).strip().upper() for value in values)
    return protected


def apply_reviser_patches(
    draft_text: str,
    patches: list[dict[str, Any]],
    critic_report: dict[str, Any] | None,
    *,
    minimum_unchanged_ratio: float = 0.8,
) -> AppliedRevision:
    """Validate and apply patches. The returned text is the sole revision truth."""
    paragraphs = _paragraphs(draft_text)
    if not paragraphs:
        raise PatchApplicationError("REVISER_PATCH_INVALID", "draft has no paragraphs")

    protected = _protected_ids(critic_report)
    seen: set[str] = set()
    validated: list[tuple[int, str, str, str]] = []
    for patch in patches:
        paragraph_id = str(patch.get("paragraph_id", "")).strip().upper()
        operation = str(patch.get("operation", "")).strip()
        replacement = str(patch.get("replacement", "")).strip()
        if not paragraph_id.startswith("P") or not paragraph_id[1:].isdigit():
            raise PatchApplicationError("REVISER_PATCH_INVALID", "paragraph_id must be a legal P### label")
        index = int(paragraph_id[1:]) - 1
        if index < 0 or index >= len(paragraphs):
            raise PatchApplicationError("REVISER_PATCH_INVALID", f"{paragraph_id} is outside the draft")
        if paragraph_id in protected:
            raise PatchApplicationError("REVISER_PATCH_PROTECTED", f"{paragraph_id} is protected")
        if paragraph_id in seen:
            raise PatchApplicationError("REVISER_PATCH_INVALID", f"duplicate target {paragraph_id}")
        if operation not in {"replace", "delete", "insert_after"}:
            raise PatchApplicationError("REVISER_PATCH_INVALID", f"unsupported operation {operation}")
        if operation != "delete" and not replacement:
            raise PatchApplicationError("REVISER_PATCH_INVALID", "replacement is required")
        seen.add(paragraph_id)
        validated.append((index, paragraph_id, operation, replacement))

    result = list(paragraphs)
    offset = 0
    for index, _paragraph_id, operation, replacement in sorted(validated):
        actual = index + offset
        if operation == "replace":
            result[actual] = replacement
        elif operation == "delete":
            result.pop(actual)
            offset -= 1
        else:
            result.insert(actual + 1, replacement)
            offset += 1

    text = "\n\n".join(result)
    ratio = SequenceMatcher(None, draft_text.strip(), text).ratio()
    if ratio < minimum_unchanged_ratio:
        raise PatchApplicationError(
            "REVISER_PATCH_UNCHANGED_RATIO",
            f"{ratio:.3f} is below required {minimum_unchanged_ratio:.3f}",
        )
    return AppliedRevision(
        text=text,
        unchanged_ratio=ratio,
        changed_paragraph_ids=[paragraph_id for _, paragraph_id, _, _ in validated],
    )
