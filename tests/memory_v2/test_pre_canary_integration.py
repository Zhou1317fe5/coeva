"""Pre-Canary Cross-Lane Invariant Integration Tests (Lane L Gate).

Verifies cross-lane interactions INT-01 through INT-10 across all merged
Memory V2.1 implementation lines:
- INT-01: Raw Evidence write -> WP-5 queue (no queue metadata as evidence)
- INT-02: WP-4 reconciled semantic memory -> WP-7 technical retrieval scoring
- INT-03: WP-7 retrieval candidate -> WP-8 Recall Gate (Retrieved != Injected != Spoken)
- INT-04: WP-6 Confirmed Insight -> WP-9 ChapterSourceBundle (hypothesis rejected)
- INT-05: Cross-layer privacy delete & fail-closed chapter redaction
- INT-06: Narrative firewall (zero automatic writes to evidence/semantic/understanding)
- INT-07: WP-10 migration shadow & WP-11 read-only compatibility views
- INT-08: WP-11 SQLite single master & JSONL post-commit failure isolation
- INT-09: Sanctuary mode task continuity vs reflective/self-model suppression
- INT-10: Production isolation & default V1 behavior
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args
from unittest.mock import MagicMock

import pytest

from src.core.flags import resolve_flags
from src.memory.v2.chapter import (
    ChapterGenerationResult,
    ChapterRepository,
    ChapterSourceBundle,
    IllegalChapterSourceError,
)
from src.memory.v2.chapter_privacy import ChapterPrivacyService
from src.memory.v2.consolidation_queue import ConsolidationQueue
from src.memory.v2.entities import (
    ChapterMetadataEntity,
    ChapterSliceLinkEntity,
    ConfirmedInsightEntity,
    HypothesisEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.jsonl_export import (
    JsonlExportError,
    ReverseImportForbiddenError,
    assert_no_reverse_import,
)
from src.memory.v2.lifecycle import LifecycleService
from src.memory.v2.provenance import ProvenanceKind, ProvenanceRef
from src.memory.v2.recall_gate import (
    RecallContext,
    RecallDisposition,
    RecallGate,
    RecallReason,
)
from src.memory.v2.retrieval.eligibility import HardEligibilityFilter
from src.memory.v2.retrieval.intent import IntentResolver
from src.memory.v2.retrieval.models import (
    CanonicalCandidateRecord,
    RetrievalQueryContext,
    RetrievedCandidate,
)
from src.memory.v2.retrieval.pipeline import TechnicalRetrievalPipeline
from src.memory.v2.retrieval.repository import RetrievalRepository
from src.memory.v2.store import CANONICAL_TABLES, TECHNICAL_METADATA_TABLES, ChronicleStoreV2
from src.memory.v2.write_service import (
    RawEvidenceWriteService,
    WriteSliceCommand,
)

EXPECTED_PROD_DB_HASH = "8b29f3c8714c1ae0ffc5db95a10e73cd299cf1ae74e01f5b8f402880a739df69"
EXPECTED_PROD_JSONL_HASH = "7f80bec3c8ca5bd4e214f470b132814f591b120e7c6174cd0700b1faf3639a6b"


def _make_candidate(
    candidate_id: str = "mem_test_1",
    candidate_type: str = "semantic_memory",
    statement: str = "用户喜欢暗黑代码主题偏好。",
    scope: str = "global",
    project_id: str | None = None,
    valid_from: str = "2026-10-18T10:00:00Z",
    validity_status: str = "active",
    authority_class: str = "user_asserted",
    proof_count: int = 1,
    final_score: float = 0.85,
    provenance_refs: tuple[ProvenanceRef, ...] = (
        ProvenanceRef(kind="slice", target_id="sl_1", role="supporting"),
    ),
) -> RetrievedCandidate:
    """Helper to construct RetrievedCandidate test fixture."""
    return RetrievedCandidate(
        candidate_id=candidate_id,
        candidate_type=candidate_type,
        statement=statement,
        provenance_refs=provenance_refs,
        scope=scope,
        project_id=project_id,
        valid_from=valid_from,
        validity_status=validity_status,
        authority_class=authority_class,
        proof_count=proof_count,
        lexical_score=final_score,
        surface_score=final_score,
        final_score=final_score,
        why_retrieved="test_fixture",
        is_ambiguous=False,
    )


# ==============================================================================
# INT-01: Raw Evidence write -> WP-5 queue
# ==============================================================================


def test_int01_raw_write_to_queue(tmp_path: Path) -> None:
    """INT-01: Canonical Raw Evidence write can enqueue WP-5 metadata without

    queue metadata becoming evidence.
    """
    db_file = tmp_path / "int01.db"
    store = ChronicleStoreV2(db_file)
    write_service = RawEvidenceWriteService(store)
    queue = ConsolidationQueue(store)

    # 1. Write canonical raw slice
    write_res = write_service.write_slice(
        WriteSliceCommand(
            content="用户今天完成了测试模块设计与集成规范",
            source="manual_feed",
            scope="global",
        )
    )
    assert write_res.status == "committed"
    slice_id = write_res.entity.slice_id

    # 2. Enqueue consolidation job
    job = queue.enqueue("slice", slice_id)
    assert job.source_kind == "slice"
    assert job.source_id == slice_id
    assert job.status == "pending"

    # 3. Verify queue row exists in technical metadata table consolidation_jobs
    row = store.connection.execute(
        "SELECT job_id, source_kind, source_id, status FROM consolidation_jobs WHERE job_id = ?;",
        (job.job_id,),
    ).fetchone()
    assert row is not None
    assert row["source_id"] == slice_id

    # 4. Invariant: consolidation_jobs is in TECHNICAL_METADATA_TABLES, NOT in CANONICAL_TABLES
    assert "consolidation_jobs" in TECHNICAL_METADATA_TABLES
    assert "consolidation_jobs" not in CANONICAL_TABLES

    # 5. Invariant: ProvenanceKind has zero queue representation
    valid_provenance_kinds = set(get_args(ProvenanceKind))
    assert "queue" not in valid_provenance_kinds
    assert "consolidation_queue" not in valid_provenance_kinds
    assert "job" not in valid_provenance_kinds

    # 6. Invariant: No queue metadata leaked into canonical evidence tables
    assert store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0] == 0
    assert store.connection.execute("SELECT count(*) FROM observations;").fetchone()[0] == 0
    store.close()


# ==============================================================================
# INT-02: Consolidation -> Retrieval
# ==============================================================================


def test_int02_consolidation_to_retrieval(tmp_path: Path) -> None:
    """INT-02: A reconciled valid Semantic Memory can be retrieved by WP-7

    using frozen scoring.
    """
    db_file = tmp_path / "int02.db"
    store = ChronicleStoreV2(db_file)

    # Insert backing slice and reconciled semantic memory in transaction
    with store.transaction():
        slice_ent = RawSliceEntity(
            slice_id="sl_theme_01",
            occurred_at="2026-10-18T10:00:00Z",
            content="我最喜欢VSCode里的Monokai暗色主题，开发效率最高。",
            source="manual_feed",
            scope="global",
            project_id=None,
            ingestion_dedup_key="dedup_theme_01",
        )
        store.insert_raw_slice(slice_ent)

        mem_ent = SemanticMemoryEntity(
            memory_id="mem_theme_monokai",
            category="preference",
            statement="用户偏好在VSCode编辑器中使用Monokai暗色代码高亮主题。",
            scope="global",
            project_id=None,
            validity_status="active",
            authority_class="user_asserted",
            valid_from="2026-10-18T10:00:00Z",
            source_slice_id="sl_theme_01",
            expression_policy="normal",
        )
        store.insert_semantic_memory(mem_ent)

    # Close write store so read-only retrieval repository has exclusive access
    store.close()

    # Initialize retrieval repository and build derived FTS5 index
    repo = RetrievalRepository(db_file, rebuild_index=True)
    indexed_count = repo.rebuild_derived_index()
    assert indexed_count >= 1

    pipeline = TechnicalRetrievalPipeline(repository=repo)
    query_ctx = RetrievalQueryContext(
        query_text="用户对VSCode的Monokai主题有什么偏好？",
        current_project_id=None,
        sanctuary_active=False,
        now=datetime(2026, 10, 19, 12, 0, tzinfo=UTC),
    )

    retrieval_res = pipeline.retrieve(query_ctx)
    assert retrieval_res.status == "SUCCESS"
    assert len(retrieval_res.candidates) >= 1

    top_cand = retrieval_res.candidates[0]
    assert top_cand.candidate_id == "mem_theme_monokai"
    # Frozen threshold requirement >= 0.16
    assert top_cand.final_score >= 0.16
    repo.close()


# ==============================================================================
# INT-03: Retrieval -> Recall Gate
# ==============================================================================


def test_int03_retrieval_to_recall_gate(tmp_path: Path) -> None:
    """INT-03: Retrieved candidate reaches WP-8 and can be suppressed/allowed

    without becoming spoken output (Retrieved != Injected != Spoken).
    """
    gate = RecallGate()

    cand = _make_candidate(
        candidate_id="mem_pref_python",
        candidate_type="semantic_memory",
        statement="用户偏好严格类型检查并使用 Ruff 进行代码校验。",
        scope="global",
        project_id=None,
        final_score=0.75,
        proof_count=3,
    )

    # 1. Normal allowed query context
    ctx_allowed = RecallContext(
        query_text="我平时喜欢用什么做代码风格检查？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )
    dec_allowed = gate.evaluate([cand], ctx_allowed)
    assert dec_allowed.disposition == RecallDisposition.ALLOW
    assert len(dec_allowed.allowed_candidates) == 1
    # Prompt §1 & INT-03: Injected != Spoken
    assert dec_allowed.injection_context.is_empty is False
    assert len(dec_allowed.injection_context.items) == 1
    injected_text = dec_allowed.injection_context.format_for_prompt()
    assert "Ruff" in injected_text
    # Proves injection is prompt data, NOT UI or spoken dialogue
    assert not hasattr(dec_allowed, "spoken_text")
    assert not hasattr(dec_allowed, "bubble_speech")

    # 2. Suppressed generic query context (matches GENERIC_QA_PATTERNS)
    ctx_suppressed = RecallContext(
        query_text="明天上海天气怎么样？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )
    dec_suppressed = gate.evaluate([cand], ctx_suppressed)
    assert dec_suppressed.disposition == RecallDisposition.SUPPRESS
    assert dec_suppressed.reason == RecallReason.GENERIC_QA_SUPPRESSED
    assert dec_suppressed.injection_context.is_empty is True
    assert len(dec_suppressed.allowed_candidates) == 0


# ==============================================================================
# INT-04: Understanding -> Chapter
# ==============================================================================


def test_int04_understanding_to_chapter(tmp_path: Path) -> None:
    """INT-04: A valid Confirmed Insight from WP-6 can enter WP-9 ChapterSourceBundle;

    candidate Hypothesis cannot.
    """
    # 1. Valid Confirmed Insight enters ChapterSourceBundle
    valid_insight = ConfirmedInsightEntity(
        insight_id="ins_focus_01",
        source_hypothesis_id="hyp_focus_01",
        source_calibration_id="cal_01",
        statement="用户在清晨专注编码时效率最高且较少受到打扰。",
        valid_from="2026-10-18T10:00:00Z",
        status="confirmed",
    )
    bundle = ChapterSourceBundle(
        time_span_start="2026-10-01T00:00:00Z",
        time_span_end="2026-10-28T00:00:00Z",
        confirmed_insights=(valid_insight,),
    )
    bundle.validate()  # Passes without exception
    assert len(bundle.insight_ids) == 1
    assert "ins_focus_01" in bundle.insight_ids

    # 2. Candidate (unconfirmed) status rejected by ChapterSourceBundle
    unconfirmed_insight = ConfirmedInsightEntity(
        insight_id="ins_cand_01",
        source_hypothesis_id="hyp_cand_01",
        source_calibration_id="cal_02",
        statement="用户可能对多任务并发感到轻微疲劳。",
        valid_from="2026-10-18T10:00:00Z",
        status="revalidation_required",  # Unconfirmed
    )
    with pytest.raises(IllegalChapterSourceError, match="status='confirmed'"):
        ChapterSourceBundle(
            time_span_start="2026-10-01T00:00:00Z",
            time_span_end="2026-10-28T00:00:00Z",
            confirmed_insights=(unconfirmed_insight,),
        ).validate()

    # 3. Invariant: Hypothesis cannot enter ChapterSourceBundle
    # Attempting to supply a HypothesisEntity as an insight fails validation
    bundle_with_hyp = ChapterSourceBundle(
        time_span_start="2026-10-01T00:00:00Z",
        time_span_end="2026-10-28T00:00:00Z",
        confirmed_insights=(
            HypothesisEntity(  # type: ignore[arg-type]
                hypothesis_id="hyp_01",
                statement="s",
                lenses="lens",
                confidence_class="tentative",
                status="candidate",
            ),
        ),
    )
    with pytest.raises((AttributeError, IllegalChapterSourceError)):
        bundle_with_hyp.validate()


# ==============================================================================
# INT-05: Privacy delete across layers
# ==============================================================================


def test_int05_privacy_delete_across_layers(tmp_path: Path) -> None:
    """INT-05: Hard-delete linked evidence:

    - lifecycle recomputes/retracts understanding as required;
    - impacted Chapter becomes privacy-pending;
    - stale chapter unreadable immediately;
    - retrieval cannot surface privacy-pending chapter.
    """
    db_file = tmp_path / "int05.db"
    store = ChronicleStoreV2(db_file)
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    chap_file = chapters_dir / "chapter_chap_2026_10.md"
    chap_file.write_text("# 初秋的工程探索\n\n那是一段深刻的旅程。", encoding="utf-8")

    repo = ChapterRepository(store, chapters_dir=chapters_dir)
    lifecycle = LifecycleService(store)

    # 1. Insert slice and chapter in transaction
    with store.transaction():
        slice_ent = RawSliceEntity(
            slice_id="sl_secret_01",
            occurred_at="2026-10-18T10:00:00Z",
            content="个人私密笔记：项目内部通信密码已修改",
            source="manual_feed",
            scope="global",
            project_id=None,
            ingestion_dedup_key="dedup_secret_01",
        )
        store.insert_raw_slice(slice_ent)

        chap_meta = ChapterMetadataEntity(
            chapter_id="chap_2026_10",
            title="初秋的工程探索",
            file_path=str(chap_file),
            time_span_start="2026-10-01T00:00:00Z",
            time_span_end="2026-10-28T00:00:00Z",
            needs_privacy_redaction=0,
            created_at="2026-10-28T12:00:00Z",
        )
        store.insert_chapter_metadata(chap_meta)
        store.insert_chapter_slice_link(
            ChapterSliceLinkEntity(chapter_id="chap_2026_10", slice_id="sl_secret_01")
        )

    # Stale read is valid prior to deletion
    r_before = repo.get_readable("chap_2026_10")
    assert r_before is not None
    assert r_before.is_redacted is False
    assert r_before.needs_privacy_redaction == 0
    assert "那是一段深刻的旅程" in r_before.content

    # 2. Hard-delete linked slice with privacy_sensitive=True
    del_res = lifecycle.hard_delete_slice("sl_secret_01", privacy_sensitive=True)
    assert del_res.success is True
    assert "chap_2026_10" in del_res.privacy_redacted_chapters

    # 3. Chapter is immediately privacy-pending in DB
    updated_meta = store.get_chapter_metadata("chap_2026_10")
    assert updated_meta is not None
    assert updated_meta.needs_privacy_redaction == 1

    # 4. Stale chapter is unreadable immediately (normal-read rate = 0%)
    r_after = repo.get_readable("chap_2026_10")
    assert r_after is not None
    assert r_after.is_redacted is True
    assert r_after.needs_privacy_redaction == 1
    assert "那是一段深刻的旅程" not in r_after.content
    assert "[This chapter is temporarily unavailable" in r_after.content

    # 5. Retrieval HardEligibilityFilter drops privacy-pending candidate
    cand_chap = CanonicalCandidateRecord(
        candidate_id="chap_2026_10",
        candidate_type="chapter_metadata",
        category="narrative",
        statement="初秋的工程探索",
        scope="global",
        project_id=None,
        valid_from="2026-10-01T00:00:00Z",
        validity_status="active",
        authority_class="user_confirmed",
        proof_count=1,
        needs_privacy_redaction=1,
        expression_policy="normal",
        provenance_refs=(),
    )
    hard_filter = HardEligibilityFilter()
    ctx = RetrievalQueryContext(query_text="查看我们过去的故事")
    intent = IntentResolver().resolve(ctx)
    assert hard_filter.is_eligible(cand_chap, ctx, intent) is False
    store.close()


# ==============================================================================
# INT-06: Narrative firewall
# ==============================================================================


def test_int06_narrative_firewall(tmp_path: Path) -> None:
    """INT-06: Chapter publish/redaction produces zero automatic

    Evidence/Semantic/Observation/Hypothesis writes.
    """
    db_file = tmp_path / "int06.db"
    store = ChronicleStoreV2(db_file)
    chapters_dir = tmp_path / "chapters"
    repo = ChapterRepository(store, chapters_dir=chapters_dir)
    privacy_svc = ChapterPrivacyService(store, repo)

    # Insert prerequisite slice for bundle in transaction
    with store.transaction():
        slice_ent = RawSliceEntity(
            slice_id="sl_valid_01",
            occurred_at="2026-10-01T10:00:00Z",
            content="完成了基础设计与重构",
            source="manual_feed",
            scope="global",
            project_id=None,
            ingestion_dedup_key="dedup_valid_01",
        )
        store.insert_raw_slice(slice_ent)

    def count_evidence_tables() -> dict[str, int]:
        c = store.connection
        return {
            "raw_slices": c.execute("SELECT count(*) FROM raw_slices;").fetchone()[0],
            "event_skeletons": c.execute("SELECT count(*) FROM event_skeletons;").fetchone()[0],
            "semantic_memories": c.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0],
            "observations": c.execute("SELECT count(*) FROM observations;").fetchone()[0],
            "hypotheses": c.execute("SELECT count(*) FROM hypotheses;").fetchone()[0],
            "confirmed_insights": c.execute("SELECT count(*) FROM confirmed_insights;").fetchone()[
                0
            ],
        }

    counts_before_publish = count_evidence_tables()

    # Publish chapter
    bundle = ChapterSourceBundle(
        time_span_start="2026-10-01T00:00:00Z",
        time_span_end="2026-10-28T00:00:00Z",
        raw_slices=(slice_ent,),
    )
    gen_result = ChapterGenerationResult(
        chapter_id="chap_fw_01",
        title="工坊沉思录",
        file_path="chapter_chap_fw_01.md",
        time_span_start="2026-10-01T00:00:00Z",
        time_span_end="2026-10-28T00:00:00Z",
        created_at="2026-10-28T12:00:00Z",
        markdown_content="""# 工坊沉思录

