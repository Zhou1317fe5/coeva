"""Legacy Compatibility Layer & Dual-Master Elimination for Coeva Memory V2.1.

Part of Stage 4 (WP-11).
Canonical Responsibility:
- V2 SQLite = single canonical writer
- Legacy readers = temporary compatibility views/adapters
- Views are READ-ONLY, non-canonical, and non-evidence
- No INSTEAD OF triggers or write-through compatibility layers
- Retirement is dependency-based (4 conditions including 7 continuous zero-read days)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.memory.v2.store import ChronicleStoreV2

COMPATIBILITY_VIEW_NAMES: tuple[str, ...] = (
    "legacy_slices_view",
    "legacy_events_view",
)

LEGACY_SLICES_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS legacy_slices_view AS
    SELECT
        slice_id AS id,
        occurred_at AS timestamp,
        actor,
        source,
        content,
        'neutral' AS mood_flag,
        created_at
    FROM raw_slices;
"""

LEGACY_EVENTS_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS legacy_events_view AS
    SELECT
        event_id AS id,
        occurred_at AS timestamp,
        agent_id,
        session_id,
        event_type,
        tool_name,
        error_category AS error_message,
        'agent_context' AS provenance,
        retention_class,
        created_at
    FROM event_skeletons;
"""

# Engine-level fail-closed views for legacy runtime compatibility
LEGACY_SLICES_COMPAT_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS slices AS
    SELECT
        slice_id AS id,
        occurred_at AS timestamp,
        actor,
        source,
        content,
        'neutral' AS mood_flag,
        created_at
    FROM raw_slices;
"""

LEGACY_EVENTS_COMPAT_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS events AS
    SELECT
        event_id AS id,
        occurred_at AS timestamp,
        agent_id,
        session_id,
        event_type,
        tool_name,
        error_category AS error_message,
        'agent_context' AS provenance,
        retention_class,
        created_at
    FROM event_skeletons;
