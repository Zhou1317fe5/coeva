"""Behavior Arbiter and Interruption Policy (Phase 2.5 WP-4).

Coordinates priority classes, interruption, protection levels, cooldowns,
and stale-timer elimination for companion body behaviors.

Invariants:
- Zero pet-specific names or assets in this module.
- Last-Write-Wins is permanently eliminated.
- Explicit user DND sleep cannot be interrupted by ambient/hover.
- Stale completion timers do not clobber newer active states.
- Arbiter is pure admission logic and generates no autonomous behaviors.
"""

from __future__ import annotations

import collections
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from src.core.behavior.manifest import PetActivity
from src.core.behavior.registry import ActivityRegistry, ActivityResolution
from src.core.behavior.semantics import BehaviorIntent


class BehaviorPriority(IntEnum):
    """Semantic priority classes for behavior arbitration."""

    P0_AMBIENT = 0
    P1_AUTONOMOUS = 10
    P2_DIRECT_INTERACTION = 20
    P3_SAFETY = 30
    P4_EXPLICIT_USER = 40


class BehaviorSource(StrEnum):
    """Origin of a behavior request."""

    EXPLICIT_USER = "explicit_user"
    SYSTEM_SAFETY = "system_safety"
    DIRECT_INTERACTION = "direct_interaction"
    AUTONOMOUS = "autonomous"
    AMBIENT = "ambient"


class ProtectionLevel(StrEnum):
    """Protection semantics against external interruptions."""

    UNPROTECTED = "unprotected"
    PROTECTED_SLEEP = "protected_sleep"
    PROTECTED_INTERACTION = "protected_interaction"


class ArbiterAction(StrEnum):
    """Action outcome from arbitration."""

    START = "start"
    INTERRUPT_AND_START = "interrupt_and_start"
    REJECT = "reject"
    RESUME = "resume"
    NO_OP = "no_op"


@dataclass(frozen=True)
class BehaviorRequest:
    """Strongly typed, immutable runtime request to execute a behavior."""

    request_id: str
    intent: BehaviorIntent
    resolution: ActivityResolution
    source: BehaviorSource = BehaviorSource.AMBIENT
    priority: BehaviorPriority = BehaviorPriority.P0_AMBIENT
    interruptible: bool = True
    resumable: bool = False
    protection: ProtectionLevel = ProtectionLevel.UNPROTECTED
    cooldown_key: str | None = None
    duration_ms: int | None = None
    created_at: float = field(default_factory=time.monotonic)

    @property
    def primary_activity(self) -> PetActivity | None:
        """Top matched activity from the resolution."""
        return self.resolution.primary_activity

    @property
    def primary_mirror_required(self) -> bool:
        """Whether top candidate requires horizontal flipping."""
        return self.resolution.primary_mirror_required


@dataclass(frozen=True)
class BehaviorDecision:
    """Structural decision returned by the Arbiter."""

    accepted: bool
    action: ArbiterAction
    reason: str
    request: BehaviorRequest | None = None
    interrupted_request_id: str | None = None


@dataclass(frozen=True)
class TransitionRecord:
    """Diagnostic trace record of an arbitration event."""

    timestamp: float
    request_id: str
    source: BehaviorSource
    action: ArbiterAction
    reason: str
    previous_request_id: str | None


