"""Unit tests for Desktop Body components."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
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
    # Test dynamic switching to Calico (Default Clawd on Desk theme)
    calico_dir = Path("assets") / "pets" / "calico"
    assert calico_dir.is_dir()
    window.load_pet(calico_dir)
    assert "idle" in window._loaded_sheets
    assert "working" in window._loaded_sheets
    assert "react-drag" in window._loaded_sheets
    assert "react-poke" in window._loaded_sheets
    assert window._loaded_sheets["idle"].frame_count == 41

    window.close()


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
    from PySide6.QtGui import QImage

    for pet, expected_padding in (
        ("tiko", (31, 32)),
        ("wangcai", (18, 19)),
        ("debug-duck", (14, 15)),
    ):
        pet_dir = Path("assets") / "pets" / pet
        # 1. The measured margin must match the atlas' real transparent border.
        for scale in (1.0, 2.0, 3.0):
            window = _isolated_window(pet_dir, tmp_path, scale=scale)
            measured_left, measured_right = window._art_padding_px
            # Padding scales with the sprite, so compare against the scaled margin.
            expected_left = round(expected_padding[0] * scale)
            expected_right = round(expected_padding[1] * scale)
            assert abs(measured_left - expected_left) <= 1
            assert abs(measured_right - expected_right) <= 1

            # 2. The reveal must clear the margin, leaving a visible sliver.
            assert window._peek_reveal_px("right") > measured_right
            assert window._peek_reveal_px("left") > measured_left
            window.close()

        # 3. Real pixels must survive in the on-screen sliver, at every scale.
        import json as _json

        meta = _json.loads((pet_dir / "pet.json").read_text(encoding="utf-8"))
        atlas = QImage(str(pet_dir / meta["spritesheetPath"]))
        cols = int(meta.get("cols", 8))
        rows = int(meta.get("rows", 9))
        frame_w, frame_h = atlas.width() // cols, atlas.height() // rows

        for scale in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
            window = _isolated_window(pet_dir, tmp_path, scale=scale)
            scaled = atlas.copy(0, 0, frame_w, frame_h).scaled(
                int(frame_w * scale), int(frame_h * scale)
            )
            width, height = scaled.width(), scaled.height()

            for edge in ("right", "left"):
                reveal = window._peek_reveal_px(edge)
                columns = range(width - reveal, width) if edge == "right" else range(reveal)
                visible = sum(
                    1
                    for x in columns
                    for y in range(height)
                    if ((scaled.pixel(x, y) >> 24) & 0xFF) > 8
                )
                assert visible > 0, (
                    f"{pet} @scale={scale} docked {edge}: no artwork visible (reveal={reveal}px)"
                )
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
    pet_dir = Path("assets") / "pets" / "tiko"
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
    """Idle doze after a quiet minute, and a single wave on hover.

    Regression guard for the two P2 DESIGN debts: nothing ever slept from
    inactivity (the pet slept only when an agent session ended, so its rhythm
    belonged to the agent), and hovering revealed the pet without greeting.
    """
    from src.body.window import IDLE_SLEEP_AFTER_MS

    tiko_dir = Path("assets") / "pets" / "tiko"
    window = _isolated_window(tiko_dir, tmp_path, scale=1.0)

    # The configured idle wait is the documented 60s.
    assert IDLE_SLEEP_AFTER_MS == 60_000
    assert window._sleep_timer.interval() == IDLE_SLEEP_AFTER_MS
    # A fresh pet is awake and its countdown is running.
    assert window.current_state == PetState.IDLE
    assert window._sleep_timer.isActive()

    # Idle timeout puts it to sleep.
    window._doze_off()
    assert window.current_state == PetState.SLEEPING
    # Sleeping is stable: the countdown must not re-arm and re-trigger.
    assert not window._sleep_timer.isActive()

    # Activity wakes it and restarts the countdown.
    window._wake_up()
    assert window.current_state == PetState.IDLE
    assert window._sleep_timer.isActive()

    # Hovering greets with a wave, then settles back on its own.
    window._start_greeting()
    assert window.current_state == PetState.HAPPY
    assert window._greeting_active
    window._finish_greeting()
    assert window.current_state == PetState.IDLE
    assert not window._greeting_active

    # A sleeping pet must not be jolted awake by the greeting path itself.
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

    pet_dir = Path("assets") / "pets" / "tiko"
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
    assert window.x() == screen.right() - window._peek_reveal_px("right")
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
