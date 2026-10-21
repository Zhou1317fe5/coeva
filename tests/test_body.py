"""Unit tests for Desktop Body components."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import QApplication

from src.body.animation import AnimationPlayer, SpriteSheet, SpriteSheetError
from src.body.contracts import PetState
from src.body.controller import BodyController
from src.body.settings_window import SettingsWindow
from src.body.window import PetWindow
from src.feeder.hotkey import DEFAULT_FEEDER_HOTKEY

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
    pet_dir = Path("assets") / "pets" / "vasu"
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
    pet_dir = Path("assets") / "pets" / "vasu"
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
    """Test that built-in pets (vasu, calico) load properly in PetWindow."""
    vasu_dir = Path("assets") / "pets" / "vasu"
    calico_dir = Path("assets") / "pets" / "calico"

    assert vasu_dir.is_dir()
    assert calico_dir.is_dir()

    # Default pet: Vasu
    window = _isolated_window(vasu_dir, tmp_path, scale=1.0)
    assert "idle" in window._loaded_sheets
    assert "review" in window._loaded_sheets
    assert "running" in window._loaded_sheets
    assert window._loaded_sheets["idle"].frame_count == 6

    # Test state transitions on Vasu
    for target_state in (PetState.WORKING, PetState.THINKING, PetState.HAPPY, PetState.ERROR):
        window.apply_state(target_state)
        assert window.current_state == target_state

    # Test dynamic switching to Calico
    window.load_pet(calico_dir)
    assert "idle" in window._loaded_sheets
    assert window._loaded_sheets["idle"].frame_count == 41

    window.close()


def test_vasu_blink_preserves_body_and_tail_pixels() -> None:
    """The baked blink frame must change the head only, never shrink the body."""
    neutral = Image.open(
        Path("assets") / "vasu" / "reference" / "vasu-native-canonical-hires.png"
    ).convert("RGBA")
    blink = Image.open(
        Path("assets") / "vasu" / "production" / "v2.1-native-desktop-idle" / "vasu-blink.png"
    ).convert("RGBA")

    assert neutral.size == blink.size == (1024, 1024)
    body_region = (0, 560, 1024, 1024)
    assert (
        ImageChops.difference(neutral.crop(body_region), blink.crop(body_region)).getbbox() is None
    )


def test_calico_theme_apng_loading_and_interactions(tmp_path: Path) -> None:
    """Test that Calico APNG theme loads all 40+ rich behaviors and responds to drag/poke."""
    from src.body.animation import ThemeApngLoader

    calico_dir = Path("assets") / "pets" / "calico"
    sheets = ThemeApngLoader.load_theme(calico_dir, scale=1.0)
    assert len(sheets) >= 25
    assert "idle" in sheets
    assert "working-typing" in sheets
    assert "react-drag" in sheets
    assert "react-poke" in sheets
    # Typing is high-speed 16 FPS, idle is calm 8 FPS
    assert sheets["working-typing"].default_fps == 16
    assert sheets["idle"].default_fps == 8

    # Test Window integration with drag & poke
    window = _isolated_window(calico_dir, tmp_path, scale=1.0)
    assert window._loaded_sheets["idle"].frame_width == 266

    # Test poking
    window.play_poke_reaction()
    assert window._wave_timer.isActive()

    window.close()


def test_docked_peek_keeps_artwork_visible_at_every_scale(tmp_path: Path) -> None:
    """A docked pet must show real artwork, not just transparent margin.

    Regression guard: the reveal used to be a fixed 24px, but Petdex atlases bake
    transparent margins (tiko up to 32px, wangcai 19px) that grow with scale. Once
    the margin exceeded 24px the docked window showed nothing but transparency, so
    a larger pet vanished at the screen edge.
    """

    calico_dir = Path("assets") / "pets" / "calico"
    assert calico_dir.is_dir()

    for scale in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        window = _isolated_window(calico_dir, tmp_path, scale=scale)
        measured_left, measured_right = window._art_padding_px

        # The reveal must clear the margin, leaving real visible artwork
        assert window._peek_reveal_px("right") > measured_right
        assert window._peek_reveal_px("left") > measured_left
        window.close()


def test_panel_action_buttons_all_map_to_a_real_state(tmp_path: Path) -> None:
    """Every action id the PI-Desktop panel posts must drive a real state.

    Regression guard: the panel offered thinking / working / celebrating while the
    controller only knew think / work / jump, so three of its four buttons silently
    did nothing. This reads the panel itself, so the two can never drift apart.
    """
    import re

    from src.body.controller import ACTION_STATES

    panel = (Path("plugins") / "pi-companion-bridge" / "renderer" / "index.html").read_text(
        encoding="utf-8"
    )
    action_ids = set(re.findall(r'data-action="([A-Za-z_]+)"', panel))

    assert action_ids, "panel should declare data-action buttons"
    unknown = sorted(action_id for action_id in action_ids if action_id not in ACTION_STATES)
    assert not unknown, f"panel actions missing from ACTION_STATES: {unknown}"

    # And each one must not be a silent no-op: the mapped state must be the one
    # the pet actually reaches.
    pet_dir = Path("assets") / "pets" / "calico"
    window = _isolated_window(pet_dir, tmp_path, scale=1.0)
    controller = BodyController(window)
    for action_id in sorted(action_ids):
        controller.perform_action("rest")  # reset to a known state
        assert controller.current_state == PetState.IDLE
        controller.perform_action(action_id)
        assert controller.current_state == ACTION_STATES[action_id]
    window.close()


def test_core_status_page_reports_live_state_not_static_prose(tmp_path: Path) -> None:
    """Page 3 must report the real Growth Core state, not fixed marketing copy."""
    from src.core.cold_start import ColdStartPolicy
    from src.core.sanctuary import SanctuaryGuard

    guard = SanctuaryGuard()
    policy = ColdStartPolicy(day_count=5)
    window = _settings_window(tmp_path)
    window.set_core_handles(sanctuary=guard, cold_start=policy)

    # Day 5 = stage 2, quota 2, no psychological analysis allowed.
    assert "第 5 天" in window.coldstart_status.text()
    assert "Stage 2" in window.coldstart_status.text()
    assert "剩余 2 次" in window.coldstart_status.text()
    assert "禁止" in window.coldstart_status.text()

    # Consuming quota must be reflected the next time the page is shown.
    assert policy.record_speech()
    window.refresh_core_status()
    assert "剩余 1 次" in window.coldstart_status.text()

    # Sanctuary must flip the indicator on real state.
    assert "未激活" in window.sanctuary_status.text()
    guard.evaluate_text("烦死了，全搞砸了")
    window.refresh_core_status()
    assert "已激活" in window.sanctuary_status.text()
    window.close()


def test_core_status_page_says_so_when_core_is_not_attached(tmp_path: Path) -> None:
    """Without handles the page must say '未接入' rather than imply it is live."""
    window = _settings_window(tmp_path)
    assert "未接入" in window.sanctuary_status.text()
    assert "未接入" in window.coldstart_status.text()
    window.close()


def test_idle_sleep_and_hover_greeting(tmp_path: Path) -> None:
    """Manual sleep/wake, autonomous wake, and hover greeting with cooldown."""
    calico_dir = Path("assets") / "pets" / "calico"
    window = _isolated_window(calico_dir, tmp_path, scale=1.0)

    # Fresh pet is awake in IDLE and has autonomous routine timer running
    assert window.current_state == PetState.IDLE
    assert window._autonomous_timer.isActive()

    # Manual sleep (from tray menu / DND) puts it to sleep and starts catnap
    window._doze_off()
    assert window.current_state == PetState.SLEEPING
    assert not window._autonomous_timer.isActive()
    assert window._nap_timer.isActive()

    # Activity / wake up wakes it back to IDLE
    window._wake_up()
    assert window.current_state == PetState.IDLE
    assert window._autonomous_timer.isActive()

    # Hovering greets with a wave, then settles back on its own
    window._start_greeting(force=True)
    assert window.current_state == PetState.HAPPY
    assert window._greeting_active
    window._finish_greeting()
    assert window.current_state == PetState.IDLE
    assert not window._greeting_active

    # A sleeping pet must not be jolted awake by the greeting path itself
    window._doze_off()
    assert window.current_state == PetState.SLEEPING
    window._start_greeting()
    assert not window._greeting_active

    window.close()


def test_docked_pet_retracts_again_after_being_dragged_to_the_edge(tmp_path: Path) -> None:
    """A pet docked by dragging must still auto-retract after a hover peek.

    Regression guard: `_has_moved` is set while dragging and both auto-retract
    paths require it to be False, but it was never cleared on release. So a pet the
    user dragged to the edge peeked out on hover and then stayed out forever, as if
    it were no longer docked. Restoring a dock from disk (the only path that worked)
    hid the bug, because that never sets the flag.
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    pet_dir = Path("assets") / "pets" / "calico"
    window = _isolated_window(pet_dir, tmp_path, scale=1.0)
    screen = (window.screen() or QApplication.primaryScreen()).availableGeometry()

    def _mouse(kind: QMouseEvent.Type, gx: float, gy: float, button: Qt.MouseButton) -> QMouseEvent:
        return QMouseEvent(
            kind,
            QPointF(1, 1),
            QPointF(gx, gy),
            button,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

    # Dock it the way a user does: press, drag to the right edge, release.
    window.mousePressEvent(
        _mouse(
            QMouseEvent.Type.MouseButtonPress,
            window.x() + 10,
            window.y() + 10,
            Qt.MouseButton.LeftButton,
        )
    )
    window.mouseMoveEvent(
        _mouse(
            QMouseEvent.Type.MouseMove,
            screen.right() - 2,
            window.y() + 40,
            Qt.MouseButton.NoButton,
        )
    )
    window.mouseReleaseEvent(
        _mouse(
            QMouseEvent.Type.MouseButtonRelease,
            screen.right() - 2,
            window.y() + 40,
            Qt.MouseButton.LeftButton,
        )
    )
    assert window._docked_edge == "right"
    assert not window._has_moved, "the drag is over, the flag must not stick"

    # Hover: it peeks out.
    window._expand_from_dock()
    assert window._is_peek_expanded

    # Leaving must schedule the retract, and the retract must really move it back.
    window.leaveEvent(QEvent(QEvent.Type.Leave))
    assert window._retract_timer.isActive(), "leaving the pet must re-arm auto-retract"
    window._retract_to_dock()
    assert not window._is_peek_expanded
    if window._mini_cfg.supported and "mini-idle" in window._loaded_sheets:
        expected_x = screen.right() - int(
            round(window.width() * (1 - window._mini_cfg.offset_ratio))
        )
        assert window.x() == expected_x
    else:
        assert window.x() == screen.right() - window._peek_reveal_px("right")
    window.close()


def test_pet_window_scale_adjustment(tmp_path: Path) -> None:
    """Test dynamic scaling adjustment and persistence for pet body."""
    calico_dir = Path("assets") / "pets" / "calico"
    window = _isolated_window(calico_dir, tmp_path, scale=1.0)
    assert abs(window.scale_factor - 1.0) < 0.01

    # Scale down to 50% (Calico native 266x200 -> 133x100)
    window.set_scale(0.5)
    assert abs(window.scale_factor - 0.5) < 0.01
    idle_sheet = window._loaded_sheets["idle"]
    assert idle_sheet.frame_width == 133
    assert idle_sheet.frame_height == 100

    # Scale up to 150% (Calico native 266x200 -> 399x300)
    window.set_scale(1.5)
    assert abs(window.scale_factor - 1.5) < 0.01
    idle_sheet_150 = window._loaded_sheets["idle"]
    assert idle_sheet_150.frame_width == 399
    assert idle_sheet_150.frame_height == 300

    window.close()


class _StubHookManager:
    """Hook manager stand-in so settings tests never touch the real filesystem."""

    @staticmethod
    def get_wsl_distros() -> list[str]:
        return []

    @staticmethod
    def check_hook_status(agent_id: str, instance_id: str) -> dict[str, object]:
        return {"installed": False, "status": "not_installed", "target_dir": None}


def _settings_window(tmp_path: Path) -> SettingsWindow:
    """Build a settings window backed by a throwaway settings file."""
    from src.connectors.settings import AgentSettingsStore

    store = AgentSettingsStore(tmp_path / "agent_settings.json")
    return SettingsWindow(store, _StubHookManager())  # type: ignore[arg-type]


def test_settings_shows_stored_feeder_hotkey(tmp_path: Path) -> None:
    """The feeder card displays the persisted combination on open."""
    window = _settings_window(tmp_path)
    assert window.hotkey_edit.text() == "Alt + Space"
    window.close()


def test_settings_records_hotkey_and_persists_it(tmp_path: Path) -> None:
    """Recording a chord updates the field, emits, and writes the canonical spec."""
    from PySide6.QtCore import Qt

    window = _settings_window(tmp_path)
    captured: list[str] = []
    window.hotkey_changed.connect(captured.append)

    window.hotkey_edit._start_recording()
    window.hotkey_edit.keyPressEvent(
        QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_F,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        )
    )

    assert captured == ["<ctrl>+<alt>+f"]
    assert window.hotkey_edit.text() == "Ctrl + Alt + F"
    assert window.store.feeder_hotkey == "<ctrl>+<alt>+f"
    window.close()


