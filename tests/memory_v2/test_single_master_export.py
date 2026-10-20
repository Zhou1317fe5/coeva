"""Test Suite for WP-11 Single Canonical Writer & JSONL One-Way Export.

Verifies:
- C-06: V2 single writer (SQLite raw_slices is single canonical authority)
- C-07: JSONL not authoritative (missing/corrupted JSONL does not alter SQLite truth)
- C-08: export after commit (exporter only sees durably committed rows)
- C-09: exporter failure isolation (export failure does not roll back SQLite or alter ACK)
- C-10: exporter restart/idempotency (restart creates no duplicates; reader deduplicates)
- C-11: no reverse import (JSONL cannot modify SQLite V2 state; reverse import forbidden)
- C-12: no rowid watermark (export identity uses canonical slice_id exclusively)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.memory.v2.entities import RawSliceEntity
from src.memory.v2.jsonl_export import (
    JsonlSliceExporter,
    ReverseImportForbiddenError,
    assert_no_reverse_import,
    read_exported_slices,
)
from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import (
    RawEvidenceWriteService,
    WriteConflictError,
)


def test_c06_v2_single_canonical_writer(tmp_path: Path) -> None:
    """C-06: Canonical Slice write commits only to SQLite authority without needing JSONL."""
    db_path = tmp_path / "c06_test.db"
    store = ChronicleStoreV2(db_path)
    service = RawEvidenceWriteService(store, exporter=None)

    try:
        # Write slice with NO exporter configured
        res = service.write_slice(
            content="Single canonical writer verification slice",
            source="manual_feed",
            scope="global",
        )
        assert res.status == "committed"
        assert res.was_persisted is True

        # SQLite transaction is durably committed and readable
        slice_row = store.get_raw_slice(res.entity.slice_id)
        assert slice_row is not None
        assert slice_row.content == "Single canonical writer verification slice"
        assert slice_row.actor == "user"
    finally:
        store.close()


def test_c07_jsonl_corrupt_missing_does_not_alter_sqlite_truth(tmp_path: Path) -> None:
    """C-07: Missing, corrupted, or truncated JSONL does not alter committed SQLite truth."""
    db_path = tmp_path / "c07_test.db"
    jsonl_path = tmp_path / "raw_slices.jsonl"
    store = ChronicleStoreV2(db_path)
    exporter = JsonlSliceExporter(jsonl_path)
    service = RawEvidenceWriteService(store, exporter=exporter)

    try:
        res = service.write_slice(content="Authoritative slice content")
        assert res.status == "committed"
        sid = res.entity.slice_id

        # 1. Corrupt JSONL with garbage bytes
        jsonl_path.write_bytes(b"\x00\xff\xfe\x00GARBAGE_NON_JSON\n")

        # SQLite truth remains completely intact
        slice_row = store.get_raw_slice(sid)
        assert slice_row is not None
        assert slice_row.content == "Authoritative slice content"

        # 2. Delete JSONL completely
        jsonl_path.unlink()
        assert not jsonl_path.exists()

        # SQLite truth still completely intact
        slice_row_2 = store.get_raw_slice(sid)
        assert slice_row_2 is not None
        assert slice_row_2.slice_id == sid
    finally:
        store.close()


def test_c08_export_only_sees_committed_canonical_rows(tmp_path: Path) -> None:
    """C-08: Exporter only sees canonical committed rows; rejected writes are never exported."""
    db_path = tmp_path / "c08_test.db"
    jsonl_path = tmp_path / "raw_slices.jsonl"
    store = ChronicleStoreV2(db_path)
    exporter = JsonlSliceExporter(jsonl_path)
    service = RawEvidenceWriteService(store, exporter=exporter)

    try:
        # Write first valid slice
        res1 = service.write_slice(
            content="First valid slice",
            slice_id="slice_fixed_001",
            ingestion_dedup_key="key_001",
        )
        assert res1.status == "committed"

        # Verify export has 1 line
        exported = read_exported_slices(jsonl_path)
        assert len(exported) == 1
        assert exported[0]["id"] == "slice_fixed_001"

        # Conflicting write with same ID but differing content -> WriteConflictError
        with pytest.raises(WriteConflictError):
            service.write_slice(
                content="Conflicting content with same ID",
                slice_id="slice_fixed_001",
                ingestion_dedup_key="key_001",
            )

        # Export destination still has ONLY the first committed slice
        exported_after = read_exported_slices(jsonl_path)
        assert len(exported_after) == 1
        assert exported_after[0]["content"] == "First valid slice"
    finally:
        store.close()


def test_c09_exporter_failure_isolated_from_ack_durability(tmp_path: Path) -> None:
    """C-09: Export failure does not roll back SQLite or change ACK outcome."""
    db_path = tmp_path / "c09_test.db"
    jsonl_path = tmp_path / "raw_slices.jsonl"
    store = ChronicleStoreV2(db_path)
    exporter = JsonlSliceExporter(jsonl_path)
    service = RawEvidenceWriteService(store, exporter=exporter)

    try:
        # Mock open on export_path to simulate disk write failure (e.g. disk full)
        with patch.object(Path, "open", side_effect=OSError("Disk full or permission denied")):
            res = service.write_slice(
                content="Slice with failing exporter",
                slice_id="slice_failing_export_001",
            )

            # ACK MUST SUCCEED (Durability invariant: SQLite commit determines success)
            assert res.status == "committed"
            assert res.was_persisted is True

            # Exporter captured the failure
            assert exporter.failure_count >= 1
            assert exporter.last_error is not None

        # Verify that SQLite record was durably saved and NOT rolled back
        row = store.get_raw_slice("slice_failing_export_001")
        assert row is not None
        assert row.content == "Slice with failing exporter"
    finally:
        store.close()


def test_c10_exporter_restart_idempotency_and_reader_dedup(tmp_path: Path) -> None:
    """C-10: Crash/restart creates no semantic duplication; reader de-duplicates physical dupes."""
    db_path = tmp_path / "c10_test.db"
    jsonl_path = tmp_path / "raw_slices.jsonl"
    store = ChronicleStoreV2(db_path)
    exporter_1 = JsonlSliceExporter(jsonl_path)
    service = RawEvidenceWriteService(store, exporter=exporter_1)

    try:
        res1 = service.write_slice(content="Slice A", slice_id="slice_a")
        res2 = service.write_slice(content="Slice B", slice_id="slice_b")
        assert res1.status == "committed"
        assert res2.status == "committed"

        initial_lines = [
            line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line
        ]
        assert len(initial_lines) == 2

        # Simulate process restart with a fresh exporter on the same file
        exporter_2 = JsonlSliceExporter(jsonl_path)
        assert exporter_2.exported_count == 2
        assert exporter_2.is_exported("slice_a") is True
        assert exporter_2.is_exported("slice_b") is True

        # Re-exporting same slices via sync_all or export_slice is a no-op
        synced = exporter_2.sync_all(store)
        assert synced == 0

        # File lines count remains exactly 2
        restarted_lines = [
            line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line
        ]
        assert len(restarted_lines) == 2

        # Simulate a crash where external append produced duplicate lines in JSONL
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(restarted_lines[0] + "\n")  # duplicate slice_a

        # read_exported_slices de-duplicates by canonical ID
        deduped = read_exported_slices(jsonl_path)
        assert len(deduped) == 2
        assert [d["id"] for d in deduped] == ["slice_a", "slice_b"]

        # Canonical SQLite state is untouched
        assert len(store.list_raw_slices()) == 2
    finally:
        store.close()


def test_c11_no_reverse_import_from_jsonl(tmp_path: Path) -> None:
    """C-11: Editing JSONL after export cannot modify SQLite V2 state; reverse import forbidden."""
    db_path = tmp_path / "c11_test.db"
    jsonl_path = tmp_path / "raw_slices.jsonl"
    store = ChronicleStoreV2(db_path)
    exporter = JsonlSliceExporter(jsonl_path)
    service = RawEvidenceWriteService(store, exporter=exporter)

    try:
        res = service.write_slice(content="Original SQLite text", slice_id="slice_c11")
        assert res.status == "committed"

        # Tamper with the JSONL file: change content to "Hacked text" and add a rogue line
        tampered_data = [
            {
                "id": "slice_c11",
                "timestamp": res.entity.occurred_at,
                "actor": "user",
                "source": "manual_feed",
                "content": "HACKED_TEXT",
                "mood_flag": "neutral",
                "created_at": res.entity.created_at,
            },
            {
                "id": "slice_rogue",
                "timestamp": res.entity.occurred_at,
                "actor": "user",
                "source": "manual_feed",
                "content": "ROGUE_SLICE",
                "mood_flag": "neutral",
                "created_at": res.entity.created_at,
            },
        ]
        with jsonl_path.open("w", encoding="utf-8") as f:
            for item in tampered_data:
                f.write(json.dumps(item) + "\n")

        # SQLite V2 state remains 100% UNTOUCHED by JSONL modifications
        db_slice = store.get_raw_slice("slice_c11")
        assert db_slice is not None
        assert db_slice.content == "Original SQLite text"

        rogue_slice = store.get_raw_slice("slice_rogue")
        assert rogue_slice is None

        # Reverse import is explicitly forbidden
        with pytest.raises(ReverseImportForbiddenError, match="Reverse import forbidden"):
            assert_no_reverse_import()
    finally:
        store.close()


def test_c12_no_rowid_watermark_canonical_id_ordering(tmp_path: Path) -> None:
    """C-12: Export uses canonical slice_id and occurred_at, never rowid watermarks."""
    db_path = tmp_path / "c12_test.db"
    jsonl_path = tmp_path / "raw_slices.jsonl"
    store = ChronicleStoreV2(db_path)
    exporter = JsonlSliceExporter(jsonl_path)

    try:
        # Insert slices with out-of-order timestamps and non-sequential IDs
        slice_3 = RawSliceEntity(
            slice_id="slice_gamma",
            occurred_at="2026-10-18T12:00:00Z",
            content="Third chronologically",
            actor="user",
            source="manual_feed",
            scope="global",
            project_id="global",
            ingestion_dedup_key="key_gamma",
            created_at="2026-10-18T12:00:00Z",
        )
        slice_1 = RawSliceEntity(
            slice_id="slice_alpha",
            occurred_at="2026-10-18T10:00:00Z",
            content="First chronologically",
            actor="user",
            source="manual_feed",
            scope="global",
            project_id="global",
            ingestion_dedup_key="key_alpha",
            created_at="2026-10-18T10:00:00Z",
        )
        slice_2 = RawSliceEntity(
            slice_id="slice_beta",
            occurred_at="2026-10-18T11:00:00Z",
            content="Second chronologically",
            actor="user",
            source="manual_feed",
            scope="global",
            project_id="global",
            ingestion_dedup_key="key_beta",
            created_at="2026-10-18T11:00:00Z",
        )

        store.insert_raw_slice(slice_3)
        store.insert_raw_slice(slice_1)
        store.insert_raw_slice(slice_2)

        # sync_all synchronizes based on (occurred_at ASC, slice_id ASC), NOT rowid
        exported_count = exporter.sync_all(store)
        assert exported_count == 3

        exported_items = read_exported_slices(jsonl_path)
        assert len(exported_items) == 3
        # Chronological order verified
        assert [item["id"] for item in exported_items] == [
            "slice_alpha",
            "slice_beta",
            "slice_gamma",
        ]

        # Verify export state is tracked by canonical IDs, not rowid
        assert exporter.is_exported("slice_alpha") is True
        assert exporter.is_exported("slice_beta") is True
        assert exporter.is_exported("slice_gamma") is True
    finally:
        store.close()
