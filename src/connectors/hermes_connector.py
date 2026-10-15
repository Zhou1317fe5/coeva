"""Hermes Agent Connector translating Hermes lifecycle events."""

from __future__ import annotations

from src.body.contracts import PetState
from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.event_bus import LocalEventBus


class HermesConnector:
    """Connector bridging Hermes Agent events into the Companion system."""

    def __init__(self, bus: LocalEventBus) -> None:
        self.bus = bus

    def on_session_start(self, session_id: str) -> PetState:
        event = AgentEvent.create("hermes", AgentEventType.SESSION_START, session_id=session_id)
        return self.bus.dispatch(event)

    def on_user_prompt(self, session_id: str) -> PetState:
        event = AgentEvent.create("hermes", AgentEventType.USER_PROMPT, session_id=session_id)
        return self.bus.dispatch(event)

    def on_pre_tool_call(self, session_id: str, tool_name: str) -> PetState:
        event = AgentEvent.create(
            "hermes", AgentEventType.PRE_TOOL_USE, session_id=session_id, tool_name=tool_name
        )
        return self.bus.dispatch(event)

    def on_tool_failure(self, session_id: str, tool_name: str, error: str) -> PetState:
        event = AgentEvent.create(
            "hermes",
            AgentEventType.TOOL_FAILURE,
            session_id=session_id,
            tool_name=tool_name,
            error_message=error,
        )
        return self.bus.dispatch(event)

    def on_task_complete(self, session_id: str) -> PetState:
        event = AgentEvent.create("hermes", AgentEventType.TASK_COMPLETE, session_id=session_id)
        return self.bus.dispatch(event)

    def on_session_end(self, session_id: str) -> PetState:
        event = AgentEvent.create("hermes", AgentEventType.SESSION_END, session_id=session_id)
        return self.bus.dispatch(event)
