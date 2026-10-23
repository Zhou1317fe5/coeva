"""Tests for Behavior Arbiter and Interruption Policy (Phase 2.5 WP-4)."""

from __future__ import annotations

import inspect

from src.core.behavior import (
    ActivityRegistry,
    ActivityResolution,
    ArbiterAction,
    BehaviorArbiter,
    BehaviorCategory,
    BehaviorIntent,
    BehaviorPriority,
    BehaviorRequest,
    BehaviorSource,
    PetActivity,
    PetManifest,
    ProtectionLevel,
    ResolvedCandidate,
    VisualBinding,
)


def _make_dummy_resolution(category: BehaviorCategory, act_id: str = "act_1") -> ActivityResolution:
    act = PetActivity(
        id=act_id,
        category=category,
        visual=VisualBinding(ref="dummy"),
    )
    return ActivityResolution(
        requested_category=category,
        resolved_category=category,
        candidates=(ResolvedCandidate(activity=act),),
        fallback_path=(category,),
    )


def _make_test_arbiter(clock_time: float = 1000.0) -> tuple[BehaviorArbiter, list[float]]:
    """Create an Arbiter backed by a controlled fake clock."""
    time_holder = [clock_time]

    def fake_clock() -> float:
        return time_holder[0]

    acts = [
        PetActivity(
            id="idle_base", category=BehaviorCategory.IDLE, visual=VisualBinding(ref="idle")
        ),
        PetActivity(
            id="sleep_base", category=BehaviorCategory.SLEEP, visual=VisualBinding(ref="sleep")
        ),
        PetActivity(
            id="move_base", category=BehaviorCategory.MOVE, visual=VisualBinding(ref="walk")
        ),
        PetActivity(
            id="work_base", category=BehaviorCategory.WORK, visual=VisualBinding(ref="work")
        ),
        PetActivity(
            id="greet_base", category=BehaviorCategory.GREET, visual=VisualBinding(ref="wave")
        ),
        PetActivity(
            id="react_base", category=BehaviorCategory.REACT, visual=VisualBinding(ref="react")
        ),
    ]
    manifest = PetManifest(
        schema_version=2,
        id="test_pet",
        name="Test Pet",
        capabilities=frozenset(a.category for a in acts),
        activities=tuple(acts),
    )
    registry = ActivityRegistry(manifest)
    arbiter = BehaviorArbiter(registry, clock=fake_clock)
    return arbiter, time_holder


def test_clean_start_and_empty_arbiter() -> None:
    arbiter, _ = _make_test_arbiter()
    assert arbiter.active_request is None
    assert arbiter.suspended_request is None

    req = BehaviorRequest(
        request_id="req_ambient_1",
        intent=BehaviorIntent(category=BehaviorCategory.IDLE),
        resolution=_make_dummy_resolution(BehaviorCategory.IDLE),
        source=BehaviorSource.AMBIENT,
        priority=BehaviorPriority.P0_AMBIENT,
    )
    decision = arbiter.submit(req)
    assert decision.accepted is True
    assert decision.action == ArbiterAction.START
    assert decision.reason == "clean_start"
    assert arbiter.active_request == req


def test_priority_ordering_and_preemption() -> None:
    arbiter, _ = _make_test_arbiter()

    # P0 Ambient
    req_p0 = BehaviorRequest(
        request_id="req_p0",
        intent=BehaviorIntent(category=BehaviorCategory.IDLE),
        resolution=_make_dummy_resolution(BehaviorCategory.IDLE),
        priority=BehaviorPriority.P0_AMBIENT,
    )
    assert arbiter.submit(req_p0).accepted is True

    # P1 Autonomous preempts P0
    req_p1 = BehaviorRequest(
        request_id="req_p1",
        intent=BehaviorIntent(category=BehaviorCategory.WORK),
        resolution=_make_dummy_resolution(BehaviorCategory.WORK),
        priority=BehaviorPriority.P1_AUTONOMOUS,
    )
    dec_p1 = arbiter.submit(req_p1)
    assert dec_p1.accepted is True
    assert dec_p1.action == ArbiterAction.INTERRUPT_AND_START
    assert dec_p1.interrupted_request_id == "req_p0"
    assert arbiter.active_request == req_p1

    # P0 Ambient rejected while P1 is running
    req_p0_late = BehaviorRequest(
        request_id="req_p0_late",
        intent=BehaviorIntent(category=BehaviorCategory.IDLE),
        resolution=_make_dummy_resolution(BehaviorCategory.IDLE),
        priority=BehaviorPriority.P0_AMBIENT,
    )
    dec_p0 = arbiter.submit(req_p0_late)
    assert dec_p0.accepted is False
    assert dec_p0.action == ArbiterAction.REJECT
    assert dec_p0.reason == "lower_priority"


