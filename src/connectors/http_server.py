"""Lightweight local HTTP server for receiving real-time agent events via Qt Signal bridge."""

from __future__ import annotations

import ipaddress
import json
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, Signal

from src.connectors.hook_manager import AgentHookManager
from src.connectors.settings import AgentSettingsStore

if TYPE_CHECKING:
    from src.body.controller import BodyController
    from src.connectors.event_bus import LocalEventBus
    from src.core.intervention import InterventionPolicy
    from src.memory.store import ChronicleStore


def _int_param(params: dict[str, str], key: str, default: int) -> int:
    """Parse an integer query parameter, falling back to a default when unusable."""
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return default


def is_loopback_address(host: str) -> bool:
    """True when `host` is a loopback address or the literal `localhost`."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


DEFAULT_PORT = 17321
DEFAULT_HOST = "0.0.0.0"


class _QtHttpBridge(QObject):
    """Bridge routing HTTP requests safely onto Qt's main GUI event loop."""

    event_received = Signal(dict)
    say_received = Signal(str, int)
    action_received = Signal(str)


class _CompanionHandler(BaseHTTPRequestHandler):
    """HTTP Request handler for Companion API."""

    bridge: _QtHttpBridge
    bus: LocalEventBus
    controller: BodyController | None
    settings_store: AgentSettingsStore
    hook_manager: AgentHookManager
    store: ChronicleStore | None
    timeout: ClassVar[float | None] = 5.0

    def _agent_may_speak(self, agent_id: str, platform: str | None, distro: str | None) -> bool:
        """True when this agent instance is enabled and allowed to show bubbles.

        Shared by /state and /bubble so both honour the same switches the
        /api/event path and the settings panel expose.
        """
        instance_id = "windows"
        if platform == "wsl":
            instance_id = f"wsl:{distro}" if distro else "wsl"
        return self.settings_store.is_agent_enabled(
            agent_id, instance_id=instance_id
        ) and self.settings_store.can_show_bubble(agent_id)

    def _is_loopback_client(self) -> bool:
        """True when the request came from this machine (SPEC section 7.2)."""
        return is_loopback_address(self.client_address[0])

    def _query(self) -> dict[str, str]:
        """First value of each query parameter, or an empty mapping."""
        parsed = urlparse(self.path)
        return {k: v[0] for k, v in parse_qs(parsed.query).items() if v}

    def _send_loopback_denied(self) -> None:
        self._send_json(
            403,
            {"ok": False, "error": "Chronicle endpoints are restricted to loopback clients"},
        )

    def _handle_chronicle_get(self) -> None:
        """Read-only Chronicle queries, loopback-only (SPEC section 7.2)."""
        if self.store is None:
            self._send_json(503, {"ok": False, "error": "Chronicle store unavailable"})
            return
        if not self._is_loopback_client():
            self._send_loopback_denied()
            return

        route = urlparse(self.path).path
        params = self._query()
        limit = _int_param(params, "limit", 20)
        offset = _int_param(params, "offset", 0)

        if route == "/api/chronicle/stats":
            self._send_json(200, {"ok": True, **self.store.stats()})
        elif route == "/api/chronicle/slices":
            slices = self.store.list_slices(limit=limit, offset=offset, mood=params.get("mood"))
            self._send_json(200, {"ok": True, "slices": [asdict(s) for s in slices]})
        elif route == "/api/chronicle/evidence":
            rows = self.store.list_evidence(
                limit=limit, offset=offset, provenance=params.get("provenance")
            )
            self._send_json(200, {"ok": True, "evidence": rows})
        elif route == "/api/chronicle/episodes":
            episodes = [asdict(e) for e in self.store.list_episodes(limit=limit)]
            self._send_json(200, {"ok": True, "episodes": episodes})
        else:
            self._send_json(404, {"ok": False, "error": "Not found"})

    def _handle_chronicle_search(self, data: dict[str, Any]) -> None:
        """Keyword search over slices, loopback-only."""
        if self.store is None:
            self._send_json(503, {"ok": False, "error": "Chronicle store unavailable"})
            return
        if not self._is_loopback_client():
            self._send_loopback_denied()
            return
        query = str(data.get("query", "")).strip()
        if not query:
            self._send_json(400, {"ok": False, "error": "Missing query"})
            return
        limit = int(data.get("limit", 20))
        matches = self.store.search_slices(query, limit=limit)
        self._send_json(200, {"ok": True, "results": [asdict(m) for m in matches]})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Silence console log pollution
        pass

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/api/status", "/health"):
            self._send_json(200, {"ok": True, "status": "running"})
        elif self.path == "/whoami":
            self._send_json(200, {"ok": True, "app": "co-evolving-companion", "version": "0.1.0"})
        elif self.path == "/api/agents":
            agents = []
            for cfg in self.settings_store.get_all():
                d = cfg.to_dict()
                for iid, idata in d.get("instances", {}).items():
                    h_res = self.hook_manager.check_hook_status(cfg.agent_id, iid)
                    idata["hook_status"] = h_res.get("status", "not_installed")
                agents.append(d)
            self._send_json(200, {"ok": True, "agents": agents})
        elif urlparse(self.path).path.startswith("/api/chronicle/"):
            self._handle_chronicle_get()
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
            agent_id = str(data.get("agent_id", "default")).strip()
            platform = str(data.get("platform", "")).strip().lower() or None
            distro = str(data.get("distro", "")).strip() or None
            instance_id = "windows"
            if platform == "wsl":
                instance_id = f"wsl:{distro}" if distro else "wsl"

            self.settings_store.record_heartbeat(agent_id, platform=platform, distro=distro)
            if not self.settings_store.is_agent_enabled(agent_id, instance_id=instance_id):
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "filtered": True,
                        "reason": f"Agent '{agent_id}' ({instance_id}) is disabled",
                    },
                )
                return
            data["_allow_bubble"] = self.settings_store.can_show_bubble(agent_id)
            data["_allow_action"] = self.settings_store.can_perform_action(agent_id)
            # Emit across thread boundary to Qt main GUI thread
            self.bridge.event_received.emit(data)
            self._send_json(200, {"ok": True, "queued": True})
        elif self.path == "/api/agents/update":
            aid = str(data.get("agent_id", "")).strip()
            if not aid:
                self._send_json(400, {"ok": False, "error": "Missing agent_id"})
                return
            self.settings_store.update_agent(
                aid,
                enabled=data.get("enabled"),
                allow_bubble=data.get("allow_bubble"),
                allow_action=data.get("allow_action"),
            )
            updated = self.settings_store.get(aid)
            self._send_json(200, {"ok": True, "agent": updated.to_dict() if updated else {}})

        elif self.path == "/api/agents/instance/update":
            aid = str(data.get("agent_id", "")).strip()
            iid = str(data.get("instance_id", "")).strip()
            if not aid or not iid:
                self._send_json(400, {"ok": False, "error": "Missing agent_id or instance_id"})
                return
            self.settings_store.update_instance(
                aid,
                iid,
                enabled=data.get("enabled"),
            )
            updated = self.settings_store.get(aid)
            self._send_json(200, {"ok": True, "agent": updated.to_dict() if updated else {}})

        elif self.path == "/api/agents/hook/install":
            aid = str(data.get("agent_id", "")).strip()
            iid = str(data.get("instance_id", "")).strip()
            res = self.hook_manager.install_hook(aid, iid)
            self._send_json(200 if res.get("ok") else 400, res)

        elif self.path == "/api/agents/hook/uninstall":
            aid = str(data.get("agent_id", "")).strip()
            iid = str(data.get("instance_id", "")).strip()
            res = self.hook_manager.uninstall_hook(aid, iid)
            self._send_json(200 if res.get("ok") else 400, res)
        elif self.path == "/api/say":
            text = str(data.get("text", "")).strip()
            ttl_ms = int(data.get("ttl_ms", 4000))
            if text:
                self.bridge.say_received.emit(text, ttl_ms)
                self._send_json(200, {"ok": True, "said": text})
            else:
                self._send_json(400, {"ok": False, "error": "Empty text"})

        elif self.path == "/api/action":
            action_id = str(data.get("animationId") or data.get("action", "idle"))
            self.bridge.action_received.emit(action_id)
            self._send_json(200, {"ok": True, "action": action_id})

        elif self.path == "/api/chronicle/slices/search":
            self._handle_chronicle_search(data)
        # ── Petdex Compatible Endpoints ──
        elif self.path == "/state":
            # Map Petdex wire state (running, idle, needs_input, completed, failed).
            # `idle` means the agent went quiet, not that a turn succeeded: mapping
            # it to task_complete made the pet celebrate whenever an agent paused.
            raw_state = str(data.get("state", "idle")).strip().lower()
            aid = str(data.get("agent_id") or data.get("agent", "hermes")).strip()
            platform = str(data.get("platform", "")).strip().lower() or None
            distro = str(data.get("distro", "")).strip() or None

            # An unrecognised or absent state must not claim user attribution:
            # `user_prompt` is the one durable, user-owned event type, so defaulting
            # to it would let agent telemetry masquerade as a user action.
            if raw_state == "completed":
                event_type = "task_complete"
            elif raw_state == "idle":
                event_type = "session_end"  # went quiet: rest, do not celebrate
            elif raw_state == "failed":
                event_type = "tool_failure"
            elif raw_state == "needs_input":
                event_type = "needs_input"
            else:
                event_type = "pre_tool_use"  # running and anything unknown

            self.settings_store.record_heartbeat(aid, platform=platform, distro=distro)
            if not self._agent_may_speak(aid, platform, distro):
                payload = {"ok": True, "state": raw_state, "petdex": True, "filtered": True}
                self._send_json(200, payload)
                return

            transformed = {
                "agent_id": aid,
                "event_type": event_type,
                "platform": platform,
                "distro": distro,
                "message": data.get("message"),
                "_allow_bubble": self.settings_store.can_show_bubble(aid),
                "_allow_action": self.settings_store.can_perform_action(aid),
            }
            self.bridge.event_received.emit(transformed)
            self._send_json(200, {"ok": True, "state": raw_state, "petdex": True})

        elif self.path == "/bubble":
            # Map Petdex bubble post. Gated exactly like /api/event, otherwise a
            # user who switched an agent's bubble off would still be interrupted.
            aid = str(data.get("agent_id") or data.get("agent", "hermes")).strip()
            text = str(data.get("text") or data.get("bubble", "")).strip()
            ttl_ms = int(data.get("ttl_ms", 3500))
            if not text:
                self._send_json(400, {"ok": False, "error": "Empty bubble text"})
                return

            platform = str(data.get("platform", "")).strip().lower() or None
            distro = str(data.get("distro", "")).strip() or None
            self.settings_store.record_heartbeat(aid, platform=platform, distro=distro)
            if not self._agent_may_speak(aid, platform, distro):
                payload = {"ok": True, "filtered": True, "reason": f"Agent '{aid}' is muted"}
                self._send_json(200, payload)
                return

            self.bridge.say_received.emit(text, ttl_ms)
            self._send_json(200, {"ok": True, "said": text, "petdex": True})
        else:
            self._send_json(404, {"ok": False, "error": "Unknown endpoint"})