def test_settings_rejects_modifierless_recording(tmp_path: Path) -> None:
    """A chord without a modifier is refused, leaving the stored value intact."""
    from PySide6.QtCore import Qt

    window = _settings_window(tmp_path)
    captured: list[str] = []
    window.hotkey_changed.connect(captured.append)

    window.hotkey_edit._start_recording()
    window.hotkey_edit.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_F, Qt.KeyboardModifier.NoModifier)
    )

    assert captured == []
    assert window.store.feeder_hotkey == DEFAULT_FEEDER_HOTKEY
    assert "无效" in window.hotkey_hint.text()
    window.close()


def test_settings_reset_restores_default_hotkey(tmp_path: Path) -> None:
    """The reset button returns the shipped default and re-emits it."""
    window = _settings_window(tmp_path)
    window._on_hotkey_captured("<ctrl>+<alt>+f")

    captured: list[str] = []
    window.hotkey_changed.connect(captured.append)
    window._on_hotkey_reset()

    assert captured == [DEFAULT_FEEDER_HOTKEY]
    assert window.store.feeder_hotkey == DEFAULT_FEEDER_HOTKEY
    assert window.hotkey_edit.text() == "Alt + Space"
    window.close()


def test_calico_mini_mode_docking_and_flipping(tmp_path: Path) -> None:
    """Test that Calico switches to mini-idle when docked, flips assets, and plays mini-peek."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    calico_dir = Path("assets") / "pets" / "calico"
    window = _isolated_window(calico_dir, tmp_path, scale=0.5)
    screen = (window.screen() or QApplication.primaryScreen()).availableGeometry()

    assert window._mini_cfg.supported is True
    assert window._mini_cfg.flip_assets is True
    assert "mini-idle" in window._loaded_sheets
    assert "mini-idle-flipped" in window._loaded_sheets

    # Dock to right edge
    window._docked_edge = "right"
    window._retract_to_dock()

    # Check right edge position: right 40% hidden, 60% on screen
    expected_right_x = screen.right() - int(round(window.width() * 0.6))
    assert window.x() == expected_right_x

    # When docked at right edge and flip_assets is true, it uses flipped sheet
    current_sheet = window._player._sheet
    assert current_sheet is not None
    assert current_sheet is window._loaded_sheets["mini-idle-flipped"]

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QEnterEvent

    window.enterEvent(QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
    assert window._is_peek_expanded is True
    peek_sheet = window._player._sheet
    assert peek_sheet is not None
    assert peek_sheet is window._loaded_sheets["mini-peek-flipped"]

    # Mouse leave re-arms retract timer and retracts back to mini-idle
    window.leaveEvent(QEvent(QEvent.Type.Leave))
    assert window._retract_timer.isActive()
    window._retract_to_dock()
    assert window._is_peek_expanded is False
    assert window.x() == expected_right_x

    # Test Left Edge: uses unflipped sheet
    window._docked_edge = "left"
    window._retract_to_dock()
    expected_left_x = screen.left() - int(round(window.width() * 0.4))
    assert window.x() == expected_left_x
    left_sheet = window._player._sheet
    assert left_sheet is not None
    assert left_sheet is window._loaded_sheets["mini-idle"]

    window.close()


def test_autonomous_life_routine_and_nap_waking(tmp_path: Path) -> None:
    """Test that Calico has autonomous daily life activities and wakes from naps."""
    calico_dir = Path("assets") / "pets" / "calico"
    window = _isolated_window(calico_dir, tmp_path, scale=0.5)

    # 1. Awake pet has an autonomous routine scheduled
    assert window.current_state == PetState.IDLE
    assert window._autonomous_timer.isActive()

    # 2. Trigger autonomous routine: plays an activity
    window._start_autonomous_routine()
    assert window._in_autonomous_routine is True
    assert window._autonomous_done_timer.isActive()

    # 3. Finish autonomous routine: returns to idle and reschedules
    window._finish_autonomous_routine()
    assert window._in_autonomous_routine is False
    assert window._autonomous_timer.isActive()

    # 4. Going to sleep stops autonomous timer and starts nap timer
    window._doze_off()
    assert window.current_state == PetState.SLEEPING
    assert not window._autonomous_timer.isActive()
    assert window._nap_timer.isActive()

    # 5. Nap timer expiring wakes the pet up with stretching
    window._wake_up()
    assert window.current_state == PetState.IDLE
    assert not window._nap_timer.isActive()
    assert window._autonomous_timer.isActive()


def test_vasu_native_idle_and_core_interactions(tmp_path: Path) -> None:
    """Test sparse native idle blink while keeping Core interaction states available."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    vasu_dir = Path("assets") / "pets" / "vasu"
    window = _isolated_window(vasu_dir, tmp_path, scale=1.0)

    # Native idle is one static frame with an independent sparse blink timer.
    assert window._native_idle_frames is not None
    assert not window._player._timer.isActive()
    assert window._native_blink_timer.isActive()
    assert not window._autonomous_timer.isActive()

    neutral, blink = window._native_idle_frames
    window._start_native_blink()
    current = window._label.pixmap()
    assert current is not None and current.cacheKey() == blink.cacheKey()
    window._finish_native_blink()
    current = window._label.pixmap()
    assert current is not None and current.cacheKey() == neutral.cacheKey()

    # 2. Hover jump on cursor enter
    assert "jumping" in window._loaded_sheets
    window._last_hover_jump_timestamp = 0.0
    jumped = window._trigger_hover_jump()
    assert jumped is True
    assert window._player._sheet == window._loaded_sheets["jumping"]

    # 3. Directional drag away from edges
    window.move(500, 500)
    press_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(20, 20),
        QPointF(520, 520),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.mousePressEvent(press_ev)

    # Drag right -> running-right
    move_right = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(60, 20),
        QPointF(560, 520),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.mouseMoveEvent(move_right)
    assert window._current_drag_dir == "right"
    assert window._player._sheet == window._loaded_sheets["running-right"]

    # Drag left -> running-left
    move_left = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(40, 20),
        QPointF(540, 520),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.mouseMoveEvent(move_left)
    assert window._current_drag_dir == "left"
    assert window._player._sheet == window._loaded_sheets["running-left"]

    # Mouse release -> settle back to idle
    release_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(40, 20),
        QPointF(540, 520),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.mouseReleaseEvent(release_ev)
    assert window._current_drag_dir is None
    assert not window._player._timer.isActive()
    current = window._label.pixmap()
    assert current is not None and current.cacheKey() == neutral.cacheKey()

    window.close()
