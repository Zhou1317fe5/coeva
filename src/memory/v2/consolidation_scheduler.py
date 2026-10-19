"""Consolidation Scheduler for Memory V2.1 Lane F (WP-5).

Near-real-time debounce and batch consolidation coordinator.
Coordinates:
    durable Raw Evidence
    -> durable technical queue metadata (consolidation_jobs)
    -> debounce / batch scheduler
    -> Admission
    -> Candidate Extraction
    -> WP-4 Deterministic Reconciliation
    -> semantic result

Key Invariants:
- Thread Ownership: Worker thread owns its own ChronicleStoreV2 connection (check_same_thread=True).
- Short Transactions: Never hold a write lock during LLM, provider calls, debouncing, or slow work.
- Debounce Semantics: Coalesces timing, never drops or merges evidence identities.
- Bounded Retry: Bounded retry count, no infinite hot loops on provider failure.
- Fail-Closed: Failures do not falsely mark jobs completed and leave zero dirty writes.
- Deterministic Idempotency: Replay safe, never inflates proof_count.
- Metadata Isolation: Queue metadata never becomes memory evidence or chapter provenance (I-S06).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.memory.v2.admission import AdmissionFilter
from src.memory.v2.candidate_extraction import CandidateExtractor
from src.memory.v2.consolidation_queue import (
    ConsolidationJob,
    ConsolidationQueue,
    JobStatus,
)
from src.memory.v2.proposals import ConsolidationProposal
from src.memory.v2.reconciliation import (
    ReconciliationEngine,
    ReconciliationResult,
)
from src.memory.v2.store import ChronicleStoreV2


@dataclass(frozen=True)
class SchedulerConfig:
    """Configuration options for ConsolidationScheduler."""

    debounce_delay_ms: float = 50.0
    max_batch_size: int = 10
    max_retries: int = 3
    poll_interval_ms: float = 100.0
    reclaim_on_start: bool = True
    abandoned_timeout_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JobResult:
    """Structured outcome of executing a single consolidation job."""

    job_id: str
    source_kind: str
    source_id: str
    status: JobStatus
    reconciliation_results: list[ReconciliationResult] = field(default_factory=list)
    retry_count: int = 0
    error: str | None = None
    scheduler_latency_ms: float = 0.0
    extraction_latency_ms: float = 0.0
    reconciliation_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConsolidationScheduler:
    """Near-real-time background consolidation scheduler and debounce processor."""

    def __init__(
        self,
        store: ChronicleStoreV2 | None = None,
        *,
        db_path: Path | str | None = None,
        store_factory: Callable[[], ChronicleStoreV2] | None = None,
        config: SchedulerConfig | None = None,
        candidate_extractor: CandidateExtractor | None = None,
        admission_filter: AdmissionFilter | None = None,
        reconciliation_engine: ReconciliationEngine | None = None,
        time_provider: Callable[[], float] | None = None,
        sleep_provider: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or SchedulerConfig()
        self._db_path = db_path or (store.db_path if store else None)
        self._store_factory = store_factory
        self._get_time = time_provider or time.perf_counter
        self._sleep = sleep_provider or time.sleep

        # Extractor and Admission can be shared across threads (read-only / stateless)
        self.admission_filter = admission_filter or AdmissionFilter()
        self.extractor = candidate_extractor or CandidateExtractor(
            admission_filter=self.admission_filter,
        )

        # Main / caller-thread store & engine (used for synchronous step() calls)
        self._sync_store = store
        self._sync_queue = ConsolidationQueue(store) if store else None
        self._sync_engine: ReconciliationEngine | None
        if reconciliation_engine is not None:
            self._sync_engine = reconciliation_engine
        elif store is not None:
            self._sync_engine = ReconciliationEngine(store, candidate_extractor=self.extractor)
        else:
            self._sync_engine = None

        # Debounce state
        self._last_enqueue_time: float = 0.0
        self._debounce_lock = threading.Lock()

        # Background worker thread state
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._worker_running = False

    @property
    def is_running(self) -> bool:
        """Return True if background worker thread is active."""
        return self._worker_running and (self._thread is not None and self._thread.is_alive())

    def notify(self) -> None:
        """Notify the scheduler that new durable raw evidence was enqueued."""
        with self._debounce_lock:
            self._last_enqueue_time = self._get_time()
        self._wake_event.set()

    # ── Job Processing Core (Thread-Safe / Context Isolated) ─────────────────

    def process_job(
        self,
        job: ConsolidationJob,
        *,
        store: ChronicleStoreV2,
        queue: ConsolidationQueue,
        engine: ReconciliationEngine,
        now_ts: str | None = None,
    ) -> JobResult:
        """Process a single claimed consolidation job outside write transactions.

        Steps:
        1. Read raw evidence from store.
        2. Extract candidate proposals via Admission + CandidateExtractor.
        3. Reconcile proposal via WP-4 ReconciliationEngine.
        4. Update job status to completed or pending (retry) / failed.
        """
        t0 = self._get_time()
        extraction_latency = 0.0
        recon_latency = 0.0

        # Step 1: Re-read durable raw evidence & check crash recovery replay
        if job.source_kind == "slice":
            # Crash recovery check: did this slice already commit a memory or reinforcement?
            existing_mem = store.connection.execute(
                """
                SELECT memory_id FROM semantic_memories
                 WHERE validity_status = 'active' AND source_slice_id = ?;
                """,
                (job.source_id,),
            ).fetchone()
            if existing_mem:
                queue.mark_completed(job.job_id, now_ts=now_ts)
                sched_lat = (self._get_time() - t0) * 1000.0
                return JobResult(
                    job_id=job.job_id,
                    source_kind=job.source_kind,
                    source_id=job.source_id,
                    status="completed",
                    reconciliation_results=[],
                    retry_count=job.retry_count,
                    error=None,
                    scheduler_latency_ms=sched_lat,
                )

            existing_reinf = store.connection.execute(
                "SELECT reinforcement_id FROM evidence_reinforcements WHERE slice_id = ?;",
                (job.source_id,),
            ).fetchone()
            if existing_reinf:
                queue.mark_completed(job.job_id, now_ts=now_ts)
                sched_lat = (self._get_time() - t0) * 1000.0
                return JobResult(
                    job_id=job.job_id,
                    source_kind=job.source_kind,
                    source_id=job.source_id,
                    status="completed",
                    reconciliation_results=[],
                    retry_count=job.retry_count,
                    error=None,
                    scheduler_latency_ms=sched_lat,
                )

            slice_entity = store.get_raw_slice(job.source_id)
            if not slice_entity:
                new_status = queue.mark_failed(
                    job.job_id,
                    retry=False,
                    max_retries=self.config.max_retries,
                    now_ts=now_ts,
                )
                sched_lat = (self._get_time() - t0) * 1000.0
                return JobResult(
                    job_id=job.job_id,
                    source_kind=job.source_kind,
                    source_id=job.source_id,
                    status=new_status,
                    error=f"Raw slice '{job.source_id}' not found in database.",
                    scheduler_latency_ms=sched_lat,
                )
            # Step 2: Admission & Candidate Extraction
            t_ext0 = self._get_time()
            try:
                proposal = self.extractor.extract_from_slice(slice_entity)
            except Exception as exc:
                extraction_latency = (self._get_time() - t_ext0) * 1000.0
                new_status = queue.mark_failed(
                    job.job_id,
                    retry=True,
                    max_retries=self.config.max_retries,
                    now_ts=now_ts,
                )
                sched_lat = (self._get_time() - t0) * 1000.0 - extraction_latency
                return JobResult(
                    job_id=job.job_id,
                    source_kind=job.source_kind,
                    source_id=job.source_id,
                    status=new_status,
                    retry_count=job.retry_count + 1,
                    error=f"Candidate extraction failed: {exc!s}",
                    scheduler_latency_ms=max(0.0, sched_lat),
                    extraction_latency_ms=extraction_latency,
                )
            extraction_latency = (self._get_time() - t_ext0) * 1000.0

        elif job.source_kind == "event":
            existing_mem = store.connection.execute(
                """
                SELECT memory_id FROM semantic_memories
                 WHERE validity_status = 'active' AND source_event_id = ?;
                """,
                (job.source_id,),
            ).fetchone()
            if existing_mem:
                queue.mark_completed(job.job_id, now_ts=now_ts)
                sched_lat = (self._get_time() - t0) * 1000.0
                return JobResult(
                    job_id=job.job_id,
                    source_kind=job.source_kind,
                    source_id=job.source_id,
                    status="completed",
                    reconciliation_results=[],
                    retry_count=job.retry_count,
                    error=None,
                    scheduler_latency_ms=sched_lat,
                )
            existing_reinf = store.connection.execute(
                "SELECT reinforcement_id FROM evidence_reinforcements WHERE event_id = ?;",
                (job.source_id,),
            ).fetchone()
            if existing_reinf:
                queue.mark_completed(job.job_id, now_ts=now_ts)
                sched_lat = (self._get_time() - t0) * 1000.0
                return JobResult(
                    job_id=job.job_id,
                    source_kind=job.source_kind,
                    source_id=job.source_id,
                    status="completed",
                    reconciliation_results=[],
                    retry_count=job.retry_count,
                    error=None,
                    scheduler_latency_ms=sched_lat,
                )
            event_entity = store.get_event_skeleton(job.source_id)
            if not event_entity:
                new_status = queue.mark_failed(
                    job.job_id,
                    retry=False,
                    max_retries=self.config.max_retries,
                    now_ts=now_ts,
                )
                sched_lat = (self._get_time() - t0) * 1000.0
                return JobResult(
                    job_id=job.job_id,
                    source_kind=job.source_kind,
                    source_id=job.source_id,
                    status=new_status,
                    error=f"Event skeleton '{job.source_id}' not found in database.",
                    scheduler_latency_ms=sched_lat,
                )

            t_ext0 = self._get_time()
            admission = self.admission_filter.evaluate_event(event_entity)
            proposal = ConsolidationProposal(
                proposal_id=f"prop_{uuid.uuid4().hex[:12]}",
                admission=admission,
                proposed_claims=[],
                source_id=event_entity.event_id,
                source_type="event",
                created_at=event_entity.occurred_at,
            )
            extraction_latency = (self._get_time() - t_ext0) * 1000.0

        else:
            new_status = queue.mark_failed(
                job.job_id,
                retry=False,
                max_retries=self.config.max_retries,
                now_ts=now_ts,
            )
            sched_lat = (self._get_time() - t0) * 1000.0
            return JobResult(
                job_id=job.job_id,
                source_kind=job.source_kind,
                source_id=job.source_id,
                status=new_status,
                error=f"Unsupported source_kind '{job.source_kind}'.",
                scheduler_latency_ms=sched_lat,
            )

        # Check for provider failure / DEFER
        if (
            proposal.admission.decision == "DEFER"
            and proposal.admission.rejection_category == "provider_failure"
        ):
            new_status = queue.mark_failed(
                job.job_id,
                retry=True,
                max_retries=self.config.max_retries,
                now_ts=now_ts,
            )
            sched_lat = (self._get_time() - t0) * 1000.0 - extraction_latency
            return JobResult(
                job_id=job.job_id,
                source_kind=job.source_kind,
                source_id=job.source_id,
                status=new_status,
                retry_count=job.retry_count + 1,
                error=proposal.admission.rationale,
                scheduler_latency_ms=max(0.0, sched_lat),
                extraction_latency_ms=extraction_latency,
            )

        # Step 3: WP-4 Deterministic Reconciliation
        ctx: dict[str, Any] = {}
        if job.source_kind == "slice" and slice_entity is not None:
            stmt_match = store.connection.execute(
                """
                SELECT memory_id FROM semantic_memories
                 WHERE validity_status = 'active' AND statement = ?;
                """,
                (slice_entity.content.strip(),),
            ).fetchone()
            if stmt_match:
                ctx["target_existing_memory"] = stmt_match["memory_id"]

        t_rec0 = self._get_time()
        try:
            recon_results = engine.reconcile_proposal(proposal, context=ctx)
        except Exception as exc:
            recon_latency = (self._get_time() - t_rec0) * 1000.0
            new_status = queue.mark_failed(
                job.job_id,
                retry=True,
                max_retries=self.config.max_retries,
                now_ts=now_ts,
            )
            sched_lat = (self._get_time() - t0) * 1000.0 - extraction_latency - recon_latency
            return JobResult(
                job_id=job.job_id,
                source_kind=job.source_kind,
                source_id=job.source_id,
                status=new_status,
                retry_count=job.retry_count + 1,
                error=f"Reconciliation engine raised unexpected exception: {exc!s}",
                scheduler_latency_ms=max(0.0, sched_lat),
                extraction_latency_ms=extraction_latency,
                reconciliation_latency_ms=recon_latency,
            )
        recon_latency = (self._get_time() - t_rec0) * 1000.0

        # Verify WP-4 results
        has_reconciliation_failure = any(not r.success for r in recon_results)
        if has_reconciliation_failure:
            failed_errors = [r.error for r in recon_results if not r.success and r.error]
            error_msg = "; ".join(failed_errors) or "Reconciliation failed."
            new_status = queue.mark_failed(
                job.job_id,
                retry=True,
                max_retries=self.config.max_retries,
                now_ts=now_ts,
            )
            sched_lat = (self._get_time() - t0) * 1000.0 - extraction_latency - recon_latency
            return JobResult(
                job_id=job.job_id,
                source_kind=job.source_kind,
                source_id=job.source_id,
                status=new_status,
                reconciliation_results=recon_results,
                retry_count=job.retry_count + 1,
                error=error_msg,
                scheduler_latency_ms=max(0.0, sched_lat),
                extraction_latency_ms=extraction_latency,
                reconciliation_latency_ms=recon_latency,
            )

        # Step 4: Short transaction mark completed
        queue.mark_completed(job.job_id, now_ts=now_ts)
        sched_lat = (self._get_time() - t0) * 1000.0 - extraction_latency - recon_latency

        return JobResult(
            job_id=job.job_id,
            source_kind=job.source_kind,
            source_id=job.source_id,
            status="completed",
            reconciliation_results=recon_results,
            retry_count=job.retry_count,
            error=None,
            scheduler_latency_ms=max(0.0, sched_lat),
            extraction_latency_ms=extraction_latency,
            reconciliation_latency_ms=recon_latency,
        )

    # ── Synchronous & Stepping Operations (Testing & Direct Control) ────────

    def step(
        self,
        *,
        force_debounce: bool = False,
        now_ts: str | None = None,
    ) -> list[JobResult]:
        """Execute one scheduler step on the caller's thread.

        If debounce delay has not elapsed since the last arrival and force_debounce
        is False, returns [] without claiming jobs.
        Otherwise claims up to max_batch_size pending jobs and processes them.
        """
        if not self._sync_store or not self._sync_queue or not self._sync_engine:
            msg = "ConsolidationScheduler requires a bound store for synchronous stepping."
            raise RuntimeError(msg)

        if not force_debounce:
            with self._debounce_lock:
                last_time = self._last_enqueue_time
            if last_time > 0.0:
                elapsed_ms = (self._get_time() - last_time) * 1000.0
                if elapsed_ms < self.config.debounce_delay_ms:
                    return []

        claimed = self._sync_queue.claim_jobs(
            limit=self.config.max_batch_size,
            now_ts=now_ts,
        )
        if not claimed:
            return []

        results: list[JobResult] = []
        for job in claimed:
            res = self.process_job(
                job,
                store=self._sync_store,
                queue=self._sync_queue,
                engine=self._sync_engine,
                now_ts=now_ts,
            )
            results.append(res)
        return results

    def process_batch(
        self,
        max_jobs: int | None = None,
        *,
        now_ts: str | None = None,
    ) -> list[JobResult]:
        """Force process a batch of pending jobs immediately, bypassing debounce."""
        if not self._sync_store or not self._sync_queue or not self._sync_engine:
            msg = "ConsolidationScheduler requires a bound store for synchronous batch processing."
            raise RuntimeError(msg)

        limit = max_jobs or self.config.max_batch_size
        claimed = self._sync_queue.claim_jobs(limit=limit, now_ts=now_ts)
        results: list[JobResult] = []
        for job in claimed:
            res = self.process_job(
                job,
                store=self._sync_store,
                queue=self._sync_queue,
                engine=self._sync_engine,
                now_ts=now_ts,
            )
            results.append(res)
        return results

    def process_one(
        self,
        job_id: str | None = None,
        *,
        now_ts: str | None = None,
    ) -> JobResult | None:
        """Process a single job immediately."""
        if not self._sync_store or not self._sync_queue or not self._sync_engine:
            msg = "ConsolidationScheduler requires a bound store for synchronous processing."
            raise RuntimeError(msg)

        if job_id:
            job = self._sync_queue.get_job(job_id)
            if not job or job.status not in ("pending", "running"):
                return None
            if job.status == "pending":
                claimed = self._sync_queue.claim_jobs(limit=1, now_ts=now_ts)
                matched = [j for j in claimed if j.job_id == job_id]
                target_job = matched[0] if matched else job
            else:
                target_job = job
        else:
            claimed = self._sync_queue.claim_jobs(limit=1, now_ts=now_ts)
            if not claimed:
                return None
            target_job = claimed[0]

        return self.process_job(
            target_job,
            store=self._sync_store,
            queue=self._sync_queue,
            engine=self._sync_engine,
            now_ts=now_ts,
        )

    def reclaim_abandoned_jobs(
        self,
        *,
        timeout_seconds: float | None = None,
        now_ts: str | None = None,
    ) -> list[str]:
        """Reclaim abandoned 'running' jobs in the bound queue."""
        if not self._sync_queue:
            msg = "ConsolidationScheduler requires a bound queue for job reclamation."
            raise RuntimeError(msg)
        return self._sync_queue.reclaim_abandoned_jobs(
            timeout_seconds=timeout_seconds,
            now_ts=now_ts,
        )

    # ── Background Worker Thread Execution (Per-Worker Store Ownership) ─────

    def _open_worker_store(self) -> ChronicleStoreV2:
        """Instantiate an isolated ChronicleStoreV2 connection for the worker thread."""
        if self._store_factory:
            return self._store_factory()
        if self._db_path and str(self._db_path) != ":memory:":
            return ChronicleStoreV2(self._db_path)
        if self._sync_store and str(self._sync_store.db_path) != ":memory:":
            return ChronicleStoreV2(self._sync_store.db_path)
        msg = (
            "Cannot run background worker thread on in-memory SQLite store without store_factory. "
            "Pass an on-disk db_path or a store_factory."
        )
        raise RuntimeError(msg)

    def _worker_loop(self) -> None:
        """Main loop executed by the background scheduler worker thread."""
        worker_store: ChronicleStoreV2 | None = None
        try:
            worker_store = self._open_worker_store()
            worker_queue = ConsolidationQueue(worker_store)
            worker_engine = ReconciliationEngine(
                worker_store,
                candidate_extractor=self.extractor,
            )

            # Reclaim abandoned running jobs on startup
            if self.config.reclaim_on_start:
                worker_queue.reclaim_abandoned_jobs(
                    timeout_seconds=self.config.abandoned_timeout_seconds,
                )

            self._worker_running = True

            while not self._stop_event.is_set():
                # Check for pending work
                pending_count = worker_queue.count_jobs(status="pending")
                if pending_count > 0:
                    with self._debounce_lock:
                        if self._last_enqueue_time == 0.0:
                            self._last_enqueue_time = self._get_time()
                        last_time = self._last_enqueue_time

                    elapsed_ms = (self._get_time() - last_time) * 1000.0
                    if elapsed_ms < self.config.debounce_delay_ms:
                        remaining_sec = (self.config.debounce_delay_ms - elapsed_ms) / 1000.0
                        self._wake_event.wait(timeout=max(0.005, remaining_sec))
                        self._wake_event.clear()
                        continue

                    with self._debounce_lock:
                        self._last_enqueue_time = 0.0

                    claimed = worker_queue.claim_jobs(limit=self.config.max_batch_size)
                    for job in claimed:
                        if self._stop_event.is_set():
                            # Return job to pending so work is preserved on shutdown
                            worker_queue.reclaim_abandoned_jobs()
                            break
                        self.process_job(
                            job,
                            store=worker_store,
                            queue=worker_queue,
                            engine=worker_engine,
                        )
                else:
                    poll_sec = self.config.poll_interval_ms / 1000.0
                    self._wake_event.wait(timeout=poll_sec)
                    self._wake_event.clear()

        finally:
            self._worker_running = False
            if worker_store:
                worker_store.close()

    def start(self) -> None:
        """Start the background scheduler worker thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="ConsolidationSchedulerWorker",
            daemon=True,
        )
        self._thread.start()
        # Brief yield to let worker initialize
        self._sleep(0.01)

    def stop(self, timeout: float = 2.0) -> None:
        """Gracefully stop the background scheduler worker thread."""
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._worker_running = False
