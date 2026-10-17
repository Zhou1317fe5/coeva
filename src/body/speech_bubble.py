"""Speech bubble overlay positioned above the pet with screen clamping and interactive reply."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class _BubbleReplyInput(QLineEdit):
    """Custom inline reply input capturing Enter to submit and Esc to cancel."""

    submit_pressed = Signal()
    cancel_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submit_pressed.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.cancel_pressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class SpeechBubble(QWidget):
    """Interactive floating speech bubble that displays messages and supports direct replies."""

    user_replied = Signal(str, str)  # (user_reply, original_pet_speech)
    bubble_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._on_dismiss_timeout)

        self._current_text = ""
        self._is_replying = False

        # Main Layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(14, 10, 14, 14)  # space for tail
        self._main_layout.setSpacing(6)

        # Message Label
        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #1e293b; background: transparent;")
        font = QFont("Segoe UI", 10)
        self._label.setFont(font)
        self._main_layout.addWidget(self._label)

        # Subtle reply prompt hint
        self._hint_label = QLabel("💬 点击回复", self)
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent;")
        self._main_layout.addWidget(self._hint_label)

        # Inline Reply Input Box (hidden by default)
        self._input_row = QWidget(self)
        input_layout = QHBoxLayout(self._input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)

        self._input = _BubbleReplyInput(self._input_row)
        self._input.setPlaceholderText("回复... (Enter发送, Esc取消)")
        self._input.setStyleSheet(
            "QLineEdit {"
            "  color: #0f172a;"
            "  background: rgba(255, 255, 255, 230);"
            "  border: 1px solid #cbd5e1;"
            "  border-radius: 6px;"
            "  padding: 4px 8px;"
            "  font-size: 11px;"
            "}"
            "QLineEdit:focus {"
            "  border: 1px solid #64748b;"
            "}"
        )
        self._input.submit_pressed.connect(self._on_submit_reply)
        self._input.cancel_pressed.connect(self._on_cancel_reply)
        input_layout.addWidget(self._input)
        self._input_row.hide()
        self._main_layout.addWidget(self._input_row)

        self._tail_relative_x: float = 0.5
        self.setMinimumWidth(160)
        self.setMaximumWidth(320)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide()

    @property
    def current_message(self) -> str:
        return self._current_text

    def show_message(self, text: str, *, ttl_ms: int = 4000) -> None:
        """Display text, hide reply input, and start dismissal timer."""
        self._current_text = text.strip()
        self._label.setText(self._current_text)
        self._is_replying = False
        self._input_row.hide()
        self._hint_label.show()
        self.adjustSize()
        self._dismiss_timer.stop()
        self.show()
        if ttl_ms > 0:
            self._dismiss_timer.start(ttl_ms)

    def open_reply_input(self) -> None:
        """Expand inline input directly in the bubble so user can reply."""
        self._is_replying = True
        self._dismiss_timer.stop()
        self._hint_label.hide()
        self._input_row.show()
        self.adjustSize()
        self._input.clear()
        self._input.setFocus()

    def _on_submit_reply(self) -> None:
        reply_text = self._input.text().strip()
        if reply_text:
            orig = self._current_text
            self._is_replying = False
            self._input_row.hide()
            self._hint_label.hide()
            self._label.setText("（思考中...）")
            self.adjustSize()
            self.user_replied.emit(reply_text, orig)
        else:
            self._on_cancel_reply()

    def _on_cancel_reply(self) -> None:
        self._is_replying = False
        self._input_row.hide()
        self._hint_label.show()
        self.adjustSize()
        self.hide()

    def _on_dismiss_timeout(self) -> None:
        if not self._is_replying:
            self.hide()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        """Hovering pauses dismissal timer so user has time to read or reply."""
        self._dismiss_timer.stop()
        self._hint_label.setStyleSheet("color: #475569; font-size: 10px; font-weight: bold;")
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        """Leaving restarts dismissal timer if user is not actively typing."""
        if not self._is_replying and self.isVisible():
            self._hint_label.setStyleSheet("color: #94a3b8; font-size: 10px;")
            self._dismiss_timer.start(3000)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Clicking on bubble opens inline reply input instead of abruptly closing."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_replying:
                self.open_reply_input()
                self.bubble_clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def anchor_to_pet(self, pet_pos: QPoint, pet_width: int, pet_height: int) -> None:
        """Move the bubble sitting above pet, strictly clamped within screen bounds."""
        bubble_width = self.width()
        bubble_height = self.height()

        ideal_center_x = pet_pos.x() + pet_width // 2
        target_x = ideal_center_x - bubble_width // 2
        target_y = pet_pos.y() - bubble_height - 6

        # Smart Screen Clamping
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            margin = 12
            target_x = max(
                geom.left() + margin, min(target_x, geom.right() - bubble_width - margin)
            )
            target_y = max(geom.top() + margin, target_y)

            relative_x = (ideal_center_x - target_x) / max(1.0, float(bubble_width))
            self._tail_relative_x = max(0.15, min(relative_x, 0.85))
        else:
            self._tail_relative_x = 0.5

        self.move(target_x, target_y)
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Draw a soft-translucent bubble with rounded corners and steered tail."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height()) - 6  # reserve 6px for bottom tail

        path = QPainterPath()
        path.addRoundedRect(1.0, 1.0, w - 2.0, h - 2.0, 10.0, 10.0)

        tail_x = w * self._tail_relative_x
        path.moveTo(tail_x - 6.0, h - 2.0)
        path.lineTo(tail_x, h + 5.0)
        path.lineTo(tail_x + 6.0, h - 2.0)

        # Background fill
        painter.fillPath(path, QColor(255, 255, 255, 246))

        # Border
        painter.setPen(QColor(203, 213, 225, 220))  # #cbd5e1
        painter.drawPath(path)
