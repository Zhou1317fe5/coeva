"""Unit tests for CompanionHttpServer."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from src.body.contracts import PetState
from src.connectors.event_bus import LocalEventBus
from src.connectors.http_server import CompanionHttpServer

_app = QApplication.instance() or QApplication([])


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
            assert data["queued"] is True

        # Process Qt event queue so the signal arrives
        time.sleep(0.05)
        QCoreApplication.processEvents()
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
            assert data["queued"] is True

        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert states_received[-1] == PetState.WORKING

    finally:
        server.stop()

def test_agent_filtering_and_settings(tmp_path: Path) -> None:
    from src.connectors.settings import AgentSettingsStore

    settings_file = tmp_path / "agent_settings.json"
    store = AgentSettingsStore(settings_file)

    bus = LocalEventBus()
    states_received: list[PetState] = []
    bus.on_state_suggested = lambda s: states_received.append(s)

    server = CompanionHttpServer(bus, controller=None, settings_store=store, port=17390)
    assert server.start()
    time.sleep(0.1)

    try:
        # 1. GET /api/agents
        req = urllib.request.Request("http://127.0.0.1:17390/api/agents")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            agents = {a["agent_id"]: a for a in data["agents"]}
            assert "hermes" in agents
            assert "pi-desktop" in agents
            assert agents["hermes"]["enabled"] is True

        # 2. Disable hermes via POST /api/agents/update
        update_payload = json.dumps(
            {"agent_id": "hermes", "enabled": False}
        ).encode("utf-8")
        req_up = urllib.request.Request(
            "http://127.0.0.1:17390/api/agents/update",
            data=update_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_up) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["agent"]["enabled"] is False

        # 3. Post event from hermes -> Should be filtered out
        event_payload = json.dumps(
            {"agent_id": "hermes", "event_type": "user_prompt"}
        ).encode("utf-8")
        req_ev = urllib.request.Request(
            "http://127.0.0.1:17390/api/event",
            data=event_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_ev) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data.get("filtered") is True
            assert "disabled" in data.get("reason", "")

        # Verify no state was triggered on the pet
        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert len(states_received) == 0

        # 4. Re-enable hermes
        re_enable = json.dumps(
            {"agent_id": "hermes", "enabled": True}
        ).encode("utf-8")
        req_re = urllib.request.Request(
            "http://127.0.0.1:17390/api/agents/update",
            data=re_enable,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_re) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["agent"]["enabled"] is True

        # 5. Post event from hermes again -> Should be queued
        with urllib.request.urlopen(req_ev) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data.get("queued") is True

        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert len(states_received) == 1
        assert states_received[-1] == PetState.THINKING

    finally:
        server.stop()

def test_multi_environment_instance_isolation(tmp_path: Path) -> None:
    """Test isolating Windows vs WSL instances of the same Agent (e.g. Hermes)."""
    from src.connectors.settings import AgentSettingsStore

    settings_file = tmp_path / "multi_env_settings.json"
    store = AgentSettingsStore(settings_file)

    bus = LocalEventBus()
    states: list[PetState] = []
    bus.on_state_suggested = lambda s: states.append(s)

    server = CompanionHttpServer(bus, controller=None, settings_store=store, port=17391)
    assert server.start()
    time.sleep(0.1)

    try:
        # Check that pi-cli and hermes exist with both windows and wsl instances
        req = urllib.request.Request("http://127.0.0.1:17391/api/agents")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            agents = {a["agent_id"]: a for a in data["agents"]}
            assert "pi-cli" in agents
            assert "hermes" in agents
            assert "windows" in agents["hermes"]["instances"]
            assert "wsl:Ubuntu-24.04" in agents["hermes"]["instances"]

        # 1. Disable only the Windows instance of Hermes, keep WSL instance enabled
        update_inst_payload = json.dumps(
            {"agent_id": "hermes", "instance_id": "windows", "enabled": False}
        ).encode("utf-8")
        req_inst = urllib.request.Request(
            "http://127.0.0.1:17391/api/agents/instance/update",
            data=update_inst_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_inst) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert res["ok"] is True
            assert res["agent"]["instances"]["windows"]["enabled"] is False

        # 2. Send event from Windows Hermes -> Should be filtered
        win_ev = json.dumps(
            {"agent_id": "hermes", "platform": "windows", "event_type": "user_prompt"}
        ).encode("utf-8")
        req_win = urllib.request.Request(
            "http://127.0.0.1:17391/api/event",
            data=win_ev,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_win) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert res["ok"] is True
            assert res.get("filtered") is True

        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert len(states) == 0

        # 3. Send event from WSL Hermes -> Should be queued and processed!
        wsl_ev = json.dumps(
            {
                "agent_id": "hermes",
                "platform": "wsl",
                "distro": "Ubuntu-24.04",
                "event_type": "user_prompt",
            }
        ).encode("utf-8")
        req_wsl = urllib.request.Request(
            "http://127.0.0.1:17391/api/event",
            data=wsl_ev,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_wsl) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert res["ok"] is True
            assert res.get("queued") is True

        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert len(states) == 1
        assert states[-1] == PetState.THINKING

    finally:
        server.stop()

def test_hook_lifecycle_endpoints(tmp_path: Path) -> None:
    """Test one-click install, inspection and uninstall of Agent hooks via HTTP API."""
    from src.connectors.hook_manager import AgentHookManager
    from src.connectors.settings import AgentSettingsStore

    settings_file = tmp_path / "hook_settings.json"
    store = AgentSettingsStore(settings_file)

    # Create mock hook manager targeting isolated temp directory
    hook_mgr = AgentHookManager()
    # Override target resolver to point inside tmp_path
    def _mock_target(aid: str, iid: str) -> Path:
        return tmp_path / "mock_hooks" / aid / iid.replace(":", "_")
    hook_mgr._resolve_target_dir = _mock_target  # type: ignore[method-assign]

    bus = LocalEventBus()
    server = CompanionHttpServer(
        bus, controller=None, settings_store=store, hook_manager=hook_mgr, port=17392
    )
    assert server.start()
    time.sleep(0.1)

    try:
        # 1. Initial status: should be not_installed
        req = urllib.request.Request("http://127.0.0.1:17392/api/agents")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            agents = {a["agent_id"]: a for a in data["agents"]}
            assert agents["hermes"]["instances"]["windows"]["hook_status"] == "not_installed"

        # 2. One-click install hook for hermes on windows
        install_payload = json.dumps(
            {"agent_id": "hermes", "instance_id": "windows"}
        ).encode("utf-8")
        req_in = urllib.request.Request(
            "http://127.0.0.1:17392/api/agents/hook/install",
            data=install_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_in) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert res["ok"] is True

        # 3. Check status again -> should be installed
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            agents = {a["agent_id"]: a for a in data["agents"]}
            assert agents["hermes"]["instances"]["windows"]["hook_status"] == "installed"

        # 4. Uninstall hook
        un_payload = json.dumps(
            {"agent_id": "hermes", "instance_id": "windows"}
        ).encode("utf-8")
        req_un = urllib.request.Request(
            "http://127.0.0.1:17392/api/agents/hook/uninstall",
            data=un_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_un) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert res["ok"] is True

        # 5. Check status again -> back to not_installed
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            agents = {a["agent_id"]: a for a in data["agents"]}
            assert agents["hermes"]["instances"]["windows"]["hook_status"] == "not_installed"

    finally:
        server.stop()

def test_petdex_wire_endpoints_compatibility(tmp_path: Path) -> None:
    """Test compatibility with Petdex wire endpoints: POST /state and POST /bubble."""
    from src.connectors.settings import AgentSettingsStore

    settings_file = tmp_path / "petdex_settings.json"
    store = AgentSettingsStore(settings_file)

    bus = LocalEventBus()
    states: list[PetState] = []
    bus.on_state_suggested = lambda s: states.append(s)

    server = CompanionHttpServer(bus, controller=None, settings_store=store, port=17393)
    assert server.start()
    time.sleep(0.1)

    try:
        # 1. GET /health and /whoami
        req_h = urllib.request.Request("http://127.0.0.1:17393/health")
        with urllib.request.urlopen(req_h) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["status"] == "running"

        req_w = urllib.request.Request("http://127.0.0.1:17393/whoami")
        with urllib.request.urlopen(req_w) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["app"] == "co-evolving-companion"

        # 2. POST /state with Petdex 'running'
        payload_state = json.dumps({"state": "running", "agent": "hermes"}).encode("utf-8")
        req_s = urllib.request.Request(
            "http://127.0.0.1:17393/state",
            data=payload_state,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data.get("petdex") is True

        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert len(states) == 1
        assert states[-1] == PetState.WORKING

        # 3. POST /bubble with Petdex 'bubble' text
        payload_b = json.dumps({"bubble": "来自 Petdex 格式的消息"}).encode("utf-8")
        req_b = urllib.request.Request(
            "http://127.0.0.1:17393/bubble",
            data=payload_b,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_b) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data.get("said") == "来自 Petdex 格式的消息"

    finally:
        server.stop()


def _post_json(port: int, path: str, payload: dict[str, object]) -> dict[str, object]:
    """POST a JSON payload to the test server and return the parsed reply."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]


