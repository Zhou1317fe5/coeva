"""Tests for Activity Registry and Semantic Fallback Resolver (Phase 2.5 WP-3)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.core.behavior import (
    ActivityRegistry,
    ActivityResolution,
    ActivityTrait,
    BehaviorCategory,
    BehaviorDirection,
    BehaviorIntent,
    PetActivity,
    PetManifest,
    ResolvedCandidate,
    VisualBinding,
    load_pet_manifest,
)


def _build_test_manifest() -> PetManifest:
    """Construct an isolated test manifest with controlled activities for testing resolver rules."""
    acts = [
        # IDLE
        PetActivity(
            id="idle_quiet",
            category=BehaviorCategory.IDLE,
            visual=VisualBinding(ref="idle_q"),
            traits=frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY}),
            weight=1.0,
        ),
        PetActivity(
            id="idle_active",
            category=BehaviorCategory.IDLE,
            visual=VisualBinding(ref="idle_a"),
            traits=frozenset({ActivityTrait.ACTIVE, ActivityTrait.STATIONARY}),
            weight=1.5,
        ),
        # OBSERVE
        PetActivity(
            id="look_casual",
            category=BehaviorCategory.OBSERVE,
            visual=VisualBinding(ref="look"),
            traits=frozenset({ActivityTrait.CASUAL, ActivityTrait.STATIONARY}),
            weight=1.0,
        ),
        # MOVE: only RIGHT natively, but with mirror=True on visual
        PetActivity(
            id="walk_east",
            category=BehaviorCategory.MOVE,
            visual=VisualBinding(ref="walk_r", mirror=True),
            traits=frozenset({ActivityTrait.ACTIVE, ActivityTrait.LOCOMOTIVE}),
            direction=BehaviorDirection.RIGHT,
            weight=1.0,
        ),
    ]
    return PetManifest(
        schema_version=2,
        id="mock_pet",
        name="Mock Pet",
        capabilities=frozenset({
            BehaviorCategory.IDLE,
            BehaviorCategory.OBSERVE,
            BehaviorCategory.MOVE,
        }),
        activities=tuple(acts),
    )


def test_registry_initialization_and_type_check() -> None:
    manifest = _build_test_manifest()
    registry = ActivityRegistry(manifest)
    assert registry.manifest == manifest

    with pytest.raises(TypeError, match="manifest must be PetManifest"):
        ActivityRegistry("invalid")  # type: ignore[arg-type]


def test_activities_for_and_supports_category() -> None:
    manifest = _build_test_manifest()
    registry = ActivityRegistry(manifest)

    assert registry.supports_category(BehaviorCategory.IDLE) is True
    assert registry.supports_category(BehaviorCategory.OBSERVE) is True
    assert registry.supports_category(BehaviorCategory.MOVE) is True
    assert registry.supports_category(BehaviorCategory.WORK) is False
    assert registry.supports_category(BehaviorCategory.SLEEP) is False

    idle_acts = registry.activities_for(BehaviorCategory.IDLE)
    assert len(idle_acts) == 2
    assert {a.id for a in idle_acts} == {"idle_quiet", "idle_active"}

    with pytest.raises(TypeError, match="category must be BehaviorCategory"):
        registry.activities_for("idle")  # type: ignore[arg-type]


def test_native_match_and_trait_preference_ranking() -> None:
    manifest = _build_test_manifest()
    registry = ActivityRegistry(manifest)

    # 1. Intent asking for QUIET trait
    intent_quiet = BehaviorIntent(
        category=BehaviorCategory.IDLE,
        preferred_traits=(ActivityTrait.QUIET,),
    )
    res_quiet = registry.resolve(intent_quiet)
    assert isinstance(res_quiet, ActivityResolution)
    assert res_quiet.requested_category == BehaviorCategory.IDLE
    assert res_quiet.resolved_category == BehaviorCategory.IDLE
    assert res_quiet.degraded is False
    assert res_quiet.no_op is False
    assert res_quiet.reason == "native_match"
    assert len(res_quiet.candidates) == 2

    # Top candidate should be idle_quiet because of +2.0 trait match
    top_cand = res_quiet.candidates[0]
    assert isinstance(top_cand, ResolvedCandidate)
    assert top_cand.activity.id == "idle_quiet"
    assert res_quiet.primary_activity == top_cand.activity

    # 2. Intent asking for ACTIVE trait
    intent_active = BehaviorIntent(
        category=BehaviorCategory.IDLE,
        preferred_traits=(ActivityTrait.ACTIVE,),
    )
    res_active = registry.resolve(intent_active)
    assert res_active.candidates[0].activity.id == "idle_active"


def test_direction_resolution_and_mirroring() -> None:
    manifest = _build_test_manifest()
    registry = ActivityRegistry(manifest)

    # Request MOVE RIGHT (native exact match)
    intent_right = BehaviorIntent(
        category=BehaviorCategory.MOVE,
        direction=BehaviorDirection.RIGHT,
    )
    res_right = registry.resolve(intent_right)
    assert res_right.resolved_category == BehaviorCategory.MOVE
    assert len(res_right.candidates) == 1
    assert res_right.candidates[0].mirror_required is False
    assert res_right.primary_mirror_required is False
    assert res_right.candidates[0].activity.id == "walk_east"

    # Request MOVE LEFT (mirrored match via walk_east which has visual.mirror=True)
    intent_left = BehaviorIntent(
        category=BehaviorCategory.MOVE,
        direction=BehaviorDirection.LEFT,
    )
    res_left = registry.resolve(intent_left)
    assert res_left.resolved_category == BehaviorCategory.MOVE
    assert len(res_left.candidates) == 1
    assert res_left.candidates[0].mirror_required is True
    assert res_left.primary_mirror_required is True
    assert res_left.candidates[0].activity.id == "walk_east"


def test_semantic_fallback_single_hop_and_multi_hop() -> None:
    manifest = _build_test_manifest()
    registry = ActivityRegistry(manifest)

    # WORK is unsupported.
    # In WP-0: WORK -> (OBSERVE, IDLE)
    # Manifest has OBSERVE, so it must fall back to OBSERVE!
    intent_work = BehaviorIntent(category=BehaviorCategory.WORK)
    res_work = registry.resolve(intent_work)
    assert res_work.requested_category == BehaviorCategory.WORK
    assert res_work.resolved_category == BehaviorCategory.OBSERVE
    assert res_work.degraded is True
    assert res_work.no_op is False
    assert res_work.fallback_path == (BehaviorCategory.WORK, BehaviorCategory.OBSERVE)
    assert res_work.primary_activity is not None
    assert res_work.primary_activity.id == "look_casual"

    # SLEEP is unsupported.
    # In WP-0: SLEEP -> (IDLE,)
    # Manifest has IDLE, so it falls back to IDLE.
    intent_sleep = BehaviorIntent(category=BehaviorCategory.SLEEP)
    res_sleep = registry.resolve(intent_sleep)
    assert res_sleep.requested_category == BehaviorCategory.SLEEP
    assert res_sleep.resolved_category == BehaviorCategory.IDLE
    assert res_sleep.degraded is True
    assert res_sleep.fallback_path == (BehaviorCategory.SLEEP, BehaviorCategory.IDLE)


def test_move_special_hold_position_when_unsupported() -> None:
    # Build a pet that has NO MOVE activities
    idle_act = PetActivity(
        id="idle_lonely",
        category=BehaviorCategory.IDLE,
        visual=VisualBinding(ref="idle"),
    )
    stationary_pet = PetManifest(
        schema_version=2,
        id="still_pet",
        name="Still Pet",
        capabilities=frozenset({BehaviorCategory.IDLE}),
        activities=(idle_act,),
    )
    registry = ActivityRegistry(stationary_pet)

    # When MOVE is requested on a pet with no MOVE support:
    # Must yield no_op=True, hold position, and NEVER fake walk or fallback to IDLE!
    intent_move = BehaviorIntent(category=BehaviorCategory.MOVE)
    res_move = registry.resolve(intent_move)

    assert res_move.requested_category == BehaviorCategory.MOVE
    assert res_move.resolved_category is None
    assert res_move.candidates == ()
    assert res_move.primary_activity is None
    assert res_move.no_op is True
    assert res_move.reason == "move_not_supported_hold_position"


def test_vasu_v2_reference_pet_resolution() -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    vasu_manifest = load_pet_manifest(vasu_dir)
    registry = ActivityRegistry(vasu_manifest)

    # 1. IDLE
    res_idle = registry.resolve(BehaviorIntent(category=BehaviorCategory.IDLE))
    assert res_idle.resolved_category == BehaviorCategory.IDLE
    assert res_idle.degraded is False
    # Top idle candidate should be idle_native (weight 2.0)
    assert res_idle.primary_activity is not None
    assert res_idle.primary_activity.id == "idle_native"

    # 2. WORK -> resolves natively to pondering
    res_work = registry.resolve(BehaviorIntent(category=BehaviorCategory.WORK))
    assert res_work.resolved_category == BehaviorCategory.WORK
    assert res_work.degraded is False
    assert res_work.primary_activity is not None
    assert res_work.primary_activity.id == "pondering"

    # 3. OBSERVE -> resolves natively to look_around
    res_obs = registry.resolve(BehaviorIntent(category=BehaviorCategory.OBSERVE))
    assert res_obs.resolved_category == BehaviorCategory.OBSERVE
    assert res_obs.primary_activity is not None
    assert res_obs.primary_activity.id == "look_around"

    # 4. MOVE RIGHT
    res_right = registry.resolve(
        BehaviorIntent(category=BehaviorCategory.MOVE, direction=BehaviorDirection.RIGHT)
    )
    assert res_right.primary_activity is not None
    assert res_right.primary_activity.id == "run_right"
    assert res_right.primary_mirror_required is False

    # 5. MOVE LEFT
    res_left = registry.resolve(
        BehaviorIntent(category=BehaviorCategory.MOVE, direction=BehaviorDirection.LEFT)
    )
    assert res_left.primary_activity is not None
    assert res_left.primary_activity.id == "run_left"
    assert res_left.primary_mirror_required is False

    # 6. SLEEP -> Vasu has no native SLEEP, so it falls back to IDLE
    res_sleep = registry.resolve(BehaviorIntent(category=BehaviorCategory.SLEEP))
    assert res_sleep.requested_category == BehaviorCategory.SLEEP
    assert res_sleep.resolved_category == BehaviorCategory.IDLE
    assert res_sleep.degraded is True
    assert res_sleep.primary_activity is not None
    assert res_sleep.primary_activity.category == BehaviorCategory.IDLE

    # 7. REST -> falls back to IDLE
    res_rest = registry.resolve(BehaviorIntent(category=BehaviorCategory.REST))
    assert res_rest.resolved_category == BehaviorCategory.IDLE
    assert res_rest.degraded is True


def test_calico_cross_pet_resolution_and_zero_hardcoding() -> None:
    calico_dir = Path("assets") / "pets" / "calico"
    calico_manifest = load_pet_manifest(calico_dir)
    vasu_dir = Path("assets") / "pets" / "vasu"
    vasu_manifest = load_pet_manifest(vasu_dir)

    calico_registry = ActivityRegistry(calico_manifest)
    vasu_registry = ActivityRegistry(vasu_manifest)

    # Send the exact same generic BehaviorIntent(category=WORK) to both pets
    generic_work_intent = BehaviorIntent(
        category=BehaviorCategory.WORK,
        preferred_traits=(ActivityTrait.FOCUSED,),
    )

    vasu_res = vasu_registry.resolve(generic_work_intent)
    calico_res = calico_registry.resolve(generic_work_intent)

    # Both resolve successfully to WORK without degrading
    assert vasu_res.resolved_category == BehaviorCategory.WORK
    assert calico_res.resolved_category == BehaviorCategory.WORK
    assert vasu_res.degraded is False
    assert calico_res.degraded is False

    # But their activities are completely different!
    assert vasu_res.primary_activity is not None
    assert calico_res.primary_activity is not None
    assert vasu_res.primary_activity.id == "pondering"
    assert "calico_" in calico_res.primary_activity.id

    # Send the exact same generic BehaviorIntent(category=SLEEP)
    generic_sleep_intent = BehaviorIntent(category=BehaviorCategory.SLEEP)
    vasu_sleep = vasu_registry.resolve(generic_sleep_intent)
    calico_sleep = calico_registry.resolve(generic_sleep_intent)

    # Vasu has no native SLEEP -> degraded=True to IDLE
    assert vasu_sleep.resolved_category == BehaviorCategory.IDLE
    assert vasu_sleep.degraded is True

    # Calico has native sleeping -> degraded=False to SLEEP
    assert calico_sleep.resolved_category == BehaviorCategory.SLEEP
    assert calico_sleep.degraded is False
    assert calico_sleep.primary_activity is not None
    assert calico_sleep.primary_activity.category == BehaviorCategory.SLEEP


def test_architecture_regression_zero_pet_specific_contamination_in_registry_source() -> None:
    """Scan ActivityRegistry source code to ensure ZERO pet names or assets exist."""
    import src.core.behavior.registry as reg_module

    source_code = inspect.getsource(reg_module)

    forbidden_tokens = [
        "vasu",
        "calico",
        "pondering",
        "look_around",
        "waving",
        "jumping",
        "stumble",
        "spritesheet.webp",
        "theme.json",
        ".png",
        ".gif",
        ".webp",
    ]

    for token in forbidden_tokens:
        assert token not in source_code.lower(), (
            f"ActivityRegistry source code is contaminated with pet-specific token '{token}'"
        )


def test_repeated_resolution_is_pure_and_idempotent() -> None:
    manifest = _build_test_manifest()
    registry = ActivityRegistry(manifest)
    intent = BehaviorIntent(
        category=BehaviorCategory.WORK,
        preferred_traits=(ActivityTrait.QUIET,),
    )

    res1 = registry.resolve(intent)
    res2 = registry.resolve(intent)

    assert res1 == res2
    assert res1.candidates == res2.candidates
