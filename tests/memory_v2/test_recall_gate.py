"""Comprehensive test suite for WP-8 Recall Gate & Sanctuary Mode Integration.

Authoritative mapping to:
- Prompt §1: Scope and boundary (Retrieved != Injected != Spoken)
- Prompt §2: Authoritative Sanctuary semantics
- Prompt §3: Defense in depth
- Prompt §4: Recall decision model (RecallDecision, RecallDisposition, InjectionContext)
- Prompt §5: Minimal injection principle
- Prompt §6: 80 / 15 / 5 policy boundary (Silence first-class, observability categories)
- Prompt §7: Explicit user requests (Outside vs Inside Sanctuary)
- Prompt §8: Privacy & deletion (IMPL-3, TOCTOU safety)
- Prompt §9: Anti-echo safety (origin metadata distinction)
- Prompt §10: No retrieval retuning
- Prompt §12: Exactly 18 required tests
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core.flags import MemoryFeatureFlags
from src.memory.v2.entities import (
    ChapterMetadataEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.recall_gate import (
    RecallContext,
    RecallDisposition,
    RecallGate,
    RecallReason,
)
from src.memory.v2.retrieval.models import (
    ProvenanceRef,
    RetrievalQueryContext,
    RetrievedCandidate,
)
from src.memory.v2.retrieval.pipeline import TechnicalRetrievalPipeline
from src.memory.v2.retrieval.repository import StaticCandidateRepository
from src.memory.v2.store import ChronicleStoreV2
from tests.memory_v2.retrieval_fixtures import (
    FROZEN_BENCHMARK_NOW,
    build_frozen_canonical_corpus,
)

EXPECTED_PROD_DB_HASH = "8b29f3c8714c1ae0ffc5db95a10e73cd299cf1ae74e01f5b8f402880a739df69"


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
        ProvenanceRef(kind="slice", id="slice_test_1", role="supporting"),
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
# 1. Retrieved but suppressed is valid (Retrieved != Injected)
# ==============================================================================


def test_01_retrieved_but_suppressed_is_valid() -> None:
    """Requirement 1: Retrieved candidates suppressed by policy is a valid outcome."""
    gate = RecallGate()
    cand = _make_candidate(
        candidate_id="mem_pref_indent",
        statement="用户偏好 4 空格缩进。",
        final_score=0.8,
    )
    # Generic question with no intent to recall personal indent preferences
    ctx = RecallContext(
        query_text="今天天气怎么样？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )

    decision = gate.evaluate([cand], ctx)

    assert decision.disposition == RecallDisposition.SUPPRESS
    assert decision.is_silent is True
    assert decision.injection_context.is_empty is True
    assert len(decision.allowed_candidates) == 0
    assert len(decision.suppressed_candidates) == 1
    assert decision.reason == RecallReason.GENERIC_QA_SUPPRESSED
    assert decision.observability_category == "silent"


# ==============================================================================
# 2. Generic QA remains silent
# ==============================================================================


def test_02_generic_qa_remains_silent() -> None:
    """Requirement 2: Generic QA queries must suppress memory and remain silent."""
    gate = RecallGate()
    queries = [
        "Python 里的列表怎么反转排序？",
        "明天上海天气怎么样？",
        "你知道量子力学的双缝干涉实验吗？",
        "通常用什么技术做高并发？",
    ]
    cand = _make_candidate(candidate_id="mem_fact_gpu", statement="用户显卡为 RTX 4090。")

    for q in queries:
        ctx = RecallContext(
            query_text=q,
            current_project_id="co-evolving-companion",
            sanctuary_active=False,
        )
        decision = gate.evaluate([cand], ctx)
        assert decision.disposition == RecallDisposition.SUPPRESS
        assert decision.reason == RecallReason.GENERIC_QA_SUPPRESSED
        assert decision.observability_category == "silent"
        assert decision.injection_context.is_empty is True


# ==============================================================================
# 3. Sanctuary reflective/self-model block
# ==============================================================================


def test_03_sanctuary_reflective_self_model_blocked() -> None:
    """Requirement 3: Psychological self-model and reflective recall blocked under Sanctuary."""
    gate = RecallGate()

    # Case A: Reflective query under Sanctuary
    ctx_query = RecallContext(
        query_text="最近我是不是越来越容易烦躁？",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
    )
    cand_insight = _make_candidate(
        candidate_id="insight_anxiety_pattern",
        candidate_type="confirmed_insight",
        statement="用户在高负荷排错时容易产生焦虑急躁情绪。",
    )
    dec_a = gate.evaluate([cand_insight], ctx_query)
    assert dec_a.disposition == RecallDisposition.SUPPRESS
    assert dec_a.reason == RecallReason.SANCTUARY_REFLECTIVE_BLOCK
    assert dec_a.observability_category == "silent"
    assert dec_a.injection_context.is_empty is True

    # Case B: General query under Sanctuary but candidate is a confirmed insight
    ctx_general = RecallContext(
        query_text="看看这个报错",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
    )
    dec_b = gate.evaluate([cand_insight], ctx_general)
    assert dec_b.disposition == RecallDisposition.SUPPRESS
    assert dec_b.reason == RecallReason.SANCTUARY_REFLECTIVE_BLOCK
    assert dec_b.observability_category == "silent"


# ==============================================================================
# 4. Sanctuary current-task continuity allowed
# ==============================================================================


def test_04_sanctuary_current_task_continuity_allowed() -> None:
    """Requirement 4: Minimum current task continuity is allowed under Sanctuary."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="烦死了，又是刚才那个报错",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
    )
    task_cand = _make_candidate(
        candidate_id="ep_recent_dll_error",
        candidate_type="episode",
        statement="刚才运行测试时遭遇 PySide6 DLL load failed 动态链接库丢失报错。",
        scope="project",
        project_id="co-evolving-companion",
    )

    decision = gate.evaluate([task_cand], ctx)

    assert decision.disposition == RecallDisposition.TASK_CONTINUITY_ONLY
    assert decision.reason == RecallReason.TASK_CONTINUITY_ALLOWED
    assert decision.observability_category == "task_continuity"
    assert len(decision.allowed_candidates) == 1
    assert decision.allowed_candidates[0].candidate_id == "ep_recent_dll_error"
    assert len(decision.injection_context.items) == 1
    assert "PySide6 DLL load failed" in decision.injection_context.items[0].statement


