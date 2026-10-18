"""Test Suite for Raw Evidence Idempotency & Conflict Resolution (Stage 2).

Formal verification of:
- W-S06: Replay Idempotency (same ID + same payload -> existing record returned)
- W-S07: Conflict Fail Closed (same ID + different payload -> WriteConflictError raised)
- W-S08: No rowid business identity (proves independence from SQLite implicit rowid)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import (
    RawEvidenceWriteService,
    WriteConflictError,
    WriteEventCommand,
    WriteSliceCommand,
)


def test_w_s06_replay_idempotency_returns_existing_record(tmp_path: Path) -> None:
    """W-S06: replaying identical write returns idempotent success without duplicate rows."""
    db_file = tmp_path / "idempotency.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        # 1. Initial write
        cmd = WriteSliceCommand(
            content="这是一条具有固定dedup_key的切片",
            source="manual_feed",
            scope="global",
            slice_id="slice_fixed_01",
            ingestion_dedup_key="key_fixed_01",
        )
        res_first = writer.write_slice(cmd)
        assert res_first.status == "committed"
        assert res_first.was_persisted is True

        # 2. Replay with exact same payload and identity
        res_replay = writer.write_slice(cmd)
        assert res_replay.status == "idempotent_replay"
        assert res_replay.was_persisted is False
        assert res_replay.entity.slice_id == "slice_fixed_01"

        # Verify only 1 row exists in DB
        count = store.connection.execute("SELECT COUNT(*) FROM raw_slices;").fetchone()[0]
        assert count == 1
    finally:
        store.close()


def test_w_s07_conflict_fails_closed_and_leaves_original_row_untouched(tmp_path: Path) -> None:
    """W-S07: replaying same ID with differing payload raises WriteConflictError."""
    db_file = tmp_path / "conflict_fail_closed.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        # 1. Initial slice write
        cmd_orig = WriteSliceCommand(
            content="原版内容：下午去公园跑步",
            source="manual_feed",
            scope="global",
            slice_id="slice_conflict_target",
        )
        res_orig = writer.write_slice(cmd_orig)
        assert res_orig.status == "committed"

        # 2. Conflicting write with same slice_id but mutated content
        cmd_mutated = WriteSliceCommand(
            content="篡改内容：下午去咖啡馆办公",
            source="manual_feed",
            scope="global",
            slice_id="slice_conflict_target",
        )

        with pytest.raises(WriteConflictError) as exc_info:
            writer.write_slice(cmd_mutated)
        assert "differs from incoming write payload" in str(exc_info.value)

        # Verify original row is 100% UNTOUCHED
        row = store.connection.execute(
            "SELECT content FROM raw_slices WHERE slice_id = 'slice_conflict_target';"
        ).fetchone()
        assert row is not None
        assert row[0] == "原版内容：下午去公园跑步"

        # 3. Same check for Event Skeletons
        event_orig = WriteEventCommand(
            agent_id="agent_alpha",
            session_id="sess_1",
            event_type="tool_success",
            tool_name="git",
            event_id="evt_conflict_01",
        )
        writer.write_event(event_orig)

        event_conflicting = WriteEventCommand(
            agent_id="agent_alpha",
            session_id="sess_1",
            event_type="tool_failure",  # Mutated event_type!
            tool_name="git",
            event_id="evt_conflict_01",
        )
        with pytest.raises(WriteConflictError):
            writer.write_event(event_conflicting)

        # Original event preserved
        evt = store.get_event_skeleton("evt_conflict_01")
        assert evt is not None
        assert evt.event_type == "tool_success"
    finally:
        store.close()


def test_w_s08_no_rowid_identity_reliance(tmp_path: Path) -> None:
    """W-S08: verify writer operates purely on canonical UUID/string keys, never SQLite rowids."""
    db_file = tmp_path / "no_rowid.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        # Insert 3 slices
        writer.write_slice(content="Slice 1", slice_id="s1")
        writer.write_slice(content="Slice 2", slice_id="s2")
        writer.write_slice(content="Slice 3", slice_id="s3")

        # Delete the middle slice directly
        store.connection.execute("DELETE FROM raw_slices WHERE slice_id = 's2';")
        store.connection.commit()

        # Insert slice 4 with explicit ID
        writer.write_slice(content="Slice 4", slice_id="s4")

        # In SQLite on tables with TEXT PRIMARY KEY, implicit rowid may reuse 2 or assign 4
        # But writer API and lookups must strictly succeed based on string ID alone
        assert store.get_raw_slice("s1") is not None
        assert store.get_raw_slice("s2") is None
        assert store.get_raw_slice("s3") is not None
        assert store.get_raw_slice("s4") is not None

        # Verify idempotency on s3 operates without rowid interference
        replay = writer.write_slice(content="Slice 3", slice_id="s3")
        assert replay.status == "idempotent_replay"
    finally:
        store.close()
