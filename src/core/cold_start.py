"""Cold Start Policy: 14-day progressive onboarding and speech quota enforcement."""

from __future__ import annotations

import json
from datetime import date
from enum import StrEnum
from pathlib import Path

DEFAULT_FIRST_SEEN_PATH = Path("data") / "first_seen.json"


def day_count_between(first_seen: date, today: date) -> int:
    """1-based day index of `today` relative to `first_seen`.

    The first day the companion is seen counts as day 1, so the 14-day cold start
    spans first_seen .. first_seen + 13 days.
    """
    return max(1, (today - first_seen).days + 1)


def read_or_create_first_seen(path: Path | None = None, *, today: date | None = None) -> date:
    """Return the persisted first-run date, creating it on first launch.

    Without this the day count never advanced: ColdStartPolicy was constructed with
    a hardcoded day_count=1 and reset_day() had no production caller, so
    allows_psychological_analysis was permanently False.
    """
    resolved_path = path or DEFAULT_FIRST_SEEN_PATH
    current = today or date.today()

    if resolved_path.is_file():
        try:
            data = json.loads(resolved_path.read_text(encoding="utf-8"))
            return date.fromisoformat(str(data["first_seen"]))
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            pass  # unreadable or corrupt: fall through and rewrite it

    try:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(
            json.dumps({"first_seen": current.isoformat()}), encoding="utf-8"
        )
    except OSError:
        pass  # a read-only filesystem must not stop the companion from starting
    return current


class ColdStartStage(StrEnum):
    """The 3 progressive stages of the companion onboarding."""

    STAGE_1_PRESENCE = "stage_1_presence"  # Day 1-3: Pure action presence, max 1 greeting/day
    STAGE_2_FACT_MIRROR = "stage_2_fact_mirror"  # Day 4-7: State care + slice echo, max 2/day
    STAGE_3_CALIBRATION = "stage_3_calibration"  # Day 8-14: Allows 1 tentative habit query
    STAGE_MATURE = "stage_mature"  # Day 15+: Full development policy


class ColdStartPolicy:
    """Enforces speech limits and psychological boundaries during cold start."""

    def __init__(self, day_count: int = 1) -> None:
        self.day_count = max(1, day_count)
        self.speeches_today = 0

    @classmethod
    def from_persisted_first_seen(
        cls, path: Path | None = None, *, today: date | None = None
    ) -> ColdStartPolicy:
        """Build a policy whose day count reflects real elapsed days.

        Replaces the previous hardcoded `day_count=1`, which pinned the companion
        to stage 1 forever because nothing ever called reset_day().
        """
        first_seen = read_or_create_first_seen(path, today=today)
        current = today or date.today()
        return cls(day_count=day_count_between(first_seen, current))

    @property
    def stage(self) -> ColdStartStage:
        """Derive the current cold start stage from total active days."""
        if self.day_count <= 3:
            return ColdStartStage.STAGE_1_PRESENCE
        if self.day_count <= 7:
            return ColdStartStage.STAGE_2_FACT_MIRROR
        if self.day_count <= 14:
            return ColdStartStage.STAGE_3_CALIBRATION
        return ColdStartStage.STAGE_MATURE

    @property
    def daily_speech_quota(self) -> int:
        """Maximum proactive messages allowed per day."""
        if self.stage == ColdStartStage.STAGE_1_PRESENCE:
            return 1
        if self.stage == ColdStartStage.STAGE_2_FACT_MIRROR:
            return 2
        return 3

    @property
    def allows_psychological_analysis(self) -> bool:
        """Deep psychological interpretation is strictly forbidden in stages 1 and 2."""
        return self.stage in (ColdStartStage.STAGE_3_CALIBRATION, ColdStartStage.STAGE_MATURE)

    def can_speak(self) -> bool:
        """Check if daily speech budget remains."""
        return self.speeches_today < self.daily_speech_quota

    def record_speech(self) -> bool:
        """Consume one quota if allowed."""
        if not self.can_speak():
            return False
        self.speeches_today += 1
        return True

    def reset_day(self) -> None:
        """Reset daily speech counter when day advances."""
        self.speeches_today = 0
        self.day_count += 1
