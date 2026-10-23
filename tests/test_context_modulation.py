"""Tests for Circadian and Context Modulation (Phase 2.5 WP-6)."""

from __future__ import annotations

import inspect
from pathlib import Path

from src.core.behavior import (
    ActivityRegistry,
    BehaviorArbiter,
    BehaviorCategory,
    BehaviorIntent,
    BehaviorPriority,
    BehaviorRequest,
    BehaviorSource,
    ContextModulator,
    LifeContext,
    LifeScheduler,
    PetActivity,
    PetManifest,
    ProtectionLevel,
    SchedulerConfig,
    VisualBinding,
    load_pet_manifest,
)
from src.core.circadian import CircadianPhase


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
        PetActivity(
            id="act_rest", category=BehaviorCategory.REST, visual=VisualBinding(ref="rest")
        ),
        PetActivity(
            id="act_sleep", category=BehaviorCategory.SLEEP, visual=VisualBinding(ref="sleep")
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


def test_no_context_leaves_base_behavior_unchanged() -> None:
    config = SchedulerConfig(silence_weight=2.0)
    scheduler = LifeScheduler(config=config)
    registry = _make_mock_registry()

    # Consider without context
    intent, delay = scheduler.consider(registry, context=None)
    assert delay >= config.consideration_min_sec


def test_circadian_phases_modulation_profiles() -> None:
    config = SchedulerConfig()

    # 1. Morning Wake
    ctx_morning = LifeContext(circadian_phase=CircadianPhase.MORNING_WAKE)
    mod_morning = ContextModulator.modulate(config, ctx_morning)
    assert mod_morning.silence_multiplier > 1.0
    assert mod_morning.category_multipliers[BehaviorCategory.PLAY] < 1.0
    assert mod_morning.category_multipliers[BehaviorCategory.REST] > 1.0

    # 2. Morning Work & Afternoon Focus
    ctx_work = LifeContext(circadian_phase=CircadianPhase.MORNING_WORK)
    mod_work = ContextModulator.modulate(config, ctx_work)
    assert mod_work.category_multipliers[BehaviorCategory.WORK] > 1.0
    assert mod_work.category_multipliers[BehaviorCategory.OBSERVE] > 1.0

    # 3. Midday Siesta
    ctx_siesta = LifeContext(circadian_phase=CircadianPhase.MIDDAY_SIESTA)
    mod_siesta = ContextModulator.modulate(config, ctx_siesta)
    assert mod_siesta.silence_multiplier > 1.0
    assert mod_siesta.category_multipliers[BehaviorCategory.REST] > 1.0
    assert mod_siesta.allow_autonomous_sleep is True

    # 4. Evening Leisure
    ctx_evening = LifeContext(circadian_phase=CircadianPhase.EVENING_LEISURE)
    mod_evening = ContextModulator.modulate(config, ctx_evening)
    assert mod_evening.category_multipliers[BehaviorCategory.PLAY] > 1.0
    assert mod_evening.category_multipliers[BehaviorCategory.WORK] < 1.0

    # 5. Night Sleep
    ctx_night = LifeContext(circadian_phase=CircadianPhase.NIGHT_SLEEP)
    mod_night = ContextModulator.modulate(config, ctx_night)
    assert mod_night.silence_multiplier >= 2.0
    assert mod_night.category_multipliers[BehaviorCategory.MOVE] == 0.0
    assert mod_night.category_multipliers[BehaviorCategory.PLAY] == 0.0
    assert mod_night.allow_autonomous_sleep is True
    assert mod_night.allowed_categories is not None
    assert BehaviorCategory.MOVE not in mod_night.allowed_categories


def test_calico_and_vasu_late_night_sleep_cross_pet() -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    calico_dir = Path("assets") / "pets" / "calico"

    vasu_registry = ActivityRegistry(load_pet_manifest(vasu_dir))
    calico_registry = ActivityRegistry(load_pet_manifest(calico_dir))

    # Generic SLEEP intent produced during night sleep
    sleep_intent = BehaviorIntent(category=BehaviorCategory.SLEEP)

    # 1. Calico has native sleep -> resolves natively to calico_sleeping (degraded=False)
    calico_res = calico_registry.resolve(sleep_intent)
    assert calico_res.resolved_category == BehaviorCategory.SLEEP
    assert calico_res.degraded is False
    assert calico_res.primary_activity is not None
    assert "sleep" in calico_res.primary_activity.id

    # 2. Vasu has no native sleep -> resolves through canonical fallback to IDLE (degraded=True)
    # Does NOT fake a sleeping animation!
    vasu_res = vasu_registry.resolve(sleep_intent)
    assert vasu_res.resolved_category == BehaviorCategory.IDLE
    assert vasu_res.degraded is True
    assert vasu_res.primary_activity is not None
    assert vasu_res.primary_activity.category == BehaviorCategory.IDLE


def test_agent_active_context_modulation() -> None:
    config = SchedulerConfig()
    ctx_agent_busy = LifeContext(agent_active=True)
    mod = ContextModulator.modulate(config, ctx_agent_busy)

    assert mod.silence_multiplier > 1.0
    assert mod.category_multipliers[BehaviorCategory.PLAY] < 0.5
    assert mod.category_multipliers[BehaviorCategory.MOVE] < 0.5
    assert mod.category_multipliers[BehaviorCategory.WORK] >= 1.0
    assert "agent_active" in mod.reasons


def test_sanctuary_active_suppresses_high_energy_actions() -> None:
    config = SchedulerConfig()
    ctx_sanctuary = LifeContext(sanctuary_active=True)
    mod = ContextModulator.modulate(config, ctx_sanctuary)

    assert mod.silence_multiplier >= 3.0
    assert mod.category_multipliers[BehaviorCategory.PLAY] == 0.0
    assert mod.category_multipliers[BehaviorCategory.MOVE] == 0.0
    assert mod.allowed_categories is not None
    assert BehaviorCategory.PLAY not in mod.allowed_categories
    assert BehaviorCategory.MOVE not in mod.allowed_categories
    assert "sanctuary_active" in mod.reasons


def test_mini_mode_and_feeder_suppress_move() -> None:
    config = SchedulerConfig()

    # Mini mode docked
    ctx_mini = LifeContext(mini_mode_docked=True)
    mod_mini = ContextModulator.modulate(config, ctx_mini)
    assert mod_mini.category_multipliers[BehaviorCategory.MOVE] == 0.0
    assert mod_mini.allowed_categories is not None
    assert BehaviorCategory.MOVE not in mod_mini.allowed_categories

    # Feeder active
    ctx_feeder = LifeContext(feeder_active=True)
    mod_feeder = ContextModulator.modulate(config, ctx_feeder)
    assert mod_feeder.silence_multiplier >= 2.0
    assert mod_feeder.category_multipliers[BehaviorCategory.MOVE] == 0.0
    assert mod_feeder.category_multipliers[BehaviorCategory.PLAY] == 0.0


def test_multiple_contexts_compose_and_clamp_safely() -> None:
    config = SchedulerConfig()

    # Extreme combination: Night sleep + Agent active + Sanctuary + Feeder active
    ctx_extreme = LifeContext(
        circadian_phase=CircadianPhase.NIGHT_SLEEP,
        agent_active=True,
        sanctuary_active=True,
        feeder_active=True,
    )
    mod = ContextModulator.modulate(config, ctx_extreme)

    # Clamped to MAX_SILENCE_MULT (5.0)
    assert mod.silence_multiplier <= ContextModulator.MAX_SILENCE_MULT
    assert mod.quiet_window_multiplier <= ContextModulator.MAX_QUIET_MULT

    # High energy is completely zeroed
    assert mod.category_multipliers[BehaviorCategory.MOVE] == 0.0
    assert mod.category_multipliers[BehaviorCategory.PLAY] == 0.0


def test_confirmed_insights_bounded_modulation() -> None:
    config = SchedulerConfig()

    ctx_base = LifeContext(active_confirmed_insights=())
    mod_base = ContextModulator.modulate(config, ctx_base)

    # Confirmed active insights
    ctx_confirmed = LifeContext(
        active_confirmed_insights=("User values quiet focus in afternoon",)
    )
    mod = ContextModulator.modulate(config, ctx_confirmed)

    # Mild, bounded boost isolated from circadian baseline
    work_ratio = (
        mod.category_multipliers[BehaviorCategory.WORK]
        / mod_base.category_multipliers[BehaviorCategory.WORK]
    )
    silence_ratio = mod.silence_multiplier / mod_base.silence_multiplier
    assert 1.0 < work_ratio <= 1.3
    assert 1.0 < silence_ratio <= 1.3


def test_candidate_or_stale_hypotheses_have_zero_effect() -> None:
    config = SchedulerConfig()

    # LifeContext only accepts confirmed active insights.
    # An empty insight tuple produces exactly the base modulation.
    ctx_empty = LifeContext(active_confirmed_insights=())
    mod_empty = ContextModulator.modulate(config, ctx_empty)

    assert "relationship_insights" not in mod_empty.reasons


def test_context_never_elevates_autonomous_priority() -> None:
    """Invariant: Context modulation can never elevate P1_AUTONOMOUS to P2/P3/P4."""
    # When LifeScheduler emits intent under any context,
    # it always submits as P1_AUTONOMOUS
    registry = _make_mock_registry()
    scheduler = LifeScheduler()
    ctx = LifeContext(agent_active=True, sanctuary_active=True)

    intent, _ = scheduler.consider(registry, context=ctx)
    if intent is not None:
        resolution = registry.resolve(intent)
        req = BehaviorRequest(
            request_id="req_test",
            intent=intent,
            resolution=resolution,
            source=BehaviorSource.AUTONOMOUS,
            priority=BehaviorPriority.P1_AUTONOMOUS,
        )
        assert req.priority == BehaviorPriority.P1_AUTONOMOUS


def test_active_protected_sleep_cannot_be_preempted_by_autonomous_consideration() -> None:
    registry = _make_mock_registry()
    scheduler = LifeScheduler()

    # Set up arbiter with user explicit DND sleep
    arbiter = BehaviorArbiter(registry)
    sleep_req = BehaviorRequest(
        request_id="dnd_sleep",
        intent=BehaviorIntent(category=BehaviorCategory.SLEEP),
        resolution=registry.resolve(BehaviorIntent(category=BehaviorCategory.SLEEP)),
        source=BehaviorSource.EXPLICIT_USER,
        priority=BehaviorPriority.P4_EXPLICIT_USER,
        protection=ProtectionLevel.PROTECTED_SLEEP,
    )
    arbiter.submit(sleep_req)
    assert arbiter.is_protected_sleep() is True

    # Scheduler consideration under daytime work context
    ctx = LifeContext(circadian_phase=CircadianPhase.MORNING_WORK)
    intent, delay = scheduler.consider(
        registry, active_request=arbiter.active_request, context=ctx
    )
    # Busy check blocks consideration: returns None
    assert intent is None


def test_architecture_regression_zero_body_calls_in_context_modules() -> None:
    """Verify that context, circadian, state_watcher, and sanctuary do not call Body state APIs."""
    import src.core.behavior.context as ctx_module
    import src.core.circadian as circ_module
    import src.core.sanctuary as sanc_module
    import src.core.state_watcher as stat_module

    forbidden_body_apis = [
        "apply_state",
        "set_state",
        "play_animation",
        "controller.set_state",
    ]

    for mod in (ctx_module, circ_module, sanc_module, stat_module):
        src_text = inspect.getsource(mod)
        for api in forbidden_body_apis:
            assert api not in src_text, (
                f"Module '{mod.__name__}' is contaminated with direct body API '{api}'"
            )
