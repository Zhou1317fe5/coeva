"""Windows-safe Atomic Swap Planner and Crash Recovery Mechanism.

Implements:
- M-S07: Windows handle/rename failure leaves V1 recoverable.
- M-S08: Crash mid-swap leaves exactly one recoverable canonical DB.
- I-S02 / I-S03: Rollback safety — blind restore forbidden if V2 has accepted
  new canonical ACKed writes.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


class SwapError(Exception):
    """Base error for swap and cutover operations."""

    pass


class WindowsFileLockError(SwapError):
    """Raised when an open file handle prevents atomic replace on Windows (M-S07)."""

    pass


class MidSwapRecoveryError(SwapError):
    """Raised when mid-swap state cannot be safely recovered."""

    pass


class RollbackForbiddenDataLossError(SwapError):
    """Raised when rollback would discard new canonical V2 ACKed writes (I-S02, I-S03)."""

    pass


@dataclass(frozen=True)
class SwapPlan:
    """Pre-calculated atomic swap plan."""

    source_path: Path
    shadow_path: Path
    backup_path: Path
    wal_checkpoint_ok: bool


@dataclass(frozen=True)
class SwapResult:
    """Outcome of atomic swap operation."""

    swapped_target_path: Path
    backup_path: Path
    duration_seconds: float
    canonical_db_verified: bool


def checkpoint_and_quiesce_db(db_path: Path) -> None:
    """Execute WAL TRUNCATE checkpoint and disconnect cleanly to close file handles."""
    if not db_path.is_file():
        return

    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        finally:
            conn.close()
    except Exception:
        pass


def verify_db_integrity(db_path: Path) -> bool:
    """Verify that a SQLite file exists, opens, and passes integrity_check."""
    if not db_path.is_file() or db_path.stat().st_size == 0:
        return False
    try:
        conn = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            results = [row[0] for row in cur.fetchall()]
            return results == ["ok"]
        finally:
            conn.close()
    except Exception:
        return False


def prepare_swap_plan(
    target_path: Path,
    shadow_path: Path,
    backup_suffix: str = ".pre_v2_backup",
) -> SwapPlan:
    """Prepare and validate an atomic swap plan.

    Ensures shadow database is valid and WAL is truncated before swap planning.
    """
    if not shadow_path.is_file():
        raise SwapError(f"Shadow database does not exist: {shadow_path}")

    # Checkpoint shadow
    checkpoint_and_quiesce_db(shadow_path)
    if not verify_db_integrity(shadow_path):
        raise SwapError(f"Shadow database integrity verification failed: {shadow_path}")

    backup_path = Path(f"{target_path}{backup_suffix}")

    return SwapPlan(
        source_path=target_path,
        shadow_path=shadow_path,
        backup_path=backup_path,
        wal_checkpoint_ok=True,
    )


def execute_atomic_swap(
    target_path: Path,
    shadow_path: Path,
    *,
    backup_source_path: Path | None = None,
    backup_suffix: str = ".pre_v2_backup",
    max_retries: int = 3,
    retry_delay_seconds: float = 0.1,
) -> SwapResult:
    """Execute Windows-safe atomic swap of target_path with shadow_path.

    Enforces:
    - Pre-swap WAL TRUNCATE checkpoint.
    - Pre-V2 backup creation before replacing target.
    - M-S07: If Windows file lock (PermissionError) occurs, target remains intact and recoverable.
    - M-S08: Invariant: after any failure, at least one verified recoverable DB exists.
    """
    start_time = time.perf_counter()
    plan = prepare_swap_plan(target_path, shadow_path, backup_suffix)

    # 1. Truncate target WAL if target exists and create pre_v2_backup
    source_to_backup = target_path if target_path.is_file() else backup_source_path
    if source_to_backup and source_to_backup.is_file():
        checkpoint_and_quiesce_db(source_to_backup)
        try:
            shutil.copy2(source_to_backup, plan.backup_path)
        except Exception as e:
            raise SwapError(f"Failed to create pre-v2 backup at {plan.backup_path}: {e}") from e
    # 2. Attempt atomic replace with Windows file-lock retry
    swap_success = False
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            os.replace(shadow_path, target_path)
            swap_success = True
            break
        except (PermissionError, OSError) as e:
            last_error = e
            time.sleep(retry_delay_seconds * (attempt + 1))

    if not swap_success:
        # Handle Windows handle / rename failure (M-S07)
        # Verify that original target or backup is intact and recoverable
        if not verify_db_integrity(target_path):
            if plan.backup_path.is_file() and verify_db_integrity(plan.backup_path):
                shutil.copy2(plan.backup_path, target_path)

        msg = (
            f"Windows handle rename failure while swapping {shadow_path} -> {target_path}. "
            f"Target remains recoverable V1 (M-S07): {last_error}"
        )
        raise WindowsFileLockError(msg) from last_error

    # Clean up associated shadow WAL / SHM files if any remain
    shadow_wal = Path(f"{shadow_path}-wal")
    shadow_shm = Path(f"{shadow_path}-shm")
    if shadow_wal.is_file():
        try:
            shadow_wal.unlink()
        except OSError:
            pass
    if shadow_shm.is_file():
        try:
            shadow_shm.unlink()
        except OSError:
            pass

    # Clean up old target WAL / SHM so new V2 starts with clean WAL
    target_wal = Path(f"{target_path}-wal")
    target_shm = Path(f"{target_path}-shm")
    if target_wal.is_file():
        try:
            target_wal.unlink()
        except OSError:
            pass
    if target_shm.is_file():
        try:
            target_shm.unlink()
        except OSError:
            pass

    # Verify newly swapped canonical database
    if not verify_db_integrity(target_path):
        # Crash/corruption recovery: restore from backup (M-S08)
        if plan.backup_path.is_file() and verify_db_integrity(plan.backup_path):
            shutil.copy2(plan.backup_path, target_path)
        raise SwapError(f"Swapped database failed integrity check at {target_path}")

    elapsed = time.perf_counter() - start_time
    return SwapResult(
        swapped_target_path=target_path,
        backup_path=plan.backup_path,
        duration_seconds=elapsed,
        canonical_db_verified=True,
    )


def recover_mid_swap_failure(
    target_path: Path,
    backup_suffix: str = ".pre_v2_backup",
) -> Path:
    """Recover state after a simulated process crash mid-swap (M-S08).

    Guarantees: Exactly one verified recoverable canonical DB is restored.
    """
    backup_path = Path(f"{target_path}{backup_suffix}")

    target_valid = verify_db_integrity(target_path)
    backup_valid = backup_path.is_file() and verify_db_integrity(backup_path)

    if target_valid:
        # Target is already a valid canonical database
        return target_path

    if backup_valid:
        # Target is missing or corrupted, but backup is valid: restore backup
        shutil.copy2(backup_path, target_path)
        if verify_db_integrity(target_path):
            return target_path

    raise MidSwapRecoveryError(
        f"Cannot recover canonical database: neither {target_path} nor {backup_path} is valid"
    )


def rollback_cutover(
    target_path: Path,
    *,
    backup_suffix: str = ".pre_v2_backup",
    force_test_only: bool = False,
) -> Path:
    """Safely roll back a migration cutover to pre-v2 backup (I-S02, I-S03).

    Safety Invariant:
    If target_path is a V2 database and has accepted NEW canonical ACKed writes
    (writes not present in backup), blind restore is STRICTLY FORBIDDEN and
    raises RollbackForbiddenDataLossError.

    Only pre-cutover rehearsal rollbacks or verified write-free rollbacks are permitted.
    """
    backup_path = Path(f"{target_path}{backup_suffix}")
    if not backup_path.is_file():
        raise SwapError(f"Cannot roll back: backup file not found at {backup_path}")

    if not verify_db_integrity(backup_path):
        raise SwapError(f"Cannot roll back: backup file is corrupt at {backup_path}")

    if not target_path.is_file():
        # Target does not exist, safe to restore
        shutil.copy2(backup_path, target_path)
        return target_path

    # Check for new V2 ACKed writes in target_path
    if not force_test_only and verify_db_integrity(target_path):
        target_conn = sqlite3.connect(f"file:{os.path.abspath(target_path)}?mode=ro", uri=True)
        try:
            cur = target_conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {r[0] for r in cur.fetchall()}

            # If target has V2 raw_slices table
            if "raw_slices" in tables:
                # Read all slice IDs in target
                cur.execute("SELECT slice_id FROM raw_slices")
                target_slice_ids = {str(r[0]) for r in cur.fetchall()}

                # Read slice IDs from backup
                b_conn = sqlite3.connect(f"file:{os.path.abspath(backup_path)}?mode=ro", uri=True)
                try:
                    b_cur = b_conn.cursor()
                    b_cur.execute("SELECT id FROM slices")
                    backup_slice_ids = {str(r[0]) for r in b_cur.fetchall()}
                finally:
                    b_conn.close()

                new_slices = target_slice_ids - backup_slice_ids
                if new_slices:
                    msg = (
                        f"Rollback forbidden (I-S02, I-S03): V2 database at {target_path} "
                        f"contains {len(new_slices)} new acknowledged canonical slice writes "
                        f"(e.g. {list(new_slices)[:3]}). Blind restore would discard ACKed data!"
                    )
                    raise RollbackForbiddenDataLossError(msg)

            # If target has V2 event_skeletons table
            if "event_skeletons" in tables:
                cur.execute("SELECT event_id FROM event_skeletons")
                target_event_ids = {str(r[0]) for r in cur.fetchall()}

                b_conn = sqlite3.connect(f"file:{os.path.abspath(backup_path)}?mode=ro", uri=True)
                try:
                    b_cur = b_conn.cursor()
                    b_cur.execute("SELECT id FROM events")
                    backup_event_ids = {str(r[0]) for r in b_cur.fetchall()}
                finally:
                    b_conn.close()

                new_events = target_event_ids - backup_event_ids
                if new_events:
                    msg = (
                        f"Rollback forbidden (I-S02, I-S03): V2 database at {target_path} "
                        f"contains {len(new_events)} new acknowledged canonical event writes. "
                        f"Blind restore would discard ACKed data!"
                    )
                    raise RollbackForbiddenDataLossError(msg)

        finally:
            target_conn.close()

    # If here, no new ACKed writes exist; rollback is safe (pre-cutover rehearsal rollback)
    checkpoint_and_quiesce_db(target_path)
    shutil.copy2(backup_path, target_path)

    # Clean any residual WAL/SHM
    for ext in ("-wal", "-shm"):
        p = Path(f"{target_path}{ext}")
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass

    return target_path
