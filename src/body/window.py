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
DEFAULT_SCALE = 2


class PetWindow(QWidget):
    """The desktop pet window with animation player, speech bubble, and dragging."""

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

    def _load_spritesheets(self) -> None:  # noqa: F811
        """Preload sprite sheets available in the pet sprites directory."""
        sprites_dir = self.pet_dir / "sprites"
        if not sprites_dir.is_dir():
            return

        # Common sprite sheet files and typical frame counts
        known_files = {
            "idle": (sprites_dir / "idle.png", 8, 6),
            "walk": (sprites_dir / "walk.png", 6, 10),
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

        # Map semantic states to loaded sprites
        sheet_key = "idle"
        fps = 6
        loop = True

        if state == PetState.SLEEPING:
            sheet_key = "sleep" if "sleep" in self._loaded_sheets else "idle"
            fps = 3
        elif state in (PetState.WORKING, PetState.THINKING):
            sheet_key = "walk" if "walk" in self._loaded_sheets else "idle"
            fps = 10
        elif state in (PetState.HAPPY, PetState.ERROR, PetState.WAITING):
            sheet_key = "idle"
            fps = 8

        sheet = self._loaded_sheets.get(sheet_key) or self._loaded_sheets.get("idle")
        if sheet is not None:
            self._player.play(sheet, fps=fps, loop=loop)

    def say(self, text: str, *, ttl_ms: int = 4000) -> None:
        """Display a speech bubble above the pet."""
        self._bubble.show_message(text, ttl_ms=ttl_ms)
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
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text("utf-8"))
                self.move(int(data.get("x", 200)), int(data.get("y", 200)))
                return
            except (json.JSONDecodeError, ValueError, OSError):
                pass
        # Default positioning: bottom right corner of primary screen
        screen = QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            self.move(geom.right() - 220, geom.bottom() - 200)

    def _save_position(self) -> None:
        cfg = self._get_config_path()
        try:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(json.dumps({"x": self.x(), "y": self.y()}), "utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Mouse interaction (Dragging and Clicking)
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
                new_pos = cur_pos - self._drag_offset
                self.move(new_pos)
                self.position_changed.emit(new_pos.x(), new_pos.y())
                if self._bubble.isVisible():
                    self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._drag_offset = None
            if self._has_moved:
                self._save_position()
            else:
                self.clicked.emit()
            event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._bubble.close()
        self._player.stop()
        super().closeEvent(event)
