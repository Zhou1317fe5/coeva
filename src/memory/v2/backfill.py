"""Background Backfill Engine for Memory V2.1 (WP-12).

Post-cutover, non-blocking enhancement to backfill historical evidence into
V2 semantic structures slowly and safely without blocking foreground use.

Key Invariants & Constraints:
- Schema Freeze: Uses only existing canonical schema at commit 790ed5c (backfill_progress).
- Process Isolation: Background backfill runs in an independent child process (BF-01/BF-10).
- Foreground Priority: Foreground writes & retrieval always win, backfill yields immediately.
- CPU Budget: Target CPU usage < 5% average/peak while active via adaptive batch yielding (BF-13).
- Graceful Shutdown: Pauses / terminates cleanly within seconds (BF-10).
- Idempotent Restart: Resumes from durable technical progress in SQLite (BF-02).
- Zero Proof Inflation: Replay delta = 0, duplicates suppressed (BF-03).
- Strict Priority Ordering: Recent slices -> older slices -> durable events -> telemetry (BF-04).
- Admission Policy: Low-entropy telemetry, greetings, noise -> NOOP (BF-05).
- Privacy Firewall: Prompt / CoT / tool output / stacktrace strictly rejected (BF-06).
- Scope Discipline: Unknown scope remains unresolved (BF-07).
- Legacy Safety: Legacy hypotheses never auto-promoted (BF-08).
- Narrative Firewall: Chapters / narratives never treated as evidence (BF-09).
- Isolation: Worker process crash or termination leaves companion healthy (BF-12).
- Retrieval Stability: Foreground retrieval latency does not materially regress (BF-14).
- Canonical Semantics: Backfilled memories support canonical invalidation / deletion (BF-15).
"""

from __future__ import annotations

import logging
import multiprocessing
import sqlite3
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from multiprocessing.connection import Connection
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
    """Outcome of one execution batch with full counter reconciliation."""

    items_scanned: int
    admission_rejected: int
    admission_accepted: int
    validator_noop: int
    add_count: int
    supersede_count: int
    reinforce_count: int
    ambiguous_count: int
    duplicate_replay_suppressions: int
    failed: int
    deferred: int
    item_results: list[BackfillItemResult]
    stage: str
    stage_completed: bool
    all_completed: bool
    batch_duration_ms: float

    @property
    def noop_count(self) -> int:
        """Total NOOP = admission rejected + replay suppressed + validator NOOP."""
        return self.admission_rejected + self.duplicate_replay_suppressions + self.validator_noop

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["noop_count"] = self.noop_count
        return d


@dataclass
class BackfillMetrics:
    """Accumulated performance and audit metrics for backfill operations."""

    items_scanned: int = 0
    admission_rejected: int = 0
    admission_accepted: int = 0
    validator_noop: int = 0
    add_count: int = 0
    supersede_count: int = 0
    reinforce_count: int = 0
    ambiguous_count: int = 0
    duplicate_replay_suppressions: int = 0
    failed: int = 0
    deferred: int = 0
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

    @property
    def noop_count(self) -> int:
        return self.admission_rejected + self.duplicate_replay_suppressions + self.validator_noop

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["noop_count"] = self.noop_count
        return d


class BackfillProgressStore:
    """Thread-safe and process-safe access to technical `backfill_progress` table."""

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


# ── Standalone Worker Process Function (Picklable for Windows spawn) ──────────


