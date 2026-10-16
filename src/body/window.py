"""Transparent, frameless, always-on-top window hosting the companion pet with edge peek docking."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QCursor,
    QEnterEvent,
    QImage,
    QMouseEvent,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from src.body.animation import (
    AnimationPlayer,
    PetdexAtlasLoader,
    SpriteSheet,
    SpriteSheetError,
    measure_art_padding,
)
from src.body.contracts import PetState
from src.body.speech_bubble import SpeechBubble

CLICK_DRAG_THRESHOLD_PX = 4
EDGE_SNAP_DISTANCE_PX = 30  # Snapping threshold set to 30px
# How much actual artwork stays on screen while docked to an edge. The reveal is
# computed from the sheet's own transparent margin (see `_peek_reveal_px`), not
# from a fixed pixel count: Petdex atlases bake wide margins, so a fixed 24px
# revealed pure transparency once the margin exceeded it, making a docked pet
# vanish entirely at larger scales.
PEEK_VISIBLE_ART_PX = 24  # artwork pixels left on screen when docked
# Shipped default size: 50%. A full-size Petdex frame (192x208 at 1.0) is large
# enough to feel intrusive on the desktop, so the companion starts small and the
# user can scale it up (settings panel, tray menu, or Ctrl + wheel).
DEFAULT_SCALE = 0.5
# DESIGN.md section 2.1: idle for a minute, then doze off. The old claw/pet.yaml
# said 120s but nothing ever read that file, so the documented 60s wins.
IDLE_SLEEP_AFTER_MS = 60_000
# Persisted window position and scale. Tests point this at tmp_path so they never
# read or overwrite the user's real file while constructing a PetWindow.
DEFAULT_POSITION_CONFIG_PATH = Path("data") / "body_position.json"


class PetWindow(QWidget):
    """The desktop pet window with animation player, speech bubble, dragging,
    and half-hidden edge peek docking.
    """

    clicked = Signal()
    position_changed = Signal(int, int)
    scale_changed = Signal(float)


    def __init__(
        self,
        pet_dir: Path,
        *,
        scale: float = DEFAULT_SCALE,
        position_config_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pet_dir = pet_dir
        self._scale = scale
        self._current_state = PetState.IDLE
        self._position_config_path = position_config_path or DEFAULT_POSITION_CONFIG_PATH
        # Worst-case transparent margin of the loaded sheets, measured once per
        # load/scale change. Docking reveals margin + a visible sliver of artwork.
        self._art_padding_px: tuple[int, int] = (0, 0)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(True)

        self._label = QLabel(self)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._label.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._label.setStyleSheet("background: transparent; border: 0;")
        self._label.setMouseTracking(True)

        self._player = AnimationPlayer(self)
        self._player.frame_changed.connect(self._on_frame_changed)

        self._bubble = SpeechBubble()

        # Drag state
        self._drag_offset: QPoint | None = None
        self._press_pos: QPoint | None = None
        self._has_moved = False

        # Edge Docking (Peek Mode) state
        self._docked_edge: str | None = None  # "right", "left", or None
        self._is_peek_expanded = False
        self._retract_timer = QTimer(self)
        self._retract_timer.setSingleShot(True)
        self._retract_timer.timeout.connect(self._retract_to_dock)

        # Polling watcher to ensure reliable leave detection across OS window borders
        self._hover_poll_timer = QTimer(self)
        self._hover_poll_timer.setInterval(150)
        self._hover_poll_timer.timeout.connect(self._check_cursor_outside_polling)

        # Idle doze: DESIGN.md section 2.1 wants the pet asleep after 60s of quiet.
        # Without this the pet only ever slept when an agent session ended, so its
        # rhythm was dictated by the agent rather than by the user's own presence.
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.setInterval(IDLE_SLEEP_AFTER_MS)
        self._sleep_timer.timeout.connect(self._doze_off)

        # Hover greeting: the pet waves once when it peeks out (DESIGN.md 2.1). The
        # one-shot timer restores the resting state after the gesture completes.
        self._wave_timer = QTimer(self)
        self._wave_timer.setSingleShot(True)
        self._wave_timer.timeout.connect(self._finish_greeting)
        self._greeting_active = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._loaded_sheets: dict[str, SpriteSheet] = {}
        self._load_spritesheets()
        self.apply_state(PetState.IDLE, force=True)  # first paint of the sprite
        self._restore_position()

    @property
    def current_state(self) -> PetState:
        return self._current_state
    @property
    def scale_factor(self) -> float:
        """Return the current scaling factor."""
        return self._scale

    def set_scale(self, scale: float) -> None:
        """Dynamically adjust pet scaling factor and refresh spritesheets."""
        clamped = max(0.4, min(3.0, round(scale, 2)))
        if abs(self._scale - clamped) < 0.01:
            return
        self._scale = clamped
        self._load_spritesheets()
        self.apply_state(self._current_state, force=True)  # sheets were re-sliced
        self._save_position()
        self.scale_changed.emit(self._scale)


    def load_pet(self, pet_dir: Path) -> None:
        """Switch to another pet directory dynamically and refresh animation."""
        self.pet_dir = pet_dir
        self._loaded_sheets.clear()
        self._load_spritesheets()
        self.apply_state(self._current_state, force=True)  # sheets were replaced

    def _load_spritesheets(self) -> None:
        """Preload sprite sheets from Petdex atlas or legacy sprites directory."""
        # 1. Try Petdex / Codex unified atlas sheet
        pet_json = self.pet_dir / "pet.json"
        atlas_candidate: Path | None = None
        cols = 8
        rows = 9

        if pet_json.is_file():
            try:
                meta = json.loads(pet_json.read_text(encoding="utf-8"))
                if "spritesheetPath" in meta:
                    candidate = self.pet_dir / str(meta["spritesheetPath"])
                    if candidate.is_file():
                        atlas_candidate = candidate
                cols = int(meta.get("cols", 8))
                rows = int(meta.get("rows", 9))
            except (json.JSONDecodeError, OSError):
                pass

        if atlas_candidate is None:
            for name in ("spritesheet.webp", "sprite.webp", "spritesheet.png", "sprite.png"):
                candidate = self.pet_dir / name
                if candidate.is_file():
                    atlas_candidate = candidate
                    break

        if atlas_candidate is not None:
            try:
                sheets = PetdexAtlasLoader.load_atlas(
                    atlas_candidate,
                    cols=cols,
                    rows=rows,
                    scale=self._scale,
                    trim_empty_frames=True,
                )
                self._loaded_sheets.update(sheets)
                self._measure_art_padding(atlas_candidate, cols=cols, rows=rows, factor=self._scale)
                return
            except SpriteSheetError:
                pass

        # 2. Fallback to legacy single sprite files
        self._art_padding_px = (0, 0)
        sprites_dir = self.pet_dir / "sprites"
        if not sprites_dir.is_dir():
            return

        known_files = {
            "idle": (sprites_dir / "idle.png", 8, 6),
            "walk": (sprites_dir / "walk.png", 6, 8),
            "sleep": (sprites_dir / "sleep.png", 4, 3),
            "placeholder": (sprites_dir / "placeholder.png", 1, 1),
        }

        for state_key, (path, frames, _fps) in known_files.items():
            if path.is_file():
                try:
                    # Legacy 32px sprites scale with a 2x base multiplier
                    factor = 2.0 * self._scale
                    factor = 2.0 * self._scale
                    sheet = SpriteSheet.load(path, frames=frames).scaled(factor)
                    self._loaded_sheets[state_key] = sheet
                    self._accumulate_art_padding(path, cols=frames, rows=1, factor=factor)
                except SpriteSheetError:
                    pass

    def _measure_art_padding(
        self, image_path: Path, *, cols: int, rows: int, factor: float
    ) -> None:
        """Record the scaled transparent margin of a Petdex atlas."""
        image = QImage(str(image_path))
        if image.isNull():
            self._art_padding_px = (0, 0)
            return
        scaled = image.scaled(
            max(1, int(round(image.width() * factor))),
            max(1, int(round(image.height() * factor))),
            aspectMode=Qt.AspectRatioMode.IgnoreAspectRatio,
            mode=Qt.TransformationMode.FastTransformation,
        )
        self._art_padding_px = measure_art_padding(scaled, cols=cols, rows=rows)

    def _accumulate_art_padding(
        self, image_path: Path, *, cols: int, rows: int, factor: float
    ) -> None:
        """Widen the recorded margin with a legacy sheet's own margin."""
        image = QImage(str(image_path))
        if image.isNull():
            return
        scaled = image.scaled(
            max(1, int(round(image.width() * factor))),
            max(1, int(round(image.height() * factor))),
            aspectMode=Qt.AspectRatioMode.IgnoreAspectRatio,
            mode=Qt.TransformationMode.FastTransformation,
        )
        left, right = measure_art_padding(scaled, cols=cols, rows=rows)
        current_left, current_right = self._art_padding_px
        self._art_padding_px = (max(current_left, left), max(current_right, right))

    def _peek_reveal_px(self, edge: str) -> int:
        """How many pixels of this window must stay on screen when docked.

        That is the frame's transparent margin on the docking side plus a fixed
        sliver of real artwork. Using the measured margin is what keeps the pet
        visible at every scale; a fixed 24px revealed only transparency once the
        margin grew past it, so a large docked pet disappeared completely.
        """
        left_pad, right_pad = self._art_padding_px
        margin = right_pad if edge == "right" else left_pad
        return margin + PEEK_VISIBLE_ART_PX

    def apply_state(self, state: PetState, *, force: bool = False) -> None:
        """Switch the pet's animated state.

        Re-applying the state already playing is a no-op unless `force` is set.
        Agent telemetry repeats the same state many times per turn (one event per
        tool call), and replaying the sheet each time reset the frame index to 0,
        so the pet visibly stuttered back to the first frame instead of running.
        """
        if state == self._current_state and not force:
            return
        self._current_state = state
        # Any state change means something happened: restart the idle countdown,
        # and let a wake-up clear the doze. Sleeping is the only state that is
        # allowed to persist, so it must not re-arm its own timer.
        if state == PetState.SLEEPING:
            self._sleep_timer.stop()
        else:
            self._sleep_timer.start()

        state_candidates: dict[PetState, tuple[list[str], int, bool]] = {
            PetState.IDLE: (["idle"], 6, True),
            PetState.SLEEPING: (["sleep", "idle"], 3, True),
            PetState.THINKING: (["review", "waiting", "idle"], 6, True),
            PetState.WORKING: (["running", "running-right", "walk", "idle"], 8, True),
            PetState.HAPPY: (["waving", "jumping", "idle"], 6, True),
            PetState.ERROR: (["failed", "idle"], 6, True),
            PetState.WAITING: (["waiting", "idle"], 6, True),
        }

        candidates, fps, loop = state_candidates.get(state, (["idle"], 6, True))

        sheet: SpriteSheet | None = None
        for key in candidates:
            if key in self._loaded_sheets:
                sheet = self._loaded_sheets[key]
                break

        if sheet is None:
            sheet = self._loaded_sheets.get("idle")

        if sheet is not None:
            self._player.play(sheet, fps=fps, loop=loop)
    def say(self, text: str, *, ttl_ms: int = 4000) -> None:
        """Display a speech bubble above the pet."""
        if self._current_state == PetState.SLEEPING:
            self._wake_up()  # a message is activity; a sleeping pet must answer
        if self._docked_edge is not None and not self._is_peek_expanded:
            self._expand_from_dock()
            self._retract_timer.start(ttl_ms + 1000)

        self._bubble.show_message(text, ttl_ms=ttl_ms)
        self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())

    def reset_to_default_position(self) -> None:
        """Emergency reset: brings the pet back to visible screen bottom-right corner."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            new_x = geom.right() - self.width() - 25
            new_y = geom.bottom() - self.height() - 15
            self._docked_edge = None
            self._is_peek_expanded = False
            self.move(new_x, new_y)
            self._save_position()
            if self._bubble.isVisible():
                self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())

    def _on_frame_changed(self, frame: QPixmap) -> None:
        self._label.setPixmap(frame)
        self.resize(frame.size())
        self._label.resize(frame.size())
        if self._bubble.isVisible():
            self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())

    def _get_config_path(self) -> Path:
        return self._position_config_path

    def _restore_position(self) -> None:
        cfg = self._get_config_path()
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            fallback_x = geom.right() - 220
            fallback_y = geom.bottom() - 200

            if cfg.is_file():
                try:
                    data = json.loads(cfg.read_text("utf-8"))
                    saved_x = int(data.get("x", fallback_x))
                    saved_y = int(data.get("y", fallback_y))
                    self._docked_edge = data.get("docked_edge", None)
                    if "scale" in data:
                        saved_scale = float(data["scale"])
                        if 0.3 <= saved_scale <= 3.0 and abs(self._scale - saved_scale) >= 0.01:
                            self._scale = saved_scale
                            self._load_spritesheets()

                    min_clamped_x = geom.left() - self.width() + self._peek_reveal_px("left")
                    max_clamped_x = geom.right() - self._peek_reveal_px("right")
                    clamped_x = max(min_clamped_x, min(saved_x, max_clamped_x))
                    clamped_y = max(geom.top(), min(saved_y, geom.bottom() - self.height()))
                    self.move(clamped_x, clamped_y)
                    return
                except (json.JSONDecodeError, ValueError, OSError):
                    pass

            self.move(fallback_x, fallback_y)

    def _save_position(self) -> None:
        cfg = self._get_config_path()
        try:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                json.dumps({
                    "x": self.x(),
                    "y": self.y(),
                    "docked_edge": self._docked_edge,
                    "scale": round(self._scale, 2),
                }),
                "utf-8",
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Peek Docking & Hover Animations
    # ------------------------------------------------------------------
    def _doze_off(self) -> None:
        """Fall asleep after a minute of no activity (DESIGN.md section 2.1)."""
        if self._greeting_active:
            return
        self.apply_state(PetState.SLEEPING)

    def _wake_up(self) -> None:
        """Return to a resting, awake state after the pet had dozed off."""
        if self._current_state == PetState.SLEEPING:
            self.apply_state(PetState.IDLE)

    def _start_greeting(self) -> None:
        """Wave hello once when the user's cursor reaches the pet."""
        if self._greeting_active or self._current_state == PetState.SLEEPING:
            return
        self._greeting_active = True
        self.apply_state(PetState.HAPPY)
        # Long enough to show the wave, short enough that it never reads as a
        # state the pet is stuck in.
        self._wave_timer.start(1400)

    def _finish_greeting(self) -> None:
        """End the hover wave and settle back to resting."""
        self._greeting_active = False
        self.apply_state(PetState.IDLE)

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        """Mouse hover: peek out if docked, and wave hello once."""
        self._wake_up()
        if self._docked_edge is not None:
            self._retract_timer.stop()
            self._expand_from_dock()
        self._start_greeting()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        """Mouse leave: schedule retracting back to docked peek state."""
        if self._docked_edge is not None and not self._has_moved:
            if not self._retract_timer.isActive():
                self._retract_timer.start(800)
        super().leaveEvent(event)

    def _check_cursor_outside_polling(self) -> None:
        """Reliable periodic check to detect cursor leaving pet and bubble area."""
        if self._docked_edge is not None and self._is_peek_expanded and not self._has_moved:
            cursor_pos = QCursor.pos()
            in_pet = self.geometry().contains(cursor_pos)
            in_bubble = self._bubble.isVisible() and self._bubble.geometry().contains(cursor_pos)
            if not in_pet and not in_bubble:
                if not self._retract_timer.isActive():
                    self._retract_timer.start(800)  # retract after 800ms
            else:
                self._retract_timer.stop()

    def _expand_from_dock(self) -> None:
        """Slide fully out of the edge so user can see whole pet body."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None or self._docked_edge is None:
            return
        geom = screen.availableGeometry()
        if self._docked_edge == "right":
            self.move(geom.right() - self.width() + 1, self.y())
        elif self._docked_edge == "left":
            self.move(geom.left(), self.y())
        self._is_peek_expanded = True
        self._hover_poll_timer.start()
        if self._bubble.isVisible():
            self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Ctrl + Wheel: smoothly zoom in/out pet scale with instant bubble feedback."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            step = 0.1 if delta > 0 else -0.1
            new_scale = round(self._scale + step, 1)
            new_scale = max(0.5, min(2.5, new_scale))
            if abs(new_scale - self._scale) >= 0.04:
                self.set_scale(new_scale)
                percent = int(round(self._scale * 100))
                self.say(f"🔍 伴生体大小: {percent}%", ttl_ms=1500)
            event.accept()
            return
        super().wheelEvent(event)

    def _retract_to_dock(self) -> None:
        """Slide half-body into screen edge, leaving only the head peeking out."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None or self._docked_edge is None:
            return
        geom = screen.availableGeometry()
        if self._docked_edge == "right":
            self.move(geom.right() - self._peek_reveal_px("right"), self.y())
        elif self._docked_edge == "left":
            self.move(geom.left() - self.width() + self._peek_reveal_px("left"), self.y())
        self._is_peek_expanded = False
        self._hover_poll_timer.stop()
        self._save_position()

    # ------------------------------------------------------------------
    # Mouse interaction (Screen-clamped Dragging and Edge Snapping)
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._wake_up()  # touching the pet is activity: it stops dozing
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()
            self._has_moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and self._press_pos is not None:
            cur_pos = event.globalPosition().toPoint()
            dist = (cur_pos - self._press_pos).manhattanLength()
            if dist >= CLICK_DRAG_THRESHOLD_PX:
                self._has_moved = True
                desired_pos = cur_pos - self._drag_offset

                screen = self.screen() or QApplication.primaryScreen()
                if screen is not None:
                    geom = screen.availableGeometry()
                    min_x = geom.left() - self.width() + self._peek_reveal_px("left")
                    max_x = geom.right() - self._peek_reveal_px("right")
                    clamped_x = max(min_x, min(desired_pos.x(), max_x))
                    clamped_y = max(geom.top(), min(desired_pos.y(), geom.bottom() - self.height()))
                    self.move(clamped_x, clamped_y)
                    self.position_changed.emit(clamped_x, clamped_y)
                else:
                    self.move(desired_pos)

                if self._bubble.isVisible():
                    self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._drag_offset = None
            if self._has_moved:
                screen = self.screen() or QApplication.primaryScreen()
                if screen is not None:
                    geom = screen.availableGeometry()
                    cur_x = self.x()
                    cur_y = self.y()

                    # Check Right Edge Docking
                    if (
                        abs(geom.right() - self.width() - cur_x) < EDGE_SNAP_DISTANCE_PX
                        or cur_x > geom.right() - self.width()
                    ):
                        self._docked_edge = "right"
                        self._retract_to_dock()
                    # Check Left Edge Docking
                    elif abs(cur_x - geom.left()) < EDGE_SNAP_DISTANCE_PX or cur_x < geom.left():
                        self._docked_edge = "left"
                        self._retract_to_dock()
                    else:
                        self._docked_edge = None
                        if abs(geom.bottom() - self.height() - cur_y) < EDGE_SNAP_DISTANCE_PX:
                            cur_y = geom.bottom() - self.height()
                            self.move(cur_x, cur_y)
                        self._save_position()
                else:
                    self._save_position()
            else:
                self.clicked.emit()
            # The drag is finished, so clear the flag: it only exists to suppress
            # auto-retract *during* a drag. Leaving it set disabled both the
            # leaveEvent path and the cursor poll for the rest of the session, so a
            # pet docked by dragging peeking out on hover and then never retracted.
            self._has_moved = False
            event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._hover_poll_timer.stop()
        self._retract_timer.stop()
        self._sleep_timer.stop()
        self._wave_timer.stop()
        self._bubble.close()
        self._player.stop()
        super().closeEvent(event)
