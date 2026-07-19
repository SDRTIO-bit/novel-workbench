"""Narrative route output validation.

Post-generation text checks that record violations WITHOUT retrying, filtering,
or preventing the original text from being saved.  Validation results are
experiment metadata only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Error codes ─────────────────────────────────────────────────────

B_SHORT_LENGTH_OUT_OF_RANGE = "B_SHORT_LENGTH_OUT_OF_RANGE"
B_SHORT_SECOND_CONFIRMATION = "B_SHORT_SECOND_CONFIRMATION"
B_SHORT_STOP_OVERRUN = "B_SHORT_STOP_OVERRUN"
ROUTE_REQUIRED_EVENT_NOT_REALIZED = "ROUTE_REQUIRED_EVENT_NOT_REALIZED"


# ── Validation note ─────────────────────────────────────────────────


@dataclass
class ValidationNote:
    error_code: str
    message: str
    route_name: str
    details: dict = field(default_factory=dict)


# ── Per-route validators ───────────────────────────────────────────


def _validate_b_short(text: str, compiled_brief: dict) -> list[ValidationNote]:
    notes: list[ValidationNote] = []

    # Length check
    char_count = len(text)
    if char_count < 350 or char_count > 550:
        notes.append(ValidationNote(
            error_code=B_SHORT_LENGTH_OUT_OF_RANGE,
            message=f"B_SHORT_RELATION text length {char_count} is outside [350, 550]",
            route_name="B_SHORT_RELATION",
            details={"char_count": char_count, "min": 350, "max": 550},
        ))

    # Second-confirmation check
    second_confirmations = [
        "双方都没走",
        "空气安静",
        "距离更近",
        "他没有松手",
        "她也没有退开",
        "两个人都没动",
        "谁也没有离开",
        "谁都",
        "谁也没",
    ]
    found = [p for p in second_confirmations if p in text]
    if found:
        notes.append(ValidationNote(
            error_code=B_SHORT_SECOND_CONFIRMATION,
            message=f"B_SHORT_RELATION text contains forbidden second-confirmation: {found}",
            route_name="B_SHORT_RELATION",
            details={"forbidden_patterns": found},
        ))

    # Stop overrun: if text keeps going after clear stop point
    # (basic heuristic: paragraph count, if more than 5 paragraphs in B-short,
    #  likely overshot)
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) > 6:
        notes.append(ValidationNote(
            error_code=B_SHORT_STOP_OVERRUN,
            message=f"B_SHORT_RELATION text has {len(paragraphs)} paragraphs, may overshoot stop point",
            route_name="B_SHORT_RELATION",
            details={"paragraph_count": len(paragraphs)},
        ))

    return notes


def _validate_b_physical(text: str, compiled_brief: dict) -> list[ValidationNote]:
    notes: list[ValidationNote] = []

    # Check that the text contains a failure — at minimum, some word indicating
    # the first attempt didn't work
    failure_words = ["冲开", "掉下来", "失败", "没封住", "没用", "不行", "不管用",
                     "漏得更", "更大了", "反而", "却", "可还是", "但", "可是"]
    first_attempt = compiled_brief.get("first_attempt", "")
    if first_attempt and not any(fw in text for fw in failure_words):
        # Not conclusive, but flag it
        notes.append(ValidationNote(
            error_code=ROUTE_REQUIRED_EVENT_NOT_REALIZED,
            message="B_PHYSICAL_PROBLEM text may not show failed first attempt",
            route_name="B_PHYSICAL_PROBLEM",
            details={"first_attempt_in_brief": first_attempt},
        ))

    return notes


# ── Main validator ──────────────────────────────────────────────────


def validate_route_output(
    text: str,
    route_name: str,
    compiled_brief: dict | None = None,
) -> list[ValidationNote]:
    """Validate generated text against the route contract.

    Returns a list of ValidationNote — empty list means all checks passed.
    Never raises exceptions.  Unknown routes return empty list.
    """
    brief = compiled_brief if isinstance(compiled_brief, dict) else {}
    notes: list[ValidationNote] = []

    if route_name == "B_SHORT_RELATION":
        notes.extend(_validate_b_short(text, brief))
    elif route_name == "B_PHYSICAL_PROBLEM":
        notes.extend(_validate_b_physical(text, brief))
    # Additional route validators can be added here

    return notes
