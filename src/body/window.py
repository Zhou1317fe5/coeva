"""Transparent, frameless, always-on-top window hosting the companion pet with edge peek docking."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QCursor, QEnterEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from src.body.animation import AnimationPlayer, SpriteSheet, SpriteSheetError
from src.body.contracts import PetState
from src.body.speech_bubble import SpeechBubble

CLICK_DRAG_THRESHOLD_PX = 4
EDGE_SNAP_DISTANCE_PX = 30  # Snapping threshold set to 30px
PEEK_REVEAL_WIDTH_PX = 24  # Width of half-body staying visible when docked
DEFAULT_SCALE = 2


class PetWindow(QWidget):
    """The desktop pet window with animation player, speech bubble, dragging,
    and half-hidden edge peek docking.
    """

    clicked = Signal()
    position_changed = Signal(int, int)

    def __init__(
        self,
        pet_dir: Path,
        *,
        scale: int = DEFAULT_SCALE,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pet_dir = pet_dir
        self._scale = scale
        self._current_state = PetState.IDLE

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

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._loaded_sheets: dict[str, SpriteSheet] = {}
        self._load_spritesheets()
        self.apply_state(PetState.IDLE)
        self._restore_position()

    @property
    def current_state(self) -> PetState:
        return self._current_state

    def _load_spritesheets(self) -> None:
        """Preload sprite sheets available in the pet sprites directory."""
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
                    sheet = SpriteSheet.load(path, frames=frames).scaled(self._scale)
                    self._loaded_sheets[state_key] = sheet
                except SpriteSheetError:
                    pass

    def apply_state(self, state: PetState) -> None:
        """Switch the pet's animated state."""
        self._current_state = state

        sheet_key = "idle"
        fps = 6
        loop = True

        if state == PetState.SLEEPING:
            sheet_key = "sleep" if "sleep" in self._loaded_sheets else "idle"
            fps = 3
        else:
            sheet_key = "idle"
            fps = 6

        sheet = self._loaded_sheets.get(sheet_key) or self._loaded_sheets.get("idle")
        if sheet is not None:
            self._player.play(sheet, fps=fps, loop=loop)

    def say(self, text: str, *, ttl_ms: int = 4000) -> None:
        """Display a speech bubble above the pet."""
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
        return Path("data") / "body_position.json"

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

                    min_clamped_x = geom.left() - self.width() + PEEK_REVEAL_WIDTH_PX
                    max_clamped_x = geom.right() - PEEK_REVEAL_WIDTH_PX
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
                json.dumps({"x": self.x(), "y": self.y(), "docked_edge": self._docked_edge}),
                "utf-8",
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Peek Docking & Hover Animations
    # ------------------------------------------------------------------
    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        """Mouse hover: peek out if docked at the edge."""
        if self._docked_edge is not None:
            self._retract_timer.stop()
            self._expand_from_dock()
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

    def _retract_to_dock(self) -> None:
        """Slide half-body into screen edge, leaving only the head peeking out."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None or self._docked_edge is None:
            return
        geom = screen.availableGeometry()
        if self._docked_edge == "right":
            self.move(geom.right() - PEEK_REVEAL_WIDTH_PX, self.y())
        elif self._docked_edge == "left":
            self.move(geom.left() - self.width() + PEEK_REVEAL_WIDTH_PX, self.y())
        self._is_peek_expanded = False
        self._hover_poll_timer.stop()
        self._save_position()

    # ------------------------------------------------------------------
    # Mouse interaction (Screen-clamped Dragging and Edge Snapping)
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
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
                    min_x = geom.left() - self.width() + PEEK_REVEAL_WIDTH_PX
                    max_x = geom.right() - PEEK_REVEAL_WIDTH_PX
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
            event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._hover_poll_timer.stop()
        self._retract_timer.stop()
        self._bubble.close()
        self._player.stop()
        super().closeEvent(event)
