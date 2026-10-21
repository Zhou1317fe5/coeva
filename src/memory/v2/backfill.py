"""Background Backfill Engine for Memory V2.1 (WP-12).

Post-cutover, non-blocking enhancement to backfill historical evidence into
V2 semantic structures slowly and safely without blocking foreground use.

Key Invariants & Constraints:
- Flag Guard: `memory_v2_backfill` remains strictly OFF by default (BF-11).
- Non-blocking: Low-priority worker thread, yields to foreground operations (BF-01).
- CPU Budget: Target CPU usage < 5% average while active via adaptive batch yielding (BF-13).
- Graceful Shutdown: Pauses / terminates cleanly within seconds (BF-10).
- Idempotent Restart: Resumes from durable technical progress in SQLite (BF-02).
- Zero Proof Inflation: Replay delta = 0, duplicates suppressed (BF-03).
- Strict Priority Ordering: Recent slices -> older slices -> durable events -> telemetry (BF-04).
- Admission Policy: Low-entropy telemetry, greetings, noise -> NOOP (BF-05).
- Privacy Firewall: Prompt / CoT / tool output / stacktrace strictly rejected (BF-06).
- Scope Discipline: Unknown scope remains unresolved (BF-07).
- Legacy Safety: Legacy hypotheses never auto-promoted (BF-08).
- Narrative Firewall: Chapters / narratives never treated as evidence (BF-09).
- Isolation: Worker failure leaves production runtime healthy (BF-12).
- Retrieval Stability: Foreground retrieval latency does not materially regress (BF-14).
- Canonical Semantics: Backfilled memories support canonical invalidation / deletion (BF-15).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.flags import MemoryFeatureFlags, resolve_flags
from src.memory.v2.admission import AdmissionFilter
from src.memory.v2.candidate_extraction import CandidateExtractor
from src.memory.v2.reconciliation import (
    ReconciliationEngine,
)
from src.memory.v2.store import ChronicleStoreV2

logger = logging.getLogger(__name__)

# Canonical Stages
STAGE_RECENT_SLICES = "recent_slices"
STAGE_OLDER_SLICES = "older_slices"
STAGE_DURABLE_EVENTS = "durable_events"
STAGE_TELEMETRY = "telemetry"

ALL_STAGES: tuple[str, ...] = (
    STAGE_RECENT_SLICES,
    STAGE_OLDER_SLICES,
    STAGE_DURABLE_EVENTS,
    STAGE_TELEMETRY,
)

# Forbidden Privacy Markers (BF-06)
PROHIBITED_PRIVACY_MARKERS = frozenset(
    {
        "<thought>",
        "</thought>",
        "Human:",
        "Assistant:",
        "System:",
        "Traceback (most recent call last):",
        "```",
    }
)


@dataclass(frozen=True)
class BackfillConfig:
    """Configuration options for BackgroundBackfillEngine."""

    batch_size: int = 5
    yield_sleep_seconds: float = 0.05
    adaptive_yield_sleep_seconds: float = 0.25
    poll_interval_seconds: float = 0.2
    max_items_per_run: int | None = None
    recent_slice_days: int = 30
    auto_stop_on_completion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackfillItemResult:
    """Outcome of processing an individual historical evidence item."""

    item_id: str
    source_kind: str
    stage: str
    action: str  # "NOOP", "ADD", "SUPERSEDE", "REINFORCE", "AMBIGUOUS"
    admission_decision: str
    rationale: str
    affected_memory_ids: list[str] = field(default_factory=list)
    proof_delta: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackfillBatchResult:
    """Outcome of one execution batch."""

    items_scanned: int
    items_admitted: int
    noop_count: int
    add_count: int
    supersede_count: int
    reinforce_count: int
    ambiguous_count: int
    duplicate_replay_suppressions: int
    item_results: list[BackfillItemResult]
    stage: str
    stage_completed: bool
    all_completed: bool
    batch_duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackfillMetrics:
    """Accumulated performance and audit metrics for backfill operations."""

    items_scanned: int = 0
    items_admitted: int = 0
    noop_count: int = 0
    add_count: int = 0
    supersede_count: int = 0
    reinforce_count: int = 0
    ambiguous_count: int = 0
    duplicate_replay_suppressions: int = 0
    cpu_average_pct: float = 0.0
    cpu_peak_pct: float = 0.0
    foreground_write_latency_ms: float = 0.0
    retrieval_latency_before_ms: float = 0.0
    retrieval_latency_after_ms: float = 0.0
    shutdown_latency_ms: float = 0.0
    db_wal_growth_bytes: int = 0
    privacy_violations: int = 0
    scope_violations: int = 0
    proof_inflation_violations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BackfillProgressStore:
    """Thread-safe access to technical `backfill_progress` table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get_progress(self, task_name: str) -> dict[str, Any] | None:
        """Fetch current checkpoint for a given task/stage."""
        row = self.connection.execute(
            """
            SELECT task_name, last_processed_id, processed_count, status, updated_at
              FROM backfill_progress
             WHERE task_name = ?;
            """,
            (task_name,),
        ).fetchone()
        if not row:
            return None
        return {
            "task_name": row[0],
            "last_processed_id": row[1],
            "processed_count": row[2],
            "status": row[3],
            "updated_at": row[4],
        }

    def update_progress(
        self,
        task_name: str,
        last_processed_id: str | None,
        increment_count: int = 1,
        status: str = "in_progress",
        now_ts: str | None = None,
    ) -> None:
        """Upsert technical progress metadata for a task/stage."""
        ts = now_ts or datetime.now(UTC).isoformat()
        self.connection.execute(
            """
            INSERT INTO backfill_progress (
                task_name, last_processed_id, processed_count, status, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(task_name) DO UPDATE SET
                last_processed_id = excluded.last_processed_id,
                processed_count = backfill_progress.processed_count + excluded.processed_count,
                status = excluded.status,
                updated_at = excluded.updated_at;
            """,
            (task_name, last_processed_id, increment_count, status, ts),
        )
        self.connection.commit()

    def mark_completed(self, task_name: str, now_ts: str | None = None) -> None:
        """Mark a stage task as completed."""
        ts = now_ts or datetime.now(UTC).isoformat()
        self.connection.execute(
            """
            UPDATE backfill_progress
               SET status = 'completed', updated_at = ?
             WHERE task_name = ?;
            """,
            (ts, task_name),
        )
        self.connection.commit()

    def reset_progress(self, task_name: str | None = None) -> None:
        """Reset progress for test or rehearsal isolation."""
        if task_name:
            self.connection.execute(
                "DELETE FROM backfill_progress WHERE task_name = ?;", (task_name,)
            )
        else:
            self.connection.execute("DELETE FROM backfill_progress;")
        self.connection.commit()


