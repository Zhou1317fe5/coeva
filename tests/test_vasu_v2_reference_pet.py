"""Tests for Vasu v2 Reference Pet (Phase 2.5 WP-2)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.body.contracts import PetState
from src.body.window import PetWindow
from src.core.behavior import (
    ActivityTrait,
    BehaviorCategory,
    BehaviorDirection,
    LoopMode,
    load_pet_manifest,
    validate_pet_directory,
    validate_pet_manifest,
)

# Ensure QApplication is initialized for offscreen tests
_app = QApplication.instance()
if _app is None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _app = QApplication([])


def test_vasu_v2_manifest_loaded_directly_not_via_v1_adapter() -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    assert vasu_dir.is_dir()

    manifest = load_pet_manifest(vasu_dir)
    assert manifest.id == "vasu"
    assert manifest.name == "Vasu"
    assert manifest.schema_version == 2
    # Must NOT have been adapted by v1 fallback
    assert manifest.metadata.get("v1_adapted") is not True

    # Declared 7 native capabilities
    expected_capabilities = {
        BehaviorCategory.IDLE,
        BehaviorCategory.MOVE,
        BehaviorCategory.WORK,
        BehaviorCategory.OBSERVE,
        BehaviorCategory.PLAY,
        BehaviorCategory.GREET,
        BehaviorCategory.REACT,
    }
    assert manifest.capabilities == expected_capabilities
    assert len(manifest.activities) == 10


def test_vasu_v2_all_activity_visual_bindings_exist() -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    manifest = load_pet_manifest(vasu_dir)

    result = validate_pet_manifest(manifest, vasu_dir)
    assert result.valid is True
    assert len(result.errors) == 0

    # Verify native idle configuration file and atlas file physically exist
    assert manifest.spritesheet_path is not None
    assert (vasu_dir / manifest.spritesheet_path).is_file()
    assert manifest.native_idle_path is not None
    assert (vasu_dir / manifest.native_idle_path).is_file()


def test_vasu_v2_activity_catalog_semantics() -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    manifest = load_pet_manifest(vasu_dir)

    activities_by_id = {act.id: act for act in manifest.activities}
    expected_ids = {
        "idle_native",
        "idle_breathing",
        "run_right",
        "run_left",
        "trot",
        "wave",
        "hop",
        "stumble",
        "look_around",
        "pondering",
    }
    assert set(activities_by_id.keys()) == expected_ids

    # 1. IDLE: native_idle + idle_breathing
    idle_native = activities_by_id["idle_native"]
    assert idle_native.category == BehaviorCategory.IDLE
    assert idle_native.visual.format == "native_idle"
    assert ActivityTrait.QUIET in idle_native.traits
    assert idle_native.direction == BehaviorDirection.NONE

    idle_breathing = activities_by_id["idle_breathing"]
    assert idle_breathing.category == BehaviorCategory.IDLE
    assert idle_breathing.visual.format == "spritesheet"
    assert ActivityTrait.QUIET in idle_breathing.traits

    # 2. MOVE: run_right, run_left, trot
    run_right = activities_by_id["run_right"]
    assert run_right.category == BehaviorCategory.MOVE
    assert run_right.direction == BehaviorDirection.RIGHT
    assert ActivityTrait.ACTIVE in run_right.traits

    run_left = activities_by_id["run_left"]
    assert run_left.category == BehaviorCategory.MOVE
    assert run_left.direction == BehaviorDirection.LEFT
    assert ActivityTrait.ACTIVE in run_left.traits

    trot = activities_by_id["trot"]
    assert trot.category == BehaviorCategory.MOVE
    assert trot.direction == BehaviorDirection.NONE

    # 3. GREET: wave
    wave = activities_by_id["wave"]
    assert wave.category == BehaviorCategory.GREET
    assert ActivityTrait.SOCIAL in wave.traits
    assert wave.loop == LoopMode.ONCE
    assert wave.duration_ms == 1400

    # 4. PLAY: hop
    hop = activities_by_id["hop"]
    assert hop.category == BehaviorCategory.PLAY
    assert ActivityTrait.ACTIVE in hop.traits
    assert hop.loop == LoopMode.ONCE
    assert hop.duration_ms == 700

    # 5. REACT: stumble
    stumble = activities_by_id["stumble"]
    assert stumble.category == BehaviorCategory.REACT
    assert stumble.loop == LoopMode.ONCE
    assert "clumsy" in stumble.tags

    # 6. OBSERVE: look_around
    look_around = activities_by_id["look_around"]
    assert look_around.category == BehaviorCategory.OBSERVE
    assert ActivityTrait.QUIET in look_around.traits
    assert ActivityTrait.STATIONARY in look_around.traits

    # 7. WORK: pondering
    pondering = activities_by_id["pondering"]
    assert pondering.category == BehaviorCategory.WORK
    assert ActivityTrait.FOCUSED in pondering.traits
    assert ActivityTrait.QUIET in pondering.traits


def test_vasu_v2_validation_directory_passes_with_sleep_fallback() -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    result = validate_pet_directory(vasu_dir)
    assert result.valid is True
    assert len(result.errors) == 0
    # Sleep fallback diagnostic warning is expected and confirms WP-0 fallback
    assert any("falling back to 'idle'" in w for w in result.warnings)


def test_vasu_v2_runtime_smoke(tmp_path: Path) -> None:
    vasu_dir = Path("assets") / "pets" / "vasu"
    assert vasu_dir.is_dir()

    # Verify pet.json on disk is valid json and contains both keys
    raw_json = json.loads((vasu_dir / "pet.json").read_text(encoding="utf-8"))
    assert raw_json["schema_version"] == 2
    assert "spritesheetPath" in raw_json
    assert "spritesheet_path" in raw_json

    window = PetWindow(
        pet_dir=vasu_dir,
        scale=1.0,
        position_config_path=tmp_path / "body_position.json",
    )
    assert window.pet_dir == vasu_dir
    assert "idle" in window._loaded_sheets
    assert "review" in window._loaded_sheets
    assert "waiting" in window._loaded_sheets
    assert "running" in window._loaded_sheets

    # Native idle is active on Vasu
    assert window._native_idle_frames is not None
    assert window.current_state == PetState.IDLE

    # Transition through states
    for target_state in (PetState.WORKING, PetState.THINKING, PetState.HAPPY, PetState.IDLE):
        window.apply_state(target_state)
        assert window.current_state == target_state

    window.close()
