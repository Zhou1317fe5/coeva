from __future__ import annotations

import json
import os
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.body.contracts import PetState
from src.body.native_idle import NativeIdlePlayer
from src.body.window import PetWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_app = QApplication.instance() or QApplication([])


def test_native_idle_player_emits_cached_display_frame() -> None:
    player = NativeIdlePlayer(Path("assets/pets/vasu/native-idle"), display_size=360)
    frames = []
    player.frame_ready.connect(frames.append)
    player.start()
    _app.processEvents()
    player.stop()

    assert frames
    assert frames[0].width() == 360
    assert frames[0].height() == 360
    body_bbox = player.layer_bboxes["body"]
    assert body_bbox is not None and body_bbox[1] < 200


def test_native_idle_metrics_record_blink_event(tmp_path: Path) -> None:
    metrics_path = tmp_path / "native-idle.jsonl"
    player = NativeIdlePlayer(
        Path("assets/pets/vasu/native-idle"),
        display_size=360,
        seed=7,
    )
    player.set_metrics_path(metrics_path)
    player._running = True
    player._started_at = time.monotonic()
    player._next_blink_at = time.monotonic() - 1.0
    player._tick()
    player.stop()

    events = [json.loads(line) for line in metrics_path.read_text().splitlines()]
    assert any(event.get("event") == "blink_start" for event in events)


def test_pet_window_routes_idle_to_native_rig(tmp_path: Path) -> None:
    window = PetWindow(
        Path("assets/pets/vasu"),
        scale=1.0,
        position_config_path=tmp_path / "body_position.json",
    )
    assert window._native_idle is not None
    assert window.enable_native_idle_test_mode()
    assert window._native_idle.is_running

    window.apply_state(PetState.WORKING)
    assert not window._native_idle.is_running
    window.close()
