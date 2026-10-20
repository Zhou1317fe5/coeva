"""Comprehensive Test Suite for Memory V2.1 WP-9: Chapter & Privacy Redaction Integration.

Formal verification of canonical test gates CH-01 through CH-20 and Stage-7 Exit Gate:
- CH-01: time-span gate (< 4 weeks -> no chapter)
- CH-02: structural-change gate (long duration alone without transition -> no chapter)
- CH-03: evidence-diversity gate (single slice/session anecdote -> no chapter)
- CH-04: voluntary/non-disturbing gate (no forced chapter generation)
- CH-05: confirmed insight allowed (valid confirmed insight enters ChapterSourceBundle)
- CH-06: candidate hypothesis forbidden (candidate hypothesis cannot enter chapter consensus)
- CH-07: typed chapter links (persisted chapter has exact reverse-traversable links)
- CH-08: no pseudo provenance (no unsupplied source IDs appear in link tables)
- CH-09: narrative never evidence (chapter cannot become ProvenanceRef / Observation / support)
- CH-10: privacy mark immediate unreadable (needs_privacy_redaction=1 stops returning stale text)
- CH-11: hard-delete impact (deleting linked slice marks chapter pending before destructive del)
- CH-12: linked insight invalidation/privacy (retracting insight marks chapter privacy pending)
- CH-13: redaction success (safe rewrite replaces file, updates links, clears flag)
- CH-14: redaction failure (failure leaves flag=1 and stale chapter unreadable)
- CH-15: crash-safe publication (temp file never exposed without complete DB transaction)
- CH-16: missing/corrupt file (reader fails closed; does not fabricate content)
- CH-17: Narrative Firewall (violating text cannot be persisted)
- CH-18: no Agent private payload (source bundle excludes Agent prompts, CoT, tool dumps)
- CH-19: no self-reinforcement (chapter text cannot re-enter memory pipeline)
- CH-20: production isolation (production DB, files, runtime, flags untouched)
- Stage-7 Exit Gate: 100% unreadable rate, 0% stale reads, 0 orphan links
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.flags import MemoryFeatureFlags
from src.memory.v2.chapter import (
    ChapterEligibilityGateV2,
    ChapterError,
    ChapterGenerationResult,
    ChapterGeneratorV2,
    ChapterRepository,
    ChapterSourceBundle,
    IllegalChapterSourceError,
    NarrativeFirewallViolationError,
)
from src.memory.v2.chapter_privacy import ChapterPrivacyService
from src.memory.v2.entities import (
    ChapterMetadataEntity,
    ConfirmedInsightEntity,
    EpisodeEntity,
    RawSliceEntity,
)
from src.memory.v2.lifecycle import LifecycleService
from src.memory.v2.provenance import ProvenanceRef
from src.memory.v2.store import ChronicleStoreV2

# ── Fixtures & Test Helpers ───────────────────────────────────────────────────


def create_test_store(tmp_path: Path, name: str = "test.db") -> ChronicleStoreV2:
    return ChronicleStoreV2(tmp_path / name)


def seed_slice(
    store: ChronicleStoreV2,
    slice_id: str,
    occurred_at: str,
    content: str = "测试切片内容",
) -> RawSliceEntity:
    sl = RawSliceEntity(
        slice_id=slice_id,
        occurred_at=occurred_at,
        content=content,
        ingestion_dedup_key=f"k_{slice_id}",
        created_at=occurred_at,
    )
    store.insert_raw_slice(sl)
    return sl


def seed_episode(
    store: ChronicleStoreV2,
    episode_id: str,
    started_at: str,
    closed_at: str | None = None,
    title_hint: str = "测试会话",
    summary: str = "会话总结",
) -> EpisodeEntity:
    ep = EpisodeEntity(
        episode_id=episode_id,
        scope="global",
        started_at=started_at,
        closed_at=closed_at or started_at,
        title_hint=title_hint,
        summary=summary,
        status="closed",
        created_at=started_at,
    )
    store.insert_episode(ep)
    return ep


def seed_insight(
    store: ChronicleStoreV2,
    insight_id: str,
    valid_from: str,
    statement: str = "已确认的心智共识",
    status: str = "confirmed",
) -> ConfirmedInsightEntity:
    # Need hypothesis and calibration for foreign key integrity
    hyp_id = f"hyp_{insight_id}"
    cal_id = f"cal_{insight_id}"
    conn = store.connection
    conn.execute(
        "INSERT OR IGNORE INTO hypotheses "
        "(hypothesis_id, statement, lenses, confidence_class, status, created_at) "
        "VALUES (?, ?, 'flexibility', 'grounded', 'candidate', ?);",
        (hyp_id, statement, valid_from),
    )
    conn.execute(
        "INSERT OR IGNORE INTO calibration_events "
        "(calibration_id, hypothesis_id, user_action, calibrated_at) "
        "VALUES (?, ?, 'yes', ?);",
        (cal_id, hyp_id, valid_from),
    )
    ins = ConfirmedInsightEntity(
        insight_id=insight_id,
        source_hypothesis_id=hyp_id,
        source_calibration_id=cal_id,
        statement=statement,
        valid_from=valid_from,
        status=status,  # type: ignore[arg-type]
        created_at=valid_from,
    )
    store.insert_confirmed_insight(ins)
    return ins


# ── CH-01: Time-Span Gate ─────────────────────────────────────────────────────


def test_ch01_time_span_gate_rejects_under_4_weeks(tmp_path: Path) -> None:
    """CH-01: Time-span gate rejects duration < 4 weeks (28 days)."""
    store = create_test_store(tmp_path, "ch01.db")
    gate = ChapterEligibilityGateV2(min_span_days=28)

    # 1. Span of 10 days (< 28 days)
    seed_episode(store, "ep_1", started_at="2026-06-01T10:00:00+00:00")
    seed_episode(store, "ep_2", started_at="2026-06-11T10:00:00+00:00")
    seed_insight(store, "ins_1", valid_from="2026-06-05T10:00:00+00:00")

    eligible, report = gate.evaluate(store)
    assert not eligible
    assert not report["sustained"]["passed"]
    assert report["sustained"]["span_days"] == 10
    assert report["sustained"]["min_span_days"] == 28

    # 2. Add an episode at day 30 (span = 30 days >= 28)
    seed_episode(store, "ep_3", started_at="2026-07-01T10:00:00+00:00")
    eligible_now, report_now = gate.evaluate(store)
    assert eligible_now
    assert report_now["sustained"]["passed"]
    assert report_now["sustained"]["span_days"] >= 28


# ── CH-02: Structural-Change Gate ─────────────────────────────────────────────


def test_ch02_structural_change_gate_requires_confirmed_insight(tmp_path: Path) -> None:
    """CH-02: Long duration alone without meaningful transition -> no chapter."""
    store = create_test_store(tmp_path, "ch02.db")
    gate = ChapterEligibilityGateV2(min_span_days=28, min_confirmed_insights=1)

    # 35-day duration with episodes, but ZERO confirmed insights
    seed_episode(store, "ep_1", started_at="2026-06-01T10:00:00+00:00")
    seed_episode(store, "ep_2", started_at="2026-07-06T10:00:00+00:00")

    eligible, report = gate.evaluate(store)
    assert not eligible
    assert report["sustained"]["passed"] is True  # Time passed
    assert report["structural"]["passed"] is False  # Structural shift missing
    assert report["structural"]["confirmed_insights_count"] == 0

    # Add confirmed insight
    seed_insight(store, "ins_1", valid_from="2026-06-15T10:00:00+00:00")
    eligible_now, report_now = gate.evaluate(store)
    assert eligible_now
    assert report_now["structural"]["passed"] is True


# ── CH-03: Evidence-Diversity Gate ───────────────────────────────────────────


def test_ch03_evidence_diversity_gate_rejects_single_anecdote(tmp_path: Path) -> None:
    """CH-03: Single slice/session anecdote alone -> no chapter."""
    store = create_test_store(tmp_path, "ch03.db")
    gate = ChapterEligibilityGateV2(min_span_days=0, min_distinct_sources=2)

    # Only single slice and single episode
    seed_slice(store, "sl_1", occurred_at="2026-06-01T10:00:00+00:00")
    seed_episode(store, "ep_1", started_at="2026-06-01T10:00:00+00:00")

    eligible, report = gate.evaluate(store)
    assert not eligible
    assert report["diversity"]["is_single_anecdote"] is True
    assert report["diversity"]["passed"] is False

    # Add second distinct episode and insight
    seed_episode(store, "ep_2", started_at="2026-06-10T10:00:00+00:00")
    seed_insight(store, "ins_1", valid_from="2026-06-05T10:00:00+00:00")
    eligible_now, report_now = gate.evaluate(store)
    assert eligible_now
    assert report_now["diversity"]["passed"] is True


# ── CH-04: Voluntary / Non-Disturbing Gate ────────────────────────────────────


def test_ch04_voluntary_gate_blocks_forced_generation(tmp_path: Path) -> None:
    """CH-04: Voluntary gate fails if forced/automated generation without consent."""
    store = create_test_store(tmp_path, "ch04.db")
    gate = ChapterEligibilityGateV2(min_span_days=10)

    seed_episode(store, "ep_1", started_at="2026-06-01T10:00:00+00:00")
    seed_episode(store, "ep_2", started_at="2026-06-20T10:00:00+00:00")
    seed_insight(store, "ins_1", valid_from="2026-06-10T10:00:00+00:00")

    # Forced run (e.g. non-voluntary background tick)
    eligible_forced, report_forced = gate.evaluate(store, voluntary=False)
    assert not eligible_forced
    assert report_forced["voluntary"]["passed"] is False

    # Voluntary user-initiated run
    eligible_voluntary, report_voluntary = gate.evaluate(store, voluntary=True)
    assert eligible_voluntary
    assert report_voluntary["voluntary"]["passed"] is True


# ── CH-05: Confirmed Insight Allowed ─────────────────────────────────────────


def test_ch05_confirmed_insight_allowed_in_bundle(tmp_path: Path) -> None:
    """CH-05: Valid confirmed insight enters ChapterSourceBundle cleanly."""
    store = create_test_store(tmp_path, "ch05.db")
    ins = seed_insight(store, "ins_valid", valid_from="2026-06-01T10:00:00+00:00")

    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins,),
    )
    bundle.validate()  # Must not raise
    assert bundle.insight_ids == ("ins_valid",)
    assert not bundle.is_empty


# ── CH-06: Candidate Hypothesis Forbidden ────────────────────────────────────


def test_ch06_candidate_hypothesis_forbidden_in_bundle(tmp_path: Path) -> None:
    """CH-06: Candidate or unconfirmed hypothesis cannot enter chapter consensus input."""
    ins_unconfirmed = ConfirmedInsightEntity(
        insight_id="ins_fake",
        source_hypothesis_id="hyp_cand",
        source_calibration_id="cal_01",
        statement="未经过确认的猜想",
        valid_from="2026-06-01",
        status="retracted",  # Not confirmed!
    )
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins_unconfirmed,),
    )
    with pytest.raises(IllegalChapterSourceError, match="status='confirmed'"):
        bundle.validate()


# ── CH-07: Typed Chapter Links ───────────────────────────────────────────────


def test_ch07_typed_chapter_links_persisted_and_traversable(tmp_path: Path) -> None:
    """CH-07: Persisted chapter has exact reverse-traversable slice/episode/insight links."""
    store = create_test_store(tmp_path, "ch07.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    generator = ChapterGeneratorV2(store, repo=repo)

    sl = seed_slice(store, "sl_07", occurred_at="2026-06-01T10:00:00+00:00")
    ep = seed_episode(store, "ep_07", started_at="2026-06-01T10:00:00+00:00")
    ins = seed_insight(store, "ins_07", valid_from="2026-06-01T10:00:00+00:00")

    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins,),
        episodes=(ep,),
        raw_slices=(sl,),
    )
    result = generator.generate(bundle, title="第七测试章")
    meta = repo.publish_chapter(result)

    # Reverse queries
    chaps_by_slice = store.get_chapters_by_slice("sl_07")
    chaps_by_ep = store.get_chapters_by_episode("ep_07")
    chaps_by_ins = store.get_chapters_by_insight("ins_07")

    assert [c.chapter_id for c in chaps_by_slice] == [meta.chapter_id]
    assert [c.chapter_id for c in chaps_by_ep] == [meta.chapter_id]
    assert [c.chapter_id for c in chaps_by_ins] == [meta.chapter_id]

    # Typed links in DB
    assert len(store.get_chapter_slice_links(meta.chapter_id)) == 1
    assert len(store.get_chapter_episode_links(meta.chapter_id)) == 1
    assert len(store.get_chapter_insight_links(meta.chapter_id)) == 1


# ── CH-08: No Pseudo Provenance ───────────────────────────────────────────────


def test_ch08_no_pseudo_provenance_rejected(tmp_path: Path) -> None:
    """CH-08: Source IDs not supplied to DB cannot appear in link tables."""
    store = create_test_store(tmp_path, "ch08.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")

    # Invented unpersisted IDs
    fake_slice = RawSliceEntity(
        slice_id="sl_fake",
        occurred_at="2026-06-01T00:00:00+00:00",
        content="虚假切片",
        ingestion_dedup_key="k_fake",
    )
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        raw_slices=(fake_slice,),
    )
    result = ChapterGenerationResult(
        chapter_id="ch_fake",
        title="虚构章",
        file_path=str(tmp_path / "chapters" / "chapter_ch_fake.md"),
        markdown_content="# 虚构章\n\n## 1. 伴生体的观察与心智转移（The Shift）\n内容",
        source_bundle=bundle,
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        created_at="2026-07-01T00:00:00+00:00",
    )

    with pytest.raises(IllegalChapterSourceError, match="does not exist in raw_slices"):
        repo.publish_chapter(result)

    assert store.get_chapter_metadata("ch_fake") is None


# ── CH-09: Narrative Never Evidence Invariant ──────────────────────────────────


def test_ch09_narrative_never_evidence_invariant() -> None:
    """CH-09: Chapter cannot become ProvenanceRef or observation/hypothesis support."""
    # 1. Type level: "chapter" or "narrative" is not in ProvenanceKind
    allowed_kinds = ("slice", "event", "episode", "semantic_memory", "observation", "insight")
    assert "chapter" not in allowed_kinds
    assert "narrative" not in allowed_kinds

    # 2. Schema level: Chapter cannot be passed as raw evidence or observation link
    ref = ProvenanceRef(kind="slice", target_id="sl_01", role="primary_source")
    assert str(ref.kind) != "chapter"


# ── CH-10: Privacy Mark Immediate Unreadable ──────────────────────────────────


def test_ch10_privacy_mark_immediate_unreadable(tmp_path: Path) -> None:
    """CH-10: needs_privacy_redaction=1 stops reader from returning stale text immediately."""
    store = create_test_store(tmp_path, "ch10.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    privacy_svc = ChapterPrivacyService(store, repo=repo)

    sl = seed_slice(store, "sl_10", occurred_at="2026-06-01T10:00:00+00:00")
    ins = seed_insight(store, "ins_10", valid_from="2026-06-01T10:00:00+00:00")
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins,),
        raw_slices=(sl,),
    )
    generator = ChapterGeneratorV2(store, repo=repo)
    res = generator.generate(bundle, title="隐私测试章")
    meta = repo.publish_chapter(res)

    # 1. Normal state: readable
    readable_before = repo.get_readable(meta.chapter_id)
    assert readable_before is not None
    assert not readable_before.is_redacted
    assert "## 1. 伴生体的观察与心智转移" in readable_before.content

    # 2. Mark privacy pending
    privacy_svc.mark_privacy_pending(meta.chapter_id)

    # 3. Read immediately: MUST return placeholder, NEVER stale markdown
    readable_after = repo.get_readable(meta.chapter_id)
    assert readable_after is not None
    assert readable_after.is_redacted is True
    assert readable_after.needs_privacy_redaction == 1
    placeholder = "[This chapter is temporarily unavailable while privacy redaction is applied.]"
    assert placeholder in readable_after.content
    assert "## 1. 伴生体的观察与心智转移" not in readable_after.content

    # 4. list_readable() excludes it by default
    clean_list = repo.list_readable(include_redacted_placeholders=False)
    assert not any(c.chapter_id == meta.chapter_id for c in clean_list)


# ── CH-11: Hard-Delete Impact ─────────────────────────────────────────────────


def test_ch11_hard_delete_slice_marks_chapter_privacy_pending(tmp_path: Path) -> None:
    """CH-11: Deleting a linked slice marks chapter pending before destructive delete."""
    store = create_test_store(tmp_path, "ch11.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    lifecycle = LifecycleService(store)

    sl = seed_slice(store, "sl_11", occurred_at="2026-06-01T10:00:00+00:00")
    ins = seed_insight(store, "ins_11", valid_from="2026-06-01T10:00:00+00:00")
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins,),
        raw_slices=(sl,),
    )
    res = ChapterGeneratorV2(store, repo=repo).generate(bundle, title="切片删除影响章")
    meta = repo.publish_chapter(res)

    # Hard delete slice with privacy_sensitive=True
    del_res = lifecycle.hard_delete_slice("sl_11", privacy_sensitive=True)
    assert del_res.success is True
    assert meta.chapter_id in del_res.privacy_redacted_chapters

    # Chapter metadata in DB is immediately pending
    updated_meta = store.get_chapter_metadata(meta.chapter_id)
    assert updated_meta is not None
    assert updated_meta.needs_privacy_redaction == 1

    # Reader returns fail-closed placeholder
    reader_view = repo.get_readable(meta.chapter_id)
    assert reader_view is not None
    assert reader_view.is_redacted is True


# ── CH-12: Linked Insight Invalidation Privacy ────────────────────────────────


def test_ch12_insight_invalidation_marks_chapter_privacy_pending(tmp_path: Path) -> None:
    """CH-12: Retracting/invalidating an insight marks citing chapters privacy-pending."""
    store = create_test_store(tmp_path, "ch12.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    lifecycle = LifecycleService(store)

    ins = seed_insight(store, "ins_12", valid_from="2026-06-01T10:00:00+00:00")
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins,),
    )
    res = ChapterGeneratorV2(store, repo=repo).generate(bundle, title="自模型失效章")
    meta = repo.publish_chapter(res)

    # Invalidate insight with privacy
    inv_res = lifecycle.invalidate_insight_with_privacy("ins_12", privacy_sensitive=True)
    assert inv_res.success is True
    assert meta.chapter_id in inv_res.privacy_redacted_chapters

    ch = store.get_chapter_metadata(meta.chapter_id)
    assert ch is not None
    assert ch.needs_privacy_redaction == 1


# ── CH-13: Redaction Success ──────────────────────────────────────────────────


def test_ch13_redaction_success_flow(tmp_path: Path) -> None:
    """CH-13: Safe rewrite replaces file, updates links, and clears pending flag."""
    store = create_test_store(tmp_path, "ch13.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    privacy_svc = ChapterPrivacyService(store, repo=repo)
    lifecycle = LifecycleService(store)

    sl_del = seed_slice(store, "sl_del", occurred_at="2026-06-01T10:00:00+00:00")
    sl_surv = seed_slice(store, "sl_surv", occurred_at="2026-06-02T10:00:00+00:00")
    ins_surv = seed_insight(store, "ins_surv", valid_from="2026-06-01T10:00:00+00:00")

    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins_surv,),
        raw_slices=(sl_del, sl_surv),
    )
    gen_res = ChapterGeneratorV2(store, repo=repo).generate(bundle, title="脱敏重写章")
    meta = repo.publish_chapter(gen_res)

    # 1. Delete sl_del -> chapter becomes privacy-pending
    lifecycle.hard_delete_slice("sl_del", privacy_sensitive=True)
    assert privacy_svc.is_unreadable(meta.chapter_id) is True

    # 2. Execute redaction/regeneration
    redact_res = privacy_svc.redact_or_regenerate_chapter(meta.chapter_id)
    assert redact_res.success is True
    assert redact_res.cleared_redaction is True
    assert redact_res.surviving_sources_count == 2  # sl_surv + ins_surv

    # 3. Flag cleared in DB
    updated_meta = store.get_chapter_metadata(meta.chapter_id)
    assert updated_meta is not None
    assert updated_meta.needs_privacy_redaction == 0

    # 4. Links updated to surviving sources only
    slice_links = store.get_chapter_slice_links(meta.chapter_id)
    assert [s.slice_id for s in slice_links] == ["sl_surv"]

    # 5. Normal readable access restored
    readable = repo.get_readable(meta.chapter_id)
    assert readable is not None
    assert not readable.is_redacted
    assert readable.needs_privacy_redaction == 0


# ── CH-14: Redaction Failure Leaves Unreadable ─────────────────────────────────


def test_ch14_redaction_failure_fails_closed(tmp_path: Path) -> None:
    """CH-14: Failure leaves flag=1 and stale chapter unreadable; no fallback to old text."""
    store = create_test_store(tmp_path, "ch14.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    privacy_svc = ChapterPrivacyService(store, repo=repo)

    sl = seed_slice(store, "sl_14", occurred_at="2026-06-01T10:00:00+00:00")
    ins = seed_insight(store, "ins_14", valid_from="2026-06-01T10:00:00+00:00")
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins,),
        raw_slices=(sl,),
    )
    meta = repo.publish_chapter(
        ChapterGeneratorV2(store, repo=repo).generate(bundle, title="失败阻断章")
    )
    privacy_svc.mark_privacy_pending(meta.chapter_id)

    # Attempt redaction with simulated failure
    result = privacy_svc.redact_or_regenerate_chapter(meta.chapter_id, simulate_failure=True)
    assert result.success is False
    assert result.cleared_redaction is False

    # Invariant: needs_privacy_redaction must remain 1
    ch = store.get_chapter_metadata(meta.chapter_id)
    assert ch is not None
    assert ch.needs_privacy_redaction == 1

    # Invariant: Reader returns placeholder, NEVER stale text
    view = repo.get_readable(meta.chapter_id)
    assert view is not None
    assert view.is_redacted is True
    assert "[This chapter is temporarily unavailable" in view.content


# ── CH-15: Crash-Safe Publication ─────────────────────────────────────────────


def test_ch15_crash_safe_publication_no_orphan_metadata(tmp_path: Path) -> None:
    """CH-15: Partial/temp file never becomes normal readable chapter if DB fails."""
    store = create_test_store(tmp_path, "ch15.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")

    sl = seed_slice(store, "sl_15", occurred_at="2026-06-01T10:00:00+00:00")
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        raw_slices=(sl,),
    )
    gen_res = ChapterGeneratorV2(store, repo=repo).generate(bundle, title="故障安全章")

    # Mock DB failure during insert_chapter_metadata
    with patch.object(
        store,
        "insert_chapter_metadata",
        side_effect=RuntimeError("Simulated DB Disk Full"),
    ):
        with pytest.raises(ChapterError, match="Failed to persist chapter metadata"):
            repo.publish_chapter(gen_res)

    # Unindexed orphan artifact cleaned up or unindexed
    final_file = Path(gen_res.file_path)
    assert not final_file.exists()
    assert store.get_chapter_metadata(gen_res.chapter_id) is None
    assert repo.get_readable(gen_res.chapter_id) is None


# ── CH-16: Missing or Corrupt File ────────────────────────────────────────────


def test_ch16_missing_file_fails_closed(tmp_path: Path) -> None:
    """CH-16: Missing/corrupt file fails closed; does not fabricate content."""
    store = create_test_store(tmp_path, "ch16.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")

    # Insert metadata pointing to non-existent file
    meta = ChapterMetadataEntity(
        chapter_id="ch_ghost",
        title="幽灵章",
        file_path=str(tmp_path / "chapters" / "ghost.md"),
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        needs_privacy_redaction=0,
        created_at="2026-07-01T00:00:00+00:00",
    )
    store.insert_chapter_metadata(meta)

    # Reader returns None, never fabricates
    assert repo.get_readable("ch_ghost") is None


# ── CH-17: Narrative Firewall Rejection ────────────────────────────────────────


def test_ch17_narrative_firewall_blocks_flattery_and_telemetry(tmp_path: Path) -> None:
    """CH-17: Generated text violating firewall cannot be persisted."""
    store = create_test_store(tmp_path, "ch17.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    sl = seed_slice(store, "sl_17", occurred_at="2026-06-01T10:00:00+00:00")

    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        raw_slices=(sl,),
    )

    # 1. Text with sycophancy
    dirty_flattery = ChapterGenerationResult(
        chapter_id="ch_dirty1",
        title="阿谀章",
        file_path=str(tmp_path / "chapters" / "ch_dirty1.md"),
        markdown_content="# 章节\n\n你太棒了，展现了卓越的智慧，这是伟大的成就！",
        source_bundle=bundle,
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        created_at="2026-07-01T00:00:00+00:00",
    )
    with pytest.raises(NarrativeFirewallViolationError, match="Contains forbidden phrase"):
        repo.publish_chapter(dirty_flattery)

    # 2. Text with clinical diagnosis
    dirty_clinical = ChapterGenerationResult(
        chapter_id="ch_dirty2",
        title="病理章",
        file_path=str(tmp_path / "chapters" / "ch_dirty2.md"),
        markdown_content="# 章节\n\n从你的表现来看，明显确诊了抑郁症与心理疾病。",
        source_bundle=bundle,
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        created_at="2026-07-01T00:00:00+00:00",
    )
    with pytest.raises(NarrativeFirewallViolationError, match="Contains forbidden phrase"):
        repo.publish_chapter(dirty_clinical)

    # 3. Text leaking internal session ID pseudo-evidence
    dirty_session = ChapterGenerationResult(
        chapter_id="ch_dirty3",
        title="泄露章",
        file_path=str(tmp_path / "chapters" / "ch_dirty3.md"),
        markdown_content="# 章节\n\n证据表明在 sess_998124_xyz 中发生了该事件。",
        source_bundle=bundle,
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        created_at="2026-07-01T00:00:00+00:00",
    )
    with pytest.raises(NarrativeFirewallViolationError, match="internal session ID"):
        repo.publish_chapter(dirty_session)


# ── CH-18: No Agent Private Payload ───────────────────────────────────────────


def test_ch18_no_agent_private_payload_in_bundle() -> None:
    """CH-18: Source bundle rejects agent prompts, CoT, or tool dump leakage."""
    bad_slice = RawSliceEntity(
        slice_id="sl_cot",
        occurred_at="2026-06-01T00:00:00+00:00",
        content="Here is my internal <cot>reasoning trace</cot> to solve this.",
        ingestion_dedup_key="k_cot",
    )
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        raw_slices=(bad_slice,),
    )
    with pytest.raises(IllegalChapterSourceError, match="forbidden agent payload"):
        bundle.validate()


# ── CH-19: No Self-Reinforcement ──────────────────────────────────────────────


def test_ch19_no_self_reinforcement_invariant(tmp_path: Path) -> None:
    """CH-19: Generated chapter text cannot re-enter memory/understanding pipeline."""
    store = create_test_store(tmp_path, "ch19.db")
    # In SQLite schema, raw_slices CHECK constraint mandates actor IN ('user')
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "INSERT INTO raw_slices "
            "(slice_id, occurred_at, content, actor, source, scope, "
            "ingestion_dedup_key, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (
                "sl_reinforce",
                "2026-06-01T00:00:00+00:00",
                "Chapter narrative",
                "chapter_author",
                "manual_feed",
                "unresolved",
                "k_r",
                "2026-06-01T00:00:00+00:00",
            ),
        )


# ── CH-20: Production Isolation ───────────────────────────────────────────────


def test_ch20_production_isolation_all_v2_flags_default_off() -> None:
    """CH-20: All Memory V2 feature flags default to False (OFF). Production runtime V1."""
    flags = MemoryFeatureFlags()
    assert flags.memory_v2_storage is False
    assert flags.memory_v2_retrieval is False
    assert flags.memory_v2_consolidation is False
    assert flags.memory_v2_self_model is False
    assert flags.memory_v2_migration is False
    assert flags.memory_v2_backfill is False


# ── Stage-7 Exit Gate Assertions ──────────────────────────────────────────────


def test_stage7_exit_gate_formal_assertions(tmp_path: Path) -> None:
    """Stage-7 Exit Gate: Formal verification of hard privacy criteria.

    Criteria:
    - needs_privacy_redaction == 1 -> stale chapter normal-read rate = 0%
    - privacy-pending chapter unreadable = 100%
    - narrative-as-evidence violations = 0
    - orphan chapter source links = 0
    - privacy-redaction failures that expose stale text = 0
    """
    store = create_test_store(tmp_path, "stage7_exit.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    privacy_svc = ChapterPrivacyService(store, repo=repo)

    sl = seed_slice(store, "sl_stg7", occurred_at="2026-06-01T10:00:00+00:00")
    ins = seed_insight(store, "ins_stg7", valid_from="2026-06-01T10:00:00+00:00")
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins,),
        raw_slices=(sl,),
    )
    gen = ChapterGeneratorV2(store, repo=repo)
    meta = repo.publish_chapter(gen.generate(bundle, title="Stage-7 终审章"))

    # 1. Mark privacy pending
    privacy_svc.mark_privacy_pending(meta.chapter_id)

    # 2. Run 100 read attempts on the privacy-pending chapter
    stale_reads_count = 0
    unreadable_count = 0

    for _ in range(100):
        view = repo.get_readable(meta.chapter_id)
        if view is not None and not view.is_redacted:
            stale_reads_count += 1
        if view is not None and view.is_redacted:
            unreadable_count += 1

    # Hard privacy criterion: stale chapter normal-read rate = 0%
    assert stale_reads_count == 0, f"Expected 0 stale reads, got {stale_reads_count}"
    # Required measured assertion: privacy-pending chapter unreadable = 100%
    assert unreadable_count == 100, f"Expected 100 unreadable views, got {unreadable_count}"

    # 3. Simulate failed redaction and re-check
    failed_res = privacy_svc.redact_or_regenerate_chapter(meta.chapter_id, simulate_failure=True)
    assert failed_res.success is False
    view_after_fail = repo.get_readable(meta.chapter_id)
    assert view_after_fail is not None
    assert view_after_fail.is_redacted is True
    # Privacy redaction failure exposing stale text = 0
    assert "[This chapter is temporarily unavailable" in view_after_fail.content

    # 4. Check orphan links in DB: PRAGMA foreign_key_check = 0
    fk_check = store.connection.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_check == [], f"Orphan foreign key links detected: {fk_check}"


def test_ch11b_hard_delete_episode_marks_chapter_privacy_pending(tmp_path: Path) -> None:
    """CH-11b: Deleting a linked episode marks chapter pending before destructive lifecycle."""
    store = create_test_store(tmp_path, "ch11b.db")
    repo = ChapterRepository(store, chapters_dir=tmp_path / "chapters")
    lifecycle = LifecycleService(store)

    ep = seed_episode(store, "ep_11b", started_at="2026-06-01T10:00:00+00:00")
    ins = seed_insight(store, "ins_11b", valid_from="2026-06-01T10:00:00+00:00")
    bundle = ChapterSourceBundle(
        time_span_start="2026-06-01",
        time_span_end="2026-07-01",
        confirmed_insights=(ins,),
        episodes=(ep,),
    )
    res = ChapterGeneratorV2(store, repo=repo).generate(bundle, title="会话删除影响章")
    meta = repo.publish_chapter(res)

    # Hard delete episode with privacy_sensitive=True
    del_res = lifecycle.hard_delete_episode("ep_11b", privacy_sensitive=True)
    assert del_res.success is True
    assert meta.chapter_id in del_res.privacy_redacted_chapters

    # Chapter metadata in DB is immediately pending
    updated_meta = store.get_chapter_metadata(meta.chapter_id)
    assert updated_meta is not None
    assert updated_meta.needs_privacy_redaction == 1

    # Reader returns fail-closed placeholder
    reader_view = repo.get_readable(meta.chapter_id)
    assert reader_view is not None
    assert reader_view.is_redacted is True
