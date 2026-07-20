"""Deterministic post-generation checks for NARRATIVE_PERMISSION_STOPPING_FACTORIAL_V1.

High-confidence literal checks only: character count, explicit banned
sentences, explicit second-confirmation endings, explicit environment coda
(tail only), stop-marker literal hit and post-stop character count.

Dimensions that cannot be judged deterministically — viewpoint violations,
cross-mind assertions, other-motive-as-fact, the *true* stop_state
satisfaction position, visible state transition counts, relationship/meaning
summaries, shared-atmosphere declarations, backstage-fact corrections — are
reported as ``manual_review_required`` on every draft.  They are never
counted, scored, or inferred.

Results are experiment metadata only.  Nothing here retries, filters, or
prevents the original text from being saved or submitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Observation codes ─────────────────────────────────────────────────

NARRATOR_OMNISCIENT_REVEAL = "NARRATOR_OMNISCIENT_REVEAL"
NARRATOR_BACKSTAGE_FACT = "NARRATOR_BACKSTAGE_FACT"
NARRATOR_TRUE_MOTIVE_REDUCE = "NARRATOR_TRUE_MOTIVE_REDUCE"
SECOND_CONFIRMATION_ENDING = "SECOND_CONFIRMATION_ENDING"
FINAL_ENVIRONMENT_CODA = "FINAL_ENVIRONMENT_CODA"
STOP_MARKER_LITERAL_HIT = "STOP_MARKER_LITERAL_HIT"
STOP_MARKER_LITERAL_MISS = "STOP_MARKER_LITERAL_MISS"

# Dimensions deferred to human review on every single draft.  A literal
# marker hit does NOT promote true_stop_state_position out of this list:
# a substring match is not proof the stop_state was truly satisfied there.
MANUAL_REVIEW_DIMENSIONS = (
    "viewpoint_violation",
    "cross_mind_assertion",
    "other_character_motive_as_fact",
    "true_stop_state_position",
    "visible_state_transition_count",
    "relationship_or_meaning_summary",
    "shared_atmosphere_declaration",
    "narrator_correction_with_backstage_fact",
)

# Explicit literal pattern families.  Precision over recall: misses are
# acceptable (manual review covers them), false positives are not.
_BANNED_PATTERNS: dict[str, tuple[str, ...]] = {
    NARRATOR_OMNISCIENT_REVEAL: ("他不知道的是", "她不知道的是"),
    NARRATOR_BACKSTAGE_FACT: ("其实他早就", "其实她早就"),
    NARRATOR_TRUE_MOTIVE_REDUCE: ("实际上对方只是",),
}

_SECOND_CONFIRMATION_PATTERNS: tuple[str, ...] = (
    "双方都没走",
    "两个人都没动",
    "谁也没有离开",
    "他没有松手",
    "她也没有退开",
    "他也没有走",
    "她也没有走",
)

# Checked against the final non-empty paragraph only — environment
# description mid-text is legitimate narration, only a trailing coda is the
# measured behaviour.
_ENVIRONMENT_CODA_PATTERNS: tuple[str, ...] = (
    "空气安静",
    "雨还在下",
    "灯还亮着",
    "夜色",
    "距离更近",
)


@dataclass(frozen=True)
class PermissionStopValidation:
    """One draft's deterministic validation record."""

    character_count: int
    validator_codes: list[str]
    banned_sentence_hits: dict[str, list[str]]
    second_confirmation_hits: list[str]
    environment_coda_hits: list[str]
    stop_marker_first_char: int | None
    post_stop_character_count: int | None
    tempo_final_line_mismatch: bool
    manual_review_required: list[str] = field(
        default_factory=lambda: list(MANUAL_REVIEW_DIMENSIONS)
    )


def _final_paragraph(text: str) -> str:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return paragraphs[-1] if paragraphs else ""


def validate_permission_stop(
    text: str,
    *,
    stop_marker: str = "",
    tempo_final_line_mismatch: bool = False,
) -> PermissionStopValidation:
    """Run the deterministic checks.  Never raises, never judges beyond
    literal evidence."""
    codes: list[str] = []

    banned_hits = {
        code: [pattern for pattern in patterns if pattern in text]
        for code, patterns in _BANNED_PATTERNS.items()
    }
    banned_hits = {code: hits for code, hits in banned_hits.items() if hits}
    codes.extend(banned_hits)

    second_confirmation_hits = [
        pattern for pattern in _SECOND_CONFIRMATION_PATTERNS if pattern in text
    ]
    if second_confirmation_hits:
        codes.append(SECOND_CONFIRMATION_ENDING)

    final_paragraph = _final_paragraph(text)
    environment_coda_hits = [
        pattern for pattern in _ENVIRONMENT_CODA_PATTERNS if pattern in final_paragraph
    ]
    if environment_coda_hits:
        codes.append(FINAL_ENVIRONMENT_CODA)

    marker = stop_marker.strip()
    stop_marker_first_char: int | None = None
    post_stop_character_count: int | None = None
    if marker:
        position = text.find(marker)
        if position >= 0:
            stop_marker_first_char = position
            post_stop_character_count = len(text) - (position + len(marker))
            codes.append(STOP_MARKER_LITERAL_HIT)
        else:
            codes.append(STOP_MARKER_LITERAL_MISS)

    return PermissionStopValidation(
        character_count=len(text),
        validator_codes=codes,
        banned_sentence_hits=banned_hits,
        second_confirmation_hits=second_confirmation_hits,
        environment_coda_hits=environment_coda_hits,
        stop_marker_first_char=stop_marker_first_char,
        post_stop_character_count=post_stop_character_count,
        tempo_final_line_mismatch=tempo_final_line_mismatch,
    )