# ==============================================================================
# 5. Historical frustration blocked under Sanctuary
# ==============================================================================


def test_05_historical_frustration_blocked_under_sanctuary() -> None:
    """Requirement 5: Proactive past-frustration comparison is blocked under Sanctuary."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="继续刚才的工作",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
    )

    # Frustration candidate containing frustration keywords
    cand_frustration = _make_candidate(
        candidate_id="mem_past_frustration",
        candidate_type="semantic_memory",
        statement="用户在昨天排查死锁问题时极度崩溃烦躁与队友发生争吵。",
    )

    decision = gate.evaluate([cand_frustration], ctx)
    assert decision.disposition == RecallDisposition.SUPPRESS
    assert decision.reason == RecallReason.SANCTUARY_PAST_FRUSTRATION_BLOCK
    assert decision.observability_category == "silent"
    assert decision.injection_context.is_empty is True


# ==============================================================================
# 6. Privacy-pending blocked (IMPL-3)
# ==============================================================================


def test_06_privacy_pending_blocked() -> None:
    """Requirement 6: Artifacts with needs_privacy_redaction == 1 are strictly uninjectable."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="帮我看看之前的记录",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
        explicit_historical_intent=True,
    )
    cand_privacy = _make_candidate(
        candidate_id="chap_01_privacy",
        candidate_type="chapter_metadata",
        statement="第一章人生纪实包含未完成脱敏的敏感日记记录。",
    )
    # Using live_validator to report privacy_pending
    ctx = RecallContext(
        query_text="帮我看看之前的记录",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
        explicit_historical_intent=True,
        live_validator=lambda cid: (
            RecallReason.PRIVACY_PENDING if cid == "chap_01_privacy" else None
        ),
    )

    decision = gate.evaluate([cand_privacy], ctx)
    assert decision.disposition == RecallDisposition.SUPPRESS
    assert decision.reason == RecallReason.PRIVACY_PENDING
    assert decision.observability_category == "silent"
    assert decision.injection_context.is_empty is True


