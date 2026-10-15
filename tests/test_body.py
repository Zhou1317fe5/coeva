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


def test_body_controller_state_and_say() -> None:
    """Test BodyController state transition and speech bubble invocation."""
    pet_dir = Path("assets") / "pets" / "claw"
    window = PetWindow(pet_dir, scale=1)
    controller = BodyController(window)

    assert controller.current_state == PetState.IDLE

    controller.set_state("working")
    assert controller.current_state == PetState.WORKING

    controller.perform_action("sleep")
    assert controller.current_state == PetState.SLEEPING

    controller.say("测试消息")
    window.close()


def test_pet_window_clamping_and_reset() -> None:
    """Test emergency position reset brings pet back into screen bounds."""
    pet_dir = Path("assets") / "pets" / "claw"
    window = PetWindow(pet_dir, scale=1)

    # Force position way outside screen
    window.move(99999, 99999)
    assert window.x() == 99999

    # Trigger emergency reset
    window.reset_to_default_position()
    assert window.x() < 5000  # brought back inside screen
    window.close()
