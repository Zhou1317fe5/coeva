"""Reusable custom UI components replicating Clawd on Desk modern design system."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget


class SwitchButton(QWidget):
    """Modern iOS / macOS style capsule toggle switch widget inspired by Clawd on Desk."""

    toggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        checked: bool = False,
        active_color: str = "#d97757",  # Clawd on Desk warm terracotta orange
        inactive_color: str = "#d4d4d8",  # Clawd on Desk light mode switch off zinc
        knob_color: str = "#ffffff",
    ) -> None:
        super().__init__(parent)
        self._checked = checked
        self._active_color = QColor(active_color)
        self._inactive_color = QColor(inactive_color)
        self._knob_color = QColor(knob_color)
        self._offset: float = 1.0 if checked else 0.0

        self.setFixedSize(38, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(38, 20)

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        if self._checked != checked:
            self._checked = checked
            self._anim.stop()
            self._anim.setStartValue(self._offset)
            self._anim.setEndValue(1.0 if checked else 0.0)
            self._anim.start()
            self.toggled.emit(self._checked)
            self.update()

    def toggle(self) -> None:
        self.setChecked(not self._checked)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, val: float) -> None:
        self._offset = val
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.toggle()
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return) and self.isEnabled():
            self.toggle()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2.0

        # Interpolate background color
        r0, r1 = self._inactive_color.red(), self._active_color.red()
        g0, g1 = self._inactive_color.green(), self._active_color.green()
        b0, b1 = self._inactive_color.blue(), self._active_color.blue()

        r = int(r0 + (r1 - r0) * self._offset)
        g = int(g0 + (g1 - g0) * self._offset)
        b = int(b0 + (b1 - b0) * self._offset)
        bg_color = QColor(r, g, b)

        if not self.isEnabled():
            bg_color.setAlpha(100)

        # Draw capsule track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        # Draw knob
        margin = 2.0
        knob_d = h - margin * 2
        start_x = margin
        end_x = w - knob_d - margin
        knob_x = start_x + (end_x - start_x) * self._offset

        knob_color = QColor(self._knob_color)
        if not self.isEnabled():
            knob_color.setAlpha(180)

        painter.setPen(QColor(0, 0, 0, 25))
        painter.setBrush(knob_color)
        painter.drawEllipse(QRectF(knob_x, margin, knob_d, knob_d))


def svg_to_icon(svg_content: str, size: int = 18, color_hex: str = "#6b6b70") -> QIcon:
    """Render an inline SVG string directly into a sharp QIcon with color replacement."""
    processed_svg = svg_content.replace('stroke="currentColor"', f'stroke="{color_hex}"')
    processed_svg = processed_svg.replace('fill="currentColor"', f'fill="{color_hex}"')
    svg_bytes = processed_svg.encode("utf-8")

    renderer = QSvgRenderer(svg_bytes)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


# SVG paths (24x24 viewBox, stroke-width=1.5)
_SVG_BASE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round">'
)

CLAWD_ICONS = {
    # Gear (General Settings)
    "general": (
        f"{_SVG_BASE}"
        '<path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06'
        "a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09"
        "A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83"
        "l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09"
        "A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83"
        "l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09"
        "a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83"
        "l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09"
        'a1.65 1.65 0 0 0-1.51 1Z"/>'
        "</svg>"
    ),
    # Bolt (Agents)
    "agents": (f'{_SVG_BASE}<path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z"/></svg>'),
    # Palette (Theme & Body)
    "theme": (
        f"{_SVG_BASE}"
        '<path d="M12 22a10 10 0 1 1 10-10c0 2.5-2 4-4 4h-2a2 2 0 0 0-1 3.7A2 2 0 0 1 12 22Z"/>'
        '<circle cx="7.5" cy="10.5" r="1" fill="currentColor"/>'
        '<circle cx="12" cy="7.5" r="1" fill="currentColor"/>'
        '<circle cx="16.5" cy="10.5" r="1" fill="currentColor"/>'
        "</svg>"
    ),
    # Brain / Mind (Core & Sanctuary)
    "core": (
        f"{_SVG_BASE}"
        '<path d="M11 20A7 7 0 0 1 4 13C4 8 8 3 19 3c0 11-5 17-8 17Z"/>'
        '<path d="M19 3v8a7 7 0 0 1-7 7"/>'
        "</svg>"
    ),
    # Info circle (About)
    "about": (f'{_SVG_BASE}<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/></svg>'),
}
