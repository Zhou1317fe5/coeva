"""Unit tests for Growth Core and Sanctuary Guard."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.core.cold_start import ColdStartPolicy, ColdStartStage
from src.core.intervention import InterventionPolicy
from src.core.sanctuary import SanctuaryGuard
from src.core.state_watcher import StateWatcher


def test_sanctuary_guard_triggers_and_meltdown() -> None:
    """Test Sanctuary Guard activates on frustration keywords and enforces silence."""
    guard = SanctuaryGuard()
    assert not guard.is_active

    # Neutral text does not activate
    assert not guard.evaluate_text("今天读完了一篇很棒的架构论文。")
    assert not guard.is_active

    # Frustrated text triggers meltdown
    assert guard.evaluate_text("这个bug真是烦死了，全搞砸了！")
    assert guard.is_active

    # After meltdown, even normal text is guarded
    guard.reset()
    assert not guard.is_active


def test_cold_start_policy_stages_and_quotas() -> None:
    """Test 14-day progressive cold start policy and daily speech quota."""
    # Day 1 -> Stage 1 (max 1 speech/day, 0% psych analysis)
    policy = ColdStartPolicy(day_count=1)
    assert policy.stage == ColdStartStage.STAGE_1_PRESENCE
    assert policy.daily_speech_quota == 1
    assert not policy.allows_psychological_analysis

    assert policy.can_speak()
    assert policy.record_speech()
    assert not policy.can_speak()  # quota consumed

    # Day 5 -> Stage 2 (max 2 speech/day)
    policy.day_count = 5
    policy.reset_day()
    assert policy.stage == ColdStartStage.STAGE_2_FACT_MIRROR
    assert policy.daily_speech_quota == 2
    assert not policy.allows_psychological_analysis

    # Day 10 -> Stage 3 (allows calibration query)
    policy.day_count = 10
    policy.reset_day()
    assert policy.stage == ColdStartStage.STAGE_3_CALIBRATION
    assert policy.allows_psychological_analysis


def test_state_watcher_work_hours_and_late_night() -> None:
    """Test continuous work tracking and midnight detection."""
    watcher = StateWatcher(overwork_threshold_hours=3.0)
    base_time = datetime(2026, 10, 15, 14, 0, 0)
    watcher.record_activity(base_time)

    # 1 hour later
    one_hour_later = base_time + timedelta(hours=1)
    assert watcher.continuous_work_hours(one_hour_later) == 1.0
    assert not watcher.is_overworking(one_hour_later)

    # 3.5 hours later
    overwork_time = base_time + timedelta(hours=3, minutes=30)
    assert watcher.continuous_work_hours(overwork_time) == 3.5
    assert watcher.is_overworking(overwork_time)

    # Late night check
    midnight_time = datetime(2026, 10, 15, 2, 30, 0)
    assert watcher.is_late_night(midnight_time)

    daytime = datetime(2026, 10, 15, 15, 0, 0)
    assert not watcher.is_late_night(daytime)


def test_intervention_policy_3_gates() -> None:
    """Test 3-gate decision flow for gentle nudges."""
    guard = SanctuaryGuard()
    policy = ColdStartPolicy(day_count=5)
    watcher = StateWatcher(overwork_threshold_hours=3.0)
    watcher.is_late_night = lambda now=None: False  # type: ignore[method-assign]
    engine = InterventionPolicy(sanctuary=guard, cold_start=policy, watcher=watcher)

    # Normal state -> Observe by default (None)
    assert engine.evaluate_intervention(is_task_in_flight=False) is None

    # Simulate overwork
    base_time = datetime(2026, 10, 15, 14, 0)
    watcher.record_activity(base_time)
    # Monkeypatch watcher's check
    watcher.continuous_work_hours = lambda now=None: 4.0  # type: ignore[method-assign]

    # Timing Gate: Task in flight -> Silence
    assert engine.evaluate_intervention(is_task_in_flight=True) is None

    # Task idle -> Gentle overwork nudge approved
    msg = engine.evaluate_intervention(is_task_in_flight=False)
    assert msg is not None
    assert "歇口气" in msg

    # Gate 1 (Sanctuary): If user vents frustration -> 100% silence
    guard.evaluate_text("别烦我，真恶心")
    assert guard.is_active
    assert engine.evaluate_intervention(is_task_in_flight=False) is None
