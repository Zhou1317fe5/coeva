"""Transient, frosted-glass overlay for quick slice feeding."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPainterPath
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
    """Semi-transparent transient modal for instant slice feeding."""

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

        self.setFixedSize(480, 160)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(8)

        # Header bar
        header_layout = QHBoxLayout()
        title_label = QLabel("🌱 随手投喂切片 (Slice Feed)", self)
        title_label.setStyleSheet("color: #E2E8F0; font-weight: bold;")
        font = QFont("Segoe UI", 10)
        font.setBold(True)
        title_label.setFont(font)
        header_layout.addWidget(title_label)

        hint_label = QLabel("Enter 发送 · Esc 取消", self)
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
            "  background: rgba(15, 23, 42, 180);"
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

    def toggle_or_show(self) -> None:
        """Toggle visibility: if visible and active, close it; otherwise show centered."""
        if self.isVisible():
            self.hide()
        else:
            self.show_centered()

    def show_centered(self) -> None:
        """Center the overlay on the active screen and focus input."""
        screen = QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            x = geom.center().x() - self.width() // 2
            y = geom.center().y() - self.height() // 2 - 80
            self.move(x, y)
        self._input.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def _on_submit(self) -> None:
        text = self._input.toPlainText().strip()
        if text:
            self.slice_submitted.emit(text)
        self.hide()

    def _on_cancel(self) -> None:
        self.cancelled.emit()
        self.hide()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Draw a frosted glass dark pill container."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(1.0, 1.0, float(self.width() - 2), float(self.height() - 2), 12.0, 12.0)

        # Dark frosted background
        painter.fillPath(path, QColor(24, 28, 38, 235))

        # Subtle elegant border
        painter.setPen(QColor(100, 116, 139, 160))
        painter.drawPath(path)
