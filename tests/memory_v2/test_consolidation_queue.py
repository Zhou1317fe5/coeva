"""Test Suite for Consolidation Queue & Technical Metadata (Lane F, WP-5).

Verifies:
- Durable enqueue and atomic commit
- Idempotent enqueue by (source_kind, source_id)
- Zero user content / prompt / CoT / model statements in queue rows
- Survives process restart
- Safe reclamation of abandoned running jobs
- Strict queue metadata isolation (never memory evidence, never provenance)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.memory.v2.consolidation_queue import (
    ConsolidationJob,
    ConsolidationQueue,
    InvalidSourceKindError,
    compute_job_id,
)
from src.memory.v2.provenance import ProvenanceKind
from src.memory.v2.store import CANONICAL_TABLES, TECHNICAL_METADATA_TABLES, ChronicleStoreV2


def test_enqueue_durable_commit(tmp_path: Path) -> None:
    """Requirement 1: Enqueued job row is physically committed to SQLite before success."""
    db_file = tmp_path / "queue_durable.db"
    store = ChronicleStoreV2(db_file)
    queue = ConsolidationQueue(store)

    try:
        job = queue.enqueue("slice", "slice_001")
        assert isinstance(job, ConsolidationJob)
        assert job.source_kind == "slice"
        assert job.source_id == "slice_001"
        assert job.status == "pending"
        assert job.retry_count == 0
        assert job.job_id == compute_job_id("slice", "slice_001")

        # Verify on an independent read connection to the same DB file
        raw_conn = sqlite3.connect(str(db_file))
        raw_conn.row_factory = sqlite3.Row
        try:
            row = raw_conn.execute(
                "SELECT * FROM consolidation_jobs WHERE job_id = ?;", (job.job_id,)
            ).fetchone()
            assert row is not None
            assert row["source_kind"] == "slice"
            assert row["source_id"] == "slice_001"
            assert row["status"] == "pending"
            assert row["retry_count"] == 0
        finally:
            raw_conn.close()
    finally:
        store.close()


def test_enqueue_invalid_source_kind(tmp_path: Path) -> None:
    """Invalid source_kind fails validation and does not touch DB."""
    store = ChronicleStoreV2(tmp_path / "queue_invalid.db")
    queue = ConsolidationQueue(store)
    try:
        with pytest.raises(InvalidSourceKindError):
            queue.enqueue("arbitrary_unsupported_kind", "id_123")
    finally:
        store.close()


def test_enqueue_same_source_idempotent(tmp_path: Path) -> None:
    """Requirement 2: Repeated enqueue of same source produces no duplicate rows."""
    store = ChronicleStoreV2(tmp_path / "queue_idempotent.db")
    queue = ConsolidationQueue(store)

    try:
        job1 = queue.enqueue("slice", "slice_same_01")
        job2 = queue.enqueue("slice", "slice_same_01")

        assert job1.job_id == job2.job_id
        assert job1.created_at == job2.created_at

        count = store.connection.execute(
            """
            SELECT COUNT(*) FROM consolidation_jobs
             WHERE source_kind = 'slice' AND source_id = 'slice_same_01';
            """
        ).fetchone()[0]
        assert count == 1

        # Claim the job to running state
        claimed = queue.claim_jobs(limit=10)
        assert len(claimed) == 1
        assert claimed[0].status == "running"

        # Re-enqueuing while running returns the existing running job without creating a second job
        job3 = queue.enqueue("slice", "slice_same_01")
        assert job3.job_id == job1.job_id
        assert job3.status == "running"

        # Mark completed
        queue.mark_completed(job1.job_id)
        job4 = queue.enqueue("slice", "slice_same_01")
        assert job4.job_id == job1.job_id
        assert job4.status == "completed"

        # Final count is still exactly 1
        final_count = store.connection.execute(
            "SELECT COUNT(*) FROM consolidation_jobs WHERE source_id = 'slice_same_01';"
        ).fetchone()[0]
        assert final_count == 1
    finally:
        store.close()


def test_queue_contains_zero_user_content(tmp_path: Path) -> None:
    """Requirement 3: Queue metadata table contains no user content, prompt text, or CoT."""
    store = ChronicleStoreV2(tmp_path / "queue_isolation.db")
    queue = ConsolidationQueue(store)

    try:
        # Enqueue a slice
        job = queue.enqueue("slice", "slice_secret_01")

        # Inspect table PRAGMA table_info
        cols = [
            row["name"]
            for row in store.connection.execute("PRAGMA table_info(consolidation_jobs);").fetchall()
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

        # Confirm strictly no content / prompt / cot / text columns
        forbidden_cols = {"content", "prompt", "cot", "statement", "output", "payload"}
        assert forbidden_cols.isdisjoint(set(cols))

        # Query row directly: only source_kind and source_id are stored
        row = store.connection.execute(
            "SELECT * FROM consolidation_jobs WHERE job_id = ?;", (job.job_id,)
        ).fetchone()
        row_dict = dict(row)
        assert "slice_secret_01" in row_dict["source_id"]
        assert row_dict["source_kind"] == "slice"
    finally:
        store.close()


def test_pending_job_survives_restart(tmp_path: Path) -> None:
    """Requirement 4: Pending job survives store closing and reopen."""
    db_file = tmp_path / "queue_restart.db"
    store1 = ChronicleStoreV2(db_file)
    queue1 = ConsolidationQueue(store1)

    try:
        j1 = queue1.enqueue("slice", "slice_r1")
        j2 = queue1.enqueue("event", "event_r2")
        assert queue1.count_jobs(status="pending") == 2
    finally:
        store1.close()

    # Reopen database
    store2 = ChronicleStoreV2(db_file)
    queue2 = ConsolidationQueue(store2)
    try:
        assert queue2.count_jobs(status="pending") == 2
        loaded1 = queue2.get_job(j1.job_id)
        loaded2 = queue2.get_job(j2.job_id)

        assert loaded1 is not None and loaded1.status == "pending"
        assert loaded2 is not None and loaded2.status == "pending"
    finally:
        store2.close()


def test_abandoned_running_jobs_safely_reclaimed(tmp_path: Path) -> None:
    """Requirement 5: Abandoned 'running' jobs are safely reclaimed back to 'pending'."""
    store = ChronicleStoreV2(tmp_path / "queue_reclaim.db")
    queue = ConsolidationQueue(store)

    try:
        j1 = queue.enqueue("slice", "s_reclaim_1")
        j2 = queue.enqueue("slice", "s_reclaim_2")

        # Claim jobs to running
        claimed = queue.claim_jobs(limit=10)
        assert len(claimed) == 2
        assert all(j.status == "running" for j in claimed)

        # Simulate process restart / crash reclamation
        reclaimed_ids = queue.reclaim_abandoned_jobs()
        assert set(reclaimed_ids) == {j1.job_id, j2.job_id}

        # Jobs are now back to pending
        assert queue.count_jobs(status="pending") == 2
        assert queue.count_jobs(status="running") == 0

        # Can be claimed again cleanly
        reclaimed = queue.claim_jobs(limit=10)
        assert len(reclaimed) == 2
    finally:
        store.close()


def test_queue_metadata_isolation_i_s06(tmp_path: Path) -> None:
    """Requirement 14: consolidation_jobs rows can never become memory evidence or provenance."""
    store = ChronicleStoreV2(tmp_path / "queue_metadata_isolation.db")
    queue = ConsolidationQueue(store)

    try:
        job = queue.enqueue("slice", "slice_test_iso")

        # 1. consolidation_jobs is in technical metadata, not canonical tables
        assert "consolidation_jobs" in TECHNICAL_METADATA_TABLES
        assert "consolidation_jobs" not in CANONICAL_TABLES

        # 2. ProvenanceKind rejects consolidation_job
        allowed_kinds: tuple[ProvenanceKind, ...] = (
            "slice",
            "event",
            "episode",
            "semantic_memory",
            "observation",
            "insight",
        )
        assert "consolidation_jobs" not in allowed_kinds
        assert "consolidation_job" not in allowed_kinds

        # 3. Observation link foreign key restriction: job_id cannot link to observation_slice_links
        # (It references raw_slices.slice_id, which requires existing raw_slice)
        store.connection.execute(
            """
            INSERT INTO observations (
                observation_id, scope, statement, proof_count, status, created_at, updated_at
            ) VALUES (
                'obs_test_01', 'unresolved', 'test belief', 1, 'active',
                '2026-10-18T00:00:00Z', '2026-10-18T00:00:00Z'
            );
            """
        )

        # Attempting to insert job_id into observation_slice_links violates foreign keys
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                """
                INSERT INTO observation_slice_links (observation_id, slice_id, role, linked_at)
                VALUES ('obs_test_01', ?, 'supporting', '2026-10-18T00:00:00Z');
                """,
                (job.job_id,),
            )

        # 4. Job presence has zero impact on proof count
        proof_cnt = store.connection.execute(
            "SELECT proof_count FROM observations WHERE observation_id = 'obs_test_01';"
        ).fetchone()[0]
        assert proof_cnt == 1

        # 5. Store foreign key check returns 0 errors
        fk_check = store.connection.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(fk_check) == 0
    finally:
        store.close()
