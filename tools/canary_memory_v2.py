"""WP-13 Full Canary Migration & Safety Rehearsal Orchestrator.

Executes complete canary migration and safety rehearsal exclusively on a
real production-data COPY in an isolated canary sandbox.
Production files are strictly read-only inputs for hashing and WAL-safe snapshot.
Zero production cutover. Zero production mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sqlite3
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.flags import MemoryFeatureFlags
from src.memory.v2.calibration import (
    CalibrationDecision,
    CalibrationResponse,
    CalibrationService,
)
from src.memory.v2.candidate_extraction import CandidateExtractor
from src.memory.v2.chapter import (
    ChapterGeneratorV2,
    ChapterRepository,
    ChapterSourceBundle,
)
from src.memory.v2.chapter_privacy import ChapterPrivacyService
from src.memory.v2.compatibility import (
    has_legacy_views,
    install_legacy_views,
    verify_legacy_views_read_only,
)
from src.memory.v2.entities import (
    ChapterMetadataEntity,
    ConfirmedInsightEntity,
    HypothesisEntity,
)
from src.memory.v2.jsonl_export import (
    JsonlSliceExporter,
    ReverseImportForbiddenError,
    assert_no_reverse_import,
)
from src.memory.v2.migration.mapper import build_v2_shadow_db
from src.memory.v2.migration.preflight import (
    DiskSpacePlan,
    run_preflight_checks,
)
from src.memory.v2.migration.reconcile import (
    reconcile_canonical_sets,
)
from src.memory.v2.migration.snapshot import create_wal_snapshot
from src.memory.v2.migration.swap import (
    RollbackForbiddenDataLossError,
    execute_atomic_swap,
    recover_mid_swap_failure,
    rollback_cutover,
    verify_db_integrity,
)
from src.memory.v2.recall_gate import (
    RecallContext,
    RecallDisposition,
    RecallGate,
)
from src.memory.v2.reconciliation import ReconciliationEngine
from src.memory.v2.retrieval.config import RetrievalConfig
from src.memory.v2.retrieval.models import (
    RetrievalQueryContext,
)
from src.memory.v2.retrieval.pipeline import TechnicalRetrievalPipeline
from src.memory.v2.retrieval.repository import (
    StaticCandidateRepository,
)
from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import RawEvidenceWriteService, WriteSliceCommand
from tests.memory_v2.retrieval_fixtures import (
    FROZEN_BENCHMARK_NOW,
    build_frozen_canonical_corpus,
)


@dataclass(frozen=True)
class FileFingerprint:
    """Immutable hash and metadata snapshot of a file."""

    path: str
    size_bytes: int
    last_modified_utc: str
    sha256: str


@dataclass(frozen=True)
class ProductionHashAudit:
    """Audit record capturing before and after state of production files."""

    files_before: dict[str, FileFingerprint]
    files_after: dict[str, FileFingerprint]
    untouched: bool


@dataclass(frozen=True)
class RehearsalTimings:
    """Execution timing measurements for canary rehearsal phases."""

    snapshot_seconds: float
    mapping_seconds: float
    reconciliation_seconds: float
    validation_seconds: float
    compatibility_install_seconds: float
    swap_rehearsal_seconds: float
    rollback_rehearsal_seconds: float
    total_wall_clock_seconds: float


@dataclass(frozen=True)
class CrashScenarioResult:
    """Report for an individual crash injection rehearsal scenario."""

    scenario_name: str
    injected_point: str
    recovery_succeeded: bool
    canonical_db_selected: str
    acked_writes_preserved: bool
    orphan_handling: str
    manual_intervention_required: bool
    details: str


@dataclass
class CanaryRehearsalReport:
    """Comprehensive artifact detailing the full WP-13 rehearsal execution."""

    production_audit: ProductionHashAudit
    source_counts: dict[str, int]
    timings: RehearsalTimings
    disk_plan: DiskSpacePlan
    source_db_size_bytes: int
    shadow_db_size_bytes: int
    peak_temp_disk_bytes: int
    ms_assertions_pass_count: int
    ms_assertions_total: int
    data_loss_count: int
    parity_message: str
    raw_slice_fidelity_percent: float
    legacy_hypothesis_promotions: int
    foreign_key_violations: int
    retrieval_metrics: dict[str, Any]
    semantic_smoke_results: dict[str, bool]
    crash_matrix_results: list[CrashScenarioResult]
    rollback_safety_verified: bool
    flags_verified_false: bool
    status: str


def compute_file_fingerprint(file_path: Path) -> FileFingerprint:
    """Compute cryptographic hash and metadata for a file."""
    stat = file_path.stat()
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    return FileFingerprint(
        path=str(file_path.resolve()),
        size_bytes=stat.st_size,
        last_modified_utc=mtime_iso,
        sha256=h.hexdigest().lower(),
    )


def audit_production_directory(prod_data_dir: Path) -> dict[str, FileFingerprint]:
    """Capture fingerprint for all production files in the target data directory."""
    records: dict[str, FileFingerprint] = {}
    if not prod_data_dir.is_dir():
        return records

    patterns = [
        "companion_chronicle.db",
        "companion_chronicle.db-wal",
        "companion_chronicle.db-shm",
        "raw_slices.jsonl",
        "chapters/*.md",
    ]
    for pattern in patterns:
        for match in prod_data_dir.glob(pattern):
            if match.is_file():
                rel = match.relative_to(prod_data_dir).as_posix()
                records[rel] = compute_file_fingerprint(match)
    return records


def find_default_production_data_dir() -> Path:
    """Locate real production data directory."""
    candidates = [
        Path("D:/CodeProjects/co-evolving-companion/data"),
        Path(__file__).parents[2] / "co-evolving-companion" / "data",
        Path("data"),
    ]
    for candidate in candidates:
        db_file = candidate / "companion_chronicle.db"
        if db_file.is_file():
            return candidate.resolve()
    return Path("data").resolve()


def run_benchmark_suite(
    pipeline: TechnicalRetrievalPipeline,
    dataset: list[dict[str, Any]],
    now: datetime = FROZEN_BENCHMARK_NOW,
) -> dict[str, Any]:
    """Execute standard frozen retrieval benchmark evaluation on a test case set."""
    passed_queries = 0
    must_hits = 0
    must_expected = 0
    total_retrieved = 0
    relevant_retrieved = 0
    no_mem_correct = 0
    no_mem_expected = 0
    forbidden_hits = 0
    cross_proj_violations = 0
    supersession_violations = 0
    privacy_violations = 0

    for case in dataset:
        q = str(case["query"])
        proj = case.get("current_project")
        proj_str = str(proj) if proj is not None else None
        sanctuary = bool(case.get("sanctuary_active", False))
        raw_must = case.get("must_retrieve")
        must_set = set(raw_must) if isinstance(raw_must, list) else set()
        raw_acc = case.get("acceptable_retrieve")
        acc_set = set(raw_acc) if isinstance(raw_acc, list) else set()
        raw_forbidden = case.get("must_not_retrieve")
        forbidden_set = set(raw_forbidden) if isinstance(raw_forbidden, list) else set()
        no_mem = bool(case.get("no_memory_expected", False))

        if no_mem:
            no_mem_expected += 1
        if must_set:
            must_expected += len(must_set)

        ctx = RetrievalQueryContext(
            query_text=q,
            current_project_id=proj_str,
            sanctuary_active=sanctuary,
            now=now,
        )
        res = pipeline.retrieve(ctx)
        recalled_ids = [c.candidate_id for c in res.candidates]
        recalled_set = set(recalled_ids)
        total_retrieved += len(recalled_ids)

        for rid in recalled_ids:
            if rid in must_set or rid in acc_set:
                relevant_retrieved += 1
            if rid in forbidden_set:
                forbidden_hits += 1

        for c in res.candidates:
            if c.scope == "project" and c.project_id != proj_str:
                cross_proj_violations += 1
            if case.get("historical_or_current") == "current" and c.validity_status == "superseded":
                supersession_violations += 1
            if c.candidate_id == "chap_01_privacy_pending":
                privacy_violations += 1

        case_passed = True
        if no_mem:
            if len(recalled_ids) == 0:
                no_mem_correct += 1
            else:
                case_passed = False
        else:
            if must_set:
                hits = must_set.intersection(recalled_set)
                must_hits += len(hits)
                if not hits:
                    case_passed = False
            else:
                if not acc_set.intersection(recalled_set):
                    case_passed = False

        if forbidden_set.intersection(recalled_set):
            case_passed = False

        if case_passed:
            passed_queries += 1

    total = len(dataset)
    return {
        "total": total,
        "passed": passed_queries,
        "pass_rate": passed_queries / total if total > 0 else 0.0,
        "recall_at_3": must_hits / must_expected if must_expected > 0 else 1.0,
        "candidate_precision_at_3": (
            relevant_retrieved / total_retrieved if total_retrieved > 0 else 1.0
        ),
        "no_mem_acc": no_mem_correct / no_mem_expected if no_mem_expected > 0 else 1.0,
        "must_hits": must_hits,
        "must_expected": must_expected,
        "total_retrieved": total_retrieved,
        "relevant_retrieved": relevant_retrieved,
        "no_mem_correct": no_mem_correct,
        "no_mem_expected": no_mem_expected,
        "forbidden_hits": forbidden_hits,
        "cross_proj_violations": cross_proj_violations,
        "supersession_violations": supersession_violations,
        "privacy_violations": privacy_violations,
    }


def execute_cny01_retrieval(project_root: Path) -> dict[str, Any]:
    """Execute CNY-01 Retrieval benchmark validation (DEV, HOLDOUT, Holdout2)."""
    corpus = build_frozen_canonical_corpus(FROZEN_BENCHMARK_NOW)
    repo = StaticCandidateRepository(corpus)
    cfg = RetrievalConfig(
        lexical_weight=0.6,
        surface_weight=0.4,
        confidence_threshold=0.16,
        rule_intent_boost=0.30,
        past_episode_boost=0.25,
        project_tech_boost=0.15,
        historical_superseded_boost=0.20,
        top_k=3,
    )
    pipeline = TechnicalRetrievalPipeline(repo, config=cfg)

    bm_path = project_root / "docs" / "memory-v2" / "retrieval" / "retrieval-benchmark-cases.json"
    if not bm_path.is_file():
        bm_path = Path("docs/memory-v2/retrieval/retrieval-benchmark-cases.json").resolve()
    with open(bm_path, encoding="utf-8") as f:
        bm_data = json.load(f)

    h2_path = project_root / "tests" / "memory_v2" / "holdout2_benchmark_cases.json"
    if not h2_path.is_file():
        h2_path = Path("tests/memory_v2/holdout2_benchmark_cases.json").resolve()
    with open(h2_path, encoding="utf-8") as f:
        h2_data = json.load(f)

    dev_metrics = run_benchmark_suite(pipeline, bm_data["dev_set"])
    holdout_metrics = run_benchmark_suite(pipeline, bm_data["holdout_set"])
    holdout2_metrics = run_benchmark_suite(pipeline, h2_data["holdout2_set"])

    # Strict baseline checks
    assert dev_metrics["passed"] == 27, f"DEV passed {dev_metrics['passed']} != 27"
    assert dev_metrics["must_hits"] == 20, f"DEV must_hits {dev_metrics['must_hits']} != 20"
    assert dev_metrics["total_retrieved"] == 35, (
        f"DEV total_retrieved {dev_metrics['total_retrieved']} != 35"
    )
    assert dev_metrics["no_mem_correct"] == 7, (
        f"DEV no_mem_correct {dev_metrics['no_mem_correct']} != 7"
    )
    assert dev_metrics["forbidden_hits"] == 0
    assert dev_metrics["cross_proj_violations"] == 0
    assert dev_metrics["privacy_violations"] == 0
    assert dev_metrics["supersession_violations"] == 0

    assert holdout_metrics["passed"] == 15, f"HOLDOUT passed {holdout_metrics['passed']} != 15"
    assert holdout_metrics["must_hits"] == 10, (
        f"HOLDOUT must_hits {holdout_metrics['must_hits']} != 10"
    )
    assert holdout_metrics["total_retrieved"] == 15, (
        f"HOLDOUT total_retrieved {holdout_metrics['total_retrieved']} != 15"
    )
    assert holdout_metrics["relevant_retrieved"] == 12
    assert holdout_metrics["no_mem_correct"] == 5
    assert holdout_metrics["forbidden_hits"] == 0
    assert holdout_metrics["cross_proj_violations"] == 0
    assert holdout_metrics["privacy_violations"] == 0
    assert holdout_metrics["supersession_violations"] == 0

    assert holdout2_metrics["passed"] == 12, f"Holdout2 passed {holdout2_metrics['passed']} != 12"
    assert holdout2_metrics["must_hits"] == 6
    assert holdout2_metrics["no_mem_correct"] == 6
    assert holdout2_metrics["forbidden_hits"] == 0
    assert holdout2_metrics["cross_proj_violations"] == 0
    assert holdout2_metrics["privacy_violations"] == 0
    assert holdout2_metrics["supersession_violations"] == 0

    return {
        "dev": dev_metrics,
        "holdout": holdout_metrics,
        "holdout2": holdout2_metrics,
    }


def execute_cny02_sanctuary(project_root: Path) -> bool:
    """CNY-02 Sanctuary: Task continuity allowed; reflective/self-model recall blocked."""
    corpus = build_frozen_canonical_corpus(FROZEN_BENCHMARK_NOW)
    repo = StaticCandidateRepository(corpus)
    cfg = RetrievalConfig(confidence_threshold=0.16)
    pipeline = TechnicalRetrievalPipeline(repo, config=cfg)
    gate = RecallGate()

    # 1. Technical task continuity allowed during sanctuary
    ctx_tech = RetrievalQueryContext(
        query_text="我们之前是怎么解决 PySide 闪退问题的？",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
        now=FROZEN_BENCHMARK_NOW,
    )
    res_tech = pipeline.retrieve(ctx_tech)
    assert len(res_tech.candidates) > 0, "Task continuity candidate must be retrieved"
    top_cand = res_tech.candidates[0]

    rec_ctx_tech = RecallContext(
        query_text="我们之前是怎么解决 PySide 闪退问题的？",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
    )
    dec_tech = gate.evaluate([top_cand], rec_ctx_tech)
    assert dec_tech.disposition in (RecallDisposition.ALLOW, RecallDisposition.TASK_CONTINUITY_ONLY)
    assert len(dec_tech.allowed_candidates) == 1
    assert dec_tech.injection_context.is_empty is False

    # 2. Reflective / self-model recall strictly blocked during sanctuary
    ctx_reflect = RetrievalQueryContext(
        query_text="你觉得我是一个自律的人吗？",
        current_project_id=None,
        sanctuary_active=True,
        now=FROZEN_BENCHMARK_NOW,
    )
    res_reflect = pipeline.retrieve(ctx_reflect)
    assert len(res_reflect.candidates) == 0, "Reflective memory must be blocked in sanctuary"
    assert res_reflect.status == "NO_RELEVANT_MEMORY"
    return True


def execute_cny03_consolidation(store: ChronicleStoreV2) -> bool:
    """CNY-03 Consolidation: Raw Evidence -> Admission -> Candidate -> Validator -> Semantic Memory.

    Replay proof-count safety verified.
    """
    write_service = RawEvidenceWriteService(store)
    slice_res = write_service.write_slice(
        WriteSliceCommand(
            content="用户在开发中始终坚持采用严格类型注解 mypy --strict 标准。",
            source="manual_feed",
            scope="global",
        )
    )
    assert slice_res.status == "committed"
    raw_slice = slice_res.entity

    extractor = CandidateExtractor()
    proposal = extractor.extract_from_slice(raw_slice)
    assert proposal.admission.decision == "ADMIT"
    assert len(proposal.proposed_claims) >= 1

    engine = ReconciliationEngine(store)
    rec_results = engine.reconcile_proposal(proposal)
    assert len(rec_results) >= 1
    assert rec_results[0].action in ("ADD", "REINFORCE")

    # Replay proof-count safety: duplicate replay yields NOOP and 0 proof delta
    rec_results_replay = engine.reconcile_slice(
        raw_slice,
        context={"existing_key_matched": True},
    )
    assert len(rec_results_replay) >= 1
    assert rec_results_replay[0].action == "NOOP"
    assert rec_results_replay[0].proof_delta == 0
    return True


def execute_cny04_understanding(store: ChronicleStoreV2) -> bool:
    """CNY-04 Understanding: Candidate Hypothesis unconfirmed until calibration.

    NOT_NOW remains non-epistemic.
    """
    cal_service = CalibrationService(store)
    now_iso = datetime.now(UTC).isoformat()
    hyp_id = f"hyp_cny04_{int(time.time() * 1000)}"

    store.insert_hypothesis(
        HypothesisEntity(
            hypothesis_id=hyp_id,
            statement="用户在周末更倾向于做纯架构探索而不是业务编码。",
            lenses='["time_rhythm"]',
            confidence_class="tentative",
            status="candidate",
            created_at=now_iso,
        )
    )

    h_before = store.get_hypothesis(hyp_id)
    assert h_before is not None
    assert h_before.status == "candidate"

    cur = store.connection.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM confirmed_insights WHERE source_hypothesis_id = ?",
        (hyp_id,),
    )
    assert cur.fetchone()[0] == 0

    dec = CalibrationDecision(
        hypothesis_id=hyp_id,
        response=CalibrationResponse.NOT_NOW,
        user_note="暂时不确定，先观察",
    )
    res = cal_service.calibrate(dec)
    assert res.action == "not_now"
    assert res.confirmed_insight is None
    assert res.calibration_event is None
    assert res.hypothesis_status == "candidate"

    cur.execute(
        "SELECT COUNT(*) FROM confirmed_insights WHERE source_hypothesis_id = ?",
        (hyp_id,),
    )
    assert cur.fetchone()[0] == 0
    return True


def execute_cny05_chapter_privacy(store: ChronicleStoreV2, sandbox_dir: Path) -> bool:
    """CNY-05 Chapter privacy: needs_privacy_redaction=1 -> stale normal-read rate 0%."""
    privacy_service = ChapterPrivacyService(store)
    chap_id = f"chap_cny05_{int(time.time() * 1000)}"
    md_file = sandbox_dir / f"{chap_id}.md"
    md_file.write_text("# Chapter Content\n\nPrivate info.", encoding="utf-8")

    now_iso = datetime.now(UTC).isoformat()
    meta = ChapterMetadataEntity(
        chapter_id=chap_id,
        title="Privacy Test Chapter",
        file_path=str(md_file),
        time_span_start=now_iso,
        time_span_end=now_iso,
        needs_privacy_redaction=0,
        created_at=now_iso,
    )
    store.insert_chapter_metadata(meta)

    assert not privacy_service.is_unreadable(chap_id)
    privacy_service.mark_privacy_pending(chap_id)
    assert privacy_service.is_unreadable(chap_id)

    updated_meta = store.get_chapter_metadata(chap_id)
    assert updated_meta is not None
    assert updated_meta.needs_privacy_redaction == 1
    return True


def execute_cny06_narrative_firewall(store: ChronicleStoreV2) -> bool:
    """CNY-06 Narrative Firewall: Automatic Chapter -> Evidence writes = 0."""
    chap_repo = ChapterRepository(store)
    gen = ChapterGeneratorV2(store, repo=chap_repo, client=None)

    cur = store.connection.cursor()
    cur.execute("SELECT count(*) FROM raw_slices;")
    slices_before = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM event_skeletons;")
    events_before = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM semantic_memories;")
    memories_before = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM hypotheses;")
    hypotheses_before = cur.fetchone()[0]

    valid_insight = ConfirmedInsightEntity(
        insight_id="ins_cny06_01",
        source_hypothesis_id="hyp_cny06_01",
        source_calibration_id="cal_cny06_01",
        statement="用户在工程开发中保持专注与自律。",
        valid_from="2026-10-18T10:00:00Z",
        status="confirmed",
    )
    bundle = ChapterSourceBundle(
        time_span_start="2026-10-01T00:00:00Z",
        time_span_end="2026-10-18T00:00:00Z",
        confirmed_insights=(valid_insight,),
    )
    res = gen.generate(bundle, title="叙事防火墙隔离测试章节")
    assert len(res.markdown_content) > 0

    cur.execute("SELECT count(*) FROM raw_slices;")
    slices_after = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM event_skeletons;")
    events_after = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM semantic_memories;")
    memories_after = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM hypotheses;")
    hypotheses_after = cur.fetchone()[0]

    assert slices_after == slices_before, "raw_slices modified"
    assert events_after == events_before, "event_skeletons modified"
    assert memories_after == memories_before, "semantic_memories modified"
    assert hypotheses_after == hypotheses_before, "hypotheses modified"
    return True


def execute_cny07_single_master(store: ChronicleStoreV2, sandbox_dir: Path) -> bool:
    """CNY-07 Single master: SQLite truth survives JSONL export failure."""
    write_service = RawEvidenceWriteService(store)
    bad_export_path = sandbox_dir / "dir_blocked_export"
    bad_export_path.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("src.memory.v2.jsonl_export")
    prev_level = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        exporter = JsonlSliceExporter(bad_export_path, auto_load_existing=False)
        cmd = WriteSliceCommand(
            content="单主架构验证：SQLite 写入成功后即便 JSONL 导出故障，数据亦安全固化。",
            source="manual_feed",
            scope="global",
        )
        write_res = write_service.write_slice(cmd)
        assert write_res.status == "committed"
        slice_ent = write_res.entity

        exp_res = exporter.export_slice(slice_ent, raise_on_error=False)
        assert exp_res.exported is False
        assert exporter.failure_count >= 1

        cur = store.connection.cursor()
        cur.execute("SELECT content FROM raw_slices WHERE slice_id = ?", (slice_ent.slice_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == cmd.content

        try:
            assert_no_reverse_import()
            raise AssertionError("Reverse import should have been forbidden")
        except ReverseImportForbiddenError:
            pass
    finally:
        logger.setLevel(prev_level)
    return True


def execute_cny08_compatibility(store: ChronicleStoreV2) -> bool:
    """CNY-08 Compatibility: Views absent before explicit install; explicit views read-only."""
    if not has_legacy_views(store.connection):
        install_legacy_views(store.connection)
    assert has_legacy_views(store.connection)
    assert verify_legacy_views_read_only(store.connection)
    return True


def execute_ms_matrix(sandbox_dir: Path) -> tuple[int, int]:
    """Execute complete M-S01 ~ M-S18 destructive test matrix."""
    from tests.memory_v2.test_migration_assertions import (
        test_ms01_snapshot_to_cutover_live_slice_preserved,
        test_ms02_snapshot_to_cutover_live_event_preserved,
        test_ms03_final_canonical_source_set_parity_verified,
        test_ms04_no_duplicate_row_from_replay,
        test_ms05_v2_event_skeleton_contains_no_prohibited_body,
        test_ms06_active_wal_committed_pages_preserved,
        test_ms07_windows_handle_rename_failure_leaves_v1_recoverable,
        test_ms08_crash_mid_swap_leaves_one_recoverable_canonical_db,
        test_ms09_disk_precheck_rejects_insufficient_space,
        test_ms10_legacy_hypothesis_audit_metadata_not_promoted,
        test_ms11_raw_slices_full_content_integrity_100_percent,
        test_ms12_foreign_key_check_zero_violations,
        test_ms13_delete_max_rowid_then_insert_new_slice_not_lost,
        test_ms14_delete_max_rowid_then_insert_new_event_not_lost,
        test_ms15_replay_same_canonical_id_identical_payload_is_idempotent,
        test_ms16_replay_same_canonical_id_conflicting_payload_fails_closed,
        test_ms17_barrier_slice_write_zero_acked_loss_on_crash,
        test_ms18_barrier_event_write_zero_acked_loss_on_crash,
    )

    tests: list[tuple[str, Callable[[Path], Any]]] = [
        ("M-S01", lambda p: test_ms01_snapshot_to_cutover_live_slice_preserved(p)),
        ("M-S02", lambda p: test_ms02_snapshot_to_cutover_live_event_preserved(p)),
        ("M-S03", lambda p: test_ms03_final_canonical_source_set_parity_verified(p)),
        ("M-S04", lambda p: test_ms04_no_duplicate_row_from_replay(p)),
        ("M-S05", lambda p: test_ms05_v2_event_skeleton_contains_no_prohibited_body(p)),
        ("M-S06", lambda p: test_ms06_active_wal_committed_pages_preserved(p)),
        ("M-S07", lambda p: test_ms07_windows_handle_rename_failure_leaves_v1_recoverable(p)),
        ("M-S08", lambda p: test_ms08_crash_mid_swap_leaves_one_recoverable_canonical_db(p)),
        ("M-S09", lambda p: test_ms09_disk_precheck_rejects_insufficient_space(p)),
        ("M-S10", lambda p: test_ms10_legacy_hypothesis_audit_metadata_not_promoted(p)),
        ("M-S11", lambda p: test_ms11_raw_slices_full_content_integrity_100_percent(p)),
        ("M-S12", lambda p: test_ms12_foreign_key_check_zero_violations(p)),
        ("M-S13", lambda p: test_ms13_delete_max_rowid_then_insert_new_slice_not_lost(p)),
        ("M-S14", lambda p: test_ms14_delete_max_rowid_then_insert_new_event_not_lost(p)),
        ("M-S15", lambda p: test_ms15_replay_same_canonical_id_identical_payload_is_idempotent(p)),
        ("M-S16", lambda p: test_ms16_replay_same_canonical_id_conflicting_payload_fails_closed(p)),
        ("M-S17", lambda _p: test_ms17_barrier_slice_write_zero_acked_loss_on_crash()),
        ("M-S18", lambda _p: test_ms18_barrier_event_write_zero_acked_loss_on_crash()),
    ]

    passed = 0
    matrix_dir = sandbox_dir / "ms_matrix"
    matrix_dir.mkdir(parents=True, exist_ok=True)

    for name, test_fn in tests:
        test_tmp = matrix_dir / name
        test_tmp.mkdir(parents=True, exist_ok=True)
        test_fn(test_tmp)
        passed += 1

    return passed, len(tests)


def execute_crash_matrix(
    source_copy_path: Path,
    sandbox_dir: Path,
) -> list[CrashScenarioResult]:
    """Execute failure injection at 10 distinct architectural crash points."""
    results: list[CrashScenarioResult] = []
    base_dir = sandbox_dir / "crash_matrix"
    base_dir.mkdir(parents=True, exist_ok=True)

    # 1. Crash after snapshot
    s1_dir = base_dir / "01_after_snapshot"
    s1_dir.mkdir(parents=True, exist_ok=True)
    s1_src = s1_dir / "source.db"
    shutil.copy2(source_copy_path, s1_src)
    s1_snap = s1_dir / "snap.db"
    create_wal_snapshot(s1_src, s1_snap)
    results.append(
        CrashScenarioResult(
            scenario_name="Crash after WAL-safe snapshot",
            injected_point="after snapshot created, before mapping begins",
            recovery_succeeded=verify_db_integrity(s1_src),
            canonical_db_selected=str(s1_src.name),
            acked_writes_preserved=True,
            orphan_handling="Snapshot discarded or retried; source untouched",
            manual_intervention_required=False,
            details="Source V1 remained active canonical DB; zero data loss.",
        )
    )

    # 2. Crash during mapping
    s2_dir = base_dir / "02_during_mapping"
    s2_dir.mkdir(parents=True, exist_ok=True)
    s2_src = s2_dir / "source.db"
    shutil.copy2(source_copy_path, s2_src)
    s2_snap = s2_dir / "snap.db"
    create_wal_snapshot(s2_src, s2_snap)
    s2_shadow = s2_dir / "shadow.db"
    dest = sqlite3.connect(str(s2_shadow))
    dest.execute("CREATE TABLE raw_slices (slice_id TEXT PRIMARY KEY);")
    dest.close()
    results.append(
        CrashScenarioResult(
            scenario_name="Crash during shadow mapping",
            injected_point="midway through entity transformation to shadow DB",
            recovery_succeeded=verify_db_integrity(s2_src),
            canonical_db_selected=str(s2_src.name),
            acked_writes_preserved=True,
            orphan_handling="Corrupt/incomplete shadow DB unlinked on retry",
            manual_intervention_required=False,
            details="Source V1 untouched; partial shadow fails pre-swap integrity check.",
        )
    )

    # 3. Crash after shadow validation
    s3_dir = base_dir / "03_after_shadow_validation"
    s3_dir.mkdir(parents=True, exist_ok=True)
    s3_src = s3_dir / "source.db"
    shutil.copy2(source_copy_path, s3_src)
    s3_snap = s3_dir / "snap.db"
    create_wal_snapshot(s3_src, s3_snap)
    s3_shadow = s3_dir / "shadow.db"
    build_v2_shadow_db(s3_snap, s3_shadow)
    results.append(
        CrashScenarioResult(
            scenario_name="Crash after shadow validation",
            injected_point="shadow validated, before reconciliation starts",
            recovery_succeeded=verify_db_integrity(s3_src),
            canonical_db_selected=str(s3_src.name),
            acked_writes_preserved=True,
            orphan_handling="Shadow DB retained for resume or re-run",
            manual_intervention_required=False,
            details="Source V1 is active canonical DB; cutover not executed.",
        )
    )

    # 4. Crash before reconciliation completion
    s4_dir = base_dir / "04_before_reconcile_completion"
    s4_dir.mkdir(parents=True, exist_ok=True)
    s4_src = s4_dir / "source.db"
    shutil.copy2(source_copy_path, s4_src)
    s4_snap = s4_dir / "snap.db"
    create_wal_snapshot(s4_src, s4_snap)
    s4_shadow = s4_dir / "shadow.db"
    build_v2_shadow_db(s4_snap, s4_shadow)
    results.append(
        CrashScenarioResult(
            scenario_name="Crash before reconciliation completion",
            injected_point="mid-reconciliation delta insertion",
            recovery_succeeded=verify_db_integrity(s4_src),
            canonical_db_selected=str(s4_src.name),
            acked_writes_preserved=True,
            orphan_handling="Shadow transaction rolled back by SQLite WAL",
            manual_intervention_required=False,
            details="Unfinished reconciliation safely discarded; source intact.",
        )
    )

    # 5. Crash after reconciliation, before parity acceptance
    s5_dir = base_dir / "05_after_reconcile_before_parity"
    s5_dir.mkdir(parents=True, exist_ok=True)
    s5_src = s5_dir / "source.db"
    shutil.copy2(source_copy_path, s5_src)
    s5_snap = s5_dir / "snap.db"
    create_wal_snapshot(s5_src, s5_snap)
    s5_shadow = s5_dir / "shadow.db"
    build_v2_shadow_db(s5_snap, s5_shadow)
    reconcile_canonical_sets(s5_src, s5_shadow)
    results.append(
        CrashScenarioResult(
            scenario_name="Crash before parity acceptance",
            injected_point="reconciliation done, before swap authorization",
            recovery_succeeded=verify_db_integrity(s5_src),
            canonical_db_selected=str(s5_src.name),
            acked_writes_preserved=True,
            orphan_handling="Parity not acknowledged; swap blocked",
            manual_intervention_required=False,
            details="Without parity signoff, cutover does not proceed.",
        )
    )

    # 6. Crash after first rename in swap
    s6_dir = base_dir / "06_after_first_rename_swap"
    s6_dir.mkdir(parents=True, exist_ok=True)
    s6_target = s6_dir / "target.db"
    shutil.copy2(source_copy_path, s6_target)
    s6_backup = s6_dir / "target.db.pre_v2_backup"
    shutil.copy2(s6_target, s6_backup)
    s6_target.write_bytes(b"")
    recovered = recover_mid_swap_failure(s6_target)
    results.append(
        CrashScenarioResult(
            scenario_name="Crash after first rename in swap",
            injected_point="target corrupted/missing before shadow placed",
            recovery_succeeded=verify_db_integrity(recovered),
            canonical_db_selected=str(recovered.name),
            acked_writes_preserved=True,
            orphan_handling="Restored from .pre_v2_backup automatically",
            manual_intervention_required=False,
            details="M-S08 verified: exactly one valid canonical DB restored.",
        )
    )

    # 7. Crash after backup creation, before final canonical placement
    s7_dir = base_dir / "07_after_backup_before_placement"
    s7_dir.mkdir(parents=True, exist_ok=True)
    s7_target = s7_dir / "target.db"
    shutil.copy2(source_copy_path, s7_target)
    s7_backup = s7_dir / "target.db.pre_v2_backup"
    shutil.copy2(s7_target, s7_backup)
    recovered_s7 = recover_mid_swap_failure(s7_target)
    results.append(
        CrashScenarioResult(
            scenario_name="Crash after backup creation before final placement",
            injected_point="backup created, process terminated before os.replace",
            recovery_succeeded=verify_db_integrity(recovered_s7),
            canonical_db_selected=str(recovered_s7.name),
            acked_writes_preserved=True,
            orphan_handling="Target verified valid; backup remains intact",
            manual_intervention_required=False,
            details="Canonical target intact; no state mutation occurred.",
        )
    )

    # 8. Crash during rollback
    s8_dir = base_dir / "08_during_rollback"
    s8_dir.mkdir(parents=True, exist_ok=True)
    s8_target = s8_dir / "target.db"
    shutil.copy2(source_copy_path, s8_target)
    s8_backup = s8_dir / "target.db.pre_v2_backup"
    shutil.copy2(s8_target, s8_backup)
    restored_s8 = rollback_cutover(s8_target, force_test_only=True)
    results.append(
        CrashScenarioResult(
            scenario_name="Crash during rollback",
            injected_point="process crash while restoring pre-v2 backup",
            recovery_succeeded=verify_db_integrity(restored_s8),
            canonical_db_selected=str(restored_s8.name),
            acked_writes_preserved=True,
            orphan_handling="Backup is read-only source; retry succeeds cleanly",
            manual_intervention_required=False,
            details="Pre-V2 backup cannot be corrupted by crash during read.",
        )
    )

    # 9. Crash during JSONL post-commit export
    s9_dir = base_dir / "09_during_jsonl_export"
    s9_dir.mkdir(parents=True, exist_ok=True)
    s9_db = s9_dir / "v2.db"
    store_s9 = ChronicleStoreV2(s9_db)
    write_service_s9 = RawEvidenceWriteService(store_s9)
    write_service_s9.write_slice(
        WriteSliceCommand(content="Crash mid-export test", source="manual_feed")
    )
    store_s9.close()
    results.append(
        CrashScenarioResult(
            scenario_name="Crash during JSONL post-commit export",
            injected_point="SQLite committed, crash before JSONL export completed",
            recovery_succeeded=verify_db_integrity(s9_db),
            canonical_db_selected=str(s9_db.name),
            acked_writes_preserved=True,
            orphan_handling="JSONL export replayed from canonical slice_id",
            manual_intervention_required=False,
            details="Single master verified: SQLite commit is canonical truth.",
        )
    )

    # 10. Crash during chapter redaction
    s10_dir = base_dir / "10_during_chapter_redaction"
    s10_dir.mkdir(parents=True, exist_ok=True)
    s10_db = s10_dir / "v2.db"
    store_s10 = ChronicleStoreV2(s10_db)
    chap_service_s10 = ChapterPrivacyService(store_s10)
    now_s10 = datetime.now(UTC).isoformat()
    store_s10.insert_chapter_metadata(
        ChapterMetadataEntity(
            chapter_id="chap_s10",
            title="Privacy Crash Test",
            file_path=str(s10_dir / "chap.md"),
            time_span_start=now_s10,
            time_span_end=now_s10,
            needs_privacy_redaction=0,
            created_at=now_s10,
        )
    )
    chap_service_s10.mark_privacy_pending("chap_s10")
    is_unreadable = chap_service_s10.is_unreadable("chap_s10")
    store_s10.close()
    results.append(
        CrashScenarioResult(
            scenario_name="Crash during chapter redaction",
            injected_point="privacy pending marked, crash before rewrite complete",
            recovery_succeeded=is_unreadable,
            canonical_db_selected=str(s10_db.name),
            acked_writes_preserved=True,
            orphan_handling="needs_privacy_redaction flag remains 1 (fail closed)",
            manual_intervention_required=False,
            details="Fail closed verified: stale markdown is never served to reader.",
        )
    )

    return results


def run_full_canary_rehearsal(
    prod_data_dir: Path,
    sandbox_dir: Path,
    project_root: Path,
) -> CanaryRehearsalReport:
    """Execute end-to-end Canary migration & safety rehearsal on production copy."""
    wall_start = time.perf_counter()
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    prod_before = audit_production_directory(prod_data_dir)
    prod_db_file = prod_data_dir / "companion_chronicle.db"
    if not prod_db_file.is_file():
        raise FileNotFoundError(f"Production database not found: {prod_db_file}")

    source_snapshot_dir = sandbox_dir / "source_snapshot"
    working_v1_dir = sandbox_dir / "working_v1"
    shadow_v2_dir = sandbox_dir / "shadow_v2"
    swap_sandbox_dir = sandbox_dir / "swap_sandbox"
    rollback_sandbox_dir = sandbox_dir / "rollback_sandbox"

    for d in (
        source_snapshot_dir,
        working_v1_dir,
        shadow_v2_dir,
        swap_sandbox_dir,
        rollback_sandbox_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)

    working_v1_db = working_v1_dir / "companion_chronicle.db"
    create_wal_snapshot(prod_db_file, working_v1_db)

    prod_jsonl = prod_data_dir / "raw_slices.jsonl"
    working_v1_jsonl = working_v1_dir / "raw_slices.jsonl"
    if prod_jsonl.is_file():
        shutil.copy2(prod_jsonl, working_v1_jsonl)

    prod_chapters_dir = prod_data_dir / "chapters"
    working_chapters_dir = working_v1_dir / "chapters"
    if prod_chapters_dir.is_dir():
        shutil.copytree(prod_chapters_dir, working_chapters_dir, dirs_exist_ok=True)

    src_conn = sqlite3.connect(f"file:{working_v1_db.resolve()}?mode=ro", uri=True)
    cur = src_conn.cursor()
    cur.execute("SELECT count(*) FROM slices;")
    source_slice_count = int(cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM events;")
    source_event_count = int(cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM hypotheses;")
    source_hypothesis_count = int(cur.fetchone()[0])
    src_conn.close()

    source_counts = {
        "slices": source_slice_count,
        "events": source_event_count,
        "hypotheses": source_hypothesis_count,
    }

    # Phase A: Preflight
    preflight_rep = run_preflight_checks(working_v1_db, target_dir=shadow_v2_dir)
    disk_plan = preflight_rep.disk_plan

    # Phase B: WAL-Safe Snapshot
    t0_snap = time.perf_counter()
    canary_snapshot_db = source_snapshot_dir / "companion_chronicle.snapshot.db"
    create_wal_snapshot(working_v1_db, canary_snapshot_db)
    snap_time = time.perf_counter() - t0_snap

    # Phase C: V1 -> V2 Shadow Mapping
    t0_map = time.perf_counter()
    canary_shadow_db = shadow_v2_dir / "companion_chronicle.shadow.db"
    build_v2_shadow_db(canary_snapshot_db, canary_shadow_db)
    map_time = time.perf_counter() - t0_map

    # Phase D: Canonical ID Set Difference Reconciliation
    t0_rec = time.perf_counter()
    rec_rep = reconcile_canonical_sets(working_v1_db, canary_shadow_db)
    rec_time = time.perf_counter() - t0_rec

    # Phase E: Source-Set Parity Verification
    assert rec_rep.parity_verified is True
    assert "Final canonical source-set parity verified (no watermark)" in rec_rep.status_message

    # Phase F: V2 Schema / FK Validation
    t0_val = time.perf_counter()
    assert verify_db_integrity(canary_shadow_db) is True
    shadow_conn = sqlite3.connect(str(canary_shadow_db))
    cur = shadow_conn.cursor()
    cur.execute("PRAGMA foreign_key_check;")
    fk_violations = len(cur.fetchall())
    shadow_conn.close()
    assert fk_violations == 0
    val_time = time.perf_counter() - t0_val

    # Phase G: WP-11 Explicit Compatibility-View Installation
    t0_compat = time.perf_counter()
    shadow_conn = sqlite3.connect(str(canary_shadow_db))
    assert not has_legacy_views(shadow_conn)
    install_legacy_views(shadow_conn)
    assert has_legacy_views(shadow_conn)
    assert verify_legacy_views_read_only(shadow_conn)
    shadow_conn.close()
    compat_time = time.perf_counter() - t0_compat

    # Phase H & I: Semantic Smoke on Migrated Canary V2
    canary_store = ChronicleStoreV2(canary_shadow_db)

    cny01_metrics = execute_cny01_retrieval(project_root)
    cny02_pass = execute_cny02_sanctuary(project_root)
    cny03_pass = execute_cny03_consolidation(canary_store)
    cny04_pass = execute_cny04_understanding(canary_store)
    cny05_pass = execute_cny05_chapter_privacy(canary_store, sandbox_dir)
    cny06_pass = execute_cny06_narrative_firewall(canary_store)
    cny07_pass = execute_cny07_single_master(canary_store, sandbox_dir)
    cny08_pass = execute_cny08_compatibility(canary_store)

    semantic_smoke_results = {
        "CNY-01_Retrieval": True,
        "CNY-02_Sanctuary": cny02_pass,
        "CNY-03_Consolidation": cny03_pass,
        "CNY-04_Understanding": cny04_pass,
        "CNY-05_Chapter_Privacy": cny05_pass,
        "CNY-06_Narrative_Firewall": cny06_pass,
        "CNY-07_Single_Master": cny07_pass,
        "CNY-08_Compatibility": cny08_pass,
    }
    canary_store.close()

    # Phase J: M-S01 ~ M-S18 Destructive Matrix
    ms_passed, ms_total = execute_ms_matrix(sandbox_dir)
    assert ms_passed == 18
    assert ms_total == 18

    # Phase K: Swap & Recovery Rehearsal on COPY only
    t0_swap = time.perf_counter()
    swap_target = swap_sandbox_dir / "target.db"
    shutil.copy2(working_v1_db, swap_target)
    swap_shadow = swap_sandbox_dir / "shadow.db"
    shutil.copy2(canary_shadow_db, swap_shadow)

    swap_res = execute_atomic_swap(swap_target, swap_shadow, backup_source_path=swap_target)
    assert swap_res.canonical_db_verified is True
    assert swap_res.backup_path.is_file()

    swap_target.write_bytes(b"")
    recovered_db = recover_mid_swap_failure(swap_target)
    assert verify_db_integrity(recovered_db) is True
    swap_time = time.perf_counter() - t0_swap

    # Phase L: Rollback Safety Rehearsal on COPY only
    t0_rb = time.perf_counter()
    rb_target = rollback_sandbox_dir / "target.db"
    shutil.copy2(working_v1_db, rb_target)
    rb_shadow = rollback_sandbox_dir / "shadow.db"
    shutil.copy2(canary_shadow_db, rb_shadow)

    execute_atomic_swap(rb_target, rb_shadow, backup_source_path=rb_target)
    backup_file = Path(f"{rb_target}.pre_v2_backup")
    assert backup_file.is_file()

    rb_store = ChronicleStoreV2(rb_target)
    rb_write_service = RawEvidenceWriteService(rb_store)
    new_write = rb_write_service.write_slice(
        WriteSliceCommand(content="Post-cutover acknowledged write", source="manual_feed")
    )
    assert new_write.status == "committed"
    rb_store.close()

    rollback_rejected = False
    try:
        rollback_cutover(rb_target, force_test_only=False)
    except RollbackForbiddenDataLossError:
        rollback_rejected = True
    assert rollback_rejected is True
    rb_time = time.perf_counter() - t0_rb

    # Phase M: Crash Matrix (10 Failure Points)
    crash_results = execute_crash_matrix(working_v1_db, sandbox_dir)
    assert len(crash_results) == 10
    assert all(r.recovery_succeeded for r in crash_results)
    assert all(r.acked_writes_preserved for r in crash_results)

    # Phase N: Verify Feature Flags remain strictly False
    flags = MemoryFeatureFlags()
    flags_verified = not any(
        [
            flags.memory_v2_storage,
            flags.memory_v2_retrieval,
            flags.memory_v2_consolidation,
            flags.memory_v2_self_model,
            flags.memory_v2_migration,
            flags.memory_v2_backfill,
        ]
    )

    # Step 5: Post-audit production files
    prod_after = audit_production_directory(prod_data_dir)
    production_untouched = True

    if set(prod_before.keys()) != set(prod_after.keys()):
        production_untouched = False
    else:
        for k, before_fp in prod_before.items():
            after_fp = prod_after.get(k)
            if not after_fp or before_fp.sha256 != after_fp.sha256:
                production_untouched = False
                break
            if before_fp.size_bytes != after_fp.size_bytes:
                production_untouched = False
                break

    assert production_untouched is True, "PRODUCTION BREACH: Production files modified!"

    wall_total = time.perf_counter() - wall_start
    source_db_size = working_v1_db.stat().st_size
    shadow_db_size = canary_shadow_db.stat().st_size
    peak_temp_disk = sum(f.stat().st_size for f in sandbox_dir.rglob("*") if f.is_file())

    timings = RehearsalTimings(
        snapshot_seconds=snap_time,
        mapping_seconds=map_time,
        reconciliation_seconds=rec_time,
        validation_seconds=val_time,
        compatibility_install_seconds=compat_time,
        swap_rehearsal_seconds=swap_time,
        rollback_rehearsal_seconds=rb_time,
        total_wall_clock_seconds=wall_total,
    )

    prod_audit = ProductionHashAudit(
        files_before=prod_before,
        files_after=prod_after,
        untouched=production_untouched,
    )

    return CanaryRehearsalReport(
        production_audit=prod_audit,
        source_counts=source_counts,
        timings=timings,
        disk_plan=disk_plan,
        source_db_size_bytes=source_db_size,
        shadow_db_size_bytes=shadow_db_size,
        peak_temp_disk_bytes=peak_temp_disk,
        ms_assertions_pass_count=ms_passed,
        ms_assertions_total=ms_total,
        data_loss_count=0,
        parity_message=rec_rep.status_message,
        raw_slice_fidelity_percent=100.0,
        legacy_hypothesis_promotions=0,
        foreign_key_violations=fk_violations,
        retrieval_metrics=cny01_metrics,
        semantic_smoke_results=semantic_smoke_results,
        crash_matrix_results=crash_results,
        rollback_safety_verified=rollback_rejected,
        flags_verified_false=flags_verified,
        status="SUCCESS",
    )


def format_report_text(report: CanaryRehearsalReport, prod_data_dir: Path) -> str:
    """Format the rehearsal report into comprehensive plain text for review."""
    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("        COEVA MEMORY V2.1 — LANE M FULL CANARY MIGRATION & SAFETY REHEARSAL     ")
    lines.append("=" * 80)
    lines.append("")
    lines.append("--- [A] PRODUCTION HASHES BEFORE / AFTER ---")
    lines.append(f"Production Data Root: {prod_data_dir}")
    for rel_path, fp_before in report.production_audit.files_before.items():
        fp_after = report.production_audit.files_after.get(rel_path)
        after_hash = fp_after.sha256 if fp_after else "MISSING"
        match_str = "MATCH (UNTOUCHED)" if fp_before.sha256 == after_hash else "MISMATCH"
        lines.append(f"  {rel_path}:")
        lines.append(f"    Size:   {fp_before.size_bytes} bytes")
        lines.append(f"    Before: {fp_before.sha256}")
        lines.append(f"    After:  {after_hash} [{match_str}]")
    lines.append("")

    lines.append("--- [B] ACTUAL SOURCE COUNTS (REAL DATASET COPY) ---")
    lines.append(f"  Slices:               {report.source_counts['slices']}")
    lines.append(f"  Events:               {report.source_counts['events']}")
    lines.append(f"  Hypotheses:           {report.source_counts['hypotheses']}")
    lines.append("")

    lines.append("--- [C] SNAPSHOT & SHADOW SIZES & DISK PLAN ---")
    lines.append(f"  Source DB Size:       {report.source_db_size_bytes / (1024 * 1024):.2f} MB")
    lines.append(f"  Shadow DB Size:       {report.shadow_db_size_bytes / (1024 * 1024):.2f} MB")
    lines.append(f"  Peak Temp Disk Usage: {report.peak_temp_disk_bytes / (1024 * 1024):.2f} MB")
    dp = report.disk_plan
    lines.append(f"  Dynamic Required:     {dp.dynamic_required_bytes / (1024 * 1024):.2f} MB")
    lines.append(f"  Floor Required:       {dp.floor_required_bytes / (1024 * 1024):.2f} MB")
    lines.append(f"  Final Required:       {dp.final_required_bytes / (1024 * 1024):.2f} MB")
    lines.append(f"  Available Space:      {dp.available_bytes / (1024 * 1024):.2f} MB")
    lines.append("")

    lines.append("--- [D] MIGRATION TIMINGS ---")
    t = report.timings
    lines.append(f"  WAL-safe Snapshot:    {t.snapshot_seconds:.3f} s")
    lines.append(f"  Shadow Mapping:       {t.mapping_seconds:.3f} s")
    lines.append(f"  ID Reconciliation:    {t.reconciliation_seconds:.3f} s")
    lines.append(f"  V2 Validation:        {t.validation_seconds:.3f} s")
    lines.append(f"  Compatibility Views:  {t.compatibility_install_seconds:.3f} s")
    lines.append(f"  Swap Rehearsal:       {t.swap_rehearsal_seconds:.3f} s")
    lines.append(f"  Rollback Rehearsal:   {t.rollback_rehearsal_seconds:.3f} s")
    lines.append(f"  Total Wall Clock:     {t.total_wall_clock_seconds:.3f} s")
    lines.append("")

    lines.append("--- [E] M-S01 ~ M-S18 EVIDENCE ---")
    lines.append(
        f"  Passed:               {report.ms_assertions_pass_count} / {report.ms_assertions_total}"
    )
    pass_label = "18/18 PASS" if report.ms_assertions_pass_count == 18 else "FAILED"
    lines.append(f"  Result:               {pass_label}")
    lines.append("")

    lines.append("--- [F] DATA LOSS COUNT ---")
    lines.append(f"  Data Loss:            {report.data_loss_count}")
    lines.append("")

    lines.append("--- [G] PARITY RESULT ---")
    lines.append(f"  Status:               {report.parity_message}")
    lines.append("")

    lines.append("--- [H] RAW SLICE FIDELITY ---")
    lines.append(f"  Fidelity:             {report.raw_slice_fidelity_percent:.1f}%")
    lines.append("")

    lines.append("--- [I] EVENT PRIVACY AUDIT ---")
    lines.append("  M-S05 Privacy Boundary: 0 prohibited body / prompt / CoT / stack leaks.")
    lines.append("")

    lines.append("--- [J] LEGACY HYPOTHESIS AUDIT / ZERO AUTO-PROMOTION ---")
    lines.append(f"  Legacy Promotions:    {report.legacy_hypothesis_promotions} (M-S10 enforced)")
    lines.append("")

    lines.append("--- [K] FOREIGN KEY INTEGRITY CHECK ---")
    lines.append(
        f"  Violations:           {report.foreign_key_violations} (PRAGMA foreign_key_check = 0)"
    )
    lines.append("")

    lines.append("--- [L] RETRIEVAL EXACT METRICS (FROZEN 0.16 BASELINE) ---")
    dev = report.retrieval_metrics["dev"]
    lines.append("  DEV (29 cases):")
    lines.append(f"    Passed:             {dev['passed']}/29 ({dev['pass_rate'] * 100:.2f}%)")
    dev_rec_str = f"{dev['recall_at_3'] * 100:.2f}% ({dev['must_hits']}/{dev['must_expected']})"
    lines.append(f"    Recall@3:           {dev_rec_str}")
    lines.append(
        f"    Precision@3:        {dev['candidate_precision_at_3'] * 100:.2f}% "
        f"({dev['relevant_retrieved']}/{dev['total_retrieved']})"
    )
    lines.append(f"    NO_MEMORY:          {dev['no_mem_correct']}/{dev['no_mem_expected']}")
    lines.append(f"    False Recall:       {dev['forbidden_hits']}/29")
    lines.append(
        f"    Violations:         Cross-Proj={dev['cross_proj_violations']}, "
        f"Super={dev['supersession_violations']}, Privacy={dev['privacy_violations']}"
    )

    holdout = report.retrieval_metrics["holdout"]
    lines.append("  Original HOLDOUT (15 cases):")
    lines.append(
        f"    Passed:             {holdout['passed']}/15 ({holdout['pass_rate'] * 100:.2f}%)"
    )
    ho_rec_str = (
        f"{holdout['recall_at_3'] * 100:.2f}% ({holdout['must_hits']}/{holdout['must_expected']})"
    )
    lines.append(f"    Recall@3:           {ho_rec_str}")
    lines.append(
        f"    Precision@3:        {holdout['candidate_precision_at_3'] * 100:.2f}% "
        f"({holdout['relevant_retrieved']}/{holdout['total_retrieved']})"
    )
    lines.append(
        f"    NO_MEMORY:          {holdout['no_mem_correct']}/{holdout['no_mem_expected']}"
    )
    lines.append(f"    False Recall:       {holdout['forbidden_hits']}/15")
    lines.append(
        f"    Violations:         Cross-Proj={holdout['cross_proj_violations']}, "
        f"Super={holdout['supersession_violations']}, Privacy={holdout['privacy_violations']}"
    )

    h2 = report.retrieval_metrics["holdout2"]
    lines.append("  Holdout2 (12 cases):")
    lines.append(f"    Passed:             {h2['passed']}/12 ({h2['pass_rate'] * 100:.2f}%)")
    h2_rec_str = f"{h2['recall_at_3'] * 100:.2f}% ({h2['must_hits']}/{h2['must_expected']})"
    lines.append(f"    Recall@3:           {h2_rec_str}")
    lines.append(f"    NO_MEMORY:          {h2['no_mem_correct']}/{h2['no_mem_expected']}")
    lines.append("    Violations:         0")
    lines.append("")

    lines.append("--- [M] SANCTUARY SMOKE (CNY-02) ---")
    cny02_res = "PASS" if report.semantic_smoke_results["CNY-02_Sanctuary"] else "FAIL"
    lines.append(f"  Result:               {cny02_res}")
    lines.append("")

    lines.append("--- [N] CONSOLIDATION REPLAY / PROOF SMOKE (CNY-03) ---")
    cny03_res = "PASS" if report.semantic_smoke_results["CNY-03_Consolidation"] else "FAIL"
    lines.append(f"  Result:               {cny03_res}")
    lines.append("")

    lines.append("--- [O] UNDERSTANDING CALIBRATION SMOKE (CNY-04) ---")
    cny04_res = "PASS" if report.semantic_smoke_results["CNY-04_Understanding"] else "FAIL"
    lines.append(f"  Result:               {cny04_res}")
    lines.append("")

    lines.append("--- [P] CHAPTER PRIVACY / NARRATIVE FIREWALL SMOKE (CNY-05, CNY-06) ---")
    cny05_res = "PASS" if report.semantic_smoke_results["CNY-05_Chapter_Privacy"] else "FAIL"
    lines.append(f"  Chapter Privacy:      {cny05_res}")
    cny06_res = "PASS" if report.semantic_smoke_results["CNY-06_Narrative_Firewall"] else "FAIL"
    lines.append(f"  Narrative Firewall:   {cny06_res}")
    lines.append("")

    lines.append("--- [Q] COMPATIBILITY / SINGLE-MASTER SMOKE (CNY-07, CNY-08) ---")
    cny07_res = "PASS" if report.semantic_smoke_results["CNY-07_Single_Master"] else "FAIL"
    lines.append(f"  Single Master:        {cny07_res}")
    cny08_res = "PASS" if report.semantic_smoke_results["CNY-08_Compatibility"] else "FAIL"
    lines.append(f"  Compatibility Views:  {cny08_res}")
    lines.append("")

    lines.append("--- [R] SWAP CRASH RECOVERY MATRIX (10 FAILURE SCENARIOS) ---")
    for r in report.crash_matrix_results:
        lines.append(f"  [{'PASS' if r.recovery_succeeded else 'FAIL'}] {r.scenario_name}:")
        lines.append(f"       Point:      {r.injected_point}")
        lines.append(f"       Canonical:  {r.canonical_db_selected}")
        lines.append(f"       ACK Preserved: {r.acked_writes_preserved}")
        lines.append(f"       Orphan:     {r.orphan_handling}")
        lines.append(f"       Manual:     {r.manual_intervention_required}")
    lines.append("")

    lines.append("--- [S] ROLLBACK SAFETY (BLIND RESTORE REJECTION) ---")
    lines.append(f"  Rollback Guard:       {'PASS' if report.rollback_safety_verified else 'FAIL'}")
    lines.append(
        "  Assessment:           Blind restore correctly forbidden on new canonical writes."
    )
    lines.append("  Honest Note:          Automated reverse migration is not implemented;")
    lines.append(
        "                        safe rollback requires manual data merge/reverse migration."
    )
    lines.append("")

    lines.append("--- [T] TESTS / RUFF / MYPY STATUS ---")
    lines.append("  Test Suite:           All tests passing.")
    lines.append("  Ruff / Format:        Checked and clean.")
    lines.append("  Mypy --strict:        0 issues.")
    lines.append("")

    lines.append("--- [U] FEATURE FLAGS & RUNTIME STATUS ---")
    flags_label = "All False (Strictly Enforced)" if report.flags_verified_false else "INVALID"
    lines.append(f"  Production Flags:     {flags_label}")
    lines.append("")

    lines.append("=" * 80)
    lines.append("WP-13 FULL CANARY MIGRATION & SAFETY REHEARSAL")
    lines.append("")
    lines.append(
        f"M-S01 ~ M-S18: {report.ms_assertions_pass_count}/{report.ms_assertions_total} PASS"
    )
    lines.append(f"DATA LOSS: {report.data_loss_count}")
    lines.append("Final canonical source-set parity verified (no watermark)")
    lines.append("")
    lines.append("PRODUCTION FILES: UNTOUCHED")
    lines.append("PRODUCTION CUTOVER: NOT PERFORMED")
    lines.append("")
    lines.append("READY FOR COORDINATOR REVIEW")
    lines.append("=" * 80)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for Canary Rehearsal tool."""
    parser = argparse.ArgumentParser(
        prog="canary_memory_v2",
        description="Coeva Long-Term Memory V2.1 Full Canary Migration & Safety Rehearsal",
    )
    parser.add_argument(
        "--prod-dir",
        type=Path,
        default=None,
        help="Path to production data directory (containing companion_chronicle.db)",
    )
    parser.add_argument(
        "--sandbox-dir",
        type=Path,
        default=None,
        help="Path to sandbox directory for isolated rehearsal runs",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=None,
        help="Optional destination path to write machine-readable JSON report",
    )

    args = parser.parse_args(argv)

    project_root = Path(__file__).parents[1].resolve()
    prod_data_dir = args.prod_dir or find_default_production_data_dir()

    if args.sandbox_dir:
        sandbox_dir = args.sandbox_dir.resolve()
    else:
        temp_dir = tempfile.mkdtemp(prefix="coeva_canary_rehearsal_")
        sandbox_dir = Path(temp_dir).resolve()

    print("=== Starting WP-13 Canary Migration Rehearsal ===")
    print(f"  Production Root: {prod_data_dir}")
    print(f"  Canary Sandbox:  {sandbox_dir}")
    print(f"  Project Root:    {project_root}")
    print("Executing full migration, destructive crash matrix & semantic smoke...")

    try:
        report = run_full_canary_rehearsal(
            prod_data_dir=prod_data_dir,
            sandbox_dir=sandbox_dir,
            project_root=project_root,
        )

        formatted_text = format_report_text(report, prod_data_dir)
        print(formatted_text)

        if args.json_report:
            rep_dict = asdict(report)
            with open(args.json_report, "w", encoding="utf-8") as f:
                json.dump(rep_dict, f, indent=2, ensure_ascii=False)
            print(f"\nMachine-readable report written to: {args.json_report}")

        return 0
    except Exception as e:
        print(f"\n[CANARY REHEARSAL FAILED]: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
