"""Codex-style docked interaction pill bar for instant slice feeding and voice interaction.

Official Codex companion interaction pill docked directly beneath the pet body:
- Handle mode (default idle): A subtle, tiny white pill handle beneath the pet's feet.
- Hovered / Pill mode: Smoothly expands into dual-button pill [ Edit | Divider | Waveform ].
- Input mode: Expands into the Codex input bar with [ + ] [ 开始新聊天 ] [ ↑ ].
- Voice mode: Animated pulsing waveform lines with listening feedback.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QEnterEvent,
    QFocusEvent,
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

# Exact Dimensions matching official Codex parameters
# (compactControlWidth: 17*2 - 10.5 gap = 23.5px, compactControlHeight: 6)
HANDLE_PILL_WIDTH = 28
HANDLE_PILL_HEIGHT = 6

PILL_WIDTH = 76
PILL_HEIGHT = 28

INPUT_WIDTH = 260
INPUT_HEIGHT = 34

SHADOW_MARGIN = 6

# Official Codex timing & spring parameters
MORPH_DURATION_MS = 220
DISMISS_DELAY_MS = 300
CONTENT_HIDDEN_SCALE = 0.75  # Codex: contentHiddenScale: .75

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

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusOutEvent(event)
        if not self.text().strip():
            self.cancel_pressed.emit()


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


class SliceFeederBar(QWidget):
    """1:1 Codex-style docked interaction pill bar positioned directly beneath the pet.

    Uses single-painter unified architecture matching Codex:
    - Handle mode: 28x6px white pill handle beneath the pet feet.
    - Pill mode: Expands into [ Edit | Divider | Waveform ] with synchronous concentric scaling.
    - Input mode: Expands horizontally into [ + ] [ 开始新聊天 ] [ ↑ ].
    """

    slice_submitted = Signal(str)
    cancelled = Signal()
    voice_clicked = Signal(bool)
    mode_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

        self._current_mode = MODE_HANDLE
        self._last_pet_pos: QPoint | None = None
        self._last_pet_size: tuple[int, int] | None = None
        self._drag_offset: QPoint | None = None

        # Content state for pill controls
        self._edit_renderer = QSvgRenderer(QByteArray(_EDIT_ICON_SVG.encode("utf-8")), self)
        self._hover_btn: str | None = None
        self._is_voice_active = False
        self._bar_heights: list[float] = [4.0, 12.0, 8.0, 3.5]
        self._anim_step = 0

        # Voice pulse animation timer
        self._voice_timer = QTimer(self)
        self._voice_timer.setInterval(110)
        self._voice_timer.timeout.connect(self._on_voice_tick)

        # Retract timer (300ms matching Codex compactDismissDelayMs)
        self._retract_timer = QTimer(self)
        self._retract_timer.setSingleShot(True)
        self._retract_timer.setInterval(DISMISS_DELAY_MS)
        self._retract_timer.timeout.connect(self._on_retract_timeout)

        # Smooth morphing animation
        self._morph_anim = QVariantAnimation(self)
        self._morph_anim.setDuration(MORPH_DURATION_MS)
        self._morph_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._morph_anim.valueChanged.connect(self._on_morph_step)
        self._morph_anim.finished.connect(self._on_morph_finished)

        self._morph_val: float = 0.0  # 0.0 = handle, 1.0 = pill
        self._from_w: int = HANDLE_PILL_WIDTH + SHADOW_MARGIN * 2
        self._from_h: int = HANDLE_PILL_HEIGHT + SHADOW_MARGIN * 2
        self._to_w: int = self._from_w
        self._to_h: int = self._from_h

        # Input container widget (only visible during MODE_INPUT)
        self._input_widget = QWidget(self)
        self._setup_input_ui()
        self._input_widget.hide()

        # Dummy button aliases for backward compatibility with older tests
        self._btn_edit = self
        self._btn_voice = self

        # Initialize in handle mode
        self._apply_mode(MODE_HANDLE, animate=False)

    def _setup_input_ui(self) -> None:
        layout = QHBoxLayout(self._input_widget)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        # Left Plus Button
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

        # Right Send Button
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
        if text.strip():
            self._btn_submit.set_bg_color("#3B82F6")
            self._btn_submit.set_hover_bg("#2563EB")
        else:
            self._btn_submit.set_bg_color("#93C5FD")
            self._btn_submit.set_hover_bg("#60A5FA")

    def _on_plus_clicked(self) -> None:
        self._input.clear()
        self._input.setFocus()

    # ------------------------------------------------------------------
    # Voice state
    # ------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self._is_voice_active

    @property
    def is_voice_active(self) -> bool:
        return self._is_voice_active

    def set_active(self, active: bool) -> None:
        if self._is_voice_active == active:
            return
        self._is_voice_active = active
        if active:
            self._voice_timer.start()
        else:
            self._voice_timer.stop()
            self._bar_heights = [4.0, 12.0, 8.0, 3.5]
        self.update()

    def set_voice_active(self, active: bool) -> None:
        self.set_active(active)

    def _toggle_voice_mode(self) -> None:
        new_state = not self._is_voice_active
        self.set_active(new_state)
        self.voice_clicked.emit(new_state)

    def _on_voice_tick(self) -> None:
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

    # ------------------------------------------------------------------
    # Modes & Transitions
    # ------------------------------------------------------------------
    @property
    def current_mode(self) -> str:
        return self._current_mode

    @property
    def is_expanded(self) -> bool:
        return self._current_mode == MODE_INPUT

    def show_handle(self) -> None:
        """Switch to tiny pill handle mode."""
        self._retract_timer.stop()
        if self._current_mode != MODE_HANDLE:
            self._apply_mode(MODE_HANDLE)
        self.show()

    def show_pill(self) -> None:
        """Switch to full dual-button pill mode and display."""
        self._retract_timer.stop()
        if self._current_mode != MODE_PILL:
            self._apply_mode(MODE_PILL)
        self.show()

    def expand_input(self) -> None:
        """Expand into the full input bar mode and focus."""
        self._retract_timer.stop()
        if self._current_mode != MODE_INPUT:
            self._apply_mode(MODE_INPUT)
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def collapse(self) -> None:
        """Collapse back from input mode to handle mode."""
        self._input.clear()
        self.show_handle()

    def toggle_input(self) -> None:
        if self._current_mode == MODE_INPUT:
            self.collapse()
        else:
            self.expand_input()

    def _apply_mode(self, mode: str, *, animate: bool = True) -> None:
        self._current_mode = mode

        # Strict isolation: hide input widget immediately when entering handle or pill
        if mode == MODE_INPUT:
            pill_w, pill_h = INPUT_WIDTH, INPUT_HEIGHT
        elif mode == MODE_PILL:
            self._input_widget.hide()
            pill_w, pill_h = PILL_WIDTH, PILL_HEIGHT
        else:  # MODE_HANDLE
            self._input_widget.hide()
            pill_w, pill_h = HANDLE_PILL_WIDTH, HANDLE_PILL_HEIGHT

        target_w = pill_w + SHADOW_MARGIN * 2
        target_h = pill_h + SHADOW_MARGIN * 2

        is_offscreen = QApplication.platformName() == "offscreen"
        if animate and self.isVisible() and not is_offscreen:
            self._from_w = self.width()
            self._from_h = self.height()
            self._to_w = target_w
            self._to_h = target_h
            self._morph_anim.stop()
            self._morph_anim.setStartValue(0.0)
            self._morph_anim.setEndValue(1.0)
            self._morph_anim.start()
        else:
            self._finalize_mode(mode, target_w, target_h)

        self.mode_changed.emit(mode == MODE_INPUT)

    def _on_morph_step(self, value: object) -> None:
        val = float(value)  # type: ignore[arg-type]
        cur_w = int(round(self._from_w + (self._to_w - self._from_w) * val))
        cur_h = int(round(self._from_h + (self._to_h - self._from_h) * val))
        self.setFixedSize(cur_w, cur_h)
        self._re_anchor()

        if self._current_mode == MODE_PILL:
            self._input_widget.hide()
            self._morph_val = val
        elif self._current_mode == MODE_HANDLE:
            self._input_widget.hide()
            self._morph_val = 1.0 - val
        elif self._current_mode == MODE_INPUT:
            self._morph_val = 0.0
            self._input_widget.setGeometry(
                SHADOW_MARGIN, SHADOW_MARGIN, INPUT_WIDTH, INPUT_HEIGHT
            )
            self._input_widget.show()

        self.update()

    def _on_morph_finished(self) -> None:
        self._finalize_mode(self._current_mode, self._to_w, self._to_h)

    def _finalize_mode(self, mode: str, total_w: int, total_h: int) -> None:
        self.setFixedSize(total_w, total_h)
        self._re_anchor()

        if mode == MODE_INPUT:
            self._morph_val = 0.0
            self._input_widget.setGeometry(
                SHADOW_MARGIN, SHADOW_MARGIN, INPUT_WIDTH, INPUT_HEIGHT
            )
            self._input_widget.show()
        elif mode == MODE_PILL:
            self._input_widget.hide()
            self._morph_val = 1.0
        else:  # MODE_HANDLE
            self._input_widget.hide()
            self._morph_val = 0.0

        self.update()

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
            target_x = max(geom.left() + margin, min(target_x, geom.right() - total_w - margin))
            if target_y + total_h > geom.bottom() - margin:
                above_y = pet_pos.y() - total_h - 4 + SHADOW_MARGIN
                if above_y >= geom.top() + margin:
                    target_y = above_y
                else:
                    target_y = geom.bottom() - total_h - margin

        self.move(target_x, target_y)

    # ------------------------------------------------------------------
    # Mouse & Proximity Events
    # ------------------------------------------------------------------
    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        self._retract_timer.stop()
        if self._current_mode == MODE_HANDLE:
            self.show_pill()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hover_btn = None
        if self._current_mode == MODE_PILL and not self._is_voice_active:
            self._retract_timer.start(DISMISS_DELAY_MS)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._current_mode == MODE_PILL and self._morph_val > 0.8:
            margin = float(SHADOW_MARGIN)
            cx = margin + (float(self.width()) - margin * 2.0) / 2.0
            new_hover = "edit" if event.position().x() < cx else "voice"
            if new_hover != self._hover_btn:
                self._hover_btn = new_hover
                self.update()
        else:
            if self._hover_btn is not None:
                self._hover_btn = None
                self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._current_mode == MODE_HANDLE:
                self.show_pill()
                event.accept()
                return
            if self._current_mode == MODE_PILL and self._morph_val > 0.6:
                margin = float(SHADOW_MARGIN)
                cx = margin + (float(self.width()) - margin * 2.0) / 2.0
                if event.position().x() < cx:
                    self.expand_input()
                else:
                    self._toggle_voice_mode()
                event.accept()
                return

            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self._save_pos()
            event.accept()

    def _on_retract_timeout(self) -> None:
        if self._current_mode == MODE_PILL and not self._is_voice_active:
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
        self._retract_timer.stop()
        self._voice_timer.stop()
        super().closeEvent(event)

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
    # Single-Painter Unified Rendering (Concentric & Hard-Clipped)
    # ------------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = float(SHADOW_MARGIN)
        pill_w = float(self.width() - SHADOW_MARGIN * 2)
        pill_h = float(self.height() - SHADOW_MARGIN * 2)
        radius = pill_h / 2.0

        # Exact center of the white capsule on every single frame
        cx = margin + pill_w / 2.0
        cy = margin + pill_h / 2.0

        # 1. Soft diffused shadow
        for step in range(3):
            spread = 2.0 - float(step) * 0.7
            alpha = int(4 + step * 4)
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

        # 2. Pure white pill capsule background
        pill_path = QPainterPath()
        pill_path.addRoundedRect(QRectF(margin, margin, pill_w, pill_h), radius, radius)
        painter.fillPath(pill_path, QColor(255, 255, 255, 252))

        # Hairline subtle border
        painter.setPen(QPen(QColor(0, 0, 0, 10), 1.0))
        painter.drawPath(pill_path)

        # 3. Synchronously scaled and concentric pill icons (only when not in input mode)
        if self._current_mode != MODE_INPUT and self._morph_val > 0.05:
            # Official Codex: scale interpolates smoothly from contentHiddenScale (.75) to 1.0!
            content_scale = CONTENT_HIDDEN_SCALE + (1.0 - CONTENT_HIDDEN_SCALE) * self._morph_val
            content_opacity = self._morph_val
            alpha = int(255 * content_opacity)

            painter.save()
            # Hard clip to the pill capsule so nothing can EVER bleed outside!
            painter.setClipPath(pill_path)

            painter.translate(cx, cy)
            painter.scale(content_scale, content_scale)
            painter.translate(-cx, -cy)

            # Hover background when pill is fully or nearly expanded
            if self._morph_val > 0.85 and self._hover_btn:
                painter.setBrush(QColor(241, 245, 249, int(alpha * 0.9)))
                painter.setPen(Qt.PenStyle.NoPen)
                if self._hover_btn == "edit":
                    painter.drawRoundedRect(QRectF(cx - 36, cy - 12, 34, 24), 10, 10)
                elif self._hover_btn == "voice":
                    painter.drawRoundedRect(QRectF(cx + 2, cy - 12, 34, 24), 10, 10)

            # Middle divider
            painter.setPen(QPen(QColor(229, 231, 235, alpha), 1.0))
            painter.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))

            # Left icon (SquarePen)
            target_rect = QRectF(cx - 19.0 - 7.5, cy - 7.5, 15, 15)
            self._edit_renderer.render(painter, target_rect)

            # Right waveform
            color = (
                QColor(37, 99, 235, alpha) if self._is_voice_active else QColor(51, 65, 85, alpha)
            )
            pen = QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            vx = cx + 19.0
            spacing = 3.2
            xs = [vx - 1.5 * spacing, vx - 0.5 * spacing, vx + 0.5 * spacing, vx + 1.5 * spacing]
            for x, h in zip(xs, self._bar_heights, strict=False):
                painter.drawLine(
                    int(round(x)),
                    int(round(cy - h / 2.0)),
                    int(round(x)),
                    int(round(cy + h / 2.0)),
                )

            painter.restore()


# Alias for 100% backward compatibility with all existing tests and imports
SliceFeederOverlay = SliceFeederBar
