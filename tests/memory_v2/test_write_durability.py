"""Test Suite for Raw Evidence Durability & ACK Invariants (Stage 2).

Formal verification of:
- W-S01: Commit Before ACK (success only after SQLite fsync/commit)
- W-S02: Failed Commit No ACK (commit failure raises WriteDurabilityError, 0 partial state)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import (
    RawEvidenceWriteService,
    WriteDurabilityError,
    WriteSliceCommand,
)


def test_w_s01_durability_commit_before_ack(tmp_path: Path) -> None:
    """W-S01: writer returns success only after SQLite commit is durable on disk."""
    db_file = tmp_path / "durability_ack.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        cmd = WriteSliceCommand(
            content="必须要物理持久化之后才返回成功",
            source="manual_feed",
            scope="global",
        )
        res = writer.write_slice(cmd)
        assert res.status == "committed"
        assert res.was_persisted is True
        assert res.duration_ms > 0.0

        # Physical verify in DB
        row = store.connection.execute(
            "SELECT content, project_id FROM raw_slices WHERE slice_id = ?;",
            (res.entity.slice_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "必须要物理持久化之后才返回成功"
    finally:
        store.close()


def test_w_s02_failed_commit_returns_no_ack_and_leaves_zero_partial_rows(
    tmp_path: Path,
) -> None:
    """W-S02: transaction failure raises WriteDurabilityError, returns NO ACK, 0 partial rows."""
    db_file = tmp_path / "durability_fail.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        # Pre-populate one valid record
        writer.write_slice(content="基线记录", scope="global")
        initial_count = store.connection.execute("SELECT COUNT(*) FROM raw_slices;").fetchone()[0]
        assert initial_count == 1

        # Mock an error during insert/commit
        cmd = WriteSliceCommand(content="发生故障的切片", scope="global")

        with patch.object(store, "insert_raw_slice", side_effect=RuntimeError("Disk I/O failure")):
            with pytest.raises(WriteDurabilityError) as exc_info:
                writer.write_slice(cmd)
            assert "Disk I/O failure" in str(exc_info.value)

        # Verify: NO partial row exists, count unchanged
        final_count = store.connection.execute("SELECT COUNT(*) FROM raw_slices;").fetchone()[0]
        assert final_count == initial_count

        # Verify: failed content was NOT written
        failed_row = store.connection.execute(
            "SELECT * FROM raw_slices WHERE content = '发生故障的切片';"
        ).fetchone()
        assert failed_row is None
    finally:
        store.close()
