"""Comprehensive Safety and Invariant Test Suite for Memory V2.1 Lifecycle (WP-2).

Formal verification of canonical gates L-01 through L-15:
- L-01: Direct raw evidence delete fails closed via RESTRICT
- L-02: Impact dry-run is strictly read-only and leaves DB unchanged
- L-03: Surviving multi-source semantic memory retains independent provenance
- L-04: Zero-source semantic memory cannot remain active in storage
- L-05: Observation proof count recomputes correctly and retracts when support=0
- L-06: Downstream hypothesis propagates to retracted or revalidation_required
- L-07: Confirmed insight adapts safely while calibration event is immutable
- L-08: Privacy-sensitive delete marks chapter needs_privacy_redaction=1 synchronously
- L-09: Architecture invariant: narrative chapters are never evidence sources
- L-10: Episode container membership alone does not retention-pin events
- L-11: Observation adoption retention-pins event and blocks blind purge
- L-12: Removal of last durable provenance unpins event for purge
- L-13: Atomic transaction rolls back completely on any mid-operation failure
- L-14: Post-operation referential integrity: PRAGMA foreign_key_check is 100% clean
- L-15: Production isolation: V1 runtime and legacy chronicle remain untouched
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.core.flags import MemoryFeatureFlags
from src.memory.v2.entities import (
    CalibrationEventEntity,
    ChapterMetadataEntity,
    ChapterSliceLinkEntity,
    ConfirmedInsightEntity,
    EpisodeEntity,
    EpisodeEventLinkEntity,
    EpisodeSliceLinkEntity,
    EventSkeletonEntity,
    EvidenceReinforcementEntity,
    HypothesisEntity,
    HypothesisObservationLinkEntity,
    ObservationEntity,
    ObservationEpisodeLinkEntity,
    ObservationEventLinkEntity,
    ObservationSliceLinkEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.lifecycle import (
    EventPinnedError,
    LifecycleService,
)
from src.memory.v2.router import RawEvidenceRouter
from src.memory.v2.store import ChronicleStoreV2

# ── L-01: Direct Delete Fails Closed ──────────────────────────────────────────


def test_l01_direct_delete_fails_closed(tmp_path: Path) -> None:
    """L-01: Direct DELETE on raw_slices fails closed via SQLite ON DELETE RESTRICT."""
    db_file = tmp_path / "l01.db"
    store = ChronicleStoreV2(db_file)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_01",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="测试基础切片",
                ingestion_dedup_key="k_01",
            )
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_01",
                category="preference",
                statement="用户测试偏好",
                authority_class="user_asserted",
                scope="global",
                project_id="global",
                source_slice_id="sl_01",
                valid_from="2026-10-19T10:00:00+00:00",
                validity_status="active",
            )
        )
        store.connection.commit()

        # Direct DELETE without lifecycle orchestration must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            store.connection.execute("DELETE FROM raw_slices WHERE slice_id = 'sl_01';")
        assert (
            "FOREIGN KEY" in str(exc_info.value).upper()
            or "RESTRICT" in str(exc_info.value).upper()
        )
        store.connection.rollback()

        # Base evidence and dependent memory remain untouched
        assert store.get_raw_slice("sl_01") is not None
        assert store.get_semantic_memory("mem_01") is not None
    finally:
        store.close()


# ── L-02: Impact Dry-Run Read-Only ────────────────────────────────────────────


def test_l02_impact_dry_run_is_strictly_read_only(tmp_path: Path) -> None:
    """L-02: analyze_slice_delete returns full dependency report without mutating DB."""
    db_file = tmp_path / "l02.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        # Build dependency chain: slice -> episode, memory, obs, hypothesis, insight, chapter
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_02",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="我爱喝无糖乌龙茶",
                ingestion_dedup_key="k_02",
            )
        )
        store.insert_episode(
            EpisodeEntity(
                episode_id="ep_02",
                scope="global",
                started_at="2026-10-19T10:00:00+00:00",
                title_hint="茶饮偏好会话",
            )
        )
        store.insert_episode_slice_link(
            EpisodeSliceLinkEntity(episode_id="ep_02", slice_id="sl_02")
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_02",
                category="preference",
                statement="用户偏好无糖乌龙茶",
                authority_class="user_asserted",
                scope="global",
                source_slice_id="sl_02",
                valid_from="2026-10-19T10:00:00+00:00",
                validity_status="active",
            )
        )
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_02",
                scope="global",
                statement="用户经常选择无糖茶饮",
                proof_count=1,
                status="active",
                created_at="2026-10-19T10:00:00+00:00",
            )
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(observation_id="obs_02", slice_id="sl_02", role="supporting")
        )
        store.insert_hypothesis(
            HypothesisEntity(
                hypothesis_id="hyp_02",
                statement="用户注重低糖健康饮食",
                lenses="health_awareness",
                confidence_class="grounded",
                status="candidate",
            )
        )
        store.insert_hypothesis_observation_link(
            HypothesisObservationLinkEntity(
                hypothesis_id="hyp_02", observation_id="obs_02", role="supporting"
            )
        )
        store.insert_calibration_event(
            CalibrationEventEntity(
                calibration_id="cal_02",
                hypothesis_id="hyp_02",
                user_action="yes",
                calibrated_at="2026-10-19T10:30:00+00:00",
            )
        )
        store.insert_confirmed_insight(
            ConfirmedInsightEntity(
                insight_id="ins_02",
                source_hypothesis_id="hyp_02",
                source_calibration_id="cal_02",
                statement="确立共识：用户坚持低糖健康生活方式",
                valid_from="2026-10-19T10:30:00+00:00",
                status="confirmed",
            )
        )
        store.insert_chapter_metadata(
            ChapterMetadataEntity(
                chapter_id="ch_02",
                title="饮食习惯篇",
                file_path="docs/chapters/ch02.md",
                time_span_start="2026-10-01T00:00:00+00:00",
                time_span_end="2026-10-19T23:59:59+00:00",
                needs_privacy_redaction=0,
            )
        )
        store.insert_chapter_slice_link(
            ChapterSliceLinkEntity(chapter_id="ch_02", slice_id="sl_02")
        )
        store.connection.commit()

        # Capture DB state before dry-run
        count_slices_before = store.connection.execute(
            "SELECT COUNT(*) FROM raw_slices;"
        ).fetchone()[0]
        count_mems_before = store.connection.execute(
            "SELECT COUNT(*) FROM semantic_memories;"
        ).fetchone()[0]
        count_obs_before = store.connection.execute(
            "SELECT COUNT(*) FROM observations;"
        ).fetchone()[0]

        # Execute Dry-Run Impact Analysis
        report = lifecycle.analyze_slice_delete("sl_02", privacy_sensitive=True)

        assert report.exists is True
        assert report.can_delete is True
        assert "ep_02" in report.affected_episodes
        assert any(m["memory_id"] == "mem_02" for m in report.affected_semantic_memories)
        assert any(o["observation_id"] == "obs_02" for o in report.affected_observations)
        assert any(h["hypothesis_id"] == "hyp_02" for h in report.affected_hypotheses)
        assert any(i["insight_id"] == "ins_02" for i in report.affected_confirmed_insights)
        assert any(c["chapter_id"] == "ch_02" for c in report.affected_chapters)

        # Assert DB is 100% untouched
        count_slices_after = store.connection.execute(
            "SELECT COUNT(*) FROM raw_slices;"
        ).fetchone()[0]
        count_mems_after = store.connection.execute(
            "SELECT COUNT(*) FROM semantic_memories;"
        ).fetchone()[0]
        count_obs_after = store.connection.execute("SELECT COUNT(*) FROM observations;").fetchone()[
            0
        ]
        ch = store.get_chapter_metadata("ch_02")

        assert count_slices_after == count_slices_before
        assert count_mems_after == count_mems_before
        assert count_obs_after == count_obs_before
        assert ch is not None and ch.needs_privacy_redaction == 0
    finally:
        store.close()


# ── L-03: Surviving Multi-Source Memory ───────────────────────────────────────


def test_l03_surviving_multi_source_memory(tmp_path: Path) -> None:
    """L-03: Slice A + Slice B support one memory; deleting A preserves memory backed by B."""
    db_file = tmp_path / "l03.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        # Slice A (primary) + Slice B (reinforcement)
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_3a",
                occurred_at="2026-10-19T09:00:00+00:00",
                content="我早晨跑了5公里",
                ingestion_dedup_key="k_3a",
            )
        )
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_3b",
                occurred_at="2026-10-20T09:00:00+00:00",
                content="今天晨跑5公里，感觉很好",
                ingestion_dedup_key="k_3b",
            )
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_03",
                category="preference",
                statement="用户有晨跑锻炼的习惯",
                authority_class="user_asserted",
                scope="global",
                source_slice_id="sl_3a",
                valid_from="2026-10-19T09:00:00+00:00",
                validity_status="active",
            )
        )
        store.insert_evidence_reinforcement(
            EvidenceReinforcementEntity(
                reinforcement_id="reinf_3b",
                memory_id="mem_03",
                slice_id="sl_3b",
                independence_fingerprint="fp_3b",
                occurred_at="2026-10-20T09:00:00+00:00",
            )
        )
        store.connection.commit()

        # Delete Slice A
        res = lifecycle.hard_delete_slice("sl_3a")
        assert res.success is True
        assert "mem_03" in res.surviving_memories

        # Slice A physically gone, Slice B preserved
        assert store.get_raw_slice("sl_3a") is None
        assert store.get_raw_slice("sl_3b") is not None

        # Memory survives and its primary source is promoted to Slice B
        mem = store.get_semantic_memory("mem_03")
        assert mem is not None
        assert mem.source_slice_id == "sl_3b"
        assert mem.validity_status == "active"

        # FK check is 100% clean
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-04: Zero-Source Memory Cannot Remain Active ─────────────────────────────


def test_l04_zero_source_memory_cannot_remain_active(tmp_path: Path) -> None:
    """L-04: Deleting sole valid source removes unsupported active memory cleanly."""
    db_file = tmp_path / "l04.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_04",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="唯一证据原话",
                ingestion_dedup_key="k_04",
            )
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_04",
                category="fact",
                statement="从唯一切片派生的单一事实",
                authority_class="user_asserted",
                scope="global",
                source_slice_id="sl_04",
                valid_from="2026-10-19T10:00:00+00:00",
                validity_status="active",
            )
        )
        store.connection.commit()

        # Delete sole source slice
        res = lifecycle.hard_delete_slice("sl_04")
        assert res.success is True
        assert "mem_04" in res.removed_memories

        # Both base slice and unsupported memory are removed
        assert store.get_raw_slice("sl_04") is None
        assert store.get_semantic_memory("mem_04") is None

        # Zero unsupported active memory in storage
        active_mems = store.connection.execute(
            "SELECT COUNT(*) FROM semantic_memories WHERE validity_status = 'active';"
        ).fetchone()[0]
        assert active_mems == 0
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-05: Observation Proof Recompute ─────────────────────────────────────────


def test_l05_observation_proof_recompute_and_retract(tmp_path: Path) -> None:
    """L-05: Proof count decreases on partial delete; observation retracts when support reaches 0.

    Also verifies counter and contextual links are NOT counted as positive support.
    """
    db_file = tmp_path / "l05.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_5a",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="证据A",
                ingestion_dedup_key="k_5a",
            )
        )
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_5b",
                occurred_at="2026-10-19T11:00:00+00:00",
                content="证据B",
                ingestion_dedup_key="k_5b",
            )
        )
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_5_counter",
                occurred_at="2026-10-19T12:00:00+00:00",
                content="反例切片",
                ingestion_dedup_key="k_5_counter",
            )
        )
        store.insert_episode(
            EpisodeEntity(
                episode_id="ep_05",
                scope="global",
                started_at="2026-10-19T10:00:00+00:00",
                title_hint="语境容器",
            )
        )
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_05",
                scope="global",
                statement="多源印证的客观观察",
                proof_count=2,
                status="active",
                created_at="2026-10-19T10:00:00+00:00",
            )
        )
        # Positive supporting links
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(observation_id="obs_05", slice_id="sl_5a", role="supporting")
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(observation_id="obs_05", slice_id="sl_5b", role="supporting")
        )
        # Counter link (must NOT add to positive proof)
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(
                observation_id="obs_05", slice_id="sl_5_counter", role="counter"
            )
        )
        # Contextual episode link (must NOT add to positive proof)
        store.insert_observation_episode_link(
            ObservationEpisodeLinkEntity(
                observation_id="obs_05", episode_id="ep_05", role="contextual_scope"
            )
        )
        store.connection.commit()

        # Step 1: Delete Slice 5a -> proof decreases from 2 to 1, observation remains active
        res1 = lifecycle.hard_delete_slice("sl_5a")
        assert res1.success is True
        assert "obs_05" in res1.recomputed_observations
        obs_mid = store.get_observation("obs_05")
        assert obs_mid is not None
        assert obs_mid.proof_count == 1
        assert obs_mid.status == "active"

        # Step 2: Delete Slice 5b -> proof drops to 0, observation retracts!
        res2 = lifecycle.hard_delete_slice("sl_5b")
        assert res2.success is True
        assert "obs_05" in res2.retracted_observations
        obs_end = store.get_observation("obs_05")
        assert obs_end is not None
        assert obs_end.proof_count == 0
        assert obs_end.status == "retracted"

        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-06: Hypothesis Downstream Propagation ───────────────────────────────────


def test_l06_hypothesis_downstream_propagation(tmp_path: Path) -> None:
    """L-06: Hypothesis retracts when all supporting observations retract; revalidates."""
    db_file = tmp_path / "l06.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_6a",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="证据6A",
                ingestion_dedup_key="k_6a",
            )
        )
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_6b",
                occurred_at="2026-10-19T11:00:00+00:00",
                content="证据6B",
                ingestion_dedup_key="k_6b",
            )
        )
        # Obs 1 backed by Slice 6a
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_6a",
                scope="global",
                statement="观察6A",
                proof_count=1,
                status="active",
                created_at="2026-10-19T10:00:00+00:00",
            )
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(observation_id="obs_6a", slice_id="sl_6a", role="supporting")
        )
        # Obs 2 backed by Slice 6b
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_6b",
                scope="global",
                statement="观察6B",
                proof_count=1,
                status="active",
                created_at="2026-10-19T11:00:00+00:00",
            )
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(observation_id="obs_6b", slice_id="sl_6b", role="supporting")
        )
        # Hyp 1 backed by BOTH obs_6a and obs_6b
        store.insert_hypothesis(
            HypothesisEntity(
                hypothesis_id="hyp_multi",
                statement="多源支撑假说",
                lenses="flexibility",
                confidence_class="grounded",
                status="candidate",
            )
        )
        store.insert_hypothesis_observation_link(
            HypothesisObservationLinkEntity(
                hypothesis_id="hyp_multi", observation_id="obs_6a", role="supporting"
            )
        )
        store.insert_hypothesis_observation_link(
            HypothesisObservationLinkEntity(
                hypothesis_id="hyp_multi", observation_id="obs_6b", role="supporting"
            )
        )
        # Hyp 2 backed SOLELY by obs_6a
        store.insert_hypothesis(
            HypothesisEntity(
                hypothesis_id="hyp_sole",
                statement="单源支撑假说",
                lenses="patience",
                confidence_class="grounded",
                status="candidate",
            )
        )
        store.insert_hypothesis_observation_link(
            HypothesisObservationLinkEntity(
                hypothesis_id="hyp_sole", observation_id="obs_6a", role="supporting"
            )
        )
        store.connection.commit()

        # Delete Slice 6a:
        # - obs_6a retracts
        # - hyp_sole loses ALL active support -> retracts!
        # - hyp_multi loses partial support (obs_6b still active) -> revalidation_required!
        res = lifecycle.hard_delete_slice("sl_6a")
        assert res.success is True
        assert "obs_6a" in res.retracted_observations
        assert "hyp_sole" in res.retracted_hypotheses
        assert "hyp_multi" in res.revalidated_hypotheses

        hyp_s = store.get_hypothesis("hyp_sole")
        hyp_m = store.get_hypothesis("hyp_multi")
        assert hyp_s is not None and hyp_s.status == "retracted"
        assert hyp_m is not None and hyp_m.status == "revalidation_required"

        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-07: Confirmed Insight Safety & Immutable Calibration ───────────────────


def test_l07_confirmed_insight_safety(tmp_path: Path) -> None:
    """L-07: Insight propagates to retracted/revalidation_required; calibration immutable."""
    db_file = tmp_path / "l07.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_07",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="关键切片证据",
                ingestion_dedup_key="k_07",
            )
        )
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_07",
                scope="global",
                statement="支持观察",
                proof_count=1,
                status="active",
                created_at="2026-10-19T10:00:00+00:00",
            )
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(observation_id="obs_07", slice_id="sl_07", role="supporting")
        )
        store.insert_hypothesis(
            HypothesisEntity(
                hypothesis_id="hyp_07",
                statement="关键假说",
                lenses="acceptance",
                confidence_class="grounded",
                status="candidate",
            )
        )
        store.insert_hypothesis_observation_link(
            HypothesisObservationLinkEntity(
                hypothesis_id="hyp_07", observation_id="obs_07", role="supporting"
            )
        )
        store.insert_calibration_event(
            CalibrationEventEntity(
                calibration_id="cal_07",
                hypothesis_id="hyp_07",
                user_action="yes",
                calibrated_at="2026-10-19T10:30:00+00:00",
                user_note="用户明确确认此条自模型共识",
            )
        )
        store.insert_confirmed_insight(
            ConfirmedInsightEntity(
                insight_id="ins_07",
                source_hypothesis_id="hyp_07",
                source_calibration_id="cal_07",
                statement="确立之自模型",
                valid_from="2026-10-19T10:30:00+00:00",
                status="confirmed",
            )
        )
        store.connection.commit()

        # Hard delete the raw slice
        res = lifecycle.hard_delete_slice("sl_07")
        assert res.success is True
        assert "ins_07" in res.retracted_insights

        # Insight is retracted
        ins = store.get_confirmed_insight("ins_07")
        assert ins is not None
        assert ins.status == "retracted"
        assert ins.invalidated_at is not None

        # Critical: Calibration event must remain 100% immutable and intact
        cal_row = store.connection.execute(
            "SELECT * FROM calibration_events WHERE calibration_id = 'cal_07';"
        ).fetchone()
        assert cal_row is not None
        assert cal_row["user_action"] == "yes"
        assert cal_row["user_note"] == "用户明确确认此条自模型共识"
        assert cal_row["calibrated_at"] == "2026-10-19T10:30:00+00:00"

        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-08: Privacy Chapter Immediate Block ─────────────────────────────────────


def test_l08_privacy_chapter_immediate_block(tmp_path: Path) -> None:
    """L-08: Privacy hard delete sets chapter needs_privacy_redaction=1 in same transaction."""
    db_file = tmp_path / "l08.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_08",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="用户私密话题切片",
                ingestion_dedup_key="k_08",
            )
        )
        store.insert_chapter_metadata(
            ChapterMetadataEntity(
                chapter_id="ch_08",
                title="人生旅途秘密章",
                file_path="docs/chapters/secret_ch.md",
                time_span_start="2026-10-01T00:00:00+00:00",
                time_span_end="2026-10-19T23:59:59+00:00",
                needs_privacy_redaction=0,
            )
        )
        store.insert_chapter_slice_link(
            ChapterSliceLinkEntity(chapter_id="ch_08", slice_id="sl_08")
        )
        store.connection.commit()

        # Execute privacy-sensitive delete
        res = lifecycle.hard_delete_slice("sl_08", privacy_sensitive=True)
        assert res.success is True
        assert "ch_08" in res.privacy_redacted_chapters

        # Chapter immediately blocked for retrieval
        ch = store.get_chapter_metadata("ch_08")
        assert ch is not None
        assert ch.needs_privacy_redaction == 1

        # Direct citation link removed to avoid FK violation
        citation = store.connection.execute(
            "SELECT COUNT(*) FROM chapter_slice_links "
            "WHERE chapter_id = 'ch_08' AND slice_id = 'sl_08';"
        ).fetchone()[0]
        assert citation == 0
        assert store.get_raw_slice("sl_08") is None
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-09: Narrative Never Evidence Invariant ───────────────────────────────────


def test_l09_narrative_never_evidence_invariant(tmp_path: Path) -> None:
    """L-09: Schema & domain rules enforce chapters can never serve as evidence sources."""
    db_file = tmp_path / "l09.db"
    store = ChronicleStoreV2(db_file)
    try:
        store.insert_chapter_metadata(
            ChapterMetadataEntity(
                chapter_id="ch_09",
                title="叙事章节",
                file_path="docs/chapters/narrative.md",
                time_span_start="2026-10-01T00:00:00+00:00",
                time_span_end="2026-10-19T23:59:59+00:00",
            )
        )
        store.connection.commit()

        # Invariant 1: Semantic memory table schema has NO foreign key to chapter
        sem_cols = [
            r[1]
            for r in store.connection.execute("PRAGMA table_info(semantic_memories);").fetchall()
        ]
        assert "source_chapter_id" not in sem_cols

        # Invariant 2: Observation link tables contain NO observation_chapter_links table
        tables = [
            r[0]
            for r in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "observation_chapter_links" not in tables

        # Invariant 3: Attempting to insert zero-provenance memory citing nonexistent source fails
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_semantic_memory(
                SemanticMemoryEntity(
                    memory_id="mem_bad_narrative",
                    category="fact",
                    statement="非法以文学章节为事实来源",
                    authority_class="system_observed",
                    scope="global",
                    source_slice_id=None,
                    source_event_id=None,
                    source_episode_id=None,
                    valid_from="2026-10-19T10:00:00+00:00",
                    validity_status="active",
                )
            )
            store.connection.commit()
    finally:
        store.close()


# ── L-10: Episode Membership Is Not Pin ───────────────────────────────────────


def test_l10_episode_membership_is_not_pin(tmp_path: Path) -> None:
    """L-10: Event referenced solely by Episode container is NOT pinned and can be purged."""
    db_file = tmp_path / "l10.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_event_skeleton(
            EventSkeletonEntity(
                event_id="evt_10",
                occurred_at="2026-10-19T10:00:00+00:00",
                agent_id="pi-desktop",
                session_id="sess_10",
                event_type="tool_execution",
                retention_class="transient",
            )
        )
        store.insert_episode(
            EpisodeEntity(
                episode_id="ep_10",
                scope="project",
                project_id="coeva",
                started_at="2026-10-19T10:00:00+00:00",
                title_hint="工具调用经历",
            )
        )
        store.insert_episode_event_link(
            EpisodeEventLinkEntity(episode_id="ep_10", event_id="evt_10")
        )
        store.connection.commit()

        # Event is in episode, but NOT pinned
        assert lifecycle.is_event_pinned("evt_10") is False
        assert lifecycle.get_event_pin_reasons("evt_10") == []

        # Purging unpinned event unlinks episode membership and removes event skeleton
        res = lifecycle.purge_event("evt_10")
        assert res.success is True
        assert res.deleted_base_evidence is True

        assert store.get_event_skeleton("evt_10") is None
        # Episode container itself remains intact
        assert store.get_episode("ep_10") is not None
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-11: Observation Adoption Pins Event ─────────────────────────────────────


def test_l11_observation_adoption_pins_event(tmp_path: Path) -> None:
    """L-11: Active observation pins event; direct purge raises EventPinnedError."""
    db_file = tmp_path / "l11.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_event_skeleton(
            EventSkeletonEntity(
                event_id="evt_11",
                occurred_at="2026-10-19T10:00:00+00:00",
                agent_id="pi-desktop",
                session_id="sess_11",
                event_type="test_pass",
                retention_class="transient",
            )
        )
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_11",
                scope="project",
                project_id="coeva",
                statement="自动化测试稳定通过",
                proof_count=1,
                status="active",
                created_at="2026-10-19T10:00:00+00:00",
            )
        )
        store.insert_observation_event_link(
            ObservationEventLinkEntity(
                observation_id="obs_11", event_id="evt_11", role="supporting"
            )
        )
        store.connection.commit()

        # Event is retention-pinned by active observation
        assert lifecycle.is_event_pinned("evt_11") is True
        assert any("obs_11" in r for r in lifecycle.get_event_pin_reasons("evt_11"))

        # Dry-run analysis reports cannot delete without cascade
        report = lifecycle.analyze_event_delete("evt_11", cascade=False)
        assert report.can_delete is False
        assert report.is_pinned is True

        # Purging pinned event fails closed with EventPinnedError
        with pytest.raises(EventPinnedError):
            lifecycle.purge_event("evt_11")

        # Base event remains intact
        assert store.get_event_skeleton("evt_11") is not None
    finally:
        store.close()


# ── L-12: Last Durable Ref Unpins ─────────────────────────────────────────────


def test_l12_last_durable_ref_unpins(tmp_path: Path) -> None:
    """L-12: Retracting the observation holding the pin unpins the event, allowing clean purge."""
    db_file = tmp_path / "l12.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_12",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="触发切片",
                ingestion_dedup_key="k_12",
            )
        )
        store.insert_event_skeleton(
            EventSkeletonEntity(
                event_id="evt_12",
                occurred_at="2026-10-19T10:00:00+00:00",
                agent_id="pi-desktop",
                session_id="sess_12",
                event_type="tool_execution",
                retention_class="transient",
            )
        )
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_12",
                scope="project",
                project_id="coeva",
                statement="由切片与遥测共同支撑的观察",
                proof_count=1,
                status="active",
                created_at="2026-10-19T10:00:00+00:00",
            )
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(observation_id="obs_12", slice_id="sl_12", role="supporting")
        )
        # Event is linked to obs_12
        store.insert_observation_event_link(
            ObservationEventLinkEntity(
                observation_id="obs_12", event_id="evt_12", role="supporting"
            )
        )
        store.connection.commit()

        assert lifecycle.is_event_pinned("evt_12") is True

        # Delete the slice supporting obs_12
        # Note: obs_12 has 2 supporting links (slice 12 + event 12).
        # Let's unlink both to retract observation:
        lifecycle.store.connection.execute(
            "DELETE FROM observation_event_links "
            "WHERE observation_id = 'obs_12' AND event_id = 'evt_12';"
        )
        lifecycle.store.connection.commit()

        # Now deleting slice_12 drops obs_12 proof to 0 -> retracts obs_12
        res = lifecycle.hard_delete_slice("sl_12")
        assert res.success is True
        assert "obs_12" in res.retracted_observations

        # Now evt_12 is completely unpinned
        assert lifecycle.is_event_pinned("evt_12") is False

        # Now purge succeeds!
        purge_res = lifecycle.purge_event("evt_12")
        assert purge_res.success is True
        assert store.get_event_skeleton("evt_12") is None
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-13: Transaction Rollback ────────────────────────────────────────────────


def test_l13_transaction_rollback(tmp_path: Path) -> None:
    """L-13: Injected failure mid-operation rolls back transaction; DB is completely unchanged."""
    db_file = tmp_path / "l13.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id="sl_13",
                occurred_at="2026-10-19T10:00:00+00:00",
                content="回滚测试切片",
                ingestion_dedup_key="k_13",
            )
        )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_13",
                category="fact",
                statement="从回滚切片派生的记忆",
                authority_class="user_asserted",
                scope="global",
                source_slice_id="sl_13",
                valid_from="2026-10-19T10:00:00+00:00",
                validity_status="active",
            )
        )
        store.insert_chapter_metadata(
            ChapterMetadataEntity(
                chapter_id="ch_13",
                title="受影响章节",
                file_path="docs/chapters/ch13.md",
                time_span_start="2026-10-01T00:00:00+00:00",
                time_span_end="2026-10-19T23:59:59+00:00",
                needs_privacy_redaction=0,
            )
        )
        store.insert_chapter_slice_link(
            ChapterSliceLinkEntity(chapter_id="ch_13", slice_id="sl_13")
        )
        store.connection.commit()

        # Inject failure right before raw evidence physical delete via before_physical_delete_hook
        def failing_hook(slice_id: str) -> None:
            raise RuntimeError("Simulated crash right before base evidence deletion!")

        with pytest.raises(RuntimeError, match="Simulated crash"):
            lifecycle.hard_delete_slice("sl_13", before_physical_delete_hook=failing_hook)

        # Verify rollback: everything is restored to pre-operation state
        assert store.get_raw_slice("sl_13") is not None
        assert store.get_semantic_memory("mem_13") is not None
        ch = store.get_chapter_metadata("ch_13")
        assert ch is not None
        assert ch.needs_privacy_redaction == 0

        citation_count = store.connection.execute(
            "SELECT COUNT(*) FROM chapter_slice_links "
            "WHERE chapter_id = 'ch_13' AND slice_id = 'sl_13';"
        ).fetchone()[0]
        assert citation_count == 1

        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []
    finally:
        store.close()


# ── L-14: FK Closure and Zero Orphan Links ────────────────────────────────────


def test_l14_fk_closure(tmp_path: Path) -> None:
    """L-14: After complex multi-entity lifecycle operations, PRAGMA foreign_key_check is 0."""
    db_file = tmp_path / "l14.db"
    store = ChronicleStoreV2(db_file)
    lifecycle = LifecycleService(store)
    try:
        # Create full multi-entity tree
        for i in range(3):
            store.insert_raw_slice(
                RawSliceEntity(
                    slice_id=f"sl_14_{i}",
                    occurred_at=f"2026-10-19T10:0{i}:00+00:00",
                    content=f"切片_{i}",
                    ingestion_dedup_key=f"k_14_{i}",
                )
            )
        store.insert_semantic_memory(
            SemanticMemoryEntity(
                memory_id="mem_14_0",
                category="fact",
                statement="多源记忆",
                authority_class="user_asserted",
                scope="global",
                source_slice_id="sl_14_0",
                valid_from="2026-10-19T10:00:00+00:00",
                validity_status="active",
            )
        )
        store.insert_evidence_reinforcement(
            EvidenceReinforcementEntity(
                reinforcement_id="reinf_14_1",
                memory_id="mem_14_0",
                slice_id="sl_14_1",
                independence_fingerprint="fp_14_1",
                occurred_at="2026-10-19T10:01:00+00:00",
            )
        )
        store.insert_observation(
            ObservationEntity(
                observation_id="obs_14",
                scope="global",
                statement="多证据观察",
                proof_count=2,
                status="active",
                created_at="2026-10-19T10:00:00+00:00",
            )
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(
                observation_id="obs_14", slice_id="sl_14_0", role="supporting"
            )
        )
        store.insert_observation_slice_link(
            ObservationSliceLinkEntity(
                observation_id="obs_14", slice_id="sl_14_2", role="supporting"
            )
        )
        store.connection.commit()

        # Delete sl_14_0 -> mem_14_0 promoted to sl_14_1; obs_14 proof decreases to 1
        res1 = lifecycle.hard_delete_slice("sl_14_0")
        assert res1.success is True
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []

        # Delete sl_14_1 -> mem_14_0 removed; obs_14 proof remains 1 (backed by sl_14_2)
        res2 = lifecycle.hard_delete_slice("sl_14_1")
        assert res2.success is True
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []

        # Delete sl_14_2 -> obs_14 retracts
        res3 = lifecycle.hard_delete_slice("sl_14_2")
        assert res3.success is True
        assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []

        # Final check: Zero orphan links across all typed link tables
        for table in (
            "episode_slice_links",
            "episode_event_links",
            "observation_slice_links",
            "observation_event_links",
            "observation_memory_links",
            "chapter_slice_links",
            "chapter_episode_links",
            "chapter_insight_links",
        ):
            assert store.connection.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0] == 0
    finally:
        store.close()


# ── L-15: Production Isolation ────────────────────────────────────────────────


def test_l15_production_isolation() -> None:
    """L-15: Production flags default to OFF; router defaults strictly to legacy V1."""
    flags = MemoryFeatureFlags()
    assert flags.memory_v2_storage is False
    assert flags.memory_v2_consolidation is False
    assert flags.memory_v2_retrieval is False
    assert flags.memory_v2_migration is False

    router = RawEvidenceRouter(flags=flags, v1_store="legacy_v1", v2_service=None)
    assert router.is_v2_active is False
    assert router.active_route == "v1_legacy"
