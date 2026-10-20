"""Preflight verification and dynamic disk-space precheck for Memory V2.1.

Implements M-S09:
- Rejects insufficient disk space strictly before creating any migration artifacts.
- Validates source schema compatibility and fails closed on corrupted or
  incompatible schemas.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path


class PreflightError(Exception):
    """Base error for preflight failures."""

    pass


class InsufficientDiskSpaceError(PreflightError):
    """Raised when available disk space is less than final_required (M-S09)."""

    def __init__(self, available_bytes: int, required_bytes: int, target_dir: Path) -> None:
        msg = (
            f"Insufficient disk space in '{target_dir}': "
            f"available {available_bytes / (1024 * 1024):.2f} MB < "
            f"required {required_bytes / (1024 * 1024):.2f} MB (M-S09 fail closed)"
        )
        super().__init__(msg)
        self.available_bytes = available_bytes
        self.required_bytes = required_bytes
        self.target_dir = target_dir


class IncompatibleSourceSchemaError(PreflightError):
    """Raised when source database schema does not match expected V1 structure."""

    pass


class SourceIntegrityCheckError(PreflightError):
    """Raised when SQLite integrity_check fails on source database."""

    pass


@dataclass(frozen=True)
class DiskSpacePlan:
    """Dynamic disk space calculation breakdown."""

    prod_db_bytes: int
    prod_wal_bytes: int
    prod_shm_bytes: int
    snapshot_bytes: int
    shadow_projected_bytes: int
    backup_bytes: int
    safety_margin_bytes: int
    dynamic_required_bytes: int
    floor_required_bytes: int
    final_required_bytes: int
    available_bytes: int
    is_sufficient: bool


@dataclass(frozen=True)
class PreflightReport:
    """Consolidated preflight check report."""

    source_path: Path
    target_dir: Path
    source_slice_count: int
    source_event_count: int
    source_hypothesis_count: int
    source_integrity_ok: bool
    disk_plan: DiskSpacePlan


def compute_disk_space_plan(
    source_db_path: Path,
    target_dir: Path | None = None,
    *,
    safety_margin_bytes: int = 50 * 1024 * 1024,  # 50 MB
    floor_min_bytes: int = 150 * 1024 * 1024,  # 150 MB floor
) -> DiskSpacePlan:
    """Calculate required disk space using the approved dynamic model."""
    target_path = target_dir or source_db_path.parent
    if not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)

    prod_db_bytes = source_db_path.stat().st_size if source_db_path.is_file() else 0
    wal_path = Path(f"{source_db_path}-wal")
    shm_path = Path(f"{source_db_path}-shm")

    prod_wal_bytes = wal_path.stat().st_size if wal_path.is_file() else 0
    prod_shm_bytes = shm_path.stat().st_size if shm_path.is_file() else 0

    total_source_bytes = prod_db_bytes + prod_wal_bytes
    snapshot_bytes = total_source_bytes
    shadow_projected_bytes = total_source_bytes
    backup_bytes = total_source_bytes

    dynamic_required = (
        prod_db_bytes
        + prod_wal_bytes
        + prod_shm_bytes
        + snapshot_bytes
        + shadow_projected_bytes
        + backup_bytes
        + safety_margin_bytes
    )

    floor_required = max(floor_min_bytes, int(3.0 * prod_db_bytes))
    final_required = max(dynamic_required, floor_required)

    total_bytes, used_bytes, free_bytes = shutil.disk_usage(target_path)
    is_sufficient = free_bytes >= final_required

    return DiskSpacePlan(
        prod_db_bytes=prod_db_bytes,
        prod_wal_bytes=prod_wal_bytes,
        prod_shm_bytes=prod_shm_bytes,
        snapshot_bytes=snapshot_bytes,
        shadow_projected_bytes=shadow_projected_bytes,
        backup_bytes=backup_bytes,
        safety_margin_bytes=safety_margin_bytes,
        dynamic_required_bytes=dynamic_required,
        floor_required_bytes=floor_required,
        final_required_bytes=final_required,
        available_bytes=free_bytes,
        is_sufficient=is_sufficient,
    )


def validate_source_schema_and_integrity(source_db_path: Path) -> tuple[int, int, int]:
    """Validate that source database is a compatible, uncorrupted V1 database.

    Returns:
        tuple of (slice_count, event_count, hypothesis_count)

    Raises:
        IncompatibleSourceSchemaError: If required V1 tables or columns are missing.
        SourceIntegrityCheckError: If PRAGMA integrity_check fails.
    """
    if not source_db_path.is_file():
        raise IncompatibleSourceSchemaError(f"Source database file not found: {source_db_path}")

    try:
        uri = f"file:{os.path.abspath(source_db_path)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    except Exception as e:
        raise IncompatibleSourceSchemaError(
            f"Failed to open source database in read-only mode: {e}"
        ) from e

    try:
        # 1. Integrity check
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        results = [row[0] for row in cursor.fetchall()]
        if results != ["ok"]:
            raise SourceIntegrityCheckError(
                f"Source integrity check failed on {source_db_path}: {results}"
            )

        # 2. Schema check: tables must include slices, events, hypotheses
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {"slices", "events", "hypotheses"}
        missing_tables = required_tables - tables
        if missing_tables:
            raise IncompatibleSourceSchemaError(
                f"Source schema is missing expected V1 tables: {sorted(missing_tables)}"
            )

        # Check required columns on slices
        cursor.execute("PRAGMA table_info(slices);")
        slice_cols = {row[1] for row in cursor.fetchall()}
        required_slice_cols = {"id", "timestamp", "content"}
        if not required_slice_cols.issubset(slice_cols):
            raise IncompatibleSourceSchemaError(
                f"Source 'slices' table missing required columns: "
                f"{sorted(required_slice_cols - slice_cols)}"
            )

        # Check required columns on events
        cursor.execute("PRAGMA table_info(events);")
        event_cols = {row[1] for row in cursor.fetchall()}
        required_event_cols = {"id", "timestamp", "event_type"}
        if not required_event_cols.issubset(event_cols):
            raise IncompatibleSourceSchemaError(
                f"Source 'events' table missing required columns: "
                f"{sorted(required_event_cols - event_cols)}"
            )

        # Check required columns on hypotheses
        cursor.execute("PRAGMA table_info(hypotheses);")
        hypo_cols = {row[1] for row in cursor.fetchall()}
        required_hypo_cols = {"id", "statement", "lenses"}
        if not required_hypo_cols.issubset(hypo_cols):
            raise IncompatibleSourceSchemaError(
                f"Source 'hypotheses' table missing required columns: "
                f"{sorted(required_hypo_cols - hypo_cols)}"
            )

        # Count rows
        cursor.execute("SELECT COUNT(*) FROM slices;")
        slice_count = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM events;")
        event_count = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM hypotheses;")
        hypothesis_count = int(cursor.fetchone()[0])

        return slice_count, event_count, hypothesis_count
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        raise IncompatibleSourceSchemaError(f"Source database is invalid or corrupt: {e}") from e
    finally:
        conn.close()


def run_preflight_checks(
    source_db_path: Path,
    target_dir: Path | None = None,
    *,
    override_available_bytes: int | None = None,
    safety_margin_bytes: int = 50 * 1024 * 1024,
    floor_min_bytes: int = 150 * 1024 * 1024,
) -> PreflightReport:
    """Execute complete preflight checks before any migration work begins.

    Raises:
        IncompatibleSourceSchemaError: If schema is incompatible.
        SourceIntegrityCheckError: If DB is corrupt.
        InsufficientDiskSpaceError: If free disk space is less than final_required (M-S09).
    """
    target_path = target_dir or source_db_path.parent
    disk_plan = compute_disk_space_plan(
        source_db_path,
        target_path,
        safety_margin_bytes=safety_margin_bytes,
        floor_min_bytes=floor_min_bytes,
    )

    available = (
        override_available_bytes
        if override_available_bytes is not None
        else disk_plan.available_bytes
    )

    if available < disk_plan.final_required_bytes:
        raise InsufficientDiskSpaceError(
            available_bytes=available,
            required_bytes=disk_plan.final_required_bytes,
            target_dir=target_path,
        )

    slice_count, event_count, hypo_count = validate_source_schema_and_integrity(source_db_path)

    return PreflightReport(
        source_path=source_db_path,
        target_dir=target_path,
        source_slice_count=slice_count,
        source_event_count=event_count,
        source_hypothesis_count=hypo_count,
        source_integrity_ok=True,
        disk_plan=disk_plan,
    )
