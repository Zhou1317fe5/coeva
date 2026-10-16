"""Wiring test for the daily evidence decay (Phase 2 spec section 4.2 lifecycle).

`ChronicleStore.prune()` had no production caller, so the retention contract was
nominal: the events table would have grown without bound. This guards the wiring
in CompanionApp without booting the whole GUI.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtWidgets import QApplication, QWidget

import run_companion
from run_companion import _PRUNE_INTERVAL_MS, CompanionApp

_app = QApplication.instance() or QApplication([])


class _FakeChronicle:
    """Records prune() calls instead of touching a real database."""

    def __init__(self) -> None:
        self.prune_calls = 0

    def prune(self, **kwargs: object) -> int:
        self.prune_calls += 1
        return 0


class _FakeChronicleRaises(_FakeChronicle):
    def prune(self, **kwargs: object) -> int:
        self.prune_calls += 1
        raise sqlite3_error()


def sqlite3_error() -> Exception:
    import sqlite3

    return sqlite3.OperationalError("database is locked")


def _app_with(chronicle: _FakeChronicle) -> CompanionApp:
    """A CompanionApp skeleton: real QWidget for the timer parent, fake store."""
    app = CompanionApp.__new__(CompanionApp)
    app.chronicle = cast("object", chronicle)  # type: ignore[assignment]
    app.window = QWidget()
    return app


def test_decay_prunes_at_startup_and_daily() -> None:
    """Startup runs prune once, then a daily timer keeps running it."""
    fake = _FakeChronicle()
    app = _app_with(fake)

    CompanionApp._setup_decay(app)

    assert fake.prune_calls == 1, "prune must run once at startup"
    assert app.prune_timer.isActive(), "the daily decay timer must be running"
    assert app.prune_timer.interval() == _PRUNE_INTERVAL_MS
    assert _PRUNE_INTERVAL_MS == 24 * 60 * 60 * 1000, "decay should be daily"

    # Firing the timer prunes again.
    app.prune_timer.timeout.emit()
    assert fake.prune_calls == 2

    app.prune_timer.stop()
    app.window.close()


def test_decay_survives_a_locked_database() -> None:
    """A locked database must not take the companion down."""
    app = _app_with(_FakeChronicleRaises())

    CompanionApp._run_prune(app)  # must not raise

    app.window.close()


def test_prune_call_site_exists_in_the_app() -> None:
    """Guard against the timer being dropped from __init__ again."""
    import inspect

    source = inspect.getsource(run_companion.CompanionApp.__init__)
    assert "_setup_decay()" in source, "__init__ must schedule evidence decay"
