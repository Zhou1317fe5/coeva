"""Global hotkey listener using pynput."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from pynput import keyboard


class GlobalHotkeyListener:
    """Background listener for global desktop hotkeys."""

    def __init__(self, hotkey_combo: str, callback: Callable[[], None]) -> None:
        self.hotkey_combo = hotkey_combo
        self.callback = callback
        self._listener: Any = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start listening in a background thread."""
        if self._running:
            return
        self._running = True

        def _run() -> None:
            hotkeys = {self.hotkey_combo: self.callback}
            with keyboard.GlobalHotKeys(hotkeys) as listener:
                self._listener = listener
                listener.join()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop hotkey listening."""
        self._running = False
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
