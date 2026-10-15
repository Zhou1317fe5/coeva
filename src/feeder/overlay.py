"""Transient, frosted-glass overlay for quick slice feeding with draggable support."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class _FeederInput(QPlainTextEdit):
    """Custom PlainTextEdit capturing Enter to submit and Shift+Enter for newlines."""

    submit_pressed = Signal()
    cancel_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.submit_pressed.emit()
                event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.cancel_pressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class SliceFeederOverlay(QWidget):
    """Semi-transparent transient modal for instant slice feeding, fully draggable."""

    slice_submitted = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.setFixedSize(500, 160)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 12, 18, 14)
        main_layout.setSpacing(8)

        # Header bar (serves as drag handle)
        header_layout = QHBoxLayout()
        title_label = QLabel("🌱 随手投喂切片 (按住顶部可拖动)", self)
        title_label.setStyleSheet("color: #E2E8F0; font-weight: bold;")
        font = QFont("Segoe UI", 10)
        font.setBold(True)
        title_label.setFont(font)
        header_layout.addWidget(title_label)

        hint_label = QLabel("Enter 发送 · Esc 退出", self)
        hint_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        header_layout.addStretch()
        header_layout.addWidget(hint_label)
        main_layout.addLayout(header_layout)

        # Text Input
        self._input = _FeederInput(self)
        self._input.setPlaceholderText("记下刚才的灵感、困惑、生活感悟或有意思的代码思考...")
        self._input.setStyleSheet(
            "QPlainTextEdit {"
            "  color: #F8FAFC;"
            "  background: rgba(15, 23, 42, 190);"
            "  border: 1px solid rgba(148, 163, 184, 90);"
            "  border-radius: 8px;"
            "  padding: 8px;"
            "  font-size: 14px;"
            "  selection-background-color: #38BDF8;"
            "}"
        )
        input_font = QFont("Segoe UI", 10)
        self._input.setFont(input_font)
        self._input.submit_pressed.connect(self._on_submit)
        self._input.cancel_pressed.connect(self._on_cancel)
        main_layout.addWidget(self._input)

        # Drag tracking
        self._drag_offset: QPoint | None = None

    def _get_pos_file(self) -> Path:
        return Path("data") / "feeder_position.json"

    def toggle_or_show(self) -> None:
        """Toggle visibility: if visible, hide; otherwise show and focus."""
        if self.isVisible():
            self.hide()
        else:
            self.show_at_saved_or_center()

    def show_at_saved_or_center(self) -> None:
        """Show overlay restoring last dragged position, or centered by default."""
        pos_file = self._get_pos_file()
        screen = QApplication.primaryScreen()
        default_x, default_y = 300, 300
        if screen is not None:
            geom = screen.availableGeometry()
            default_x = geom.center().x() - self.width() // 2
            default_y = geom.center().y() - self.height() // 2 - 80

        if pos_file.is_file():
            try:
                data = json.loads(pos_file.read_text("utf-8"))
                target_x = int(data.get("x", default_x))
                target_y = int(data.get("y", default_y))
                # Validate in screen
                if screen is not None:
                    geom = screen.availableGeometry()
                    target_x = max(geom.left(), min(target_x, geom.right() - self.width()))
                    target_y = max(geom.top(), min(target_y, geom.bottom() - self.height()))
                self.move(target_x, target_y)
            except Exception:
                self.move(default_x, default_y)
        else:
            self.move(default_x, default_y)

        self._input.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def show_centered(self) -> None:
        self.show_at_saved_or_center()

    def _save_pos(self) -> None:
        try:
            pos_file = self._get_pos_file()
            pos_file.parent.mkdir(parents=True, exist_ok=True)
            pos_file.write_text(json.dumps({"x": self.x(), "y": self.y()}), "utf-8")
        except Exception:
            pass

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Allow dragging the input overlay from anywhere except the inner input box."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None:
            cur_pos = event.globalPosition().toPoint()
            new_pos = cur_pos - self._drag_offset
            # Clamp to screen
            screen = self.screen() or QApplication.primaryScreen()
            if screen is not None:
                geom = screen.availableGeometry()
                clamped_x = max(geom.left(), min(new_pos.x(), geom.right() - self.width()))
                clamped_y = max(geom.top(), min(new_pos.y(), geom.bottom() - self.height()))
                self.move(clamped_x, clamped_y)
            else:
                self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self._save_pos()
            event.accept()

    def _on_submit(self) -> None:
        text = self._input.toPlainText().strip()
        if text:
            self.slice_submitted.emit(text)
        self.hide()

    def _on_cancel(self) -> None:
        self.cancelled.emit()
        self.hide()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Draw a frosted glass dark pill container with top drag bar indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(1.0, 1.0, float(self.width() - 2), float(self.height() - 2), 12.0, 12.0)

        # Dark frosted background
        painter.fillPath(path, QColor(24, 28, 38, 240))

        # Subtle elegant border
        painter.setPen(QColor(100, 116, 139, 160))
        painter.drawPath(path)
