"""Chronicle Store: local SQLite archive of slices, agent events and evidence.

Phase 2A scope only -- see docs/specs/phase-2-chronicle-and-growth-chapters/SPEC.md.
Two tables plus one view; no reasoning layer, no LLM.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.connectors.contracts import AgentEvent
from src.core.attribution import classify
from src.core.hypotheses import (
    ConfidenceLevel,
    DevelopmentHypothesis,
    DevelopmentLens,
    HypothesisStatus,
)
from src.core.self_model import (
    ConfirmedInsight,
    GrowthTheme,
    InsightStatus,
    ThemeStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS slices (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'user',
    source      TEXT NOT NULL DEFAULT 'manual_feed',
    content     TEXT NOT NULL,
    mood_flag   TEXT NOT NULL DEFAULT 'neutral',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    session_id      TEXT NOT NULL DEFAULT 'default',
    event_type      TEXT NOT NULL,
    tool_name       TEXT NOT NULL DEFAULT '',
    error_message   TEXT NOT NULL DEFAULT '',
    provenance      TEXT NOT NULL,
    retention_class TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_slices_time      ON slices(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_time      ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_session   ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_retention ON events(retention_class, timestamp);
CREATE VIEW IF NOT EXISTS evidence AS
    SELECT id, timestamp, 'slice' AS source_type, actor,
           'user_explicit' AS provenance, 'durable' AS retention_class,
           content
      FROM slices
    UNION ALL
    SELECT id, timestamp, 'event' AS source_type, agent_id,
           provenance, retention_class,
           CASE WHEN tool_name <> '' THEN event_type || ':' || tool_name ELSE event_type END
      FROM events;
CREATE TABLE IF NOT EXISTS hypotheses (
    id                  TEXT PRIMARY KEY,
    statement           TEXT NOT NULL,
    lenses              TEXT NOT NULL,
    supporting_patterns TEXT NOT NULL,
    supporting_episodes TEXT NOT NULL,
    counter_episodes    TEXT NOT NULL,
    confidence          TEXT NOT NULL,
    status              TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS insights (
    id                  TEXT PRIMARY KEY,
    statement           TEXT NOT NULL,
    lenses              TEXT NOT NULL,
    supporting_patterns TEXT NOT NULL,
    user_confirmation   TEXT NOT NULL,
    valid_from          TEXT NOT NULL,
    last_revalidated    TEXT NOT NULL,
    status              TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS growth_themes (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    lens                TEXT NOT NULL,
    statement           TEXT NOT NULL,
    status              TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
"""

DEFAULT_DB_PATH = Path("data") / "companion_chronicle.db"
DEFAULT_TRANSIENT_TTL_DAYS = 30


@dataclass(frozen=True)
class SliceRecord:
    """A user-authored slice as stored in the archive."""

    id: str
    timestamp: str
    content: str
    mood_flag: str
    actor: str = "user"
    source: str = "manual_feed"


@dataclass(frozen=True)
class Episode:
    """A work session: agent events sharing one session_id."""

    session_id: str
    started_at: str
    ended_at: str
    event_count: int
    agent_ids: tuple[str, ...]
    has_user_action: bool


