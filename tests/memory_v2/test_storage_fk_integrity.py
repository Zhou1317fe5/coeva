"""Unit tests for Foreign Key enforcement and enum constraints on V2.1 storage.

Part of Stage 1 (WP-1, Section 12, 13).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.memory.v2.entities import (
    EpisodeEventLinkEntity,
    EpisodeSliceLinkEntity,
    RawSliceEntity,
)
from src.memory.v2.store import ChronicleStoreV2


def test_missing_foreign_key_fails(tmp_path: Path) -> None:
    """Verify that inserting a link pointing to a non-existent entity raises IntegrityError."""
    db_file = tmp_path / "fk_missing.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Attempt to link a non-existent episode and non-existent slice
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_episode_slice_link(
                EpisodeSliceLinkEntity(
                    episode_id="ep_ghost",
                    slice_id="slice_ghost",
                    linked_at="2026-10-18T10:00:00+00:00",
                )
            )
            store.connection.commit()
    finally:
        store.close()


def test_typed_relation_cannot_point_to_arbitrary_id(tmp_path: Path) -> None:
    """Verify that typed links strictly require target entity IDs of matching types."""
    db_file = tmp_path / "fk_typed_target.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Create a slice
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="slice_valid",
                occurred_at="2026-10-18T10:00:00+00:00",
                content="测试原话",
                ingestion_dedup_key="key_valid",
            )
        )
        store.connection.commit()

        # Attempt to insert episode_event_link using slice_id as event_id -> must fail!
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_episode_event_link(
                EpisodeEventLinkEntity(
                    episode_id="ep_any",
                    event_id="slice_valid",  # Invalid! Not in event_skeletons
                    linked_at="2026-10-18T10:00:00+00:00",
                )
            )
            store.connection.commit()
    finally:
        store.close()


def test_raw_slices_scope_check_constraint(tmp_path: Path) -> None:
    """Verify SQLite CHECK constraints on raw_slices scope and project_id rules."""
    db_file = tmp_path / "check_scope.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Invalid 1: scope='unresolved' but project_id is NOT NULL -> violates CHECK!
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                """
                INSERT INTO raw_slices (
                    slice_id, occurred_at, content, actor, source, scope, project_id,
                    ingestion_dedup_key, created_at
                ) VALUES ('s_bad1', '2026-10-18T10:00:00+00:00', '内容', 'user', 'manual_feed',
                          'unresolved', 'some_project', 'k_bad1', '2026-10-18T10:00:00+00:00');
                """
            )
            store.connection.commit()

        # Invalid 2: scope='global' but project_id is NOT 'global' -> violates CHECK!
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                """
                INSERT INTO raw_slices (
                    slice_id, occurred_at, content, actor, source, scope, project_id,
                    ingestion_dedup_key, created_at
                ) VALUES ('s_bad2', '2026-10-18T10:00:00+00:00', '内容', 'user', 'manual_feed',
                          'global', 'local_proj', 'k_bad2', '2026-10-18T10:00:00+00:00');
                """
            )
            store.connection.commit()

        # Invalid 3: illegal enum value for actor -> violates CHECK!
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                """
                INSERT INTO raw_slices (
                    slice_id, occurred_at, content, actor, source, scope, project_id,
                    ingestion_dedup_key, created_at
                ) VALUES ('s_bad3', '2026-10-18T10:00:00+00:00', '内容', 'admin', 'manual_feed',
                          'unresolved', NULL, 'k_bad3', '2026-10-18T10:00:00+00:00');
                """
            )
            store.connection.commit()
    finally:
        store.close()


def test_observation_role_check_constraint(tmp_path: Path) -> None:
    """Verify that observation_slice_links role must be supporting or counter."""
    db_file = tmp_path / "check_role.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Attempt to insert role='contextual' in observation_slice_links -> violates CHECK!
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                """
                INSERT INTO observation_slice_links (observation_id, slice_id, role, linked_at)
                VALUES ('obs1', 's1', 'invalid_role', '2026-10-18T10:00:00+00:00');
                """
            )
            store.connection.commit()
    finally:
        store.close()
