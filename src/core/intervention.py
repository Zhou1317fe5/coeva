"""Intervention Policy: Evaluates Evidence, Permission, and Timing Gates."""

from __future__ import annotations

from src.core.cold_start import ColdStartPolicy
from src.core.sanctuary import SanctuaryGuard
from src.core.state_watcher import StateWatcher


class InterventionPolicy:
    """Decides whether the companion should remain silent or offer a gentle nudge."""

    def __init__(
        self,
        sanctuary: SanctuaryGuard | None = None,
        cold_start: ColdStartPolicy | None = None,
        watcher: StateWatcher | None = None,
    ) -> None:
        self.sanctuary = sanctuary or SanctuaryGuard()
        self.cold_start = cold_start or ColdStartPolicy()
        self.watcher = watcher or StateWatcher()

    def evaluate_intervention(self, *, is_task_in_flight: bool = False) -> str | None:
        """Run through the 3 Gates and return message text if intervention is approved.

        Gate 1 (Permission/Sanctuary): If user is in distress, 100% silence.
        Gate 2 (Quota/Cooldown): If cold-start speech quota is full, silence.
        Gate 3 (Timing Gate): If agent/user is in active task, silence.
        """
        # 1. Sanctuary check
        if self.sanctuary.is_active:
            return None

        # 2. Permission / Quota check
        if not self.cold_start.can_speak():
            return None

        # 3. Timing Gate: do not disrupt active high-cognitive tasks
        if is_task_in_flight:
            return None

        # State intervention: Overworking
        if self.watcher.is_overworking():
            if self.cold_start.record_speech():
                return "今天这个任务折腾挺久了，先歇口气？"

        # State intervention: Late night
        if self.watcher.is_late_night():
            if self.cold_start.record_speech():
                return "夜深了，这个问题今晚一定要解决吗？"

        # Default action: Observe by default (silence)
        return None
