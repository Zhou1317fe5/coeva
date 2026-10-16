"""Intervention Policy: Evaluates Evidence, Permission, and Timing Gates."""

from __future__ import annotations

from datetime import datetime

from src.core.cold_start import ColdStartPolicy
from src.core.sanctuary import SanctuaryGuard
from src.core.state_watcher import StateWatcher

# Agent lifecycle telemetry is a data-plane signal: by default it must not speak.
# Only these event types are notable enough to ever warrant a bubble, and even
# then at most once per cooldown (DESIGN.md section 2.3, the 80/15/5 ratio).
NOTABLE_AGENT_EVENTS = frozenset({"tool_failure"})
DEFAULT_AGENT_BUBBLE_COOLDOWN_SECONDS = 60.0


class InterventionPolicy:
    """Decides whether the companion should remain silent or offer a gentle nudge."""

    def __init__(
        self,
        sanctuary: SanctuaryGuard | None = None,
        cold_start: ColdStartPolicy | None = None,
        watcher: StateWatcher | None = None,
        *,
        agent_bubble_cooldown_seconds: float = DEFAULT_AGENT_BUBBLE_COOLDOWN_SECONDS,
    ) -> None:
        self.sanctuary = sanctuary or SanctuaryGuard()
        self.cold_start = cold_start or ColdStartPolicy()
        self.watcher = watcher or StateWatcher()
        self.agent_bubble_cooldown_seconds = agent_bubble_cooldown_seconds
        self._last_agent_bubble_at: datetime | None = None

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

    def allow_agent_bubble(self, event_type: str, *, now: datetime | None = None) -> bool:
        """Decide whether an agent-triggered bubble may interrupt the user.

        Agent events used to drive a bubble unconditionally, so every tool call
        printed "正在执行: <tool>" and every turn printed a celebration -- the
        desktop became an agent log viewer instead of a companion. This is the
        gate that keeps the 80/15/5 ratio (DESIGN.md section 2.3) true.

        Gate 1 (Sanctuary): user in distress -> 100% silence, no exceptions.
        Gate 2 (Notability): routine telemetry (prompt / tool call / turn end)
            never speaks; only an event in NOTABLE_AGENT_EVENTS may.
        Gate 3 (Quota + Cooldown): the daily proactive budget must have room,
            and the same class of event speaks at most once per cooldown.

        Returns True only when all gates pass, consuming one speech quota.
        """
        if self.sanctuary.is_active:
            return False

        if event_type not in NOTABLE_AGENT_EVENTS:
            return False

        current = now or datetime.now()
        # The quota is daily: roll it over before checking it, otherwise a
        # companion that spent its budget stays silent until it is restarted.
        self.cold_start.roll_over_if_new_day(current)
        if not self.cold_start.can_speak(now=current):
            return False

        if self._last_agent_bubble_at is not None:
            elapsed = (current - self._last_agent_bubble_at).total_seconds()
            if elapsed < self.agent_bubble_cooldown_seconds:
                return False

        if not self.cold_start.record_speech(now=current):
            return False

        self._last_agent_bubble_at = current
        return True
