"""Tests for Life Scheduler and silence-first autonomous rhythm (Phase 2.5 WP-5)."""

from __future__ import annotations

import inspect
import os
import random
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.body.contracts import PetState
from src.body.window import PetWindow
from src.core.behavior import (
    AUTONOMOUS_CATEGORIES,
    ActivityRegistry,
    BehaviorCategory,
    BehaviorIntent,
    BehaviorPriority,
    BehaviorRequest,
    LifeScheduler,
    PetActivity,
    PetManifest,
    SchedulerConfig,
    VisualBinding,
    load_pet_manifest,
)

# Ensure QApplication is initialized for offscreen tests
_app = QApplication.instance()
if _app is None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _app = QApplication([])


def _make_mock_registry() -> ActivityRegistry:
    acts = [
        PetActivity(
            id="act_idle", category=BehaviorCategory.IDLE, visual=VisualBinding(ref="idle")
        ),
        PetActivity(
            id="act_work", category=BehaviorCategory.WORK, visual=VisualBinding(ref="work")
        ),
        PetActivity(
            id="act_observe", category=BehaviorCategory.OBSERVE, visual=VisualBinding(ref="look")
        ),
        PetActivity(
            id="act_play", category=BehaviorCategory.PLAY, visual=VisualBinding(ref="play")
        ),
        PetActivity(
            id="act_move", category=BehaviorCategory.MOVE, visual=VisualBinding(ref="walk")
        ),
    ]
    manifest = PetManifest(
        schema_version=2,
        id="mock_pet",
        name="Mock Pet",
        capabilities=frozenset(a.category for a in acts),
        activities=tuple(acts),
    )
    return ActivityRegistry(manifest)


def test_quiet_window_enforces_silence() -> None:
    current_time = [1000.0]

    def fake_clock() -> float:
        return current_time[0]

    config = SchedulerConfig(minimum_quiet_sec=15.0)
    scheduler = LifeScheduler(config=config, clock=fake_clock)
    registry = _make_mock_registry()

    # Finish an activity at t = 1000.0
    scheduler.record_activity_finished(1000.0)

    # Consider at t = 1005.0 (< 1015.0 quiet window) -> must return None (Silence)
    current_time[0] = 1005.0
    intent, delay = scheduler.consider(registry)
    assert intent is None
    assert delay >= 10.0  # At least the remaining quiet window


def test_deterministic_seed_produces_identical_sequence() -> None:
    clock_fn = lambda: 100.0  # noqa: E731
    registry = _make_mock_registry()

    # Scheduler A with seed 42
    sched_a = LifeScheduler(
        SchedulerConfig(minimum_quiet_sec=0.0, silence_weight=1.0),
        clock=clock_fn,
        rng=random.Random(42),
    )
    results_a = [sched_a.consider(registry)[0] for _ in range(10)]

    # Scheduler B with seed 42
    sched_b = LifeScheduler(
        SchedulerConfig(minimum_quiet_sec=0.0, silence_weight=1.0),
        clock=clock_fn,
        rng=random.Random(42),
    )
    results_b = [sched_b.consider(registry)[0] for _ in range(10)]

    assert [i.category if i else None for i in results_a] == [
        i.category if i else None for i in results_b
    ]


def test_anti_repetition_suppresses_consecutive_same_category() -> None:
    registry = _make_mock_registry()
    scheduler = LifeScheduler(
        SchedulerConfig(minimum_quiet_sec=0.0, silence_weight=0.0),
        rng=random.Random(123),
    )

    # Record WORK as last started activity
    # Record WORK as last started activity
    scheduler.record_activity_started(BehaviorCategory.WORK)
    last_category = BehaviorCategory.WORK

    # Across 15 consecutive choices, no category is ever picked consecutively
    for _ in range(15):
        intent, _ = scheduler.consider(registry)
        assert intent is not None
        assert intent.category != last_category
        last_category = intent.category
        scheduler.record_activity_started(intent.category)

def test_move_frequency_limiter() -> None:
    registry = _make_mock_registry()
    config = SchedulerConfig(
        minimum_quiet_sec=0.0,
        silence_weight=0.0,
        max_moves_in_history=2,
    )
    scheduler = LifeScheduler(config=config, rng=random.Random(77))

    # Pre-fill history with 2 recent moves
    scheduler.record_activity_started(BehaviorCategory.MOVE)
    scheduler.record_activity_started(BehaviorCategory.OBSERVE)
    scheduler.record_activity_started(BehaviorCategory.MOVE)

    # Consider 10 times: MOVE must be suppressed because recent moves >= 2
    for _ in range(10):
        intent, _ = scheduler.consider(registry)
        if intent is not None:
            assert intent.category != BehaviorCategory.MOVE


