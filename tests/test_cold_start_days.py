"""Tests for cold-start day counting (Phase 2 spec section 8).

The day count never advanced: ColdStartPolicy was built with a hardcoded
day_count=1 and reset_day() had no production caller, so
allows_psychological_analysis was permanently False and the companion could
never leave stage 1 no matter how long it ran.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from src.core.cold_start import (
    ColdStartPolicy,
    ColdStartStage,
    day_count_between,
    read_or_create_first_seen,
)


def test_day_count_is_one_based() -> None:
    """The first day counts as day 1, and the 14-day window spans 14 days."""
    first = date(2026, 1, 1)
    assert day_count_between(first, first) == 1
    assert day_count_between(first, first + timedelta(days=1)) == 2
    assert day_count_between(first, first + timedelta(days=13)) == 14
    assert day_count_between(first, first + timedelta(days=14)) == 15
    # A clock going backwards must not produce a nonsensical day count.
    assert day_count_between(first, first - timedelta(days=5)) == 1


def test_first_seen_is_created_once_then_reused(tmp_path: Path) -> None:
    """First launch writes the file; later launches read the same date back."""
    path = tmp_path / "first_seen.json"
    day_one = date(2026, 3, 1)

    assert read_or_create_first_seen(path, today=day_one) == day_one
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["first_seen"] == "2026-03-01"

    # A later launch keeps the original date rather than resetting it.
    assert read_or_create_first_seen(path, today=date(2026, 3, 20)) == day_one


def test_corrupt_first_seen_is_recovered(tmp_path: Path) -> None:
    """A corrupt or unreadable file is rewritten instead of crashing startup."""
    path = tmp_path / "first_seen.json"
    path.write_text("{ not json", encoding="utf-8")
    assert read_or_create_first_seen(path, today=date(2026, 5, 5)) == date(2026, 5, 5)
    assert json.loads(path.read_text(encoding="utf-8"))["first_seen"] == "2026-05-05"

    path.write_text(json.dumps({"wrong_key": "x"}), encoding="utf-8")
    assert read_or_create_first_seen(path, today=date(2026, 5, 6)) == date(2026, 5, 6)

    path.write_text(json.dumps({"first_seen": "not-a-date"}), encoding="utf-8")
    assert read_or_create_first_seen(path, today=date(2026, 5, 7)) == date(2026, 5, 7)


def test_policy_advances_through_stages_over_real_time(tmp_path: Path) -> None:
    """The whole point: the stage progresses as days actually pass."""
    path = tmp_path / "first_seen.json"
    start = date(2026, 1, 1)
    read_or_create_first_seen(path, today=start)

    day1 = ColdStartPolicy.from_persisted_first_seen(path, today=start)
    assert day1.day_count == 1
    assert day1.stage == ColdStartStage.STAGE_1_PRESENCE
    assert not day1.allows_psychological_analysis

    day5 = ColdStartPolicy.from_persisted_first_seen(path, today=start + timedelta(days=4))
    assert day5.stage == ColdStartStage.STAGE_2_FACT_MIRROR
    assert not day5.allows_psychological_analysis

    day10 = ColdStartPolicy.from_persisted_first_seen(path, today=start + timedelta(days=9))
    assert day10.stage == ColdStartStage.STAGE_3_CALIBRATION
    assert day10.allows_psychological_analysis, "day 10 must permit analysis"

    day20 = ColdStartPolicy.from_persisted_first_seen(path, today=start + timedelta(days=19))
    assert day20.stage == ColdStartStage.STAGE_MATURE
    assert day20.allows_psychological_analysis


def test_app_wires_the_persisted_day_count() -> None:
    """Guard the call site so the hardcoded day_count=1 cannot come back."""
    import inspect

    import run_companion

    source = inspect.getsource(run_companion.CompanionApp.__init__)
    assert "from_persisted_first_seen()" in source, "cold start must use real elapsed days"
    assert "ColdStartPolicy(day_count=1)" not in source, "hardcoded day_count=1 is the bug"
