"""Global hotkey listener using pynput with thread-safe Qt Signal bridge.

This module owns the whole global-hotkey domain: the canonical combination
format persisted on disk, the Qt-key-event -> pynput mapping used by the
settings recorder, and the background listener that dispatches to Qt.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pynput import keyboard
from PySide6.QtCore import QObject, Qt, Signal

DEFAULT_FEEDER_HOTKEY = "<alt>+<space>"

# Canonical output order for modifiers, so one combination has exactly one
# written form. The first four are the modifiers a user is expected to use.
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "cmd", "alt_gr")
_MODIFIER_TOKENS = frozenset(_MODIFIER_ORDER)

_MODIFIER_LABELS = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "cmd": "Win",
    "alt_gr": "AltGr",
}

# Qt.Key names whose pynput counterpart is spelled differently.
_QT_KEY_ALIASES = {
    "escape": "esc",
    "return": "enter",
    "control": "ctrl",
    "meta": "cmd",
    "print": "print_screen",
}

# Keys that are modifiers themselves: pressing one records nothing on its own.
_QT_MODIFIER_KEY_NAMES = frozenset(
    {"Key_Control", "Key_Alt", "Key_Shift", "Key_Meta", "Key_AltGr", "Key_Super_L", "Key_Super_R"}
)

_PYNPUT_KEY_BY_NORMALIZED = {
    member.name.lower().replace("_", ""): member.name for member in keyboard.Key
}


def _build_qt_key_tokens() -> dict[str, str]:
    """Derive the Qt.Key -> pynput token table from both libraries' own names.

    Deriving beats hand-writing: a Qt or pynput upgrade that adds or renames a
    key shows up here instead of silently drifting out of sync.
    """
    tokens: dict[str, str] = {}
    for member in Qt.Key:
        name = member.name
        if not name.startswith("Key_"):
            continue
        raw = name[4:]
        if len(raw) == 1 and raw.isalnum():
            tokens[name] = raw.lower()
            continue
        normalized = raw.lower().replace("_", "")
        alias = _QT_KEY_ALIASES.get(normalized, normalized).replace("_", "")
        pynput_name = _PYNPUT_KEY_BY_NORMALIZED.get(alias)
        if pynput_name is not None:
            tokens[name] = f"<{pynput_name}>"
    return tokens


_QT_KEY_TOKENS = _build_qt_key_tokens()


@dataclass(frozen=True)
class HotkeySpec:
    """A validated global hotkey: canonical pynput spec plus its display label."""

    spec: str
    display: str


def _normalize_token(token: str) -> str | None:
    """Reduce one combination part to a bare pynput token, or None if unknown."""
    text = token.strip().lower()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1]
    if not text:
        return None
    if len(text) == 1:
        return text if text.isalnum() else None
    return _PYNPUT_KEY_BY_NORMALIZED.get(text.replace("_", ""))


def _render_token(name: str) -> str:
    """Render a bare pynput token back into canonical spec form."""
    return name if len(name) == 1 else f"<{name}>"


def _token_label(name: str) -> str:
    """Human label for one bare token."""
    if name in _MODIFIER_LABELS:
        return _MODIFIER_LABELS[name]
    if len(name) == 1:
        return name.upper()
    return name.replace("_", " ").title()


def _display_for(spec: str) -> str:
    """Turn a canonical spec into its display label without re-validating it."""
    return " + ".join(_token_label(part.strip().strip("<>").lower()) for part in spec.split("+"))


def parse_hotkey(raw: str) -> HotkeySpec | None:
    """Validate a user-facing combination and return its canonical form.

    Accepts ``"<alt>+<space>"``, ``"Alt+Space"`` and ``"alt + space"`` alike.
    Returns None when the combination is unusable: no modifier, no single main
    key, an unknown key name, or anything pynput itself rejects.
    """
    if not raw or not raw.strip():
        return None

    modifiers: list[str] = []
    main_keys: list[str] = []
    for part in raw.split("+"):
        name = _normalize_token(part)
        if name is None:
            return None
        if name in _MODIFIER_TOKENS:
            if name not in modifiers:
                modifiers.append(name)
        else:
            main_keys.append(name)

    if not modifiers or len(main_keys) != 1:
        return None

    ordered = sorted(modifiers, key=_MODIFIER_ORDER.index)
    spec = "+".join([_render_token(m) for m in ordered] + [_render_token(main_keys[0])])
    try:
        keyboard.HotKey.parse(spec)
    except ValueError:
        return None
    return HotkeySpec(spec=spec, display=_display_for(spec))


def hotkey_display(spec: str) -> str:
    """Display label for a stored spec, falling back to the raw text."""
    parsed = parse_hotkey(spec)
    return parsed.display if parsed is not None else spec


def hotkey_from_qt(modifiers: Qt.KeyboardModifier, key: Qt.Key) -> HotkeySpec | None:
    """Map a Qt key press to a hotkey, or None while the chord is still incomplete.

    A bare modifier or a key outside the supported set returns None so the
    settings recorder keeps waiting instead of saving something unusable.
    """
    if key.name in _QT_MODIFIER_KEY_NAMES:
        return None
    token = _QT_KEY_TOKENS.get(key.name)
    if token is None:
        return None

    pressed: list[str] = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        pressed.append("ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        pressed.append("alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        pressed.append("shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        pressed.append("cmd")
    if not pressed:
        return None

    return parse_hotkey("+".join([*pressed, token]))


class _QtSignalBridge(QObject):
    """Bridge emitting Qt signal safely across thread boundaries."""

    hotkey_triggered = Signal()


class GlobalHotkeyListener:
    """Background listener for global desktop hotkeys, dispatching safely to Qt main thread.

    One instance binds one combination; the owner rebuilds it when the
    combination changes, which keeps the listener itself immutable in shape.
    """

    def __init__(self, hotkey_combo: str, callback: Callable[[], None]) -> None:
        self.hotkey_combo = hotkey_combo
        self.callback = callback
        self._bridge = _QtSignalBridge()
        self._bridge.hotkey_triggered.connect(self.callback)

        self._listener: Any = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start listening in a background thread.

        The combination is validated here, on the calling thread, against this
        module's own rule (a modifier plus one main key) rather than pynput's
        looser one. An illegal chord therefore raises where the caller can
        report it, instead of vanishing inside the worker.
        """
        if self._running:
            return
        parsed = parse_hotkey(self.hotkey_combo)
        if parsed is None:
            raise ValueError(f"非法快捷键组合: {self.hotkey_combo!r}")
        self.hotkey_combo = parsed.spec
        self._running = True

        def _on_press() -> None:
            # Emit signal across thread boundary -> Qt safely executes in GUI main thread
            self._bridge.hotkey_triggered.emit()

        def _run() -> None:
            hotkeys = {self.hotkey_combo: _on_press}
            with keyboard.GlobalHotKeys(hotkeys) as listener:
                self._listener = listener
                if not self._running:
                    # stop() ran before this listener existed. Leaving the block
                    # stops it, so a superseded hotkey can never stay bound.
                    return
                listener.join()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listening and wait for the worker, so the old chord cannot stay bound.

        The worker may not have built its listener yet when this is called; the
        ``_running`` check inside it covers that ordering, and the join below
        waits for whichever path the worker took.
        """
        self._running = False
        listener = self._listener
        if listener is not None:
            listener.stop()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._listener = None
        self._thread = None