def test_scheduler_never_produces_greet_react_or_sleep() -> None:
    registry = _make_mock_registry()
    scheduler = LifeScheduler(
        SchedulerConfig(minimum_quiet_sec=0.0, silence_weight=0.0),
        rng=random.Random(999),
    )

    forbidden_categories = {
        BehaviorCategory.GREET,
        BehaviorCategory.REACT,
        BehaviorCategory.SLEEP,
    }

    for _ in range(30):
        intent, _ = scheduler.consider(registry)
        if intent is not None:
            assert intent.category not in forbidden_categories
            assert intent.category in AUTONOMOUS_CATEGORIES


def test_scheduler_respects_busy_active_request() -> None:
    registry = _make_mock_registry()
    scheduler = LifeScheduler(SchedulerConfig(minimum_quiet_sec=0.0))

    # Construct an active request at P2_DIRECT_INTERACTION
    res = registry.resolve(BehaviorIntent(category=BehaviorCategory.GREET))
    active_req = BehaviorRequest(
        request_id="req_busy",
        intent=BehaviorIntent(category=BehaviorCategory.GREET),
        resolution=res,
        priority=BehaviorPriority.P2_DIRECT_INTERACTION,
    )

    # When active request is busy, scheduler stays quiet (None) without storm
    intent, delay = scheduler.consider(registry, active_request=active_req)
    assert intent is None
    assert delay > 0.0


def test_cross_pet_vasu_and_calico_identical_scheduler() -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    calico_dir = Path("assets") / "pets" / "calico"

    vasu_registry = ActivityRegistry(load_pet_manifest(vasu_dir))
    calico_registry = ActivityRegistry(load_pet_manifest(calico_dir))

    # LifeScheduler is completely pet-agnostic
    _ = LifeScheduler()

    # Generate an autonomous intent for WORK
    intent = BehaviorIntent(category=BehaviorCategory.WORK)

    vasu_res = vasu_registry.resolve(intent)
    calico_res = calico_registry.resolve(intent)

    # Same intent -> Vasu resolves to pondering, Calico resolves to its own work activity
    assert vasu_res.primary_activity is not None
    assert vasu_res.primary_activity.id == "pondering"

    assert calico_res.primary_activity is not None
    assert "calico_" in calico_res.primary_activity.id


def test_history_bounded_capacity() -> None:
    config = SchedulerConfig(history_capacity=5)
    scheduler = LifeScheduler(config=config)

    for i in range(10):
        scheduler.record_activity_started(
            category=BehaviorCategory.OBSERVE,
            duration_sec=float(i),
            activity_id=f"act_{i}",
        )

    assert len(scheduler.history) == 5
    # Oldest entries were discarded
    assert [e.activity_id for e in scheduler.history] == [
        "act_5",
        "act_6",
        "act_7",
        "act_8",
        "act_9",
    ]


def test_architecture_regression_zero_pet_specific_contamination_in_scheduler() -> None:
    """Verify LifeScheduler source code contains zero pet names or asset filenames."""
    import src.core.behavior.scheduler as sched_module

    source_lines = [
        line
        for line in inspect.getsource(sched_module).splitlines()
        if not line.strip().startswith(("from typing", "import typing"))
    ]
    cleaned_source = "\n".join(source_lines).lower()
    forbidden = [
        "vasu",
        "calico",
        "pondering",
        "look_around",
        "waving",
        "jumping",
        "typing",
        "review",
        "sweeping",
        ".png",
        ".gif",
        ".webp",
    ]
    for token in forbidden:
        assert token not in cleaned_source, (
            f"LifeScheduler source code is contaminated with '{token}'"
        )


def test_vasu_runtime_smoke_with_life_scheduler(tmp_path: Path) -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    window = PetWindow(
        pet_dir=vasu_dir,
        scale=1.0,
        position_config_path=tmp_path / "body_position.json",
    )

    # 1. Vasu now has an active LifeScheduler
    assert hasattr(window, "scheduler")
    assert isinstance(window.scheduler, LifeScheduler)
    assert window._autonomous_timer.isActive()

    # 2. Native idle is maintained as baseline
    assert window._native_idle_frames is not None
    assert window.current_state == PetState.IDLE

    # 3. Simulate autonomous consideration triggering WORK
    intent = BehaviorIntent(category=BehaviorCategory.WORK)
    resolution = window._registry.resolve(intent)
    assert resolution.candidates

    # Pre-condition: Native idle is active
    assert window._native_idle_active is True

    # Start autonomous routine directly simulating timer fire
    window._start_autonomous_routine()

    # Finish autonomous routine returns to IDLE
    window._finish_autonomous_routine()
    assert window.current_state == PetState.IDLE
    assert window._in_autonomous_routine is False

    window.close()
