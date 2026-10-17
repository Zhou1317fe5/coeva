"""Unit tests for low-frequency State Care periodic intervention wiring."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast

from PySide6.QtWidgets import QApplication, QWidget

import run_companion
from run_companion import (
    _CARE_CHECK_INTERVAL_MS,
    _IN_FLIGHT_COOLDOWN_SECONDS,
    CompanionApp,
)
from src.connectors.contracts import AgentEvent, AgentEventType

_app = QApplication.instance() or QApplication([])


class _FakeController:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.actions: list[str] = []

    def say(self, text: str, ttl_ms: int = 4000) -> None:
        self.said.append(text)

    def perform_action(self, action_id: str) -> None:
        self.actions.append(action_id)


class _FakeIntervention:
    def __init__(self, message_to_return: str | None = None) -> None:
        self.msg = message_to_return
        self.last_in_flight: bool | None = None

    def evaluate_intervention(self, *, is_task_in_flight: bool = False) -> str | None:
        self.last_in_flight = is_task_in_flight
        return None if is_task_in_flight else self.msg


class _FakeWatcher:
    def __init__(self) -> None:
        self.activity_recorded = False

    def record_activity(self) -> None:
        self.activity_recorded = True


def _make_app(msg: str | None = None) -> tuple[CompanionApp, _FakeController, _FakeIntervention]:
    app = CompanionApp.__new__(CompanionApp)
    app.window = QWidget()
    ctrl = _FakeController()
    interv = _FakeIntervention(msg)
    app.controller = cast("object", ctrl)  # type: ignore[assignment]
    app.intervention = cast("object", interv)  # type: ignore[assignment]
    app.watcher = cast("object", _FakeWatcher())  # type: ignore[assignment]
    app._last_agent_active_at = None
    return app, ctrl, interv


def test_in_flight_timing_gate() -> None:
    """Test task in flight detection based on event stream and cooldown."""
    app, _, _ = _make_app()
    base = datetime(2026, 10, 16, 14, 0, 0)

    # 1. Initially no activity -> not in flight
    assert app._is_task_in_flight(now=base) is False

    # 2. Tool call occurs -> In flight
    ev = AgentEvent.create("hermes", AgentEventType.PRE_TOOL_USE)
    app._on_agent_event_received(ev)
    assert app._last_agent_active_at is not None

    # Within cooldown
    now_soon = app._last_agent_active_at + timedelta(seconds=10)
    assert app._is_task_in_flight(now=now_soon) is True

    # Beyond cooldown (30s)
    now_later = app._last_agent_active_at + timedelta(seconds=_IN_FLIGHT_COOLDOWN_SECONDS + 5)
    assert app._is_task_in_flight(now=now_later) is False

    app.window.close()


def test_check_state_care_triggers_bubble_when_idle() -> None:
    """When idle and intervention approved, trigger gentle care bubble and rest action."""
    app, ctrl, interv = _make_app("今天这个任务折腾挺久了，先歇口气？")

    # 1. Currently idle -> approved
    app._check_state_care()
    assert interv.last_in_flight is False
    assert len(ctrl.said) == 1
    assert "歇口气" in ctrl.said[0]
    assert ctrl.actions == ["rest"]

    # 2. Currently in flight -> suppressed by Timing Gate
    app._last_agent_active_at = datetime.now()
    app._check_state_care()
    assert interv.last_in_flight is True
    # No new speech triggered
    assert len(ctrl.said) == 1

    app.window.close()


def test_state_care_timer_interval_and_call_site() -> None:
    """Ensure timer is configured to 5 minutes and scheduled at startup."""
    app, _, _ = _make_app()
    CompanionApp._setup_state_care(app)
    assert app.care_timer.isActive()
    assert app.care_timer.interval() == _CARE_CHECK_INTERVAL_MS
    assert _CARE_CHECK_INTERVAL_MS == 5 * 60 * 1000

    import inspect

    src = inspect.getsource(run_companion.CompanionApp.__init__)
    assert "_setup_state_care()" in src

    app.care_timer.stop()
    app.window.close()
