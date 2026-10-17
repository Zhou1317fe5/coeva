"""Unit tests for Clawd-on-Desk style widgets."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from src.body.widgets import CLAWD_ICONS, SwitchButton, svg_to_icon

_app = QApplication.instance()
if _app is None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _app = QApplication([])


def test_switch_button_state_and_toggled() -> None:
    switch = SwitchButton(checked=False)
    assert not switch.isChecked()
    assert switch.sizeHint() == QSize(38, 20)

    events: list[bool] = []
    switch.toggled.connect(events.append)

    switch.setChecked(True)
    assert switch.isChecked()
    assert events == [True]

    switch.toggle()
    assert not switch.isChecked()
    assert events == [True, False]
    switch.deleteLater()


def test_svg_to_icon_renders() -> None:
    for name, svg in CLAWD_ICONS.items():
        icon = svg_to_icon(svg, size=18, color_hex="#a1a1aa")
        assert not icon.isNull(), f"Icon {name} rendered null"
