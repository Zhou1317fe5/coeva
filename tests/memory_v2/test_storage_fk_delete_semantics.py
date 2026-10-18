"""Test Suite for Stage 1 Foreign Key Delete Semantics & Fail-Closed Guard.

Formal verification of:
- S1-D01: Raw slice referenced by semantic memory -> direct DELETE raw_slices fails closed
- S1-D02: Event skeleton referenced by semantic memory -> direct DELETE event fails closed
- S1-D03: Episode referenced by semantic memory -> direct DELETE episode fails closed
- S1-D04: Raw slice referenced by observation provenance -> direct DELETE fails closed
- S1-D05: Raw slice referenced by chapter provenance -> direct DELETE fails closed
- S1-D06: Explicit application-side cleanup in transaction -> base DELETE succeeds, FK check clean
- S1-D07: Pure ownership FK intentionally keeps CASCADE -> only structural child rows removed
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.memory.v2.entities import (
    ChapterMetadataEntity,
    ChapterSliceLinkEntity,
    EpisodeEntity,
    EpisodeSliceLinkEntity,
    EventSkeletonEntity,
    EvidenceReinforcementEntity,
    ObservationEntity,
    ObservationSliceLinkEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.store import ChronicleStoreV2


def test_s1_d01_raw_slice_referenced_by_semantic_memory_fails_closed(tmp_path: Path) -> None:
    """S1-D01: direct DELETE raw_slices fails closed when referenced by active semantic memory."""
    db_file = tmp_path / "d01.db"
    store = ChronicleStoreV2(db_file)
    try:
        # 1. Insert source slice and derived memory
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="slice_d01",
                occurred_at="2026-10-18T10:00:00+00:00",
                content="我喜欢在清晨散步",
                ingestion_dedup_key="k_d01",
            )
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_d01",
                category="preference",
                statement="用户喜欢在清晨散步",
                authority_class="user_asserted",
                scope="global",
                project_id="global",
                source_slice_id="slice_d01",
                valid_from="2026-10-18T10:00:00+00:00",
                validity_status="active",
            )
        )
        store.connection.commit()

        # 2. Direct DELETE on raw_slices must fail closed due to ON DELETE RESTRICT
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            store.connection.execute("DELETE FROM raw_slices WHERE slice_id = 'slice_d01';")
        assert (
            "FOREIGN KEY" in str(exc_info.value).upper()
            or "RESTRICT" in str(exc_info.value).upper()
        )
        store.connection.rollback()

        # 3. Verify semantic memory and provenance pointer remain completely intact
        mem = store.get_semantic_memory("mem_d01")
        assert mem is not None
        assert mem.source_slice_id == "slice_d01"
        assert store.get_raw_slice("slice_d01") is not None
    finally:
        store.close()


def test_s1_d02_event_skeleton_referenced_by_semantic_memory_fails_closed(tmp_path: Path) -> None:
    """S1-D02: direct DELETE event_skeletons fails closed when referenced by semantic memory."""
    db_file = tmp_path / "d02.db"
    store = ChronicleStoreV2(db_file)
    try:
        store.insert_event_skeleton(
            EventSkeletonEntity(
                event_id="evt_d02",
                occurred_at="2026-10-18T11:00:00+00:00",
                agent_id="pi-desktop",
                session_id="s_d02",
                event_type="test_run",
                retention_class="transient",
            )
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_d02",
                category="fact",
                statement="自动化测试套件通过",
                authority_class="system_observed",
                scope="project",
                project_id="coeva",
                source_event_id="evt_d02",
                valid_from="2026-10-18T11:00:00+00:00",
                validity_status="active",
            )
        )
        store.connection.commit()

        # Direct DELETE must fail closed
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute("DELETE FROM event_skeletons WHERE event_id = 'evt_d02';")
        store.connection.rollback()

        mem = store.get_semantic_memory("mem_d02")
        assert mem is not None
        assert mem.source_event_id == "evt_d02"
        assert store.get_event_skeleton("evt_d02") is not None
    finally:
        store.close()


def test_s1_d03_episode_referenced_by_semantic_memory_fails_closed(tmp_path: Path) -> None:
    """S1-D03: direct DELETE episodes fails closed when referenced by semantic memory."""
    db_file = tmp_path / "d03.db"
    store = ChronicleStoreV2(db_file)
    try:
        store.insert_episode(
            EpisodeEntity(
                episode_id="ep_d03",
                scope="project",
                project_id="coeva",
                started_at="2026-10-18T12:00:00+00:00",
                title_hint="长时攻关重构",
            )
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_d03",
                category="relationship_rule",
                statement="长时攻关时保持专注",
                authority_class="user_asserted",
                scope="project",
                project_id="coeva",
                source_episode_id="ep_d03",
                valid_from="2026-10-18T12:00:00+00:00",
                validity_status="active",
            )
        )
        store.connection.commit()

        # Direct DELETE of episode fails closed
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute("DELETE FROM episodes WHERE episode_id = 'ep_d03';")
        store.connection.rollback()

        mem = store.get_semantic_memory("mem_d03")
        assert mem is not None
        assert mem.source_episode_id == "ep_d03"
        assert store.get_episode("ep_d03") is not None
    finally:
        store.close()


def test_s1_d04_raw_slice_referenced_by_observation_provenance_fails_closed(
    tmp_path: Path,
) -> None:
    """S1-D04: direct DELETE raw_slices fails closed when referenced by observation link."""
    db_file = tmp_path / "d04.db"
    store = ChronicleStoreV2(db_file)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="slice_d04",
                occurred_at="2026-10-18T10:00:00+00:00",
                content="我更喜欢深色主题",
                ingestion_dedup_key="k_d04",
            )
        )
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_d04",
                scope="global",
                project_id="global",
                statement="用户倾向于使用深色界面主题",
                proof_count=1,
                status="active",
                created_at="2026-10-18T10:00:00+00:00",
                updated_at="2026-10-18T10:00:00+00:00",
            )
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(
                observation_id="obs_d04",
                slice_id="slice_d04",
                role="supporting",
                linked_at="2026-10-18T10:00:00+00:00",
            )
        )
        store.connection.commit()

        # Direct DELETE fails closed
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute("DELETE FROM raw_slices WHERE slice_id = 'slice_d04';")
        store.connection.rollback()

        assert store.get_raw_slice("slice_d04") is not None
        assert store.get_observation("obs_d04") is not None
    finally:
        store.close()


def test_s1_d05_raw_slice_referenced_by_chapter_provenance_fails_closed(
    tmp_path: Path,
) -> None:
    """S1-D05: direct DELETE raw_slices fails closed when cited by chapter metadata link."""
    db_file = tmp_path / "d05.db"
    store = ChronicleStoreV2(db_file)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="slice_d05",
                occurred_at="2026-10-18T10:00:00+00:00",
                content="最初写下的代码段",
                ingestion_dedup_key="k_d05",
            )
        )
        store.insert_chapter_metadata(
            ChapterMetadataEntity(
                chapter_id="ch_d05",
                title="初心篇章",
                file_path="docs/chapters/ch01.md",
                time_span_start="2026-10-01T00:00:00+00:00",
                time_span_end="2026-10-18T23:59:59+00:00",
                needs_privacy_redaction=0,
                created_at="2026-10-18T10:00:00+00:00",
            )
        )
        store.insert_chapter_slice_link(
            ChapterSliceLinkEntity(
                chapter_id="ch_d05",
                slice_id="slice_d05",
                linked_at="2026-10-18T10:00:00+00:00",
            )
        )
        store.connection.commit()

        # Direct DELETE of raw slice cited by chapter must fail closed
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute("DELETE FROM raw_slices WHERE slice_id = 'slice_d05';")
        store.connection.rollback()

        assert store.get_raw_slice("slice_d05") is not None
        assert store.get_chapter_metadata("ch_d05") is not None
    finally:
        store.close()


def test_s1_d06_application_side_dependency_cleanup_allows_base_delete(
    tmp_path: Path,
) -> None:
    """S1-D06: explicit application-side cleanup in one transaction allows base delete."""
    db_file = tmp_path / "d06.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Set up slice with memory, reinforcement, and chapter link
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="slice_d06",
                occurred_at="2026-10-18T10:00:00+00:00",
                content="待删除的敏感内容",
                ingestion_dedup_key="k_d06",
            )
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_d06",
                category="fact",
                statement="从敏感切片派生的事实",
                authority_class="user_asserted",
                scope="global",
                project_id="global",
                source_slice_id="slice_d06",
                valid_from="2026-10-18T10:00:00+00:00",
                validity_status="active",
            )
        )
        store.insert_evidence_reinforcement(
            EvidenceReinforcementEntity(
                reinforcement_id="reinf_d06",
                memory_id="mem_d06",
                slice_id="slice_d06",
                independence_fingerprint="fp_d06",
                occurred_at="2026-10-18T10:00:00+00:00",
            )
        )
        store.insert_chapter_metadata(
            ChapterMetadataEntity(
                chapter_id="ch_d06",
                title="受影响章节",
                file_path="docs/chapters/ch02.md",
                time_span_start="2026-10-01T00:00:00+00:00",
                time_span_end="2026-10-18T23:59:59+00:00",
                needs_privacy_redaction=0,
                created_at="2026-10-18T10:00:00+00:00",
            )
        )
        store.insert_chapter_slice_link(
            ChapterSliceLinkEntity(
                chapter_id="ch_d06",
                slice_id="slice_d06",
                linked_at="2026-10-18T10:00:00+00:00",
            )
        )
        store.connection.commit()

        # Step-by-step application transaction simulating Stage 3 lifecycle
        with store.transaction():
            # 1. Redact chapter & remove citation link
            store.connection.execute(
                "UPDATE chapter_metadata SET needs_privacy_redaction = 1 "
                "WHERE chapter_id = 'ch_d06';"
            )
            store.connection.execute(
                "DELETE FROM chapter_slice_links "
                "WHERE chapter_id = 'ch_d06' AND slice_id = 'slice_d06';"
            )

            # 2. Retract / delete dependent semantic memory and reinforcement
            store.connection.execute(
                "DELETE FROM evidence_reinforcements WHERE reinforcement_id = 'reinf_d06';"
            )
            store.connection.execute("DELETE FROM semantic_memories WHERE memory_id = 'mem_d06';")

            # 3. Finally delete base evidence
            store.connection.execute("DELETE FROM raw_slices WHERE slice_id = 'slice_d06';")

        # Verify base slice is removed and database foreign key checks are 100% clean
        assert store.get_raw_slice("slice_d06") is None
        assert store.get_semantic_memory("mem_d06") is None
        ch = store.get_chapter_metadata("ch_d06")
        assert ch is not None
        assert ch.needs_privacy_redaction == 1
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


def test_s1_d07_pure_ownership_cascade_preserves_independent_evidence(
    tmp_path: Path,
) -> None:
    """S1-D07: parent container delete cascades only structural child links, preserving evidence."""
    db_file = tmp_path / "d07.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Create base evidence
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="slice_d07",
                occurred_at="2026-10-18T10:00:00+00:00",
                content="经历中的一段切片",
                ingestion_dedup_key="k_d07",
            )
        )
        # Create episode container linking to slice
        store.insert_episode(
            EpisodeEntity(
                episode_id="ep_d07",
                scope="project",
                project_id="coeva",
                started_at="2026-10-18T10:00:00+00:00",
                title_hint="临时经历容器",
            )
        )
        store.insert_episode_slice_link(
            EpisodeSliceLinkEntity(
                episode_id="ep_d07",
                slice_id="slice_d07",
                curation_source="system",
                linked_at="2026-10-18T10:00:00+00:00",
            )
        )
        store.connection.commit()

        # Pure ownership edge: deleting episode cascades and removes only episode_slice_links
        store.connection.execute("DELETE FROM episodes WHERE episode_id = 'ep_d07';")
        store.connection.commit()

        assert store.get_episode("ep_d07") is None
        # Structural link row was cleanly cascaded
        links = store.connection.execute(
            "SELECT * FROM episode_slice_links WHERE episode_id = 'ep_d07';"
        ).fetchall()
        assert len(links) == 0

        # Base evidence raw_slice is 100% PRESERVED!
        slice_record = store.get_raw_slice("slice_d07")
        assert slice_record is not None
        assert slice_record.content == "经历中的一段切片"
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()