# ==============================================================================
# 7. Candidate invalidated/retracted after retrieval is suppressed
# ==============================================================================


def test_07_candidate_invalidated_or_retracted_suppressed() -> None:
    """Requirement 7: Invalidated or retracted candidates must never be injected."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="用户使用的显卡是哪款？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )
    cand_invalid = _make_candidate(
        candidate_id="mem_fact_old_gpu",
        statement="用户使用的显卡为 GTX 1080Ti。",
        validity_status="invalidated",
    )
    cand_retracted = _make_candidate(
        candidate_id="mem_fact_retracted",
        statement="用户偏好浅色主题。",
        validity_status="retracted",
    )

    dec_1 = gate.evaluate([cand_invalid], ctx)
    assert dec_1.disposition == RecallDisposition.SUPPRESS
    assert dec_1.reason == RecallReason.INVALIDATED_SUPPRESSED

    dec_2 = gate.evaluate([cand_retracted], ctx)
    assert dec_2.disposition == RecallDisposition.SUPPRESS
    assert dec_2.reason == RecallReason.INVALIDATED_SUPPRESSED


# ==============================================================================
# 8. Project scope mismatch blocked
# ==============================================================================


def test_08_project_scope_mismatch_blocked() -> None:
    """Requirement 8: Project scope mismatch and unresolved scope are blocked."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="我们项目的构建命令是什么？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )

    # Candidate belonging to project-alpha, query does not mention project-alpha
    cand_mismatch = _make_candidate(
        candidate_id="mem_proj_alpha_build",
        statement="项目构建使用 cargo build --release。",
        scope="project",
        project_id="project-alpha",
    )
    dec_mismatch = gate.evaluate([cand_mismatch], ctx)
    assert dec_mismatch.disposition == RecallDisposition.SUPPRESS
    assert dec_mismatch.reason == RecallReason.SCOPE_MISMATCH

    # Candidate with unresolved scope
    cand_unresolved = _make_candidate(
        candidate_id="mem_unresolved_scope",
        statement="临时测试命令 npm run dev。",
        scope="unresolved",
    )
    dec_unresolved = gate.evaluate([cand_unresolved], ctx)
    assert dec_unresolved.disposition == RecallDisposition.SUPPRESS
    assert dec_unresolved.reason == RecallReason.UNRESOLVED_SCOPE_SUPPRESSED


# ==============================================================================
# 9. Explicit historical request outside Sanctuary allowed
# ==============================================================================


def test_09_explicit_historical_request_outside_sanctuary_allowed() -> None:
    """Requirement 9: Explicit historical request outside Sanctuary is allowed."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="我们之前是怎么解决 PySide 闪退问题的？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
        explicit_historical_intent=True,
    )
    cand_history = _make_candidate(
        candidate_id="ep_pyside_crash_fix",
        candidate_type="episode",
        statement="之前通过调整 PySide6 动态链接库并修复无边框窗口双重重绘解决了闪退。",
        scope="project",
        project_id="co-evolving-companion",
    )

    decision = gate.evaluate([cand_history], ctx)
    assert decision.disposition == RecallDisposition.ALLOW
    assert decision.reason == RecallReason.EXPLICIT_HISTORY_ALLOWED
    assert decision.observability_category == "factual_context"
    assert len(decision.allowed_candidates) == 1
    assert decision.allowed_candidates[0].candidate_id == "ep_pyside_crash_fix"
    assert len(decision.injection_context.items) == 1


# ==============================================================================
# 10. Relationship-rule lookup allowed
# ==============================================================================


def test_10_relationship_rule_lookup_allowed() -> None:
    """Requirement 10: Relationship rule lookup outside Sanctuary is allowed."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="我们之间定过什么相处原则？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )
    cand_rule = _make_candidate(
        candidate_id="mem_rule_rest",
        candidate_type="semantic_memory",
        statement="用户专注工作时不希望被频繁打扰或反复提醒喝水休息，偏好自主掌握节奏。",
    )

    decision = gate.evaluate([cand_rule], ctx)
    assert decision.disposition == RecallDisposition.ALLOW
    assert decision.reason == RecallReason.EXPLICIT_RULE_ALLOWED
    assert decision.observability_category == "factual_context"
    assert len(decision.allowed_candidates) == 1


