"""Tests for Circadian Life Schedule: human-like daily rhythm."""

from datetime import datetime

from src.core.circadian import (
    CircadianPhase,
    get_circadian_phase,
)


def test_circadian_24_hour_phases() -> None:
    """Verify circadian phase mapping across all 24 hours of the day."""
    cases = [
        (datetime(2026, 10, 17, 0, 0), CircadianPhase.NIGHT_SLEEP),
        (datetime(2026, 10, 17, 3, 30), CircadianPhase.NIGHT_SLEEP),
        (datetime(2026, 10, 17, 7, 0), CircadianPhase.NIGHT_SLEEP),
        (datetime(2026, 10, 17, 7, 45), CircadianPhase.MORNING_WAKE),
        (datetime(2026, 10, 17, 8, 30), CircadianPhase.MORNING_WAKE),
        (datetime(2026, 10, 17, 9, 0), CircadianPhase.MORNING_WORK),
        (datetime(2026, 10, 17, 11, 15), CircadianPhase.MORNING_WORK),
        (datetime(2026, 10, 17, 12, 0), CircadianPhase.MIDDAY_SIESTA),
        (datetime(2026, 10, 17, 13, 30), CircadianPhase.MIDDAY_SIESTA),
        (datetime(2026, 10, 17, 14, 0), CircadianPhase.AFTERNOON_FOCUS),
        (datetime(2026, 10, 17, 16, 30), CircadianPhase.AFTERNOON_FOCUS),
        (datetime(2026, 10, 17, 18, 15), CircadianPhase.AFTERNOON_FOCUS),
        (datetime(2026, 10, 17, 18, 45), CircadianPhase.EVENING_LEISURE),
        (datetime(2026, 10, 17, 21, 0), CircadianPhase.EVENING_LEISURE),
        (datetime(2026, 10, 17, 22, 59), CircadianPhase.EVENING_LEISURE),
        (datetime(2026, 10, 17, 23, 0), CircadianPhase.NIGHT_SLEEP),
    ]
    for dt, expected in cases:
        assert get_circadian_phase(dt) == expected, f"Failed for {dt}"


def test_circadian_schedules_pacing() -> None:
    """Verify pacing and activity durations across circadian schedule configs."""
    from src.core.circadian import SCHEDULE_CONFIGS

    for schedule in SCHEDULE_CONFIGS.values():
        assert schedule.min_pause_ms >= 25_000
        assert schedule.max_pause_ms >= schedule.min_pause_ms
        assert len(schedule.allowed_activities) > 0
        # Work phases have is_work_phase=True
        if schedule.is_work_phase:
            assert schedule.phase in (CircadianPhase.MORNING_WORK, CircadianPhase.AFTERNOON_FOCUS)
