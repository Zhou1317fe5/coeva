"""Unit tests for Agent Connectors and LocalEventBus."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    assert states_observed[-1] == PetState.WORKING


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
