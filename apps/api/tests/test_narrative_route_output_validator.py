"""Failing tests for narrative route output validation.

These tests import narrative_route_output_validator which does not yet exist.
"""
import pytest

from app.services.narrative_route_output_validator import (
    validate_route_output,
    ValidationNote,
    B_SHORT_LENGTH_OUT_OF_RANGE,
    B_SHORT_SECOND_CONFIRMATION,
    B_SHORT_STOP_OVERRUN,
    ROUTE_REQUIRED_EVENT_NOT_REALIZED,
)


# ── B_SHORT_RELATION tests ─────────────────────────────────────────


def _b_short_valid_text() -> str:
    """A valid B-short text, exactly 400 chars — no forbidden patterns."""
    base = (
        "韩川把手机扣在桌上就去洗菜了。水已经开了，锅里冒着白汽。夏知盯着那台扣着的手机看了两秒，"
        "没去翻，也没等他回来。她把洗好的青菜倒进锅里，用筷子拨了两下。油星溅到手腕上，"
        "她缩了一下，但没出声。韩川转过身，看见锅里多了菜，又看了她一眼。"
        "夏知没看他，端起空菜筐往水槽走。两人的影子在水槽边碰了一下又分开。"
        "韩川把火调小了一点。锅里的声音低了下去。夏知洗了手，把擦手的毛巾挂回原来的钩子上。"
    )
    # Pad to exactly 400 chars
    padding_needed = 400 - len(base)
    return base + "。" * padding_needed


def _b_short_too_long_text() -> str:
    """A B-short text that exceeds 550 characters."""
    return "a" * 600


def _b_short_second_confirmation_text() -> str:
    """A B-short text that appends the forbidden second-confirmation tail."""
    return (
        "韩川把手机扣在桌上就去洗菜了。\n\n"
        "夏知盯着那台扣着的手机看了两秒。她把洗好的青菜倒进锅里。\n\n"
        "韩川转过身，看见锅里多了菜。两人都没说话。\n\n"
        "他没有再去拿手机。她也没有退开。\n\n"
        "空气安静下来。距离好像近了一点。"
    )


def test_b_short_valid_passes():
    notes = validate_route_output(_b_short_valid_text(), "B_SHORT_RELATION", {})
    assert len(notes) == 0


def test_b_short_too_long_triggers_error():
    notes = validate_route_output(_b_short_too_long_text(), "B_SHORT_RELATION", {})
    assert any(n.error_code == B_SHORT_LENGTH_OUT_OF_RANGE for n in notes)


def test_b_short_second_confirmation_triggers_error():
    notes = validate_route_output(_b_short_second_confirmation_text(), "B_SHORT_RELATION", {})
    assert any(n.error_code == B_SHORT_SECOND_CONFIRMATION for n in notes)


def test_b_short_no_error_for_non_relation_route():
    """B-short validator only activates for B_SHORT_RELATION route."""
    notes = validate_route_output(_b_short_too_long_text(), "C_OBJECT_CAUSAL", {})
    assert not any(n.error_code == B_SHORT_LENGTH_OUT_OF_RANGE for n in notes)


# ── B_PHYSICAL_PROBLEM tests ───────────────────────────────────────


def _physical_problem_valid_text() -> str:
    return (
        "水滴打在机房地板上，已经在插线板方向汇成了一条细线。\n\n"
        "魏临把拖把横在插线板前面，又从柜子里摸出那卷透明胶带。他踩着凳子，把胶带往天花板的裂缝上按。\n\n"
        "水珠从胶带边缘挤出来，啪嗒啪嗒落在他肩膀上。胶带被水冲开，整条掉了下来，砸在键盘上。\n\n"
        "魏临从凳子上下来，把总闸提示牌挂在了漏水点正下方的电脑屏幕上，然后拨了维修老师的号码。"
    )


def _physical_problem_no_failure_text() -> str:
    """Text where first attempt succeeds — violates B_PHYSICAL contract."""
    return (
        "魏临发现天花板漏水，立刻用胶带封住了裂缝。\n\n水不滴了。他擦干插线板旁边，继续上自习。"
    )


def test_physical_problem_valid_passes():
    notes = validate_route_output(_physical_problem_valid_text(), "B_PHYSICAL_PROBLEM", {})
    assert len(notes) == 0


def test_physical_problem_no_failure_triggers_error():
    notes = validate_route_output(
        _physical_problem_no_failure_text(),
        "B_PHYSICAL_PROBLEM",
        {"first_attempt": "用胶带封住裂缝"},
    )
    assert any(n.error_code == ROUTE_REQUIRED_EVENT_NOT_REALIZED for n in notes)


# ── D_FALLIBLE_TASK tests ──────────────────────────────────────────


def _d_task_valid_text() -> str:
    return (
        "陶然蹲下来，指着票面上的场次时间问小男孩：'你妈妈是在这个厅看电影？'\n\n"
        "小男孩点头又摇头，攥着那张湿透的票，手指头往电梯方向指了一下。\n\n"
        "陶然看了看保安——还在跟人解释退票流程。她没有再等，走过去按下了服务台的广播键。\n\n"
        "广播声响彻商场的瞬间，她看见保安转过头来瞪了她一眼。\n\n"
        "小男孩被广播声吓得往她身后躲。\n\n"
        "没有人来。电梯口的人流继续涌过去，一个戴眼镜的女人在出口处停下来，盯着手机看。"
    )


def test_d_task_valid_passes():
    notes = validate_route_output(_d_task_valid_text(), "D_FALLIBLE_TASK", {})
    assert len(notes) == 0


# ── Structural tests ───────────────────────────────────────────────


def test_validation_notes_have_all_required_fields():
    notes = validate_route_output(_b_short_too_long_text(), "B_SHORT_RELATION", {})
    for note in notes:
        assert isinstance(note, ValidationNote)
        assert isinstance(note.error_code, str)
        assert len(note.error_code) > 0
        assert isinstance(note.message, str)
        assert note.route_name == "B_SHORT_RELATION"


def test_validation_never_raises():
    """Validator must never raise — only return notes."""
    result = validate_route_output("", "B_SHORT_RELATION", {})
    assert isinstance(result, list)
    # Empty text should trigger validation but never crash


def test_unknown_route_skips_validation():
    """Non-existent route returns empty notes."""
    notes = validate_route_output("any text", "NONEXISTENT_ROUTE", {})
    assert len(notes) == 0
