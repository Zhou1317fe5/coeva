"""Cold Start Policy: 14-day progressive onboarding and speech quota enforcement."""

from __future__ import annotations

from enum import StrEnum


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
