"""Tests for Delta-Aware Echo Guard (Lane C).

Covers:
- Case E1: Pure acknowledgement without new proposition -> filtered (NOOP_LONG_TERM)
- Case E2: Assistant echo + genuinely new user delta -> delta preserved
- Case E3: Parroting without contrast -> filtered (NOOP_LONG_TERM)
- Fence extraction: <!-- COEVA_ECHO_FENCE: ... -->
- Punctuation & prefix stripping
"""

from __future__ import annotations

from src.memory.v2.echo_guard import EchoGuard


def test_no_echo_context() -> None:
    guard = EchoGuard()
    res = guard.inspect("我的主显示器换成了 4K 144Hz 的 LG 27GP95R。")
    assert not res.has_echo_context
    assert not res.is_pure_echo
    assert res.delta_text == "我的主显示器换成了 4K 144Hz 的 LG 27GP95R。"


def test_case_e1_pure_acknowledgement() -> None:
    guard = EchoGuard()
    # Typical assistant proposition
    echo_prop = "你之前提到过偏好深色主题对吧？"

    # Variations of pure ack
    for ack in ["嗯，你说得对。", "对啊", "是的，没错", "确实是这样", "好的！", "ok, yes"]:
        res = guard.inspect(ack, echo_prop)
        assert res.has_echo_context
        assert res.is_pure_echo, f"Expected pure echo for: {ack}"
        assert res.delta_text is None


def test_case_e2_echo_with_contrast_delta() -> None:
    guard = EchoGuard()
    echo_prop = "你之前提到过偏好深色主题对吧？"
    user_reply = "嗯，不过现在改用浅色主题确实看久了更舒服。"

    res = guard.inspect(user_reply, echo_prop)
    assert res.has_echo_context
    assert not res.is_pure_echo
    assert res.has_contrast_marker
    assert res.delta_text is not None
    assert "改用浅色主题" in res.delta_text
    assert not res.delta_text.startswith("嗯")


def test_case_e2_echo_with_conditional_delta() -> None:
    guard = EchoGuard()
    echo_prop = "所以你更喜欢先定框架？"
    user_reply = "对，不过只在复杂项目里，简单东西直接做。"

    res = guard.inspect(user_reply, echo_prop)
    assert res.has_echo_context
    assert not res.is_pure_echo
    assert res.delta_text is not None
    assert "只在复杂项目里" in res.delta_text


def test_case_e3_parroting_without_delta() -> None:
    guard = EchoGuard()
    echo_prop = "你之前提到过偏好深色主题对吧？"
    user_reply = "对啊，我之前是提到过偏好深色主题。"

    res = guard.inspect(user_reply, echo_prop)
    assert res.has_echo_context
    assert res.is_pure_echo
    assert res.delta_text is None
    assert res.overlap_ratio >= 0.70


def test_embedded_fence_extraction() -> None:
    guard = EchoGuard()
    fenced_content = (
        "<!-- COEVA_ECHO_FENCE: 你之前提到过偏好深色主题对吧？ -->\n"
        "嗯，不过现在改用浅色主题看久了更舒服。"
    )

    res = guard.inspect(fenced_content)
    assert res.has_echo_context
    assert not res.is_pure_echo
    assert res.delta_text is not None
    assert "改用浅色主题" in res.delta_text