class _RecordingController:
    """Stand-in BodyController that records what the pet was asked to do."""

    def __init__(self) -> None:
        self.states: list[PetState] = []
        self.said: list[str] = []

    def set_state(self, state: PetState) -> None:
        self.states.append(state)

    def say(self, text: str, *, ttl_ms: int = 4000) -> None:
        self.said.append(text)

    def perform_action(self, action_id: str) -> None:
        pass


def test_agent_events_move_the_pet_but_do_not_print_bubbles(tmp_path: Path) -> None:
    """The desktop must stay a companion, not an agent log viewer.

    End-to-end regression guard for the P0 fix: a full simulated turn (prompt ->
    tool calls -> turn end) animates the pet and speaks nothing.
    """
    from src.connectors.settings import AgentSettingsStore
    from src.core.cold_start import ColdStartPolicy
    from src.core.intervention import InterventionPolicy
    from src.core.sanctuary import SanctuaryGuard
    from src.core.state_watcher import StateWatcher

    store = AgentSettingsStore(tmp_path / "agent_settings.json")
    controller = _RecordingController()
    engine = InterventionPolicy(
        sanctuary=SanctuaryGuard(),
        cold_start=ColdStartPolicy(day_count=30),
        watcher=StateWatcher(),
    )

    bus = LocalEventBus()
    server = CompanionHttpServer(
        bus,
        controller=controller,  # type: ignore[arg-type]
        settings_store=store,
        intervention=engine,
        port=17394,
    )
    assert server.start()
    time.sleep(0.1)

    try:
        _post_json(
            17394,
            "/api/event",
            {"agent_id": "pi-desktop", "event_type": "user_prompt", "message": "🤔 思考中"},
        )
        _post_json(
            17394,
            "/api/event",
            {
                "agent_id": "pi-desktop",
                "event_type": "pre_tool_use",
                "tool_name": "bash",
                "message": "⚙️ 正在执行: bash",
            },
        )
        _post_json(
            17394,
            "/api/event",
            {"agent_id": "pi-desktop", "event_type": "task_complete", "message": "🎉 回合完成！"},
        )

        time.sleep(0.05)
        QCoreApplication.processEvents()

        # The pet still animates through the turn...
        assert controller.states == [PetState.THINKING, PetState.WORKING, PetState.HAPPY]
        # ...but none of that routine telemetry was spoken.
        assert controller.said == []
    finally:
        server.stop()


