"""Global hotkey listener using pynput with thread-safe Qt Signal bridge."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from pynput import keyboard
from PySide6.QtCore import QObject, Signal


class _QtSignalBridge(QObject):
    """Bridge emitting Qt signal safely across thread boundaries."""

    hotkey_triggered = Signal()


class GlobalHotkeyListener:
    """Background listener for global desktop hotkeys, dispatching safely to Qt main thread."""

    def __init__(self, hotkey_combo: str, callback: Callable[[], None]) -> None:
        self.hotkey_combo = hotkey_combo
        self.callback = callback
        self._bridge = _QtSignalBridge()
        self._bridge.hotkey_triggered.connect(self.callback)

        self._listener: Any = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start listening in a background thread."""
        if self._running:
            return
        self._running = True

        def _on_press() -> None:
            # Emit signal across thread boundary -> Qt safely executes in GUI main thread
            self._bridge.hotkey_triggered.emit()

        def _run() -> None:
            hotkeys = {self.hotkey_combo: _on_press}
            try:
                with keyboard.GlobalHotKeys(hotkeys) as listener:
                    self._listener = listener
                    listener.join()
            except Exception:
                pass

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop hotkey listening."""
        self._running = False
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
