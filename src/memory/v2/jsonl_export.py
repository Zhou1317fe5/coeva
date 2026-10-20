"""Asynchronous One-Way JSONL Exporter for Coeva Memory V2.1.

Part of Stage 4 (WP-11: Dual-Master Elimination).
Canonical Invariants Enforced:
- SQLite raw_slices is the SINGLE authoritative writer (C-06)
- raw_slices.jsonl is non-canonical, one-way export only (C-07, C-11)
- SQLite commit determines write success / durability ACK (C-08, C-09)
- JSONL export failure CANNOT roll back or invalidate SQLite truth (C-09)
- Export identity uses canonical Slice IDs exclusively, NEVER rowid watermarks (C-12)
- Replay / restart is deterministically idempotent without duplicate lines (C-10)
- Readers de-duplicate by canonical slice_id if physical duplicates exist (C-10)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.memory.v2.entities import RawSliceEntity

if TYPE_CHECKING:
    from src.memory.v2.store import ChronicleStoreV2

logger = logging.getLogger(__name__)


class JsonlExportError(RuntimeError):
    """Raised when JSONL export encounters an unrecoverable I/O or serialization error."""

    pass


class ReverseImportForbiddenError(RuntimeError):
    """Raised when an attempt is made to feed JSONL back into canonical V2 SQLite (C-11)."""

    pass


@dataclass(frozen=True)
class ExportResult:
    """Outcome of an export operation."""

    slice_id: str
    exported: bool
    is_duplicate: bool
    export_path: str


class JsonlSliceExporter:
    """Deterministic, idempotent one-way JSONL exporter for canonical V2 raw slices.

    Properties:
    - Non-canonical: never acts as a source of truth for V2.
    - Idempotent: tracks exported slice IDs to prevent duplicate lines.
    - No rowid: relies strictly on canonical slice_id and occurred_at ordering.
    """

    def __init__(
        self,
        export_path: Path | str,
        *,
        auto_load_existing: bool = True,
    ) -> None:
        self.export_path = Path(export_path)
        self._exported_slice_ids: set[str] = set()
        self.last_error: Exception | None = None
        self.failure_count: int = 0
        self.success_count: int = 0

        if auto_load_existing and self.export_path.is_file():
            self._load_existing_ids()

    def _load_existing_ids(self) -> None:
        """Scan existing export file to load known canonical slice IDs for idempotency."""
        if not self.export_path.is_file():
            return
        try:
            with self.export_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        sid = record.get("id") or record.get("slice_id")
                        if sid and isinstance(sid, str):
                            self._exported_slice_ids.add(sid)
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            logger.warning(
                "Failed to scan existing JSONL export file '%s': %s", self.export_path, exc
            )

    def is_exported(self, slice_id: str) -> bool:
        """Return True if slice_id has already been exported."""
        return slice_id in self._exported_slice_ids

    @property
    def exported_count(self) -> int:
        """Return total unique canonical slice IDs exported."""
        return len(self._exported_slice_ids)

    def export_slice(
        self,
        slice_entity: RawSliceEntity,
        *,
        raise_on_error: bool = False,
    ) -> ExportResult:
        """Export a single committed canonical raw slice to the JSONL destination.

        Strict Invariants:
        - If slice was already exported, returns without appending (idempotent).
        - If I/O fails, records error and failure count; never alters SQLite state.
        """
        sid = slice_entity.slice_id
        if sid in self._exported_slice_ids:
            return ExportResult(
                slice_id=sid,
                exported=False,
                is_duplicate=True,
                export_path=str(self.export_path),
            )

        payload = {
            "id": sid,
            "timestamp": slice_entity.occurred_at,
            "actor": slice_entity.actor,
            "source": slice_entity.source,
            "content": slice_entity.content,
            "mood_flag": "neutral",
            "created_at": slice_entity.created_at,
        }

        line = json.dumps(payload, ensure_ascii=False) + "\n"

        try:
            self.export_path.parent.mkdir(parents=True, exist_ok=True)
            with self.export_path.open("a", encoding="utf-8") as f:
                f.write(line)
            self._exported_slice_ids.add(sid)
            self.success_count += 1
            return ExportResult(
                slice_id=sid,
                exported=True,
                is_duplicate=False,
                export_path=str(self.export_path),
            )
        except OSError as exc:
            self.last_error = exc
            self.failure_count += 1
            logger.warning("Failed to append slice '%s' to export file: %s", sid, exc)
            if raise_on_error:
                raise JsonlExportError(f"Export failed for slice '{sid}': {exc}") from exc
            return ExportResult(
                slice_id=sid,
                exported=False,
                is_duplicate=False,
                export_path=str(self.export_path),
            )

    def sync_all(
        self,
        store: ChronicleStoreV2,
        *,
        raise_on_error: bool = False,
    ) -> int:
        """Synchronize all unexported canonical slices from SQLite to JSONL.

        Uses canonical slice_id and occurred_at ordering; strictly NO rowid watermark (C-12).
        """
        cursor = store._conn.cursor()
        cursor.execute(
            "SELECT slice_id, occurred_at, content, actor, source, scope, project_id, "
            "ingestion_dedup_key, created_at FROM raw_slices "
            "ORDER BY occurred_at ASC, slice_id ASC;"
        )
        rows = cursor.fetchall()
        exported_now = 0

        for row in rows:
            sid = str(row[0])
            if sid in self._exported_slice_ids:
                continue

            entity = RawSliceEntity(
                slice_id=sid,
                occurred_at=str(row[1]),
                content=str(row[2]),
                actor=str(row[3]),
                source=str(row[4]),  # type: ignore[arg-type]
                scope=str(row[5]),  # type: ignore[arg-type]
                project_id=str(row[6]) if row[6] is not None else None,
                ingestion_dedup_key=str(row[7]),
                created_at=str(row[8]),
            )
            result = self.export_slice(entity, raise_on_error=raise_on_error)
            if result.exported:
                exported_now += 1

        return exported_now


def read_exported_slices(export_path: Path | str) -> list[dict[str, Any]]:
    """Read exported slices from JSONL, de-duplicating by canonical slice id (C-10).

    Guarantees:
    - Skips malformed or blank lines.
    - If duplicate lines exist physically, only the first occurrence is returned.
    - Non-canonical: reading this file cannot alter canonical V2 SQLite state.
    """
    path = Path(export_path)
    if not path.is_file():
        return []

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            sid = data.get("id") or data.get("slice_id")
            if not sid or sid in seen_ids:
                continue

            seen_ids.add(sid)
            results.append(data)

    return results


def assert_no_reverse_import() -> None:
    """Enforce that JSONL cannot be imported into V2 SQLite (C-11)."""
    raise ReverseImportForbiddenError(
        "Reverse import forbidden: V2 SQLite raw_slices is the single authoritative "
        "writer. raw_slices.jsonl is a one-way non-canonical export."
    )
