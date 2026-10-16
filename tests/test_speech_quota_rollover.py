"""Tests for daily speech quota rollover.

The counter was only ever reset by `reset_day()`, which no production code
called. Once `allow_agent_bubble` started consuming the quota, a companion that
spent its 3 bubbles went permanently silent until the process restarted --
proved with the sequence reproduced in `test_quota_recovers_next_day` below.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.core.cold_start import ColdStartPolicy
from src.core.intervention import InterventionPolicy


def _local(day: int, hour: int) -> datetime:
    """A local-time datetime, since the quota rolls over on the local calendar day."""
    return datetime(2026, 10, day, hour, 0, 0)


def test_quota_rolls_over_at_the_next_calendar_day() -> None:
    """Spending the budget on one day must not silence the next day."""
    policy = ColdStartPolicy(day_count=30)  # mature: 3/day
    assert policy.daily_speech_quota == 3

    morning = _local(16, 9)
    assert policy.record_speech(now=morning)
    assert policy.record_speech(now=morning + timedelta(minutes=1))
    assert policy.record_speech(now=morning + timedelta(minutes=2))
    assert policy.speeches_today == 3
    assert not policy.can_speak(now=morning + timedelta(minutes=3))

    # Later the same evening: still spent.
    assert not policy.can_speak(now=_local(16, 23))

    # Next calendar day: the budget is back.
    tomorrow = _local(17, 8)
    assert policy.can_speak(now=tomorrow), "quota must reset on the next day"
    assert policy.speeches_today == 0
    assert policy.record_speech(now=tomorrow)


def test_quota_rolls_over_even_when_nobody_asks_for_days() -> None:
    """A long-running process must recover without any explicit day tick."""
    policy = ColdStartPolicy(day_count=30)
    for _ in range(3):
        policy.record_speech(now=_local(16, 10))
    assert not policy.can_speak(now=_local(16, 11))

    # No one calls reset_day(); two days pass silently, then a bubble is wanted.
    assert policy.can_speak(now=_local(18, 10))


def test_roll_over_reports_whether_it_happened() -> None:
    """The rollover helper is idempotent within a day and true across days."""
    policy = ColdStartPolicy(day_count=30)

    # First observation just records the day.
    assert policy.roll_over_if_new_day(_local(16, 9)) is False
    policy.record_speech(now=_local(16, 9))
    assert policy.roll_over_if_new_day(_local(16, 20)) is False
    assert policy.speeches_today == 1

    assert policy.roll_over_if_new_day(_local(17, 1)) is True
    assert policy.speeches_today == 0
    assert policy.roll_over_if_new_day(_local(17, 2)) is False


def test_quota_recovers_next_day_through_the_intervention_gate() -> None:
    """The end-to-end path that was broken: gate -> quota -> silence forever."""
    policy = ColdStartPolicy(day_count=30)
    engine = InterventionPolicy(cold_start=policy)

    day_one = _local(16, 9)
    allowed = [
        engine.allow_agent_bubble("tool_failure", now=day_one + timedelta(minutes=2 * i))
        for i in range(5)
    ]
    assert allowed == [True, True, True, False, False], allowed

    # The old bug: this used to stay False forever.
    next_day = _local(17, 9)
    assert engine.allow_agent_bubble("tool_failure", now=next_day) is True

    # And the cooldown still applies within a day.
    assert engine.allow_agent_bubble("tool_failure", now=next_day + timedelta(seconds=30)) is False
    assert engine.allow_agent_bubble("tool_failure", now=next_day + timedelta(seconds=61)) is True


def test_sanctuary_still_beats_the_quota_reset() -> None:
    """A new day must not override Sanctuary: distress stays 100% silent."""
    from src.core.sanctuary import SanctuaryGuard

    guard = SanctuaryGuard()
    guard.evaluate_text("烦死了")
    engine = InterventionPolicy(sanctuary=guard, cold_start=ColdStartPolicy(day_count=30))

    assert engine.allow_agent_bubble("tool_failure", now=_local(17, 9)) is False
    assert engine.allow_agent_bubble("tool_failure", now=_local(18, 9)) is False


def test_quota_respects_stage_limits_on_a_new_day() -> None:
    """Rollover must restore the stage's quota, not a fixed number."""
    # Day 1-3: 1 bubble/day.
    stage1 = ColdStartPolicy(day_count=1)
    assert stage1.daily_speech_quota == 1
    assert stage1.record_speech(now=_local(16, 9))
    assert not stage1.can_speak(now=_local(16, 10))
    assert stage1.can_speak(now=_local(17, 9))
    assert stage1.record_speech(now=_local(17, 9))
    assert not stage1.can_speak(now=_local(17, 10))

    # Day 15+: 3 bubbles/day.
    mature = ColdStartPolicy(day_count=30)
    assert mature.daily_speech_quota == 3
    assert sum(mature.record_speech(now=_local(16, 9)) for _ in range(5)) == 3
    restored = sum(mature.record_speech(now=_local(17, 9)) for _ in range(5))
    assert restored == 3, f"expected 3 on the new day, got {restored}"


def test_utc_timestamps_still_roll_over() -> None:
    """Callers may pass UTC datetimes; the day boundary follows them."""
    policy = ColdStartPolicy(day_count=30)
    for _ in range(3):
        policy.record_speech(now=datetime(2026, 10, 16, 22, 0, tzinfo=UTC))
    assert not policy.can_speak(now=datetime(2026, 10, 16, 23, 0, tzinfo=UTC))
    assert policy.can_speak(now=datetime(2026, 10, 17, 1, 0, tzinfo=UTC))
