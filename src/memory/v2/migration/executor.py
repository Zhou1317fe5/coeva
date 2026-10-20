"""Migration Executor coordinating the complete V1->V2 migration pipeline.

Pipeline Flow:
Preflight (M-S09) ->
Acquire MigrationBarrier (Hard Quiesce, M-S17, M-S18) ->
Create WAL-Safe Snapshot (M-S06) ->
Build V2 Shadow DB (M-S05, M-S10, M-S11, M-S12) ->
Option D Canonical ID Set Difference & Conflict Check (M-S03, M-S13~M-S16) ->
Prepare / Execute Atomic Swap (M-S07, M-S08) ->
Release MigrationBarrier.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from src.memory.v2.migration.barrier import MigrationBarrier, get_global_barrier
from src.memory.v2.migration.mapper import MappingReport, build_v2_shadow_db
from src.memory.v2.migration.preflight import (
    PreflightReport,
    run_preflight_checks,
)
from src.memory.v2.migration.reconcile import (
    ReconciliationReport,
    reconcile_canonical_sets,
)
from src.memory.v2.migration.snapshot import create_wal_snapshot
from src.memory.v2.migration.swap import (
    SwapResult,
    execute_atomic_swap,
    prepare_swap_plan,
    rollback_cutover,
)


@dataclass(frozen=True)
class MigrationExecutionReport:
    """Comprehensive report of a migration run."""

    preflight: PreflightReport
    mapping: MappingReport
    reconciliation: ReconciliationReport
    swap: SwapResult | None
    total_elapsed_seconds: float
    barrier_released: bool
    status: str


class MigrationExecutor:
    """End-to-end coordinator for Coeva Long-Term Memory V2.1 migration."""

    def __init__(self, barrier: MigrationBarrier | None = None) -> None:
        self.barrier = barrier or get_global_barrier()

    def dry_run(
        self,
        source_path: Path,
        target_dir: Path | None = None,
        *,
        override_available_bytes: int | None = None,
    ) -> PreflightReport:
        """Execute preflight and dry-run planning without mutating any files.

        Mutates nothing on disk.
        """
        return run_preflight_checks(
            source_path,
            target_dir,
            override_available_bytes=override_available_bytes,
        )

    def run_migration(
        self,
        source_path: Path,
        target_path: Path,
        *,
        execute_swap: bool = False,
        scratch_dir: Path | None = None,
        override_available_bytes: int | None = None,
    ) -> MigrationExecutionReport:
        """Execute full migration pipeline in a controlled rehearsal environment.

        Args:
            source_path: Path to source V1 SQLite database.
            target_path: Destination path for migrated V2 SQLite database.
            execute_swap: If True, executes atomic swap of target_path.
                          If False, leaves shadow DB at shadow_path for inspection.
            scratch_dir: Directory for intermediate snapshot and shadow DBs.
            override_available_bytes: Override for disk precheck testing.

        Returns:
            MigrationExecutionReport detailing all phases.
        """
        start_time = time.perf_counter()
        target_dir = scratch_dir or target_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        snapshot_path = target_dir / f"{target_path.stem}.snapshot.db"
        shadow_path = target_dir / f"{target_path.stem}.shadow.db"

        # Step 1: Preflight
        preflight_report = run_preflight_checks(
            source_path,
            target_dir,
            override_available_bytes=override_available_bytes,
        )

        swap_result: SwapResult | None = None

        # Step 2: Acquire MigrationBarrier (Option A Hard Quiesce)
        with self.barrier.quiesce(reason=f"Migrating {source_path.name} to V2"):
            # Step 3: Create WAL-safe snapshot
            create_wal_snapshot(source_path, snapshot_path)

            # Step 4: Build V2 shadow database with privacy sanitization
            mapping_report = build_v2_shadow_db(snapshot_path, shadow_path)

            # Step 5: Option D Canonical ID Set Difference Reconciliation
            reconcile_report = reconcile_canonical_sets(source_path, shadow_path)

            # Step 6: Atomic swap planning / execution
            if execute_swap:
                swap_result = execute_atomic_swap(
                    target_path, shadow_path, backup_source_path=source_path
                )
            else:
                # Just validate swap plan
                _ = prepare_swap_plan(target_path, shadow_path)

        # Cleanup transient snapshot if swap occurred or on success
        if snapshot_path.is_file():
            try:
                snapshot_path.unlink()
            except OSError:
                pass

        elapsed = time.perf_counter() - start_time
        return MigrationExecutionReport(
            preflight=preflight_report,
            mapping=mapping_report,
            reconciliation=reconcile_report,
            swap=swap_result,
            total_elapsed_seconds=elapsed,
            barrier_released=True,
            status="SUCCESS",
        )

    def rollback(
        self,
        target_path: Path,
        *,
        backup_suffix: str = ".pre_v2_backup",
        force_test_only: bool = False,
    ) -> Path:
        """Safely rollback target database to pre-v2 backup."""
        return rollback_cutover(
            target_path,
            backup_suffix=backup_suffix,
            force_test_only=force_test_only,
        )
