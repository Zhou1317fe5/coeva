"""Contracts and data schemas for Slice Feeder."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class RawSlice:
    """A raw input slice submitted by the user."""

    id: str
    timestamp: str
    actor: str
    source: str
    content: str
    mood_flag: str = "neutral"

    @classmethod
    def create(
        cls, content: str, *, mood_flag: str = "neutral", source: str = "manual_feed"
    ) -> RawSlice:
        """Helper to create a new timestamped slice with UUID."""
        now_iso = datetime.now(UTC).isoformat()
        slice_id = f"slice_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        return cls(
            id=slice_id,
            timestamp=now_iso,
            actor="user",
            source=source,
            content=content.strip(),
            mood_flag=mood_flag,
        )

    def to_dict(self) -> dict[str, str]:
        """Convert slice to json-serializable dictionary."""
        return asdict(self)
