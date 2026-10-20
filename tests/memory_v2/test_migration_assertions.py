"""Test harness verifying all 18 Frozen Migration Safety Assertions (M-S01 ~ M-S18).

Targeting isolated scratch / temporary databases exclusively.
Zero production file mutation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.memory.v2.migration.barrier import (
    MigrationBarrier,
    MigrationInProgressError,
)
from src.memory.v2.migration.mapper import (
    build_v2_shadow_db,
)
from src.memory.v2.migration.preflight import (
    InsufficientDiskSpaceError,
    run_preflight_checks,
)
from src.memory.v2.migration.reconcile import (
    MigrationConflictError,
    reconcile_canonical_sets,
)
from src.memory.v2.migration.snapshot import create_wal_snapshot
from src.memory.v2.migration.swap import (
    WindowsFileLockError,
    execute_atomic_swap,
    recover_mid_swap_failure,
)


def create_v1_database(db_path: Path, num_slices: int = 10, num_events: int = 20) -> Path:
    """Fixture helper to create a populated, valid V1 SQLite database."""
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.executescript(
        """
        CREATE TABLE slices (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'user',
            source TEXT NOT NULL DEFAULT 'manual_feed',
            content TEXT NOT NULL,
            mood_flag TEXT NOT NULL DEFAULT 'neutral',
            created_at TEXT NOT NULL
        );
        CREATE TABLE events (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT 'default',
            event_type TEXT NOT NULL,
            tool_name TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            provenance TEXT NOT NULL,
            retention_class TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE hypotheses (
            id TEXT PRIMARY KEY,
            statement TEXT NOT NULL,
            lenses TEXT NOT NULL,
            supporting_patterns TEXT NOT NULL,
            supporting_episodes TEXT NOT NULL,
            counter_episodes TEXT NOT NULL,
            confidence TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    # Populate slices
    slices_data = [
        (
            f"slice_{i:04d}",
            f"2026-10-18T10:{i % 60:02d}:00Z",
            "user",
            "manual_feed",
            f"User reflection and notes entry {i}",
            "neutral",
            f"2026-10-18T10:{i % 60:02d}:00Z",
        )
        for i in range(num_slices)
    ]
    conn.executemany("INSERT INTO slices VALUES (?, ?, ?, ?, ?, ?, ?)", slices_data)

    # Populate events
    events_data = [
        (
            f"event_{i:04d}",
            f"2026-10-18T11:{i % 60:02d}:00Z",
            "pi-desktop",
            "sess_01",
            "tool_call" if i % 2 == 0 else "tool_failure",
            "bash" if i % 2 == 0 else "edit",
            "bash failed" if i % 2 != 0 else "",
            "agent_context",
            "transient",
            f"2026-10-18T11:{i % 60:02d}:00Z",
        )
        for i in range(num_events)
    ]
    conn.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", events_data)

    # Populate hypotheses
    hypo_data = [
        (
            f"hypo_{i:04d}",
            f"Working hypothesis statement {i}",
            '["growth", "agency"]',
            '["pat_01"]',
            '["ep_01"]',
            "[]",
            "moderate",
            "supported",
            "2026-10-18T12:00:00Z",
        )
        for i in range(3)
    ]
    conn.executemany("INSERT INTO hypotheses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", hypo_data)

    conn.commit()
    conn.close()
    return db_path


def test_ms01_snapshot_to_cutover_live_slice_preserved(tmp_path: Path) -> None:
    """M-S01: Live slice written between snapshot and cutover is preserved."""
    src = create_v1_database(tmp_path / "src.db", num_slices=5, num_events=5)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    # Snapshot taken at T0
    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    # Live write occurs on source at T1
    conn = sqlite3.connect(str(src))
    conn.execute(
        "INSERT INTO slices VALUES ("
        "'slice_live_99', '2026-10-18T12:30:00Z', 'user', 'manual_feed', "
        "'Live slice content', 'neutral', '2026-10-18T12:30:00Z')"
    )
    conn.commit()
    conn.close()

    # Option D Reconciliation
    reconcile_report = reconcile_canonical_sets(src, shadow)
    assert reconcile_report.slices_inserted == 1

    # Verify slice exists in shadow
    s_conn = sqlite3.connect(str(shadow))
    cur = s_conn.cursor()
    cur.execute("SELECT content FROM raw_slices WHERE slice_id = 'slice_live_99'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "Live slice content"
    s_conn.close()


def test_ms02_snapshot_to_cutover_live_event_preserved(tmp_path: Path) -> None:
    """M-S02: Live event written between snapshot and cutover is preserved."""
    src = create_v1_database(tmp_path / "src.db", num_slices=5, num_events=5)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    # Live event written to source at T1
    conn = sqlite3.connect(str(src))
    conn.execute(
        "INSERT INTO events VALUES ("
        "'event_live_99', '2026-10-18T12:35:00Z', 'pi-desktop', 'sess_01', "
        "'tool_call', 'read', '', 'agent_context', 'transient', '2026-10-18T12:35:00Z')"
    )
    conn.commit()
    conn.close()

    reconcile_report = reconcile_canonical_sets(src, shadow)
    assert reconcile_report.events_inserted == 1

    s_conn = sqlite3.connect(str(shadow))
    cur = s_conn.cursor()
    cur.execute(
        "SELECT event_type, tool_name FROM event_skeletons WHERE event_id = 'event_live_99'"
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "tool_call"
    assert row[1] == "read"
    s_conn.close()


def test_ms03_final_canonical_source_set_parity_verified(tmp_path: Path) -> None:
    """M-S03: Final canonical source-set parity verified (no watermark)."""
    src = create_v1_database(tmp_path / "src.db", num_slices=12, num_events=25)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)
    report = reconcile_canonical_sets(src, shadow)

    assert report.parity_verified is True
    assert "Final canonical source-set parity verified (no watermark)" in report.status_message
    assert report.final_slices_count == 12
    assert report.final_events_count == 25


def test_ms04_no_duplicate_row_from_replay(tmp_path: Path) -> None:
    """M-S04: No duplicate row introduced by delta replay."""
    src = create_v1_database(tmp_path / "src.db", num_slices=10, num_events=10)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    # Reconcile once
    reconcile_canonical_sets(src, shadow)
    # Replay reconcile a second time (identical source)
    report2 = reconcile_canonical_sets(src, shadow)

    assert report2.slices_inserted == 0
    assert report2.slices_noop == 10
    assert report2.events_inserted == 0
    assert report2.events_noop == 10

    s_conn = sqlite3.connect(str(shadow))
    cur = s_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM raw_slices")
    assert cur.fetchone()[0] == 10
    cur.execute("SELECT COUNT(*) FROM event_skeletons")
    assert cur.fetchone()[0] == 10
    s_conn.close()


def test_ms05_v2_event_skeleton_contains_no_prohibited_body(tmp_path: Path) -> None:
    """M-S05: V2 event skeleton contains no prohibited legacy body fields (prompt, CoT, stack)."""
    src = tmp_path / "src.db"
    conn = sqlite3.connect(str(src))
    conn.executescript(
        """
        CREATE TABLE slices (id TEXT PRIMARY KEY, timestamp TEXT, content TEXT);
        CREATE TABLE hypotheses (id TEXT PRIMARY KEY, statement TEXT, lenses TEXT);
        CREATE TABLE events (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            agent_id TEXT,
            session_id TEXT,
            event_type TEXT,
            tool_name TEXT,
            error_message TEXT,
            provenance TEXT,
            retention_class TEXT,
            created_at TEXT
        );
        """
    )
    # Event with prohibited stack trace and prompt leak
    toxic_error = (
        "Traceback (most recent call last):\n"
        "  File 'agent.py', line 42, in run\n"
        "    raise RuntimeError('Human: do X Assistant: <thought>leak</thought>')\n"
        "RuntimeError: secret prompt leaked"
    )
    conn.execute(
        "INSERT INTO events VALUES ("
        "'ev_toxic', '2026-10-18T10:00:00Z', 'pi', 's1', 'tool_failure', "
        "'bash', ?, 'agent_context', 'transient', '2026-10-18T10:00:00Z')",
        (toxic_error,),
    )
    conn.commit()
    conn.close()

    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"
    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    s_conn = sqlite3.connect(str(shadow))
    cur = s_conn.cursor()
    cur.execute("SELECT error_category FROM event_skeletons WHERE event_id = 'ev_toxic'")
    err_cat = cur.fetchone()[0]
    s_conn.close()

    # Must NOT contain prompt, CoT markers or multi-line traceback
    assert "<thought>" not in err_cat
    assert "Assistant:" not in err_cat
    assert "Human:" not in err_cat
    assert "Traceback" not in err_cat
    assert len(err_cat) <= 120


def test_ms06_active_wal_committed_pages_preserved(tmp_path: Path) -> None:
    """M-S06: Active WAL committed pages are preserved via SQLite Online Backup."""
    src = tmp_path / "src_wal.db"
    conn = sqlite3.connect(str(src))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.executescript(
        """
        CREATE TABLE slices (id TEXT PRIMARY KEY, timestamp TEXT, content TEXT);
        CREATE TABLE events (id TEXT PRIMARY KEY, timestamp TEXT, event_type TEXT);
        CREATE TABLE hypotheses (id TEXT PRIMARY KEY, statement TEXT, lenses TEXT);
        INSERT INTO slices VALUES ('slice_01', '2026-10-18T10:00:00Z', 'Content in WAL');
        """
    )
    # Keep WAL uncheckpointed
    conn.commit()
    wal_file = Path(f"{src}-wal")
    assert wal_file.is_file()

    snap = tmp_path / "snap.db"
    # Create WAL snapshot while source connection might even be active
    create_wal_snapshot(src, snap)
    conn.close()

    # Verify snap contains committed row from WAL
    snap_conn = sqlite3.connect(str(snap))
    cur = snap_conn.cursor()
    cur.execute("SELECT content FROM slices WHERE id = 'slice_01'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "Content in WAL"
    snap_conn.close()


def test_ms07_windows_handle_rename_failure_leaves_v1_recoverable(tmp_path: Path) -> None:
    """M-S07: Windows handle/rename failure leaves V1 recoverable."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    shadow = tmp_path / "shadow.db"
    snap = tmp_path / "snap.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    # Lock target file with an open handle to simulate Windows file lock
    locked_conn = sqlite3.connect(str(src))
    cur = locked_conn.cursor()
    cur.execute("BEGIN EXCLUSIVE;")

    try:
        # Atomic swap should fail due to file lock on Windows or raise WindowsFileLockError
        with pytest.raises(WindowsFileLockError):
            execute_atomic_swap(src, shadow, max_retries=1, retry_delay_seconds=0.01)
    finally:
        locked_conn.rollback()
        locked_conn.close()

    # Verify original V1 database is intact and recoverable
    v1_conn = sqlite3.connect(str(src))
    cur = v1_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM slices")
    assert cur.fetchone()[0] == 5
    v1_conn.close()


def test_ms08_crash_mid_swap_leaves_one_recoverable_canonical_db(tmp_path: Path) -> None:
    """M-S08: Crash mid-swap leaves exactly one recoverable canonical DB."""
    target = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    backup = tmp_path / "prod.db.pre_v2_backup"

    # Simulate crash right after target was renamed/deleted and before replacement was finalized:
    # Target file is corrupted or 0 bytes, but valid backup exists
    import shutil

    shutil.copy2(target, backup)
    # Corrupt target to 0 bytes
    target.write_bytes(b"")

    recovered = recover_mid_swap_failure(target)
    assert recovered == target

    # Target must be valid again
    conn = sqlite3.connect(str(target))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM slices")
    assert cur.fetchone()[0] == 5
    conn.close()


def test_ms09_disk_precheck_rejects_insufficient_space(tmp_path: Path) -> None:
    """M-S09: Disk precheck rejects insufficient space before migration starts."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)

    # Override available space to a tiny value (10 MB < 150 MB floor)
    with pytest.raises(InsufficientDiskSpaceError) as exc_info:
        run_preflight_checks(src, tmp_path, override_available_bytes=10 * 1024 * 1024)

    assert "M-S09 fail closed" in str(exc_info.value)
    # Verify no shadow/snapshot artifacts were created
    assert not (tmp_path / "prod.db.shadow.db").exists()
    assert not (tmp_path / "prod.db.snapshot.db").exists()


def test_ms10_legacy_hypothesis_audit_metadata_not_promoted(tmp_path: Path) -> None:
    """M-S10: Legacy hypothesis state preserved only in audit metadata, not promoted."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=2, num_events=2)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    conn = sqlite3.connect(str(shadow))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. hypotheses table must force status='candidate' and confidence_class='tentative'
    cur.execute("SELECT hypothesis_id, status, confidence_class FROM hypotheses")
    hypos = cur.fetchall()
    assert len(hypos) == 3
    for h in hypos:
        assert h["status"] == "candidate"
        assert h["confidence_class"] == "tentative"

    # 2. legacy_hypothesis_audit preserves old status ('supported') and original metadata
    cur.execute("SELECT hypothesis_id, original_status FROM legacy_hypothesis_audit")
    audits = cur.fetchall()
    assert len(audits) == 3
    assert all(a["original_status"] == "supported" for a in audits)

    # 3. confirmed_insights must remain empty (0 rows)
    cur.execute("SELECT COUNT(*) FROM confirmed_insights")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_ms11_raw_slices_full_content_integrity_100_percent(tmp_path: Path) -> None:
    """M-S11: raw_slices full-content integrity = 100% (byte-for-byte fidelity)."""
    src = tmp_path / "prod.db"
    conn = sqlite3.connect(str(src))
    conn.executescript(
        """
        CREATE TABLE slices (id TEXT PRIMARY KEY, timestamp TEXT, content TEXT);
        CREATE TABLE events (id TEXT PRIMARY KEY, timestamp TEXT, event_type TEXT);
        CREATE TABLE hypotheses (id TEXT PRIMARY KEY, statement TEXT, lenses TEXT);
        """
    )
    long_multiline_content = (
        "Line 1: Special chars \u2014 \u2013 \u00a9\n"
        "Line 2: Indented text\n\nLine 3: 100% exact fidelity."
    )
    conn.execute(
        "INSERT INTO slices VALUES ('slice_exact', '2026-10-18T10:00:00Z', ?)",
        (long_multiline_content,),
    )
    conn.commit()
    conn.close()

    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"
    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    s_conn = sqlite3.connect(str(shadow))
    cur = s_conn.cursor()
    cur.execute("SELECT content FROM raw_slices WHERE slice_id = 'slice_exact'")
    retrieved = cur.fetchone()[0]
    s_conn.close()

    assert retrieved == long_multiline_content


def test_ms12_foreign_key_check_zero_violations(tmp_path: Path) -> None:
    """M-S12: foreign_key_check = 0 on resulting shadow database."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=15, num_events=30)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    report = build_v2_shadow_db(snap, shadow)
    assert report.foreign_key_violations == 0

    conn = sqlite3.connect(str(shadow))
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_key_check;")
    violations = cur.fetchall()
    conn.close()
    assert len(violations) == 0


def test_ms13_delete_max_rowid_then_insert_new_slice_not_lost(tmp_path: Path) -> None:
    """M-S13: Delete current max ROWID after T0, then insert new Slice: not lost."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    conn = sqlite3.connect(str(src))
    cur = conn.cursor()
    cur.execute("SELECT MAX(rowid) FROM slices")
    max_rowid = cur.fetchone()[0]

    # Delete max rowid
    cur.execute("DELETE FROM slices WHERE rowid = ?", (max_rowid,))
    # Insert new slice with novel canonical ID
    cur.execute(
        "INSERT INTO slices VALUES ("
        "'slice_post_del_99', '2026-10-18T14:00:00Z', 'user', 'manual_feed', "
        "'New slice after max rowid deletion', 'neutral', '2026-10-18T14:00:00Z')"
    )
    conn.commit()
    conn.close()

    # Reconcile using Option D Canonical ID Set Difference
    reconcile_canonical_sets(src, shadow)

    # Verify new slice was NOT lost despite rowid reuse/regression
    s_conn = sqlite3.connect(str(shadow))
    cur = s_conn.cursor()
    cur.execute("SELECT content FROM raw_slices WHERE slice_id = 'slice_post_del_99'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "New slice after max rowid deletion"
    s_conn.close()


def test_ms14_delete_max_rowid_then_insert_new_event_not_lost(tmp_path: Path) -> None:
    """M-S14: Delete current max ROWID after T0, then insert new Event: not lost."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    conn = sqlite3.connect(str(src))
    cur = conn.cursor()
    cur.execute("SELECT MAX(rowid) FROM events")
    max_rowid = cur.fetchone()[0]

    # Delete max rowid
    cur.execute("DELETE FROM events WHERE rowid = ?", (max_rowid,))
    # Insert new event with novel canonical ID
    cur.execute(
        "INSERT INTO events VALUES ("
        "'event_post_del_99', '2026-10-18T14:05:00Z', 'pi-desktop', 'sess_01', "
        "'tool_call', 'grep', '', 'agent_context', 'transient', '2026-10-18T14:05:00Z')"
    )
    conn.commit()
    conn.close()

    reconcile_canonical_sets(src, shadow)

    s_conn = sqlite3.connect(str(shadow))
    cur = s_conn.cursor()
    cur.execute("SELECT tool_name FROM event_skeletons WHERE event_id = 'event_post_del_99'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "grep"
    s_conn.close()


def test_ms15_replay_same_canonical_id_identical_payload_is_idempotent(tmp_path: Path) -> None:
    """M-S15: Replay same canonical ID with identical payload is idempotent NOOP."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    # Reconcile repeatedly
    rep1 = reconcile_canonical_sets(src, shadow)
    rep2 = reconcile_canonical_sets(src, shadow)

    assert rep1.slices_noop == 5
    assert rep2.slices_noop == 5
    assert rep2.slices_inserted == 0

    s_conn = sqlite3.connect(str(shadow))
    cur = s_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM raw_slices")
    assert cur.fetchone()[0] == 5
    s_conn.close()


def test_ms16_replay_same_canonical_id_conflicting_payload_fails_closed(tmp_path: Path) -> None:
    """M-S16: Replay same canonical ID with changed/conflicting payload fails closed."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    snap = tmp_path / "snap.db"
    shadow = tmp_path / "shadow.db"

    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    # Mutate payload of existing canonical slice in source
    conn = sqlite3.connect(str(src))
    conn.execute(
        "UPDATE slices SET content = 'TAMPERED / CONFLICTING CONTENT' WHERE id = 'slice_0001'"
    )
    conn.commit()
    conn.close()

    # Reconcile MUST raise MigrationConflictError and fail closed
    with pytest.raises(MigrationConflictError) as exc_info:
        reconcile_canonical_sets(src, shadow)

    assert "MIGRATION CONFLICT on Slice ID 'slice_0001'" in str(exc_info.value)
    assert "FAIL CLOSED: cutover forbidden" in str(exc_info.value)


def test_ms17_barrier_slice_write_zero_acked_loss_on_crash() -> None:
    """M-S17: Barrier + new Slice + crash -> zero acknowledged Slice loss.

    ACKED WRITE MUST BE DURABLE: Writes during barrier are withheld (unacknowledged).
    """
    barrier = MigrationBarrier("test_barrier_slice")
    barrier.acquire("rehearsal migration")

    # In non-blocking mode: raises MigrationInProgressError immediately
    with pytest.raises(MigrationInProgressError) as exc_info:
        barrier.guard_slice_write("slice_100", block=False)

    assert exc_info.value.write_type == "slice"
    assert exc_info.value.payload_id == "slice_100"

    # In blocking mode: times out if migration does not finish in time
    with pytest.raises(MigrationInProgressError):
        barrier.guard_slice_write("slice_100", block=True, timeout=0.05)

    # Invariant: No Success ACK was ever given to caller
    barrier.release()


def test_ms18_barrier_event_write_zero_acked_loss_on_crash() -> None:
    """M-S18: Barrier + new Event + crash -> zero acknowledged Event loss.

    ACKED WRITE MUST BE DURABLE: Telemetry consumption pauses, withholding ACK.
    """
    barrier = MigrationBarrier("test_barrier_event")
    barrier.acquire("rehearsal migration")

    with pytest.raises(MigrationInProgressError) as exc_info:
        barrier.guard_event_write("event_100", block=False)

    assert exc_info.value.write_type == "event"
    assert exc_info.value.payload_id == "event_100"

    # Blocking with timeout withholding ACK
    with pytest.raises(MigrationInProgressError):
        barrier.guard_event_write("event_100", block=True, timeout=0.05)

    barrier.release()