def _backfill_worker_process_main(
    db_path: Path,
    config: BackfillConfig,
    stop_event: Any,
    yield_event: Any,
    pause_event: Any,
    status_pipe: Connection | None,
) -> None:
    """Worker loop executing inside an independent background process (P0-2).

    Owns its own dedicated ChronicleStoreV2 connection.
    Exchanges only minimal control and diagnostic signals over IPC.
    Never transmits user content over IPC.
    """
    logger.info("Backfill worker process started (PID: %d)", multiprocessing.current_process().pid)
    worker_store = ChronicleStoreV2(db_path, timeout=10.0)
    admission_filter = AdmissionFilter()
    extractor = CandidateExtractor(admission_filter=admission_filter)
    worker_engine = ReconciliationEngine(worker_store, candidate_extractor=extractor)
    worker_progress = BackfillProgressStore(worker_store.connection)

    engine_helper = BackgroundBackfillEngine(
        store=worker_store,
        db_path=db_path,
        config=config,
        flags=MemoryFeatureFlags(
            memory_v2_storage=True,
            memory_v2_retrieval=True,
            memory_v2_consolidation=True,
            memory_v2_backfill=True,
        ),
    )

    total_processed = 0

    try:
        while not stop_event.is_set():
            # 1. Check pause state
            if pause_event.is_set():
                time.sleep(config.poll_interval_seconds)
            if pause_event.is_set():
                stop_event.wait(timeout=config.poll_interval_seconds)
                continue

            # 2. Check foreground yield signal
            if yield_event.is_set():
                yield_event.clear()
                stop_event.wait(timeout=config.adaptive_yield_sleep_seconds)
                continue

            # 3. Execute one bounded batch
            try:
                batch_res = engine_helper.step(
                    max_items=config.batch_size,
                    store=worker_store,
                    engine=worker_engine,
                    progress_store=worker_progress,
                )
            except Exception as exc:
                logger.warning("Backfill worker process batch error: %s", exc)
                time.sleep(config.poll_interval_seconds)
                continue

            total_processed += batch_res.items_scanned

            # Send minimal diagnostic heartbeat (no user content)
            if status_pipe is not None and not getattr(status_pipe, "closed", False):
                try:
                    status_pipe.send(
                        {
                            "type": "heartbeat",
                            "items_scanned": batch_res.items_scanned,
                            "admission_rejected": batch_res.admission_rejected,
                            "admission_accepted": batch_res.admission_accepted,
                            "validator_noop": batch_res.validator_noop,
                            "add_count": batch_res.add_count,
                            "supersede_count": batch_res.supersede_count,
                            "reinforce_count": batch_res.reinforce_count,
                            "ambiguous_count": batch_res.ambiguous_count,
                            "duplicate_replay_suppressed": batch_res.duplicate_replay_suppressions,
                            "failed": batch_res.failed,
                            "deferred": batch_res.deferred,
                            "all_completed": batch_res.all_completed,
                        }
                    )
                except Exception:
                    pass

            if config.max_items_per_run is not None and total_processed >= config.max_items_per_run:
                logger.info(
                    "Reached max_items_per_run (%d). Exiting process.", config.max_items_per_run
                )
                break

            if batch_res.all_completed:
                logger.info("All backfill stages completed. Worker process idling.")
                if config.auto_stop_on_completion:
                    break
                if stop_event.wait(timeout=config.poll_interval_seconds * 3):
                    break
                continue

            # Yield sleep between batches to bound CPU usage < 5%
            if stop_event.wait(timeout=config.yield_sleep_seconds):
                break

    finally:
        try:
            worker_store.close()
        except Exception:
            pass
        if status_pipe is not None:
            try:
                status_pipe.close()
            except Exception:
                pass
        logger.info("Backfill worker process exiting cleanly.")


