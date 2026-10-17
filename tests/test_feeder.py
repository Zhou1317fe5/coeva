"""Unit tests for Slice Feeder components."""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.feeder.contracts import RawSlice
from src.feeder.hotkey import (
    DEFAULT_FEEDER_HOTKEY,
    GlobalHotkeyListener,
    hotkey_display,
    hotkey_from_qt,
    parse_hotkey,
)
from src.feeder.overlay import SliceFeederBar, SliceFeederOverlay
from src.feeder.storage import SliceStore

_app = QApplication.instance()
if _app is None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _app = QApplication([])


def test_raw_slice_creation_and_dict() -> None:
    """Test RawSlice creation with default and custom mood."""
    slice_item = RawSlice.create("今天读《悉达多》有感，允许河流经过。", mood_flag="reflective")
    assert slice_item.actor == "user"
    assert slice_item.source == "manual_feed"
    assert "河流" in slice_item.content
    assert slice_item.mood_flag == "reflective"
    assert slice_item.id.startswith("slice_")

    data = slice_item.to_dict()
    assert data["id"] == slice_item.id
    assert data["content"] == slice_item.content


def test_slice_store_save_and_load(tmp_path: Path) -> None:
    """Test SliceStore appending to jsonl file."""
    db_path = tmp_path / "raw_slices.jsonl"
    store = SliceStore(db_path)

    assert store.count() == 0
    assert store.load_recent() == []

    s1 = RawSlice.create("思考 1")
    s2 = RawSlice.create("思考 2", mood_flag="frustrated")

    store.save(s1)
    store.save(s2)

    assert store.count() == 2
    loaded = store.load_recent(10)
    assert len(loaded) == 2
    assert loaded[0].content == "思考 1"
    assert loaded[1].content == "思考 2"
    assert loaded[1].mood_flag == "frustrated"


def test_feeder_overlay_signal_flow() -> None:
    """Test SliceFeederOverlay submit and cancel signals."""
    overlay = SliceFeederOverlay()
    submitted = []
    cancelled = []

    overlay.slice_submitted.connect(lambda s: submitted.append(s))
    overlay.cancelled.connect(lambda: cancelled.append(True))

    # Test submit
    overlay._input.setPlainText("测试切片内容")
    overlay._on_submit()
    assert len(submitted) == 1
    assert submitted[0] == "测试切片内容"

    # Test cancel
    overlay._on_cancel()
    assert len(cancelled) == 1
    overlay.close()


def test_parse_hotkey_normalizes_and_is_idempotent() -> None:
    """Every accepted spelling collapses to one canonical spec and label."""
    for raw in ("<alt>+<space>", "Alt+Space", "alt + space", "ALT+SPACE"):
        parsed = parse_hotkey(raw)
        assert parsed is not None
        assert parsed.spec == DEFAULT_FEEDER_HOTKEY
        assert parsed.display == "Alt + Space"

    # Modifier order is canonicalised, so the output re-parses to itself.
    shuffled = parse_hotkey("<shift>+<ctrl>+a")
    assert shuffled is not None
    assert shuffled.spec == "<ctrl>+<shift>+a"
    assert shuffled.display == "Ctrl + Shift + A"
    rounded = parse_hotkey(shuffled.spec)
    assert rounded is not None
    assert rounded.spec == shuffled.spec


def test_parse_hotkey_rejects_unusable_combinations() -> None:
    """A bare key, a lone modifier, unknown names and duplicates are all refused."""
    for raw in ("", "   ", "f", "<ctrl>", "<ctrl>+<ctrl>", "<f25>", "ctrl", "alt++f"):
        assert parse_hotkey(raw) is None, raw


def test_hotkey_display_falls_back_to_raw_text() -> None:
    """Unparsable text is echoed instead of raising, so UI copy never breaks."""
    assert hotkey_display("<cmd>+<space>") == "Win + Space"
    assert hotkey_display("garbage") == "garbage"


def test_hotkey_from_qt_maps_chords_and_waits_for_modifiers() -> None:
    """Qt chords map to canonical specs; incomplete chords return None."""
    mods = Qt.KeyboardModifier
    captured = hotkey_from_qt(mods.ControlModifier | mods.AltModifier, Qt.Key.Key_F)
    assert captured is not None
    assert captured.spec == "<ctrl>+<alt>+f"
    space = hotkey_from_qt(mods.AltModifier, Qt.Key.Key_Space)
    assert space is not None
    assert space.spec == DEFAULT_FEEDER_HOTKEY
    # A bare modifier, a modifier-less key and an unsupported key all keep waiting.
    assert hotkey_from_qt(mods.ControlModifier, Qt.Key.Key_Control) is None
    assert hotkey_from_qt(mods.NoModifier, Qt.Key.Key_A) is None
    assert hotkey_from_qt(mods.ControlModifier, Qt.Key.Key_unknown) is None