def test_protected_sleep_blocks_hover_and_ambient() -> None:
    # CASE 2 & CASE 3
    arbiter, _ = _make_test_arbiter()

    # User explicitly puts pet to sleep with DND protection
    req_sleep = BehaviorRequest(
        request_id="req_user_sleep",
        intent=BehaviorIntent(category=BehaviorCategory.SLEEP),
        resolution=_make_dummy_resolution(BehaviorCategory.SLEEP),
        source=BehaviorSource.EXPLICIT_USER,
        priority=BehaviorPriority.P4_EXPLICIT_USER,
        protection=ProtectionLevel.PROTECTED_SLEEP,
        interruptible=False,
    )
    dec_sleep = arbiter.submit(req_sleep)
    assert dec_sleep.accepted is True
    assert arbiter.is_protected_sleep() is True

    # Mouse hover (P2) is REJECTED
    req_hover = BehaviorRequest(
        request_id="req_hover",
        intent=BehaviorIntent(category=BehaviorCategory.GREET),
        resolution=_make_dummy_resolution(BehaviorCategory.GREET),
        source=BehaviorSource.DIRECT_INTERACTION,
        priority=BehaviorPriority.P2_DIRECT_INTERACTION,
    )
    dec_hover = arbiter.submit(req_hover)
    assert dec_hover.accepted is False
    assert dec_hover.action == ArbiterAction.REJECT
    assert dec_hover.reason == "protected_sleep_active"
    assert arbiter.active_request == req_sleep

    # Ambient micro-action (P0) is REJECTED
    req_ambient = BehaviorRequest(
        request_id="req_ambient",
        intent=BehaviorIntent(category=BehaviorCategory.IDLE),
        resolution=_make_dummy_resolution(BehaviorCategory.IDLE),
        source=BehaviorSource.AMBIENT,
        priority=BehaviorPriority.P0_AMBIENT,
    )
    dec_amb = arbiter.submit(req_ambient)
    assert dec_amb.accepted is False
    assert dec_amb.reason == "protected_sleep_active"


def test_protected_sleep_interrupted_by_explicit_wake() -> None:
    # CASE 7
    arbiter, _ = _make_test_arbiter()

    req_sleep = BehaviorRequest(
        request_id="req_user_sleep",
        intent=BehaviorIntent(category=BehaviorCategory.SLEEP),
        resolution=_make_dummy_resolution(BehaviorCategory.SLEEP),
        source=BehaviorSource.EXPLICIT_USER,
        priority=BehaviorPriority.P4_EXPLICIT_USER,
        protection=ProtectionLevel.PROTECTED_SLEEP,
    )
    arbiter.submit(req_sleep)
    assert arbiter.is_protected_sleep() is True

    # Explicit user wake (P4)
    req_wake = BehaviorRequest(
        request_id="req_user_wake",
        intent=BehaviorIntent(category=BehaviorCategory.IDLE),
        resolution=_make_dummy_resolution(BehaviorCategory.IDLE),
        source=BehaviorSource.EXPLICIT_USER,
        priority=BehaviorPriority.P4_EXPLICIT_USER,
        protection=ProtectionLevel.UNPROTECTED,
    )
    dec_wake = arbiter.submit(req_wake)
    assert dec_wake.accepted is True
    assert arbiter.is_protected_sleep() is False
    assert arbiter.active_request == req_wake