# ==============================================================================
# 11. Redundant candidates collapse to minimal sufficient context
# ==============================================================================


def test_11_redundant_candidates_collapse_to_minimal_sufficient_context() -> None:
    """Requirement 11: Duplicate/redundant propositions collapse to minimal sufficient context."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="我的机械键盘和显卡型号是什么？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )
    # Cand 1 and Cand 2 have identical proposition
    cand_kb_1 = _make_candidate(
        candidate_id="mem_kb_1",
        statement="用户的物理机械键盘型号为 HHKB Professional Hybrid Type-S 静电容键盘。",
        final_score=0.92,
    )
    cand_kb_dup = _make_candidate(
        candidate_id="mem_kb_2",
        statement="用户的物理机械键盘型号为 HHKB Professional Hybrid Type-S 静电容键盘。",
        final_score=0.80,
    )
    cand_gpu = _make_candidate(
        candidate_id="mem_gpu",
        statement="用户的显卡型号为 NVIDIA RTX 4090 24GB。",
        final_score=0.88,
    )

    decision = gate.evaluate([cand_kb_1, cand_kb_dup, cand_gpu], ctx)

    assert decision.disposition == RecallDisposition.ALLOW
    # Only 2 distinct propositions injected
    assert len(decision.injection_context.items) == 2
    injected_ids = decision.injection_context.candidate_ids()
    assert "mem_kb_1" in injected_ids
    assert "mem_gpu" in injected_ids
    assert "mem_kb_2" not in injected_ids
    # Duplicate candidate was recorded under suppressed
    suppressed_ids = [c.candidate_id for c in decision.suppressed_candidates]
    assert "mem_kb_2" in suppressed_ids


# ==============================================================================
# 12. Technical metadata cannot be injected
# ==============================================================================


def test_12_technical_metadata_cannot_be_injected() -> None:
    """Requirement 12: Injected context strictly strips technical scores and metadata."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="我平时用什么键盘？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )
    cand = _make_candidate(
        candidate_id="mem_fact_keyboard",
        statement="用户的物理机械键盘型号为 HHKB 静电容键盘。",
        final_score=0.95,
    )

    decision = gate.evaluate([cand], ctx)
    assert len(decision.injection_context.items) == 1
    item = decision.injection_context.items[0]

    # Verify InjectedMemoryItem has no score attributes
    assert not hasattr(item, "final_score")
    assert not hasattr(item, "lexical_score")
    assert not hasattr(item, "surface_score")
    assert not hasattr(item, "why_retrieved")

    # Verify prompt format does not contain score or debug strings
    prompt_context = decision.injection_context.format_for_prompt()
    assert "0.95" not in prompt_context
    assert "score" not in prompt_context.lower()
    assert "why_retrieved" not in prompt_context
    assert "test_fixture" not in prompt_context
    assert "[Retrieved Memory Context]" in prompt_context
    assert "- 用户的物理机械键盘型号为 HHKB 静电容键盘。" in prompt_context


# ==============================================================================
# 13. Allowed context retains provenance/candidate identity
# ==============================================================================


