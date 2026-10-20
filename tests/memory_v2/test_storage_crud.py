"""Unit tests for typed CRUD primitives on V2.1 storage layer.

Part of Stage 1 (WP-1, Section 7, 8, 9, 10, 11).
"""

from __future__ import annotations

from pathlib import Path

from src.memory.v2.entities import (
    CalibrationEventEntity,
    ChapterMetadataEntity,
    ConfirmedInsightEntity,
    EpisodeEntity,
    EpisodeEventLinkEntity,
    EpisodeSliceLinkEntity,
    EventSkeletonEntity,
    EvidenceReinforcementEntity,
    HypothesisEntity,
    HypothesisObservationLinkEntity,
    ObservationEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.store import ChronicleStoreV2


def test_raw_slice_crud(tmp_path: Path) -> None:
    """Verify RawSliceEntity insertion, query, and unresolved scope constraints."""
    db_file = tmp_path / "crud_slices.db"
    store = ChronicleStoreV2(db_file)
    try:
        item = RawSliceEntity(
            slice_id="slice_001",
            occurred_at="2026-10-18T10:00:00+00:00",
            content="用户原始输入：今天天气晴朗，很适合敲代码",
            actor="user",
            source="manual_feed",
            scope="unresolved",
            project_id=None,
            ingestion_dedup_key="key_001",
            created_at="2026-10-18T10:00:05+00:00",
        )
        store.insert_raw_slice(item)
        store.connection.commit()

        # Query back
        retrieved = store.get_raw_slice("slice_001")
        assert retrieved is not None
        assert retrieved.slice_id == "slice_001"
        assert retrieved.content == "用户原始输入：今天天气晴朗，很适合敲代码"
        assert retrieved.scope == "unresolved"
        assert retrieved.project_id is None

        # List query
        all_slices = store.list_raw_slices()
        assert len(all_slices) == 1
        assert all_slices[0].slice_id == "slice_001"
    finally:
        store.close()


def test_event_skeleton_privacy_boundary(tmp_path: Path) -> None:
    """Verify EventSkeletonEntity insertion respecting privacy boundaries (no prompt/CoT)."""
    db_file = tmp_path / "crud_events.db"
    store = ChronicleStoreV2(db_file)
    try:
        evt = EventSkeletonEntity(
            event_id="evt_sha1_hash_001",
            occurred_at="2026-10-18T10:05:00+00:00",
            agent_id="pi-desktop",
            session_id="sess_123",
            event_type="tool_failure",
            tool_name="bash",
            error_category="TimeoutError",
            retention_class="transient",
            created_at="2026-10-18T10:05:01+00:00",
        )
        store.insert_event_skeleton(evt)
        store.connection.commit()

        retrieved = store.get_event_skeleton("evt_sha1_hash_001")
        assert retrieved is not None
        assert retrieved.agent_id == "pi-desktop"
        assert retrieved.tool_name == "bash"
        assert retrieved.error_category == "TimeoutError"
        assert retrieved.retention_class == "transient"
    finally:
        store.close()


def test_episodes_and_typed_links_crud(tmp_path: Path) -> None:
    """Verify Episode and typed relation links (episode_slice_links, episode_event_links)."""
    db_file = tmp_path / "crud_episodes.db"
    store = ChronicleStoreV2(db_file)
    try:
        # Pre-insert slice and event
        slice_item = RawSliceEntity(
            slice_id="s1",
            occurred_at="2026-10-18T09:00:00+00:00",
            content="切片1",
            ingestion_dedup_key="k1",
        )
        event_item = EventSkeletonEntity(
            event_id="e1",
            occurred_at="2026-10-18T09:01:00+00:00",
            agent_id="pi",
            session_id="s123",
            event_type="pre_tool_use",
            retention_class="transient",
        )
        store.insert_raw_slice(slice_item)
        store.insert_event_skeleton(event_item)

        # Insert episode
        ep = EpisodeEntity(
            episode_id="ep_001",
            scope="project",
            project_id="companion",
            started_at="2026-10-18T09:00:00+00:00",
            title_hint="调试 PySide 窗口布局",
            summary="排查了窗口缩放和边框贴边问题",
            status="open",
        )
        store.insert_episode(ep)

        # Insert links
        store.insert_episode_slice_link(
            EpisodeSliceLinkEntity(
                episode_id="ep_001", slice_id="s1", linked_at="2026-10-18T09:02:00+00:00"
            )
        )
        store.insert_episode_event_link(
            EpisodeEventLinkEntity(
                episode_id="ep_001", event_id="e1", linked_at="2026-10-18T09:02:00+00:00"
            )
        )
        store.connection.commit()

        # Query back
        retrieved_ep = store.get_episode("ep_001")
        assert retrieved_ep is not None
        assert retrieved_ep.title_hint == "调试 PySide 窗口布局"
        assert retrieved_ep.project_id == "companion"
    finally:
        store.close()


def test_semantic_memory_and_reinforcement_crud(tmp_path: Path) -> None:
    """Verify SemanticMemoryEntity and evidence reinforcement ledger."""
    db_file = tmp_path / "crud_semantic.db"
    store = ChronicleStoreV2(db_file)
    try:
        slice_item = RawSliceEntity(
            slice_id="s_pref",
            occurred_at="2026-10-18T10:00:00+00:00",
            content="我喜欢在安静的时候写代码",
            ingestion_dedup_key="k_pref",
        )
        store.insert_raw_slice(slice_item)

        mem = SemanticMemoryEntity(
            memory_id="mem_001",
            category="preference",
            statement="用户偏好在安静无打扰的环境下编写代码",
            authority_class="user_asserted",
            scope="global",
            project_id="global",
            source_slice_id="s_pref",
            valid_from="2026-10-18T10:00:00+00:00",
            validity_status="active",
            expression_policy="normal",
        )
        store.insert_semantic_memory(mem)

        reinf = EvidenceReinforcementEntity(
            reinforcement_id="reinf_001",
            memory_id="mem_001",
            slice_id="s_pref",
            independence_fingerprint="fp_session_1",
            occurred_at="2026-10-18T10:00:00+00:00",
        )
        store.insert_evidence_reinforcement(reinf)
        store.connection.commit()

        retrieved_mem = store.get_semantic_memory("mem_001")
        assert retrieved_mem is not None
        assert retrieved_mem.category == "preference"
        assert retrieved_mem.source_slice_id == "s_pref"
        assert retrieved_mem.validity_status == "active"
    finally:
        store.close()


def test_observation_and_hypothesis_calibration_crud(tmp_path: Path) -> None:
    """Verify Observation, Hypothesis, Calibration Event, and Confirmed Insight CRUD."""
    db_file = tmp_path / "crud_understanding.db"
    store = ChronicleStoreV2(db_file)
    try:
        # 1. Observation
        obs = ObservationEntity(
            observation_id="obs_001",
            scope="project",
            project_id="coeva",
            statement="用户在遇到编译错误时习惯先通读报错日志",
            proof_count=2,
            status="active",
            created_at="2026-10-18T11:00:00+00:00",
        )
        store.insert_observation(obs)

        # 2. Hypothesis
        hyp = HypothesisEntity(
            hypothesis_id="hyp_001",
            statement="用户具备高理性调节灵活性，排错时先沉着分析",
            lenses="regulatory_flexibility",
            confidence_class="tentative",
            status="candidate",
            created_at="2026-10-18T11:05:00+00:00",
        )
        store.insert_hypothesis(hyp)

        store.insert_hypothesis_observation_link(
            HypothesisObservationLinkEntity(
                hypothesis_id="hyp_001",
                observation_id="obs_001",
                role="supporting",
                is_primary=1,
                linked_at="2026-10-18T11:05:00+00:00",
            )
        )

        # 3. Calibration Event
        calib = CalibrationEventEntity(
            calibration_id="calib_001",
            hypothesis_id="hyp_001",
            user_action="yes",
            user_note="确实如此",
            calibrated_at="2026-10-18T11:10:00+00:00",
        )
        store.insert_calibration_event(calib)

        # 4. Confirmed Insight
        insight = ConfirmedInsightEntity(
            insight_id="ins_001",
            source_hypothesis_id="hyp_001",
            source_calibration_id="calib_001",
            statement="用户具备高理性调节灵活性，排错时先沉着分析",
            valid_from="2026-10-18T11:10:00+00:00",
            status="confirmed",
        )
        store.insert_confirmed_insight(insight)
        store.connection.commit()

        # Check retrievals
        assert store.get_observation("obs_001") is not None
        assert store.get_hypothesis("hyp_001") is not None
        retrieved_ins = store.get_confirmed_insight("ins_001")
        assert retrieved_ins is not None
        assert retrieved_ins.status == "confirmed"
    finally:
        store.close()


def test_chapter_metadata_and_links_crud(tmp_path: Path) -> None:
    """Verify Chapter Metadata and its typed cross-domain links."""
    db_file = tmp_path / "crud_chapters.db"
    store = ChronicleStoreV2(db_file)
    try:
        chap = ChapterMetadataEntity(
            chapter_id="chap_01",
            title="第一章：共生伙伴的初次探索",
            file_path="chapters/chapter_01.md",
            time_span_start="2026-10-01T00:00:00+00:00",
            time_span_end="2026-10-18T00:00:00+00:00",
            needs_privacy_redaction=0,
            created_at="2026-10-18T12:00:00+00:00",
        )
        store.insert_chapter_metadata(chap)
        store.connection.commit()

        row = store.connection.execute(
            "SELECT * FROM chapter_metadata WHERE chapter_id = 'chap_01';"
        ).fetchone()
        assert row is not None
        assert row["title"] == "第一章：共生伙伴的初次探索"
        assert row["needs_privacy_redaction"] == 0
    finally:
        store.close()
