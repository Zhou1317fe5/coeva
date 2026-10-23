"""Tests for Pet Behavior Semantics (Phase 2.5 WP-0)."""

from __future__ import annotations

import dataclasses

import pytest

from src.core.behavior import (
    OPTIONAL_BEHAVIOR_CATEGORIES,
    REQUIRED_BEHAVIOR_CATEGORIES,
    SEMANTIC_FALLBACK_CHAINS,
    ActivityTrait,
    BehaviorCategory,
    BehaviorDirection,
    BehaviorIntent,
    resolve_semantic_fallback,
)


def test_behavior_category_coverage_and_partition() -> None:
    expected_categories = {
        "idle",
        "rest",
        "sleep",
        "work",
        "observe",
        "play",
        "move",
        "greet",
        "react",
    }
    actual_categories = {c.value for c in BehaviorCategory}
    assert actual_categories == expected_categories
    assert len(BehaviorCategory) == 9

    assert REQUIRED_BEHAVIOR_CATEGORIES == {
        BehaviorCategory.IDLE,
        BehaviorCategory.SLEEP,
        BehaviorCategory.MOVE,
    }
    assert OPTIONAL_BEHAVIOR_CATEGORIES == {
        BehaviorCategory.REST,
        BehaviorCategory.WORK,
        BehaviorCategory.OBSERVE,
        BehaviorCategory.PLAY,
        BehaviorCategory.GREET,
        BehaviorCategory.REACT,
    }

    assert REQUIRED_BEHAVIOR_CATEGORIES.isdisjoint(OPTIONAL_BEHAVIOR_CATEGORIES)
    assert REQUIRED_BEHAVIOR_CATEGORIES | OPTIONAL_BEHAVIOR_CATEGORIES == set(BehaviorCategory)


def test_activity_traits_coverage() -> None:
    expected_traits = {
        "quiet",
        "active",
        "stationary",
        "locomotive",
        "social",
        "solitary",
        "focused",
        "casual",
        "low_energy",
        "medium_energy",
        "high_energy",
    }
    actual_traits = {t.value for t in ActivityTrait}
    assert actual_traits == expected_traits
    assert len(ActivityTrait) == 11


def test_behavior_direction() -> None:
    assert {d.value for d in BehaviorDirection} == {"none", "left", "right"}


def test_behavior_intent_defaults_and_immutability() -> None:
    intent = BehaviorIntent(category=BehaviorCategory.IDLE)
    assert intent.category == BehaviorCategory.IDLE
    assert intent.source == "life_scheduler"
    assert intent.preferred_traits == ()
    assert intent.direction == BehaviorDirection.NONE
    assert intent.intensity == 1.0
    assert intent.tags == ()

    with pytest.raises(dataclasses.FrozenInstanceError):
        intent.category = BehaviorCategory.WORK  # type: ignore[misc]


def test_behavior_intent_custom_values_and_coercion() -> None:
    intent = BehaviorIntent(
        category=BehaviorCategory.WORK,
        source="circadian",
        preferred_traits=[ActivityTrait.QUIET, ActivityTrait.FOCUSED],  # type: ignore[arg-type]
        direction=BehaviorDirection.RIGHT,
        intensity=0.8,
        tags=["desk_companion"],  # type: ignore[arg-type]
    )
    assert intent.category == BehaviorCategory.WORK
    assert intent.source == "circadian"
    assert intent.preferred_traits == (ActivityTrait.QUIET, ActivityTrait.FOCUSED)
    assert intent.direction == BehaviorDirection.RIGHT
    assert intent.intensity == 0.8
    assert intent.tags == ("desk_companion",)


def test_behavior_intent_intensity_bounds() -> None:
    with pytest.raises(ValueError, match="intensity must be between 0.0 and 1.0"):
        BehaviorIntent(category=BehaviorCategory.IDLE, intensity=-0.1)

    with pytest.raises(ValueError, match="intensity must be between 0.0 and 1.0"):
        BehaviorIntent(category=BehaviorCategory.IDLE, intensity=1.05)


