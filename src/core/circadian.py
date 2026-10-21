"""Circadian Life Schedule: Realistic human-like 24-hour daily rhythm.

Maps the 24-hour day into natural human living phases:
- Night Sleep (23:00 - 07:30): restful sleeping, deep quiet, companion stays sleeping.
- Morning Wake (07:30 - 09:00): waking stretch, yawning, slow morning start.
- Morning Work (09:00 - 12:00): deep craft & coding work (typing, carpentry, thinking).
- Midday Siesta (12:00 - 14:00): lunch rest, dozing, relaxed catnap.
- Afternoon Focus (14:00 - 18:30): workshop production (building, typing, sweeping, carrying).
- Evening Leisure (18:30 - 23:00): evening relaxation, leisure play (music, juggling, idle).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CircadianPhase(StrEnum):
    NIGHT_SLEEP = "night_sleep"
    MORNING_WAKE = "morning_wake"
    MORNING_WORK = "morning_work"
    MIDDAY_SIESTA = "midday_siesta"
    AFTERNOON_FOCUS = "afternoon_focus"
    EVENING_LEISURE = "evening_leisure"


@dataclass(frozen=True)
class PhaseSchedule:
    """Schedule policy defining activities and intervals for a living phase."""

    phase: CircadianPhase
    default_state: str  # "idle" or "sleeping"
    allowed_activities: tuple[tuple[str, int], ...]  # (sheet_name, duration_ms)
    min_pause_ms: int  # calm idle breathing pause before next action
    max_pause_ms: int
    is_work_phase: bool = False  # True during 09:00-12:00 and 14:00-18:30


def get_circadian_phase(dt: datetime | None = None) -> CircadianPhase:
    """Return the circadian living phase for the given datetime (defaults to now)."""
    now = dt or datetime.now()
    total_minutes = now.hour * 60 + now.minute

    # 23:00 (1380m) to 07:30 (450m): Night Sleep
    if total_minutes >= 23 * 60 or total_minutes < 7 * 60 + 30:
        return CircadianPhase.NIGHT_SLEEP
    # 07:30 to 09:00: Morning Wake & slow start
    elif total_minutes < 9 * 60:
        return CircadianPhase.MORNING_WAKE
    # 09:00 to 12:00: Morning Deep Work
    elif total_minutes < 12 * 60:
        return CircadianPhase.MORNING_WORK
    # 12:00 to 14:00: Midday Siesta & Lunch Rest
    elif total_minutes < 14 * 60:
        return CircadianPhase.MIDDAY_SIESTA
    # 14:00 to 18:30: Afternoon Focus & Craft Workshop
    elif total_minutes < 18 * 60 + 30:
        return CircadianPhase.AFTERNOON_FOCUS
    # 18:30 to 23:00: Evening Leisure & Free Time
    else:
        return CircadianPhase.EVENING_LEISURE


# Activity definitions per phase (sheet name, duration in ms)
SCHEDULE_CONFIGS: dict[CircadianPhase, PhaseSchedule] = {
    CircadianPhase.NIGHT_SLEEP: PhaseSchedule(
        phase=CircadianPhase.NIGHT_SLEEP,
        default_state="sleeping",
        allowed_activities=(
            ("dozing", 20_000),
            ("waking", 6_000),
        ),
        min_pause_ms=600_000,  # 10 - 25 minutes in deep night
        max_pause_ms=1_500_000,
        is_work_phase=False,
    ),
    CircadianPhase.MORNING_WAKE: PhaseSchedule(
        phase=CircadianPhase.MORNING_WAKE,
        default_state="idle",
        allowed_activities=(
            ("waking", 10_000),
            ("yawning", 10_000),
            ("thinking", 15_000),
        ),
        min_pause_ms=90_000,  # 1.5 - 3 minutes calm pause
        max_pause_ms=180_000,
        is_work_phase=False,
    ),
    CircadianPhase.MORNING_WORK: PhaseSchedule(
        phase=CircadianPhase.MORNING_WORK,
        default_state="idle",
        allowed_activities=(
            ("working-typing", 70_000),  # Calico
            ("working-building", 60_000),  # Calico
            ("review", 60_000),  # Vasu 专注审查/思考
            ("waiting", 45_000),  # Vasu 专注凝视
            ("running", 35_000),  # Vasu 活力奔跑
            ("thinking", 40_000),  # Calico
            ("working-sweeping", 45_000),  # Calico
            ("working-carrying", 35_000),  # Calico
        ),
        min_pause_ms=25_000,  # 25s - 50s breather between focused work bouts
        max_pause_ms=50_000,
        is_work_phase=True,
    ),
    CircadianPhase.MIDDAY_SIESTA: PhaseSchedule(
        phase=CircadianPhase.MIDDAY_SIESTA,
        default_state="idle",
        allowed_activities=(
            ("yawning", 10_000),
            ("dozing", 30_000),
            ("waiting", 25_000),  # Vasu 午间放空
            ("thinking", 20_000),
            ("waking", 8_000),
        ),
        min_pause_ms=120_000,  # 2 - 4 minutes
        max_pause_ms=240_000,
        is_work_phase=False,
    ),
    CircadianPhase.AFTERNOON_FOCUS: PhaseSchedule(
        phase=CircadianPhase.AFTERNOON_FOCUS,
        default_state="idle",
        allowed_activities=(
            ("working-building", 75_000),  # Calico
            ("working-typing", 70_000),  # Calico
            ("review", 65_000),  # Vasu 下午深度复盘与构思
            ("waiting", 45_000),  # Vasu 耐心等待与凝视
            ("running", 35_000),  # Vasu 奔跑
            ("running-right", 30_000),  # Vasu 向右小跑
            ("running-left", 30_000),  # Vasu 向左小跑
            ("working-sweeping", 45_000),  # Calico
            ("thinking", 40_000),  # Calico
            ("working-carrying", 35_000),  # Calico
        ),
        min_pause_ms=25_000,  # 25s - 50s breather between focused work bouts
        max_pause_ms=50_000,
        is_work_phase=True,
    ),
    CircadianPhase.EVENING_LEISURE: PhaseSchedule(
        phase=CircadianPhase.EVENING_LEISURE,
        default_state="idle",
        allowed_activities=(
            ("working-conducting", 35_000),
            ("working-juggling", 30_000),
            ("jumping", 25_000),  # Vasu 欢快跳跃玩耍
            ("waving", 15_000),  # Vasu 招手挥爪致意
            ("running-right", 20_000),  # Vasu 闲暇小跑
            ("running-left", 20_000),  # Vasu
            ("thinking", 20_000),
            ("waiting", 25_000),  # Vasu 发呆放空
            ("yawning", 10_000),
        ),
        min_pause_ms=90_000,  # 1.5 - 3 minutes
        max_pause_ms=180_000,
        is_work_phase=False,
    ),
}


def get_schedule_for_time(dt: datetime | None = None) -> PhaseSchedule:
    """Return the PhaseSchedule corresponding to current or specified time."""
    phase = get_circadian_phase(dt)
    return SCHEDULE_CONFIGS[phase]
