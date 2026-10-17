"""Codex-style docked interaction pill bar for instant slice feeding and voice interaction.

1:1 reproduction of the Codex companion interaction pill docked directly beneath the pet body:
- Handle mode: A subtle, tiny white pill handle beneath the pet feet.
- Pill mode: Expands on hover into [ Edit / SquarePen | Divider | Voice Waveform ılı ].
- Input mode: Expands on click into [ + ] [ 开始新聊天 ] [ ↑ ].
- Voice mode: Animated pulsing waveform lines with listening feedback.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QByteArray, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPalette,
    QPen,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QWidget,
)

# Modes
MODE_HANDLE = "handle"
MODE_PILL = "pill"
MODE_INPUT = "input"

# Exact Dimensions matching Codex
HANDLE_PILL_WIDTH = 28
HANDLE_PILL_HEIGHT = 6

PILL_WIDTH = 76
PILL_HEIGHT = 28

INPUT_WIDTH = 260
INPUT_HEIGHT = 34

SHADOW_MARGIN = 6

# SVG definitions matching Codex icons
_EDIT_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24"'
    ' fill="none" stroke="#334155" stroke-width="1.8" stroke-linecap="round"'
    ' stroke-linejoin="round">'
    '<path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>'
    '<path d="M18.375 2.625a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4Z"/>'
    "</svg>"
)

_PLUS_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"'
    ' fill="none" stroke="#64748B" stroke-width="2.2" stroke-linecap="round"'
    ' stroke-linejoin="round">'
    '<path d="M5 12h14"/>'
    '<path d="M12 5v14"/>'
    "</svg>"
)

_SUBMIT_ARROW_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"'
    ' fill="none" stroke="#ffffff" stroke-width="2.6" stroke-linecap="round"'
    ' stroke-linejoin="round">'
    '<path d="m5 12 7-7 7 7"/>'
    '<path d="M12 19V5"/>'
    "</svg>"
)


class _FeederLineEdit(QLineEdit):
    """Custom single-line text input capturing Enter to submit and Esc to cancel."""

    submit_pressed = Signal()
    cancel_pressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("开始新聊天")

        # 1:1 Codex exact font: Microsoft YaHei UI 14px, antialiased, matching Windows Electron
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(14)
        font.setWeight(QFont.Weight.Normal)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)

        # Set placeholder text color explicitly to neutral gray #8E8EA0
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(142, 142, 160))
        self.setPalette(pal)

        self.setStyleSheet(
            "QLineEdit {"
            "  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;"
            "  font-size: 14px;"
            "  color: #1F2937;"
            "  background: transparent;"
            "  border: none;"
            "  padding: 0 4px;"
            "  selection-background-color: #38BDF8;"
            "}"
            "QLineEdit::placeholder {"
            "  color: #8E8EA0;"
            "  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;"
            "  font-size: 14px;"
            "}"
        )

    # Backward compatibility with older QPlainTextEdit interface
    def setPlainText(self, text: str) -> None:  # noqa: N802
        self.setText(text)

    def toPlainText(self) -> str:  # noqa: N802
        return self.text()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submit_pressed.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.cancel_pressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class _CircleIconButton(QWidget):
    """Circular button rendering a solid background and centered SVG icon."""

    clicked = Signal()

    def __init__(
        self,
        size: int,
        bg_color: str,
        hover_bg: str,
        svg_str: str,
        icon_size: float,
        *,
        tooltip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self._bg_color = QColor(bg_color)
        self._hover_bg = QColor(hover_bg)
        self._renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")), self)
        self._icon_size = icon_size
        self._is_hovered = False

    def set_bg_color(self, color_str: str) -> None:
        self._bg_color = QColor(color_str)
        self.update()

    def set_hover_bg(self, color_str: str) -> None:
        self._hover_bg = QColor(color_str)
        self.update()

    def enterEvent(self, event: object) -> None:  # noqa: N802
        self._is_hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = self._hover_bg if self._is_hovered else self._bg_color
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.width(), self.height())

        cx = (float(self.width()) - self._icon_size) / 2.0
        cy = (float(self.height()) - self._icon_size) / 2.0
        self._renderer.render(painter, QRectF(cx, cy, self._icon_size, self._icon_size))


class _EditIconButton(QWidget):
    """Clickable edit icon button rendering the delicate SquarePen vector icon."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("开始输入")
        self._is_hovered = False
        self._renderer = QSvgRenderer(QByteArray(_EDIT_ICON_SVG.encode("utf-8")), self)

    def enterEvent(self, event: object) -> None:  # noqa: N802
        self._is_hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._is_hovered:
            painter.setBrush(QColor(241, 245, 249))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

        icon_size = 15.0
        target_rect = QRectF(
            (self.width() - icon_size) / 2.0,
            (self.height() - icon_size) / 2.0,
            icon_size,
            icon_size,
        )
        self._renderer.render(painter, target_rect)


