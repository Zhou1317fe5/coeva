"""Maintenance CLI for Coeva Long-Term Memory V2.1 Migration.

Strictly maintenance-only tool (Rule 5 / S0-F01 / S0-F02):
- Explicit maintenance CLI entry point.
- Zero auto-migration on app startup.
- Supports --dry-run, --execute, --rollback.
- Returns non-zero exit code on safety failure, space rejection, or conflict.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.memory.v2.migration.executor import MigrationExecutor
from src.memory.v2.migration.preflight import (
    IncompatibleSourceSchemaError,
    InsufficientDiskSpaceError,
    SourceIntegrityCheckError,
)
from src.memory.v2.migration.reconcile import MigrationConflictError
from src.memory.v2.migration.swap import (
    RollbackForbiddenDataLossError,
    WindowsFileLockError,
)


def create_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for memory migration tool."""
    parser = argparse.ArgumentParser(
        prog="migrate",
        description="Coeva Long-Term Memory V2.1 Maintenance Migration Tool",
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to source SQLite database (e.g. data/companion_chronicle.db)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Path to target V2 SQLite database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute preflight checks, calculate required disk space, mutate nothing",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the full migration pipeline to shadow database",
    )
    parser.add_argument(
        "--execute-swap",
        action="store_true",
        help="Execute atomic swap replacing target database with migrated shadow DB",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback target database to pre-V2 backup (strictly forbids losing ACKed writes)",
    )
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        default=None,
        help="Directory to store intermediate snapshot and shadow databases",
    )
    parser.add_argument(
        "--force-test-only",
        action="store_true",
        help="Allow test-only bypass of safety locks during simulated test fixtures",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point returning status code."""
    parser = create_parser()
    args = parser.parse_args(argv)

    executor = MigrationExecutor()

    # Mode 1: Dry-run
    if args.dry_run:
        try:
            print("=== COEVA MEMORY V2.1 MIGRATION: DRY-RUN ===")
            print(f"Source Database: {args.source}")
            preflight_report = executor.dry_run(args.source, target_dir=args.scratch_dir)
            dp = preflight_report.disk_plan
            print("\n[PREFLIGHT PASSED]")
            print(f"  Source Slices:      {preflight_report.source_slice_count}")
            print(f"  Source Events:      {preflight_report.source_event_count}")
            print(f"  Source Hypotheses:   {preflight_report.source_hypothesis_count}")
            print(
                f"  Source Integrity:   {'OK' if preflight_report.source_integrity_ok else 'FAIL'}"
            )
            print("\n[DISK SPACE PLAN]")
            print(f"  Source DB Bytes:    {dp.prod_db_bytes / (1024 * 1024):.2f} MB")
            print(f"  WAL Bytes:          {dp.prod_wal_bytes / (1024 * 1024):.2f} MB")
            print(f"  Snapshot Bytes:     {dp.snapshot_bytes / (1024 * 1024):.2f} MB")
            print(f"  Shadow Bytes:       {dp.shadow_projected_bytes / (1024 * 1024):.2f} MB")
            print(f"  Dynamic Required:   {dp.dynamic_required_bytes / (1024 * 1024):.2f} MB")
            print(f"  Floor Required:     {dp.floor_required_bytes / (1024 * 1024):.2f} MB")
            print(f"  Final Required:     {dp.final_required_bytes / (1024 * 1024):.2f} MB")
            print(f"  Available Space:    {dp.available_bytes / (1024 * 1024):.2f} MB")
            print("Dry-run complete. Mutated nothing on disk.")
            return 0
        except InsufficientDiskSpaceError as e:
            print(f"[PREFLIGHT FAILED - INSUFFICIENT DISK SPACE]: {e}", file=sys.stderr)
            return 2
        except (IncompatibleSourceSchemaError, SourceIntegrityCheckError) as e:
            print(f"[PREFLIGHT FAILED - SCHEMA MISMATCH]: {e}", file=sys.stderr)
            return 3
        except Exception as e:
            print(f"[PREFLIGHT ERROR]: {e}", file=sys.stderr)
            return 1

    # Mode 2: Rollback
    if args.rollback:
        target = args.target or args.source
        print("=== COEVA MEMORY V2.1 MIGRATION: ROLLBACK ===")
        print(f"Target Database: {target}")
        try:
            restored = executor.rollback(target, force_test_only=args.force_test_only)
            print(f"[ROLLBACK SUCCESS]: Restored {restored} from pre-V2 backup.")
            return 0
        except RollbackForbiddenDataLossError as e:
            print(f"[ROLLBACK REJECTED - DATA LOSS FORBIDDEN (I-S02/I-S03)]: {e}", file=sys.stderr)
            return 4
        except Exception as e:
            print(f"[ROLLBACK FAILED]: {e}", file=sys.stderr)
            return 1

    # Mode 3: Execute migration
    if args.execute or args.execute_swap:
        target = args.target or args.source
        print("=== COEVA MEMORY V2.1 MIGRATION: EXECUTION ===")
        print(f"Source: {args.source}")
        print(f"Target: {target}")
        print(f"Execute Swap: {args.execute_swap}")

        try:
            migration_report = executor.run_migration(
                source_path=args.source,
                target_path=target,
                execute_swap=args.execute_swap,
                scratch_dir=args.scratch_dir,
            )
            print("\n[MIGRATION SUCCESS]")
            print(f"  Status:             {migration_report.status}")
            print(f"  Elapsed Time:       {migration_report.total_elapsed_seconds:.3f} s")
            print(f"  Slices Migrated:    {migration_report.mapping.slices_migrated}")
            print(f"  Events Migrated:    {migration_report.mapping.events_migrated}")
            print(f"  Hypotheses:         {migration_report.mapping.hypotheses_migrated}")
            print(f"  Audit Records:      {migration_report.mapping.audit_records_written}")
            print(f"  FK Violations:      {migration_report.mapping.foreign_key_violations}")
            print(f"  Parity Status:      {migration_report.reconciliation.status_message}")
            if migration_report.swap:
                swap_sec = migration_report.swap.duration_seconds
                print(f"  Atomic Swap:        Completed in {swap_sec:.3f} s")
            return 0
        except InsufficientDiskSpaceError as e:
            print(f"[EXECUTION FAILED - INSUFFICIENT DISK SPACE]: {e}", file=sys.stderr)
            return 2
        except (IncompatibleSourceSchemaError, SourceIntegrityCheckError) as e:
            print(f"[EXECUTION FAILED - SCHEMA MISMATCH]: {e}", file=sys.stderr)
            return 3
        except MigrationConflictError as e:
            print(f"[EXECUTION FAILED - MIGRATION CONFLICT (FAIL CLOSED)]: {e}", file=sys.stderr)
            return 5
        except WindowsFileLockError as e:
            print(f"[EXECUTION FAILED - WINDOWS FILE LOCK (M-S07)]: {e}", file=sys.stderr)
            return 6
        except Exception as e:
            print(f"[EXECUTION FAILED]: {e}", file=sys.stderr)
            return 1

    # Default: if no action specified, show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