class BackgroundBackfillEngine:
    """Low-priority, non-blocking historical evidence backfill engine."""

    def __init__(
        self,
        store: ChronicleStoreV2 | None = None,
        *,
        db_path: Path | str | None = None,
        config: BackfillConfig | None = None,
        admission_filter: AdmissionFilter | None = None,
        candidate_extractor: CandidateExtractor | None = None,
        reconciliation_engine: ReconciliationEngine | None = None,
        flags: MemoryFeatureFlags | None = None,
        foreground_detector: Callable[[], bool] | None = None,
        time_provider: Callable[[], float] | None = None,
        sleep_provider: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or BackfillConfig()
        self._db_path = db_path or (store.db_path if store else None)
        self.flags = flags if flags is not None else resolve_flags()
        self._foreground_detector = foreground_detector
        self._get_time = time_provider or time.perf_counter
        self._sleep = sleep_provider or time.sleep

        # Extractor and Admission are stateless / read-only
        self.admission_filter = admission_filter or AdmissionFilter()
        self.extractor = candidate_extractor or CandidateExtractor(
            admission_filter=self.admission_filter
        )

        # Main / caller-thread store & engine for synchronous step() execution
        self._sync_store = store
        self._sync_engine = reconciliation_engine or (
            ReconciliationEngine(store, candidate_extractor=self.extractor)
            if store is not None
            else None
        )
        self._sync_progress = BackfillProgressStore(store.connection) if store else None

        # Thread state
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._foreground_active_event = threading.Event()
        self._is_running = False
        self._metrics = BackfillMetrics()
        self._metrics_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Return True if background worker thread is active."""
        return self._is_running and (self._thread is not None and self._thread.is_alive())

    @property
    def metrics(self) -> BackfillMetrics:
        """Return a copy of accumulated metrics."""
        with self._metrics_lock:
            return BackfillMetrics(**asdict(self._metrics))

    def notify_foreground_active(self) -> None:
        """Signal that foreground activity has occurred (yields worker immediately)."""
        self._foreground_active_event.set()

    # ── Progress and Cursor Mechanics ─────────────────────────────────────────

    @staticmethod
    def _parse_cursor(cursor_str: str | None) -> tuple[str, str] | None:
        """Parse 'occurred_at|canonical_id' cursor."""
        if not cursor_str:
            return None
        parts = cursor_str.split("|", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None

    @staticmethod
    def _format_cursor(occurred_at: str, item_id: str) -> str:
        """Format 'occurred_at|canonical_id' cursor."""
        return f"{occurred_at}|{item_id}"

    def get_current_stage(self, progress: BackfillProgressStore) -> str | None:
        """Determine which stage should be processed next."""
        for stage in ALL_STAGES:
            state = progress.get_progress(stage)
            if not state or state["status"] != "completed":
                return stage
        return None

    # ── Item Fetching Core ────────────────────────────────────────────────────

    def _fetch_next_items(
        self,
        stage: str,
        cursor: tuple[str, str] | None,
        limit: int,
        store: ChronicleStoreV2,
        now_utc: datetime,
    ) -> list[tuple[str, str, str]]:
        """Fetch next batch of items for a given stage.

        Returns list of tuples: (item_id, source_kind, occurred_at).
        Ordered strictly by occurred_at DESC, item_id DESC.
        """
        cutoff_date = (now_utc - timedelta(days=self.config.recent_slice_days)).isoformat()

        if stage == STAGE_RECENT_SLICES:
            # User raw slices >= cutoff_date
            if cursor:
                c_occ, c_id = cursor
                query = """
                    SELECT slice_id, 'slice', occurred_at
                      FROM raw_slices
                     WHERE occurred_at >= ?
                       AND (occurred_at < ? OR (occurred_at = ? AND slice_id < ?))
                     ORDER BY occurred_at DESC, slice_id DESC
                     LIMIT ?;
                """
                params: tuple[Any, ...] = (cutoff_date, c_occ, c_occ, c_id, limit)
            else:
                query = """
                    SELECT slice_id, 'slice', occurred_at
                      FROM raw_slices
                     WHERE occurred_at >= ?
                     ORDER BY occurred_at DESC, slice_id DESC
                     LIMIT ?;
                """
                params = (cutoff_date, limit)

        elif stage == STAGE_OLDER_SLICES:
            # User raw slices < cutoff_date
            if cursor:
                c_occ, c_id = cursor
                query = """
                    SELECT slice_id, 'slice', occurred_at
                      FROM raw_slices
                     WHERE occurred_at < ?
                       AND (occurred_at < ? OR (occurred_at = ? AND slice_id < ?))
                     ORDER BY occurred_at DESC, slice_id DESC
                     LIMIT ?;
                """
                params = (cutoff_date, c_occ, c_occ, c_id, limit)
            else:
                query = """
                    SELECT slice_id, 'slice', occurred_at
                      FROM raw_slices
                     WHERE occurred_at < ?
                     ORDER BY occurred_at DESC, slice_id DESC
                     LIMIT ?;
                """
                params = (cutoff_date, limit)

        elif stage == STAGE_DURABLE_EVENTS:
            # Durable external agent event skeletons
            if cursor:
                c_occ, c_id = cursor
                query = """
                    SELECT event_id, 'event', occurred_at
                      FROM event_skeletons
                     WHERE retention_class = 'durable'
                       AND (occurred_at < ? OR (occurred_at = ? AND event_id < ?))
                     ORDER BY occurred_at DESC, event_id DESC
                     LIMIT ?;
                """
                params = (c_occ, c_occ, c_id, limit)
            else:
                query = """
                    SELECT event_id, 'event', occurred_at
                      FROM event_skeletons
                     WHERE retention_class = 'durable'
                     ORDER BY occurred_at DESC, event_id DESC
                     LIMIT ?;
                """
                params = (limit,)

        elif stage == STAGE_TELEMETRY:
            # Remaining transient event skeletons
            if cursor:
                c_occ, c_id = cursor
                query = """
                    SELECT event_id, 'event', occurred_at
                      FROM event_skeletons
                     WHERE retention_class = 'transient'
                       AND (occurred_at < ? OR (occurred_at = ? AND event_id < ?))
                     ORDER BY occurred_at DESC, event_id DESC
                     LIMIT ?;
                """
                params = (c_occ, c_occ, c_id, limit)
            else:
                query = """
                    SELECT event_id, 'event', occurred_at
                      FROM event_skeletons
                     WHERE retention_class = 'transient'
                     ORDER BY occurred_at DESC, event_id DESC
                     LIMIT ?;
                """
                params = (limit,)
        else:
            return []

        rows = store.connection.execute(query, params).fetchall()
        return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]

    # ── Item Processing Core ──────────────────────────────────────────────────

    def _process_item(
        self,
        item_id: str,
        source_kind: str,
        occurred_at: str,
        stage: str,
        store: ChronicleStoreV2,
        engine: ReconciliationEngine,
    ) -> BackfillItemResult:
        """Admit, extract candidates, and reconcile a single historical item."""
        # 1. Epistemic Replay & Duplicate Transport Check (BF-02 / BF-03)
        if source_kind == "slice":
            # Check if this slice already has active semantic memory or evidence reinforcement
            existing_mem = store.connection.execute(
                """
                SELECT memory_id FROM semantic_memories
                 WHERE source_slice_id = ?
                   AND validity_status IN ('active', 'superseded', 'ambiguous');
                """,
                (item_id,),
            ).fetchone()
            if existing_mem:
                return BackfillItemResult(
                    item_id=item_id,
                    source_kind=source_kind,
                    stage=stage,
                    action="NOOP",
                    admission_decision="NOOP_LONG_TERM",
                    rationale="Slice already in semantic memory (replay suppression).",
                    proof_delta=0,
                )

            existing_reinf = store.connection.execute(
                "SELECT reinforcement_id FROM evidence_reinforcements WHERE slice_id = ?;",
                (item_id,),
            ).fetchone()
            if existing_reinf:
                return BackfillItemResult(
                    item_id=item_id,
                    source_kind=source_kind,
                    stage=stage,
                    action="NOOP",
                    admission_decision="NOOP_LONG_TERM",
                    rationale="Slice already in evidence reinforcements (replay suppression).",
                    proof_delta=0,
                )

            slice_entity = store.get_raw_slice(item_id)
            if not slice_entity:
                return BackfillItemResult(
                    item_id=item_id,
                    source_kind=source_kind,
                    stage=stage,
                    action="NOOP",
                    admission_decision="NOOP_LONG_TERM",
                    rationale=f"Raw slice '{item_id}' not found in store.",
                    error="missing_entity",
                )

            # Privacy Check on raw content (BF-06)
            for marker in PROHIBITED_PRIVACY_MARKERS:
                if marker in slice_entity.content:
                    with self._metrics_lock:
                        self._metrics.privacy_violations += 1
                    return BackfillItemResult(
                        item_id=item_id,
                        source_kind=source_kind,
                        stage=stage,
                        action="NOOP",
                        admission_decision="NOOP_LONG_TERM",
                        rationale=f"Privacy violation: prohibited marker '{marker}'.",
                        error="privacy_boundary_violation",
                    )

            # 2. Admission Gate
            admission = self.admission_filter.evaluate_slice(slice_entity)
            if admission.decision != "ADMIT":
                return BackfillItemResult(
                    item_id=item_id,
                    source_kind=source_kind,
                    stage=stage,
                    action="NOOP",
                    admission_decision=admission.decision,
                    rationale=admission.rationale,
                    proof_delta=0,
                )

            # 3. Candidate Extraction
            proposal = self.extractor.extract_from_slice(slice_entity)
            if not proposal.proposed_claims:
                return BackfillItemResult(
                    item_id=item_id,
                    source_kind=source_kind,
                    stage=stage,
                    action="NOOP",
                    admission_decision=proposal.admission.decision,
                    rationale=proposal.admission.rationale,
                    proof_delta=0,
                )

            # Privacy & Scope validation on extracted claims (BF-06 / BF-07)
            for claim in proposal.proposed_claims:
                for marker in PROHIBITED_PRIVACY_MARKERS:
                    if marker in claim.statement:
                        with self._metrics_lock:
                            self._metrics.privacy_violations += 1
                        return BackfillItemResult(
                            item_id=item_id,
                            source_kind=source_kind,
                            stage=stage,
                            action="NOOP",
                            admission_decision="NOOP_LONG_TERM",
                            rationale=f"Privacy violation in extracted statement: '{marker}'.",
                            error="privacy_boundary_violation",
                        )
                # Scope discipline (BF-07)
                if not claim.project_id and claim.scope == "global":
                    with self._metrics_lock:
                        self._metrics.scope_violations += 1
                    return BackfillItemResult(
                        item_id=item_id,
                        source_kind=source_kind,
                        stage=stage,
                        action="NOOP",
                        admission_decision="NOOP_LONG_TERM",
                        rationale="Scope violation: unresolved project promoted to global.",
                        error="scope_violation",
                    )

            # 4. Reconciliation
            ctx: dict[str, Any] = {}
            stmt_match = store.connection.execute(
                """
                SELECT memory_id FROM semantic_memories
                 WHERE validity_status = 'active' AND statement = ?;
                """,
                (slice_entity.content.strip(),),
            ).fetchone()
            if stmt_match:
                ctx["target_existing_memory"] = stmt_match["memory_id"]

            recon_results = engine.reconcile_proposal(proposal, context=ctx)
            if not recon_results:
                return BackfillItemResult(
                    item_id=item_id,
                    source_kind=source_kind,
                    stage=stage,
                    action="NOOP",
                    admission_decision=admission.decision,
                    rationale="Reconciliation yielded zero actions.",
                    proof_delta=0,
                )

            first_res = recon_results[0]
            affected_ids = [m for r in recon_results for m in r.affected_memory_ids]
            proof_delta_sum = sum(r.proof_delta for r in recon_results)

            return BackfillItemResult(
                item_id=item_id,
                source_kind=source_kind,
                stage=stage,
                action=first_res.action,
                admission_decision="ADMIT",
                rationale=first_res.plan.rationale,
                affected_memory_ids=affected_ids,
                proof_delta=proof_delta_sum,
                error=first_res.error if not first_res.success else None,
            )

        elif source_kind == "event":
            # External agent telemetry (BF-05)
            event_entity = store.get_event_skeleton(item_id)
            if not event_entity:
                return BackfillItemResult(
                    item_id=item_id,
                    source_kind=source_kind,
                    stage=stage,
                    action="NOOP",
                    admission_decision="NOOP_LONG_TERM",
                    rationale=f"Event skeleton '{item_id}' not found.",
                    error="missing_entity",
                )

            admission = self.admission_filter.evaluate_event(event_entity)
            return BackfillItemResult(
                item_id=item_id,
                source_kind=source_kind,
                stage=stage,
                action="NOOP",
                admission_decision=admission.decision,
                rationale=admission.rationale,
                proof_delta=0,
            )

        return BackfillItemResult(
            item_id=item_id,
            source_kind=source_kind,
            stage=stage,
            action="NOOP",
            admission_decision="NOOP_LONG_TERM",
            rationale=f"Unknown source kind '{source_kind}'.",
            error="unknown_source_kind",
        )

    # ── Step & Batch Execution (Synchronous / Bounded) ────────────────────────

    def step(
        self,
        max_items: int | None = None,
        *,
        store: ChronicleStoreV2 | None = None,
        engine: ReconciliationEngine | None = None,
        progress_store: BackfillProgressStore | None = None,
        now_ts: datetime | None = None,
    ) -> BackfillBatchResult:
        """Execute one bounded batch of backfill work.

        Deterministic, bounded, and safe for canary and unit tests.
        """
        # Flag guard: if flag is OFF, do zero work (BF-11)
        if not self.flags.memory_v2_backfill:
            return BackfillBatchResult(
                items_scanned=0,
                items_admitted=0,
                noop_count=0,
                add_count=0,
                supersede_count=0,
                reinforce_count=0,
                ambiguous_count=0,
                duplicate_replay_suppressions=0,
                item_results=[],
                stage="",
                stage_completed=False,
                all_completed=True,
                batch_duration_ms=0.0,
            )

        t0 = self._get_time()
        active_store = store or self._sync_store
        active_engine = engine or self._sync_engine
        active_progress = progress_store or self._sync_progress

        if active_store is None or active_engine is None or active_progress is None:
            raise ValueError(
                "BackgroundBackfillEngine requires an initialized ChronicleStoreV2, "
                "ReconciliationEngine, and BackfillProgressStore for step() execution."
            )

        batch_limit = max_items if max_items is not None else self.config.batch_size
        now_utc = now_ts or datetime.now(UTC)

        # 1. Determine active stage
        current_stage = self.get_current_stage(active_progress)
        if current_stage is None:
            # All stages completed!
            return BackfillBatchResult(
                items_scanned=0,
                items_admitted=0,
                noop_count=0,
                add_count=0,
                supersede_count=0,
                reinforce_count=0,
                ambiguous_count=0,
                duplicate_replay_suppressions=0,
                item_results=[],
                stage="all_completed",
                stage_completed=True,
                all_completed=True,
                batch_duration_ms=(self._get_time() - t0) * 1000.0,
            )

        # 2. Read progress cursor
        state = active_progress.get_progress(current_stage)
        last_id = state["last_processed_id"] if state else None
        cursor = self._parse_cursor(last_id)

        # 3. Fetch items
        items = self._fetch_next_items(
            current_stage,
            cursor=cursor,
            limit=batch_limit,
            store=active_store,
            now_utc=now_utc,
        )

        if not items:
            # Stage completed!
            active_progress.mark_completed(current_stage, now_ts=now_utc.isoformat())
            next_stage = self.get_current_stage(active_progress)
            return BackfillBatchResult(
                items_scanned=0,
                items_admitted=0,
                noop_count=0,
                add_count=0,
                supersede_count=0,
                reinforce_count=0,
                ambiguous_count=0,
                duplicate_replay_suppressions=0,
                item_results=[],
                stage=current_stage,
                stage_completed=True,
                all_completed=(next_stage is None),
                batch_duration_ms=(self._get_time() - t0) * 1000.0,
            )

        # 4. Process items sequentially
        results: list[BackfillItemResult] = []
        scanned = 0
        admitted = 0
        noop_c = 0
        add_c = 0
        sup_c = 0
        reinf_c = 0
        amb_c = 0
        dup_c = 0

        last_item_cursor: str | None = None

        for item_id, source_kind, occurred_at in items:
            # Check for immediate foreground activity yield (BF-01)
            if self._foreground_active_event.is_set():
                break

            scanned += 1
            res = self._process_item(
                item_id=item_id,
                source_kind=source_kind,
                occurred_at=occurred_at,
                stage=current_stage,
                store=active_store,
                engine=active_engine,
            )
            results.append(res)
            last_item_cursor = self._format_cursor(occurred_at, item_id)

            if res.admission_decision == "ADMIT":
                admitted += 1
            if res.action == "NOOP":
                noop_c += 1
                if "replay" in res.rationale or "already" in res.rationale:
                    dup_c += 1
            elif res.action == "ADD":
                add_c += 1
            elif res.action == "SUPERSEDE":
                sup_c += 1
            elif res.action == "REINFORCE":
                reinf_c += 1
            elif res.action == "AMBIGUOUS":
                amb_c += 1

        # 5. Update technical progress in one short write transaction
        if last_item_cursor:
            active_progress.update_progress(
                task_name=current_stage,
                last_processed_id=last_item_cursor,
                increment_count=len(results),
                status="in_progress",
                now_ts=now_utc.isoformat(),
            )

        # Update metrics
        with self._metrics_lock:
            self._metrics.items_scanned += scanned
            self._metrics.items_admitted += admitted
            self._metrics.noop_count += noop_c
            self._metrics.add_count += add_c
            self._metrics.supersede_count += sup_c
            self._metrics.reinforce_count += reinf_c
            self._metrics.ambiguous_count += amb_c
            self._metrics.duplicate_replay_suppressions += dup_c

        duration_ms = (self._get_time() - t0) * 1000.0

        return BackfillBatchResult(
            items_scanned=scanned,
            items_admitted=admitted,
            noop_count=noop_c,
            add_count=add_c,
            supersede_count=sup_c,
            reinforce_count=reinf_c,
            ambiguous_count=amb_c,
            duplicate_replay_suppressions=dup_c,
            item_results=results,
            stage=current_stage,
            stage_completed=False,
            all_completed=False,
            batch_duration_ms=duration_ms,
        )

    # ── Background Worker Loop (Thread Ownership & Yielding) ──────────────────

    def start(self) -> None:
        """Start low-priority background backfill worker thread."""
        if not self.flags.memory_v2_backfill:
            logger.info("memory_v2_backfill is False; worker will not start (BF-11).")
            return

        if self.is_running:
            return

        self._stop_event.clear()
        self._foreground_active_event.clear()
        self._is_running = True

        self._thread = threading.Thread(
            target=self._worker_loop,
            name="CoevaBackfillWorker",
            daemon=True,
        )
        self._thread.start()
        logger.info("BackgroundBackfillEngine worker thread started.")

    def stop(self, timeout: float = 2.0) -> float:
        """Gracefully stop background backfill worker within timeout seconds (BF-10).

        Returns shutdown latency in milliseconds.
        """
        t0 = self._get_time()
        self._stop_event.set()
        self._wake_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._is_running = False
        shutdown_latency = (self._get_time() - t0) * 1000.0
        with self._metrics_lock:
            self._metrics.shutdown_latency_ms = shutdown_latency
        logger.info("BackgroundBackfillEngine stopped in %.2f ms.", shutdown_latency)
        return shutdown_latency

    def _worker_loop(self) -> None:
        """Background worker thread run loop with dedicated connection ownership."""
        if not self._db_path:
            logger.error("No database path configured for background backfill worker.")
            self._is_running = False
            return

        # Dedicated SQLite connection ownership for worker thread (Thread Ownership Invariant)
        worker_store = ChronicleStoreV2(self._db_path)
        worker_engine = ReconciliationEngine(worker_store, candidate_extractor=self.extractor)
        worker_progress = BackfillProgressStore(worker_store.connection)

        total_processed_items = 0

        try:
            while not self._stop_event.is_set():
                # Check foreground priority yield (BF-01)
                if self._foreground_active_event.is_set() or (
                    self._foreground_detector and self._foreground_detector()
                ):
                    self._foreground_active_event.clear()
                    # Sleep longer during foreground activity
                    self._sleep(self.config.adaptive_yield_sleep_seconds)
                    continue

                # Execute one bounded batch
                try:
                    result = self.step(
                        max_items=self.config.batch_size,
                        store=worker_store,
                        engine=worker_engine,
                        progress_store=worker_progress,
                    )
                except Exception as exc:
                    # Fail-closed isolation: worker error does not kill host runtime (BF-12)
                    logger.warning("Backfill worker error in step(): %s", exc)
                    self._sleep(self.config.poll_interval_seconds)
                    continue

                total_processed_items += result.items_scanned

                # Check max items cap (used in canary runs)
                if (
                    self.config.max_items_per_run is not None
                    and total_processed_items >= self.config.max_items_per_run
                ):
                    logger.info(
                        "Backfill reached max_items_per_run cap (%d items). Stopping worker.",
                        self.config.max_items_per_run,
                    )
                    break

                if result.all_completed:
                    logger.info("All backfill stages completed. Worker idling.")
                    if self.config.auto_stop_on_completion:
                        break
                    # Wait for stop event or wake event
                    self._wake_event.wait(timeout=self.config.poll_interval_seconds * 5)
                    self._wake_event.clear()
                    continue

                # Adaptive sleep between batches to keep CPU < 5% (BF-13)
                self._sleep(self.config.yield_sleep_seconds)

        finally:
            self._is_running = False
            try:
                worker_store.close()
            except Exception:
                pass
            logger.info("BackgroundBackfillEngine worker loop exited.")
