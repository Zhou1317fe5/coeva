"""Unit tests for transaction atomicity, thread ownership, and production DB safety.

Part of Stage 1 (WP-1, Section 5, 14, 20).
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

import pytest

from src.memory.v2.entities import RawSliceEntity
from src.memory.v2.store import ChronicleStoreV2


def _compute_file_sha256(filepath: Path) -> str:
    """Compute sha256 of a file if it exists."""
    if not filepath.exists():
        return ""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_transaction_atomic_commit(tmp_path: Path) -> None:
    """Verify that multi-write transaction commits all rows atomically."""
    db_file = tmp_path / "tx_atomic.db"
    store = ChronicleStoreV2(db_file)
    try:
        with store.transaction():
            store.insert_raw_slice(
                RawSliceEntity(
                    slice_id="tx_s1",
                    occurred_at="2026-10-18T10:00:00+00:00",
                    content="原子事务切片1",
                    ingestion_dedup_key="tx_k1",
                )
            )
            store.insert_raw_slice(
                RawSliceEntity(
                    slice_id="tx_s2",
                    occurred_at="2026-10-18T10:01:00+00:00",
                    content="原子事务切片2",
                    ingestion_dedup_key="tx_k2",
                )
            )

        # Verified in DB
        assert store.get_raw_slice("tx_s1") is not None
        assert store.get_raw_slice("tx_s2") is not None
    finally:
        store.close()


def test_transaction_rollback_on_exception_leaves_zero_partial_state(tmp_path: Path) -> None:
    """Verify that an exception inside transaction() rolls back all writes without partial state."""
    db_file = tmp_path / "tx_rollback.db"
    store = ChronicleStoreV2(db_file)
    try:
        with pytest.raises(RuntimeError):
            with store.transaction():
                store.insert_raw_slice(
                    RawSliceEntity(
                        slice_id="tx_fail1",
                        occurred_at="2026-10-18T10:00:00+00:00",
                        content="应该被回滚的切片",
                        ingestion_dedup_key="k_fail1",
                    )
                )
                # Deliberate exception mid-transaction
                raise RuntimeError("Simulated crash mid-transaction")

        # Must be 100% rolled back
        assert store.get_raw_slice("tx_fail1") is None
        assert len(store.list_raw_slices()) == 0
    finally:
        store.close()


def test_thread_ownership_prevents_unsafe_connection_sharing(tmp_path: Path) -> None:
    """Verify that check_same_thread=True prevents unsafe cross-thread connection sharing."""
    db_file = tmp_path / "tx_thread.db"
    store = ChronicleStoreV2(db_file)
    error_caught = []

    def _worker_attempt_using_parent_connection() -> None:
        try:
            # Using store connection across threads should raise ProgrammingError in SQLite
            store.connection.execute("SELECT 1;")
        except sqlite3.ProgrammingError as e:
            error_caught.append(str(e))

    t = threading.Thread(target=_worker_attempt_using_parent_connection)
    t.start()
    t.join()

    try:
        assert len(error_caught) == 1
        assert "same thread" in error_caught[0].lower()
    finally:
        store.close()


def test_independent_connections_per_thread_safely_coexist(tmp_path: Path) -> None:
    """Verify that multiple threads holding independent connections work cleanly with WAL."""
    db_file = tmp_path / "tx_multi_thread.db"
    # Main store initializes schema
    main_store = ChronicleStoreV2(db_file)
    thread_results: list[bool] = []

    def _worker(worker_id: int) -> None:
        try:
            worker_store = ChronicleStoreV2(db_file, initialize=False)
            with worker_store.transaction():
                worker_store.insert_raw_slice(
                    RawSliceEntity(
                        slice_id=f"slice_worker_{worker_id}",
                        occurred_at=f"2026-10-18T10:{worker_id:02d}:00+00:00",
                        content=f"线程 {worker_id} 独立连接写入",
                        ingestion_dedup_key=f"k_worker_{worker_id}",
                    )
                )
            worker_store.close()
            thread_results.append(True)
        except Exception:
            thread_results.append(False)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(1, 4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert len(thread_results) == 3
        assert all(thread_results)
        # All 3 slices committed cleanly
        slices = main_store.list_raw_slices()
        assert len(slices) == 3
    finally:
        main_store.close()


def test_production_db_remains_untouched_after_stage1_storage_tests() -> None:
    """Section 20: Explicitly verify production DB file mtime and hash remain strictly unchanged."""
    prod_db = Path("data") / "companion_chronicle.db"
    if not prod_db.exists():
        pytest.skip("Production database not present in current workspace")

    mtime_before = prod_db.stat().st_mtime
    size_before = prod_db.stat().st_size
    hash_before = _compute_file_sha256(prod_db)

    # Instantiate scratch DB and perform operations
    scratch_store = ChronicleStoreV2(":memory:")
    scratch_store.insert_raw_slice(
        RawSliceEntity(
            slice_id="probe_slice",
            occurred_at="2026-10-18T12:00:00+00:00",
            content="探针切片",
            ingestion_dedup_key="probe_key",
        )
    )
    scratch_store.close()

    # Re-verify production DB
    mtime_after = prod_db.stat().st_mtime
    size_after = prod_db.stat().st_size
    hash_after = _compute_file_sha256(prod_db)

    assert mtime_after == mtime_before
    assert size_after == size_before
    assert hash_after == hash_before
