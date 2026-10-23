"""Life Scheduler (Phase 2.5 WP-5).

Lightweight, silence-first autonomous behavior scheduler.
Generates generic BehaviorIntent instances without hard-coding pet identities,
assets, or activity names.

Invariants:
- Quiet presence first: silence is a first-class result, not a failure.
- Zero pet-specific names or assets in this module.
- Generates only base autonomous categories: OBSERVE, WORK, REST, PLAY, MOVE.
- Anti-repetition: suppresses consecutive identical categories and limits MOVE frequency.
- Deterministic testability via Clock and RNG injection.
"""

from __future__ import annotations

import collections
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.behavior.context import LifeContext, SchedulerModulation

from src.core.behavior.arbiter import BehaviorPriority, BehaviorRequest
from src.core.behavior.registry import ActivityRegistry
from src.core.behavior.semantics import (
    ActivityTrait,
    BehaviorCategory,
    BehaviorDirection,
    BehaviorIntent,
)

# Allowed autonomous categories in WP-5
AUTONOMOUS_CATEGORIES: tuple[BehaviorCategory, ...] = (
    BehaviorCategory.OBSERVE,
    BehaviorCategory.WORK,
    BehaviorCategory.REST,
    BehaviorCategory.PLAY,
    BehaviorCategory.MOVE,
)


@dataclass(frozen=True)
class SchedulerConfig:
    """Configuration governing autonomous behavior cadence and weighting."""

    consideration_min_sec: float = 12.0
    consideration_max_sec: float = 35.0
    minimum_quiet_sec: float = 10.0
    autonomous_duration_min_sec: float = 6.0
    autonomous_duration_max_sec: float = 16.0
    silence_weight: float = 3.5
    category_weights: Mapping[BehaviorCategory, float] = field(
        default_factory=lambda: {
            BehaviorCategory.OBSERVE: 3.0,
            BehaviorCategory.WORK: 2.5,
            BehaviorCategory.REST: 2.0,
            BehaviorCategory.PLAY: 1.5,
            BehaviorCategory.MOVE: 1.0,
        }
    )
    max_consecutive_same_category: int = 1
    max_moves_in_history: int = 2
    history_capacity: int = 20

    def __post_init__(self) -> None:
        min_c = self.consideration_min_sec
        max_c = self.consideration_max_sec
        if min_c <= 0 or max_c < min_c:
            msg = "consideration range must be positive and min <= max"
            raise ValueError(msg)
        if self.minimum_quiet_sec < 0:
            msg = "minimum_quiet_sec must be non-negative"
            raise ValueError(msg)
        min_d = self.autonomous_duration_min_sec
        max_d = self.autonomous_duration_max_sec
        if min_d <= 0 or max_d < min_d:
            msg = "autonomous duration range must be positive and min <= max"
            raise ValueError(msg)


@dataclass(frozen=True)
class AutonomousHistoryEntry:
    """In-memory trace of an executed autonomous activity."""

    timestamp: float
    category: BehaviorCategory
    direction: BehaviorDirection
    duration_sec: float
    activity_id: str | None = None


