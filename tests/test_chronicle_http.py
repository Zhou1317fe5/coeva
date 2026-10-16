"""Loopback restriction tests for the Chronicle HTTP endpoints (AC-7).

A remote client must not be able to read the user's slices or evidence, while the
WSL cross-network Agent path (see hook_manager.py) stays unaffected.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.connectors.event_bus import LocalEventBus
from src.connectors.http_server import CompanionHttpServer, is_loopback_address
from src.memory.store import ChronicleStore, SliceRecord

_app = QApplication.instance() or QApplication([])

_PORT = 17395


def _start_server(store: ChronicleStore | None) -> CompanionHttpServer:
    server = CompanionHttpServer(LocalEventBus(), controller=None, store=store, port=_PORT)
    assert server.start()
    time.sleep(0.1)
    return server


def _get(path: str) -> tuple[int, dict[str, object]]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{_PORT}{path}") as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


def test_ac7_chronicle_endpoints_answer_on_loopback() -> None:
    """AC-7: a loopback client gets 200 from every Chronicle endpoint."""
    store = ChronicleStore(Path(":memory:"))
    store.record_slice(
        SliceRecord(
            id="s1",
            timestamp="2026-10-15T10:00:00+00:00",
            content="明天再说",
            mood_flag="neutral",
        )
    )
    server = _start_server(store)
    try:
        status, body = _get("/api/chronicle/stats")
        assert status == 200
        assert body["ok"] is True
        assert body["slices"] == 1

        for route in (
            "/api/chronicle/slices?limit=5",
            "/api/chronicle/evidence?limit=5",
            "/api/chronicle/episodes?limit=5",
        ):
            status, body = _get(route)
            assert status == 200, f"{route} returned {status}"
            assert body["ok"] is True

        status, _ = _get("/api/chronicle/nonsense")
        assert status == 404
    finally:
        server.stop()


def test_chronicle_search_over_loopback() -> None:
    """POST search returns matches for a 2-character Chinese keyword."""
    store = ChronicleStore(Path(":memory:"))
    store.record_slice(
        SliceRecord(
            id="s2",
            timestamp="2026-10-15T10:00:00+00:00",
            content="今天这个问题明天再继续",
            mood_flag="neutral",
        )
    )
    server = _start_server(store)
    try:
        payload = json.dumps({"query": "明天"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{_PORT}/api/chronicle/slices/search",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert body["ok"] is True
        assert len(body["results"]) == 1
    finally:
        server.stop()


def test_ac7_non_loopback_client_is_denied() -> None:
    """AC-7: the Chronicle guard rejects non-loopback peers and accepts local ones."""
    for local in ("127.0.0.1", "::1", "127.0.0.5", "localhost"):
        assert is_loopback_address(local) is True, f"{local} should be loopback"
    for remote in ("192.168.1.50", "10.0.0.7", "172.30.0.1", "8.8.8.8"):
        assert is_loopback_address(remote) is False, f"{remote} should be denied"


def test_chronicle_endpoints_report_unavailable_without_a_store() -> None:
    """With no store wired the endpoints answer 503 rather than crashing."""
    server = _start_server(None)
    try:
        status, body = _get("/api/chronicle/stats")
        assert status == 503
        assert body["ok"] is False
    finally:
        server.stop()
