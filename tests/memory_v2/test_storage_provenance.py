"""Unit tests for IMPL-2 Semantic Memory Provenance Conformance.

Verifies:
- S1-P01: Raw Slice-backed semantic memory (FK-safe, reverse traversal)
- S1-P02: Event Skeleton-backed semantic memory (FK-safe, reverse traversal)
- S1-P03: Episode-backed semantic memory (FK-safe, reverse traversal)
- S1-P04: Zero-provenance semantic memory fails closed
- S1-P05: Invalid provenance ID fails closed
- S1-P06: Source impact reverse traversal without pseudo-polymorphism
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.memory.v2.entities import (
    EpisodeEntity,
    EventSkeletonEntity,
    EvidenceReinforcementEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.store import ChronicleStoreV2


def test_s1_p01_raw_slice_provenance_reverse_traversal(tmp_path: Path) -> None:
    """S1-P01: Raw Slice-backed semantic memory has valid FK and deterministic reverse traversal."""
    db_file = tmp_path / "p01.db"
    store = ChronicleStoreV2(db_file)
    try:
        # 1. Insert source slice
        slice_item = RawSliceEntity(
            slice_id="slice_p01",
            occurred_at="2026-10-18T10:00:00+00:00",
            content="我习惯在每天早上9点看邮件",
            ingestion_dedup_key="k_p01",
        )
        store.insert_raw_slice(slice_item)

        # 2. Derive semantic memory from slice
        mem = SemanticMemoryEntity(
            memory_id="mem_p01",
            category="preference",
            statement="用户习惯在早上9点处理日常邮件",
            authority_class="user_asserted",
            scope="global",
            project_id="global",
            source_slice_id="slice_p01",
            source_event_id=None,
            source_episode_id=None,
            valid_from="2026-10-18T10:00:00+00:00",
            validity_status="active",
        )
        store.insert_semantic_memory(mem)
        store.connection.commit()

        # 3. Verify reverse traversal finds memory from slice_id
        affected = store.get_memories_by_source_slice("slice_p01")
        assert len(affected) == 1
        assert affected[0].memory_id == "mem_p01"
        assert affected[0].source_slice_id == "slice_p01"

        # 4. Verify structured ProvenanceRef
        refs = store.get_provenance_refs_for_memory("mem_p01")
        assert len(refs) == 1
        assert refs[0]["kind"] == "slice"
        assert refs[0]["id"] == "slice_p01"
    finally:
        store.close()


def test_s1_p02_event_skeleton_provenance_reverse_traversal(tmp_path: Path) -> None:
    """S1-P02: Event Skeleton-backed semantic memory has valid FK and reverse traversal."""
    db_file = tmp_path / "p02.db"
    store = ChronicleStoreV2(db_file)
    try:
        # 1. Insert source event skeleton
        event_item = EventSkeletonEntity(
            event_id="evt_p02",
            occurred_at="2026-10-18T11:00:00+00:00",
            agent_id="pi-desktop",
            session_id="sess_p02",
            event_type="tool_failure",
            tool_name="git",
            error_category="MergeConflict",
            retention_class="transient",
        )
        store.insert_event_skeleton(event_item)

        # 2. Derive semantic memory directly from event
        mem = SemanticMemoryEntity(
            memory_id="mem_p02",
            category="fact",
            statement="本次发布分支在 git rebase 中发生合并冲突",
            authority_class="system_observed",
            scope="project",
            project_id="coeva",
            source_slice_id=None,
            source_event_id="evt_p02",
            source_episode_id=None,
            valid_from="2026-10-18T11:00:00+00:00",
            validity_status="active",
        )
        store.insert_semantic_memory(mem)
        store.connection.commit()

        # 3. Verify reverse traversal finds memory from event_id
        affected = store.get_memories_by_source_event("evt_p02")
        assert len(affected) == 1
        assert affected[0].memory_id == "mem_p02"
        assert affected[0].source_event_id == "evt_p02"

        # 4. Verify structured ProvenanceRef
        refs = store.get_provenance_refs_for_memory("mem_p02")
        assert len(refs) == 1
        assert refs[0]["kind"] == "event"
        assert refs[0]["id"] == "evt_p02"
    finally:
        store.close()


def test_s1_p03_episode_provenance_reverse_traversal(tmp_path: Path) -> None:
    """S1-P03: Episode-backed semantic memory has valid FK and deterministic reverse traversal."""
    db_file = tmp_path / "p03.db"
    store = ChronicleStoreV2(db_file)
    try:
        # 1. Insert source episode
        ep = EpisodeEntity(
            episode_id="ep_p03",
            scope="project",
            project_id="coeva",
            started_at="2026-10-18T09:00:00+00:00",
            title_hint="长会话攻关重构",
            status="closed",
        )
        store.insert_episode(ep)

        # 2. Derive semantic memory directly from episode context
        mem = SemanticMemoryEntity(
            memory_id="mem_p03",
            category="relationship_rule",
            statement="在长会话集中攻关期间伴生体应保持静默陪伴",
            authority_class="user_asserted",
            scope="project",
            project_id="coeva",
            source_slice_id=None,
            source_event_id=None,
            source_episode_id="ep_p03",
            valid_from="2026-10-18T09:00:00+00:00",
            validity_status="active",
        )
        store.insert_semantic_memory(mem)
        store.connection.commit()

        # 3. Verify reverse traversal finds memory from episode_id
        affected = store.get_memories_by_source_episode("ep_p03")
        assert len(affected) == 1
        assert affected[0].memory_id == "mem_p03"
        assert affected[0].source_episode_id == "ep_p03"

        # 4. Verify structured ProvenanceRef
        refs = store.get_provenance_refs_for_memory("mem_p03")
        assert len(refs) == 1
        assert refs[0]["kind"] == "episode"
        assert refs[0]["id"] == "ep_p03"
    finally:
        store.close()


def test_s1_p04_zero_provenance_semantic_memory_fails_closed(tmp_path: Path) -> None:
    """S1-P04: semantic memory with zero effective provenance is rejected by CHECK constraint."""
    db_file = tmp_path / "p04.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Attempt to insert a memory with all source pointers NULL
        orphan_mem = SemanticMemoryEntity(
            memory_id="mem_zero_prov",
            category="fact",
            statement="凭空凭想出来的孤儿事实",
            authority_class="system_observed",
            scope="global",
            project_id="global",
            source_slice_id=None,
            source_event_id=None,
            source_episode_id=None,
            valid_from="2026-10-18T10:00:00+00:00",
            validity_status="active",
        )
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            store.insert_semantic_memory(orphan_mem)
            store.connection.commit()
        # CHECK constraint failure
        assert "CHECK" in str(exc_info.value).upper() or "CONSTRAINT" in str(exc_info.value).upper()
    finally:
        store.close()


def test_s1_p05_invalid_provenance_id_fails_closed(tmp_path: Path) -> None:
    """S1-P05: invalid provenance ID pointing to non-existent parent raises IntegrityError."""
    db_file = tmp_path / "p05.db"
    store = ChronicleStoreV2(db_file)
    try:
        # 1. Invalid slice ID
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_semantic_memory(
                SemanticMemoryEntity(
                    memory_id="mem_bad_slice",
                    category="fact",
                    statement="测试事实",
                    authority_class="user_asserted",
                    scope="global",
                    project_id="global",
                    source_slice_id="non_existent_slice_id",
                    valid_from="2026-10-18T10:00:00+00:00",
                    validity_status="active",
                )
            )
            store.connection.commit()

        # 2. Invalid event ID
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_semantic_memory(
                SemanticMemoryEntity(
                    memory_id="mem_bad_event",
                    category="fact",
                    statement="测试事实",
                    authority_class="system_observed",
                    scope="global",
                    project_id="global",
                    source_event_id="non_existent_event_id",
                    valid_from="2026-10-18T10:00:00+00:00",
                    validity_status="active",
                )
            )
            store.connection.commit()

        # 3. Invalid episode ID
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_semantic_memory(
                SemanticMemoryEntity(
                    memory_id="mem_bad_ep",
                    category="fact",
                    statement="测试事实",
                    authority_class="system_observed",
                    scope="global",
                    project_id="global",
                    source_episode_id="non_existent_ep_id",
                    valid_from="2026-10-18T10:00:00+00:00",
                    validity_status="active",
                )
            )
            store.connection.commit()
    finally:
        store.close()


def test_s1_p06_source_impact_reverse_traversal_without_pseudo_polymorphism(
    tmp_path: Path,
) -> None:
    """S1-P06: source impact identifies dependent memory without source_type strings."""
    db_file = tmp_path / "p06.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Insert evidence
        slice_a = RawSliceEntity(
            slice_id="sa",
            occurred_at="2026-10-18T10:00:00+00:00",
            content="A",
            ingestion_dedup_key="ka",
        )
        event_b = EventSkeletonEntity(
            event_id="eb",
            occurred_at="2026-10-18T10:01:00+00:00",
            agent_id="p",
            session_id="s",
            event_type="t",
            retention_class="transient",
        )
        store.insert_raw_slice(slice_a)
        store.insert_event_skeleton(event_b)

        # Insert derived memories
        mem_a = SemanticMemoryEntity(
            memory_id="ma",
            category="fact",
            statement="A的事实",
            authority_class="user_asserted",
            scope="global",
            project_id="global",
            source_slice_id="sa",
            valid_from="2026-10-18T10:00:00+00:00",
            validity_status="active",
        )
        mem_b = SemanticMemoryEntity(
            memory_id="mb",
            category="fact",
            statement="B的事实",
            authority_class="system_observed",
            scope="global",
            project_id="global",
            source_event_id="eb",
            valid_from="2026-10-18T10:01:00+00:00",
            validity_status="active",
        )
        store.insert_semantic_memory(mem_a)
        store.insert_semantic_memory(mem_b)

        # Multi-source reinforcement: mem_a is also reinforced by event_b
        reinf = EvidenceReinforcementEntity(
            reinforcement_id="r_ab",
            memory_id="ma",
            event_id="eb",
            independence_fingerprint="fp_ab",
            occurred_at="2026-10-18T10:02:00+00:00",
        )
        store.insert_evidence_reinforcement(reinf)
        store.connection.commit()

        # Reverse traversal query for slice_a finds ma (primary)
        mems_from_sa = store.get_memories_by_source_slice("sa")
        assert len(mems_from_sa) == 1
        assert mems_from_sa[0].memory_id == "ma"

        # Reverse traversal query for event_b finds mb (primary) and ma (via reinforcement)
        mems_from_eb = store.get_memories_by_source_event("eb")
        assert len(mems_from_eb) == 1
        assert mems_from_eb[0].memory_id == "mb"

        refs_ma = store.get_provenance_refs_for_memory("ma")
        # ma has slice primary + event reinforcement!
        kinds = {r["kind"] for r in refs_ma}
        assert "slice" in kinds
        assert "event" in kinds

        # Direct DELETE fails closed with IntegrityError (semantic_memories ON DELETE RESTRICT)
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute("DELETE FROM raw_slices WHERE slice_id = 'sa';")
        store.connection.rollback()
        with store.transaction():
            store.connection.execute(
                "DELETE FROM evidence_reinforcements WHERE reinforcement_id = 'r_ab';"
            )
            store.connection.execute("DELETE FROM semantic_memories WHERE memory_id = 'ma';")
            store.connection.execute("DELETE FROM raw_slices WHERE slice_id = 'sa';")

        assert store.get_semantic_memory("ma") is None
        # mem_b remains untouched!
        assert store.get_semantic_memory("mb") is not None
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()