class LifeScheduler:
    """Autonomous life scheduler deciding WHAT to do next and WHEN to consider again."""

    def __init__(
        self,
        config: SchedulerConfig | None = None,
        *,
        clock: Callable[[], float] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config or SchedulerConfig()
        self._clock = clock or time.monotonic
        self._rng = rng or random.Random()
        self._history: collections.deque[AutonomousHistoryEntry] = collections.deque(
            maxlen=self._config.history_capacity
        )
        self._last_activity_finished_at: float = 0.0

    @property
    def config(self) -> SchedulerConfig:
        """Scheduler configuration."""
        return self._config

    @property
    def history(self) -> tuple[AutonomousHistoryEntry, ...]:
        """In-memory recent autonomous behavior history."""
        return tuple(self._history)

    def record_activity_finished(self, finish_time: float | None = None) -> None:
        """Mark that an active activity has finished, initiating the quiet window."""
        self._last_activity_finished_at = finish_time if finish_time is not None else self._clock()

    def record_activity_started(
        self,
        category: BehaviorCategory,
        direction: BehaviorDirection = BehaviorDirection.NONE,
        duration_sec: float = 10.0,
        activity_id: str | None = None,
        start_time: float | None = None,
    ) -> None:
        """Record an autonomous behavior in recent history."""
        t = start_time if start_time is not None else self._clock()
        entry = AutonomousHistoryEntry(
            timestamp=t,
            category=category,
            direction=direction,
            duration_sec=duration_sec,
            activity_id=activity_id,
        )
        self._history.append(entry)

    def consider(
        self,
        registry: ActivityRegistry,
        *,
        active_request: BehaviorRequest | None = None,
        context: LifeContext | None = None,
    ) -> tuple[BehaviorIntent | None, float]:
        """Evaluate whether to stay quiet or emit an autonomous BehaviorIntent.

        Returns:
            (intent_or_none, next_delay_sec)
        """
        now = self._clock()

        # Compute next consideration delay
        next_delay = self._rng.uniform(
            self._config.consideration_min_sec, self._config.consideration_max_sec
        )

        # 1. Busy check: if active request is >= P1_AUTONOMOUS, stay quiet
        if active_request is not None and active_request.priority >= BehaviorPriority.P1_AUTONOMOUS:
            return None, next_delay

        # Compile context modulation if provided
        modulation: SchedulerModulation | None = None
        effective_quiet_sec = self._config.minimum_quiet_sec
        if context is not None:
            from src.core.behavior.context import ContextModulator

            modulation = ContextModulator.modulate(self._config, context)
            effective_quiet_sec *= modulation.quiet_window_multiplier

        # 2. Quiet window check: must stay quiet for at least effective_quiet_sec
        time_since_last = now - self._last_activity_finished_at
        if self._last_activity_finished_at > 0.0:
            if time_since_last < effective_quiet_sec:
                remaining_quiet = effective_quiet_sec - time_since_last
                return None, max(next_delay, remaining_quiet)

        # 3. Filter candidates based on pet registry capabilities and anti-repetition rules
        candidates, weights = self._gather_candidates(registry, modulation=modulation)

        if not candidates:
            # Nothing viable right now
            return None, next_delay

        # 4. Weighted random choice (including SILENCE)
        chosen = self._rng.choices(candidates, weights=weights, k=1)[0]
        if chosen is None:
            # Silence chosen! Quiet presence preserved.
            return None, next_delay

        # 5. Form generic BehaviorIntent for the chosen category
        direction = BehaviorDirection.NONE
        if chosen == BehaviorCategory.MOVE:
            direction = self._rng.choice((BehaviorDirection.LEFT, BehaviorDirection.RIGHT))

        preferred_traits = self._traits_for_category(chosen)
        intent = BehaviorIntent(
            category=chosen,
            source="life_scheduler",
            preferred_traits=preferred_traits,
            direction=direction,
        )
        return intent, next_delay

    def sample_duration_sec(self) -> float:
        """Sample a natural duration for an autonomous activity."""
        return round(
            self._rng.uniform(
                self._config.autonomous_duration_min_sec,
                self._config.autonomous_duration_max_sec,
            ),
            1,
        )

    def _gather_candidates(
        self,
        registry: ActivityRegistry,
        *,
        modulation: SchedulerModulation | None = None,
    ) -> tuple[list[BehaviorCategory | None], list[float]]:
        """Collect viable categories and their weights according to anti-repetition rules."""
        silence_w = self._config.silence_weight
        if modulation is not None:
            silence_w *= modulation.silence_multiplier

        candidates: list[BehaviorCategory | None] = [None]
        weights: list[float] = [silence_w]

        last_category: BehaviorCategory | None = None
        if self._history:
            last_category = self._history[-1].category

        recent_moves = sum(
            1 for entry in list(self._history)[-6:] if entry.category == BehaviorCategory.MOVE
        )

        pool: tuple[BehaviorCategory, ...] = AUTONOMOUS_CATEGORIES
        if modulation is not None and modulation.allow_autonomous_sleep:
            pool = (*AUTONOMOUS_CATEGORIES, BehaviorCategory.SLEEP)

        for cat in pool:
            # Check category restrictions from context
            if modulation is not None and modulation.allowed_categories is not None:
                if cat not in modulation.allowed_categories:
                    continue

            # Category must be natively supported by the pet or fall back safely
            if not registry.supports_category(cat):
                acts = registry.activities_for(cat)
                if not acts:
                    continue

            # Anti-repetition: suppress consecutive same category
            if last_category is not None and cat == last_category:
                continue

            # Anti-repetition: limit MOVE rate
            if cat == BehaviorCategory.MOVE and recent_moves >= self._config.max_moves_in_history:
                continue

            base_w = self._config.category_weights.get(cat, 1.0)
            if modulation is not None:
                cat_mult = modulation.category_multipliers.get(cat, 1.0)
                base_w *= cat_mult

            if base_w > 0.0:
                candidates.append(cat)
                weights.append(base_w)
        # Fallback if all non-silence candidates were suppressed by repetition
        if len(candidates) == 1:
            for cat in AUTONOMOUS_CATEGORIES:
                if registry.supports_category(cat):
                    candidates.append(cat)
                    weights.append(self._config.category_weights.get(cat, 1.0))

        return candidates, weights

    @staticmethod
    def _traits_for_category(category: BehaviorCategory) -> tuple[ActivityTrait, ...]:
        if category == BehaviorCategory.SLEEP:
            return (ActivityTrait.QUIET, ActivityTrait.LOW_ENERGY, ActivityTrait.STATIONARY)
        if category == BehaviorCategory.WORK:
            return (ActivityTrait.QUIET, ActivityTrait.STATIONARY, ActivityTrait.FOCUSED)
        if category == BehaviorCategory.OBSERVE:
            return (ActivityTrait.QUIET, ActivityTrait.STATIONARY, ActivityTrait.CASUAL)
        if category == BehaviorCategory.REST:
            return (ActivityTrait.QUIET, ActivityTrait.STATIONARY, ActivityTrait.LOW_ENERGY)
        if category == BehaviorCategory.PLAY:
            return (ActivityTrait.CASUAL, ActivityTrait.STATIONARY)
        if category == BehaviorCategory.MOVE:
            return (ActivityTrait.ACTIVE, ActivityTrait.LOCOMOTIVE)
        return ()