"""


class CompatibilityError(RuntimeError):
    """Base exception for legacy compatibility layer errors."""

    pass


class CompatibilityViewReadOnlyViolationError(CompatibilityError):
    """Raised when a compatibility view is unexpectedly writable or has write triggers."""

    pass


class CompatibilityEvidenceViolationError(CompatibilityError):
    """Raised when a compatibility view or record is illegally used as canonical evidence."""

    pass


class CompatibilityRetirementBlockedError(CompatibilityError):
    """Raised when an attempt is made to drop views before retirement criteria are met."""

    pass


@dataclass(frozen=True)
class LegacySliceRecord:
    """Projected legacy read record from legacy_slices_view."""

    id: str
    timestamp: str
    actor: str
    source: str
    content: str
    mood_flag: str
    created_at: str


@dataclass(frozen=True)
class LegacyEventRecord:
    """Projected legacy read record from legacy_events_view."""

    id: str
    timestamp: str
    agent_id: str
    session_id: str
    event_type: str
    tool_name: str
    error_message: str
    provenance: str
    retention_class: str
    created_at: str


@dataclass
class CompatibilityObservability:
    """Technical usage tracker for compatibility views.

    Strict Invariant (C-15):
    Contains ONLY technical counts and timestamps.
    NO user content, NO query text, and NO evidence semantics.
    """

    total_slice_reads: int = 0
    total_event_reads: int = 0
    last_slice_read_at: datetime | None = None
    last_event_read_at: datetime | None = None
    registered_readers: set[str] = field(default_factory=set)

    @property
    def total_reads(self) -> int:
        return self.total_slice_reads + self.total_event_reads

    @property
    def last_read_at(self) -> datetime | None:
        times = [t for t in (self.last_slice_read_at, self.last_event_read_at) if t is not None]
        return max(times) if times else None

    def record_slice_read(self, reader_id: str = "") -> None:
        self.total_slice_reads += 1
        self.last_slice_read_at = datetime.now(UTC)
        if reader_id:
            self.registered_readers.add(reader_id)

    def record_event_read(self, reader_id: str = "") -> None:
        self.total_event_reads += 1
        self.last_event_read_at = datetime.now(UTC)
        if reader_id:
            self.registered_readers.add(reader_id)


@dataclass(frozen=True)
class CompatibilityRetirementStatus:
    """Structured report on whether compatibility views are safe to drop."""

    active_readers: int
    transitional_clients_retired: bool
    last_read_at: datetime | None
    zero_read_days: float
    rollback_plan_cleared: bool
    safe_to_drop: bool
    reasons_blocking_drop: tuple[str, ...]


def _unwrap_conn(target: sqlite3.Connection | ChronicleStoreV2) -> sqlite3.Connection:
    if isinstance(target, sqlite3.Connection):
        return target
    if hasattr(target, "_conn") and isinstance(target._conn, sqlite3.Connection):
        return target._conn
    raise TypeError(f"Expected sqlite3.Connection or ChronicleStoreV2, got {type(target)}")


def install_legacy_views(target: sqlite3.Connection | ChronicleStoreV2) -> None:
    """Explicitly install read-only legacy compatibility views on a V2 database.

    Strict Invariant:
    Views are NOT canonical entities and do not change CANONICAL_TABLES.
    NO INSTEAD OF triggers are created.
    Installs both WP-11 legacy_* views and fail-safe slices/events views.
    """
    conn = _unwrap_conn(target)
    conn.execute(LEGACY_SLICES_VIEW_SQL)
    conn.execute(LEGACY_EVENTS_VIEW_SQL)
    conn.execute(LEGACY_SLICES_COMPAT_VIEW_SQL)
    conn.execute(LEGACY_EVENTS_COMPAT_VIEW_SQL)
    conn.commit()


def drop_legacy_views(
    target: sqlite3.Connection | ChronicleStoreV2,
    *,
    force: bool = False,
    retirement_status: CompatibilityRetirementStatus | None = None,
) -> None:
    """Explicitly drop legacy compatibility views.

    Unless force=True, retirement_status must be provided and safe_to_drop must be True.
    """
    if not force:
        if retirement_status is None:
            raise CompatibilityRetirementBlockedError(
                "Cannot drop legacy views without retirement_status or explicit force=True."
            )
        if not retirement_status.safe_to_drop:
            reasons = "; ".join(retirement_status.reasons_blocking_drop)
            raise CompatibilityRetirementBlockedError(
                f"Cannot drop legacy views: retirement criteria unmet: {reasons}"
            )

    conn = _unwrap_conn(target)
    conn.execute("DROP VIEW IF EXISTS legacy_slices_view;")
    conn.execute("DROP VIEW IF EXISTS legacy_events_view;")
    conn.execute("DROP VIEW IF EXISTS slices;")
    conn.execute("DROP VIEW IF EXISTS events;")
    conn.commit()


def has_legacy_views(target: sqlite3.Connection | ChronicleStoreV2) -> bool:
    """Return True if both compatibility views exist."""
    conn = _unwrap_conn(target)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name IN (?, ?);",
        COMPATIBILITY_VIEW_NAMES,
    )
    found = {row[0] for row in cursor.fetchall()}
    return len(found) == len(COMPATIBILITY_VIEW_NAMES)


def verify_legacy_views_read_only(target: sqlite3.Connection | ChronicleStoreV2) -> bool:
    """Verify that legacy compatibility views are strictly read-only at the engine level.

    Attempts INSERT, UPDATE, and DELETE on both views and verifies that SQLite
    engine rejects each with OperationalError ('cannot modify ... because it is a view').
    Also asserts that no INSTEAD OF triggers exist for these views.
    """
    conn = _unwrap_conn(target)
    cursor = conn.cursor()

    # 1. Assert no write triggers exist on the views
    cursor.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type='trigger' AND tbl_name IN (?, ?);",
        COMPATIBILITY_VIEW_NAMES,
    )
    triggers = cursor.fetchall()
    if triggers:
        raise CompatibilityViewReadOnlyViolationError(
            f"Write triggers detected on compatibility views: {triggers}"
        )

    # 2. Test legacy_slices_view write attempts
    now_iso = datetime.now(UTC).isoformat()
    try:
        cursor.execute(
            "INSERT INTO legacy_slices_view (id, timestamp, actor, source, content, mood_flag, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?);",
            ("test_slice_id", now_iso, "user", "manual_feed", "test", "neutral", now_iso),
        )
        raise CompatibilityViewReadOnlyViolationError(
            "INSERT into legacy_slices_view succeeded unexpectedly!"
        )
    except sqlite3.OperationalError as exc:
        if "cannot modify" not in str(exc).lower():
            raise CompatibilityViewReadOnlyViolationError(
                f"Unexpected error on INSERT to legacy_slices_view: {exc}"
            ) from exc

    try:
        cursor.execute(
            "UPDATE legacy_slices_view SET content = 'tampered' WHERE id = 'test_slice_id';"
        )
        raise CompatibilityViewReadOnlyViolationError(
            "UPDATE on legacy_slices_view succeeded unexpectedly!"
        )
    except sqlite3.OperationalError as exc:
        if "cannot modify" not in str(exc).lower():
            raise CompatibilityViewReadOnlyViolationError(
                f"Unexpected error on UPDATE to legacy_slices_view: {exc}"
            ) from exc

    try:
        cursor.execute("DELETE FROM legacy_slices_view WHERE id = 'test_slice_id';")
        raise CompatibilityViewReadOnlyViolationError(
            "DELETE from legacy_slices_view succeeded unexpectedly!"
        )
    except sqlite3.OperationalError as exc:
        if "cannot modify" not in str(exc).lower():
            raise CompatibilityViewReadOnlyViolationError(
                f"Unexpected error on DELETE to legacy_slices_view: {exc}"
            ) from exc

    # 3. Test legacy_events_view write attempts
    try:
        cursor.execute(
            "INSERT INTO legacy_events_view (id, timestamp, agent_id, session_id, event_type, "
            "tool_name, error_message, provenance, retention_class, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (
                "test_event_id",
                now_iso,
                "agent",
                "sess",
                "tool_call",
                "tool",
                "",
                "agent_context",
                "transient",
                now_iso,
            ),
        )
        raise CompatibilityViewReadOnlyViolationError(
            "INSERT into legacy_events_view succeeded unexpectedly!"
        )
    except sqlite3.OperationalError as exc:
        if "cannot modify" not in str(exc).lower():
            raise CompatibilityViewReadOnlyViolationError(
                f"Unexpected error on INSERT to legacy_events_view: {exc}"
            ) from exc

    try:
        cursor.execute(
            "UPDATE legacy_events_view SET tool_name = 'tampered' WHERE id = 'test_event_id';"
        )
        raise CompatibilityViewReadOnlyViolationError(
            "UPDATE on legacy_events_view succeeded unexpectedly!"
        )
    except sqlite3.OperationalError as exc:
        if "cannot modify" not in str(exc).lower():
            raise CompatibilityViewReadOnlyViolationError(
                f"Unexpected error on UPDATE to legacy_events_view: {exc}"
            ) from exc

    try:
        cursor.execute("DELETE FROM legacy_events_view WHERE id = 'test_event_id';")
        raise CompatibilityViewReadOnlyViolationError(
            "DELETE from legacy_events_view succeeded unexpectedly!"
        )
    except sqlite3.OperationalError as exc:
        if "cannot modify" not in str(exc).lower():
            raise CompatibilityViewReadOnlyViolationError(
                f"Unexpected error on DELETE to legacy_events_view: {exc}"
            ) from exc

    return True


def assert_not_evidence_source(source_name: str) -> None:
    """Verify that a source identifier is not a compatibility view (C-05, C-13).

    Raises:
        CompatibilityEvidenceViolationError: If source_name is a compatibility view.
    """
    norm = source_name.strip().lower()
    if norm in COMPATIBILITY_VIEW_NAMES or "legacy_" in norm:
        raise CompatibilityEvidenceViolationError(
            f"Compatibility view '{source_name}' cannot be used as canonical evidence, "
            "provenance source, retrieval input, or consolidation candidate."
        )


class CompatibilityReader:
    """Narrow transitional reader adapter reading strictly through compatibility views.

    Features:
    - Reads projected safe shapes for slices and events
    - Records read observability (technical counters only, no content/query text)
    - Enforces non-evidence boundary: cannot produce canonical evidence entities
    """

    def __init__(
        self,
        target: sqlite3.Connection | ChronicleStoreV2,
        *,
        reader_id: str = "legacy_reader",
        observability: CompatibilityObservability | None = None,
    ) -> None:
        self._conn = _unwrap_conn(target)
        self.reader_id = reader_id
        self.observability = observability or CompatibilityObservability()

    def get_slice(self, slice_id: str) -> LegacySliceRecord | None:
        """Fetch a slice through legacy_slices_view by ID."""
        self.observability.record_slice_read(self.reader_id)
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, actor, source, content, mood_flag, created_at "
            "FROM legacy_slices_view WHERE id = ?;",
            (slice_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return LegacySliceRecord(
            id=str(row[0]),
            timestamp=str(row[1]),
            actor=str(row[2]),
            source=str(row[3]),
            content=str(row[4]),
            mood_flag=str(row[5]),
            created_at=str(row[6]),
        )

    def list_slices(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        mood: str | None = None,
    ) -> list[LegacySliceRecord]:
        """List slices through legacy_slices_view."""
        self.observability.record_slice_read(self.reader_id)
        cursor = self._conn.cursor()
        cols = "id, timestamp, actor, source, content, mood_flag, created_at"
        sql = f"SELECT {cols} FROM legacy_slices_view"
        params: list[Any] = []
        if mood:
            sql += " WHERE mood_flag = ?"
            params.append(mood)
        sql += " ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(sql, params)
        records: list[LegacySliceRecord] = []
        for row in cursor.fetchall():
            records.append(
                LegacySliceRecord(
                    id=str(row[0]),
                    timestamp=str(row[1]),
                    actor=str(row[2]),
                    source=str(row[3]),
                    content=str(row[4]),
                    mood_flag=str(row[5]),
                    created_at=str(row[6]),
                )
            )
        return records

    def count_slices(self) -> int:
        """Return total row count in legacy_slices_view."""
        self.observability.record_slice_read(self.reader_id)
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM legacy_slices_view;")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def get_event(self, event_id: str) -> LegacyEventRecord | None:
        """Fetch an event through legacy_events_view by ID (privacy-sanitized)."""
        self.observability.record_event_read(self.reader_id)
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, agent_id, session_id, event_type, tool_name, "
            "error_message, provenance, retention_class, created_at "
            "FROM legacy_events_view WHERE id = ?;",
            (event_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return LegacyEventRecord(
            id=str(row[0]),
            timestamp=str(row[1]),
            agent_id=str(row[2]),
            session_id=str(row[3]),
            event_type=str(row[4]),
            tool_name=str(row[5]),
            error_message=str(row[6]),
            provenance=str(row[7]),
            retention_class=str(row[8]),
            created_at=str(row[9]),
        )

    def list_events(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
    ) -> list[LegacyEventRecord]:
        """List events through legacy_events_view."""
        self.observability.record_event_read(self.reader_id)
        cursor = self._conn.cursor()
        cols = (
            "id, timestamp, agent_id, session_id, event_type, tool_name, "
            "error_message, provenance, retention_class, created_at"
        )
        sql = f"SELECT {cols} FROM legacy_events_view"
        params: list[Any] = []
        if event_type:
            sql += " WHERE event_type = ?"
            params.append(event_type)
        sql += " ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(sql, params)
        records: list[LegacyEventRecord] = []
        for row in cursor.fetchall():
            records.append(
                LegacyEventRecord(
                    id=str(row[0]),
                    timestamp=str(row[1]),
                    agent_id=str(row[2]),
                    session_id=str(row[3]),
                    event_type=str(row[4]),
                    tool_name=str(row[5]),
                    error_message=str(row[6]),
                    provenance=str(row[7]),
                    retention_class=str(row[8]),
                    created_at=str(row[9]),
                )
            )
        return records

    def count_events(self) -> int:
        """Return total row count in legacy_events_view."""
        self.observability.record_event_read(self.reader_id)
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM legacy_events_view;")
        row = cursor.fetchone()
        return int(row[0]) if row else 0


class CompatibilityRetirementEvaluator:
    """Dependency-based retirement gate evaluator for legacy compatibility views.

    Rules:
    Compatibility views may be dropped ONLY after ALL 4 conditions are met:
    1. production code no longer depends on legacy readers (active_readers == 0);
    2. transitional clients are retired (transitional_clients_retired is True);
    3. observed legacy-view read count is zero for 7 continuous days (zero_read_days >= 7.0);
    4. canary / rollback plans no longer require them (rollback_plan_cleared is True).
    """

    @classmethod
    def evaluate(
        cls,
        *,
        active_readers: int,
        transitional_clients_retired: bool,
        last_read_at: datetime | None,
        rollback_plan_cleared: bool,
        now: datetime | None = None,
    ) -> CompatibilityRetirementStatus:
        current_time = now or datetime.now(UTC)
        reasons: list[str] = []

        # Condition 1: active readers count
        if active_readers > 0:
            reasons.append(
                f"Production code still has {active_readers} active legacy readers registered"
            )

        # Condition 2: transitional clients retired
        if not transitional_clients_retired:
            reasons.append("Transitional legacy clients have not been marked retired")

        # Condition 3: zero read days >= 7 continuous days
        if last_read_at is None:
            # Never read -> satisfies zero read days requirement
            zero_read_days = 999.0
        else:
            diff = current_time - last_read_at
            zero_read_days = max(0.0, diff.total_seconds() / 86400.0)
            if zero_read_days < 7.0:
                reasons.append(
                    f"Observed legacy-view read within last 7 days: {zero_read_days:.2f} "
                    "zero-read days (< 7.0 days required)"
                )

        # Condition 4: rollback plan cleared
        if not rollback_plan_cleared:
            reasons.append("Canary / rollback plans still require compatibility views")

        safe_to_drop = len(reasons) == 0

        return CompatibilityRetirementStatus(
            active_readers=active_readers,
            transitional_clients_retired=transitional_clients_retired,
            last_read_at=last_read_at,
            zero_read_days=zero_read_days,
            rollback_plan_cleared=rollback_plan_cleared,
            safe_to_drop=safe_to_drop,
            reasons_blocking_drop=tuple(reasons),
        )


class V2ChronicleStoreAdapter:
    """Read-only compatibility adapter for legacy UI/HTTP readers wrapping CompatibilityReader.

    Adheres to WP-11:
    - Compatibility reads work via legacy_slices_view and legacy_events_view.
    - Canonical writes directly to legacy views are rejected (read-only).
    - Exposes stats(), list_slices(), search_slices(), list_events(), search_events().
    """

    def __init__(
        self,
        v2_store: ChronicleStoreV2,
        reader: CompatibilityReader | None = None,
    ) -> None:
        self.v2_store = v2_store
        self.reader = reader or CompatibilityReader(v2_store)

    def stats(self) -> dict[str, int]:
        return {
            "slices": self.reader.count_slices(),
            "events": self.reader.count_events(),
            "episodes": 0,
            "hypotheses": len(self.v2_store.list_hypotheses()),
            "insights": len(self.v2_store.list_confirmed_insights()),
        }

    def list_slices(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        mood: str | None = None,
    ) -> list[Any]:
        from src.memory.store import SliceRecord

        legacy_records = self.reader.list_slices(limit=limit, offset=offset, mood=mood)
        return [
            SliceRecord(
                id=r.id,
                timestamp=r.timestamp,
                actor=r.actor,
                source=r.source,
                content=r.content,
                mood_flag=r.mood_flag,
            )
            for r in legacy_records
        ]

    def search_slices(self, keyword: str, *, limit: int = 20) -> list[Any]:
        from src.memory.store import SliceRecord

        conn = _unwrap_conn(self.v2_store)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, actor, source, content, mood_flag, created_at "
            "FROM legacy_slices_view WHERE content LIKE ? "
            "ORDER BY timestamp DESC LIMIT ?;",
            (f"%{keyword}%", limit),
        )
        records = []
        for row in cursor.fetchall():
            records.append(
                SliceRecord(
                    id=str(row[0]),
                    timestamp=str(row[1]),
                    actor=str(row[2]),
                    source=str(row[3]),
                    content=str(row[4]),
                    mood_flag=str(row[5]),
                )
            )
        return records

    def search_events(self, keyword: str, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = _unwrap_conn(self.v2_store)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, agent_id, session_id, event_type, tool_name, "
            "error_message, provenance, retention_class, created_at "
            "FROM legacy_events_view WHERE tool_name LIKE ? OR event_type LIKE ? "
            "ORDER BY timestamp DESC LIMIT ?;",
            (f"%{keyword}%", f"%{keyword}%", limit),
        )
        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "id": str(row[0]),
                    "timestamp": str(row[1]),
                    "agent_id": str(row[2]),
                    "session_id": str(row[3]),
                    "event_type": str(row[4]),
                    "tool_name": str(row[5]),
                    "error_message": str(row[6]),
                    "provenance": str(row[7]),
                    "retention_class": str(row[8]),
                    "created_at": str(row[9]),
                }
            )
        return results

    def list_evidence(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    def list_episodes(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    def list_hypotheses(self, *args: Any, **kwargs: Any) -> list[Any]:
        return list(self.v2_store.list_hypotheses())

    def list_insights(self, *args: Any, **kwargs: Any) -> list[Any]:
        return list(self.v2_store.list_confirmed_insights())

    def prune(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def close(self) -> None:
        pass

    # Reject direct writes to compatibility layer
    def record_slice(self, *args: Any, **kwargs: Any) -> None:
        raise sqlite3.OperationalError("cannot modify legacy_slices_view because it is a view")

    def record_event(self, *args: Any, **kwargs: Any) -> bool:
        raise sqlite3.OperationalError("cannot modify legacy_events_view because it is a view")

    def save_hypothesis(self, *args: Any, **kwargs: Any) -> None:
        raise sqlite3.OperationalError("cannot modify legacy hypotheses via compatibility view")

    def save_insight(self, *args: Any, **kwargs: Any) -> None:
        raise sqlite3.OperationalError("cannot modify legacy insights via compatibility view")


class V2EventStoreAdapter:
    """Directs AgentEvent from LocalEventBus to V2 RawEvidenceWriteService."""

    def __init__(self, write_service: Any) -> None:
        self._service = write_service

    def record_event(self, event: Any) -> bool:
        from src.memory.v2.write_service import WriteEventCommand

        event_type_str = (
            event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        )
        cmd = WriteEventCommand(
            agent_id=str(event.agent_id),
            session_id=str(event.session_id),
            event_type=event_type_str,
            occurred_at=str(event.timestamp) if hasattr(event, "timestamp") else None,
            tool_name=str(getattr(event, "tool_name", "") or ""),
            error_category=str(getattr(event, "error_message", "") or "")[:100],
            retention_class="transient",
            event_id=str(getattr(event, "id", None) or ""),
        )
        res = self._service.write_event(cmd)
        return bool(res.was_persisted)