class BackgroundBackfillEngine:
    """Low-priority historical evidence backfill engine with independent process isolation."""

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
        self._db_path = Path(db_path) if db_path else (store.db_path if store else None)
        self.flags = flags if flags is not None else resolve_flags()
        self._foreground_detector = foreground_detector
        self._get_time = time_provider or time.perf_counter
        self._sleep = sleep_provider or time.sleep

        # Extractor and Admission are stateless / read-only
        self.admission_filter = admission_filter or AdmissionFilter()
        self.extractor = candidate_extractor or CandidateExtractor(
            admission_filter=self.admission_filter
        )

        # Synchronous store & engine for direct step() execution (tests & canary)
        self._sync_store = store
        self._sync_engine = reconciliation_engine or (
            ReconciliationEngine(store, candidate_extractor=self.extractor)
            if store is not None
            else None
        )
        self._sync_progress = BackfillProgressStore(store.connection) if store else None

        # Multiprocessing process state (P0-2)
        self._process: Any = None
        self._mp_ctx = multiprocessing.get_context("spawn")
        self._stop_event = self._mp_ctx.Event()
        self._yield_event = self._mp_ctx.Event()
        self._pause_event = self._mp_ctx.Event()
        self._parent_pipe: Any = None

        self._metrics = BackfillMetrics()

    @property
    def is_running(self) -> bool:
        """Return True if background worker process is alive."""
        return self._process is not None and self._process.is_alive()

    @property
    def metrics(self) -> BackfillMetrics:
        """Return a copy of accumulated metrics."""
        return BackfillMetrics(**asdict(self._metrics))

    def notify_foreground_active(self) -> None:
        """Signal that foreground activity has occurred (yields worker process immediately)."""
        self._yield_event.set()

    def pause(self) -> None:
        """Request worker process to pause execution."""
        self._pause_event.set()

    def resume(self) -> None:
        """Resume worker process execution."""
        self._pause_event.clear()

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
        """Fetch next batch of items for a given stage ordered occurred_at DESC, item_id DESC."""
        cutoff_date = (now_utc - timedelta(days=self.config.recent_slice_days)).isoformat()

        if stage == STAGE_RECENT_SLICES:
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
        """Admit, extract candidates, and reconcile a single historical evidence item."""
        if source_kind == "slice":
            # 1. Epistemic Replay & Duplicate Transport Check (BF-02 / BF-03)
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
        """Execute one bounded batch of backfill work with strict accounting."""
        if not self.flags.memory_v2_backfill:
            return BackfillBatchResult(
                items_scanned=0,
                admission_rejected=0,
                admission_accepted=0,
                validator_noop=0,
                add_count=0,
                supersede_count=0,
                reinforce_count=0,
                ambiguous_count=0,
                duplicate_replay_suppressions=0,
                failed=0,
                deferred=0,
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
            return BackfillBatchResult(
                items_scanned=0,
                admission_rejected=0,
                admission_accepted=0,
                validator_noop=0,
                add_count=0,
                supersede_count=0,
                reinforce_count=0,
                ambiguous_count=0,
                duplicate_replay_suppressions=0,
                failed=0,
                deferred=0,
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
            active_progress.mark_completed(current_stage, now_ts=now_utc.isoformat())
            next_stage = self.get_current_stage(active_progress)
            return BackfillBatchResult(
                items_scanned=0,
                admission_rejected=0,
                admission_accepted=0,
                validator_noop=0,
                add_count=0,
                supersede_count=0,
                reinforce_count=0,
                ambiguous_count=0,
                duplicate_replay_suppressions=0,
                failed=0,
                deferred=0,
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
        rejected = 0
        v_noop = 0
        add_c = 0
        sup_c = 0
        reinf_c = 0
        amb_c = 0
        dup_c = 0
        fail_c = 0
        def_c = 0

        last_item_cursor: str | None = None

        for item_id, source_kind, occurred_at in items:
            if self._yield_event.is_set():
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

            if res.error is not None:
                fail_c += 1

            if res.admission_decision == "ADMIT":
                admitted += 1
                if res.action == "ADD":
                    add_c += 1
                elif res.action == "SUPERSEDE":
                    sup_c += 1
                elif res.action == "REINFORCE":
                    reinf_c += 1
                elif res.action == "AMBIGUOUS":
                    amb_c += 1
                elif res.action == "NOOP":
                    v_noop += 1
            elif res.admission_decision == "DEFER":
                def_c += 1
            else:
                # NOOP_LONG_TERM
                if "replay" in res.rationale or "already" in res.rationale:
                    dup_c += 1
                else:
                    rejected += 1

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
        self._metrics.items_scanned += scanned
        self._metrics.admission_rejected += rejected
        self._metrics.admission_accepted += admitted
        self._metrics.validator_noop += v_noop
        self._metrics.add_count += add_c
        self._metrics.supersede_count += sup_c
        self._metrics.reinforce_count += reinf_c
        self._metrics.ambiguous_count += amb_c
        self._metrics.duplicate_replay_suppressions += dup_c
        self._metrics.failed += fail_c
        self._metrics.deferred += def_c

        duration_ms = (self._get_time() - t0) * 1000.0

        return BackfillBatchResult(
            items_scanned=scanned,
            admission_rejected=rejected,
            admission_accepted=admitted,
            validator_noop=v_noop,
            add_count=add_c,
            supersede_count=sup_c,
            reinforce_count=reinf_c,
            ambiguous_count=amb_c,
            duplicate_replay_suppressions=dup_c,
            failed=fail_c,
            deferred=def_c,
            item_results=results,
            stage=current_stage,
            stage_completed=False,
            all_completed=False,
            batch_duration_ms=duration_ms,
        )

    # ── Independent Process Orchestration (P0-2) ───────────────────────────────

    def start(self) -> None:
        """Start low-priority background backfill in an independent child process (P0-2)."""
        if not self.flags.memory_v2_backfill:
            logger.info("memory_v2_backfill is False; worker process will not start (BF-11).")
            return

        if self.is_running:
            return

        if self._db_path is None:
            raise ValueError("BackgroundBackfillEngine requires db_path for process launch.")

        self._stop_event.clear()
        self._yield_event.clear()
        self._pause_event.clear()

        parent_conn, child_conn = self._mp_ctx.Pipe(duplex=False)
        self._parent_pipe = parent_conn

        self._process = self._mp_ctx.Process(
            target=_backfill_worker_process_main,
            args=(
                self._db_path,
                self.config,
                self._stop_event,
                self._yield_event,
                self._pause_event,
                child_conn,
            ),
            name="CoevaBackfillProcess",
            daemon=True,
        )
        self._process.start()
        # Close child handle in parent process
        child_conn.close()
        logger.info("Backfill process spawned successfully (PID: %d).", self._process.pid)

    def stop(self, timeout: float = 2.0) -> float:
        """Gracefully stop background backfill process within timeout seconds (BF-10)."""
        t0 = self._get_time()
        self._stop_event.set()

        if self._parent_pipe is not None:
            try:
                while self._parent_pipe.poll(timeout=0.05):
                    msg = self._parent_pipe.recv()
                    if isinstance(msg, dict) and msg.get("type") == "heartbeat":
                        self._metrics.items_scanned += msg.get("items_scanned", 0)
                        self._metrics.admission_rejected += msg.get("admission_rejected", 0)
                        self._metrics.admission_accepted += msg.get("admission_accepted", 0)
                        self._metrics.validator_noop += msg.get("validator_noop", 0)
                        self._metrics.add_count += msg.get("add_count", 0)
                        self._metrics.supersede_count += msg.get("supersede_count", 0)
                        self._metrics.reinforce_count += msg.get("reinforce_count", 0)
                        self._metrics.ambiguous_count += msg.get("ambiguous_count", 0)
                        self._metrics.duplicate_replay_suppressions += msg.get(
                            "duplicate_replay_suppressed", 0
                        )
                        self._metrics.failed += msg.get("failed", 0)
                        self._metrics.deferred += msg.get("deferred", 0)
            except Exception:
                pass
            try:
                self._parent_pipe.close()
            except Exception:
                pass
            self._parent_pipe = None

        if self._process is not None and self._process.is_alive():
            self._process.join(timeout=timeout)
            if self._process.is_alive():
                logger.warning("Worker process did not exit within timeout. Terminating safely.")
                self._process.terminate()
                self._process.join(timeout=1.0)
        self._process = None
        shutdown_latency = (self._get_time() - t0) * 1000.0
        self._metrics.shutdown_latency_ms = shutdown_latency
        logger.info("BackgroundBackfillEngine process stopped in %.2f ms.", shutdown_latency)
        return shutdown_latency