class ChronicleStore:
    """Owns the Chronicle SQLite database: writes, queries and decay."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL keeps the telemetry writer from blocking reader queries (SPEC section 10.2).
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    # ── writes ────────────────────────────────────────────────────────────────

    def record_slice(self, slice_record: SliceRecord) -> None:
        """Insert a slice, ignoring a duplicate id."""
        self._conn.execute(
            "INSERT OR IGNORE INTO slices "
            "(id, timestamp, actor, source, content, mood_flag) VALUES (?, ?, ?, ?, ?, ?)",
            (
                slice_record.id,
                slice_record.timestamp,
                slice_record.actor,
                slice_record.source,
                slice_record.content,
                slice_record.mood_flag,
            ),
        )
        self._conn.commit()

    def record_event(self, event: AgentEvent) -> bool:
        """Persist an agent event. Returns False when it was a duplicate."""
        provenance, retention_class = classify(event.event_type)
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO events "
            "(id, timestamp, agent_id, session_id, event_type, tool_name, error_message, "
            " provenance, retention_class) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id(event),
                event.timestamp,
                event.agent_id,
                event.session_id,
                str(event.event_type),
                event.tool_name,
                event.error_message,
                provenance,
                retention_class,
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def record_events_batch(self, events: Iterable[AgentEvent]) -> int:
        """Batch insert events in a single transaction. Returns count of newly inserted rows."""
        rows = []
        for event in events:
            provenance, retention_class = classify(event.event_type)
            rows.append(
                (
                    event_id(event),
                    event.timestamp,
                    event.agent_id,
                    event.session_id,
                    str(event.event_type),
                    event.tool_name,
                    event.error_message,
                    provenance,
                    retention_class,
                )
            )
        if not rows:
            return 0
        cursor = self._conn.executemany(
            "INSERT OR IGNORE INTO events "
            "(id, timestamp, agent_id, session_id, event_type, tool_name, error_message, "
            " provenance, retention_class) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return cursor.rowcount

    def import_slices_jsonl(self, path: Path | None = None) -> int:
        """Idempotently import the legacy raw slice stream. Returns newly added rows."""
        source_path = path or (Path("data") / "raw_slices.jsonl")
        if not source_path.is_file():
            return 0

        known = {row["id"] for row in self._conn.execute("SELECT id FROM slices")}
        added = 0
        with source_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    record = SliceRecord(
                        id=data["id"],
                        timestamp=data["timestamp"],
                        content=data["content"],
                        mood_flag=data.get("mood_flag", "neutral"),
                        actor=data.get("actor", "user"),
                        source=data.get("source", "manual_feed"),
                    )
                except (json.JSONDecodeError, KeyError):
                    continue  # skip a malformed line rather than aborting the import
                if record.id in known:
                    continue
                self.record_slice(record)
                known.add(record.id)
                added += 1
        return added

    # ── queries ───────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Row counts per archive section."""
        return {
            "slices": self._count("slices"),
            "events": self._count("events"),
            "episodes": self._count_episodes(),
        }

    def list_slices(
        self, *, limit: int = 20, offset: int = 0, mood: str | None = None
    ) -> list[SliceRecord]:
        """Return slices newest-first, optionally filtered by mood."""
        sql = "SELECT * FROM slices"
        params: list[Any] = []
        if mood:
            sql += " WHERE mood_flag = ?"
            params.append(mood)
        sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [
            SliceRecord(
                id=row["id"],
                timestamp=row["timestamp"],
                content=row["content"],
                mood_flag=row["mood_flag"],
                actor=row["actor"],
                source=row["source"],
            )
            for row in self._conn.execute(sql, params)
        ]

    def search_slices(self, keyword: str, *, limit: int = 20) -> list[SliceRecord]:
        """Substring search over slice content.

        shortcut: LIKE full scan; FTS5 needs a Chinese tokenizer to match 2-char words,
        switch when slices > 10k (SPEC section 4.4 and the Deferred Backlog).
        """
        pattern = f"%{keyword}%"
        return [
            SliceRecord(
                id=row["id"],
                timestamp=row["timestamp"],
                content=row["content"],
                mood_flag=row["mood_flag"],
                actor=row["actor"],
                source=row["source"],
            )
            for row in self._conn.execute(
                "SELECT * FROM slices WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (pattern, limit),
            )
        ]

    def get_slices_in_timerange(
        self, start_iso: str, end_iso: str, *, limit: int = 50
    ) -> list[SliceRecord]:
        """Return slices within an ISO timestamp range [start_iso, end_iso], newest-first."""
        rows = self._conn.execute(
            "SELECT * FROM slices WHERE timestamp >= ? AND timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (start_iso, end_iso, limit),
        ).fetchall()
        return [
            SliceRecord(
                id=row["id"],
                timestamp=row["timestamp"],
                content=row["content"],
                mood_flag=row["mood_flag"],
                actor=row["actor"],
                source=row["source"],
            )
            for row in rows
        ]

    def search_events(self, keyword: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Search historical events by session_id, tool_name, error_message, or agent_id."""
        pattern = f"%{keyword}%"
        rows = self._conn.execute(
            "SELECT id, timestamp, agent_id, session_id, event_type, tool_name, error_message "
            "FROM events "
            "WHERE session_id LIKE ? OR tool_name LIKE ? "
            "   OR error_message LIKE ? OR agent_id LIKE ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (pattern, pattern, pattern, pattern, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_evidence(
        self, *, limit: int = 20, offset: int = 0, provenance: str | None = None
    ) -> list[dict[str, Any]]:
        """Return rows of the unified evidence view, newest-first."""
        sql = "SELECT * FROM evidence"
        params: list[Any] = []
        if provenance:
            sql += " WHERE provenance = ?"
            params.append(provenance)
        sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in self._conn.execute(sql, params)]

    def list_episodes(self, *, limit: int = 20) -> list[Episode]:
        """Group events into episodes by session_id (SPEC section 6)."""
        rows = self._conn.execute(
            "SELECT session_id, MIN(timestamp) AS started_at, MAX(timestamp) AS ended_at, "
            "       COUNT(*) AS event_count, "
            "       GROUP_CONCAT(DISTINCT agent_id) AS agent_ids, "
            "       MAX(CASE WHEN provenance = 'user_action' THEN 1 ELSE 0 END) AS has_user "
            "  FROM events GROUP BY session_id "
            " ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        return [
            Episode(
                session_id=row["session_id"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                event_count=row["event_count"],
                agent_ids=tuple(sorted((row["agent_ids"] or "").split(","))),
                has_user_action=bool(row["has_user"]),
            )
            for row in rows
        ]

    # ── decay ─────────────────────────────────────────────────────────────────

    def prune(
        self, *, ttl_days: int = DEFAULT_TRANSIENT_TTL_DAYS, now: datetime | None = None
    ) -> int:
        """Delete transient events older than the TTL. Durable rows are never touched."""
        cutoff = ((now or datetime.now(UTC)) - timedelta(days=ttl_days)).isoformat()
        cursor = self._conn.execute(
            "DELETE FROM events WHERE retention_class = 'transient' AND timestamp < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cursor.rowcount

    def _count(self, table: str) -> int:
        # `table` is only ever an internal literal, never user input.
        row = self._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"])

    def _count_episodes(self) -> int:
        row = self._conn.execute("SELECT COUNT(DISTINCT session_id) AS n FROM events").fetchone()
        return int(row["n"])

    # ── Phase 2C: Self Model, Hypotheses, Insights & Growth Themes ───

    def save_hypothesis(self, hyp: DevelopmentHypothesis) -> None:
        """Insert or update a development hypothesis."""
        self._conn.execute(
            "INSERT OR REPLACE INTO hypotheses "
            "(id, statement, lenses, supporting_patterns, supporting_episodes, "
            " counter_episodes, confidence, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                hyp.hypothesis_id,
                hyp.statement,
                ",".join(lens.value for lens in hyp.lenses),
                ",".join(hyp.supporting_patterns),
                ",".join(hyp.supporting_episodes),
                ",".join(hyp.counter_episodes),
                hyp.confidence.value,
                hyp.status.value,
                hyp.created_at,
            ),
        )
        self._conn.commit()

    def list_hypotheses(
        self, *, status: HypothesisStatus | None = None
    ) -> list[DevelopmentHypothesis]:
        """Query development hypotheses, optionally filtered by status."""
        sql = "SELECT * FROM hypotheses"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status.value)
        sql += " ORDER BY created_at DESC"

        out: list[DevelopmentHypothesis] = []
        for r in self._conn.execute(sql, params):
            lenses = tuple(DevelopmentLens(x) for x in r["lenses"].split(",") if x)
            out.append(
                DevelopmentHypothesis(
                    hypothesis_id=r["id"],
                    statement=r["statement"],
                    lenses=lenses,
                    supporting_patterns=tuple(x for x in r["supporting_patterns"].split(",") if x),
                    supporting_episodes=tuple(x for x in r["supporting_episodes"].split(",") if x),
                    counter_episodes=tuple(x for x in r["counter_episodes"].split(",") if x),
                    confidence=ConfidenceLevel(r["confidence"]),
                    status=HypothesisStatus(r["status"]),
                    created_at=r["created_at"],
                )
            )
        return out

    def save_insight(self, insight: ConfirmedInsight) -> None:
        """Persist a confirmed mutual insight."""
        self._conn.execute(
            "INSERT OR REPLACE INTO insights "
            "(id, statement, lenses, supporting_patterns, user_confirmation, "
            " valid_from, last_revalidated, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                insight.insight_id,
                insight.statement,
                ",".join(lens.value for lens in insight.lenses),
                ",".join(insight.supporting_patterns),
                insight.user_confirmation_text,
                insight.valid_from,
                insight.last_revalidated,
                insight.status.value,
            ),
        )
        self._conn.commit()

    def list_insights(self, *, status: InsightStatus | None = None) -> list[ConfirmedInsight]:
        """Query confirmed insights, optionally filtered by status."""
        sql = "SELECT * FROM insights"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status.value)
        sql += " ORDER BY valid_from DESC"

        out: list[ConfirmedInsight] = []
        for r in self._conn.execute(sql, params):
            lenses = tuple(DevelopmentLens(x) for x in r["lenses"].split(",") if x)
            out.append(
                ConfirmedInsight(
                    insight_id=r["id"],
                    statement=r["statement"],
                    lenses=lenses,
                    supporting_patterns=tuple(x for x in r["supporting_patterns"].split(",") if x),
                    user_confirmation_text=r["user_confirmation"],
                    valid_from=r["valid_from"],
                    last_revalidated=r["last_revalidated"],
                    status=InsightStatus(r["status"]),
                )
            )
        return out

    def save_theme(self, theme: GrowthTheme) -> None:
        """Persist a growth theme."""
        self._conn.execute(
            "INSERT OR REPLACE INTO growth_themes "
            "(id, title, lens, statement, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                theme.theme_id,
                theme.title,
                theme.lens.value,
                theme.statement,
                theme.status.value,
                theme.created_at,
            ),
        )
        self._conn.commit()

    def list_themes(self, *, status: ThemeStatus | None = None) -> list[GrowthTheme]:
        """Query active or historical growth themes."""
        sql = "SELECT * FROM growth_themes"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status.value)
        sql += " ORDER BY created_at DESC"

        out: list[GrowthTheme] = []
        for r in self._conn.execute(sql, params):
            out.append(
                GrowthTheme(
                    theme_id=r["id"],
                    title=r["title"],
                    lens=DevelopmentLens(r["lens"]),
                    statement=r["statement"],
                    status=ThemeStatus(r["status"]),
                    created_at=r["created_at"],
                )
            )
        return out


def event_id(event: AgentEvent) -> str:
    """Stable identity for an agent event, so a redelivered hook cannot duplicate evidence."""
    parts = (
        event.agent_id,
        event.session_id,
        event.timestamp,
        str(event.event_type),
        event.tool_name,
        event.error_message,
    )
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