def test_drag_preempts_autonomous_and_blocks_hover() -> None:
    # CASE 4 & CASE 5
    arbiter, _ = _make_test_arbiter()

    # Autonomous routine running
    req_auto = BehaviorRequest(
        request_id="req_auto_work",
        intent=BehaviorIntent(category=BehaviorCategory.WORK),
        resolution=_make_dummy_resolution(BehaviorCategory.WORK),
        priority=BehaviorPriority.P1_AUTONOMOUS,
    )
    arbiter.submit(req_auto)

    # User drags pet (P4, PROTECTED_INTERACTION)
    req_drag = BehaviorRequest(
        request_id="req_drag_move",
        intent=BehaviorIntent(category=BehaviorCategory.MOVE),
        resolution=_make_dummy_resolution(BehaviorCategory.MOVE),
        source=BehaviorSource.EXPLICIT_USER,
        priority=BehaviorPriority.P4_EXPLICIT_USER,
        protection=ProtectionLevel.PROTECTED_INTERACTION,
    )
    dec_drag = arbiter.submit(req_drag)
    assert dec_drag.accepted is True
    assert dec_drag.action == ArbiterAction.INTERRUPT_AND_START
    assert dec_drag.interrupted_request_id == "req_auto_work"

    # Hover event during drag is REJECTED
    req_hover = BehaviorRequest(
        request_id="req_hover_during_drag",
        intent=BehaviorIntent(category=BehaviorCategory.GREET),
        resolution=_make_dummy_resolution(BehaviorCategory.GREET),
        priority=BehaviorPriority.P2_DIRECT_INTERACTION,
    )
    dec_hover = arbiter.submit(req_hover)
    assert dec_hover.accepted is False
    assert dec_hover.reason == "protected_interaction_active"


def test_drag_release_settles_to_idle_without_resuming_short_autonomous() -> None:
    # CASE 6
    arbiter, _ = _make_test_arbiter()

    req_auto = BehaviorRequest(
        request_id="req_auto_work",
        intent=BehaviorIntent(category=BehaviorCategory.WORK),
        resolution=_make_dummy_resolution(BehaviorCategory.WORK),
        priority=BehaviorPriority.P1_AUTONOMOUS,
        resumable=False,  # Short autonomous is non-resumable per section F
    )
    arbiter.submit(req_auto)

    req_drag = BehaviorRequest(
        request_id="req_drag",
        intent=BehaviorIntent(category=BehaviorCategory.MOVE),
        resolution=_make_dummy_resolution(BehaviorCategory.MOVE),
        priority=BehaviorPriority.P4_EXPLICIT_USER,
    )
    arbiter.submit(req_drag)

    # User releases mouse: drag completes
    dec_complete = arbiter.complete("req_drag")
    assert dec_complete.accepted is True
    assert dec_complete.action == ArbiterAction.START
    assert dec_complete.reason == "settle_to_baseline_idle"
    assert arbiter.active_request is None
    assert arbiter.suspended_request is None


def test_stale_completion_timer_ignored() -> None:
    # CASE 1 & CASE 8: Stale Timer Safety
    arbiter, _ = _make_test_arbiter()

    # Step 1: Hover greeting starts (P2)
    req_hover = BehaviorRequest(
        request_id="req_hover_100",
        intent=BehaviorIntent(category=BehaviorCategory.GREET),
        resolution=_make_dummy_resolution(BehaviorCategory.GREET),
        priority=BehaviorPriority.P2_DIRECT_INTERACTION,
        duration_ms=1400,
    )
    arbiter.submit(req_hover)
    assert arbiter.active_request == req_hover

    # Step 2: Slice submitted mid-greeting (P3) -> preempts hover!
    req_slice = BehaviorRequest(
        request_id="req_slice_200",
        intent=BehaviorIntent(category=BehaviorCategory.GREET),
        resolution=_make_dummy_resolution(BehaviorCategory.GREET),
        priority=BehaviorPriority.P3_SAFETY,
        duration_ms=2500,
    )
    dec_slice = arbiter.submit(req_slice)
    assert dec_slice.accepted is True
    assert arbiter.active_request == req_slice

    # Step 3: Old hover timer fires for req_hover_100!
    # Arbiter MUST recognize it as stale and do absolutely nothing!
    dec_stale = arbiter.complete("req_hover_100")
    assert dec_stale.accepted is False
    assert dec_stale.action == ArbiterAction.NO_OP
    assert dec_stale.reason == "stale_completion_ignored"

    # Slice feedback remains active!
    assert arbiter.active_request == req_slice