## 一、那段日子的轮廓
我们一起专注于重构核心模块，代码逐渐清晰。

## 二、我们是如何共事的
安静地记录每一个提交，按部就班。

## 三、那些重要的转变
系统架构变得稳固，减少了不必要的外部依赖。

## 四、留给未来的路标
继续保持这种专注与质朴的节奏。
""",
        source_bundle=bundle,
    )
    repo.publish_chapter(gen_result)

    counts_after_publish = count_evidence_tables()
    # 0 automatic writes during publish
    assert counts_before_publish == counts_after_publish

    # Redact chapter
    privacy_svc.mark_privacy_pending("chap_fw_01")
    redaction_res = privacy_svc.redact_or_regenerate_chapter("chap_fw_01")
    assert redaction_res.success is True

    counts_after_redaction = count_evidence_tables()
    # 0 automatic writes during redaction
    assert counts_after_publish == counts_after_redaction
    store.close()


# ==============================================================================
# INT-07: Migration -> Compatibility
# ==============================================================================


def test_int07_migration_to_compatibility(tmp_path: Path) -> None:
    """INT-07: WP-10 scratch shadow has no compatibility views initially;

    WP-11 explicit installer can add read-only views; canonical source parity
    remains unchanged.
    """
    db_file = tmp_path / "int07_shadow.db"
    store = ChronicleStoreV2(db_file)

    # Insert canonical raw slices in transaction
    with store.transaction():
        for i in range(3):
            store.insert_raw_slice(
                RawSliceEntity(
                    slice_id=f"sl_shadow_{i}",
                    occurred_at="2026-10-18T10:00:00Z",
                    content=f"迁移影子数据测试 {i}",
                    source="manual_feed",
                    scope="global",
                    project_id=None,
                    ingestion_dedup_key=f"dedup_shadow_{i}",
                )
            )

    # 1. WP-10 scratch shadow initially has NO compatibility views
    assert store.has_compatibility_views() is False
    view_rows = store.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='view' "
        "AND name IN ('legacy_slices_view', 'legacy_events_view');"
    ).fetchall()
    assert len(view_rows) == 0
    # 2. WP-11 explicitly installs read-only compatibility views
    store.install_compatibility_views()
    assert store.has_compatibility_views() is True
    assert store.verify_compatibility_views_read_only() is True

    # 3. Views are strictly read-only (writes fail closed)
    with pytest.raises(sqlite3.OperationalError):
        store.connection.execute(
            "INSERT INTO legacy_slices_view (id, timestamp, content) "
            "VALUES (999, 'now', 'illegal write');"
        )
    raw_count = store.connection.execute("SELECT count(*) FROM raw_slices;").fetchone()[0]
    view_count = store.connection.execute("SELECT count(*) FROM legacy_slices_view;").fetchone()[0]
    assert raw_count == view_count == 3
    store.close()


# ==============================================================================
# INT-08: Single Master
# ==============================================================================


def test_int08_single_master(tmp_path: Path) -> None:
    """INT-08: In scratch V2 mode:

    - SQLite commit defines truth;
    - JSONL exporter failure does not invalidate ACKed SQLite write;
    - JSONL cannot reverse-import into V2.
    """
    db_file = tmp_path / "int08.db"
    store = ChronicleStoreV2(db_file)

    # Failing exporter mock
    failing_exporter = MagicMock()
    failing_exporter.export_slice.side_effect = JsonlExportError("Disk full or permission denied")

    service = RawEvidenceWriteService(store, exporter=failing_exporter)

    # 1. Write slice with failing exporter
    cmd = WriteSliceCommand(
        content="重要项目设计规范：SQLite是唯一主数据源",
        source="manual_feed",
        scope="global",
    )
    result = service.write_slice(cmd)

    # SQLite write committed durably despite exporter failure!
    assert result.status == "committed"
    assert result.entity.slice_id is not None

    # Verify slice exists in SQLite canonical store
    persisted = store.get_raw_slice(result.entity.slice_id)
    assert persisted is not None
    assert persisted.content == "重要项目设计规范：SQLite是唯一主数据源"

    # 2. Invariant: JSONL cannot reverse-import into V2
    with pytest.raises(ReverseImportForbiddenError, match="Reverse import forbidden"):
        assert_no_reverse_import()
    store.close()


# ==============================================================================
# INT-09: Sanctuary task continuity vs reflective block
# ==============================================================================


def test_int09_sanctuary_task_continuity() -> None:
    """INT-09: Current/recent task continuity survives Sanctuary while

    reflective/self-model recall remains blocked.
    """
    gate = RecallGate()

    # Candidate 1: Psychological self-model / confirmed insight
    cand_reflective = _make_candidate(
        candidate_id="ins_psych_01",
        candidate_type="confirmed_insight",
        statement="用户在高负荷排错时容易产生焦虑急躁情绪。",
        scope="global",
        project_id=None,
        final_score=0.65,
        proof_count=2,
    )

    # Candidate 2: Current project technical task continuity
    cand_task_continuity = _make_candidate(
        candidate_id="ep_task_cont_01",
        candidate_type="episode",
        statement="刚才运行测试时遭遇 PySide6 DLL load failed 动态链接库丢失报错。",
        scope="project",
        project_id="co-evolving-companion",
        final_score=0.82,
        proof_count=1,
    )

    # Sanctuary active query context
    ctx_sanctuary = RecallContext(
        query_text="烦死了，又是刚才那个动态链接库报错",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
    )

    # Case A: Reflective / self-model recall is BLOCKED under Sanctuary
    dec_reflective = gate.evaluate([cand_reflective], ctx_sanctuary)
    assert dec_reflective.disposition == RecallDisposition.SUPPRESS
    assert dec_reflective.reason == RecallReason.SANCTUARY_REFLECTIVE_BLOCK
    assert dec_reflective.injection_context.is_empty is True
    assert len(dec_reflective.allowed_candidates) == 0

    # Case B: Current task continuity survives and is ALLOWED under Sanctuary
    dec_task = gate.evaluate([cand_task_continuity], ctx_sanctuary)
    assert dec_task.disposition == RecallDisposition.TASK_CONTINUITY_ONLY
    assert dec_task.reason == RecallReason.TASK_CONTINUITY_ALLOWED
    assert dec_task.injection_context.is_empty is False
    assert len(dec_task.allowed_candidates) == 1
    assert "PySide6 DLL load failed" in dec_task.injection_context.items[0].statement


# ==============================================================================
# INT-10: Production isolation & default V1 behavior
# ==============================================================================


def test_int10_production_isolation() -> None:
    """INT-10: All integration tests operate on scratch/temp/copies only.

    Production DB/JSONL untouched and all V2 feature flags default strictly
    OFF.
    """
    # 1. Feature flags default strictly OFF
    flags = resolve_flags()
    assert flags.memory_v2_storage is False
    assert flags.memory_v2_retrieval is False
    assert flags.memory_v2_consolidation is False
    assert flags.memory_v2_self_model is False
    assert flags.memory_v2_migration is False
    assert flags.memory_v2_backfill is False

    # 2. Production DB file exists and its hash is untouched
    prod_db = Path("data/companion_chronicle.db")
    if prod_db.exists():
        h = hashlib.sha256(prod_db.read_bytes()).hexdigest().lower()
        assert h == EXPECTED_PROD_DB_HASH

    # 3. Production raw_slices.jsonl exists and its hash is untouched
    prod_jsonl = Path("data/raw_slices.jsonl")
    if prod_jsonl.exists():
        h_jsonl = hashlib.sha256(prod_jsonl.read_bytes()).hexdigest().lower()
        assert h_jsonl == EXPECTED_PROD_JSONL_HASH