def test_13_allowed_context_retains_provenance_and_candidate_identity() -> None:
    """Requirement 13: Injected items retain candidate_id and typed provenance_refs."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="我平时用什么键盘？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )
    cand = _make_candidate(
        candidate_id="mem_fact_keyboard",
        statement="用户的物理机械键盘型号为 HHKB 静电容键盘。",
        provenance_refs=(
            ProvenanceRef(kind="slice", id="slice_kb_001", role="supporting"),
            ProvenanceRef(kind="event", id="evt_kb_002", role="contextual"),
        ),
    )

    decision = gate.evaluate([cand], ctx)
    assert len(decision.injection_context.items) == 1
    item = decision.injection_context.items[0]

    assert item.candidate_id == "mem_fact_keyboard"
    assert len(item.provenance_refs) == 2
    assert item.provenance_refs[0].id == "slice_kb_001"
    assert item.provenance_refs[0].kind == "slice"
    assert item.provenance_refs[1].id == "evt_kb_002"
    assert item.provenance_refs[1].kind == "event"
    assert item.origin == "retrieved_memory_context"


# ==============================================================================
# 14. WP-8 generates no final assistant sentence
# ==============================================================================


def test_14_wp8_generates_no_final_assistant_sentence() -> None:
    """Requirement 14: WP-8 must not generate any natural language assistant reply."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="我偏好多少空格缩进？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
    )
    cand = _make_candidate(
        candidate_id="mem_pref_indent",
        statement="用户写所有代码都严格偏好 4 空格缩进排版。",
    )

    decision = gate.evaluate([cand], ctx)

    # Decision only carries injection context and decisions, no reply sentence
    decision_dict = decision.to_dict()
    assert "reply" not in decision_dict
    assert "response" not in decision_dict
    assert "assistant_sentence" not in decision_dict

    # Check format_for_prompt() only has the raw bullet item
    prompt_str = decision.injection_context.format_for_prompt()
    assert "我记得" not in prompt_str
    assert "好的" not in prompt_str
    assert "你偏好" not in prompt_str


# ==============================================================================
# 15. Non-sensitive observability category/reason emitted
# ==============================================================================


def test_15_non_sensitive_observability_category_and_reason_emitted() -> None:
    """Requirement 15: Decision must emit structured machine-readable reason and category."""
    gate = RecallGate()
    valid_categories = {"silent", "factual_context", "reflective_context", "task_continuity"}

    test_cases = [
        # (query, sanctuary, expected_category, expected_reason)
        ("天气怎么样？", False, "silent", RecallReason.GENERIC_QA_SUPPRESSED),
        (
            "烦死了，又是刚才那个报错",
            True,
            "task_continuity",
            RecallReason.TASK_CONTINUITY_ALLOWED,
        ),
        (
            "我们之前是怎么解决 PySide 闪退问题的？",
            False,
            "factual_context",
            RecallReason.EXPLICIT_HISTORY_ALLOWED,
        ),
        (
            "最近我是不是越来越容易烦躁？",
            True,
            "silent",
            RecallReason.SANCTUARY_REFLECTIVE_BLOCK,
        ),
    ]

    for q, sanct, exp_cat, exp_reason in test_cases:
        ctx = RecallContext(
            query_text=q,
            current_project_id="co-evolving-companion",
            sanctuary_active=sanct,
            explicit_historical_intent=("之前" in q),
        )
        cand = _make_candidate(
            candidate_id="cand_test",
            candidate_type="episode" if "报错" in q or "解决" in q else "semantic_memory",
            statement="相关测试经历或事实。",
            scope="project",
            project_id="co-evolving-companion",
        )
        decision = gate.evaluate([cand], ctx)
        assert decision.observability_category in valid_categories
        assert decision.observability_category == exp_cat
        assert decision.reason == exp_reason


# ==============================================================================
# 16. No random forced 80/15/5 speaking behavior
# ==============================================================================


