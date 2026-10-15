"""Storage manager for persisting raw slices to disk."""

from __future__ import annotations

import json
from pathlib import Path

from src.feeder.contracts import RawSlice


class SliceStore:
    """Manages the append-only raw slice stream on disk."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or (Path("data") / "raw_slices.jsonl")

    def save(self, raw_slice: RawSlice) -> None:
        """Append a slice to the jsonl storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(raw_slice.to_dict(), ensure_ascii=False) + "\n"
        with self.storage_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def load_recent(self, limit: int = 50) -> list[RawSlice]:
        """Load the most recent slices from disk."""
        if not self.storage_path.is_file():
            return []

        slices: list[RawSlice] = []
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            slices.append(
                                RawSlice(
                                    id=data["id"],
                                    timestamp=data["timestamp"],
                                    actor=data.get("actor", "user"),
                                    source=data.get("source", "manual_feed"),
                                    content=data["content"],
                                    mood_flag=data.get("mood_flag", "neutral"),
                                )
                            )
                        except (json.JSONDecodeError, KeyError):
                            continue
        except OSError:
            return []

        return slices[-limit:]

    def count(self) -> int:
        """Count total stored slices."""
        if not self.storage_path.is_file():
            return 0
        total = 0
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        total += 1
        except OSError:
            return 0
        return total
