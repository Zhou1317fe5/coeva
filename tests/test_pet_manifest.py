"""Tests for Pet Manifest and Capability Contract (Phase 2.5 WP-1)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from src.core.behavior import (
    OPTIONAL_BEHAVIOR_CATEGORIES,
    ActivityTrait,
    BehaviorCategory,
    BehaviorDirection,
    BehaviorIntent,
    LoopMode,
    PetActivity,
    PetManifest,
    VisualBinding,
    load_manifest_from_dict,
    load_pet_manifest,
    validate_pet_directory,
    validate_pet_manifest,
)


def _make_valid_minimal_pet() -> PetManifest:
    """Helper creating a minimal valid pet satisfying baseline requirements."""
    idle_act = PetActivity(
        id="idle_base",
        category=BehaviorCategory.IDLE,
        visual=VisualBinding(ref="idle"),
        traits=frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY}),
    )
    sleep_act = PetActivity(
        id="sleep_base",
        category=BehaviorCategory.SLEEP,
        visual=VisualBinding(ref="sleep"),
        traits=frozenset({ActivityTrait.QUIET, ActivityTrait.LOW_ENERGY}),
    )
    move_act = PetActivity(
        id="move_base",
        category=BehaviorCategory.MOVE,
        visual=VisualBinding(ref="walk"),
        traits=frozenset({ActivityTrait.ACTIVE, ActivityTrait.LOCOMOTIVE}),
    )
    return PetManifest(
        schema_version=2,
        id="mini_pet",
        name="Mini Pet",
        capabilities=frozenset({
            BehaviorCategory.IDLE,
            BehaviorCategory.SLEEP,
            BehaviorCategory.MOVE,
        }),
        activities=(idle_act, sleep_act, move_act),
    )


def test_valid_minimal_pet() -> None:
    manifest = _make_valid_minimal_pet()
    result = validate_pet_manifest(manifest)
    assert result.valid is True
    assert len(result.errors) == 0
    assert "Status: VALID" in result.summary()


def test_valid_rich_pet() -> None:
    acts = [
        PetActivity(
            id="idle_breathe",
            category=BehaviorCategory.IDLE,
            visual=VisualBinding(ref="idle"),
            traits=frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY}),
        ),
        PetActivity(
            id="idle_blink",
            category=BehaviorCategory.IDLE,
            visual=VisualBinding(ref="blink"),
            traits=frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY}),
        ),
        PetActivity(
            id="nap",
            category=BehaviorCategory.SLEEP,
            visual=VisualBinding(ref="sleep"),
            traits=frozenset({ActivityTrait.LOW_ENERGY, ActivityTrait.QUIET}),
        ),
        PetActivity(
            id="walk_right",
            category=BehaviorCategory.MOVE,
            visual=VisualBinding(ref="walk_right"),
            traits=frozenset({ActivityTrait.ACTIVE, ActivityTrait.LOCOMOTIVE}),
            direction=BehaviorDirection.RIGHT,
        ),
        PetActivity(
            id="walk_left",
            category=BehaviorCategory.MOVE,
            visual=VisualBinding(ref="walk_right", mirror=True),
            traits=frozenset({ActivityTrait.ACTIVE, ActivityTrait.LOCOMOTIVE}),
            direction=BehaviorDirection.LEFT,
        ),
        PetActivity(
            id="typing",
            category=BehaviorCategory.WORK,
            visual=VisualBinding(ref="type"),
            traits=frozenset({ActivityTrait.FOCUSED, ActivityTrait.STATIONARY}),
        ),
        PetActivity(
            id="pondering",
            category=BehaviorCategory.OBSERVE,
            visual=VisualBinding(ref="look"),
            traits=frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY}),
        ),
        PetActivity(
            id="tail_chase",
            category=BehaviorCategory.PLAY,
            visual=VisualBinding(ref="play"),
            traits=frozenset({ActivityTrait.ACTIVE, ActivityTrait.CASUAL}),
        ),
        PetActivity(
            id="wave_paw",
            category=BehaviorCategory.GREET,
            visual=VisualBinding(ref="wave"),
            traits=frozenset({ActivityTrait.SOCIAL, ActivityTrait.STATIONARY}),
            loop=LoopMode.ONCE,
            duration_ms=1200,
        ),
        PetActivity(
            id="startled",
            category=BehaviorCategory.REACT,
            visual=VisualBinding(ref="jump"),
            traits=frozenset({ActivityTrait.CASUAL, ActivityTrait.STATIONARY}),
            loop=LoopMode.ONCE,
        ),
        PetActivity(
            id="relax",
            category=BehaviorCategory.REST,
            visual=VisualBinding(ref="lie_down"),
            traits=frozenset({ActivityTrait.QUIET, ActivityTrait.LOW_ENERGY}),
        ),
    ]
    manifest = PetManifest(
        schema_version=2,
        id="rich_pet",
        name="Rich Pet",
        capabilities=frozenset(a.category for a in acts),
        activities=tuple(acts),
    )
    result = validate_pet_manifest(manifest)
    assert result.valid is True
    assert len(result.errors) == 0


def test_missing_required_capability_idle() -> None:
    # A pet with no IDLE activity must fail validation
    manifest = PetManifest(
        schema_version=2,
        id="bad_pet",
        name="No Idle Pet",
        capabilities=frozenset({BehaviorCategory.SLEEP}),
        activities=(
            PetActivity(
                id="sleep_only",
                category=BehaviorCategory.SLEEP,
                visual=VisualBinding(ref="sleep"),
            ),
        ),
    )
    result = validate_pet_manifest(manifest)
    assert result.valid is False
    assert any("required capability 'idle' has no valid activity" in e for e in result.errors)


def test_optional_capabilities_missing_is_valid() -> None:
    # A pet declaring only minimal required capabilities has all optional capabilities missing.
    # This must be 100% valid per INV-B5.
    manifest = _make_valid_minimal_pet()
    for opt_cap in OPTIONAL_BEHAVIOR_CATEGORIES:
        assert not manifest.has_capability(opt_cap)
    result = validate_pet_manifest(manifest)
    assert result.valid is True


def test_capability_activity_mismatch() -> None:
    # 1. Declared capability has no activities
    manifest_unimplemented_cap = PetManifest(
        schema_version=2,
        id="mismatch_1",
        name="Mismatch 1",
        capabilities=frozenset({
            BehaviorCategory.IDLE,
            BehaviorCategory.SLEEP,
            BehaviorCategory.WORK,  # declared but no activity
        }),
        activities=(
            PetActivity(
                id="idle_act",
                category=BehaviorCategory.IDLE,
                visual=VisualBinding(ref="idle"),
            ),
            PetActivity(
                id="sleep_act",
                category=BehaviorCategory.SLEEP,
                visual=VisualBinding(ref="sleep"),
            ),
        ),
    )
    result1 = validate_pet_manifest(manifest_unimplemented_cap)
    assert result1.valid is False
    assert any("declared capability 'work' has no activities defined" in e for e in result1.errors)

    # 2. Activity category not declared in capabilities
    manifest_undeclared_act = PetManifest(
        schema_version=2,
        id="mismatch_2",
        name="Mismatch 2",
        capabilities=frozenset({
            BehaviorCategory.IDLE,
            BehaviorCategory.SLEEP,
        }),
        activities=(
            PetActivity(
                id="idle_act",
                category=BehaviorCategory.IDLE,
                visual=VisualBinding(ref="idle"),
            ),
            PetActivity(
                id="sleep_act",
                category=BehaviorCategory.SLEEP,
                visual=VisualBinding(ref="sleep"),
            ),
            PetActivity(
                id="secret_play",
                category=BehaviorCategory.PLAY,  # not declared!
                visual=VisualBinding(ref="play"),
            ),
        ),
    )
    result2 = validate_pet_manifest(manifest_undeclared_act)
    assert result2.valid is False
    assert any("is not in declared capabilities" in e for e in result2.errors)


def test_duplicate_activity_id() -> None:
    manifest = PetManifest(
        schema_version=2,
        id="dup_pet",
        name="Duplicate Activity Pet",
        capabilities=frozenset({BehaviorCategory.IDLE, BehaviorCategory.SLEEP}),
        activities=(
            PetActivity(
                id="common_id",
                category=BehaviorCategory.IDLE,
                visual=VisualBinding(ref="idle"),
            ),
            PetActivity(
                id="common_id",  # duplicate!
                category=BehaviorCategory.SLEEP,
                visual=VisualBinding(ref="sleep"),
            ),
        ),
    )
    result = validate_pet_manifest(manifest)
    assert result.valid is False
    assert any("duplicate activity id 'common_id'" in e for e in result.errors)


def test_invalid_types_and_values() -> None:
    # 1. Invalid weight
    with pytest.raises(ValueError, match="weight must be > 0.0"):
        PetActivity(
            id="act_bad_weight",
            category=BehaviorCategory.IDLE,
            visual=VisualBinding(ref="idle"),
            weight=0.0,
        )

    # 2. Invalid duration
    with pytest.raises(ValueError, match="duration_ms must be positive"):
        PetActivity(
            id="act_bad_duration",
            category=BehaviorCategory.IDLE,
            visual=VisualBinding(ref="idle"),
            duration_ms=-10,
        )

    # 3. Invalid tag ending with image extension (INV-B1 violation)
    with pytest.raises(ValueError, match="INV-B1 violation"):
        PetActivity(
            id="act_bad_tag",
            category=BehaviorCategory.IDLE,
            visual=VisualBinding(ref="idle"),
            tags=("animation.png",),
        )

    # 4. Invalid trait type
    with pytest.raises(TypeError, match="All traits must be ActivityTrait instances"):
        PetActivity(
            id="act_bad_trait",
            category=BehaviorCategory.IDLE,
            visual=VisualBinding(ref="idle"),
            traits=frozenset({"random_trait"}),  # type: ignore[arg-type]
        )


def test_visual_reference_existence_and_mirroring(tmp_path: Path) -> None:
    pet_dir = tmp_path / "custom_pet"
    pet_dir.mkdir()

    # Create one actual asset file
    assets_dir = pet_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "walk.apng").write_text("dummy")

    # Activity references existing file with mirror=True
    act_right = PetActivity(
        id="walk_right",
        category=BehaviorCategory.MOVE,
        visual=VisualBinding(ref="walk.apng", format="apng", mirror=False),
        direction=BehaviorDirection.RIGHT,
    )
    act_left = PetActivity(
        id="walk_left",
        category=BehaviorCategory.MOVE,
        visual=VisualBinding(ref="walk.apng", format="apng", mirror=True),
        direction=BehaviorDirection.LEFT,
    )
    act_idle = PetActivity(
        id="idle",
        category=BehaviorCategory.IDLE,
        visual=VisualBinding(ref="walk.apng", format="apng"),
    )
    act_missing = PetActivity(
        id="missing_visual",
        category=BehaviorCategory.WORK,
        visual=VisualBinding(ref="non_existent.apng", format="apng"),
    )

    manifest = PetManifest(
        schema_version=2,
        id="custom_pet",
        name="Custom Pet",
        capabilities=frozenset({
            BehaviorCategory.IDLE,
            BehaviorCategory.MOVE,
            BehaviorCategory.WORK,
        }),
        activities=(act_right, act_left, act_idle, act_missing),
    )

    result = validate_pet_manifest(manifest, pet_dir)
    assert result.valid is False
    assert any("visual ref 'non_existent.apng' not found" in e for e in result.errors)


def test_fallback_compatibility_warning_for_sleep() -> None:
    # A pet declaring only IDLE and MOVE without SLEEP:
    # SLEEP falls back to IDLE per WP-0, so manifest is VALID with a diagnostic warning.
    idle_act = PetActivity(
        id="idle_only",
        category=BehaviorCategory.IDLE,
        visual=VisualBinding(ref="idle"),
    )
    manifest = PetManifest(
        schema_version=2,
        id="awake_pet",
        name="Awake Pet",
        capabilities=frozenset({BehaviorCategory.IDLE}),
        activities=(idle_act,),
    )
    result = validate_pet_manifest(manifest)
    assert result.valid is True
    assert any("falling back to 'idle'" in w for w in result.warnings)


def test_v1_compatibility_vasu() -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    assert vasu_dir.is_dir()

    manifest = load_pet_manifest(vasu_dir)
    assert manifest.id == "vasu"
    assert manifest.schema_version == 2
    assert manifest.has_capability(BehaviorCategory.IDLE)
    assert manifest.has_capability(BehaviorCategory.MOVE)
    assert manifest.has_capability(BehaviorCategory.WORK)
    assert manifest.has_capability(BehaviorCategory.GREET)
    assert len(manifest.activities) >= 8

    # Validate against directory
    result = validate_pet_directory(vasu_dir)
    assert result.valid is True
    assert len(result.errors) == 0


def test_v1_compatibility_calico() -> None:
    calico_dir = Path("assets") / "pets" / "calico"
    assert calico_dir.is_dir()

    manifest = load_pet_manifest(calico_dir)
    assert manifest.id == "calico"
    assert manifest.schema_version == 2
    assert manifest.has_capability(BehaviorCategory.IDLE)
    assert manifest.has_capability(BehaviorCategory.SLEEP)
    assert manifest.has_capability(BehaviorCategory.MOVE)
    assert manifest.has_capability(BehaviorCategory.WORK)
    assert manifest.has_capability(BehaviorCategory.REST)

    result = validate_pet_directory(calico_dir)
    assert result.valid is True
    assert len(result.errors) == 0


def test_immutable_runtime_model() -> None:
    manifest = _make_valid_minimal_pet()
    with pytest.raises(dataclasses.FrozenInstanceError):
        manifest.name = "Mutated"  # type: ignore[misc]

    act = manifest.activities[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        act.category = BehaviorCategory.WORK  # type: ignore[misc]

    with pytest.raises(dataclasses.FrozenInstanceError):
        act.visual.ref = "mutated_ref"  # type: ignore[misc]


def test_v2_json_roundtrip_parsing() -> None:
    raw_data = {
        "schema_version": 2,
        "id": "sample_fox",
        "name": "Sample Fox",
        "capabilities": ["idle", "sleep", "move", "work"],
        "activities": [
            {
                "id": "fox_idle",
                "category": "idle",
                "traits": ["quiet", "stationary"],
                "direction": "none",
                "visual": {"ref": "fox_idle.png", "format": "png"},
                "loop": "loop",
                "interruptible": True,
                "weight": 1.0,
            },
            {
                "id": "fox_sleep",
                "category": "sleep",
                "traits": ["quiet", "low_energy"],
                "direction": "none",
                "visual": {"ref": "fox_sleep.png", "format": "png"},
                "loop": "loop",
                "interruptible": False,
                "weight": 1.0,
            },
            {
                "id": "fox_walk",
                "category": "move",
                "traits": ["active", "locomotive"],
                "direction": "right",
                "visual": {"ref": "fox_walk.png", "format": "png"},
                "loop": "loop",
                "interruptible": True,
                "weight": 1.0,
            },
            {
                "id": "fox_hunt",
                "category": "work",
                "traits": ["focused", "active"],
                "direction": "none",
                "visual": {"ref": "fox_hunt.png", "format": "png"},
                "loop": "once",
                "duration_ms": 3500,
                "weight": 2.0,
            },
        ],
    }

    manifest = load_manifest_from_dict(raw_data)
    assert manifest.id == "sample_fox"
    assert manifest.schema_version == 2
    assert manifest.capabilities == {
        BehaviorCategory.IDLE,
        BehaviorCategory.SLEEP,
        BehaviorCategory.MOVE,
        BehaviorCategory.WORK,
    }
    assert len(manifest.activities) == 4
    hunt_act = next(a for a in manifest.activities if a.id == "fox_hunt")
    assert hunt_act.duration_ms == 3500
    assert hunt_act.weight == 2.0
    assert hunt_act.loop == LoopMode.ONCE


def test_architecture_regression_zero_scheduler_domain_contamination() -> None:
    """Architectural Regression Guard (INV-B1, INV-B2, INV-M2).

    Scans the runtime BehaviorIntent definition and its fields to verify that
    it has ZERO references to pet-specific activity IDs, names, or asset file types.
    """
    intent_fields = {f.name for f in dataclasses.fields(BehaviorIntent)}

    # 1. BehaviorIntent fields must NOT include pet-specific activity IDs or asset paths
    forbidden_field_substrings = [
        "activity_id",
        "pet_activity",
        "vasu",
        "calico",
        "asset",
        "animation",
        "spritesheet",
        "row",
        "gif",
        "png",
        "webp",
        "file",
    ]
    for field_name in intent_fields:
        for forbidden in forbidden_field_substrings:
            assert forbidden not in field_name.lower(), (
                f"Scheduler BehaviorIntent field '{field_name}' contaminated with '{forbidden}'"
            )

    # 2. Creating a standard BehaviorIntent must only require generic semantics
    intent = BehaviorIntent(
        category=BehaviorCategory.WORK,
        preferred_traits=(ActivityTrait.QUIET, ActivityTrait.STATIONARY),
    )
    assert intent.category == BehaviorCategory.WORK
    assert intent.preferred_traits == (ActivityTrait.QUIET, ActivityTrait.STATIONARY)
    # Ensure neither "vasu" nor "calico" appear anywhere in repr or str
    assert "vasu" not in repr(intent).lower()
    assert "calico" not in repr(intent).lower()
    assert ".png" not in repr(intent).lower()
