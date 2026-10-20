"""Option D Canonical ID Set Difference Reconciliation Engine.

Enforces:
- M-S01: Snapshot-to-cutover live Slice preserved.
- M-S02: Snapshot-to-cutover live Event preserved.
- M-S03: Final canonical source-set parity verified (no watermark).
- M-S04: No duplicate row introduced by delta replay.
- M-S13: Delete max ROWID then insert new Slice — new Slice not lost.
- M-S14: Delete max ROWID then insert new Event — new Event not lost.
- M-S15: Replay same canonical ID with identical payload is idempotent NOOP.
- M-S16: Replay same canonical ID with conflicting payload fails closed.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.memory.v2.migration.mapper import sanitize_error_category


class ReconciliationError(Exception):
    """Base error for reconciliation failures."""

    pass


class MigrationConflictError(ReconciliationError):
    """Raised when same canonical ID has differing payloads (M-S16 fail closed)."""

    def __init__(
        self,
        entity_type: str,
        canonical_id: str,
        source_summary: str,
        shadow_summary: str,
    ) -> None:
        msg = (
            f"MIGRATION CONFLICT on {entity_type} ID '{canonical_id}': "
            f"source payload ({source_summary}) does not match shadow payload ({shadow_summary}). "
            f"FAIL CLOSED: cutover forbidden."
        )
        super().__init__(msg)
        self.entity_type = entity_type
        self.canonical_id = canonical_id
        self.source_summary = source_summary
        self.shadow_summary = shadow_summary


@dataclass(frozen=True)
class ReconciliationReport:
    """Detailed summary of canonical ID reconciliation and parity check."""

    slices_inserted: int
    slices_noop: int
    slices_deleted: int
    events_inserted: int
    events_noop: int
    events_deleted: int
    final_slices_count: int
    final_events_count: int
    parity_verified: bool
    status_message: str


def reconcile_canonical_sets(
    source_db_path: Path,
    shadow_db_path: Path,
) -> ReconciliationReport:
    """Reconcile source DB and shadow DB using Canonical ID Set Difference.

    NEVER relies on SQLite rowid as watermark or sequence (M-S13, M-S14).
    Uses canonical primary keys:
    - Slice: canonical `id` vs `slice_id`
    - Event: canonical `id` vs `event_id`

    Raises:
        MigrationConflictError: If same canonical ID has conflicting payloads (M-S16).
        ReconciliationError: If parity cannot be established.
    """
    if not source_db_path.is_file():
        raise ReconciliationError(f"Source database not found: {source_db_path}")
    if not shadow_db_path.is_file():
        raise ReconciliationError(f"Shadow database not found: {shadow_db_path}")

    src_uri = f"file:{os.path.abspath(source_db_path)}?mode=ro"
    src_conn = sqlite3.connect(src_uri, uri=True)
    src_conn.row_factory = sqlite3.Row

    shadow_conn = sqlite3.connect(str(shadow_db_path))
    shadow_conn.row_factory = sqlite3.Row

    try:
        # =====================================================================
        # 1. Reconcile Slices (Canonical slice ID)
        # =====================================================================
        src_cur = src_conn.cursor()
        src_cur.execute("PRAGMA table_info(slices);")
        slice_cols = {r[1] for r in src_cur.fetchall()}
        actor_col = "actor" if "actor" in slice_cols else "'user' AS actor"
        source_col = "source" if "source" in slice_cols else "'manual_feed' AS source"
        created_col = "created_at" if "created_at" in slice_cols else "timestamp AS created_at"
        src_cur.execute(
            f"SELECT id, timestamp, content, {actor_col}, {source_col}, {created_col} FROM slices"
        )
        # Map: id -> (timestamp, content, actor, source, created_at)
        src_slices: dict[str, tuple[str, str, str, str, str]] = {}
        for r in src_cur:
            s_id = str(r["id"])
            ts = str(r["timestamp"])
            content = str(r["content"])
            actor = str(r["actor"]) if r["actor"] else "user"
            source = str(r["source"]) if r["source"] else "manual_feed"
            created_at = str(r["created_at"]) if r["created_at"] else ts
            src_slices[s_id] = (ts, content, actor, source, created_at)

        shadow_cur = shadow_conn.cursor()
        shadow_cur.execute(
            "SELECT slice_id, occurred_at, content, actor, source, created_at FROM raw_slices"
        )
        shadow_slices: dict[str, tuple[str, str, str, str, str]] = {}
        for r in shadow_cur:
            s_id = str(r["slice_id"])
            ts = str(r["occurred_at"])
            content = str(r["content"])
            actor = str(r["actor"])
            source = str(r["source"])
            created_at = str(r["created_at"])
            shadow_slices[s_id] = (ts, content, actor, source, created_at)

        src_slice_ids = set(src_slices.keys())
        shadow_slice_ids = set(shadow_slices.keys())

        slices_to_insert = src_slice_ids - shadow_slice_ids
        slices_to_delete = shadow_slice_ids - src_slice_ids
        slices_common = src_slice_ids & shadow_slice_ids

        # Check for conflicts on common canonical slice IDs (M-S15 / M-S16)
        slices_noop_count = 0
        for s_id in slices_common:
            src_item = src_slices[s_id]
            shw_item = shadow_slices[s_id]
            # Content must match exactly byte-for-byte (M-S11, M-S16)
            if (
                src_item[1] != shw_item[1]
                or src_item[2] != shw_item[2]
                or src_item[3] != shw_item[3]
            ):
                raise MigrationConflictError(
                    entity_type="Slice",
                    canonical_id=s_id,
                    source_summary=f"content='{src_item[1][:30]}...', actor='{src_item[2]}'",
                    shadow_summary=f"content='{shw_item[1][:30]}...', actor='{shw_item[2]}'",
                )
            slices_noop_count += 1

        # Apply slice insertions
        slice_insert_rows = []
        for s_id in slices_to_insert:
            item = src_slices[s_id]
            dedup_key = f"legacy_slice_{s_id}"
            slice_insert_rows.append(
                (
                    s_id,
                    item[0],
                    item[1],
                    item[2],
                    item[3],
                    "unresolved",
                    None,
                    dedup_key,
                    item[4],
                )
            )

        if slice_insert_rows:
            shadow_conn.executemany(
                """
                INSERT INTO raw_slices (
                    slice_id, occurred_at, content, actor, source,
                    scope, project_id, ingestion_dedup_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                slice_insert_rows,
            )

        # Apply slice deletions (if records were removed from source before cutover)
        if slices_to_delete:
            shadow_conn.executemany(
                "DELETE FROM raw_slices WHERE slice_id = ?;",
                [(s_id,) for s_id in slices_to_delete],
            )

        shadow_conn.commit()

        # =====================================================================
        # 2. Reconcile Events (Canonical event ID)
        # =====================================================================
        src_cur.execute("PRAGMA table_info(events);")
        event_cols = {r[1] for r in src_cur.fetchall()}
        agent_col = "agent_id" if "agent_id" in event_cols else "'pi-desktop' AS agent_id"
        session_col = "session_id" if "session_id" in event_cols else "'default' AS session_id"
        tool_col = "tool_name" if "tool_name" in event_cols else "'' AS tool_name"
        err_col = "error_message" if "error_message" in event_cols else "'' AS error_message"
        ret_col = (
            "retention_class"
            if "retention_class" in event_cols
            else "'transient' AS retention_class"
        )
        ev_created_col = "created_at" if "created_at" in event_cols else "timestamp AS created_at"
        src_cur.execute(
            f"SELECT id, timestamp, {agent_col}, {session_col}, event_type, "
            f"{tool_col}, {err_col}, {ret_col}, {ev_created_col} FROM events"
        )
        src_events: dict[str, tuple[str, str, str, str, str, str, str, str]] = {}
        for r in src_cur:
            e_id = str(r["id"])
            ts = str(r["timestamp"])
            agent_id = str(r["agent_id"]) if r["agent_id"] else "pi-desktop"
            session_id = str(r["session_id"]) if r["session_id"] else "default"
            event_type = str(r["event_type"])
            tool_name = str(r["tool_name"]) if r["tool_name"] else ""
            error_cat = sanitize_error_category(
                str(r["error_message"]) if r["error_message"] else ""
            )
            ret_cls = str(r["retention_class"]) if r["retention_class"] else "transient"
            if ret_cls not in ("transient", "durable"):
                ret_cls = "transient"
            created_at = str(r["created_at"]) if r["created_at"] else ts
            src_events[e_id] = (
                ts,
                agent_id,
                session_id,
                event_type,
                tool_name,
                error_cat,
                ret_cls,
                created_at,
            )

        shadow_cur.execute(
            """
            SELECT event_id, occurred_at, agent_id, session_id, event_type,
                   tool_name, error_category, retention_class, created_at
            FROM event_skeletons
            """
        )
        shadow_events: dict[str, tuple[str, str, str, str, str, str, str, str]] = {}
        for r in shadow_cur:
            e_id = str(r["event_id"])
            ts = str(r["occurred_at"])
            agent_id = str(r["agent_id"])
            session_id = str(r["session_id"])
            event_type = str(r["event_type"])
            tool_name = str(r["tool_name"])
            error_cat = str(r["error_category"])
            ret_cls = str(r["retention_class"])
            created_at = str(r["created_at"])
            shadow_events[e_id] = (
                ts,
                agent_id,
                session_id,
                event_type,
                tool_name,
                error_cat,
                ret_cls,
                created_at,
            )

        src_event_ids = set(src_events.keys())
        shadow_event_ids = set(shadow_events.keys())

        events_to_insert = src_event_ids - shadow_event_ids
        events_to_delete = shadow_event_ids - src_event_ids
        events_common = src_event_ids & shadow_event_ids

        # Check for conflicts on common canonical event IDs (M-S15 / M-S16)
        events_noop_count = 0
        for e_id in events_common:
            src_ev = src_events[e_id]
            shw_ev = shadow_events[e_id]
            # Compare event_type, tool_name, error_category, agent_id
            if (
                src_ev[1] != shw_ev[1]  # agent_id
                or src_ev[3] != shw_ev[3]  # event_type
                or src_ev[4] != shw_ev[4]  # tool_name
                or src_ev[5] != shw_ev[5]  # error_category
            ):
                raise MigrationConflictError(
                    entity_type="Event",
                    canonical_id=e_id,
                    source_summary=f"type='{src_ev[3]}', tool='{src_ev[4]}', error='{src_ev[5]}'",
                    shadow_summary=f"type='{shw_ev[3]}', tool='{shw_ev[4]}', error='{shw_ev[5]}'",
                )
            events_noop_count += 1

        # Apply event insertions
        event_insert_rows = []
        for e_id in events_to_insert:
            ev = src_events[e_id]
            event_insert_rows.append(
                (
                    e_id,
                    ev[0],
                    ev[1],
                    ev[2],
                    ev[3],
                    ev[4],
                    ev[5],
                    ev[6],
                    ev[7],
                )
            )

        if event_insert_rows:
            shadow_conn.executemany(
                """
                INSERT INTO event_skeletons (
                    event_id, occurred_at, agent_id, session_id, event_type,
                    tool_name, error_category, retention_class, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                event_insert_rows,
            )

        # Apply event deletions
        if events_to_delete:
            shadow_conn.executemany(
                "DELETE FROM event_skeletons WHERE event_id = ?;",
                [(e_id,) for e_id in events_to_delete],
            )

        shadow_conn.commit()

        # =====================================================================
        # 3. Verify Final Source-Set Parity (M-S03, no watermark)
        # =====================================================================
        shadow_cur.execute("SELECT COUNT(*) FROM raw_slices;")
        final_slices_count = int(shadow_cur.fetchone()[0])

        shadow_cur.execute("SELECT COUNT(*) FROM event_skeletons;")
        final_events_count = int(shadow_cur.fetchone()[0])

        if final_slices_count != len(src_slices):
            raise ReconciliationError(
                f"Parity check failed: source slices ({len(src_slices)}) != "
                f"shadow raw_slices ({final_slices_count})"
            )

        if final_events_count != len(src_events):
            raise ReconciliationError(
                f"Parity check failed: source events ({len(src_events)}) != "
                f"shadow event_skeletons ({final_events_count})"
            )

        status_msg = "Final canonical source-set parity verified (no watermark)"

        return ReconciliationReport(
            slices_inserted=len(slices_to_insert),
            slices_noop=slices_noop_count,
            slices_deleted=len(slices_to_delete),
            events_inserted=len(events_to_insert),
            events_noop=events_noop_count,
            events_deleted=len(events_to_delete),
            final_slices_count=final_slices_count,
            final_events_count=final_events_count,
            parity_verified=True,
            status_message=status_msg,
        )

    finally:
        src_conn.close()
        shadow_conn.close()
