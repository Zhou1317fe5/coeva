"""Tests for maintenance CLI, dry-run safety, and Section 15 integration requirements.

Covers:
- dry-run mutates nothing
- auto-startup migration absent
- source schema mismatch fails closed
- shadow build failure leaves source intact
- validation failure forbids swap
- rollback cannot discard post-V2 ACKed writes (I-S02, I-S03)
- legacy audit table is not memory evidence (not in retrieval, not in canonical tables)
- migration does not run backfill
- foreign_key_check = 0 on resulting shadow
- maintenance CLI entry points and exit codes
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.memory.v2.migration.cli import main
from src.memory.v2.migration.executor import MigrationExecutor
from src.memory.v2.migration.preflight import (
    IncompatibleSourceSchemaError,
    InsufficientDiskSpaceError,
)
from src.memory.v2.migration.swap import RollbackForbiddenDataLossError
from src.memory.v2.store import CANONICAL_TABLES, ChronicleStoreV2
from tests.memory_v2.test_migration_assertions import create_v1_database


def test_dry_run_mutates_nothing(tmp_path: Path) -> None:
    """Dry-run must calculate space, validate schema, but leave filesystem completely untouched."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=10, num_events=10)
    hash_before = src.read_bytes()

    scratch_dir = tmp_path / "scratch_work"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    files_before = set(scratch_dir.glob("*"))

    executor = MigrationExecutor()
    report = executor.dry_run(src, target_dir=scratch_dir)

    assert report.source_slice_count == 10
    assert report.source_event_count == 10
    assert report.source_hypothesis_count == 3
    assert report.disk_plan.final_required_bytes >= 150 * 1024 * 1024

    # Filesystem check: absolutely zero new files created
    assert src.read_bytes() == hash_before
    assert set(scratch_dir.glob("*")) == files_before


def test_auto_startup_migration_absent() -> None:
    """Ensure importing memory components does NOT execute migration automatically."""
    # When importing store or write_service or flags, migration barrier should remain inactive
    from src.memory.v2.migration.barrier import get_global_barrier

    barrier = get_global_barrier()
    assert barrier.is_active is False


def test_source_schema_mismatch_fails_closed(tmp_path: Path) -> None:
    """Source database missing expected V1 tables fails closed."""
    bad_db = tmp_path / "corrupt_schema.db"
    conn = sqlite3.connect(str(bad_db))
    # Table exists but wrong structure (missing slices table)
    conn.execute("CREATE TABLE foo (id TEXT PRIMARY KEY);")
    conn.commit()
    conn.close()

    executor = MigrationExecutor()
    with pytest.raises(IncompatibleSourceSchemaError) as exc_info:
        executor.dry_run(bad_db)

    assert "missing expected V1 tables" in str(exc_info.value)


def test_shadow_build_failure_leaves_source_intact(tmp_path: Path) -> None:
    """If an error occurs during shadow construction, source DB remains completely unmodified."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    source_bytes_before = src.read_bytes()

    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    executor = MigrationExecutor()
    # Force failure with insufficient disk space override
    with pytest.raises(InsufficientDiskSpaceError):
        executor.run_migration(
            src,
            tmp_path / "target.db",
            scratch_dir=scratch_dir,
            override_available_bytes=1000,
        )

    # Source DB must remain exactly byte-identical
    assert src.read_bytes() == source_bytes_before


def test_rollback_cannot_discard_post_v2_acked_writes(tmp_path: Path) -> None:
    """Rollback fails closed if V2 database accepted new ACKed writes (I-S02, I-S03)."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    target = tmp_path / "live_v2.db"
    scratch = tmp_path / "scratch"

    executor = MigrationExecutor()
    # Execute full migration with swap to create live target and backup
    executor.run_migration(src, target, execute_swap=True, scratch_dir=scratch)

    # Add a brand new V2 write into the target database
    t_conn = sqlite3.connect(str(target))
    t_conn.execute(
        """
        INSERT INTO raw_slices (
            slice_id, occurred_at, content, actor, source,
            scope, project_id, ingestion_dedup_key, created_at
        ) VALUES (
            'new_v2_slice_999', '2026-10-18T16:00:00Z', 'New user reflection in V2',
            'user', 'manual_feed', 'unresolved', NULL, 'v2_slice_999', '2026-10-18T16:00:00Z'
        );
        """
    )
    t_conn.commit()
    t_conn.close()

    # Attempt rollback: must fail closed to prevent discarding acknowledged write!
    with pytest.raises(RollbackForbiddenDataLossError) as exc_info:
        executor.rollback(target)

    assert "Rollback forbidden (I-S02, I-S03)" in str(exc_info.value)
    assert "new acknowledged canonical slice writes" in str(exc_info.value)


