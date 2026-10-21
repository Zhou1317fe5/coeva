"""V1 to V2 Schema Construction and Data Transformation Mapper.

Implements:
- M-S05: V2 event skeleton contains no prohibited legacy body fields.
- M-S10: Legacy hypothesis state preserved only in audit metadata, not promoted.
- M-S11: Raw Slice full-content integrity = 100% (byte-for-byte fidelity).
- M-S12: foreign_key_check = 0.
- Migration != Backfill: does not trigger semantic derivation or backfill.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.memory.v2.store import SCHEMA_SQL_PATH


class MapperError(Exception):
    """Base error for schema mapping and transformation failures."""

    pass


class PrivacySanitizationError(MapperError):
    """Raised when an unredactable prohibited body is detected."""

    pass


@dataclass(frozen=True)
class MappingReport:
    """Report of transformed entity counts and verification status."""

    slices_migrated: int
    events_migrated: int
    hypotheses_migrated: int
    audit_records_written: int
    foreign_key_violations: int
    content_integrity_verified: bool


def sanitize_error_category(raw_error: str | None) -> str:
    """Sanitize legacy error_message into a privacy-safe error_category (M-S05).

    Permitted: short error categories/summaries (e.g. 'bash failed', 'timeout').
    Forbidden: agent prompts, chain-of-thought, tool outputs, raw JSON bodies,
    full stack traces.
    """
    if not raw_error:
        return ""

    text = raw_error.strip()
    if not text:
        return ""

    # Redact stack traces: if "Traceback" is present, extract only the exception name/line
    if "Traceback" in text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        last_line = lines[-1] if lines else "Error"
        # Extract exception pattern if available
        match = re.search(r"([A-Za-z_]+Error|[A-Za-z_]+Exception):\s*(.*)", last_line)
        if match:
            text = f"{match.group(1)}: {match.group(2)[:60]}"
        else:
            text = last_line[:80]

    # Redact prompt-like markers or CoT markers
    forbidden_markers = [
        "Human:",
        "Assistant:",
        "System:",
        "<thought>",
        "</thought>",
        "```",
    ]
    for marker in forbidden_markers:
        if marker in text:
            # Strip forbidden body completely and keep safe generic label
            text = "redacted_execution_error"
            break

    # Bound maximum length of category to 120 chars
    if len(text) > 120:
        text = text[:117] + "..."

    return text


def initialize_v2_schema(dest_conn: sqlite3.Connection) -> None:
    """Initialize V2.1 schema on destination connection using canonical schema.sql."""
    if not SCHEMA_SQL_PATH.is_file():
        raise MapperError(f"Canonical schema.sql not found at {SCHEMA_SQL_PATH}")

    schema_sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    dest_conn.executescript(schema_sql)


def build_v2_shadow_db(
    snapshot_path: Path,
    shadow_path: Path,
    *,
    batch_size: int = 5000,
) -> MappingReport:
    """Build a complete V2 shadow DB from the WAL-safe snapshot DB.

    Applies exact frozen transformation rules:
    - slices -> raw_slices (scope='unresolved', project_id=NULL, dedup_key, 100% content fidelity)
    - events -> event_skeletons (privacy sanitized error_category, retention_class)
    - hypotheses -> hypotheses (status='candidate', confidence_class='tentative')
      AND legacy_hypothesis_audit (technical audit metadata only)

    Ensures:
    - M-S05: privacy boundary enforced.
    - M-S10: legacy hypothesis not promoted to confirmed_insights.
    - M-S11: full-content hash integrity = 100%.
    - M-S12: foreign_key_check = 0.
    """
    if shadow_path.is_file():
        shadow_path.unlink()

    shadow_path.parent.mkdir(parents=True, exist_ok=True)

    dest_conn = sqlite3.connect(str(shadow_path))
    dest_conn.execute("PRAGMA journal_mode = WAL;")
    dest_conn.execute("PRAGMA foreign_keys = ON;")

    try:
        # Step 1: Initialize V2 schema
        initialize_v2_schema(dest_conn)

        # Step 2: Open snapshot connection
        src_uri = f"file:{snapshot_path.resolve()}?mode=ro"
        src_conn = sqlite3.connect(src_uri, uri=True)
        src_conn.row_factory = sqlite3.Row

        slices_count = 0
        events_count = 0
        hypotheses_count = 0
        audit_count = 0

        now_iso = datetime.now(UTC).isoformat()

        try:
            # 1. Transform slices -> raw_slices
            src_cur = src_conn.cursor()
            src_cur.execute("PRAGMA table_info(slices);")
            slice_cols = {r[1] for r in src_cur.fetchall()}
            actor_col = "actor" if "actor" in slice_cols else "'user' AS actor"
            source_col = "source" if "source" in slice_cols else "'manual_feed' AS source"
            created_col = "created_at" if "created_at" in slice_cols else "timestamp AS created_at"
            src_cur.execute(
                f"SELECT id, timestamp, content, {actor_col}, {source_col}, {created_col} "
                f"FROM slices ORDER BY rowid"
            )

            slices_batch: list[tuple[str, str, str, str, str, str, None, str, str]] = []
            original_slice_contents: dict[str, str] = {}

            for row in src_cur:
                s_id = str(row["id"])
                occurred_at = str(row["timestamp"])
                content = str(row["content"])
                actor = str(row["actor"]) if row["actor"] else "user"
                source = str(row["source"]) if row["source"] else "manual_feed"
                created_at = str(row["created_at"]) if row["created_at"] else occurred_at
                dedup_key = f"legacy_slice_{s_id}"

                original_slice_contents[s_id] = content

                slices_batch.append(
                    (
                        s_id,
                        occurred_at,
                        content,
                        actor,
                        source,
                        "unresolved",
                        None,
                        dedup_key,
                        created_at,
                    )
                )

                if len(slices_batch) >= batch_size:
                    dest_conn.executemany(
                        """
                        INSERT INTO raw_slices (
                            slice_id, occurred_at, content, actor, source,
                            scope, project_id, ingestion_dedup_key, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        slices_batch,
                    )
                    dest_conn.commit()
                    slices_count += len(slices_batch)
                    slices_batch.clear()

            if slices_batch:
                dest_conn.executemany(
                    """
                    INSERT INTO raw_slices (
                        slice_id, occurred_at, content, actor, source,
                        scope, project_id, ingestion_dedup_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    slices_batch,
                )
                dest_conn.commit()
                slices_count += len(slices_batch)
                slices_batch.clear()

            # Verify M-S11: raw_slices full-content integrity = 100%
            dest_cur = dest_conn.cursor()
            dest_cur.execute("SELECT slice_id, content FROM raw_slices")
            for row in dest_cur:
                s_id = str(row[0])
                dest_content = str(row[1])
                orig_content = original_slice_contents.get(s_id)
                if orig_content is None or orig_content != dest_content:
                    raise MapperError(
                        f"M-S11 violation: Slice content integrity check failed for slice {s_id}"
                    )

            # 2. Transform events -> event_skeletons
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
            ev_created_col = (
                "created_at" if "created_at" in event_cols else "timestamp AS created_at"
            )
            src_cur.execute(
                f"SELECT id, timestamp, {agent_col}, {session_col}, event_type, "
                f"{tool_col}, {err_col}, {ret_col}, {ev_created_col} "
                f"FROM events ORDER BY rowid"
            )

            events_batch: list[tuple[str, str, str, str, str, str, str, str, str]] = []
            for row in src_cur:
                e_id = str(row["id"])
                occurred_at = str(row["timestamp"])
                agent_id = str(row["agent_id"]) if row["agent_id"] else "pi-desktop"
                session_id = str(row["session_id"]) if row["session_id"] else "default"
                event_type = str(row["event_type"])
                tool_name = str(row["tool_name"]) if row["tool_name"] else ""
                raw_err = str(row["error_message"]) if row["error_message"] else ""
                error_cat = sanitize_error_category(raw_err)
                ret_cls = str(row["retention_class"]) if row["retention_class"] else "transient"
                # Ensure retention_class is valid enum
                if ret_cls not in ("transient", "durable"):
                    ret_cls = "transient"
                created_at = str(row["created_at"]) if row["created_at"] else occurred_at

                events_batch.append(
                    (
                        e_id,
                        occurred_at,
                        agent_id,
                        session_id,
                        event_type,
                        tool_name,
                        error_cat,
                        ret_cls,
                        created_at,
                    )
                )

                if len(events_batch) >= batch_size:
                    dest_conn.executemany(
                        """
                        INSERT INTO event_skeletons (
                            event_id, occurred_at, agent_id, session_id,
                            event_type, tool_name, error_category, retention_class, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        events_batch,
                    )
                    dest_conn.commit()
                    events_count += len(events_batch)
                    events_batch.clear()

            if events_batch:
                dest_conn.executemany(
                    """
                    INSERT INTO event_skeletons (
                        event_id, occurred_at, agent_id, session_id,
                        event_type, tool_name, error_category, retention_class, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    events_batch,
                )
                dest_conn.commit()
                events_count += len(events_batch)
                events_batch.clear()

            # 3. Transform hypotheses -> hypotheses + legacy_hypothesis_audit
            src_cur.execute("PRAGMA table_info(hypotheses);")
            hypo_cols = {r[1] for r in src_cur.fetchall()}
            conf_col = "confidence" if "confidence" in hypo_cols else "NULL AS confidence"
            stat_col = "status" if "status" in hypo_cols else "'candidate' AS status"
            supp_col = (
                "supporting_episodes"
                if "supporting_episodes" in hypo_cols
                else "NULL AS supporting_episodes"
            )
            h_created_col = "created_at" if "created_at" in hypo_cols else "NULL AS created_at"
            src_cur.execute(
                f"SELECT id, statement, lenses, {conf_col}, {stat_col}, "
                f"{supp_col}, {h_created_col} FROM hypotheses ORDER BY rowid"
            )

            for row in src_cur:
                h_id = str(row["id"])
                statement = str(row["statement"])
                lenses = str(row["lenses"])
                orig_confidence = str(row["confidence"]) if row["confidence"] else None
                orig_status = str(row["status"]) if row["status"] else "candidate"
                supporting_episodes_raw = (
                    str(row["supporting_episodes"]) if row["supporting_episodes"] else None
                )
                h_created_at = str(row["created_at"]) if row["created_at"] else now_iso

                # Canonical hypotheses table: status MUST be candidate, confidence_class tentative
                dest_conn.execute(
                    """
                    INSERT INTO hypotheses (
                        hypothesis_id, statement, lenses, confidence_class,
                        status, last_calibrated_at, created_at
                    ) VALUES (?, ?, ?, 'tentative', 'candidate', NULL, ?);
                    """,
                    (h_id, statement, lenses, h_created_at),
                )
                hypotheses_count += 1

                # Technical audit table: preserve exact legacy metadata
                dest_conn.execute(
                    """
                    INSERT INTO legacy_hypothesis_audit (
                        hypothesis_id, original_statement, original_status,
                        original_lenses, original_confidence, supporting_episodes_raw,
                        migrated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        h_id,
                        statement,
                        orig_status,
                        lenses,
                        orig_confidence,
                        supporting_episodes_raw,
                        now_iso,
                    ),
                )
                audit_count += 1

            dest_conn.commit()

            # 4. Check that confirmed_insights has ZERO promoted hypotheses
            dest_cur.execute("SELECT COUNT(*) FROM confirmed_insights;")
            insight_count = int(dest_cur.fetchone()[0])
            if insight_count != 0:
                raise MapperError("M-S10 violation: Hypotheses were illegally promoted to insights")

            # 5. Check foreign key integrity (M-S12)
            dest_cur.execute("PRAGMA foreign_key_check;")
            fk_violations = dest_cur.fetchall()
            if fk_violations:
                msg = (
                    f"M-S12 violation: foreign_key_check returned "
                    f"{len(fk_violations)} violations: {fk_violations}"
                )
                raise MapperError(msg)

            # Record migration marker in _schema_migrations
            dest_conn.execute(
                """
                INSERT INTO _schema_migrations (
                    migration_id, source_version, target_version,
                    started_at, completed_at, status, checksum, error_message
                ) VALUES ('mig_v1_to_v2', 1, 20261018, ?, ?, 'completed', 'v2.1_cutover', NULL);
                """,
                (now_iso, now_iso),
            )
            dest_conn.execute("PRAGMA user_version = 20261018;")
            dest_conn.commit()

        finally:
            src_conn.close()

    finally:
        dest_conn.close()

    return MappingReport(
        slices_migrated=slices_count,
        events_migrated=events_count,
        hypotheses_migrated=hypotheses_count,
        audit_records_written=audit_count,
        foreign_key_violations=0,
        content_integrity_verified=True,
    )
