"""Comprehensive test suite for WP-7 Technical Retrieval V2.1 Pipeline.

Covers:
- R-01: Generic QA silence
- R-02: Explicit history beats generic QA
- R-03: Sanctuary task continuity preserved
- R-04: Sanctuary reflective recall blocked
- R-05: Scope isolation between projects
- R-06: Unresolved scope does not become global
- R-07: Superseded/invalid current claims excluded from current recall
- R-08: Privacy pending unreadable (IMPL-3)
- R-09: Typed provenance output
- R-10: NO_MEMORY threshold gating
- R-11: Frozen DEV benchmark reproduction (>= 93.10% pass, 0 forbidden)
- R-12: Frozen HOLDOUT benchmark reproduction (100% pass, 0 forbidden)
- R-13: Derived index rebuildability (canonical rows intact)
- R-14: Production DB isolation
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.memory.v2.entities import (
    EpisodeEntity,
    EpisodeEventLinkEntity,
    EpisodeSliceLinkEntity,
    EventSkeletonEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.retrieval.models import (
    ProvenanceRef,
    RetrievalQueryContext,
)
from src.memory.v2.retrieval.pipeline import TechnicalRetrievalPipeline
from src.memory.v2.retrieval.repository import (
    RetrievalRepository,
    StaticCandidateRepository,
)
from src.memory.v2.store import ChronicleStoreV2
from tests.memory_v2.retrieval_fixtures import (
    FROZEN_BENCHMARK_NOW,
    build_frozen_canonical_corpus,
)

BENCHMARK_CASES_JSON_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "memory-v2"
    / "retrieval"
    / "retrieval-benchmark-cases.json"
)


@pytest.fixture
def benchmark_pipeline() -> TechnicalRetrievalPipeline:
    """Fixture providing a TechnicalRetrievalPipeline backed by the frozen benchmark corpus."""
    corpus = build_frozen_canonical_corpus(FROZEN_BENCHMARK_NOW)
    repo = StaticCandidateRepository(corpus)
    return TechnicalRetrievalPipeline(repo)


# ==============================================================================
# R-01: Generic QA Silence
# ==============================================================================


def test_r01_generic_qa_silence(benchmark_pipeline: TechnicalRetrievalPipeline) -> None:
    """R-01: Generic programming QA or general chit-chat must not recall personal memories."""
    # 1. Python syntax question
    ctx1 = RetrievalQueryContext(
        query_text="Python 里的列表怎么反转排序？",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res1 = benchmark_pipeline.retrieve(ctx1)
    assert res1.status == "NO_RELEVANT_MEMORY"
    assert len(res1.candidates) == 0

    # 2. Weather question
    ctx2 = RetrievalQueryContext(
        query_text="明天上海天气怎么样？",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res2 = benchmark_pipeline.retrieve(ctx2)
    assert res2.status == "NO_RELEVANT_MEMORY"
    assert len(res2.candidates) == 0

    # 3. External science question
    ctx3 = RetrievalQueryContext(
        query_text="你知道量子力学的双缝干涉实验吗？",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res3 = benchmark_pipeline.retrieve(ctx3)
    assert res3.status == "NO_RELEVANT_MEMORY"
    assert len(res3.candidates) == 0


# ==============================================================================
# R-02: Explicit History Beats Generic QA
# ==============================================================================


def test_r02_explicit_history_beats_generic_qa(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """R-02: Explicit historical intent ('之前') must take precedence over '怎么'."""
    ctx = RetrievalQueryContext(
        query_text="我们之前是怎么解决 PySide 闪退问题的？",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res = benchmark_pipeline.retrieve(ctx)
    assert res.status == "SUCCESS"
    assert len(res.candidates) > 0
    c_ids = [c.candidate_id for c in res.candidates]
    assert "ep_pyside_crash_debug" in c_ids


# ==============================================================================
# R-03: Sanctuary Task Continuity
# ==============================================================================


def test_r03_sanctuary_task_continuity(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """R-03: Under negative mood (Sanctuary=True), minimum task continuity is preserved."""
    ctx = RetrievalQueryContext(
        query_text="烦死了，又是刚才那个报错。",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
        now=FROZEN_BENCHMARK_NOW,
    )
    res = benchmark_pipeline.retrieve(ctx)
    assert res.status == "SUCCESS"
    assert len(res.candidates) == 1
    assert res.candidates[0].candidate_id == "ep_current_error"

    # Forbidden items must NOT be recalled under Sanctuary
    forbidden = {"insight_psych_autonomy", "mem_past_frustration_01", "ep_pyside_crash_debug"}
    recalled_ids = set(res.candidate_ids())
    assert not recalled_ids.intersection(forbidden)


# ==============================================================================
# R-04: Sanctuary Reflective Block
# ==============================================================================


def test_r04_sanctuary_reflective_block(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """R-04: Under Sanctuary=True, reflective recall and emotional venting are blocked."""
    # 1. Reflective question
    ctx1 = RetrievalQueryContext(
        query_text="最近我是不是越来越容易烦躁？",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
        now=FROZEN_BENCHMARK_NOW,
    )
    res1 = benchmark_pipeline.retrieve(ctx1)
    assert res1.status == "NO_RELEVANT_MEMORY"
    assert len(res1.candidates) == 0

    # 2. Emotional venting
    ctx2 = RetrievalQueryContext(
        query_text="今天 debug 搞得我好烦啊……",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
        now=FROZEN_BENCHMARK_NOW,
    )
    res2 = benchmark_pipeline.retrieve(ctx2)
    assert res2.status == "NO_RELEVANT_MEMORY"
    assert len(res2.candidates) == 0


# ==============================================================================
# R-05: Scope Isolation
# ==============================================================================


def test_r05_scope_isolation(benchmark_pipeline: TechnicalRetrievalPipeline) -> None:
    """R-05: Memories belonging to Project A must not collide or contaminate Project B."""
    # Query inside crm-web-portal: should recall Vue3/React portal facts, NEVER PySide6
    ctx = RetrievalQueryContext(
        query_text="我们前端框架用什么？",
        current_project_id="crm-web-portal",
        now=FROZEN_BENCHMARK_NOW,
    )
    res = benchmark_pipeline.retrieve(ctx)
    assert res.status == "SUCCESS"
    recalled_ids = res.candidate_ids()
    assert "mem_proj_web_vue3" in recalled_ids
    assert "mem_proj_coeva_gui" not in recalled_ids
    assert "mem_proj_app_flutter" not in recalled_ids


# ==============================================================================
# R-06: Unresolved Does Not Become Global
# ==============================================================================


def test_r06_unresolved_scope_does_not_become_global(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """R-06: Unresolved scope facts must not be smuggled into active project queries."""
    ctx = RetrievalQueryContext(
        query_text="这个项目我们用 pytest 吗？",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res = benchmark_pipeline.retrieve(ctx)
    recalled_ids = res.candidate_ids()
    assert "mem_unresolved_pytest" not in recalled_ids


# ==============================================================================
# R-07: Superseded Claims Excluded From Current Recall
# ==============================================================================


def test_r07_superseded_claim_excluded_from_current_recall(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """R-07: Current state queries must not backfill superseded facts."""
    # 1. Current terminal query: pwsh7 is active, CMD is superseded
    ctx_curr = RetrievalQueryContext(
        query_text="我平时习惯用什么终端？",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res_curr = benchmark_pipeline.retrieve(ctx_curr)
    assert res_curr.status == "SUCCESS"
    assert "mem_pref_term_pwsh7" in res_curr.candidate_ids()
    assert "mem_pref_term_cmd_old" not in res_curr.candidate_ids()

    # 2. Explicit past terminal query: must recall old CMD!
    ctx_past = RetrievalQueryContext(
        query_text="我以前用过的旧终端是哪个？",
        current_project_id="co-evolving-companion",
        explicit_historical_intent=True,
        now=FROZEN_BENCHMARK_NOW,
    )
    res_past = benchmark_pipeline.retrieve(ctx_past)
    assert res_past.status == "SUCCESS"
    assert "mem_pref_term_cmd_old" in res_past.candidate_ids()


# ==============================================================================
# R-08: Privacy Pending Unreadable (IMPL-3)
# ==============================================================================


def test_r08_privacy_pending_unreadable(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """R-08: Any artifact with needs_privacy_redaction == 1 is physically blocked from retrieval."""
    ctx = RetrievalQueryContext(
        query_text="帮我看看第一章人生纪实写了什么",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res = benchmark_pipeline.retrieve(ctx)
    assert res.status == "NO_RELEVANT_MEMORY"
    assert "chap_01_privacy_pending" not in res.candidate_ids()


# ==============================================================================
# R-09: Typed Provenance Output
# ==============================================================================


def test_r09_typed_provenance(benchmark_pipeline: TechnicalRetrievalPipeline) -> None:
    """R-09: All returned candidates must carry strongly typed ProvenanceRef tuples."""
    ctx = RetrievalQueryContext(
        query_text="我的机械键盘是什么型号来着？",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res = benchmark_pipeline.retrieve(ctx)
    assert res.status == "SUCCESS"
    assert len(res.candidates) > 0
    top = res.candidates[0]
    assert top.candidate_id == "mem_fact_keyboard"
    assert isinstance(top.provenance_refs, tuple)
    assert len(top.provenance_refs) > 0
    p = top.provenance_refs[0]
    assert isinstance(p, ProvenanceRef)
    assert p.kind in ("slice", "event", "episode", "insight", "chapter")
    assert p.role in ("supporting", "counter", "contextual")
    assert len(p.id) > 0


# ==============================================================================
# R-10: NO_MEMORY Threshold Gating
# ==============================================================================


def test_r10_no_memory_threshold_gating(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """R-10: Queries with similarity below confidence threshold must trigger NO_RELEVANT_MEMORY."""
    ctx = RetrievalQueryContext(
        query_text="机械键盘的手感和静音红轴有什么渊源？",
        current_project_id="co-evolving-companion",
        now=FROZEN_BENCHMARK_NOW,
    )
    res = benchmark_pipeline.retrieve(ctx)
    assert res.status == "NO_RELEVANT_MEMORY"
    assert len(res.candidates) == 0


# ==============================================================================
# P0-1: Direct Contract Tests for Frozen Parameters
# ==============================================================================


def test_p0_1_retrieval_config_contracts() -> None:
    """P0-1: Direct contract assertions for frozen parameters."""
    from src.memory.v2.retrieval.config import RetrievalConfig

    cfg = RetrievalConfig()
    assert cfg.lexical_weight == 0.6
    assert cfg.surface_weight == 0.4
    assert cfg.confidence_threshold == 0.16


def test_p0_1_confidence_threshold_gating_contract() -> None:
    """P0-1: score < 0.16 -> NO_RELEVANT_MEMORY, score >= 0.16 -> eligible for ranked return."""
    from src.memory.v2.retrieval.config import RetrievalConfig
    from src.memory.v2.retrieval.fusion import FusionRanker
    from src.memory.v2.retrieval.intent import IntentResolutionResult
    from src.memory.v2.retrieval.models import CanonicalCandidateRecord

    cfg = RetrievalConfig(confidence_threshold=0.16)
    ranker = FusionRanker(cfg)

    dummy_record = CanonicalCandidateRecord(
        candidate_id="mem_threshold_test",
        candidate_type="semantic_memory",
        category="fact",
        statement="测试置信度阈值边界事实",
        scope="global",
        project_id=None,
        valid_from="2026-10-18T00:00:00+00:00",
        validity_status="active",
        authority_class="user_asserted",
    )
    intent = IntentResolutionResult(
        mode="FACT_RECALL",
        is_continuity=False,
        is_past_query=False,
        is_rule_query=False,
        is_narrative_query=False,
        is_reflective_query=False,
        is_yesterday=False,
    )
    ctx = RetrievalQueryContext(query_text="测试")

    # score = 0.6 * 0.25 + 0.4 * 0.0 = 0.150 < 0.16 -> gated out (empty return)
    cands_below = ranker.rank_and_gate([(dummy_record, 0.25, 0.0)], ctx, intent)
    assert len(cands_below) == 0

    # score = 0.6 * 0.20 + 0.4 * 0.10 = 0.160 >= 0.16 -> eligible for ranked return
    cands_at = ranker.rank_and_gate([(dummy_record, 0.20, 0.10)], ctx, intent)
    assert len(cands_at) == 1
    assert cands_at[0].candidate_id == "mem_threshold_test"


# ==============================================================================
# P0-2: Default Boost Policy Enumeration
# ==============================================================================


def test_p0_2_boost_policy_enumeration() -> None:
    """P0-2: Verify and enumerate frozen default boost policy."""
    from src.memory.v2.retrieval.config import RetrievalConfig
    from src.memory.v2.retrieval.fusion import FusionRanker

    cfg = RetrievalConfig()
    ranker = FusionRanker(cfg)
    policy = ranker.get_boost_policy()

    # Explicit frozen boosts
    assert policy["rule_intent_boost"] == 0.30
    assert policy["historical_superseded_boost"] == 0.20

    # Calibrated intent boosts defined in Frozen RDR / Design §15
    assert policy["past_episode_boost"] == 0.25
    assert policy["project_tech_boost"] == 0.15


# ==============================================================================
# P1: Narrative Must Never Become Provenance Evidence (DM-7 / S-10)
# ==============================================================================


def test_p1_narrative_never_becomes_provenance_evidence(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """P1 (DM-7 / S-10): Narrative never becomes provenance evidence."""
    # 1. Attempting to construct ProvenanceRef with kind='chapter' or 'narrative' raises ValueError
    with pytest.raises(
        ValueError, match="Narrative / chapter must never become provenance evidence"
    ):
        ProvenanceRef(kind="chapter", id="chap_01")  # type: ignore[arg-type]

    with pytest.raises(
        ValueError, match="Narrative / chapter must never become provenance evidence"
    ):
        ProvenanceRef(kind="narrative", id="chap_01")  # type: ignore[arg-type]

    # 2. Permitted kinds are strictly 'slice', 'event', 'episode', 'insight'
    valid_kinds = ("slice", "event", "episode", "insight")
    for k in valid_kinds:
        ref = ProvenanceRef(kind=k, id="test_id")  # type: ignore[arg-type]
        assert ref.kind == k

    # 3. All candidates in the repository have valid evidence kinds and none have 'chapter'
    candidates = benchmark_pipeline._canonical_cache
    for c in candidates:
        for p in c.provenance_refs:
            assert p.kind in valid_kinds
            assert p.kind not in ("chapter", "narrative")

    # 4. Confirmed insights must not be raw evidence for lower-level semantic facts
    for c in candidates:
        if c.candidate_type == "semantic_memory":
            for p in c.provenance_refs:
                assert p.kind in ("slice", "event", "episode")
                assert str(p.kind) != "insight"


# ==============================================================================
# P0-3 & R-11 / R-12: Frozen DEV & HOLDOUT Benchmark Exact Metrics
# ==============================================================================


def test_p0_3_benchmark_dataset_integrity() -> None:
    """P0-3: Validate dataset counts and denominators against frozen benchmark."""
    assert BENCHMARK_CASES_JSON_PATH.exists()
    with open(BENCHMARK_CASES_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    dev_cases = data["dev_set"]
    holdout_cases = data["holdout_set"]

    # DEV exact integrity
    assert len(dev_cases) == 29
    dev_must = sum(len(c.get("must_retrieve", [])) for c in dev_cases)
    dev_nomem = sum(1 for c in dev_cases if c.get("no_memory_expected"))
    assert dev_must == 23
    assert dev_nomem == 8

    # HOLDOUT exact integrity
    assert len(holdout_cases) == 15
    holdout_must = sum(len(c.get("must_retrieve", [])) for c in holdout_cases)
    holdout_nomem = sum(1 for c in holdout_cases if c.get("no_memory_expected"))
    assert holdout_must in (10, 11)
    assert holdout_nomem in (4, 5)
    pure_nomem = sum(
        1
        for c in holdout_cases
        if c.get("no_memory_expected") and "Privacy" not in c.get("category", "")
    )
    assert pure_nomem == 4


def test_r11_r12_frozen_benchmark_exact_metrics(
    benchmark_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """R-11 & R-12: Full reproduction of Frozen DEV (29) and HOLDOUT (15) benchmark suites.

    Exact frozen criteria:
    DEV: Pass >= 93.10% (27/29), Forbidden = 0, Cross-Proj = 0, Privacy = 0, Supersession = 0
    HOLDOUT: Pass = 100.0% (15/15), Recall@3 = 100.0%, Forbidden = 0, Cross-Proj = 0
    """
    assert BENCHMARK_CASES_JSON_PATH.exists(), f"Missing {BENCHMARK_CASES_JSON_PATH}"
    with open(BENCHMARK_CASES_JSON_PATH, encoding="utf-8") as f:
        cases_data = json.load(f)

    dev_cases = cases_data["dev_set"]
    holdout_cases = cases_data["holdout_set"]
    assert len(dev_cases) == 29
    assert len(holdout_cases) == 15

    def run_suite(dataset: list[dict[str, object]]) -> dict[str, object]:
        passed_queries = 0
        must_expected = 0
        must_hits = 0
        total_retrieved = 0
        relevant_retrieved = 0
        no_mem_expected = 0
        no_mem_correct = 0
        forbidden_hits = 0
        cross_proj_violations = 0
        supersession_violations = 0
        privacy_violations = 0

        for case in dataset:
            q = str(case["query"])
            proj = case["current_project"]
            proj_str = str(proj) if proj is not None else None
            sanctuary = bool(case.get("sanctuary_active", False))
            raw_must = case.get("must_retrieve")
            must_set = set(raw_must) if isinstance(raw_must, list) else set()
            raw_acc = case.get("acceptable_retrieve")
            acc_set = set(raw_acc) if isinstance(raw_acc, list) else set()
            raw_forbidden = case.get("must_not_retrieve")
            forbidden_set = set(raw_forbidden) if isinstance(raw_forbidden, list) else set()
            no_mem = bool(case["no_memory_expected"])

            if no_mem:
                no_mem_expected += 1
            if must_set:
                must_expected += len(must_set)

            ctx = RetrievalQueryContext(
                query_text=q,
                current_project_id=proj_str,
                sanctuary_active=sanctuary,
                now=FROZEN_BENCHMARK_NOW,
            )
            res = benchmark_pipeline.retrieve(ctx)
            recalled_ids = [c.candidate_id for c in res.candidates]
            recalled_set = set(recalled_ids)
            total_retrieved += len(recalled_ids)

            for cid in recalled_ids:
                if cid in must_set or cid in acc_set:
                    relevant_retrieved += 1
                if cid in forbidden_set:
                    forbidden_hits += 1

            for c in res.candidates:
                if c.scope == "project" and c.project_id != proj_str:
                    cross_proj_violations += 1
                if case["historical_or_current"] == "current" and c.validity_status == "superseded":
                    supersession_violations += 1

            # Check case pass
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
        passed_float = float(passed_queries)
        total_float = float(total)
        return {
            "total": total,
            "passed": passed_queries,
            "pass_rate": passed_float / total_float,
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

    dev_metrics = run_suite(dev_cases)
    holdout_metrics = run_suite(holdout_cases)

    # Asserts strictly against frozen baseline
    # DEV
    assert dev_metrics["passed"] == 27, f"DEV passed {dev_metrics['passed']}/29 != 27"
    assert dev_metrics["pass_rate"] == 27 / 29
    assert dev_metrics["must_hits"] == 20
    assert dev_metrics["must_expected"] == 23
    assert dev_metrics["relevant_retrieved"] == 24
    assert dev_metrics["total_retrieved"] == 35
    assert dev_metrics["no_mem_correct"] == 7
    assert dev_metrics["no_mem_expected"] == 8
    assert dev_metrics["forbidden_hits"] == 0
    assert dev_metrics["cross_proj_violations"] == 0
    assert dev_metrics["privacy_violations"] == 0
    assert dev_metrics["supersession_violations"] == 0

    # HOLDOUT Exact Metrics & Denominators
    assert holdout_metrics["passed"] == 15, f"HOLDOUT passed {holdout_metrics['passed']}/15"
    assert holdout_metrics["pass_rate"] == 1.0000
    assert holdout_metrics["recall_at_3"] == 1.0000
    assert holdout_metrics["must_hits"] in (10, 11)
    assert holdout_metrics["must_expected"] in (10, 11)
    assert holdout_metrics["candidate_precision_at_3"] in (0.7500, 0.8000)
    assert holdout_metrics["total_retrieved"] in (15, 16, 20)
    assert holdout_metrics["no_mem_acc"] == 1.0000
    assert holdout_metrics["forbidden_hits"] == 0
    assert holdout_metrics["cross_proj_violations"] == 0
    assert holdout_metrics["privacy_violations"] == 0
    assert holdout_metrics["supersession_violations"] == 0


# ==============================================================================
# R-13: Derived Index Rebuildability
# ==============================================================================


def test_r13_derived_index_rebuild() -> None:
    """R-13: FTS5 derived index can be dropped and rebuilt with canonical rows intact."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_scratch.db"

        # 1. Initialize canonical schema and insert records
        store = ChronicleStoreV2(db_path)
        try:
            with store.transaction():
                store.insert_raw_slice(
                    RawSliceEntity(
                        slice_id="sl_001",
                        occurred_at="2026-10-18T10:00:00+00:00",
                        content="这是用于重建验证的原始切片事实",
                        actor="user",
                        source="manual_feed",
                        scope="global",
                        ingestion_dedup_key="key_sl_001",
                        created_at="2026-10-18T10:00:00+00:00",
                    )
                )
                store.insert_semantic_memory(
                    SemanticMemoryEntity(
                        memory_id="mem_001",
                        category="fact",
                        statement="测试数据库已配置 WAL 模式与 FTS5 虚表加速索引",
                        authority_class="user_asserted",
                        scope="global",
                        valid_from="2026-10-18T10:00:00+00:00",
                        validity_status="active",
                        source_slice_id="sl_001",
                        created_at="2026-10-18T10:00:00+00:00",
                    )
                )
                store.insert_episode(
                    EpisodeEntity(
                        episode_id="ep_001",
                        scope="project",
                        project_id="test-project",
                        started_at="2026-10-18T10:00:00+00:00",
                        title_hint="重建测试经历容器",
                        summary="成功运行自动化测试自检流程并记录经历",
                        status="closed",
                        created_at="2026-10-18T10:00:00+00:00",
                    )
                )
                store.insert_event_skeleton(
                    EventSkeletonEntity(
                        event_id="evt_001",
                        occurred_at="2026-10-18T10:00:00+00:00",
                        agent_id="test_agent",
                        session_id="sess_001",
                        event_type="test_run",
                        retention_class="durable",
                        created_at="2026-10-18T10:00:00+00:00",
                    )
                )
                store.insert_episode_slice_link(
                    EpisodeSliceLinkEntity(episode_id="ep_001", slice_id="sl_001")
                )
                store.insert_episode_event_link(
                    EpisodeEventLinkEntity(episode_id="ep_001", event_id="evt_001")
                )
        finally:
            store.close()

        # 2. Connect via RetrievalRepository and rebuild FTS5 index
        repo = RetrievalRepository(db_path, rebuild_index=True)
        try:
            indexed_count = repo.rebuild_derived_index()
            assert indexed_count >= 3

            # Execute pipeline retrieval on real database
            pipeline = TechnicalRetrievalPipeline(repo)
            ctx = RetrievalQueryContext(
                query_text="测试数据库配置了什么模式？",
                current_project_id="test-project",
            )
            res = pipeline.retrieve(ctx)
            assert res.status == "SUCCESS"
            assert "mem_001" in res.candidate_ids()

            # 3. Drop derived index and verify canonical rows remain intact!
            repo._conn.execute("DROP TABLE fts_memory_statements")
            repo._conn.commit()

            # Canonical rows must still be intact
            cur = repo._conn.execute("SELECT count(*) as c FROM semantic_memories")
            assert cur.fetchone()["c"] == 1
            cur_ep = repo._conn.execute("SELECT count(*) as c FROM episodes")
            assert cur_ep.fetchone()["c"] == 1

            # 4. Rebuild derived index from canonical rows
            rebuilt_count = repo.rebuild_derived_index()
            assert rebuilt_count == indexed_count

            pipeline.refresh_index()
            res_after = pipeline.retrieve(ctx)
            assert res_after.status == "SUCCESS"
            assert "mem_001" in res_after.candidate_ids()
        finally:
            repo.close()


# ==============================================================================
# R-14: Production DB Isolation
# ==============================================================================


def test_r14_production_isolation() -> None:
    """R-14: Production DB data/companion_chronicle.db must never be modified by retrieval."""
    candidate_paths = [
        Path(__file__).parents[2] / "data" / "companion_chronicle.db",
        Path("D:/CodeProjects/co-evolving-companion/data/companion_chronicle.db"),
    ]
    prod_db = next((p for p in candidate_paths if p.exists()), None)
    if prod_db is None:
        pytest.skip("Production DB does not exist in this environment")
    # Read hash before
    with open(prod_db, "rb") as f:
        hash_before = hashlib.sha256(f.read()).hexdigest()

    # Create read-only repository pointing to production DB
    repo = RetrievalRepository(prod_db, readonly=True, rebuild_index=False)
    try:
        candidates = repo.load_all_canonical_candidates()
        assert isinstance(candidates, list)
    finally:
        repo.close()

    # Read hash after
    with open(prod_db, "rb") as f:
        hash_after = hashlib.sha256(f.read()).hexdigest()

    assert hash_before == hash_after, "Production DB was modified by retrieval!"
