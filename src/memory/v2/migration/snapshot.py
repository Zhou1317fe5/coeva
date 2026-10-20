"""WAL-safe SQLite snapshot infrastructure for Memory V2.1.

Implements M-S06:
Preserves active WAL committed pages using SQLite Online Backup API.
Never copies only the main .db file while ignoring active WAL pages.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


class SnapshotError(Exception):
    """Base error for snapshot failures."""

    pass


def create_wal_snapshot(
    source_db_path: Path,
    snapshot_path: Path,
    *,
    pages_per_step: int = 100,
) -> Path:
    """Create a WAL-safe, consistent SQLite snapshot of source_db_path at snapshot_path.

    Uses `sqlite3.Connection.backup` to read both main DB pages and active committed
    WAL pages safely without lock starvation or partial-page corruption (M-S06).

    Args:
        source_db_path: Path to source SQLite database.
        snapshot_path: Destination path for snapshot DB file.
        pages_per_step: Number of pages to copy per step (-1 for all at once).

    Returns:
        The snapshot_path.

    Raises:
        SnapshotError: If snapshot creation or integrity check fails.
    """
    if not source_db_path.is_file():
        raise SnapshotError(f"Source database file does not exist: {source_db_path}")

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_path.is_file():
        snapshot_path.unlink()

    # Open source in read-only mode to prevent unintended mutation
    abs_source = os.path.abspath(source_db_path)
    source_uri = f"file:{abs_source}?mode=ro"

    try:
        source_conn = sqlite3.connect(source_uri, uri=True)
    except Exception as e:
        raise SnapshotError(f"Failed to open source database for snapshot: {e}") from e

    try:
        dest_conn = sqlite3.connect(str(snapshot_path))
        try:
            # Execute online backup
            with dest_conn:
                source_conn.backup(dest_conn, pages=pages_per_step)
        finally:
            dest_conn.close()
    except Exception as e:
        if snapshot_path.is_file():
            snapshot_path.unlink()
        raise SnapshotError(
            f"Online backup failed from {source_db_path} to {snapshot_path}: {e}"
        ) from e
    finally:
        source_conn.close()

    # Validate snapshot integrity
    verify_conn = sqlite3.connect(f"file:{os.path.abspath(snapshot_path)}?mode=ro", uri=True)
    try:
        cur = verify_conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        results = [row[0] for row in cur.fetchall()]
        if results != ["ok"]:
            if snapshot_path.is_file():
                snapshot_path.unlink()
            raise SnapshotError(f"Snapshot integrity check failed: {results}")
    finally:
        verify_conn.close()

    return snapshot_path