def test_petdex_idle_does_not_celebrate_and_bubble_is_mutable(tmp_path: Path) -> None:
    """`idle` means the agent went quiet, and a muted agent must not speak."""
    from src.connectors.settings import AgentSettingsStore
    from src.core.cold_start import ColdStartPolicy
    from src.core.intervention import InterventionPolicy
    from src.core.sanctuary import SanctuaryGuard
    from src.core.state_watcher import StateWatcher

    store = AgentSettingsStore(tmp_path / "petdex_settings.json")
    controller = _RecordingController()
    engine = InterventionPolicy(
        sanctuary=SanctuaryGuard(),
        cold_start=ColdStartPolicy(day_count=30),
        watcher=StateWatcher(),
    )

    bus = LocalEventBus()
    server = CompanionHttpServer(
        bus,
        controller=controller,  # type: ignore[arg-type]
        settings_store=store,
        intervention=engine,
        port=17395,
    )
    assert server.start()
    time.sleep(0.1)

    try:
        # Petdex "idle" is not a completed turn: it must not celebrate.
        _post_json(17395, "/state", {"state": "idle", "agent": "hermes"})
        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert controller.states == [PetState.SLEEPING]

        # Muting the agent's bubbles must silence /bubble too.
        store.update_agent("hermes", allow_bubble=False)
        reply = _post_json(17395, "/bubble", {"agent_id": "hermes", "text": "你不该看到这句"})
        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert reply.get("filtered") is True
        assert controller.said == []
    finally:
        server.stop()