class CompanionHttpServer:
    """Runs the background HTTP server for external Agent connectors."""

    def __init__(
        self,
        bus: LocalEventBus,
        controller: BodyController | None = None,
        settings_store: AgentSettingsStore | None = None,
        hook_manager: AgentHookManager | None = None,
        *,
        store: ChronicleStore | None = None,
        intervention: InterventionPolicy | None = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.bus = bus
        self.controller = controller
        self.settings_store = settings_store or AgentSettingsStore()
        self.hook_manager = hook_manager or AgentHookManager()
        self.store = store
        self.intervention = intervention
        self.host = host
        self.port = port
        self.bridge = _QtHttpBridge()

        # Connect bridge signals to handlers executing on the Qt main thread
        self.bridge.event_received.connect(self._handle_event_on_main_thread)
        if self.controller is not None:
            self.bridge.say_received.connect(self.controller.say)
            self.bridge.action_received.connect(self.controller.perform_action)

        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _handle_event_on_main_thread(self, data: dict[str, Any]) -> None:
        """Executed safely on the Qt GUI main loop.

        Data Plane & Control Plane separation (AGENTS.md section 4):
        Agent telemetry (tool calls, prompt turns, session changes, tool failures)
        is purely read-only background evidence. It is dispatched to the event bus
        and persisted into Chronicle for growth chapters, but it STRICTLY NEVER
        drives or overrides the pet's body posture or speech bubble directly.
        The companion's voice belongs only to the companion itself, never mirroring
        raw terminal errors like '⚠️ 工具报错: Bash'.
        """
        self.bus.dispatch_json(data)
    def start(self) -> bool:
        """Start listening on the background thread."""
        handler_class = type(
            "BoundCompanionHandler",
            (_CompanionHandler,),
            {
                "bridge": self.bridge,
                "bus": self.bus,
                "controller": self.controller,
                "settings_store": self.settings_store,
                "hook_manager": self.hook_manager,
                "store": self.store,
            },
        )
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), handler_class)
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
