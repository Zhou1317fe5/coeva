"""Test suite for Old-Runtime Safety and Fail-Closed Verification (WP-14 Phase A.5).

Verifies:
- SAFE-01: Legacy V1 ChronicleStore opening a V2 canonical database (user_version >= 20261018)
  immediately raises RuntimeError and fails closed before executing schema scripts.
- SAFE-02: SQLite engine-level protection prevents legacy _SCHEMA script from recreating
  slices/events tables over existing compatibility views, failing closed on index creation.
- SAFE-03: Direct legacy INSERT/UPDATE/DELETE on slices and events views is rejected by SQLite
  engine as read-only views, preventing any rogue second canonical writer.
- SAFE-04: Legacy import_slices_jsonl cannot write or modify canonical SQLite state.
- SAFE-05: Path resolution via get_data_dir() resolves explicitly to the canonical production
  data root without worktree ambiguity.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.paths import (
    CANONICAL_PROD_DATA_DIR,
    ENV_DATA_DIR,
    get_data_dir,
    get_db_path,
    get_jsonl_path,
    get_settings_path,
)
from src.memory.store import _SCHEMA, ChronicleStore
from src.memory.v2.compatibility import install_legacy_views
from src.memory.v2.store import ChronicleStoreV2


def _create_test_v2_db(db_path: Path) -> ChronicleStoreV2:
    store = ChronicleStoreV2(db_path)
    install_legacy_views(store.connection)
    return store


def test_safe01_legacy_v1_store_fails_closed_on_v2_user_version(tmp_path: Path) -> None:
    """SAFE-01: ChronicleStore fails closed with RuntimeError when opening V2 DB."""
    db_file = tmp_path / "v2_canonical.db"
    store = _create_test_v2_db(db_file)
    store.close()

    # Attempt to open with legacy V1 ChronicleStore
    with pytest.raises(RuntimeError) as exc_info:
        ChronicleStore(db_file)

    err_msg = str(exc_info.value)
    assert "user_version=20261018" in err_msg
    assert "FAIL-CLOSED" in err_msg


def test_safe02_engine_level_block_on_legacy_schema_recreation(tmp_path: Path) -> None:
    """SAFE-02: SQLite engine blocks legacy _SCHEMA script over V2 views."""
    db_file = tmp_path / "v2_engine_block.db"
    store = _create_test_v2_db(db_file)
    store.close()

    # Direct raw connection simulating unpatched legacy process executing _SCHEMA
    raw_conn = sqlite3.connect(str(db_file))
    try:
        with pytest.raises(sqlite3.OperationalError) as exc_info:
            raw_conn.executescript(_SCHEMA)
        # SQLite fails closed because views may not be indexed
        assert "views may not be indexed" in str(exc_info.value).lower()
    finally:
        raw_conn.close()


def test_safe03_engine_level_block_on_legacy_table_writes(tmp_path: Path) -> None:
    """SAFE-03: Direct INSERT into slices/events views is rejected by SQLite engine."""
    db_file = tmp_path / "v2_write_block.db"
    store = _create_test_v2_db(db_file)
    store.close()

    raw_conn = sqlite3.connect(str(db_file))
    try:
        # Attempt INSERT into slices
        with pytest.raises(sqlite3.OperationalError) as exc_info_s:
            raw_conn.execute(
                "INSERT INTO slices (id, timestamp, actor, source, content, mood_flag) "
                "VALUES ('s_test', '2026-10-18T12:00:00Z', 'user', 'manual_feed', "
                "'content', 'neutral');"
            )
        assert "cannot modify slices because it is a view" in str(exc_info_s.value).lower()

        # Attempt INSERT into events
        with pytest.raises(sqlite3.OperationalError) as exc_info_e:
            raw_conn.execute(
                "INSERT INTO events (id, timestamp, agent_id, session_id, event_type, "
                "provenance, retention_class) "
                "VALUES ('e_test', '2026-10-18T12:00:00Z', 'pi', 'default', 'prompt', "
                "'context', 'transient');"
            )
        assert "cannot modify events because it is a view" in str(exc_info_e.value).lower()
    finally:
        raw_conn.close()


def test_safe04_legacy_jsonl_import_fails_closed(tmp_path: Path) -> None:
    """SAFE-04: Legacy import_slices_jsonl cannot modify canonical SQLite state."""
    db_file = tmp_path / "v2_import_block.db"
    store = _create_test_v2_db(db_file)
    store.close()

    raw_conn = sqlite3.connect(str(db_file))
    try:
        with pytest.raises(sqlite3.OperationalError):
            raw_conn.execute(
                "INSERT OR IGNORE INTO slices "
                "(id, timestamp, actor, source, content, mood_flag, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                ("id1", "ts", "user", "manual_feed", "txt", "neutral", "ts"),
            )
    finally:
        raw_conn.close()


def test_safe05_path_resolution_precedence(tmp_path: Path) -> None:
    """SAFE-05: Path resolution follows strict precedence without ambiguity."""
    # 1. Explicit argument has highest priority
    custom_dir = tmp_path / "custom_data"
    assert get_data_dir(custom_dir) == custom_dir.resolve()
    assert get_db_path(custom_dir) == custom_dir.resolve() / "companion_chronicle.db"
    assert get_jsonl_path(custom_dir) == custom_dir.resolve() / "raw_slices.jsonl"
    assert get_settings_path(custom_dir) == custom_dir.resolve() / "agent_settings.json"

    # 2. Environment variable COEVA_DATA_DIR has second priority
    env_dir = tmp_path / "env_data"
    with patch.dict(os.environ, {ENV_DATA_DIR: str(env_dir)}):
        assert get_data_dir() == env_dir.resolve()
        assert get_db_path() == env_dir.resolve() / "companion_chronicle.db"

    # 3. Canonical production data dir has third priority if present
    if CANONICAL_PROD_DATA_DIR.is_dir():
        with patch.dict(os.environ, {}, clear=True):
            # Ensure COEVA_DATA_DIR is unset
            os.environ.pop(ENV_DATA_DIR, None)
            resolved = get_data_dir()
            assert resolved == CANONICAL_PROD_DATA_DIR
            assert resolved.name == "data"
            assert (resolved / "companion_chronicle.db").is_file()