class BehaviorArbiter:
    """Central authority governing behavior admission, interruption, and completion."""

    def __init__(
        self,
        registry: ActivityRegistry,
        *,
        clock: Callable[[], float] | None = None,
        trace_capacity: int = 100,
    ) -> None:
        if not isinstance(registry, ActivityRegistry):
            msg = f"registry must be ActivityRegistry, got {type(registry).__name__}"
            raise TypeError(msg)

        self._registry = registry
        self._clock = clock or time.monotonic
        self._active_request: BehaviorRequest | None = None
        self._suspended_request: BehaviorRequest | None = None
        self._cooldowns: dict[str, float] = {}
        self._trace: collections.deque[TransitionRecord] = collections.deque(
            maxlen=trace_capacity
        )

    @property
    def registry(self) -> ActivityRegistry:
        """Underlying pet activity registry."""
        return self._registry

    @property
    def active_request(self) -> BehaviorRequest | None:
        """Currently executing behavior request, or None if completely idle."""
        return self._active_request

    @property
    def suspended_request(self) -> BehaviorRequest | None:
        """Single suspended behavior waiting to be resumed, or None."""
        return self._suspended_request

    @property
    def trace(self) -> tuple[TransitionRecord, ...]:
        """Diagnostic transition log."""
        return tuple(self._trace)

    def is_protected_sleep(self) -> bool:
        """Return True if active behavior is user-mandated DND protected sleep."""
        if self._active_request is None:
            return False
        return self._active_request.protection == ProtectionLevel.PROTECTED_SLEEP

    def set_cooldown(self, key: str, duration_sec: float) -> None:
        """Explicitly record a cooldown deadline for a key."""
        now = self._clock()
        self._cooldowns[key] = now + duration_sec

    def is_cooling_down(self, key: str) -> bool:
        """Check if a cooldown key is currently active."""
        deadline = self._cooldowns.get(key)
        if deadline is None:
            return False
        return self._clock() < deadline

    def submit(self, request: BehaviorRequest) -> BehaviorDecision:
        """Arbitrate an incoming behavior request against active state and policies."""
        if not isinstance(request, BehaviorRequest):
            msg = f"request must be BehaviorRequest, got {type(request).__name__}"
            raise TypeError(msg)

        # 1. Cooldown check (explicit user P4 bypasses ambient/interaction cooldowns)
        if (
            request.cooldown_key is not None
            and request.priority < BehaviorPriority.P4_EXPLICIT_USER
        ):
            if self.is_cooling_down(request.cooldown_key):
                decision = BehaviorDecision(
                    accepted=False,
                    action=ArbiterAction.REJECT,
                    reason="cooldown_active",
                    request=request,
                )
                self._record_trace(decision, None)
                return decision

        # 2. If no-op resolution (e.g. MOVE unsupported)
        if request.resolution.no_op:
            decision = BehaviorDecision(
                accepted=False,
                action=ArbiterAction.NO_OP,
                reason=request.resolution.reason or "resolution_no_op",
                request=request,
            )
            self._record_trace(decision, None)
            return decision

        # 3. Active behavior evaluation
        active = self._active_request

        if active is None:
            # Clean start
            self._activate(request)
            decision = BehaviorDecision(
                accepted=True,
                action=ArbiterAction.START,
                reason="clean_start",
                request=request,
            )
            self._record_trace(decision, None)
            return decision

        # Check protected sleep immunity
        if active.protection == ProtectionLevel.PROTECTED_SLEEP:
            if request.priority < BehaviorPriority.P4_EXPLICIT_USER:
                decision = BehaviorDecision(
                    accepted=False,
                    action=ArbiterAction.REJECT,
                    reason="protected_sleep_active",
                    request=request,
                )
                self._record_trace(decision, active.request_id)
                return decision

        # Check protected interaction immunity
        if active.protection == ProtectionLevel.PROTECTED_INTERACTION:
            if request.priority < BehaviorPriority.P4_EXPLICIT_USER:
                decision = BehaviorDecision(
                    accepted=False,
                    action=ArbiterAction.REJECT,
                    reason="protected_interaction_active",
                    request=request,
                )
                self._record_trace(decision, active.request_id)
                return decision

        # Evaluate priority
        if request.priority > active.priority:
            # Higher priority: check if active is interruptible
            if not active.interruptible and request.priority < BehaviorPriority.P4_EXPLICIT_USER:
                decision = BehaviorDecision(
                    accepted=False,
                    action=ArbiterAction.REJECT,
                    reason="active_behavior_not_interruptible",
                    request=request,
                )
                self._record_trace(decision, active.request_id)
                return decision

            # Preempt active! Save as suspended if resumable
            prev_id = active.request_id
            if active.resumable:
                self._suspended_request = active
            else:
                self._suspended_request = None

            self._activate(request)
            decision = BehaviorDecision(
                accepted=True,
                action=ArbiterAction.INTERRUPT_AND_START,
                reason="higher_priority_preempt",
                request=request,
                interrupted_request_id=prev_id,
            )
            self._record_trace(decision, prev_id)
            return decision

        if request.priority == active.priority:
            # Same priority: if duplicate intent and same source, ignore or reject
            if (
                request.intent.category == active.intent.category
                and request.source == active.source
                and request.primary_activity == active.primary_activity
            ):
                decision = BehaviorDecision(
                    accepted=False,
                    action=ArbiterAction.REJECT,
                    reason="duplicate_same_priority_request",
                    request=request,
                )
                self._record_trace(decision, active.request_id)
                return decision

            # Same priority allow replacement (e.g. continuous drag direction updates)
            prev_id = active.request_id
            self._activate(request)
            decision = BehaviorDecision(
                accepted=True,
                action=ArbiterAction.START,
                reason="same_priority_update",
                request=request,
                interrupted_request_id=prev_id,
            )
            self._record_trace(decision, prev_id)
            return decision

        # Lower priority: reject
        decision = BehaviorDecision(
            accepted=False,
            action=ArbiterAction.REJECT,
            reason="lower_priority",
            request=request,
        )
        self._record_trace(decision, active.request_id)
        return decision

    def complete(self, request_id: str) -> BehaviorDecision:
        """Signal that a behavior execution has completed.

        Stale Timer Safety:
        If request_id does not match active_request, this completion is stale and
        must be completely ignored (NO_OP).
        """
        active = self._active_request

        if active is None:
            return BehaviorDecision(
                accepted=False,
                action=ArbiterAction.NO_OP,
                reason="no_active_behavior_to_complete",
            )

        if active.request_id != request_id:
            # Stale timer! Completely ignore.
            return BehaviorDecision(
                accepted=False,
                action=ArbiterAction.NO_OP,
                reason="stale_completion_ignored",
            )

        # Matched active behavior completed!
        self._active_request = None

        # Check if there is a suspended request to resume
        if self._suspended_request is not None:
            resumed = self._suspended_request
            self._suspended_request = None
            self._active_request = resumed

            decision = BehaviorDecision(
                accepted=True,
                action=ArbiterAction.RESUME,
                reason="resumed_suspended_behavior",
                request=resumed,
            )
            self._record_trace(decision, request_id)
            return decision

        # No suspended behavior: settle to idle
        decision = BehaviorDecision(
            accepted=True,
            action=ArbiterAction.START,
            reason="settle_to_baseline_idle",
            request=None,
        )
        self._record_trace(decision, request_id)
        return decision

    def clear(self) -> None:
        """Reset all active and suspended states (used on pet unload/re-init)."""
        self._active_request = None
        self._suspended_request = None
        self._cooldowns.clear()

    def _activate(self, request: BehaviorRequest) -> None:
        """Store active request and record cooldown deadline if applicable."""
        self._active_request = request
        if request.cooldown_key is not None and request.duration_ms is not None:
            cooldown_sec = request.duration_ms / 1000.0
            self.set_cooldown(request.cooldown_key, cooldown_sec)

    def _record_trace(self, decision: BehaviorDecision, prev_id: str | None) -> None:
        """Record arbitration decision into ring buffer."""
        now = self._clock()
        req_id = decision.request.request_id if decision.request else "none"
        source = decision.request.source if decision.request else BehaviorSource.AMBIENT
        self._trace.append(
            TransitionRecord(
                timestamp=now,
                request_id=req_id,
                source=source,
                action=decision.action,
                reason=decision.reason,
                previous_request_id=prev_id,
            )
        )
