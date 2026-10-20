"""ChronicleStoreV2: V2.1 SQLite storage layer with typed repository primitives.

Part of Coeva Long-Term Memory V2.1 Stage 1 (WP-1).
Features:
- Explicit SQLite connection ownership (PRAGMA foreign_keys=ON, WAL mode)
- No cross-thread connection reuse (check_same_thread=True, fail-closed)
- Explicit atomic transaction context manager
- Typed CRUD primitives for 20 canonical memory entities
- Schema contract validation and schema drift detection
- Isolation from production V1 database (for test/scratch/shadow DBs)
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.memory.v2.consolidation_queue import ConsolidationJob, ConsolidationQueue

from datetime import UTC

from src.memory.v2.entities import (
    CalibrationEventEntity,
    ChapterEpisodeLinkEntity,
    ChapterInsightLinkEntity,
    ChapterMetadataEntity,
    ChapterSliceLinkEntity,
    ConfirmedInsightEntity,
    ConfirmedInsightStatus,
    EpisodeEntity,
    EpisodeEventLinkEntity,
    EpisodeSliceLinkEntity,
    EventSkeletonEntity,
    EvidenceReinforcementEntity,
    HypothesisEntity,
    HypothesisObservationLinkEntity,
    HypothesisStatus,
    ObservationEntity,
    ObservationEpisodeLinkEntity,
    ObservationEventLinkEntity,
    ObservationMemoryLinkEntity,
    ObservationSliceLinkEntity,
    ObservationStatus,
    RawSliceEntity,
    Scope,
    SemanticMemoryEntity,
    ValidityStatus,
)

SCHEMA_VERSION: int = 20261018

SCHEMA_SQL_PATH = Path(__file__).parent / "schema.sql"

CANONICAL_TABLES: tuple[str, ...] = (
    "raw_slices",
    "event_skeletons",
    "episodes",
    "episode_slice_links",
    "episode_event_links",
    "semantic_memories",
    "evidence_reinforcements",
    "observations",
    "observation_slice_links",
    "observation_event_links",
    "observation_memory_links",
    "observation_episode_links",
    "hypotheses",
    "hypothesis_observation_links",
    "calibration_events",
    "confirmed_insights",
    "chapter_metadata",
    "chapter_slice_links",
    "chapter_episode_links",
    "chapter_insight_links",
)

TECHNICAL_METADATA_TABLES: tuple[str, ...] = (
    "_schema_migrations",
    "legacy_hypothesis_audit",
    "consolidation_jobs",
    "backfill_progress",
)


class SchemaDriftError(RuntimeError):
    """Raised when the database schema does not match the canonical V2.1 specification."""

    pass


class ChronicleStoreV2:
    """V2.1 Canonical SQLite database store with explicit repository primitives."""

    def __init__(
        self,
        db_path: Path | str = ":memory:",
        *,
        timeout: float = 5.0,
        initialize: bool = True,
    ) -> None:
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        if isinstance(self.db_path, Path) and str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Thread ownership: check_same_thread=True ensures connection is not unsafely shared
        self._conn = sqlite3.connect(
            str(self.db_path),
            timeout=timeout,
            check_same_thread=True,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        if str(self.db_path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL;")

        if initialize:
            self.initialize_schema()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """Direct connection handle for scoped internal operations."""
        return self._conn

    # ── Schema Management & Contract Validation ─────────────────────────────

    def initialize_schema(self, force: bool = False) -> None:
        """Initialize exact V2.1 schema on a new database or verify compatibility."""
        cur_version = self.get_schema_version()
        if cur_version == 0 or force:
            sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
            self._conn.executescript(sql)
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
            self._conn.commit()
        elif cur_version != SCHEMA_VERSION:
            raise SchemaDriftError(
                f"Incompatible database schema version {cur_version}; expected {SCHEMA_VERSION}."
            )

    def get_schema_version(self) -> int:
        """Return the current user_version pragma value."""
        row = self._conn.execute("PRAGMA user_version;").fetchone()
        return int(row[0]) if row else 0

    def validate_schema_contract(self) -> dict[str, Any]:
        """Validate that all 20 canonical tables and foreign keys conform to V2.1.

        Raises:
            SchemaDriftError: If any canonical table is missing or FK violations exist.
        """
        # 1. Version check
        cur_ver = self.get_schema_version()
        if cur_ver != SCHEMA_VERSION:
            raise SchemaDriftError(
                f"Schema version drift: found {cur_ver}, expected {SCHEMA_VERSION}"
            )

        # 2. Required tables check
        existing_tables = set(
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        )
        missing_canonical = [t for t in CANONICAL_TABLES if t not in existing_tables]
        if missing_canonical:
            raise SchemaDriftError(f"Missing canonical tables: {missing_canonical}")

        missing_tech = [t for t in TECHNICAL_METADATA_TABLES if t not in existing_tables]
        if missing_tech:
            raise SchemaDriftError(f"Missing technical metadata tables: {missing_tech}")

        # 3. Foreign key integrity check
        fk_violations = self._conn.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_violations:
            raise SchemaDriftError(f"Foreign key integrity violations detected: {fk_violations}")

        return {
            "status": "VALID",
            "schema_version": cur_ver,
            "canonical_table_count": len(CANONICAL_TABLES),
            "technical_table_count": len(TECHNICAL_METADATA_TABLES),
            "foreign_key_violations": 0,
        }

    # ── Transaction Context Manager ──────────────────────────────────────────

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        """Explicit atomic transaction scope: commits on exit, rollbacks on error."""
        cursor = self._conn.cursor()
        if not self._conn.in_transaction:
            cursor.execute("BEGIN;")
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cursor.close()

    # ── Repository: Raw Slices (Entity 1) ───────────────────────────────────

    def insert_raw_slice(self, item: RawSliceEntity) -> None:
        """Insert a canonical raw slice record."""
        self._conn.execute(
            """
            INSERT INTO raw_slices (
                slice_id, occurred_at, content, actor, source, scope, project_id,
                ingestion_dedup_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                item.slice_id,
                item.occurred_at,
                item.content,
                item.actor,
                item.source,
                item.scope,
                item.project_id,
                item.ingestion_dedup_key,
                item.created_at or item.occurred_at,
            ),
        )

    def get_raw_slice(self, slice_id: str) -> RawSliceEntity | None:
        """Fetch a single raw slice by its ID."""
        row = self._conn.execute(
            "SELECT * FROM raw_slices WHERE slice_id = ?;", (slice_id,)
        ).fetchone()
        if not row:
            return None
        return RawSliceEntity(
            slice_id=row["slice_id"],
            occurred_at=row["occurred_at"],
            content=row["content"],
            actor=row["actor"],
            source=row["source"],
            scope=row["scope"],
            project_id=row["project_id"],
            ingestion_dedup_key=row["ingestion_dedup_key"],
            created_at=row["created_at"],
        )

    def get_raw_slice_by_dedup_key(self, dedup_key: str) -> RawSliceEntity | None:
        """Fetch a single raw slice by its ingestion dedup key."""
        row = self._conn.execute(
            "SELECT * FROM raw_slices WHERE ingestion_dedup_key = ?;", (dedup_key,)
        ).fetchone()
        if not row:
            return None
        return RawSliceEntity(
            slice_id=row["slice_id"],
            occurred_at=row["occurred_at"],
            content=row["content"],
            actor=row["actor"],
            source=row["source"],
            scope=row["scope"],
            project_id=row["project_id"],
            ingestion_dedup_key=row["ingestion_dedup_key"],
            created_at=row["created_at"],
        )

    def list_raw_slices(self, limit: int = 50, offset: int = 0) -> list[RawSliceEntity]:
        """List raw slices ordered newest-first."""
        rows = self._conn.execute(
            "SELECT * FROM raw_slices ORDER BY occurred_at DESC LIMIT ? OFFSET ?;",
            (limit, offset),
        ).fetchall()
        return [
            RawSliceEntity(
                slice_id=r["slice_id"],
                occurred_at=r["occurred_at"],
                content=r["content"],
                actor=r["actor"],
                source=r["source"],
                scope=r["scope"],
                project_id=r["project_id"],
                ingestion_dedup_key=r["ingestion_dedup_key"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ── Repository: Event Skeletons (Entity 2) ──────────────────────────────

    def insert_event_skeleton(self, item: EventSkeletonEntity) -> None:
        """Insert a structured telemetry event skeleton (respects privacy boundary)."""
        self._conn.execute(
            """
            INSERT INTO event_skeletons (
                event_id, occurred_at, agent_id, session_id, event_type,
                tool_name, error_category, retention_class, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                item.event_id,
                item.occurred_at,
                item.agent_id,
                item.session_id,
                item.event_type,
                item.tool_name,
                item.error_category,
                item.retention_class,
                item.created_at or item.occurred_at,
            ),
        )

    def get_event_skeleton(self, event_id: str) -> EventSkeletonEntity | None:
        """Fetch an event skeleton by ID."""
        row = self._conn.execute(
            "SELECT * FROM event_skeletons WHERE event_id = ?;", (event_id,)
        ).fetchone()
        if not row:
            return None
        return EventSkeletonEntity(
            event_id=row["event_id"],
            occurred_at=row["occurred_at"],
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            event_type=row["event_type"],
            tool_name=row["tool_name"],
            error_category=row["error_category"],
            retention_class=row["retention_class"],
            created_at=row["created_at"],
        )

    # ── Repository: Episodes & Links (Entities 3, 4, 5) ─────────────────────

    def insert_episode(self, ep: EpisodeEntity) -> None:
        """Insert an experience grouping container."""
        self._conn.execute(
            """
            INSERT INTO episodes (
                episode_id, scope, project_id, started_at, closed_at,
                title_hint, summary, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                ep.episode_id,
                ep.scope,
                ep.project_id,
                ep.started_at,
                ep.closed_at,
                ep.title_hint,
                ep.summary,
                ep.status,
                ep.created_at or ep.started_at,
            ),
        )

    def get_episode(self, episode_id: str) -> EpisodeEntity | None:
        """Fetch an episode by ID."""
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE episode_id = ?;", (episode_id,)
        ).fetchone()
        if not row:
            return None
        return EpisodeEntity(
            episode_id=row["episode_id"],
            scope=row["scope"],
            project_id=row["project_id"],
            started_at=row["started_at"],
            closed_at=row["closed_at"],
            title_hint=row["title_hint"],
            summary=row["summary"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def insert_episode_slice_link(self, link: EpisodeSliceLinkEntity) -> None:
        """Link an episode to a raw slice."""
        self._conn.execute(
            """
            INSERT INTO episode_slice_links (episode_id, slice_id, curation_source, linked_at)
            VALUES (?, ?, ?, ?);
            """,
            (link.episode_id, link.slice_id, link.curation_source, link.linked_at),
        )

    def insert_episode_event_link(self, link: EpisodeEventLinkEntity) -> None:
        """Link an episode to an event skeleton."""
        self._conn.execute(
            """
            INSERT INTO episode_event_links (episode_id, event_id, curation_source, linked_at)
            VALUES (?, ?, ?, ?);
            """,
            (link.episode_id, link.event_id, link.curation_source, link.linked_at),
        )

    # ── Repository: Semantic Memories & Reinforcements (Entities 6, 7) ──────

    def insert_semantic_memory(self, mem: SemanticMemoryEntity) -> None:
        """Insert a derived semantic memory item."""
        self._conn.execute(
            """
            INSERT INTO semantic_memories (
                memory_id, category, statement, authority_class, scope, project_id,
                source_slice_id, source_event_id, source_episode_id, valid_from, invalidated_at,
                superseded_by, validity_status, expression_policy, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                mem.memory_id,
                mem.category,
                mem.statement,
                mem.authority_class,
                mem.scope,
                mem.project_id,
                mem.source_slice_id,
                mem.source_event_id,
                mem.source_episode_id,
                mem.valid_from,
                mem.invalidated_at,
                mem.superseded_by,
                mem.validity_status,
                mem.expression_policy,
                mem.created_at or mem.valid_from,
            ),
        )

    def get_semantic_memory(self, memory_id: str) -> SemanticMemoryEntity | None:
        """Fetch a semantic memory by ID."""
        row = self._conn.execute(
            "SELECT * FROM semantic_memories WHERE memory_id = ?;", (memory_id,)
        ).fetchone()
        if not row:
            return None
        return SemanticMemoryEntity(
            memory_id=row["memory_id"],
            category=row["category"],
            statement=row["statement"],
            authority_class=row["authority_class"],
            scope=row["scope"],
            project_id=row["project_id"],
            source_slice_id=row["source_slice_id"],
            source_event_id=row["source_event_id"],
            source_episode_id=row["source_episode_id"],
            valid_from=row["valid_from"],
            invalidated_at=row["invalidated_at"],
            superseded_by=row["superseded_by"],
            validity_status=row["validity_status"],
            expression_policy=row["expression_policy"],
            created_at=row["created_at"],
        )

    def update_semantic_memory_superseded(
        self,
        memory_id: str,
        invalidated_at: str,
        superseded_by: str,
    ) -> None:
        """Update a semantic memory to superseded status with audit tracking."""
        self._conn.execute(
            """
            UPDATE semantic_memories
               SET validity_status = 'superseded',
                   invalidated_at = ?,
                   superseded_by = ?
             WHERE memory_id = ?;
            """,
            (invalidated_at, superseded_by, memory_id),
        )

    def update_semantic_memory_status(
        self,
        memory_id: str,
        validity_status: ValidityStatus,
    ) -> None:
        """Update validity status of a semantic memory (e.g. to ambiguous or invalidated)."""
        self._conn.execute(
            "UPDATE semantic_memories SET validity_status = ? WHERE memory_id = ?;",
            (validity_status, memory_id),
        )

    def insert_evidence_reinforcement(self, item: EvidenceReinforcementEntity) -> None:
        """Record an independent evidence confirmation."""
        self._conn.execute(
            """
            INSERT INTO evidence_reinforcements (
                reinforcement_id, memory_id, slice_id, event_id,
                independence_fingerprint, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                item.reinforcement_id,
                item.memory_id,
                item.slice_id,
                item.event_id,
                item.independence_fingerprint,
                item.occurred_at,
            ),
        )

    def get_memories_by_source_slice(self, slice_id: str) -> list[SemanticMemoryEntity]:
        """Reverse-traversal: find all semantic memories derived directly from a raw slice."""
        rows = self._conn.execute(
            "SELECT * FROM semantic_memories WHERE source_slice_id = ?;", (slice_id,)
        ).fetchall()
        return [
            SemanticMemoryEntity(
                memory_id=row["memory_id"],
                category=row["category"],
                statement=row["statement"],
                authority_class=row["authority_class"],
                scope=row["scope"],
                project_id=row["project_id"],
                source_slice_id=row["source_slice_id"],
                source_event_id=row["source_event_id"],
                source_episode_id=row["source_episode_id"],
                valid_from=row["valid_from"],
                invalidated_at=row["invalidated_at"],
                superseded_by=row["superseded_by"],
                validity_status=row["validity_status"],
                expression_policy=row["expression_policy"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_memories_by_source_event(self, event_id: str) -> list[SemanticMemoryEntity]:
        """Reverse-traversal: find all semantic memories derived directly from an event skeleton."""
        rows = self._conn.execute(
            "SELECT * FROM semantic_memories WHERE source_event_id = ?;", (event_id,)
        ).fetchall()
        return [
            SemanticMemoryEntity(
                memory_id=row["memory_id"],
                category=row["category"],
                statement=row["statement"],
                authority_class=row["authority_class"],
                scope=row["scope"],
                project_id=row["project_id"],
                source_slice_id=row["source_slice_id"],
                source_event_id=row["source_event_id"],
                source_episode_id=row["source_episode_id"],
                valid_from=row["valid_from"],
                invalidated_at=row["invalidated_at"],
                superseded_by=row["superseded_by"],
                validity_status=row["validity_status"],
                expression_policy=row["expression_policy"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_memories_by_source_episode(self, episode_id: str) -> list[SemanticMemoryEntity]:
        """Reverse-traversal: find all semantic memories derived directly from an episode."""
        rows = self._conn.execute(
            "SELECT * FROM semantic_memories WHERE source_episode_id = ?;", (episode_id,)
        ).fetchall()
        return [
            SemanticMemoryEntity(
                memory_id=row["memory_id"],
                category=row["category"],
                statement=row["statement"],
                authority_class=row["authority_class"],
                scope=row["scope"],
                project_id=row["project_id"],
                source_slice_id=row["source_slice_id"],
                source_event_id=row["source_event_id"],
                source_episode_id=row["source_episode_id"],
                valid_from=row["valid_from"],
                invalidated_at=row["invalidated_at"],
                superseded_by=row["superseded_by"],
                validity_status=row["validity_status"],
                expression_policy=row["expression_policy"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_provenance_refs_for_memory(self, memory_id: str) -> list[dict[str, str]]:
        """Return typed provenance references (IMPL-2) for a given semantic memory."""
        mem = self.get_semantic_memory(memory_id)
        if not mem:
            return []
        refs: list[dict[str, str]] = []
        if mem.source_slice_id:
            refs.append({"kind": "slice", "id": mem.source_slice_id, "role": "primary_source"})
        if mem.source_event_id:
            refs.append({"kind": "event", "id": mem.source_event_id, "role": "primary_source"})
        if mem.source_episode_id:
            refs.append(
                {"kind": "episode", "id": mem.source_episode_id, "role": "contextual_source"}
            )
        reinf_rows = self._conn.execute(
            "SELECT slice_id, event_id FROM evidence_reinforcements WHERE memory_id = ?;",
            (memory_id,),
        ).fetchall()
        for r in reinf_rows:
            if r["slice_id"]:
                refs.append({"kind": "slice", "id": r["slice_id"], "role": "reinforcement"})
            if r["event_id"]:
                refs.append({"kind": "event", "id": r["event_id"], "role": "reinforcement"})
        return refs

    # ── Repository: Observations & Links (Entities 8 ~ 12) ──────────────────

    def insert_observation(self, obs: ObservationEntity) -> None:
        """Insert an aggregated objective belief."""
        self._conn.execute(
            """
            INSERT INTO observations (
                observation_id, scope, project_id, statement, proof_count,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                obs.observation_id,
                obs.scope,
                obs.project_id,
                obs.statement,
                obs.proof_count,
                obs.status,
                obs.created_at,
                obs.updated_at or obs.created_at,
            ),
        )

    def get_observation(self, observation_id: str) -> ObservationEntity | None:
        """Fetch an observation by ID."""
        row = self._conn.execute(
            "SELECT * FROM observations WHERE observation_id = ?;", (observation_id,)
        ).fetchone()
        if not row:
            return None
        return ObservationEntity(
            observation_id=row["observation_id"],
            scope=row["scope"],
            project_id=row["project_id"],
            statement=row["statement"],
            proof_count=row["proof_count"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def insert_observation_slice_link(self, link: ObservationSliceLinkEntity) -> None:
        """Link an observation to a raw slice."""
        self._conn.execute(
            """
            INSERT INTO observation_slice_links (observation_id, slice_id, role, linked_at)
            VALUES (?, ?, ?, ?);
            """,
            (link.observation_id, link.slice_id, link.role, link.linked_at),
        )

    def insert_observation_event_link(self, link: ObservationEventLinkEntity) -> None:
        """Link an observation to an event skeleton (Retention Pin)."""
        self._conn.execute(
            """
            INSERT INTO observation_event_links (observation_id, event_id, role, linked_at)
            VALUES (?, ?, ?, ?);
            """,
            (link.observation_id, link.event_id, link.role, link.linked_at),
        )

    def insert_observation_memory_link(self, link: ObservationMemoryLinkEntity) -> None:
        """Link an observation to a semantic memory."""
        self._conn.execute(
            """
            INSERT INTO observation_memory_links (observation_id, memory_id, role, linked_at)
            VALUES (?, ?, ?, ?);
            """,
            (link.observation_id, link.memory_id, link.role, link.linked_at),
        )

    def insert_observation_episode_link(self, link: ObservationEpisodeLinkEntity) -> None:
        """Link an observation to an episode context scope."""
        self._conn.execute(
            """
            INSERT INTO observation_episode_links (observation_id, episode_id, role, linked_at)
            VALUES (?, ?, ?, ?);
            """,
            (link.observation_id, link.episode_id, link.role, link.linked_at),
        )

    # ── Repository: Hypotheses & Calibration (Entities 13 ~ 16) ─────────────

    def insert_hypothesis(self, hyp: HypothesisEntity) -> None:
        """Insert a development hypothesis."""
        self._conn.execute(
            """
            INSERT INTO hypotheses (
                hypothesis_id, statement, lenses, confidence_class,
                status, last_calibrated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                hyp.hypothesis_id,
                hyp.statement,
                hyp.lenses,
                hyp.confidence_class,
                hyp.status,
                hyp.last_calibrated_at,
                hyp.created_at,
            ),
        )

    def get_hypothesis(self, hypothesis_id: str) -> HypothesisEntity | None:
        """Fetch a hypothesis by ID."""
        row = self._conn.execute(
            "SELECT * FROM hypotheses WHERE hypothesis_id = ?;", (hypothesis_id,)
        ).fetchone()
        if not row:
            return None
        return HypothesisEntity(
            hypothesis_id=row["hypothesis_id"],
            statement=row["statement"],
            lenses=row["lenses"],
            confidence_class=row["confidence_class"],
            status=row["status"],
            last_calibrated_at=row["last_calibrated_at"],
            created_at=row["created_at"],
        )

    def insert_hypothesis_observation_link(self, link: HypothesisObservationLinkEntity) -> None:
        """Link a hypothesis to a supporting/counter observation."""
        self._conn.execute(
            """
            INSERT INTO hypothesis_observation_links (
                hypothesis_id, observation_id, role, is_primary, linked_at
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (link.hypothesis_id, link.observation_id, link.role, link.is_primary, link.linked_at),
        )

    def insert_calibration_event(self, calib: CalibrationEventEntity) -> None:
        """Record an immutable human calibration decision."""
        self._conn.execute(
            """
            INSERT INTO calibration_events (
                calibration_id, hypothesis_id, user_action, user_note, calibrated_at
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (
                calib.calibration_id,
                calib.hypothesis_id,
                calib.user_action,
                calib.user_note,
                calib.calibrated_at,
            ),
        )

    def insert_confirmed_insight(self, insight: ConfirmedInsightEntity) -> None:
        """Insert a human-confirmed self model insight."""
        self._conn.execute(
            """
            INSERT INTO confirmed_insights (
                insight_id, source_hypothesis_id, source_calibration_id, statement,
                valid_from, invalidated_at, superseded_by, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                insight.insight_id,
                insight.source_hypothesis_id,
                insight.source_calibration_id,
                insight.statement,
                insight.valid_from,
                insight.invalidated_at,
                insight.superseded_by,
                insight.status,
                insight.created_at or insight.valid_from,
            ),
        )

    def get_confirmed_insight(self, insight_id: str) -> ConfirmedInsightEntity | None:
        """Fetch a confirmed insight by ID."""
        row = self._conn.execute(
            "SELECT * FROM confirmed_insights WHERE insight_id = ?;", (insight_id,)
        ).fetchone()
        if not row:
            return None
        return ConfirmedInsightEntity(
            insight_id=row["insight_id"],
            source_hypothesis_id=row["source_hypothesis_id"],
            source_calibration_id=row["source_calibration_id"],
            statement=row["statement"],
            valid_from=row["valid_from"],
            invalidated_at=row["invalidated_at"],
            superseded_by=row["superseded_by"],
            status=row["status"],
            created_at=row["created_at"],
        )

    # ── Repository: Chapter Metadata & Links (Entities 17 ~ 20) ─────────────

    def insert_chapter_metadata(self, chap: ChapterMetadataEntity) -> None:
        """Insert chapter metadata and privacy redaction flag."""
        self._conn.execute(
            """
            INSERT INTO chapter_metadata (
                chapter_id, title, file_path, time_span_start, time_span_end,
                needs_privacy_redaction, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                chap.chapter_id,
                chap.title,
                chap.file_path,
                chap.time_span_start,
                chap.time_span_end,
                chap.needs_privacy_redaction,
                chap.created_at,
            ),
        )

    def get_chapter_metadata(self, chapter_id: str) -> ChapterMetadataEntity | None:
        """Fetch a growth chapter's metadata record."""
        row = self._conn.execute(
            "SELECT * FROM chapter_metadata WHERE chapter_id = ?;", (chapter_id,)
        ).fetchone()
        if not row:
            return None
        return ChapterMetadataEntity(
            chapter_id=row["chapter_id"],
            title=row["title"],
            file_path=row["file_path"],
            time_span_start=row["time_span_start"],
            time_span_end=row["time_span_end"],
            needs_privacy_redaction=int(row["needs_privacy_redaction"]),
            created_at=row["created_at"],
        )

    def insert_chapter_slice_link(self, link: ChapterSliceLinkEntity) -> None:
        """Link a chapter to a referenced slice."""
        self._conn.execute(
            """
            INSERT INTO chapter_slice_links (chapter_id, slice_id, linked_at)
            VALUES (?, ?, ?);
            """,
            (link.chapter_id, link.slice_id, link.linked_at),
        )

    def insert_chapter_episode_link(self, link: ChapterEpisodeLinkEntity) -> None:
        """Link a chapter to a referenced episode."""
        self._conn.execute(
            """
            INSERT INTO chapter_episode_links (chapter_id, episode_id, linked_at)
            VALUES (?, ?, ?);
            """,
            (link.chapter_id, link.episode_id, link.linked_at),
        )

    def insert_chapter_insight_link(self, link: ChapterInsightLinkEntity) -> None:
        """Link a chapter to a confirmed insight."""
        self._conn.execute(
            """
            INSERT INTO chapter_insight_links (chapter_id, insight_id, linked_at)
            VALUES (?, ?, ?);
            """,
            (link.chapter_id, link.insight_id, link.linked_at),
        )

    # ── Typed Provenance Reverse Traversal & Query Primitives ───────────────

    def get_observations_by_source_slice(self, slice_id: str) -> list[ObservationEntity]:
        """Return all observations directly referencing a raw slice."""
        rows = self._conn.execute(
            """
            SELECT o.* FROM observation_slice_links osl
            JOIN observations o ON osl.observation_id = o.observation_id
            WHERE osl.slice_id = ?;
            """,
            (slice_id,),
        ).fetchall()
        return [
            ObservationEntity(
                observation_id=r["observation_id"],
                scope=r["scope"],
                project_id=r["project_id"],
                statement=r["statement"],
                proof_count=r["proof_count"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get_observations_by_source_event(self, event_id: str) -> list[ObservationEntity]:
        """Return all observations referencing an event skeleton."""
        rows = self._conn.execute(
            """
            SELECT o.* FROM observation_event_links oel
            JOIN observations o ON oel.observation_id = o.observation_id
            WHERE oel.event_id = ?;
            """,
            (event_id,),
        ).fetchall()
        return [
            ObservationEntity(
                observation_id=r["observation_id"],
                scope=r["scope"],
                project_id=r["project_id"],
                statement=r["statement"],
                proof_count=r["proof_count"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get_observations_by_source_memory(self, memory_id: str) -> list[ObservationEntity]:
        """Return all observations referencing a semantic memory."""
        rows = self._conn.execute(
            """
            SELECT o.* FROM observation_memory_links oml
            JOIN observations o ON oml.observation_id = o.observation_id
            WHERE oml.memory_id = ?;
            """,
            (memory_id,),
        ).fetchall()
        return [
            ObservationEntity(
                observation_id=r["observation_id"],
                scope=r["scope"],
                project_id=r["project_id"],
                statement=r["statement"],
                proof_count=r["proof_count"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get_hypotheses_by_observation(self, observation_id: str) -> list[HypothesisEntity]:
        """Return all hypotheses referencing an observation."""
        rows = self._conn.execute(
            """
            SELECT h.* FROM hypothesis_observation_links hol
            JOIN hypotheses h ON hol.hypothesis_id = h.hypothesis_id
            WHERE hol.observation_id = ?;
            """,
            (observation_id,),
        ).fetchall()
        return [
            HypothesisEntity(
                hypothesis_id=r["hypothesis_id"],
                statement=r["statement"],
                lenses=r["lenses"],
                confidence_class=r["confidence_class"],
                status=r["status"],
                last_calibrated_at=r["last_calibrated_at"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_confirmed_insights_by_hypothesis(
        self, hypothesis_id: str
    ) -> list[ConfirmedInsightEntity]:
        """Return all confirmed insights derived from a hypothesis."""
        rows = self._conn.execute(
            "SELECT * FROM confirmed_insights WHERE source_hypothesis_id = ?;",
            (hypothesis_id,),
        ).fetchall()
        return [
            ConfirmedInsightEntity(
                insight_id=r["insight_id"],
                source_hypothesis_id=r["source_hypothesis_id"],
                source_calibration_id=r["source_calibration_id"],
                statement=r["statement"],
                valid_from=r["valid_from"],
                invalidated_at=r["invalidated_at"],
                superseded_by=r["superseded_by"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_chapters_by_slice(self, slice_id: str) -> list[ChapterMetadataEntity]:
        """Return all chapters referencing a raw slice."""
        rows = self._conn.execute(
            """
            SELECT cm.* FROM chapter_slice_links csl
            JOIN chapter_metadata cm ON csl.chapter_id = cm.chapter_id
            WHERE csl.slice_id = ?;
            """,
            (slice_id,),
        ).fetchall()
        return [
            ChapterMetadataEntity(
                chapter_id=r["chapter_id"],
                title=r["title"],
                file_path=r["file_path"],
                time_span_start=r["time_span_start"],
                time_span_end=r["time_span_end"],
                needs_privacy_redaction=int(r["needs_privacy_redaction"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_chapters_by_episode(self, episode_id: str) -> list[ChapterMetadataEntity]:
        """Return all chapters referencing an episode."""
        rows = self._conn.execute(
            """
            SELECT cm.* FROM chapter_episode_links cel
            JOIN chapter_metadata cm ON cel.chapter_id = cm.chapter_id
            WHERE cel.episode_id = ?;
            """,
            (episode_id,),
        ).fetchall()
        return [
            ChapterMetadataEntity(
                chapter_id=r["chapter_id"],
                title=r["title"],
                file_path=r["file_path"],
                time_span_start=r["time_span_start"],
                time_span_end=r["time_span_end"],
                needs_privacy_redaction=int(r["needs_privacy_redaction"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_chapters_by_insight(self, insight_id: str) -> list[ChapterMetadataEntity]:
        """Return all chapters referencing a confirmed insight."""
        rows = self._conn.execute(
            """
            SELECT cm.* FROM chapter_insight_links cil
            JOIN chapter_metadata cm ON cil.chapter_id = cm.chapter_id
            WHERE cil.insight_id = ?;
            """,
            (insight_id,),
        ).fetchall()
        return [
            ChapterMetadataEntity(
                chapter_id=r["chapter_id"],
                title=r["title"],
                file_path=r["file_path"],
                time_span_start=r["time_span_start"],
                time_span_end=r["time_span_end"],
                needs_privacy_redaction=int(r["needs_privacy_redaction"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_provenance_refs_for_observation(self, observation_id: str) -> list[dict[str, str]]:
        """Return typed provenance references (IMPL-2) for an observation."""
        refs: list[dict[str, str]] = []
        # Slices
        for r in self._conn.execute(
            "SELECT slice_id, role FROM observation_slice_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall():
            refs.append({"kind": "slice", "id": r["slice_id"], "role": r["role"]})
        # Events
        for r in self._conn.execute(
            "SELECT event_id, role FROM observation_event_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall():
            refs.append({"kind": "event", "id": r["event_id"], "role": r["role"]})
        # Memories
        for r in self._conn.execute(
            "SELECT memory_id, role FROM observation_memory_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall():
            refs.append({"kind": "semantic_memory", "id": r["memory_id"], "role": r["role"]})
        # Episodes
        for r in self._conn.execute(
            "SELECT episode_id, role FROM observation_episode_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall():
            refs.append({"kind": "episode", "id": r["episode_id"], "role": r["role"]})
        return refs

    def get_provenance_refs_for_hypothesis(self, hypothesis_id: str) -> list[dict[str, str]]:
        """Return typed provenance references (IMPL-2) for a hypothesis."""
        refs: list[dict[str, str]] = []
        for r in self._conn.execute(
            "SELECT observation_id, role, is_primary FROM hypothesis_observation_links "
            "WHERE hypothesis_id = ?;",
            (hypothesis_id,),
        ).fetchall():
            role = "primary_supporting" if r["is_primary"] else r["role"]
            refs.append({"kind": "observation", "id": r["observation_id"], "role": role})
        return refs

    def get_provenance_refs_for_chapter(self, chapter_id: str) -> list[dict[str, str]]:
        """Return typed provenance references for a growth chapter."""
        refs: list[dict[str, str]] = []
        for r in self._conn.execute(
            "SELECT slice_id FROM chapter_slice_links WHERE chapter_id = ?;",
            (chapter_id,),
        ).fetchall():
            refs.append({"kind": "slice", "id": r["slice_id"], "role": "citation"})
        for r in self._conn.execute(
            "SELECT episode_id FROM chapter_episode_links WHERE chapter_id = ?;",
            (chapter_id,),
        ).fetchall():
            refs.append({"kind": "episode", "id": r["episode_id"], "role": "citation"})
        for r in self._conn.execute(
            "SELECT insight_id FROM chapter_insight_links WHERE chapter_id = ?;",
            (chapter_id,),
        ).fetchall():
            refs.append({"kind": "insight", "id": r["insight_id"], "role": "citation"})
        return refs

    def get_lifecycle_service(self) -> Any:
        """Return a LifecycleService bound to this store."""
        from src.memory.v2.lifecycle import LifecycleService

        return LifecycleService(self)

    # ── Technical Metadata: Consolidation Jobs (WP-5) ─────────────────────────

    def get_consolidation_queue(self) -> ConsolidationQueue:
        """Return a ConsolidationQueue bound to this store."""
        from src.memory.v2.consolidation_queue import ConsolidationQueue

        return ConsolidationQueue(self)

    def insert_consolidation_job(self, job: ConsolidationJob) -> None:
        """Insert a technical consolidation background job row."""
        self._conn.execute(
            """
            INSERT INTO consolidation_jobs (
                job_id, source_kind, source_id, status, retry_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                job.job_id,
                job.source_kind,
                job.source_id,
                job.status,
                job.retry_count,
                job.created_at,
                job.updated_at,
            ),
        )

    def get_consolidation_job(self, job_id: str) -> ConsolidationJob | None:
        """Fetch a consolidation job by job_id."""
        row = self._conn.execute(
            "SELECT * FROM consolidation_jobs WHERE job_id = ?;",
            (job_id,),
        ).fetchone()
        if not row:
            return None
        from src.memory.v2.consolidation_queue import ConsolidationJob

        return ConsolidationJob(
            job_id=row["job_id"],
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            status=row["status"],
            retry_count=int(row["retry_count"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_consolidation_job_by_source(
        self, source_kind: str, source_id: str
    ) -> ConsolidationJob | None:
        """Fetch a consolidation job by source identity."""
        from src.memory.v2.consolidation_queue import compute_job_id

        job_id = compute_job_id(source_kind, source_id)
        return self.get_consolidation_job(job_id)

    def list_consolidation_jobs(
        self, status: str | None = None, limit: int = 100
    ) -> list[ConsolidationJob]:
        """List consolidation jobs, optionally filtered by status."""
        from src.memory.v2.consolidation_queue import ConsolidationJob

        if status:
            rows = self._conn.execute(
                """
                SELECT job_id, source_kind, source_id, status, retry_count, created_at, updated_at
                  FROM consolidation_jobs
                 WHERE status = ?
                 ORDER BY created_at ASC
                 LIMIT ?;
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT job_id, source_kind, source_id, status, retry_count, created_at, updated_at
                  FROM consolidation_jobs
                 ORDER BY created_at ASC
                 LIMIT ?;
                """,
                (limit,),
            ).fetchall()

        return [
            ConsolidationJob(
                job_id=r["job_id"],
                source_kind=r["source_kind"],
                source_id=r["source_id"],
                status=r["status"],
                retry_count=int(r["retry_count"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # ── WP-6: Observation, Hypothesis & Calibration Query Primitives ─────────

    def list_observations(
        self,
        scope: Scope | None = None,
        project_id: str | None = None,
        status: ObservationStatus | None = None,
    ) -> list[ObservationEntity]:
        """List observations filtered by scope, project_id, or status."""
        clauses: list[str] = []
        params: list[Any] = []
        if scope is not None:
            clauses.append("scope = ?")
            params.append(scope)
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)

        sql = "SELECT * FROM observations"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC;"

        rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [
            ObservationEntity(
                observation_id=r["observation_id"],
                scope=r["scope"],
                project_id=r["project_id"],
                statement=r["statement"],
                proof_count=int(r["proof_count"]),
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def list_hypotheses(self, status: HypothesisStatus | None = None) -> list[HypothesisEntity]:
        """List hypotheses, optionally filtered by status."""
        if status is not None:
            rows = self._conn.execute(
                "SELECT * FROM hypotheses WHERE status = ? ORDER BY created_at ASC;",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM hypotheses ORDER BY created_at ASC;"
            ).fetchall()
        return [
            HypothesisEntity(
                hypothesis_id=r["hypothesis_id"],
                statement=r["statement"],
                lenses=r["lenses"],
                confidence_class=r["confidence_class"],
                status=r["status"],
                last_calibrated_at=r["last_calibrated_at"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def list_confirmed_insights(
        self, status: ConfirmedInsightStatus | None = None
    ) -> list[ConfirmedInsightEntity]:
        """List confirmed insights, optionally filtered by status."""
        if status is not None:
            rows = self._conn.execute(
                "SELECT * FROM confirmed_insights WHERE status = ? ORDER BY valid_from ASC;",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM confirmed_insights ORDER BY valid_from ASC;"
            ).fetchall()
        return [
            ConfirmedInsightEntity(
                insight_id=r["insight_id"],
                source_hypothesis_id=r["source_hypothesis_id"],
                source_calibration_id=r["source_calibration_id"],
                statement=r["statement"],
                valid_from=r["valid_from"],
                invalidated_at=r["invalidated_at"],
                superseded_by=r["superseded_by"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def list_calibration_events(
        self, hypothesis_id: str | None = None
    ) -> list[CalibrationEventEntity]:
        """List calibration events, optionally filtered by hypothesis_id."""
        if hypothesis_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM calibration_events "
                "WHERE hypothesis_id = ? ORDER BY calibrated_at ASC;",
                (hypothesis_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM calibration_events ORDER BY calibrated_at ASC;"
            ).fetchall()
        return [
            CalibrationEventEntity(
                calibration_id=r["calibration_id"],
                hypothesis_id=r["hypothesis_id"],
                user_action=r["user_action"],
                calibrated_at=r["calibrated_at"],
                user_note=r["user_note"],
            )
            for r in rows
        ]

    def get_observation_slice_links(self, observation_id: str) -> list[ObservationSliceLinkEntity]:
        """Return slice links for an observation."""
        rows = self._conn.execute(
            "SELECT * FROM observation_slice_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall()
        return [
            ObservationSliceLinkEntity(
                observation_id=r["observation_id"],
                slice_id=r["slice_id"],
                role=r["role"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def get_observation_event_links(self, observation_id: str) -> list[ObservationEventLinkEntity]:
        """Return event links for an observation."""
        rows = self._conn.execute(
            "SELECT * FROM observation_event_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall()
        return [
            ObservationEventLinkEntity(
                observation_id=r["observation_id"],
                event_id=r["event_id"],
                role=r["role"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def get_observation_memory_links(
        self, observation_id: str
    ) -> list[ObservationMemoryLinkEntity]:
        """Return semantic memory links for an observation."""
        rows = self._conn.execute(
            "SELECT * FROM observation_memory_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall()
        return [
            ObservationMemoryLinkEntity(
                observation_id=r["observation_id"],
                memory_id=r["memory_id"],
                role=r["role"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def get_observation_episode_links(
        self, observation_id: str
    ) -> list[ObservationEpisodeLinkEntity]:
        """Return episode links for an observation."""
        rows = self._conn.execute(
            "SELECT * FROM observation_episode_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall()
        return [
            ObservationEpisodeLinkEntity(
                observation_id=r["observation_id"],
                episode_id=r["episode_id"],
                role=r["role"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def get_hypothesis_observation_links(
        self, hypothesis_id: str
    ) -> list[HypothesisObservationLinkEntity]:
        """Return observation links for a hypothesis."""
        rows = self._conn.execute(
            "SELECT * FROM hypothesis_observation_links WHERE hypothesis_id = ?;",
            (hypothesis_id,),
        ).fetchall()
        return [
            HypothesisObservationLinkEntity(
                hypothesis_id=r["hypothesis_id"],
                observation_id=r["observation_id"],
                role=r["role"],
                is_primary=int(r["is_primary"]),
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def update_hypothesis_status(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        last_calibrated_at: str | None = None,
    ) -> None:
        """Update status and optionally last_calibrated_at for a hypothesis."""
        if last_calibrated_at is not None:
            self._conn.execute(
                "UPDATE hypotheses SET status = ?, last_calibrated_at = ? WHERE hypothesis_id = ?;",
                (status, last_calibrated_at, hypothesis_id),
            )
        else:
            self._conn.execute(
                "UPDATE hypotheses SET status = ? WHERE hypothesis_id = ?;",
                (status, hypothesis_id),
            )

    def update_observation_proof_count(
        self,
        observation_id: str,
        proof_count: int,
        status: ObservationStatus | None = None,
        updated_at: str = "",
    ) -> None:
        """Update proof_count and status on an observation."""
        from datetime import datetime

        ts = updated_at or datetime.now(UTC).isoformat()
        if status is not None:
            self._conn.execute(
                "UPDATE observations SET proof_count = ?, status = ?, updated_at = ? "
                "WHERE observation_id = ?;",
                (proof_count, status, ts, observation_id),
            )
        else:
            self._conn.execute(
                "UPDATE observations SET proof_count = ?, updated_at = ? WHERE observation_id = ?;",
                (proof_count, ts, observation_id),
            )
