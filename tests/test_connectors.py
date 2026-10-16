"""Unit tests for Agent Connectors and LocalEventBus."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


from src.body.contracts import PetState
from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.event_bus import LocalEventBus
from src.connectors.hermes_connector import HermesConnector


def test_agent_event_creation() -> None:
    """Test normalized AgentEvent creation."""
    event = AgentEvent.create(
        "hermes", AgentEventType.PRE_TOOL_USE, session_id="s123", tool_name="smart_search"
    )
    assert event.agent_id == "hermes"
    assert event.event_type == AgentEventType.PRE_TOOL_USE
    assert event.tool_name == "smart_search"
    assert event.session_id == "s123"

    d = event.to_dict()
    assert d["agent_id"] == "hermes"
    assert d["event_type"] == "pre_tool_use"


def test_local_event_bus_dispatch_and_state_mapping() -> None:
    """Test LocalEventBus maps events to appropriate PetState."""
    states_observed: list[PetState] = []
    events_observed: list[AgentEvent] = []

    bus = LocalEventBus(
        on_event_received=lambda e: events_observed.append(e),
        on_state_suggested=lambda s: states_observed.append(s),
    )

    ev_prompt = AgentEvent.create("pi", AgentEventType.USER_PROMPT)
    state = bus.dispatch(ev_prompt)
    assert state == PetState.THINKING
    assert len(events_observed) == 1
    assert states_observed[-1] == PetState.THINKING

    # Test json dispatch
    state_tool = bus.dispatch_json(
        {
            "agent_id": "codex",
            "event_type": "pre_tool_use",
            "tool_name": "bash",
        }
    )
    assert state_tool == PetState.WORKING
    assert states_observed[-1] == PetState.WORKING  # type: ignore[comparison-overlap]


def test_hermes_connector_lifecycle() -> None:
    """Test HermesConnector lifecycle methods drive correct pet states."""
    bus = LocalEventBus()
    connector = HermesConnector(bus)

    # 1. Session start -> Idle
    assert connector.on_session_start("s1") == PetState.IDLE

    # 2. User prompt -> Thinking
    assert connector.on_user_prompt("s1") == PetState.THINKING

    # 3. Pre tool call -> Working
    assert connector.on_pre_tool_call("s1", "grep") == PetState.WORKING

    # 4. Tool fail -> Error
    assert connector.on_tool_failure("s1", "grep", "file not found") == PetState.ERROR

    # 5. Task complete -> Happy
    assert connector.on_task_complete("s1") == PetState.HAPPY

    # 6. Session end -> Sleeping
    assert connector.on_session_end("s1") == PetState.SLEEPING

    assert len(bus.history) == 6

def test_agent_settings_pet_preference(tmp_path: Path) -> None:
    """Test that selected desktop pet preference defaults to tiko and persists correctly."""
    from src.connectors.settings import AgentSettingsStore

    settings_file = tmp_path / "agent_settings.json"
    store = AgentSettingsStore(settings_file)
    assert store.selected_pet == "tiko"

    store.set_selected_pet("debug-duck")
    assert store.selected_pet == "debug-duck"

    # Reload from disk
    reloaded = AgentSettingsStore(settings_file)
    assert reloaded.selected_pet == "debug-duck"

    reloaded.set_selected_pet("wangcai")
    assert reloaded.selected_pet == "wangcai"


def _persisted_hotkey(settings_file: Path) -> object:
    """Read the hotkey straight off disk, bypassing the in-memory store."""
    return json.loads(settings_file.read_text(encoding="utf-8"))["feeder_hotkey"]


def test_feeder_hotkey_defaults_persists_and_rejects_illegal(tmp_path: Path) -> None:
    """The feeder hotkey round-trips canonically and never persists a bad value."""
    from src.connectors.settings import AgentSettingsStore
    from src.feeder.hotkey import DEFAULT_FEEDER_HOTKEY

    settings_file = tmp_path / "agent_settings.json"
    store = AgentSettingsStore(settings_file)
    assert store.feeder_hotkey == DEFAULT_FEEDER_HOTKEY

    # A friendly spelling is normalised on the way to disk.
    store.set_feeder_hotkey("Ctrl+Alt+F")
    assert store.feeder_hotkey == "<ctrl>+<alt>+f"
    assert _persisted_hotkey(settings_file) == "<ctrl>+<alt>+f"
    assert AgentSettingsStore(settings_file).feeder_hotkey == "<ctrl>+<alt>+f"

    # Illegal input raises and leaves both memory and disk untouched.
    with pytest.raises(ValueError):
        store.set_feeder_hotkey("f")
    assert store.feeder_hotkey == "<ctrl>+<alt>+f"
    assert _persisted_hotkey(settings_file) == "<ctrl>+<alt>+f"


def test_feeder_hotkey_falls_back_when_stored_value_is_invalid(tmp_path: Path) -> None:
    """A hand-edited or missing value degrades to the default instead of crashing."""
    from src.connectors.settings import AgentSettingsStore
    from src.feeder.hotkey import DEFAULT_FEEDER_HOTKEY

    settings_file = tmp_path / "agent_settings.json"
    settings_file.write_text(
        json.dumps({"version": 2, "selected_pet": "tiko", "feeder_hotkey": "f", "agents": {}}),
        encoding="utf-8",
    )
    assert AgentSettingsStore(settings_file).feeder_hotkey == DEFAULT_FEEDER_HOTKEY

    settings_file.write_text(
        json.dumps({"version": 2, "selected_pet": "tiko", "agents": {}}), encoding="utf-8"
    )
    assert AgentSettingsStore(settings_file).feeder_hotkey == DEFAULT_FEEDER_HOTKEY

def test_codex_hook_lifecycle(tmp_path: Path) -> None:
    """Test one-click installation, status check and clean uninstall of Codex CLI hook."""
    from src.connectors.hook_manager import AgentHookManager

    mgr = AgentHookManager()
    target_dir = tmp_path / ".codex" / "companion-bridge"
    mgr._resolve_target_dir = lambda aid, iid: target_dir  # type: ignore[method-assign,assignment]

    # 1. Initially not installed
    status = mgr.check_hook_status("codex", "windows")
    assert status["installed"] is False

    # 2. Install
    res = mgr.install_hook("codex", "windows")
    assert res["ok"] is True
    assert (target_dir / "codex_hook.py").is_file()
    hooks_file = tmp_path / ".codex" / "hooks.json"
    assert hooks_file.is_file()
    assert "companion-bridge" in hooks_file.read_text(encoding="utf-8")

    # 3. Status check -> installed
    status_after = mgr.check_hook_status("codex", "windows")
    assert status_after["installed"] is True

    # 4. Uninstall
    un_res = mgr.uninstall_hook("codex", "windows")
    assert un_res["ok"] is True
    assert not (target_dir / "codex_hook.py").exists()
    assert "companion-bridge" not in hooks_file.read_text(encoding="utf-8")

    # 5. Status check -> not installed
    status_final = mgr.check_hook_status("codex", "windows")
    assert status_final["installed"] is False


def test_claude_code_hook_lifecycle(tmp_path: Path) -> None:
    """Test one-click installation, status check and clean uninstall of Claude Code hook."""
    from src.connectors.hook_manager import AgentHookManager

    mgr = AgentHookManager()
    target_dir = tmp_path / ".claude" / "companion-bridge"
    mgr._resolve_target_dir = lambda aid, iid: target_dir  # type: ignore[method-assign,assignment]

    # 1. Initially not installed
    status = mgr.check_hook_status("claude-code", "windows")
    assert status["installed"] is False

    # 2. Install
    res = mgr.install_hook("claude-code", "windows")
    assert res["ok"] is True
    assert (target_dir / "claude_hook.py").is_file()
    settings_file = tmp_path / ".claude" / "settings.json"
    assert settings_file.is_file()
    assert "companion-bridge" in settings_file.read_text(encoding="utf-8")

    # 3. Status check -> installed
    status_after = mgr.check_hook_status("claude-code", "windows")
    assert status_after["installed"] is True

    # 4. Uninstall
    un_res = mgr.uninstall_hook("claude-code", "windows")
    assert un_res["ok"] is True
    assert not (target_dir / "claude_hook.py").exists()
    assert "companion-bridge" not in settings_file.read_text(encoding="utf-8")

    # 5. Status check -> not installed
    status_final = mgr.check_hook_status("claude-code", "windows")
    assert status_final["installed"] is False

