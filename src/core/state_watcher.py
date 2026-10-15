"""State Watcher: Tracks continuous work sessions and midnight activity."""

from __future__ import annotations

from datetime import datetime


class StateWatcher:
    """Monitors objective work rhythm without psychological projection."""

    def __init__(self, overwork_threshold_hours: float = 3.0) -> None:
        self.overwork_threshold_hours = overwork_threshold_hours
        self._session_start: datetime | None = None
        self._last_active: datetime | None = None

    def record_activity(self, now: datetime | None = None) -> None:
        """Mark an activity event from the user or tool interaction."""
        current_time = now or datetime.now()
        if self._session_start is None:
            self._session_start = current_time
        self._last_active = current_time

    def reset_session(self) -> None:
        """User paused or took a break; reset session clock."""
        self._session_start = None
        self._last_active = None

    def continuous_work_hours(self, now: datetime | None = None) -> float:
        """Return continuous active work duration in hours."""
        if self._session_start is None:
            return 0.0
        current_time = now or datetime.now()
        seconds = max(0.0, (current_time - self._session_start).total_seconds())
        return round(seconds / 3600.0, 2)

    def is_overworking(self, now: datetime | None = None) -> bool:
        """Returns True if continuous activity exceeds the threshold."""
        return self.continuous_work_hours(now) >= self.overwork_threshold_hours

    def is_late_night(self, now: datetime | None = None) -> bool:
        """Returns True if current hour is in the midnight range [00:00 - 05:00]."""
        current_time = now or datetime.now()
        return current_time.hour in (0, 1, 2, 3, 4)
