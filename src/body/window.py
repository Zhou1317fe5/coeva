"""Transparent, frameless, always-on-top window hosting the companion pet."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCloseEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from src.body.animation import AnimationPlayer, SpriteSheet, SpriteSheetError
from src.body.contracts import PetState
from src.body.speech_bubble import SpeechBubble

CLICK_DRAG_THRESHOLD_PX = 4
EDGE_SNAP_DISTANCE_PX = 30
DEFAULT_SCALE = 2


class PetWindow(QWidget):
    """The desktop pet window with animation player, speech bubble, dragging, and edge clamping."""

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

        self._label = QLabel(self)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._label.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._label.setStyleSheet("background: transparent; border: 0;")

        self._player = AnimationPlayer(self)
        self._player.frame_changed.connect(self._on_frame_changed)

        self._bubble = SpeechBubble()

        # Drag state
        self._drag_offset: QPoint | None = None
        self._press_pos: QPoint | None = None
        self._has_moved = False

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
        """Switch the pet's animated state with distinct visual rhythms."""
        self._current_state = state

        sheet_key = "idle"
        fps = 6
        loop = True

        if state == PetState.SLEEPING:
            sheet_key = "sleep" if "sleep" in self._loaded_sheets else "idle"
            fps = 3
        elif state == PetState.THINKING:
            # Thoughtful slower breathing rhythm (calm, not frantic walking)
            sheet_key = "idle"
            fps = 4
        elif state == PetState.WORKING:
            # Tool working: lively walking/typing rhythm
            sheet_key = "walk" if "walk" in self._loaded_sheets else "idle"
            fps = 8
        elif state == PetState.HAPPY:
            # Cheerful quick cadence
            sheet_key = "idle"
            fps = 10
        elif state == PetState.ERROR:
            # Alert pace
            sheet_key = "idle"
            fps = 12

        sheet = self._loaded_sheets.get(sheet_key) or self._loaded_sheets.get("idle")
        if sheet is not None:
            self._player.play(sheet, fps=fps, loop=loop)

    def say(self, text: str, *, ttl_ms: int = 4000) -> None:
        """Display a speech bubble above the pet."""
        self._bubble.show_message(text, ttl_ms=ttl_ms)
        self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())

    def reset_to_default_position(self) -> None:
        """Emergency reset: brings the pet back to visible screen bottom-right corner."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            new_x = geom.right() - self.width() - 30
            new_y = geom.bottom() - self.height() - 20
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
            # Default fall back
            fallback_x = geom.right() - 220
            fallback_y = geom.bottom() - 200

            if cfg.is_file():
                try:
                    data = json.loads(cfg.read_text("utf-8"))
                    saved_x = int(data.get("x", fallback_x))
                    saved_y = int(data.get("y", fallback_y))

                    # Safety check: ensure saved position is inside the visible screen!
                    clamped_x = max(geom.left(), min(saved_x, geom.right() - 100))
                    clamped_y = max(geom.top(), min(saved_y, geom.bottom() - 100))
                    self.move(clamped_x, clamped_y)
                    return
                except (json.JSONDecodeError, ValueError, OSError):
                    pass

            self.move(fallback_x, fallback_y)

    def _save_position(self) -> None:
        cfg = self._get_config_path()
        try:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(json.dumps({"x": self.x(), "y": self.y()}), "utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Mouse interaction (Screen-clamped Dragging and Snapping)
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

                # Clamp strictly to the available screen boundary! (Never lost off-screen)
                screen = self.screen() or QApplication.primaryScreen()
                if screen is not None:
                    geom = screen.availableGeometry()
                    clamped_x = max(geom.left(), min(desired_pos.x(), geom.right() - self.width()))
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
                # Snap to edge if within snapping threshold
                screen = self.screen() or QApplication.primaryScreen()
                if screen is not None:
                    geom = screen.availableGeometry()
                    cur_x = self.x()
                    cur_y = self.y()

                    # Right edge snap
                    if abs(geom.right() - self.width() - cur_x) < EDGE_SNAP_DISTANCE_PX:
                        cur_x = geom.right() - self.width()
                    # Left edge snap
                    elif abs(cur_x - geom.left()) < EDGE_SNAP_DISTANCE_PX:
                        cur_x = geom.left()
                    # Bottom edge snap
                    if abs(geom.bottom() - self.height() - cur_y) < EDGE_SNAP_DISTANCE_PX:
                        cur_y = geom.bottom() - self.height()

                    self.move(cur_x, cur_y)

                self._save_position()
            else:
                self.clicked.emit()
            event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._bubble.close()
        self._player.stop()
        super().closeEvent(event)
