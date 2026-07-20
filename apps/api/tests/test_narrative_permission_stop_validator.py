"""Contract tests for the permission/stop deterministic output validator.

High-confidence literal checks only; everything else must be reported as
manual_review_required, never counted. Phase 1, tests first.
"""
from app.services.narrative_permission_stop_validator import (
    MANUAL_REVIEW_DIMENSIONS,
    validate_permission_stop,
)


def test_character_count():
    text = "正文一\n\n正文二"
    result = validate_permission_stop(text, stop_marker="")
    assert result.character_count == len(text)


def test_banned_sentences_hit_and_miss():
    hit = validate_permission_stop("他不知道的是，她早就看穿了。", stop_marker="")
    assert "NARRATOR_OMNISCIENT_REVEAL" in hit.validator_codes
    clean = validate_permission_stop("他把杯子放回桌上。", stop_marker="")
    assert clean.validator_codes == []


def test_all_banned_families_detected():
    text = "其实她早就知道了。实际上对方只是路过。她不知道的是，门没锁。"
    result = validate_permission_stop(text, stop_marker="")
    assert "NARRATOR_BACKSTAGE_FACT" in result.validator_codes
    assert "NARRATOR_TRUE_MOTIVE_REDUCE" in result.validator_codes
    assert "NARRATOR_OMNISCIENT_REVEAL" in result.validator_codes
    assert "其实她早就" in result.banned_sentence_hits["NARRATOR_BACKSTAGE_FACT"]


def test_second_confirmation_patterns():
    for text in ("两个人都没动。", "谁也没有离开。", "他没有松手。", "她也没有退开。"):
        result = validate_permission_stop(text, stop_marker="")
        assert "SECOND_CONFIRMATION_ENDING" in result.validator_codes, text
    clean = validate_permission_stop("他转身走了。", stop_marker="")
    assert "SECOND_CONFIRMATION_ENDING" not in clean.validator_codes


def test_environment_coda_tail_only():
    tail_hit = validate_permission_stop("他把伞收好。\n\n雨还在下。", stop_marker="")
    assert "FINAL_ENVIRONMENT_CODA" in tail_hit.validator_codes
    mid_only = validate_permission_stop(
        "雨还在下，他冲进楼道。\n\n他把伞递过去。", stop_marker=""
    )
    assert "FINAL_ENVIRONMENT_CODA" not in mid_only.validator_codes


def test_stop_marker_hit_position_and_post_stop_count():
    text = "他把水壶放回架子上。转身离开。"
    marker = "水壶放回架子上"
    result = validate_permission_stop(text, stop_marker=marker)
    assert result.stop_marker_first_char == text.find(marker)
    assert result.post_stop_character_count == len(text) - (
        result.stop_marker_first_char + len(marker)
    )
    assert "STOP_MARKER_LITERAL_HIT" in result.validator_codes


def test_stop_marker_miss_records_none():
    result = validate_permission_stop("正文", stop_marker="不存在的事实")
    assert result.stop_marker_first_char is None
    assert result.post_stop_character_count is None
    assert "STOP_MARKER_LITERAL_MISS" in result.validator_codes


def test_empty_stop_marker_is_not_a_hit():
    result = validate_permission_stop("正文", stop_marker="")
    assert result.stop_marker_first_char is None
    assert result.post_stop_character_count is None
    assert "STOP_MARKER_LITERAL_HIT" not in result.validator_codes
    assert "STOP_MARKER_LITERAL_MISS" not in result.validator_codes


def test_manual_review_dimensions_always_present():
    result = validate_permission_stop("他把水壶放回架子上。", stop_marker="水壶放回架子上")
    for dim in (
        "viewpoint_violation",
        "cross_mind_assertion",
        "other_character_motive_as_fact",
        "true_stop_state_position",
        "visible_state_transition_count",
    ):
        assert dim in result.manual_review_required
    assert result.manual_review_required == list(MANUAL_REVIEW_DIMENSIONS)


def test_never_raises_on_garbage_input():
    assert validate_permission_stop("", stop_marker="").character_count == 0
    assert validate_permission_stop("", stop_marker="x").stop_marker_first_char is None
    assert validate_permission_stop("\n\n\n", stop_marker="").validator_codes == []


def test_validation_is_deterministic():
    one = validate_permission_stop("样本正文", stop_marker="样")
    two = validate_permission_stop("样本正文", stop_marker="样")
    assert one == two


def test_tempo_flag_is_passed_through_not_derived():
    flagged = validate_permission_stop(
        "任意", stop_marker="", tempo_final_line_mismatch=True
    )
    assert flagged.tempo_final_line_mismatch is True
    clean = validate_permission_stop(
        "任意", stop_marker="", tempo_final_line_mismatch=False
    )
    assert clean.tempo_final_line_mismatch is False