class _DividerWidget(QWidget):
    """Subtle 1px vertical divider between Edit and Voice buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(1, 12)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(QColor(229, 231, 235))  # #E5E7EB
        painter.drawLine(0, 0, 0, self.height())


class _WaveformIconButton(QWidget):
    """Clickable audio waveform button with animated pulsing voice lines."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("语音互动 / 倾听模式")
        self._is_hovered = False
        self._is_active = False
        self._bar_heights: list[float] = [4.0, 12.0, 8.0, 3.5]
        self._anim_step = 0

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(110)
        self._anim_timer.timeout.connect(self._on_anim_tick)

    @property
    def is_active(self) -> bool:
        return self._is_active

    def set_active(self, active: bool) -> None:
        if self._is_active == active:
            return
        self._is_active = active
        if active:
            self._anim_timer.start()
        else:
            self._anim_timer.stop()
            self._bar_heights = [4.0, 12.0, 8.0, 3.5]
        self.update()

    def _on_anim_tick(self) -> None:
        patterns = [
            [4.0, 12.0, 8.0, 3.5],
            [7.0, 8.0, 13.0, 6.0],
            [10.0, 5.0, 10.0, 9.0],
            [6.0, 13.0, 6.0, 11.0],
            [9.0, 10.0, 12.0, 5.0],
            [5.0, 7.0, 9.0, 3.5],
        ]
        self._anim_step = (self._anim_step + 1) % len(patterns)
        self._bar_heights = patterns[self._anim_step]
        self.update()

    def enterEvent(self, event: object) -> None:  # noqa: N802
        self._is_hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._anim_timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._is_hovered:
            painter.setBrush(QColor(241, 245, 249))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

        # Active color is deep vibrant blue, idle is refined slate
        stroke_color = QColor("#2563EB") if self._is_active else QColor("#334155")
        pen = QPen(stroke_color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        spacing = 3.2
        xs = [cx - 1.5 * spacing, cx - 0.5 * spacing, cx + 0.5 * spacing, cx + 1.5 * spacing]

        for x, h in zip(xs, self._bar_heights, strict=False):
            painter.drawLine(
                int(round(x)),
                int(round(cy - h / 2.0)),
                int(round(x)),
                int(round(cy + h / 2.0)),
            )


class SliceFeederBar(QWidget):
    """1:1 Codex-style docked interaction pill bar positioned directly beneath the pet.

    - Handle mode (idle): Small white pill handle beneath the pet feet.
    - Pill mode (hover): Expands into [ Edit | Divider | Waveform ].
    - Input mode (clicked): Expands into [ + ] [ 开始新聊天 ] [ ↑ ].
    """

    slice_submitted = Signal(str)
    cancelled = Signal()
    voice_clicked = Signal(bool)  # True = listening started, False = listening stopped
    mode_changed = Signal(bool)  # True = expanded (input), False = collapsed (handle/pill)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self._current_mode = MODE_HANDLE
        self._last_pet_pos: QPoint | None = None
        self._last_pet_size: tuple[int, int] | None = None
        self._drag_offset: QPoint | None = None

        # Container widgets for different modes
        self._handle_widget = QWidget(self)
        self._pill_widget = QWidget(self)
        self._input_widget = QWidget(self)

        self._setup_pill_ui()
        self._setup_input_ui()

        # Hide debouncer timer to smoothly retract back to handle when cursor leaves
        self._retract_to_handle_timer = QTimer(self)
        self._retract_to_handle_timer.setSingleShot(True)
        self._retract_to_handle_timer.setInterval(260)
        self._retract_to_handle_timer.timeout.connect(self._on_retract_timeout)

        # Start in handle mode
        self._apply_mode(MODE_HANDLE)

    def _setup_pill_ui(self) -> None:
        layout = QHBoxLayout(self._pill_widget)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(1)

        self._btn_edit = _EditIconButton(self._pill_widget)
        self._btn_edit.clicked.connect(self.expand_input)
        layout.addWidget(self._btn_edit)

        self._divider = _DividerWidget(self._pill_widget)
        layout.addWidget(self._divider)

        self._btn_voice = _WaveformIconButton(self._pill_widget)
        self._btn_voice.clicked.connect(self._toggle_voice_mode)
        layout.addWidget(self._btn_voice)

    def _setup_input_ui(self) -> None:
        layout = QHBoxLayout(self._input_widget)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        # Left Plus Button (circular button with +)
        self._btn_plus = _CircleIconButton(
            size=22,
            bg_color="#F1F5F9",
            hover_bg="#E2E8F0",
            svg_str=_PLUS_ICON_SVG,
            icon_size=11.0,
            tooltip="清空/开始新聊天",
            parent=self._input_widget,
        )
        self._btn_plus.clicked.connect(self._on_plus_clicked)
        layout.addWidget(self._btn_plus)

        # Center Text Input
        self._input = _FeederLineEdit(self._input_widget)
        self._input.submit_pressed.connect(self._on_submit)
        self._input.cancel_pressed.connect(self._on_cancel)
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input, 1)

        # Right Send Button (circular blue button with white up-arrow)
        self._btn_submit = _CircleIconButton(
            size=24,
            bg_color="#93C5FD",
            hover_bg="#60A5FA",
            svg_str=_SUBMIT_ARROW_SVG,
            icon_size=12.0,
            tooltip="发送 (Enter)",
            parent=self._input_widget,
        )
        self._btn_submit.clicked.connect(self._on_submit)
        layout.addWidget(self._btn_submit)

    def _on_text_changed(self, text: str) -> None:
        """Update submit button color dynamically when text is entered."""
        if text.strip():
            self._btn_submit.set_bg_color("#3B82F6")
            self._btn_submit.set_hover_bg("#2563EB")
        else:
            self._btn_submit.set_bg_color("#93C5FD")
            self._btn_submit.set_hover_bg("#60A5FA")

    def _on_plus_clicked(self) -> None:
        self._input.clear()
        self._input.setFocus()

    @property
    def current_mode(self) -> str:
        return self._current_mode

    @property
    def is_expanded(self) -> bool:
        return self._current_mode == MODE_INPUT

    @property
    def is_voice_active(self) -> bool:
        return self._btn_voice.is_active

    def set_voice_active(self, active: bool) -> None:
        self._btn_voice.set_active(active)

    def _toggle_voice_mode(self) -> None:
        new_state = not self._btn_voice.is_active
        self._btn_voice.set_active(new_state)
        self.voice_clicked.emit(new_state)

    def show_handle(self) -> None:
        """Switch to tiny pill handle mode."""
        if self._current_mode != MODE_HANDLE:
            self._apply_mode(MODE_HANDLE)

    def show_pill(self) -> None:
        """Switch to full dual-button pill mode."""
        self._retract_to_handle_timer.stop()
        if self._current_mode != MODE_PILL:
            self._apply_mode(MODE_PILL)

    def expand_input(self) -> None:
        """Expand into the full input bar mode and focus."""
        self._retract_to_handle_timer.stop()
        if self._current_mode != MODE_INPUT:
            self._apply_mode(MODE_INPUT)
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def collapse(self) -> None:
        """Collapse back from input mode."""
        self._input.clear()
        self.show_pill()

    def toggle_input(self) -> None:
        if self._current_mode == MODE_INPUT:
            self.collapse()
        else:
            self.expand_input()

    def _apply_mode(self, mode: str) -> None:
        self._current_mode = mode

        # Hide all containers first
        self._handle_widget.hide()
        self._pill_widget.hide()
        self._input_widget.hide()

        if mode == MODE_HANDLE:
            pill_w, pill_h = HANDLE_PILL_WIDTH, HANDLE_PILL_HEIGHT
            self._handle_widget.setGeometry(SHADOW_MARGIN, SHADOW_MARGIN, pill_w, pill_h)
            self._handle_widget.show()
        elif mode == MODE_PILL:
            pill_w, pill_h = PILL_WIDTH, PILL_HEIGHT
            self._pill_widget.setGeometry(SHADOW_MARGIN, SHADOW_MARGIN, pill_w, pill_h)
            self._pill_widget.show()
        else:  # MODE_INPUT
            pill_w, pill_h = INPUT_WIDTH, INPUT_HEIGHT
            self._input_widget.setGeometry(SHADOW_MARGIN, SHADOW_MARGIN, pill_w, pill_h)
            self._input_widget.show()

        total_w = pill_w + SHADOW_MARGIN * 2
        total_h = pill_h + SHADOW_MARGIN * 2
        self.setFixedSize(total_w, total_h)
        self._re_anchor()
        self.update()
        self.mode_changed.emit(mode == MODE_INPUT)

    def _re_anchor(self) -> None:
        if self._last_pet_pos is not None and self._last_pet_size is not None:
            self.anchor_to_pet(
                self._last_pet_pos, self._last_pet_size[0], self._last_pet_size[1]
            )

    def anchor_to_pet(self, pet_pos: QPoint, pet_width: int, pet_height: int) -> None:
        """Dock the interaction bar centered directly beneath the pet's feet."""
        self._last_pet_pos = pet_pos
        self._last_pet_size = (pet_width, pet_height)

        total_w = self.width()
        total_h = self.height()

        ideal_center_x = pet_pos.x() + pet_width // 2
        target_x = ideal_center_x - total_w // 2
        target_y = pet_pos.y() + pet_height + 3 - SHADOW_MARGIN

        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            margin = 8
            # Clamping horizontally
            target_x = max(geom.left() + margin, min(target_x, geom.right() - total_w - margin))
            # If bottom screen bound is reached, clamp or place above pet
            if target_y + total_h > geom.bottom() - margin:
                above_y = pet_pos.y() - total_h - 4 + SHADOW_MARGIN
                if above_y >= geom.top() + margin:
                    target_y = above_y
                else:
                    target_y = geom.bottom() - total_h - margin

        self.move(target_x, target_y)

    def enterEvent(self, event: object) -> None:  # noqa: N802
        self._retract_to_handle_timer.stop()
        if self._current_mode == MODE_HANDLE:
            self.show_pill()

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        # Start debounced retract timer when cursor leaves
        if self._current_mode == MODE_PILL and not self._btn_voice.is_active:
            self._retract_to_handle_timer.start()

    def _on_retract_timeout(self) -> None:
        if self._current_mode == MODE_PILL and not self._btn_voice.is_active:
            self.show_handle()

    def _on_submit(self) -> None:
        text = self._input.text().strip()
        if text:
            self.slice_submitted.emit(text)
        self._input.clear()
        self.show_handle()

    def _on_cancel(self) -> None:
        self.cancelled.emit()
        self._input.clear()
        self.show_handle()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._retract_to_handle_timer.stop()
        self._btn_voice.set_active(False)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Dragging Support (active when standalone / not docked to pet)
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._current_mode == MODE_HANDLE:
                self.show_pill()
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None:
            cur_pos = event.globalPosition().toPoint()
            new_pos = cur_pos - self._drag_offset
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

    def _get_pos_file(self) -> Path:
        return Path("data") / "feeder_position.json"

    def _save_pos(self) -> None:
        try:
            pos_file = self._get_pos_file()
            pos_file.parent.mkdir(parents=True, exist_ok=True)
            pos_file.write_text(json.dumps({"x": self.x(), "y": self.y()}), "utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Legacy Compatibility methods (for SliceFeederOverlay compatibility)
    # ------------------------------------------------------------------
    def toggle_or_show(self) -> None:
        if self.isVisible() and self.is_expanded:
            self.collapse()
        else:
            self.expand_input()

    def show_at_saved_or_center(self) -> None:
        if self._last_pet_pos is None:
            screen = QApplication.primaryScreen()
            if screen is not None:
                geom = screen.availableGeometry()
                target_x = geom.center().x() - self.width() // 2
                target_y = geom.center().y() - self.height() // 2 - 60
                self.move(target_x, target_y)
        self.expand_input()

    def show_centered(self) -> None:
        self.show_at_saved_or_center()

    # ------------------------------------------------------------------
    # Rendering: Soft drop shadow + pure white rounded pill
    # ------------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = float(SHADOW_MARGIN)
        pill_w = float(self.width() - SHADOW_MARGIN * 2)
        pill_h = float(self.height() - SHADOW_MARGIN * 2)
        radius = pill_h / 2.0  # perfect capsule radius

        # Multi-pass soft diffused drop shadow (refined to match Codex)
        for step in range(3):
            spread = 2.0 - float(step) * 0.7
            alpha = int(4 + step * 4)  # 4, 8, 12
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(
                QRectF(
                    margin - spread,
                    margin - spread + 1.5,
                    pill_w + spread * 2.0,
                    pill_h + spread * 2.0,
                ),
                radius + spread,
                radius + spread,
            )
            painter.fillPath(shadow_path, QColor(0, 0, 0, alpha))

        # Solid pure white pill background
        pill_path = QPainterPath()
        pill_path.addRoundedRect(QRectF(margin, margin, pill_w, pill_h), radius, radius)
        painter.fillPath(pill_path, QColor(255, 255, 255, 252))

        # Delicate hairline outer border
        painter.setPen(QPen(QColor(0, 0, 0, 10), 1.0))
        painter.drawPath(pill_path)


# Alias for 100% backward compatibility with all existing tests and imports
SliceFeederOverlay = SliceFeederBar
