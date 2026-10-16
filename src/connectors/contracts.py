"""Contracts and data models for Agent Connectors."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum


class AgentEventType(StrEnum):
    """Standardized event types emitted by Agent Connectors."""

    SESSION_START = "session_start"
    USER_PROMPT = "user_prompt"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    TOOL_FAILURE = "tool_failure"
    TASK_COMPLETE = "task_complete"
    SESSION_END = "session_end"
    NEEDS_INPUT = "needs_input"


@dataclass(frozen=True)
class AgentEvent:
    """A normalized event representing an agent's lifecycle or action."""

    agent_id: str
    event_type: AgentEventType
    session_id: str
    timestamp: str
    tool_name: str = ""
    error_message: str = ""

    @classmethod
    def create(
        cls,
        agent_id: str,
        event_type: AgentEventType | str,
        session_id: str = "default",
        tool_name: str = "",
        error_message: str = "",
    ) -> AgentEvent:
        """Create a timestamped agent event."""
        if isinstance(event_type, str):
            event_type = AgentEventType(event_type.lower())
        now_iso = datetime.now(UTC).isoformat()
        return cls(
            agent_id=agent_id,
            event_type=event_type,
            session_id=session_id,
            timestamp=now_iso,
            tool_name=tool_name,
            error_message=error_message,
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
