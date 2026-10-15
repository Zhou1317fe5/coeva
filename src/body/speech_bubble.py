"""Speech bubble overlay positioned above the pet."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SpeechBubble(QWidget):
    """A floating, non-focus-stealing speech bubble that displays messages above the pet."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

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

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)

        # Content layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 14)  # space for tail

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #222222; background: transparent;")
        font = QFont("Segoe UI", 10)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        self._label.setFont(font)
        layout.addWidget(self._label)

        self.setMaximumWidth(280)
        self.hide()

    def show_message(self, text: str, *, ttl_ms: int = 4000) -> None:
        """Display text and start dismissal timer."""
        self._label.setText(text)
        self.adjustSize()
        self._dismiss_timer.stop()
        self.show()
        if ttl_ms > 0:
            self._dismiss_timer.start(ttl_ms)

    def anchor_to_pet(self, pet_pos: QPoint, pet_width: int, pet_height: int) -> None:
        """Move the bubble horizontally centered and sitting directly above the pet."""
        bubble_width = self.width()
        bubble_height = self.height()

        target_x = pet_pos.x() + (pet_width - bubble_width) // 2
        target_y = pet_pos.y() - bubble_height - 6

        # Avoid placing outside the top screen margin
        target_y = max(10, target_y)
        self.move(target_x, target_y)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Clicking on the bubble dismisses it immediately."""
        self._dismiss_timer.stop()
        self.hide()
        super().mousePressEvent(event)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Draw a warm, soft-translucent bubble with rounded corners and a small tail."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height()) - 6  # reserve 6px for bottom tail

        # Main bubble body
        path = QPainterPath()
        path.addRoundedRect(1.0, 1.0, w - 2.0, h - 2.0, 10.0, 10.0)

        # Bottom pointer tail
        tail_x = w / 2.0
        path.moveTo(tail_x - 6.0, h - 2.0)
        path.lineTo(tail_x, h + 5.0)
        path.lineTo(tail_x + 6.0, h - 2.0)

        # Background fill
        painter.fillPath(path, QColor(255, 255, 255, 235))

        # Subtle border
        painter.setPen(QColor(190, 190, 190, 180))
        painter.drawPath(path)
