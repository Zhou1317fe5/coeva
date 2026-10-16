"""Unit tests for Desktop Body components."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from src.body.animation import AnimationPlayer, SpriteSheet, SpriteSheetError
from src.body.contracts import PetState
from src.body.controller import BodyController
from src.body.window import PetWindow

# Ensure QApplication is initialized for offscreen tests
_app = QApplication.instance()
if _app is None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _app = QApplication([])


def _isolated_window(pet_dir: Path, tmp_path: Path, *, scale: float = 1.0) -> PetWindow:
    """Build a PetWindow whose position config lives in tmp_path.

    Without this, constructing a PetWindow reads and (via closeEvent /
    reset_to_default_position) writes the user's real data/body_position.json,
    which also makes the persisted scale leak into unrelated tests.
    """
    return PetWindow(pet_dir, scale=scale, position_config_path=tmp_path / "body_position.json")


def test_spritesheet_load_and_slice(tmp_path: Path) -> None:
    """Test creating and slicing a test image into multiple frames."""
    # Create a 40x10 image with 4 frames of 10x10
    image = QImage(40, 10, QImage.Format.Format_ARGB32)
    image.fill(0xFF00FF00)
    file_path = tmp_path / "test_sheet.png"
    image.save(str(file_path))

    sheet = SpriteSheet.load(file_path, frames=4)
    assert sheet.frame_count == 4
    assert sheet.frame_width == 10
    assert sheet.frame_height == 10


def test_spritesheet_invalid_frame_count(tmp_path: Path) -> None:
    """Test error when frame count does not divide width evenly."""
    image = QImage(35, 10, QImage.Format.Format_ARGB32)
    file_path = tmp_path / "test_sheet.png"
    image.save(str(file_path))

    with pytest.raises(SpriteSheetError):
        SpriteSheet.load(file_path, frames=4)


def test_animation_player_logic() -> None:
    """Test AnimationPlayer frame emission."""
    image = QImage(20, 10, QImage.Format.Format_ARGB32)
    pix = QPixmap.fromImage(image)
    sheet = SpriteSheet([pix, pix], frame_width=10, frame_height=10)

    player = AnimationPlayer()
    frames_received = []
    player.frame_changed.connect(lambda f: frames_received.append(f))

    player.play(sheet, fps=10, loop=False)
    assert len(frames_received) >= 1
    assert player.current_frame is not None
    player.stop()


def test_body_controller_state_and_say(tmp_path: Path) -> None:
    """Test BodyController state transition and speech bubble invocation."""
    pet_dir = Path("assets") / "pets" / "claw"
    window = _isolated_window(pet_dir, tmp_path, scale=1.0)
    controller = BodyController(window)

    assert controller.current_state == PetState.IDLE

    controller.set_state("working")
    assert controller.current_state == PetState.WORKING

    controller.perform_action("sleep")
    assert controller.current_state == PetState.SLEEPING

    controller.say("测试消息")
    window.close()


def test_pet_window_clamping_and_reset(tmp_path: Path) -> None:
    """Test emergency position reset brings pet back into screen bounds."""
    pet_dir = Path("assets") / "pets" / "claw"
    window = _isolated_window(pet_dir, tmp_path, scale=1.0)

    # Force position way outside screen
    window.move(99999, 99999)
    assert window.x() == 99999

    # Trigger emergency reset
    window.reset_to_default_position()
    assert window.x() < 5000  # brought back inside screen
    window.close()

def test_petdex_atlas_loader(tmp_path: Path) -> None:
    """Test loading and slicing a standard 9-row Petdex atlas image."""
    from src.body.animation import PetdexAtlasLoader

    # Create an 8-col x 9-row image (total 160x180, each frame 20x20)
    image = QImage(160, 180, QImage.Format.Format_ARGB32)
    image.fill(0xFF10B981)
    atlas_path = tmp_path / "petdex_sheet.png"
    image.save(str(atlas_path))

    sheets = PetdexAtlasLoader.load_atlas(atlas_path, cols=8, rows=9)
    assert len(sheets) == 9
    assert "idle" in sheets
    assert "running" in sheets
    assert "jumping" in sheets
    assert "failed" in sheets
    assert "review" in sheets

    idle_sheet = sheets["idle"]
    assert idle_sheet.frame_count == 8
    assert idle_sheet.frame_width == 20
    assert idle_sheet.frame_height == 20

def test_petdex_atlas_trim_empty_frames(tmp_path: Path) -> None:
    """Test that PetdexAtlasLoader trims trailing completely transparent frames."""
    from src.body.animation import PetdexAtlasLoader

    # 8 cols x 9 rows (total 160x180, frame 20x20)
    image = QImage(160, 180, QImage.Format.Format_ARGB32)
    image.fill(0x00000000)  # transparent
    # fill only the first 3 frames in row 0
    for c in range(3):
        for y in range(0, 20):
            for x in range(c * 20, (c + 1) * 20):
                image.setPixelColor(x, y, 0xFFFFFFFF)

    atlas_path = tmp_path / "trimmed_sheet.png"
    image.save(str(atlas_path))

    sheets = PetdexAtlasLoader.load_atlas(atlas_path, cols=8, rows=9, trim_empty_frames=True)
    idle_sheet = sheets["idle"]
    assert idle_sheet.frame_count == 3
    assert idle_sheet.frame_width == 20
    assert idle_sheet.frame_height == 20


def test_builtin_pets_loading(tmp_path: Path) -> None:
    """Test that all three built-in pets (tiko, debug-duck, wangcai) load properly in PetWindow."""
    tiko_dir = Path("assets") / "pets" / "tiko"
    duck_dir = Path("assets") / "pets" / "debug-duck"
    wangcai_dir = Path("assets") / "pets" / "wangcai"

    assert tiko_dir.is_dir()
    assert duck_dir.is_dir()
    assert wangcai_dir.is_dir()

    # Default pet: Tiko
    window = _isolated_window(tiko_dir, tmp_path, scale=1.0)
    assert "idle" in window._loaded_sheets
    assert "review" in window._loaded_sheets
    assert "running" in window._loaded_sheets
    assert window._loaded_sheets["idle"].frame_count == 6

    # Test state transitions
    for target_state in (PetState.WORKING, PetState.THINKING, PetState.HAPPY, PetState.ERROR):
        window.apply_state(target_state)
        assert window.current_state == target_state

    # Test dynamic switching to Debug Duck
    window.load_pet(duck_dir)
    assert "idle" in window._loaded_sheets
    assert window._loaded_sheets["idle"].frame_count == 6

    # Test dynamic switching to Wangcai
    window.load_pet(wangcai_dir)
    assert "idle" in window._loaded_sheets
    assert window._loaded_sheets["idle"].frame_count == 6

    window.close()

def test_pet_window_scale_adjustment(tmp_path: Path) -> None:
    """Test dynamic scaling adjustment and persistence for pet body."""
    tiko_dir = Path("assets") / "pets" / "tiko"
    window = _isolated_window(tiko_dir, tmp_path, scale=1.0)
    assert abs(window.scale_factor - 1.0) < 0.01

    # Scale down to 50%
    window.set_scale(0.5)
    assert abs(window.scale_factor - 0.5) < 0.01
    idle_sheet = window._loaded_sheets["idle"]
    assert idle_sheet.frame_width == 96
    assert idle_sheet.frame_height == 104

    # Scale up to 150%
    window.set_scale(1.5)
    assert abs(window.scale_factor - 1.5) < 0.01
    idle_sheet_150 = window._loaded_sheets["idle"]
    assert idle_sheet_150.frame_width == 288
    assert idle_sheet_150.frame_height == 312

    window.close()