def test_16_no_random_forced_80_15_5_speaking_behavior() -> None:
    """Requirement 16: Gating must be 100% deterministic with zero randomness."""
    gate = RecallGate()
    ctx = RecallContext(
        query_text="烦死了，又是刚才那个报错",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
    )
    cand = _make_candidate(
        candidate_id="ep_error_pyside",
        candidate_type="episode",
        statement="刚才运行测试时遭遇 PySide6 闪退报错。",
        scope="project",
        project_id="co-evolving-companion",
    )

    first_decision = gate.evaluate([cand], ctx)

    # Run 100 times to verify determinism
    for _ in range(100):
        decision = gate.evaluate([cand], ctx)
        assert decision.disposition == first_decision.disposition
        assert decision.reason == first_decision.reason
        assert decision.observability_category == first_decision.observability_category
        assert (
            decision.injection_context.candidate_ids()
            == first_decision.injection_context.candidate_ids()
        )


# ==============================================================================
# 17. TOCTOU: candidate becomes privacy-pending/invalid before injection -> blocked
# ==============================================================================


def test_17_toctou_candidate_invalidated_or_redacted_before_injection() -> None:
    """Requirement 17: Candidate invalidated/redacted post-retrieval is blocked at injection."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_store.db"
        store = ChronicleStoreV2(db_path)
        try:
            # Insert required raw slice evidence
            raw_slice = RawSliceEntity(
                slice_id="slice_toctou_test",
                occurred_at="2026-10-18T10:00:00Z",
                content="我使用的是 iPhone 15 Pro",
            )
            store.insert_raw_slice(raw_slice)

            # Insert active memory
            mem = SemanticMemoryEntity(
                memory_id="mem_toctou_test",
                category="fact",
                statement="用户使用的开发手机为 iPhone 15 Pro。",
                authority_class="user_asserted",
                scope="global",
                valid_from="2026-10-18T10:00:00Z",
                validity_status="active",
                source_slice_id="slice_toctou_test",
            )
            store.insert_semantic_memory(mem)
            # Insert chapter metadata
            chap = ChapterMetadataEntity(
                chapter_id="chap_toctou_test",
                title="第一章",
                file_path="growth/ch01.md",
                time_span_start="2026-01-01",
                time_span_end="2026-06-01",
                needs_privacy_redaction=0,
            )
            store.insert_chapter_metadata(chap)

            # Initial candidates retrieved earlier when active
            cand_mem = _make_candidate(
                candidate_id="mem_toctou_test",
                statement="用户使用的开发手机为 iPhone 15 Pro。",
            )
            cand_chap = _make_candidate(
                candidate_id="chap_toctou_test",
                candidate_type="chapter_metadata",
                statement="第一章人生纪实。",
            )

            gate = RecallGate()

            # Step 1: Invalidate mem_toctou_test in live store
            store.connection.execute(
                "UPDATE semantic_memories SET validity_status = 'invalidated' WHERE memory_id = ?",
                ("mem_toctou_test",),
            )
            store.connection.commit()
            ctx_1 = RecallContext(
                query_text="我的开发手机是什么型号？",
                store=store,
            )
            dec_1 = gate.evaluate([cand_mem], ctx_1)
            assert dec_1.disposition == RecallDisposition.SUPPRESS
            assert dec_1.reason == RecallReason.INVALIDATED_SUPPRESSED

            # Step 2: Mark chapter as needs_privacy_redaction in live store
            store.connection.execute(
                "UPDATE chapter_metadata SET needs_privacy_redaction = 1 WHERE chapter_id = ?",
                ("chap_toctou_test",),
            )
            store.connection.commit()
            ctx_2 = RecallContext(
                query_text="帮我回顾第一章",
                store=store,
                explicit_historical_intent=True,
            )
            dec_2 = gate.evaluate([cand_chap], ctx_2)
            assert dec_2.disposition == RecallDisposition.SUPPRESS
            assert dec_2.reason == RecallReason.PRIVACY_PENDING
        finally:
            store.close()


def test_17_toctou_live_validator_callback() -> None:
    """Requirement 17b: TOCTOU validation via live_validator hook."""
    cand = _make_candidate(candidate_id="cand_cached", statement="某条活跃缓存记忆。")
    gate = RecallGate()

    # Hook indicates candidate has been marked privacy_pending
    ctx_privacy = RecallContext(
        query_text="查询记录",
        live_validator=lambda cid: RecallReason.PRIVACY_PENDING if cid == "cand_cached" else None,
    )
    dec_p = gate.evaluate([cand], ctx_privacy)
    assert dec_p.disposition == RecallDisposition.SUPPRESS
    assert dec_p.reason == RecallReason.PRIVACY_PENDING

    # Hook indicates candidate has been deleted/invalidated
    ctx_invalid = RecallContext(
        query_text="查询记录",
        live_validator=lambda cid: False,
    )
    dec_inv = gate.evaluate([cand], ctx_invalid)
    assert dec_inv.disposition == RecallDisposition.SUPPRESS
    assert dec_inv.reason == RecallReason.INVALIDATED_SUPPRESSED


# ==============================================================================
# 18. Production DB/runtime untouched
# ==============================================================================


def test_18_production_db_and_runtime_untouched() -> None:
    """Requirement 18: Production DB and runtime remain untouched and isolated."""
    # 1. Verify production database hash
    candidate_paths = [
        Path("D:/CodeProjects/co-evolving-companion/data/companion_chronicle.db"),
        Path(__file__).parents[2] / "data" / "companion_chronicle.db",
    ]
    prod_db = next((p for p in candidate_paths if p.exists()), None)
    if prod_db is not None:
        with open(prod_db, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest().lower()
        assert actual_hash == EXPECTED_PROD_DB_HASH, (
            f"Production DB modified! {actual_hash} != {EXPECTED_PROD_DB_HASH}"
        )

    # 2. Verify feature flags default OFF
    flags = MemoryFeatureFlags()
    assert flags.memory_v2_retrieval is False, (
        "memory_v2_retrieval must default to False in production!"
    )

    # 3. Verify V1 runtime is default
    assert flags.memory_v2_storage is False


# ==============================================================================
# End-to-End Pipeline -> Gate Integration Test
# ==============================================================================


def test_e2e_retrieval_pipeline_to_recall_gate_integration() -> None:
    """Integration: TechnicalRetrievalPipeline output feeds directly into RecallGate."""
    corpus = build_frozen_canonical_corpus(FROZEN_BENCHMARK_NOW)
    repo = StaticCandidateRepository(corpus)
    pipeline = TechnicalRetrievalPipeline(repo)
    gate = RecallGate()

    # Query 1: Task continuity under Sanctuary
    q_ctx_1 = RetrievalQueryContext(
        query_text="烦死了，又是刚才那个报错",
        current_project_id="co-evolving-companion",
        sanctuary_active=True,
        now=FROZEN_BENCHMARK_NOW,
    )
    res_1 = pipeline.retrieve(q_ctx_1)
    dec_1 = gate.evaluate(res_1, q_ctx_1)

    assert dec_1.disposition == RecallDisposition.TASK_CONTINUITY_ONLY
    assert dec_1.reason == RecallReason.TASK_CONTINUITY_ALLOWED
    assert dec_1.observability_category == "task_continuity"
    assert len(dec_1.injection_context.items) == 1

    # Query 2: Generic QA through pipeline
    q_ctx_2 = RetrievalQueryContext(
        query_text="Python 里的列表怎么反转排序？",
        current_project_id="co-evolving-companion",
        sanctuary_active=False,
        now=FROZEN_BENCHMARK_NOW,
    )
    res_2 = pipeline.retrieve(q_ctx_2)
    dec_2 = gate.evaluate(res_2, q_ctx_2)

    assert dec_2.disposition == RecallDisposition.NO_MEMORY or dec_2.is_silent is True
    assert dec_2.observability_category == "silent"
    assert dec_2.injection_context.is_empty is True
