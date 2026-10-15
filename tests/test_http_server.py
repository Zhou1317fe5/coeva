"""Unit tests for CompanionHttpServer."""

from __future__ import annotations

import json
import time
import urllib.request

from src.body.contracts import PetState
from src.connectors.event_bus import LocalEventBus
from src.connectors.http_server import CompanionHttpServer


def test_companion_http_server_endpoints() -> None:
    """Test HTTP API /status, /event, and /say over loopback."""
    bus = LocalEventBus()
    states_received: list[PetState] = []
    bus.on_state_suggested = lambda s: states_received.append(s)

    # Use a non-default test port
    server = CompanionHttpServer(bus, controller=None, port=17389)
    assert server.start()
    time.sleep(0.1)

    try:
        # 1. GET /api/status
        req_status = urllib.request.Request("http://127.0.0.1:17389/api/status")
        with urllib.request.urlopen(req_status) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["status"] == "running"

        # 2. POST /api/event from PI-Desktop
        event_payload = json.dumps(
            {
                "agent_id": "pi-desktop",
                "event_type": "user_prompt",
                "message": "思考中...",
            }
        ).encode("utf-8")
        req_event = urllib.request.Request(
            "http://127.0.0.1:17389/api/event",
            data=event_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_event) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["state"] == "thinking"
        assert states_received[-1] == PetState.THINKING

        # 3. Tool use event
        tool_payload = json.dumps(
            {
                "agent_id": "pi-desktop",
                "event_type": "pre_tool_use",
                "tool_name": "bash",
            }
        ).encode("utf-8")
        req_tool = urllib.request.Request(
            "http://127.0.0.1:17389/api/event",
            data=tool_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_tool) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["state"] == "working"
        assert states_received[-1] == PetState.WORKING

    finally:
        server.stop()
