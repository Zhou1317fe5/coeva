"""Unit tests for V2.1 schema initialization, canonical entity inventory, and drift detection.

Part of Stage 1 (WP-1, Section 13, 15, 16).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.memory.v2.store import (
    CANONICAL_TABLES,
    SCHEMA_VERSION,
    TECHNICAL_METADATA_TABLES,
    ChronicleStoreV2,
    SchemaDriftError,
)


def test_scratch_db_initializes_exact_canonical_schema(tmp_path: Path) -> None:
    """Verify that a scratch DB initializes 20 canonical tables and 4 metadata tables."""
    db_file = tmp_path / "scratch_v2.db"
    store = ChronicleStoreV2(db_file)
    try:
        report = store.validate_schema_contract()
        assert report["status"] == "VALID"
        assert report["schema_version"] == SCHEMA_VERSION
        assert report["canonical_table_count"] == 20
        assert report["technical_table_count"] == 4
        assert report["foreign_key_violations"] == 0

        # Inspect sqlite_master
        tables = [
            r[0]
            for r in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        assert len(CANONICAL_TABLES) == 20
        for ct in CANONICAL_TABLES:
            assert ct in tables

        for tt in TECHNICAL_METADATA_TABLES:
            assert tt in tables
    finally:
        store.close()


def test_schema_version_pragma(tmp_path: Path) -> None:
    """Verify that user_version pragma is set to 20261018."""
    db_file = tmp_path / "scratch_v2_version.db"
    store = ChronicleStoreV2(db_file)
    try:
        assert store.get_schema_version() == 20261018
    finally:
        store.close()


def test_foreign_key_check_clean(tmp_path: Path) -> None:
    """Verify that foreign_key_check returns 0 rows on fresh initialized schema."""
    db_file = tmp_path / "scratch_v2_fk.db"
    store = ChronicleStoreV2(db_file)
    try:
        violations = store.connection.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(violations) == 0
    finally:
        store.close()


def test_schema_drift_detection_fails_closed(tmp_path: Path) -> None:
    """Verify that missing table or modified version triggers SchemaDriftError."""
    db_file = tmp_path / "scratch_drift.db"
    store = ChronicleStoreV2(db_file)
    try:
        # 1. Tamper with user_version
        store.connection.execute("PRAGMA user_version = 1000;")
        store.connection.commit()
        with pytest.raises(SchemaDriftError) as exc_info:
            store.validate_schema_contract()
        assert "Schema version drift" in str(exc_info.value)

        # Restore version
        store.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
        store.connection.commit()

        # 2. Tamper by dropping a canonical table
        store.connection.execute("DROP TABLE chapter_insight_links;")
        store.connection.commit()
        with pytest.raises(SchemaDriftError) as exc_info2:
            store.validate_schema_contract()
        assert "Missing canonical tables" in str(exc_info2.value)
    finally:
        store.close()


def test_idempotent_schema_initialization(tmp_path: Path) -> None:
    """Verify that re-running initialize_schema() on an existing valid DB is safe and idempotent."""
    db_file = tmp_path / "scratch_idempotent.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Second call must pass cleanly without error
        store.initialize_schema()
        assert store.get_schema_version() == SCHEMA_VERSION
    finally:
        store.close()