def test_behavior_intent_type_validations() -> None:
    with pytest.raises(TypeError, match="category must be BehaviorCategory"):
        BehaviorIntent(category="work")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="direction must be BehaviorDirection"):
        BehaviorIntent(category=BehaviorCategory.MOVE, direction="left")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="All preferred_traits must be ActivityTrait instances"):
        BehaviorIntent(
            category=BehaviorCategory.WORK,
            preferred_traits=(ActivityTrait.QUIET, "invalid_trait"),  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="All tags must be strings"):
        BehaviorIntent(category=BehaviorCategory.REACT, tags=(123,))  # type: ignore[arg-type]


def test_behavior_intent_inv_b1_asset_disallowed_in_tags() -> None:
    with pytest.raises(ValueError, match="INV-B1 violation"):
        BehaviorIntent(category=BehaviorCategory.WORK, tags=("running.gif",))

    with pytest.raises(ValueError, match="INV-B1 violation"):
        BehaviorIntent(category=BehaviorCategory.IDLE, tags=("idle_blink.PNG",))

    with pytest.raises(ValueError, match="INV-B1 violation"):
        BehaviorIntent(category=BehaviorCategory.MOVE, tags=("walk.webp",))


def test_behavior_intent_schema_has_no_asset_or_pet_specific_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(BehaviorIntent)}
    forbidden_terms = {"asset", "animation", "spritesheet", "row", "gif", "frame", "pet_activity"}
    for field in field_names:
        assert not any(term in field.lower() for term in forbidden_terms)


def test_fallback_chains_completeness_and_acyclic() -> None:
    assert set(SEMANTIC_FALLBACK_CHAINS.keys()) == set(BehaviorCategory)

    for cat, chain in SEMANTIC_FALLBACK_CHAINS.items():
        assert cat not in chain, f"Category {cat} cannot fall back to itself"
        for target in chain:
            assert isinstance(target, BehaviorCategory)

    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.WORK] == (
        BehaviorCategory.OBSERVE,
        BehaviorCategory.IDLE,
    )
    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.PLAY] == (
        BehaviorCategory.OBSERVE,
        BehaviorCategory.IDLE,
    )
    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.REST] == (BehaviorCategory.IDLE,)
    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.OBSERVE] == (BehaviorCategory.IDLE,)
    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.GREET] == (
        BehaviorCategory.REACT,
        BehaviorCategory.IDLE,
    )
    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.REACT] == (BehaviorCategory.IDLE,)
    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.SLEEP] == (BehaviorCategory.IDLE,)
    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.MOVE] == ()
    assert SEMANTIC_FALLBACK_CHAINS[BehaviorCategory.IDLE] == ()


def test_resolve_semantic_fallback() -> None:
    # 1. Directly supported category returns itself
    def all_supported(_cat: BehaviorCategory) -> bool:
        return True

    assert resolve_semantic_fallback(BehaviorCategory.WORK, all_supported) == BehaviorCategory.WORK

    # 2. Only minimal required supported: WORK -> OBSERVE (unsupported) -> IDLE (supported)
    minimal_supported = {BehaviorCategory.IDLE, BehaviorCategory.SLEEP, BehaviorCategory.MOVE}
    assert (
        resolve_semantic_fallback(BehaviorCategory.WORK, lambda c: c in minimal_supported)
        == BehaviorCategory.IDLE
    )

    # 3. Intermediate fallback: WORK with OBSERVE supported returns OBSERVE
    work_observe_supported = {BehaviorCategory.IDLE, BehaviorCategory.OBSERVE}
    assert (
        resolve_semantic_fallback(BehaviorCategory.WORK, lambda c: c in work_observe_supported)
        == BehaviorCategory.OBSERVE
    )

    # 4. GREET -> REACT -> IDLE
    greet_react_supported = {BehaviorCategory.REACT, BehaviorCategory.IDLE}
    assert (
        resolve_semantic_fallback(BehaviorCategory.GREET, lambda c: c in greet_react_supported)
        == BehaviorCategory.REACT
    )

    # 5. MOVE unsupported holds position: never falls back
    assert (
        resolve_semantic_fallback(BehaviorCategory.MOVE, lambda c: c in {BehaviorCategory.IDLE})
        is None
    )

    # 6. Nothing supported in chain
    assert resolve_semantic_fallback(BehaviorCategory.WORK, lambda _c: False) is None