def test_cooldown_rejection_and_expiration() -> None:
    # CASE 9
    arbiter, time_holder = _make_test_arbiter(clock_time=100.0)

    # First hover greeting
    req1 = BehaviorRequest(
        request_id="req_hover_1",
        intent=BehaviorIntent(category=BehaviorCategory.GREET),
        resolution=_make_dummy_resolution(BehaviorCategory.GREET),
        priority=BehaviorPriority.P2_DIRECT_INTERACTION,
        cooldown_key="hover_greet",
        duration_ms=2000,
    )
    dec1 = arbiter.submit(req1)
    assert dec1.accepted is True
    assert arbiter.is_cooling_down("hover_greet") is True

    # Complete req1
    arbiter.complete("req_hover_1")

    # Second hover greeting immediately (t=100.5s < 102.0s) -> Rejected by cooldown!
    time_holder[0] = 100.5
    req2 = BehaviorRequest(
        request_id="req_hover_2",
        intent=BehaviorIntent(category=BehaviorCategory.GREET),
        resolution=_make_dummy_resolution(BehaviorCategory.GREET),
        priority=BehaviorPriority.P2_DIRECT_INTERACTION,
        cooldown_key="hover_greet",
        duration_ms=2000,
    )
    dec2 = arbiter.submit(req2)
    assert dec2.accepted is False
    assert dec2.action == ArbiterAction.REJECT
    assert dec2.reason == "cooldown_active"

    # Forward time past cooldown (t=102.5s) -> Accepted!
    time_holder[0] = 102.5
    assert arbiter.is_cooling_down("hover_greet") is False
    dec3 = arbiter.submit(req2)
    assert dec3.accepted is True


def test_resumable_request_is_suspended_and_restored() -> None:
    arbiter, _ = _make_test_arbiter()

    # Long reading task that is marked resumable
    req_read = BehaviorRequest(
        request_id="req_reading",
        intent=BehaviorIntent(category=BehaviorCategory.WORK),
        resolution=_make_dummy_resolution(BehaviorCategory.WORK),
        priority=BehaviorPriority.P1_AUTONOMOUS,
        resumable=True,
    )
    arbiter.submit(req_read)
    assert arbiter.active_request == req_read
    assert arbiter.suspended_request is None

    # User clicks/pokes (P2)
    req_poke = BehaviorRequest(
        request_id="req_poke",
        intent=BehaviorIntent(category=BehaviorCategory.REACT),
        resolution=_make_dummy_resolution(BehaviorCategory.REACT),
        priority=BehaviorPriority.P2_DIRECT_INTERACTION,
    )
    arbiter.submit(req_poke)
    assert arbiter.active_request == req_poke
    assert arbiter.suspended_request == req_read

    # Poke completes -> Resumes reading!
    dec_complete = arbiter.complete("req_poke")
    assert dec_complete.accepted is True
    assert dec_complete.action == ArbiterAction.RESUME
    assert dec_complete.reason == "resumed_suspended_behavior"
    assert arbiter.active_request == req_read
    assert arbiter.suspended_request is None


def test_transition_trace_recording() -> None:
    arbiter, time_holder = _make_test_arbiter(clock_time=10.0)

    req = BehaviorRequest(
        request_id="req_trace_test",
        intent=BehaviorIntent(category=BehaviorCategory.IDLE),
        resolution=_make_dummy_resolution(BehaviorCategory.IDLE),
    )
    arbiter.submit(req)
    assert len(arbiter.trace) == 1
    record = arbiter.trace[0]
    assert record.request_id == "req_trace_test"
    assert record.action == ArbiterAction.START
    assert record.timestamp == 10.0


def test_architecture_regression_zero_pet_specific_contamination_in_arbiter_source() -> None:
    """Verify Arbiter source code contains zero pet-specific names or asset extensions."""
    import src.core.behavior.arbiter as arbiter_module

    source_code = inspect.getsource(arbiter_module)
    forbidden_tokens = [
        "vasu",
        "calico",
        "pondering",
        "look_around",
        "waving",
        "jumping",
        "stumble",
        ".png",
        ".gif",
        ".webp",
    ]
    for token in forbidden_tokens:
        assert token not in source_code.lower(), (
            f"BehaviorArbiter source code is contaminated with token '{token}'"
        )
