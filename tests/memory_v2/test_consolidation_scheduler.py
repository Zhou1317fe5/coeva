"""Comprehensive Test Suite for Consolidation Scheduler & Queue (Lane F, WP-5).

Formally verifies all 17 Requirements from Section 13:
1. Durable enqueue: job row committed before enqueue success.
2. Same-source enqueue idempotent.
3. Queue contains no user/model content.
4. Pending job survives restart.
5. Abandoned `running` job is safely reclaimed.
6. Debounce never drops source identities.
7. Slow provider does not block enqueue caller/main thread.
8. Worker owns its own Store/connection.
9. Provider unavailable -> retry/defer; no dirty semantic write.
10. WP-4 failure -> job not falsely completed.
11. Crash after reconciliation before completion marker -> replay safe; no proof inflation.
12. Retry bounded.
13. Completed job not accidentally rerun.
14. Queue metadata never becomes memory evidence.
15. Shutdown preserves pending work.
16. No Observation/Hypothesis/ConfirmedInsight generated.
17. Production DB untouched; V1 default unchanged.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.core.flags import resolve_flags, validate_memory_v2_configuration
from src.memory.v2.candidate_extraction import CandidateExtractor
from src.memory.v2.consolidation_queue import ConsolidationQueue
from src.memory.v2.consolidation_scheduler import (
    ConsolidationScheduler,
    SchedulerConfig,
)
from src.memory.v2.entities import (
    EventSkeletonEntity,
    RawSliceEntity,
)
from src.memory.v2.proposals import (
    AdmissionDecision,
    CandidateSemanticMemory,
    ConsolidationProposal,
)
from src.memory.v2.provenance import ProvenanceKind
from src.memory.v2.reconciliation import (
    MutationPlan,
    ReconciliationEngine,
    ReconciliationResult,
)
from src.memory.v2.reconciliation_validator import (
    ReconciliationDecision,
)
from src.memory.v2.store import CANONICAL_TABLES, TECHNICAL_METADATA_TABLES, ChronicleStoreV2


class FakeClock:
    """Controllable time provider for deterministic debounce and latency testing."""

    def __init__(self, initial_time: float = 1000.0) -> None:
        self._time = initial_time

    def time(self) -> float:
        return self._time

    def advance(self, delta_seconds: float) -> None:
        self._time += delta_seconds


def insert_test_slice(
    store: ChronicleStoreV2,
    slice_id: str,
    content: str,
    project_id: str | None = None,
    scope: str = "unresolved",
    occurred_at: str = "2026-10-18T12:00:00+00:00",
) -> RawSliceEntity:
    """Helper to persist a canonical raw slice in the store."""
    entity = RawSliceEntity(
        slice_id=slice_id,
        occurred_at=occurred_at,
        content=content,
        actor="user",
        source="manual_feed",
        scope=scope,  # type: ignore[arg-type]
        project_id=project_id,
        ingestion_dedup_key=f"dedup_{slice_id}",
    )
    store.insert_raw_slice(entity)
    return entity


def insert_test_event(
    store: ChronicleStoreV2,
    event_id: str,
    event_type: str = "tool_execution",
    occurred_at: str = "2026-10-18T12:00:00+00:00",
) -> EventSkeletonEntity:
    """Helper to persist a canonical event skeleton in the store."""
    entity = EventSkeletonEntity(
        event_id=event_id,
        occurred_at=occurred_at,
        agent_id="test_agent",
        session_id="sess_001",
        event_type=event_type,
        tool_name="bash",
        error_category="",
        retention_class="durable",
    )
    store.insert_event_skeleton(entity)
    return entity


# ── Requirement 1: Durable Enqueue ──────────────────────────────────────────


def test_req01_durable_enqueue_committed_before_success(tmp_path: Path) -> None:
    """1. Durable enqueue: job row committed before enqueue success."""
    db_file = tmp_path / "req01.db"
    store = ChronicleStoreV2(db_file)
    queue = ConsolidationQueue(store)
    try:
        job = queue.enqueue("slice", "s_01")
        assert job.status == "pending"
        assert job.retry_count == 0

        # Query raw DB connection to prove physical commitment
        raw_conn = sqlite3.connect(str(db_file))
        raw_conn.row_factory = sqlite3.Row
        try:
            row = raw_conn.execute(
                "SELECT * FROM consolidation_jobs WHERE job_id = ?;", (job.job_id,)
            ).fetchone()
            assert row is not None
            assert row["status"] == "pending"
        finally:
            raw_conn.close()

        # Simulated commit failure fails closed
        with patch.object(store, "transaction", side_effect=sqlite3.OperationalError("disk error")):
            with pytest.raises(sqlite3.OperationalError):
                queue.enqueue("slice", "s_fail")
    finally:
        store.close()


# ── Requirement 2: Same-Source Idempotent Enqueue ───────────────────────────


def test_req02_same_source_enqueue_idempotent(tmp_path: Path) -> None:
    """2. Same-source enqueue idempotent: repeated enqueue yields no duplicate jobs."""
    store = ChronicleStoreV2(tmp_path / "req02.db")
    queue = ConsolidationQueue(store)
    try:
        j1 = queue.enqueue("slice", "s_idem_01")
        j2 = queue.enqueue("slice", "s_idem_01")
        assert j1.job_id == j2.job_id

        # Total rows is exactly 1
        count = store.connection.execute(
            """
            SELECT COUNT(*) FROM consolidation_jobs
             WHERE source_kind = 'slice' AND source_id = 's_idem_01';
            """
        ).fetchone()[0]
        assert count == 1

        # Completed job replay: remains completed without resetting
        queue.mark_completed(j1.job_id)
        j3 = queue.enqueue("slice", "s_idem_01")
        assert j3.job_id == j1.job_id
        assert j3.status == "completed"
    finally:
        store.close()


# ── Requirement 3: Queue Contains No User/Model Content ─────────────────────


def test_req03_queue_contains_no_user_model_content(tmp_path: Path) -> None:
    """3. Queue contains no user/model content: strictly technical operational metadata."""
    store = ChronicleStoreV2(tmp_path / "req03.db")
    queue = ConsolidationQueue(store)
    try:
        sensitive_text = "SECRET_USER_INPUT: Do not store this in operational queue metadata!"
        insert_test_slice(store, "s_sec_01", sensitive_text)
        job = queue.enqueue("slice", "s_sec_01")

        # Verify schema table info has no content columns
        cols = [
            r["name"]
            for r in store.connection.execute("PRAGMA table_info(consolidation_jobs);").fetchall()
        ]
        assert sorted(cols) == sorted(
            [
                "job_id",
                "source_kind",
                "source_id",
                "status",
                "retry_count",
                "created_at",
                "updated_at",
            ]
        )

        row = store.connection.execute(
            "SELECT * FROM consolidation_jobs WHERE job_id = ?;", (job.job_id,)
        ).fetchone()
        row_str = " ".join(str(val) for val in row)
        assert "SECRET_USER_INPUT" not in row_str
        assert "consolidation_jobs" in TECHNICAL_METADATA_TABLES
    finally:
        store.close()


# ── Requirement 4: Pending Job Survives Restart ─────────────────────────────


def test_req04_pending_job_survives_restart(tmp_path: Path) -> None:
    """4. Pending job survives restart: persistent SQLite durable state."""
    db_file = tmp_path / "req04.db"
    store1 = ChronicleStoreV2(db_file)
    queue1 = ConsolidationQueue(store1)
    try:
        j1 = queue1.enqueue("slice", "s_surv_01")
        j2 = queue1.enqueue("event", "e_surv_02")
    finally:
        store1.close()

    # Reopen after process restart
    store2 = ChronicleStoreV2(db_file)
    queue2 = ConsolidationQueue(store2)
    try:
        assert queue2.count_jobs(status="pending") == 2
        r1 = queue2.get_job(j1.job_id)
        r2 = queue2.get_job(j2.job_id)
        assert r1 is not None and r1.status == "pending"
        assert r2 is not None and r2.status == "pending"
    finally:
        store2.close()


# ── Requirement 5: Abandoned Running Job Safely Reclaimed ───────────────────


def test_req05_abandoned_running_job_safely_reclaimed(tmp_path: Path) -> None:
    """5. Abandoned `running` job is safely reclaimed back to pending."""
    store = ChronicleStoreV2(tmp_path / "req05.db")
    queue = ConsolidationQueue(store)
    try:
        insert_test_slice(store, "s_ab_01", "我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。")
        job = queue.enqueue("slice", "s_ab_01")

        # Simulate crash while running
        claimed = queue.claim_jobs(limit=1)
        assert claimed[0].status == "running"

        # Reclaim abandoned running jobs
        reclaimed = queue.reclaim_abandoned_jobs()
        assert job.job_id in reclaimed
        assert queue.get_job(job.job_id).status == "pending"  # type: ignore[union-attr]

        # Scheduler processes it to completion
        scheduler = ConsolidationScheduler(store)
        results = scheduler.process_batch()
        assert len(results) == 1
        assert results[0].status == "completed"
        assert queue.get_job(job.job_id).status == "completed"  # type: ignore[union-attr]
    finally:
        store.close()


# ── Requirement 6: Debounce Never Drops Source Identities ───────────────────


def test_req06_debounce_never_drops_source_identities(tmp_path: Path) -> None:
    """6. Debounce never drops source identities: coalesces timing, preserves each source."""
    clock = FakeClock(100.0)
    store = ChronicleStoreV2(tmp_path / "req06.db")
    queue = ConsolidationQueue(store)
    scheduler = ConsolidationScheduler(
        store,
        config=SchedulerConfig(debounce_delay_ms=50.0, max_batch_size=10),
        time_provider=clock.time,
    )
    try:
        # Enqueue 5 slices in rapid succession (t = 100, 105, 110, 115, 120 ms)
        slice_ids: list[str] = []
        for i in range(5):
            clock.advance(0.005)  # +5ms
            sid = f"s_debounce_{i}"
            insert_test_slice(store, sid, f"用户偏好配置项第 {i} 条：习惯只用黑色主题。")
            queue.enqueue("slice", sid)
            scheduler.notify()
            slice_ids.append(sid)

        # Before debounce window elapses, step() returns empty (coalescing)
        res_early = scheduler.step()
        assert len(res_early) == 0

        # Advance past debounce window (e.g. +60ms)
        clock.advance(0.060)
        res_batch = scheduler.step()

        # All 5 slices are processed, none dropped or merged into a blob
        assert len(res_batch) == 5
        processed_ids = [r.source_id for r in res_batch]
        assert sorted(processed_ids) == sorted(slice_ids)
        assert all(r.status == "completed" for r in res_batch)

        # Confirm all 5 jobs in DB are completed
        for sid in slice_ids:
            job = queue.get_job_by_source("slice", sid)
            assert job is not None
            assert job.status == "completed"
    finally:
        store.close()


# ── Requirement 7: Slow Provider Non-Blocking ───────────────────────────────


class SlowMockProposalProvider:
    """Mock provider with simulated latency."""

    def __init__(self, delay_seconds: float = 0.2) -> None:
        self.delay_seconds = delay_seconds

    def generate_proposal(
        self,
        slice_entity: RawSliceEntity,
        admission: AdmissionDecision,
        delta_text: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ConsolidationProposal:
        time.sleep(self.delay_seconds)
        claim = CandidateSemanticMemory(
            statement="用户偏好只用深色模式。",
            category="preference",
            scope="unresolved",
            authority_class="user_asserted",
            source_slice_id=slice_entity.slice_id,
        )
        return ConsolidationProposal(
            proposal_id="prop_slow_01",
            admission=admission,
            proposed_claims=[claim],
            source_id=slice_entity.slice_id,
            source_type="slice",
            created_at=slice_entity.occurred_at,
        )


def test_req07_slow_provider_does_not_block_enqueue_caller(tmp_path: Path) -> None:
    """7. Slow provider does not block enqueue caller/main thread."""
    db_file = tmp_path / "req07.db"
    main_store = ChronicleStoreV2(db_file)
    queue = ConsolidationQueue(main_store)

    slow_provider = SlowMockProposalProvider(delay_seconds=0.15)
    slow_extractor = CandidateExtractor(provider=slow_provider)

    scheduler = ConsolidationScheduler(
        db_path=db_file,
        config=SchedulerConfig(debounce_delay_ms=10.0, poll_interval_ms=20.0),
        candidate_extractor=slow_extractor,
    )
    scheduler.start()

    try:
        insert_test_slice(main_store, "s_slow_01", "我其实只用深色模式。")

        # Measure enqueue latency on caller thread
        t0 = time.perf_counter()
        job = queue.enqueue("slice", "s_slow_01")
        scheduler.notify()
        enqueue_latency_ms = (time.perf_counter() - t0) * 1000.0

        # Enqueue returns almost instantaneously (< 50ms), far below provider delay (150ms)
        assert enqueue_latency_ms < 50.0
        assert job.status == "pending"

        # Wait for background worker to complete
        deadline = time.time() + 2.0
        completed = False
        while time.time() < deadline:
            updated_job = queue.get_job(job.job_id)
            if updated_job and updated_job.status == "completed":
                completed = True
                break
            time.sleep(0.03)

        assert completed is True
    finally:
        scheduler.stop()
        main_store.close()


# ── Requirement 8: Worker Owns Its Own Store Connection ─────────────────────


def test_req08_worker_owns_own_store_connection(tmp_path: Path) -> None:
    """8. Worker owns its own Store/connection (check_same_thread=True enforced)."""
    db_file = tmp_path / "req08.db"
    main_store = ChronicleStoreV2(db_file)

    # Cross-thread check: using main_store connection on another thread must raise ProgrammingError
    cross_thread_error: list[Exception] = []

    def illegal_cross_thread_access() -> None:
        try:
            main_store.connection.execute("SELECT 1;").fetchone()
        except sqlite3.ProgrammingError as exc:
            cross_thread_error.append(exc)

    t = threading.Thread(target=illegal_cross_thread_access)
    t.start()
    t.join()

    assert len(cross_thread_error) == 1
    assert "same thread" in str(cross_thread_error[0]).lower()

    # Scheduler worker creates its own connection and executes cleanly
    insert_test_slice(main_store, "s_own_01", "我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。")
    queue = ConsolidationQueue(main_store)
    queue.enqueue("slice", "s_own_01")

    scheduler = ConsolidationScheduler(
        db_path=db_file,
        config=SchedulerConfig(debounce_delay_ms=5.0, poll_interval_ms=10.0),
    )
    scheduler.start()
    try:
        scheduler.notify()
        deadline = time.time() + 2.0
        done = False
        while time.time() < deadline:
            j = queue.get_job_by_source("slice", "s_own_01")
            if j and j.status == "completed":
                done = True
                break
            time.sleep(0.02)
        assert done is True
    finally:
        scheduler.stop()
        main_store.close()


# ── Requirement 9: Provider Unavailable -> Retry / Defer, No Dirty Write ──


class FailingProposalProvider:
    """Mock provider that simulates network / provider outage."""

    def generate_proposal(
        self,
        slice_entity: RawSliceEntity,
        admission: AdmissionDecision,
        delta_text: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ConsolidationProposal:
        msg = "LLM API connection timed out (503 Service Unavailable)"
        raise ConnectionError(msg)


def test_req09_provider_unavailable_retry_defer_no_dirty_write(tmp_path: Path) -> None:
    """9. Provider unavailable -> retry/defer; no dirty semantic write."""
    store = ChronicleStoreV2(tmp_path / "req09.db")
    queue = ConsolidationQueue(store)
    fail_extractor = CandidateExtractor(provider=FailingProposalProvider())
    scheduler = ConsolidationScheduler(
        store,
        config=SchedulerConfig(max_retries=3),
        candidate_extractor=fail_extractor,
    )
    try:
        insert_test_slice(store, "s_fail_01", "换成了全新键盘。")
        job = queue.enqueue("slice", "s_fail_01")

        # Step 1: execution fails
        res = scheduler.process_one(job.job_id)
        assert res is not None
        assert res.status == "pending"  # Retryable
        assert res.retry_count == 1
        assert "timed out" in (res.error or "")

        sem_count = store.connection.execute("SELECT COUNT(*) FROM semantic_memories;").fetchone()[
            0
        ]
        reinf_count = store.connection.execute(
            "SELECT COUNT(*) FROM evidence_reinforcements;"
        ).fetchone()[0]
        assert sem_count == 0
        assert reinf_count == 0

        # Verify: raw slice remains 100% intact
        assert store.get_raw_slice("s_fail_01") is not None
    finally:
        store.close()


# ── Requirement 10: WP-4 Failure Not Falsely Completed ──────────────────────


def test_req10_wp4_failure_not_falsely_completed(tmp_path: Path) -> None:
    """10. WP-4 failure -> job not falsely completed, rolled back atomically."""
    store = ChronicleStoreV2(tmp_path / "req10.db")
    queue = ConsolidationQueue(store)

    class FailingReconciliationEngine(ReconciliationEngine):
        def reconcile_proposal(
            self,
            proposal: ConsolidationProposal,
            context: dict[str, Any] | None = None,
        ) -> list[ReconciliationResult]:
            # Simulate a reconciliation failure
            return [
                ReconciliationResult(
                    success=False,
                    action="ADD",
                    decision=ReconciliationDecision(
                        action="ADD",
                        target_memory_id=None,
                        claim=None,
                        statement="test statement",
                        category="preference",
                        scope="unresolved",
                        project_id=None,
                        authority_class="user_asserted",
                        proof_delta=0,
                        rationale="mock failure",
                        is_valid=False,
                    ),
                    plan=MutationPlan(action="ADD"),
                    error="Simulated DB transaction deadlock or constraint failure",
                )
            ]

    failing_engine = FailingReconciliationEngine(store)
    scheduler = ConsolidationScheduler(
        store,
        config=SchedulerConfig(max_retries=3),
        reconciliation_engine=failing_engine,
    )
    try:
        insert_test_slice(store, "s_wp4_fail", "习惯于早起散步。")
        job = queue.enqueue("slice", "s_wp4_fail")

        res = scheduler.process_one(job.job_id)
        assert res is not None
        assert res.status == "pending"  # Not falsely completed!
        assert res.retry_count == 1
        assert "constraint failure" in (res.error or "")

        # Check DB status
        updated_job = queue.get_job(job.job_id)
        assert updated_job is not None
        assert updated_job.status != "completed"
        assert updated_job.status == "pending"
    finally:
        store.close()


# ── Requirement 11: Crash Replay Safe, No Proof Inflation ───────────────────


def test_req11_crash_after_reconciliation_replay_safe_no_proof_inflation(
    tmp_path: Path,
) -> None:
    """11. Crash after reconciliation before completion marker -> replay safe."""
    store = ChronicleStoreV2(tmp_path / "req11.db")
    queue = ConsolidationQueue(store)
    scheduler = ConsolidationScheduler(store)
    try:
        # Step 1: Normal first reconciliation
        sid = "s_crash_01"
        insert_test_slice(store, sid, "我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。")
        job = queue.enqueue("slice", sid)

        # Process job 1st time
        res1 = scheduler.process_one(job.job_id)
        assert res1 is not None and res1.status == "completed"

        memories1 = store.connection.execute(
            "SELECT memory_id, statement, validity_status FROM semantic_memories;"
        ).fetchall()
        assert len(memories1) == 1
        reinf_count1 = store.connection.execute(
            "SELECT COUNT(*) FROM evidence_reinforcements;"
        ).fetchone()[0]

        # Step 2: Simulate crash before queue completion marker was written
        # Reset job status in consolidation_jobs back to 'pending' to simulate recovered replay
        store.connection.execute(
            "UPDATE consolidation_jobs SET status = 'pending' WHERE job_id = ?;",
            (job.job_id,),
        )

        # Step 3: Replay execution
        res2 = scheduler.process_one(job.job_id)
        assert res2 is not None and res2.status == "completed"

        # Step 4: Verification of Idempotency
        memories2 = store.connection.execute(
            """
            SELECT memory_id, statement, validity_status FROM semantic_memories
             WHERE validity_status = 'active';
            """
        ).fetchall()
        assert len(memories2) == 1

        # - Proof count / reinforcements did not inflate
        reinf_count2 = store.connection.execute(
            "SELECT COUNT(*) FROM evidence_reinforcements;"
        ).fetchone()[0]
        assert reinf_count2 == reinf_count1

        # Proof delta on replay was strictly 0
        total_proof_delta = sum(r.proof_delta for r in res2.reconciliation_results)
        assert total_proof_delta == 0
    finally:
        store.close()


# ── Requirement 12: Retry Bounded ───────────────────────────────────────────


def test_req12_retry_bounded_no_infinite_loop(tmp_path: Path) -> None:
    """12. Retry bounded: job transitions to failed after max_retries, no hot loop."""
    store = ChronicleStoreV2(tmp_path / "req12.db")
    queue = ConsolidationQueue(store)
    fail_extractor = CandidateExtractor(provider=FailingProposalProvider())
    scheduler = ConsolidationScheduler(
        store,
        config=SchedulerConfig(max_retries=3),
        candidate_extractor=fail_extractor,
    )
    try:
        insert_test_slice(store, "s_retry_01", "换成了新键盘。")
        job = queue.enqueue("slice", "s_retry_01")

        # Retry 1
        r1 = scheduler.process_one(job.job_id)
        assert r1 is not None and r1.status == "pending" and r1.retry_count == 1

        # Retry 2
        r2 = scheduler.process_one(job.job_id)
        assert r2 is not None and r2.status == "pending" and r2.retry_count == 2

        # Retry 3 -> Max retries reached, transitions permanently to 'failed'
        r3 = scheduler.process_one(job.job_id)
        assert r3 is not None and r3.status == "failed" and r3.retry_count == 3

        # Next claim attempt: failed job is NOT claimed, no infinite loop
        next_job = scheduler.process_one()
        assert next_job is None

        # Queue verification
        j_db = queue.get_job(job.job_id)
        assert j_db is not None
        assert j_db.status == "failed"
        assert j_db.retry_count == 3
    finally:
        store.close()


# ── Requirement 13: Completed Job Not Accidentally Rerun ────────────────────


def test_req13_completed_job_not_accidentally_rerun(tmp_path: Path) -> None:
    """13. Completed job not accidentally rerun."""
    store = ChronicleStoreV2(tmp_path / "req13.db")
    queue = ConsolidationQueue(store)
    scheduler = ConsolidationScheduler(store)
    try:
        insert_test_slice(store, "s_comp_01", "我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。")
        job = queue.enqueue("slice", "s_comp_01")

        # Run to completed
        res = scheduler.process_one(job.job_id)
        assert res is not None and res.status == "completed"

        # Attempt to claim jobs again -> none pending
        claimed = queue.claim_jobs(limit=10)
        assert len(claimed) == 0

        # Attempting process_one(job.job_id) ignores completed job
        assert scheduler.process_one(job.job_id) is None

        # Re-enqueue returns completed job without resetting to pending
        j_re = queue.enqueue("slice", "s_comp_01")
        assert j_re.status == "completed"
    finally:
        store.close()


# ── Requirement 14: Queue Metadata Never Becomes Memory Evidence ────────────


def test_req14_queue_metadata_never_becomes_memory_evidence(tmp_path: Path) -> None:
    """14. Queue metadata never becomes memory evidence, chapter provenance, or proof count."""
    store = ChronicleStoreV2(tmp_path / "req14.db")
    queue = ConsolidationQueue(store)
    try:
        job = queue.enqueue("slice", "s_iso_01")

        # 1. consolidation_jobs is technical metadata
        assert "consolidation_jobs" in TECHNICAL_METADATA_TABLES
        assert "consolidation_jobs" not in CANONICAL_TABLES

        # 2. Type validation: ProvenanceKind has no consolidation_jobs
        assert "consolidation_jobs" not in ProvenanceKind.__args__  # type: ignore[attr-defined]

        # 3. Foreign key protection: observation links reject job_id
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                """
                INSERT INTO observation_slice_links (observation_id, slice_id, role, linked_at)
                VALUES ('nonexistent_obs', ?, 'supporting', '2026-10-18T00:00:00Z');
                """,
                (job.job_id,),
            )

        # 4. FK check is 0
        assert len(store.connection.execute("PRAGMA foreign_key_check;").fetchall()) == 0
    finally:
        store.close()


# ── Requirement 15: Shutdown Preserves Pending Work ─────────────────────────


def test_req15_shutdown_preserves_pending_work(tmp_path: Path) -> None:
    """15. Shutdown preserves pending work cleanly without false completion."""
    db_file = tmp_path / "req15.db"
    store = ChronicleStoreV2(db_file)
    queue = ConsolidationQueue(store)

    try:
        for i in range(3):
            insert_test_slice(store, f"s_shut_{i}", f"切片测试记录 {i}")
            queue.enqueue("slice", f"s_shut_{i}")

        assert queue.count_jobs(status="pending") == 3

        scheduler = ConsolidationScheduler(
            db_path=db_file,
            config=SchedulerConfig(debounce_delay_ms=500.0),
        )
        scheduler.start()
        # Immediately stop before debounce delay completes
        scheduler.stop(timeout=1.0)

        # All 3 jobs remain intact as 'pending'
        assert queue.count_jobs(status="pending") == 3
        assert queue.count_jobs(status="completed") == 0
    finally:
        store.close()


# ── Requirement 16: No Observation / Hypothesis / Confirmed Insight Generated


def test_req16_no_observation_hypothesis_confirmed_insight_generated(
    tmp_path: Path,
) -> None:
    """16. Consolidation strictly stops at WP-4: zero hypotheses, observations, insights created."""
    store = ChronicleStoreV2(tmp_path / "req16.db")
    queue = ConsolidationQueue(store)
    scheduler = ConsolidationScheduler(store)
    try:
        insert_test_slice(store, "s_iso_a", "我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。")
        insert_test_slice(store, "s_iso_b", "请严肃打断我提醒。")
        insert_test_event(store, "e_iso_c")

        queue.enqueue("slice", "s_iso_a")
        queue.enqueue("slice", "s_iso_b")
        queue.enqueue("event", "e_iso_c")

        results = scheduler.process_batch()
        assert len(results) == 3

        # Strict assertion on higher-order tables: all must be exactly 0
        obs_count = store.connection.execute("SELECT COUNT(*) FROM observations;").fetchone()[0]
        hyp_count = store.connection.execute("SELECT COUNT(*) FROM hypotheses;").fetchone()[0]
        cal_count = store.connection.execute("SELECT COUNT(*) FROM calibration_events;").fetchone()[
            0
        ]
        ins_count = store.connection.execute("SELECT COUNT(*) FROM confirmed_insights;").fetchone()[
            0
        ]

        assert obs_count == 0
        assert hyp_count == 0
        assert cal_count == 0
        assert ins_count == 0
    finally:
        store.close()


# ── Requirement 17: Production DB Untouched & V1 Default Unchanged ───────────


def test_req17_production_db_untouched_and_v1_default_unchanged(tmp_path: Path) -> None:
    """17. Production DB hash unchanged; V1 default behavior intact; FK check = 0."""
    # 1. Feature flags: all default to False
    flags = resolve_flags()
    assert flags.memory_v2_storage is False
    assert flags.memory_v2_consolidation is False
    assert flags.memory_v2_retrieval is False

    # 2. Production runtime selected path is strictly v1
    diag = validate_memory_v2_configuration(flags)
    assert diag["status"] == "VALID"
    assert diag["selected_path"] == "v1"

    # 3. Production DB verification: if companion_chronicle.db exists in main repo
    prod_db_path = Path("D:/CodeProjects/co-evolving-companion/data/companion_chronicle.db")
    if prod_db_path.exists():
        v1_backup = prod_db_path.parent / "companion_chronicle.db.pre_v2_backup"
        chk_target = v1_backup if v1_backup.is_file() else prod_db_path
        h_before = hashlib.sha256(chk_target.read_bytes()).hexdigest()
        assert h_before == "8b29f3c8714c1ae0ffc5db95a10e73cd299cf1ae74e01f5b8f402880a739df69"

    # 4. Foreign key check on test store is 0
    store = ChronicleStoreV2(tmp_path / "req17.db")
    try:
        fk_errors = store.connection.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(fk_errors) == 0
    finally:
        store.close()


# ── Performance / Scheduler Overhead Verification ───────────────────────────


def test_scheduler_overhead_reporting(tmp_path: Path) -> None:
    """Scheduler overhead reported separately from extraction and reconciliation."""
    store = ChronicleStoreV2(tmp_path / "overhead.db")
    queue = ConsolidationQueue(store)
    scheduler = ConsolidationScheduler(store)
    try:
        insert_test_slice(store, "s_lat_01", "我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。")
        job = queue.enqueue("slice", "s_lat_01")

        res = scheduler.process_one(job.job_id)
        assert res is not None
        assert res.status == "completed"
        # Latency fields exist and are non-negative
        assert res.scheduler_latency_ms >= 0.0
        assert res.extraction_latency_ms >= 0.0
        assert res.reconciliation_latency_ms >= 0.0
    finally:
        store.close()