def test_listener_start_rejects_illegal_combination() -> None:
    """An illegal chord raises to the caller instead of failing silently."""
    listener = GlobalHotkeyListener("f", lambda: None)
    try:
        listener.start()
    except ValueError:
        pass
    else:
        listener.stop()
        raise AssertionError("非法组合键必须被拒绝")


def test_listener_stop_releases_a_worker_that_has_not_started_yet() -> None:
    """Stopping immediately must not leave a live listener behind.

    The worker may still be building its listener when stop() runs. If that
    ordering leaks the listener, changing the hotkey would leave the old chord
    bound alongside the new one.
    """
    listener = GlobalHotkeyListener(DEFAULT_FEEDER_HOTKEY, lambda: None)
    listener.start()
    listener.stop()

    # Give a late-assigning worker the chance to expose a leak.
    time.sleep(0.5)
    assert listener._listener is None
    assert listener._thread is None

def test_feeder_bar_collapsed_and_expanded_modes() -> None:
    """SliceFeederBar starts in handle mode and expands to input/pill properly."""
    bar = SliceFeederBar()
    assert not bar.is_expanded
    assert bar.width() == 40
    assert bar.height() == 18
    assert bar.current_mode == "handle"

    modes: list[bool] = []
    bar.mode_changed.connect(lambda exp: modes.append(exp))

    bar.show_pill()
    assert not bar.is_expanded
    assert bar.width() == 88
    assert bar.height() == 40
    assert bar.current_mode == "pill"

    bar.expand_input()
    assert bar.is_expanded
    assert bar.width() == 272
    assert bar.height() == 46
    assert bar.current_mode == "input"
    assert modes == [False, True]

    bar.collapse()
    assert not bar.is_expanded
    assert bar.width() == 88
    assert bar.height() == 40
    assert modes == [False, True, False]

    bar.show_handle()
    assert bar.current_mode == "handle"
    bar.close()


def test_feeder_bar_voice_toggle() -> None:
    """Waveform button toggles listening mode and emits signals."""
    bar = SliceFeederBar()
    assert not bar.is_voice_active

    voice_events: list[bool] = []
    bar.voice_clicked.connect(lambda active: voice_events.append(active))

    bar._toggle_voice_mode()
    assert bar.is_voice_active
    assert voice_events == [True]

    bar._toggle_voice_mode()
    assert not bar.is_voice_active
    assert voice_events == [True, False]
    bar.close()


def test_feeder_bar_anchor_to_pet() -> None:
    """Bar anchors centered directly beneath the pet body."""
    from PySide6.QtCore import QPoint

    bar = SliceFeederBar()
    pet_pos = QPoint(400, 300)
    pet_w, pet_h = 100, 100
    bar.show_pill()
    bar.anchor_to_pet(pet_pos, pet_w, pet_h)

    # In pill mode (width 88), ideal center x is 400 + 50 = 450 -> x = 450 - 44 = 406
    assert bar.x() == 406
    # Pet bottom is 300 + 100 = 400. Below pet: 400 + 3 - 6 (margin) = 397
    assert bar.y() == 397

    # Expanding re-anchors centered around the pet
    bar.expand_input()
    assert bar.x() == 450 - 272 // 2  # 314
    bar.close()

def test_pet_window_integration_with_feeder_bar(tmp_path: Path) -> None:
    """PetWindow owns a docked SliceFeederBar, handles submission and voice feedback."""
    from src.body.contracts import PetState
    from src.body.window import PetWindow

    pet_dir = Path("assets") / "pets" / "vasu"
    store_file = tmp_path / "test_slices.jsonl"
    store = SliceStore(store_file)

    win = PetWindow(
        pet_dir,
        position_config_path=tmp_path / "body_pos.json",
        slice_store=store,
    )
    assert win.feeder_bar is not None

    submitted: list[str] = []
    win.slice_fed.connect(lambda s: submitted.append(s))

    # Trigger feeder input
    win.open_feeder_input()
    assert win.feeder_bar.isVisible()
    assert win.feeder_bar.is_expanded

    # Submit a slice
    win.feeder_bar._input.setText("共生伴生体成长切片测试")
    win.feeder_bar._on_submit()

    assert len(submitted) == 1
    assert submitted[0] == "共生伴生体成长切片测试"
    assert store.count() == 1
    assert store.load_recent(1)[0].content == "共生伴生体成长切片测试"
    assert win.current_state == PetState.HAPPY

    # Trigger voice toggle
    win.feeder_bar._toggle_voice_mode()
    assert win.current_state == PetState.THINKING
    win.feeder_bar._toggle_voice_mode()
    assert win.current_state == PetState.IDLE

    win.close()
    assert not win.feeder_bar.isVisible()


def test_feeder_bar_cancel_hides() -> None:
    """Pressing cancel or Esc completely closes and hides the feeder bar."""
    bar = SliceFeederBar()
    bar.expand_input()
    assert bar.isVisible()
    bar._on_cancel()
    assert not bar.isVisible()
    bar.close()
