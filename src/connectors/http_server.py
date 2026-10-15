"""Lightweight local HTTP server for receiving real-time agent events."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.body.controller import BodyController
    from src.connectors.event_bus import LocalEventBus

DEFAULT_PORT = 17321
DEFAULT_HOST = "127.0.0.1"


class _CompanionHandler(BaseHTTPRequestHandler):
    """HTTP Request handler for Companion API."""

    bus: LocalEventBus
    controller: BodyController | None

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Silence standard console output to avoid polluting user terminal
        pass

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/status":
            self._send_json(200, {"ok": True, "status": "running"})
        else:
            self._send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        length_header = self.headers.get("Content-Length")
        if not length_header:
            self._send_json(400, {"ok": False, "error": "Missing Content-Length"})
            return

        try:
            length = int(length_header)
            body_bytes = self.rfile.read(length)
            data = json.loads(body_bytes.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as e:
            self._send_json(400, {"ok": False, "error": f"Invalid JSON: {e}"})
            return

        if self.path == "/api/event":
            # Event dispatch
            suggested_state = self.bus.dispatch_json(data)

            # Bubble message support
            msg = data.get("message")
            if msg and self.controller is not None:
                ttl_ms = int(data.get("ttl_ms", 3000))
                self.controller.say(str(msg), ttl_ms=ttl_ms)

            self._send_json(200, {"ok": True, "state": str(suggested_state)})

        elif self.path == "/api/say":
            text = str(data.get("text", "")).strip()
            ttl_ms = int(data.get("ttl_ms", 4000))
            if text and self.controller is not None:
                self.controller.say(text, ttl_ms=ttl_ms)
                self._send_json(200, {"ok": True, "said": text})
            else:
                self._send_json(400, {"ok": False, "error": "Empty text"})

        elif self.path == "/api/action":
            action_id = str(data.get("animationId") or data.get("action", "idle"))
            if self.controller is not None:
                self.controller.perform_action(action_id)
                self._send_json(200, {"ok": True, "action": action_id})
            else:
                self._send_json(500, {"ok": False, "error": "Controller unavailable"})

        else:
            self._send_json(404, {"ok": False, "error": "Unknown endpoint"})


class CompanionHttpServer:
    """Runs the background HTTP server for external Agent connectors."""

    def __init__(
        self,
        bus: LocalEventBus,
        controller: BodyController | None = None,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.bus = bus
        self.controller = controller
        self.host = host
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Start listening on the background thread."""
        handler_class = type(
            "BoundCompanionHandler",
            (_CompanionHandler,),
            {"bus": self.bus, "controller": self.controller},
        )
        try:
            self._server = HTTPServer((self.host, self.port), handler_class)
        except OSError:
            return False

        def _serve() -> None:
            if self._server:
                self._server.serve_forever()

        self._thread = threading.Thread(target=_serve, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
