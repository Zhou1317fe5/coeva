"""Context Modulation Layer for Autonomous Life (Phase 2.5 WP-6).

Translates external conditions (Circadian time phases, StateWatcher aggregate
activity, Sanctuary mode, dock states, UI active states, and confirmed relationship insights)
into read-only, deterministic modulation biases for the LifeScheduler.

Invariants:
- Context is strictly read-only and generates ZERO direct Body commands.
- Base SchedulerConfig remains completely immutable.
- Multiplicative composition is clamped within safe mathematical bounds.
- Autonomous sleep is strictly P1_AUTONOMOUS and never grants PROTECTED_SLEEP.
- Candidate, rejected, or retracted hypotheses have ZERO effect on behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.core.behavior.scheduler import SchedulerConfig
from src.core.behavior.semantics import BehaviorCategory
from src.core.circadian import CircadianPhase


@dataclass(frozen=True)
class LifeContext:
    """Read-only snapshot of current external environment and operational modes."""

    circadian_phase: CircadianPhase = CircadianPhase.MORNING_WORK
    hour: int = 10
    agent_active: bool = False
    sanctuary_active: bool = False
    mini_mode_docked: bool = False
    feeder_active: bool = False
    bubble_active: bool = False
    active_confirmed_insights: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchedulerModulation:
    """Deterministic multipliers and category constraints derived from context."""

    silence_multiplier: float = 1.0
    quiet_window_multiplier: float = 1.0
    category_multipliers: Mapping[BehaviorCategory, float] = field(default_factory=dict)
    allowed_categories: frozenset[BehaviorCategory] | None = None
    allow_autonomous_sleep: bool = False
    reasons: tuple[str, ...] = ()


class ContextModulator:
    """Pure domain engine compiling a LifeContext into a SchedulerModulation."""

    MIN_SILENCE_MULT = 0.3
    MAX_SILENCE_MULT = 5.0

    MIN_QUIET_MULT = 0.5
    MAX_QUIET_MULT = 3.0

    MIN_CAT_MULT = 0.0
    MAX_CAT_MULT = 3.0

    @classmethod
    def modulate(
        cls, base_config: SchedulerConfig, context: LifeContext
    ) -> SchedulerModulation:
        """Compile context into an immutable SchedulerModulation."""
        silence_m = 1.0
        quiet_m = 1.0
        cat_m: dict[BehaviorCategory, float] = {
            cat: 1.0 for cat in base_config.category_weights
        }
        allowed_sets: list[frozenset[BehaviorCategory]] = []
        allow_sleep = False
        reasons: list[str] = []

        # 1. Circadian Phase Profile
        phase = context.circadian_phase
        reasons.append(f"circadian_{phase.value}")

        if phase == CircadianPhase.NIGHT_SLEEP:
            silence_m *= 2.5
            quiet_m *= 1.8
            cat_m[BehaviorCategory.REST] = cat_m.get(BehaviorCategory.REST, 1.0) * 1.8
            cat_m[BehaviorCategory.MOVE] = 0.0
            cat_m[BehaviorCategory.PLAY] = 0.0
            cat_m[BehaviorCategory.WORK] = cat_m.get(BehaviorCategory.WORK, 1.0) * 0.3
            allow_sleep = True
            allowed_sets.append(
                frozenset({
                    BehaviorCategory.REST,
                    BehaviorCategory.SLEEP,
                    BehaviorCategory.OBSERVE,
                })
            )
        elif phase == CircadianPhase.MORNING_WAKE:
            silence_m *= 1.2
            cat_m[BehaviorCategory.REST] = cat_m.get(BehaviorCategory.REST, 1.0) * 1.3
            cat_m[BehaviorCategory.OBSERVE] = cat_m.get(BehaviorCategory.OBSERVE, 1.0) * 1.2
            cat_m[BehaviorCategory.PLAY] = cat_m.get(BehaviorCategory.PLAY, 1.0) * 0.5
        elif phase == CircadianPhase.MORNING_WORK:
            cat_m[BehaviorCategory.WORK] = cat_m.get(BehaviorCategory.WORK, 1.0) * 1.4
            cat_m[BehaviorCategory.OBSERVE] = cat_m.get(BehaviorCategory.OBSERVE, 1.0) * 1.2
            cat_m[BehaviorCategory.PLAY] = cat_m.get(BehaviorCategory.PLAY, 1.0) * 0.6
            cat_m[BehaviorCategory.MOVE] = cat_m.get(BehaviorCategory.MOVE, 1.0) * 0.9
        elif phase == CircadianPhase.MIDDAY_SIESTA:
            silence_m *= 1.5
            quiet_m *= 1.3
            cat_m[BehaviorCategory.REST] = cat_m.get(BehaviorCategory.REST, 1.0) * 1.6
            cat_m[BehaviorCategory.PLAY] = cat_m.get(BehaviorCategory.PLAY, 1.0) * 0.3
            cat_m[BehaviorCategory.MOVE] = cat_m.get(BehaviorCategory.MOVE, 1.0) * 0.3
            allow_sleep = True
        elif phase == CircadianPhase.AFTERNOON_FOCUS:
            cat_m[BehaviorCategory.WORK] = cat_m.get(BehaviorCategory.WORK, 1.0) * 1.4
            cat_m[BehaviorCategory.OBSERVE] = cat_m.get(BehaviorCategory.OBSERVE, 1.0) * 1.2
            cat_m[BehaviorCategory.PLAY] = cat_m.get(BehaviorCategory.PLAY, 1.0) * 0.6
        elif phase == CircadianPhase.EVENING_LEISURE:
            cat_m[BehaviorCategory.PLAY] = cat_m.get(BehaviorCategory.PLAY, 1.0) * 1.4
            cat_m[BehaviorCategory.REST] = cat_m.get(BehaviorCategory.REST, 1.0) * 1.3
            cat_m[BehaviorCategory.WORK] = cat_m.get(BehaviorCategory.WORK, 1.0) * 0.6

        # 2. Agent Active Context
        if context.agent_active:
            reasons.append("agent_active")
            silence_m *= 1.6
            cat_m[BehaviorCategory.PLAY] = cat_m.get(BehaviorCategory.PLAY, 1.0) * 0.2
            cat_m[BehaviorCategory.MOVE] = cat_m.get(BehaviorCategory.MOVE, 1.0) * 0.2
            cat_m[BehaviorCategory.WORK] = cat_m.get(BehaviorCategory.WORK, 1.0) * 1.2
            cat_m[BehaviorCategory.OBSERVE] = cat_m.get(BehaviorCategory.OBSERVE, 1.0) * 1.2

        # 3. Sanctuary Mode Context
        if context.sanctuary_active:
            reasons.append("sanctuary_active")
            silence_m *= 3.0
            quiet_m *= 1.5
            cat_m[BehaviorCategory.PLAY] = 0.0
            cat_m[BehaviorCategory.MOVE] = 0.0
            cat_m[BehaviorCategory.WORK] = cat_m.get(BehaviorCategory.WORK, 1.0) * 0.4
            cat_m[BehaviorCategory.REST] = cat_m.get(BehaviorCategory.REST, 1.0) * 1.5
            allowed_sets.append(
                frozenset({
                    BehaviorCategory.REST,
                    BehaviorCategory.OBSERVE,
                    BehaviorCategory.SLEEP,
                })
            )

        # 4. Mini Mode Docked Context
        if context.mini_mode_docked:
            reasons.append("mini_mode_docked")
            cat_m[BehaviorCategory.MOVE] = 0.0
            # Autonomous behaviors cannot move pet out of edge dock
            allowed_sets.append(
                frozenset({
                    BehaviorCategory.IDLE,
                    BehaviorCategory.OBSERVE,
                    BehaviorCategory.WORK,
                    BehaviorCategory.REST,
                    BehaviorCategory.SLEEP,
                })
            )

        # 5. Feeder Input Active Context
        if context.feeder_active:
            reasons.append("feeder_active")
            silence_m *= 2.5
            cat_m[BehaviorCategory.MOVE] = 0.0
            cat_m[BehaviorCategory.PLAY] = 0.0

        # 6. Speech Bubble Active Context
        if context.bubble_active:
            reasons.append("bubble_active")
            silence_m *= 2.0
            cat_m[BehaviorCategory.MOVE] = 0.0

        # 7. Confirmed Relationship Insights (Weak & Bounded)
        if context.active_confirmed_insights:
            reasons.append("relationship_insights")
            for insight in context.active_confirmed_insights:
                s = insight.lower()
                if "focus" in s or "deep_work" in s or "专注" in s:
                    cat_m[BehaviorCategory.WORK] = min(
                        cls.MAX_CAT_MULT, cat_m.get(BehaviorCategory.WORK, 1.0) * 1.15
                    )
                if "quiet" in s or "calm" in s or "安静" in s:
                    silence_m = min(cls.MAX_SILENCE_MULT, silence_m * 1.15)
                if "active" in s or "playful" in s or "活力" in s:
                    cat_m[BehaviorCategory.PLAY] = min(
                        cls.MAX_CAT_MULT, cat_m.get(BehaviorCategory.PLAY, 1.0) * 1.15
                    )

        # Apply Clamping (Safety Bound Invariant)
        clamped_silence = max(cls.MIN_SILENCE_MULT, min(cls.MAX_SILENCE_MULT, silence_m))
        clamped_quiet = max(cls.MIN_QUIET_MULT, min(cls.MAX_QUIET_MULT, quiet_m))
        clamped_cats = {
            cat: max(cls.MIN_CAT_MULT, min(cls.MAX_CAT_MULT, mult))
            for cat, mult in cat_m.items()
        }

        # Intersect allowed categories if any were restricted
        final_allowed: frozenset[BehaviorCategory] | None = None
        if allowed_sets:
            intersected = set(allowed_sets[0])
            for cat_set in allowed_sets[1:]:
                intersected.intersection_update(cat_set)
            final_allowed = frozenset(intersected)

        return SchedulerModulation(
            silence_multiplier=round(clamped_silence, 3),
            quiet_window_multiplier=round(clamped_quiet, 3),
            category_multipliers=clamped_cats,
            allowed_categories=final_allowed,
            allow_autonomous_sleep=allow_sleep,
            reasons=tuple(reasons),
        )
