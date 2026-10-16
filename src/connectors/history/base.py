"""Base parser interface and contracts for historical session harvesting."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.connectors.contracts import AgentEvent


def normalize_timestamp(val: str | float | int) -> str:
    """Convert various timestamp formats (epoch float/int or ISO string) to standardized ISO."""
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=UTC).isoformat()
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return datetime.now(UTC).isoformat()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        try:
            # Validate ISO format
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.isoformat()
        except ValueError:
            return datetime.now(UTC).isoformat()
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class HarvestedSession:
    """Normalized representation of a single harvested multi-agent session."""

    session_id: str
    agent_id: str
    started_at: str
    ended_at: str
    events: tuple[AgentEvent, ...]


class BaseSessionParser(ABC):
    """Abstract base parser for extracting normalized AgentEvents from agent session logs."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier of the agent source (e.g., 'pi-desktop', 'codex', 'hermes')."""

    @abstractmethod
    def discover_targets(self) -> list[Path]:
        """Discover available session log files or database paths on the local system."""

    @abstractmethod
    def parse_session(self, target: Path | str) -> HarvestedSession | None:
        """Parse a single session log or database into a normalized HarvestedSession."""