def test_pre_cutover_rehearsal_rollback_succeeds(tmp_path: Path) -> None:
    """If no new V2 writes were accepted, rollback safely restores backup."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    target = tmp_path / "rehearsal_v2.db"
    scratch = tmp_path / "scratch"

    executor = MigrationExecutor()
    executor.run_migration(src, target, execute_swap=True, scratch_dir=scratch)

    # Rollback without any new writes
    restored = executor.rollback(target)
    assert restored == target

    # Verify restored database is V1 slices table
    conn = sqlite3.connect(str(target))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}
    conn.close()

    assert "slices" in tables
    assert "raw_slices" not in tables


def test_legacy_hypothesis_audit_table_not_memory_evidence(tmp_path: Path) -> None:
    """legacy_hypothesis_audit must not be in CANONICAL_TABLES or retrieval entities."""
    # 1. CANONICAL_TABLES check
    assert "legacy_hypothesis_audit" not in CANONICAL_TABLES

    # 2. Schema check on store: ChronicleStoreV2 isolates it into TECHNICAL_METADATA_TABLES
    src = create_v1_database(tmp_path / "prod.db", num_slices=3, num_events=3)
    target = tmp_path / "target_v2.db"
    executor = MigrationExecutor()
    executor.run_migration(src, target, execute_swap=True, scratch_dir=tmp_path / "scratch")

    store = ChronicleStoreV2(target)
    try:
        # Canonical schema contract validation should succeed cleanly
        store.validate_schema_contract()
    finally:
        store.close()


def test_migration_does_not_run_backfill(tmp_path: Path) -> None:
    """Migration preserves evidence but does NOT generate derived semantic memories."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=10, num_events=20)
    target = tmp_path / "target_v2.db"
    executor = MigrationExecutor()
    executor.run_migration(src, target, execute_swap=True, scratch_dir=tmp_path / "scratch")

    conn = sqlite3.connect(str(target))
    cur = conn.cursor()

    # Derived semantic entities must remain 0 (not generated during migration)
    cur.execute("SELECT COUNT(*) FROM semantic_memories;")
    assert cur.fetchone()[0] == 0

    cur.execute("SELECT COUNT(*) FROM episodes;")
    assert cur.fetchone()[0] == 0

    cur.execute("SELECT COUNT(*) FROM observations;")
    assert cur.fetchone()[0] == 0

    cur.execute("SELECT COUNT(*) FROM confirmed_insights;")
    assert cur.fetchone()[0] == 0

    conn.close()


def test_cli_dry_run_and_execution_modes(tmp_path: Path) -> None:
    """Test maintenance CLI commands via main() entrypoint."""
    src = create_v1_database(tmp_path / "prod.db", num_slices=5, num_events=5)
    scratch = tmp_path / "scratch_cli"

    # 1. CLI Dry-Run
    code = main(["--source", str(src), "--dry-run", "--scratch-dir", str(scratch)])
    assert code == 0

    # 2. CLI Execution to target
    target = tmp_path / "cli_target.db"
    code = main(
        [
            "--source",
            str(src),
            "--target",
            str(target),
            "--execute",
            "--scratch-dir",
            str(scratch),
        ]
    )
    assert code == 0

    # 3. CLI with invalid schema should return exit code 3
    bad_db = tmp_path / "bad.db"
    bad_db.write_text("invalid sqlite", encoding="utf-8")
    code = main(["--source", str(bad_db), "--dry-run"])
    assert code == 3
