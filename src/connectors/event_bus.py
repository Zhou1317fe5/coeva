"""Local event bus dispatching agent events to the Growth Core and Pet Body."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.body.contracts import PetState
from src.connectors.contracts import AgentEvent, AgentEventType

if TYPE_CHECKING:
    from src.memory.store import ChronicleStore
_EVENT_TO_STATE: dict[AgentEventType, PetState] = {
    AgentEventType.SESSION_START: PetState.IDLE,
    AgentEventType.USER_PROMPT: PetState.THINKING,
    AgentEventType.PRE_TOOL_USE: PetState.WORKING,
    AgentEventType.POST_TOOL_USE: PetState.WORKING,
    AgentEventType.TOOL_FAILURE: PetState.ERROR,
    AgentEventType.TASK_COMPLETE: PetState.HAPPY,
    AgentEventType.SESSION_END: PetState.SLEEPING,
}


class LocalEventBus:
    """In-process and IPC event dispatcher connecting agents with Growth Core."""

    def __init__(
        self,
        on_event_received: Callable[[AgentEvent], None] | None = None,
        on_state_suggested: Callable[[PetState], None] | None = None,
        store: ChronicleStore | None = None,
    ) -> None:
        self.on_event_received = on_event_received
        self.on_state_suggested = on_state_suggested
        # Optional Chronicle sink; the bus stays usable without one (Phase 1 tests).
        self.store = store
        self._history: list[AgentEvent] = []

    @property
    def history(self) -> list[AgentEvent]:
        return list(self._history)

    def dispatch(self, event: AgentEvent) -> PetState:
        """Process an agent event, notify observers, and derive the corresponding pet state."""
        self._history.append(event)

        # Data plane: persist before notifying observers, so evidence survives a UI callback error.
        if self.store is not None:
            self.store.record_event(event)

        if self.on_event_received is not None:
            self.on_event_received(event)

        suggested_state = _EVENT_TO_STATE.get(event.event_type, PetState.IDLE)
        if self.on_state_suggested is not None:
            self.on_state_suggested(suggested_state)

        return suggested_state

    def dispatch_json(self, raw_json: str | dict[str, Any]) -> PetState:
        """Parse raw json dictionary and dispatch."""
        if isinstance(raw_json, str):
            data = json.loads(raw_json)
        else:
            data = raw_json

        event = AgentEvent.create(
            agent_id=data.get("agent_id", "unknown"),
            event_type=data.get("event_type", "user_prompt"),
            session_id=data.get("session_id", "default"),
            tool_name=data.get("tool_name", ""),
            error_message=data.get("error_message", ""),
        )
        return self.dispatch(event)
