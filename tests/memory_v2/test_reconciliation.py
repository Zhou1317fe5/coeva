"""Tests for Reconciliation Engine & Invariants (Memory V2.1 Lane E / WP-4).

Covers all required implementation scenarios:
1. ADD valid.
2. “显示器换成了 X” with no prior display fact must not false-SUPERSEDE.
3. Explicit correction of an existing GPU fact -> SUPERSEDE.
4. Weak contradiction -> AMBIGUOUS.
5. Independent equivalent evidence -> REINFORCE.
6. Duplicate/replay -> NOOP, proof delta 0.
7. Echo-only -> NOOP.
8. Echo + new delta -> preserve/reconcile delta.
9. Unknown scope stays unresolved.
10. Missing/nonexistent provenance -> fail closed, no write.
11. Invalid model-suggested action is overridden/rejected safely.
12. Failure mid-mutation -> full rollback.
13. Superseded history remains representable/queryable.
14. Same-episode retry/replay/UI duplicate cannot inflate proof.
15. WP-2 lifecycle sees correct provenance after mutations.
16. No Observation/Hypothesis/Insight is generated.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.memory.v2.entities import (
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.lifecycle import LifecycleService
from src.memory.v2.proposals import (
    AdmissionDecision,
    CandidateSemanticMemory,
    ConsolidationProposal,
)
from src.memory.v2.reconciliation import (
    ReconciliationEngine,
)
from src.memory.v2.store import ChronicleStoreV2


@pytest.fixture
def store() -> ChronicleStoreV2:
    """Provide an in-memory ChronicleStoreV2 with PRAGMA foreign_keys = ON."""
    return ChronicleStoreV2(":memory:")


@pytest.fixture
def engine(store: ChronicleStoreV2) -> ReconciliationEngine:
    """Provide a ReconciliationEngine initialized on the in-memory store."""
    return ReconciliationEngine(store)


def make_test_slice(
    slice_id: str,
    content: str,
    occurred_at: str = "2026-10-18T12:00:00+00:00",
    project_id: str | None = None,
    source: Any = "manual_feed",
    ingestion_dedup_key: str | None = None,
) -> RawSliceEntity:
    """Helper to create a RawSliceEntity with unique dedup key."""
    return RawSliceEntity(
        slice_id=slice_id,
        occurred_at=occurred_at,
        content=content,
        actor="user",
        source=source,
        project_id=project_id,
        ingestion_dedup_key=ingestion_dedup_key or f"dedup_{slice_id}",
    )


# ── Scenario 1: ADD valid ─────────────────────────────────────────────────────


def test_scenario_01_add_valid(store: ChronicleStoreV2, engine: ReconciliationEngine) -> None:
    """1. ADD valid: genuine new durable fact creates active semantic memory."""
    slice_entity = make_test_slice(
        slice_id="slice_add_01",
        content="我平时的首选编程语言是 Python 和 Rust。",
    )
    store.insert_raw_slice(slice_entity)

    results = engine.reconcile_slice(slice_entity)
    assert len(results) == 1
    res = results[0]

    assert res.success
    assert res.action == "ADD"
    assert res.proof_delta == 1
    assert len(res.affected_memory_ids) == 1

    # Verify state in database
    new_mem_id = res.affected_memory_ids[0]
    mem = store.get_semantic_memory(new_mem_id)
    assert mem is not None
    assert mem.validity_status == "active"
    assert mem.source_slice_id == "slice_add_01"
    assert mem.invalidated_at is None
    assert mem.superseded_by is None


# ── Scenario 2: “换成了” with no prior fact must not false-SUPERSEDE ───────────


def test_scenario_02_no_prior_fact_prevents_false_supersede(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """2. “显示器换成了 X” with no prior display fact must NOT false-SUPERSEDE."""
    slice_entity = make_test_slice(
        slice_id="slice_lg_01",
        content="我的主显示器换成了 4K 144Hz 的 LG 27GP95R。",
    )
    store.insert_raw_slice(slice_entity)

    # Even if an untrusted Phase-1 model suggests SUPERSEDE:
    untrusted_claim = CandidateSemanticMemory(
        statement="我的主显示器换成了 4K 144Hz 的 LG 27GP95R。",
        category="fact",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_lg_01",
        suggested_action="SUPERSEDE",
        target_superseded_id="mem_nonexistent_display",
    )
    proposal = ConsolidationProposal(
        proposal_id="prop_lg_01",
        admission=AdmissionDecision(decision="ADMIT", rationale="Hardware fact"),
        proposed_claims=[untrusted_claim],
        source_id="slice_lg_01",
        source_type="slice",
        created_at="2026-10-18T12:00:00+00:00",
    )

    results = engine.reconcile_proposal(proposal)
    assert len(results) == 1
    res = results[0]

    # Deterministic validator must fail-closed downgrade to ADD (False SUPERSEDE = 0)
    assert res.success
    assert res.action == "ADD"
    assert res.proof_delta == 1

    created_mem = store.get_semantic_memory(res.affected_memory_ids[0])
    assert created_mem is not None
    assert created_mem.validity_status == "active"


# ── Scenario 3: Explicit correction of an existing GPU fact -> SUPERSEDE ──────


def test_scenario_03_explicit_correction_supersedes(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """3. Explicit correction of an existing GPU fact -> SUPERSEDE."""
    # Seed old GPU fact
    slice_old = make_test_slice(
        slice_id="slice_gpu_old",
        occurred_at="2026-10-01T12:00:00+00:00",
        content="显卡是 RTX 4090",
    )
    store.insert_raw_slice(slice_old)
    old_mem = SemanticMemoryEntity(
        memory_id="mem_fact_gpu_4090",
        category="fact",
        statement="显卡是 RTX 4090",
        authority_class="user_asserted",
        scope="unresolved",
        valid_from="2026-10-01T12:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_gpu_old",
    )
    store.insert_semantic_memory(old_mem)

    # User corrects: "不好意思，刚才我记错了，显卡其实是 RTX 4080 不是 4090。"
    slice_correction = make_test_slice(
        slice_id="slice_gpu_corr",
        content="不好意思，刚才我记错了，显卡其实是 RTX 4080 不是 4090。",
    )
    store.insert_raw_slice(slice_correction)

    results = engine.reconcile_slice(
        slice_correction,
        context={"target_existing_memory": "mem_fact_gpu_4090"},
    )
    assert len(results) == 1
    res = results[0]

    assert res.success
    assert res.action == "SUPERSEDE"
    assert res.proof_delta == 1

    # Verify old memory is superseded
    updated_old = store.get_semantic_memory("mem_fact_gpu_4090")
    assert updated_old is not None
    assert updated_old.validity_status == "superseded"
    assert updated_old.invalidated_at is not None
    assert updated_old.superseded_by is not None

    # Verify new memory is active and linked
    new_mem_id = updated_old.superseded_by
    new_mem = store.get_semantic_memory(new_mem_id)
    assert new_mem is not None
    assert new_mem.validity_status == "active"
    assert new_mem.source_slice_id == "slice_gpu_corr"


# ── Scenario 4: Weak contradiction -> AMBIGUOUS ───────────────────────────────


def test_scenario_04_weak_contradiction_is_ambiguous(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """4. Weak contradiction / hesitation -> AMBIGUOUS (fail-closed, proof delta 0)."""
    slice_base = make_test_slice(
        slice_id="slice_indent_base",
        occurred_at="2025-01-01T00:00:00+00:00",
        content="代码缩进坚持 4 格",
    )
    store.insert_raw_slice(slice_base)
    base_mem = SemanticMemoryEntity(
        memory_id="mem_pref_indent_4",
        category="preference",
        statement="代码缩进坚持 4 格",
        authority_class="user_asserted",
        scope="global",
        valid_from="2025-01-01T00:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_indent_base",
    )
    store.insert_semantic_memory(base_mem)

    # User says: "有些前端项目用 2 格缩进看起来也挺紧凑好看的。"
    slice_weak = make_test_slice(
        slice_id="slice_weak_tab",
        content="有些前端项目用 2 格缩进看起来也挺紧凑好看的。",
    )
    store.insert_raw_slice(slice_weak)

    results = engine.reconcile_slice(
        slice_weak,
        context={"target_existing_memory": "mem_pref_indent_4"},
    )
    assert len(results) == 1
    res = results[0]

    assert res.success
    assert res.action == "AMBIGUOUS"
    assert res.proof_delta == 0

    # Old memory MUST remain active and intact
    old_mem = store.get_semantic_memory("mem_pref_indent_4")
    assert old_mem is not None
    assert old_mem.validity_status == "active"
    assert old_mem.invalidated_at is None

    # New claim is recorded as ambiguous
    amb_mem_id = res.affected_memory_ids[0]
    amb_mem = store.get_semantic_memory(amb_mem_id)
    assert amb_mem is not None
    assert amb_mem.validity_status == "ambiguous"


# ── Scenario 5: Independent equivalent evidence -> REINFORCE ──────────────────


def test_scenario_05_independent_evidence_reinforces(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """5. Independent equivalent evidence -> REINFORCE with proof delta 1."""
    slice_base = make_test_slice(
        slice_id="slice_disp_base",
        content="我的主显示器换成了 4K 144Hz 的 LG 27GP95R。",
    )
    store.insert_raw_slice(slice_base)
    mem_base = SemanticMemoryEntity(
        memory_id="mem_display_lg_27gp",
        category="fact",
        statement="我的主显示器换成了 4K 144Hz 的 LG 27GP95R。",
        authority_class="user_asserted",
        scope="unresolved",
        valid_from="2026-10-18T12:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_disp_base",
    )
    store.insert_semantic_memory(mem_base)

    # One month later in a different episode:
    slice_reinf = make_test_slice(
        slice_id="slice_disp_month_later",
        occurred_at="2026-11-17T12:00:00+00:00",
        content="顺便说下，这台 4K 144Hz LG 显示器打代码确实比旧的舒服多了。",
    )
    store.insert_raw_slice(slice_reinf)

    results = engine.reconcile_slice(
        slice_reinf,
        context={
            "target_existing_memory": "mem_display_lg_27gp",
            "episode_id": "ep_display_review",
            "occurred_at": "2026-11-17T12:00:00+00:00",
        },
    )
    assert len(results) == 1
    res = results[0]

    assert res.success
    assert res.action == "REINFORCE"
    assert res.proof_delta == 1

    # Verify reinforcement ledger row inserted
    rows = store.connection.execute(
        "SELECT * FROM evidence_reinforcements WHERE memory_id = ?;",
        ("mem_display_lg_27gp",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["slice_id"] == "slice_disp_month_later"


# ── Scenario 6: Duplicate transport / replay -> NOOP, proof delta 0 ────────────


def test_scenario_06_duplicate_transport_noop(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """6. Duplicate / replay transport -> NOOP with proof delta 0."""
    slice_retry = make_test_slice(
        slice_id="slice_retry_02",
        occurred_at="2026-10-18T12:00:02+00:00",
        content="我的主显示器换成了 4K 144Hz 的 LG 27GP95R。",
        ingestion_dedup_key="dedup_lg_display_hash",
    )
    store.insert_raw_slice(slice_retry)

    results = engine.reconcile_slice(
        slice_retry,
        context={"existing_key_matched": True},
    )
    assert len(results) == 1
    res = results[0]

    assert res.success
    assert res.action == "NOOP"
    assert res.proof_delta == 0
    assert len(res.affected_memory_ids) == 0

    # No semantic memories created
    count = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert count == 0


# ── Scenario 7: Echo-only -> NOOP ─────────────────────────────────────────────


def test_scenario_07_echo_only_noop(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """7. Echo-only acknowledgment (Case E1) -> NOOP with proof delta 0."""
    slice_echo_ack = make_test_slice(
        slice_id="slice_echo_01",
        content="嗯，你说的对。",
        source="bubble_reply",
    )
    store.insert_raw_slice(slice_echo_ack)

    results = engine.reconcile_slice(
        slice_echo_ack,
        echoed_proposition="你之前提到过偏好深色主题与暗黑模式对吧？",
    )
    assert len(results) == 1
    res = results[0]

    assert res.success
    assert res.action == "NOOP"
    assert res.proof_delta == 0


# ── Scenario 8: Echo + new delta -> preserve and reconcile delta ───────────────


def test_scenario_08_echo_with_delta_preserved(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """8. Echo + new delta (Case E2) -> preserve and reconcile delta."""
    # Seed old dark theme preference
    slice_dark = make_test_slice(
        slice_id="slice_dark_base",
        occurred_at="2025-01-01T00:00:00+00:00",
        content="偏好深色主题与暗黑模式",
    )
    store.insert_raw_slice(slice_dark)
    mem_dark = SemanticMemoryEntity(
        memory_id="mem_pref_theme_dark",
        category="preference",
        statement="偏好深色主题与暗黑模式",
        authority_class="user_asserted",
        scope="global",
        valid_from="2025-01-01T00:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_dark_base",
    )
    store.insert_semantic_memory(mem_dark)

    # User response with echo + delta: "嗯，不过现在改用浅色主题确实看久了更舒服。"
    slice_echo_delta = make_test_slice(
        slice_id="slice_echo_delta_01",
        content="嗯，不过现在改用浅色主题确实看久了更舒服。",
        source="bubble_reply",
    )
    store.insert_raw_slice(slice_echo_delta)

    results = engine.reconcile_slice(
        slice_echo_delta,
        echoed_proposition="你之前提到过偏好深色主题对吧？",
        context={"target_existing_memory": "mem_pref_theme_dark"},
    )
    assert len(results) == 1
    res = results[0]

    assert res.success
    assert res.action == "SUPERSEDE"
    assert res.proof_delta == 1

    # Old theme superseded
    old_theme = store.get_semantic_memory("mem_pref_theme_dark")
    assert old_theme is not None
    assert old_theme.validity_status == "superseded"


# ── Scenario 9: Unknown scope stays unresolved ────────────────────────────────


def test_scenario_09_unknown_scope_stays_unresolved(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """9. Unknown scope stays unresolved (INV: Unknown != Global)."""
    slice_entity = make_test_slice(
        slice_id="slice_unresolved_01",
        content="把单元测试框架统一换成 pytest。",
        project_id=None,
    )
    store.insert_raw_slice(slice_entity)

    results = engine.reconcile_slice(slice_entity)
    assert len(results) == 1
    res = results[0]

    assert res.success
    assert res.action == "ADD"
    assert res.proof_delta == 1

    mem = store.get_semantic_memory(res.affected_memory_ids[0])
    assert mem is not None
    assert mem.scope == "unresolved"
    assert mem.project_id is None


# ── Scenario 10: Missing/nonexistent provenance -> fail closed ────────────────


def test_scenario_10_missing_provenance_fails_closed(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """10. Missing / nonexistent provenance -> fail closed, no write."""
    claim = CandidateSemanticMemory(
        statement="未持久化切片的伪记忆",
        category="fact",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_phantom_999",
        suggested_action="ADD",
    )
    proposal = ConsolidationProposal(
        proposal_id="prop_phantom",
        admission=AdmissionDecision(decision="ADMIT", rationale="Phantom claim"),
        proposed_claims=[claim],
        source_id="slice_phantom_999",
        source_type="slice",
        created_at="2026-10-18T12:00:00+00:00",
    )

    results = engine.reconcile_proposal(proposal)
    assert len(results) == 1
    res = results[0]

    assert res.action == "NOOP"
    assert res.proof_delta == 0
    assert len(res.affected_memory_ids) == 0

    count = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert count == 0


# ── Scenario 11: Invalid model-suggested action overridden safely ─────────────


def test_scenario_11_invalid_model_suggestion_overridden(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """11. Invalid model-suggested action is overridden safely by deterministic validator."""
    slice_entity = make_test_slice(
        slice_id="slice_term_change",
        content="我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。",
    )
    store.insert_raw_slice(slice_entity)

    # LLM hallucinates suggested_action="REINFORCE" for an explicit migration
    untrusted_claim = CandidateSemanticMemory(
        statement="开发全面迁移到 PowerShell 7，不再用 CMD",
        category="preference",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_term_change",
        suggested_action="REINFORCE",  # Invalid suggestion!
        target_superseded_id=None,
    )
    proposal = ConsolidationProposal(
        proposal_id="prop_term_change",
        admission=AdmissionDecision(decision="ADMIT", rationale="Valid preference"),
        proposed_claims=[untrusted_claim],
        source_id="slice_term_change",
        source_type="slice",
        created_at="2026-10-18T12:00:00+00:00",
    )

    results = engine.reconcile_proposal(proposal)
    assert len(results) == 1
    res = results[0]

    # REINFORCE without valid active target downgrades to ADD
    assert res.success
    assert res.action == "ADD"
    assert res.proof_delta == 1


# ── Scenario 12: Failure mid-mutation -> full rollback ─────────────────────────


def test_scenario_12_failure_mid_mutation_rolls_back(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """12. Failure mid-mutation -> full rollback (zero partial semantic state)."""
    slice_entity = make_test_slice(
        slice_id="slice_fail_test",
        content="测试事务原子回滚",
    )
    store.insert_raw_slice(slice_entity)

    plan = engine.build_mutation_plan(
        decision=engine.validator.validate_claim(
            CandidateSemanticMemory(
                statement="测试事务原子回滚",
                category="fact",
                scope="unresolved",
                authority_class="user_asserted",
                source_slice_id="slice_fail_test",
                suggested_action="ADD",
            ),
            AdmissionDecision(decision="ADMIT", rationale="Test"),
        ),
        source_slice_id="slice_fail_test",
        occurred_at="2026-10-18T12:00:00+00:00",
    )

    with patch.object(store, "insert_semantic_memory", side_effect=RuntimeError("Disk failure")):
        res = engine.execute_plan(
            plan,
            engine.validator.validate_claim(
                CandidateSemanticMemory(
                    statement="测试事务原子回滚",
                    category="fact",
                    scope="unresolved",
                    authority_class="user_asserted",
                    source_slice_id="slice_fail_test",
                ),
                AdmissionDecision(decision="ADMIT", rationale="Test"),
            ),
        )
        assert not res.success
        assert "Disk failure" in str(res.error)

    # Verify zero partial state in database
    count = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert count == 0


# ── Scenario 13: Superseded history remains representable/queryable ───────────


def test_scenario_13_superseded_history_remains_queryable(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """13. Superseded history remains representable and queryable (INV-2)."""
    slice_old = make_test_slice(
        slice_id="slice_cmd_base",
        occurred_at="2025-01-01T00:00:00+00:00",
        content="终端使用 CMD",
    )
    store.insert_raw_slice(slice_old)
    mem_cmd = SemanticMemoryEntity(
        memory_id="mem_pref_term_cmd",
        category="preference",
        statement="终端使用 CMD",
        authority_class="user_asserted",
        scope="global",
        valid_from="2025-01-01T00:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_cmd_base",
    )
    store.insert_semantic_memory(mem_cmd)

    slice_new = make_test_slice(
        slice_id="slice_pwsh_new",
        content="我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。",
    )
    store.insert_raw_slice(slice_new)

    engine.reconcile_slice(
        slice_new,
        context={"target_existing_memory": "mem_pref_term_cmd"},
    )

    # Historical query specifically looking up the superseded memory
    historical_mem = store.get_semantic_memory("mem_pref_term_cmd")
    assert historical_mem is not None
    assert historical_mem.validity_status == "superseded"
    assert historical_mem.invalidated_at is not None
    assert historical_mem.superseded_by is not None

    # New memory is active
    new_active = store.get_semantic_memory(historical_mem.superseded_by)
    assert new_active is not None
    assert new_active.validity_status == "active"


# ── Scenario 14: Same-episode retry/replay cannot inflate proof ───────────────


def test_scenario_14_same_episode_retry_cannot_inflate_proof(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """14. Same-episode retry/replay/UI duplicate cannot inflate proof."""
    slice_base = make_test_slice(
        slice_id="slice_pyside_s14",
        content="项目用 PySide6 作为表现层",
    )
    store.insert_raw_slice(slice_base)
    mem_pyside = SemanticMemoryEntity(
        memory_id="mem_pyside_s14",
        category="fact",
        statement="项目用 PySide6 作为表现层",
        authority_class="user_asserted",
        scope="project",
        project_id="co-evolving-companion",
        valid_from="2026-10-18T12:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_pyside_s14",
    )
    store.insert_semantic_memory(mem_pyside)

    # First reinforcement in episode ep_work_01
    slice_reinf1 = make_test_slice(
        slice_id="slice_reinf1",
        occurred_at="2026-10-18T12:05:00+00:00",
        content="项目用 PySide6 作为表现层",
    )
    store.insert_raw_slice(slice_reinf1)
    res1 = engine.reconcile_slice(
        slice_reinf1,
        context={
            "target_existing_memory": "mem_pyside_s14",
            "episode_id": "ep_work_01",
            "occurred_at": "2026-10-18T12:05:00+00:00",
        },
    )[0]
    assert res1.action == "REINFORCE"
    assert res1.proof_delta == 1

    # Second repetition in SAME episode ep_work_01 and SAME date
    slice_reinf2 = make_test_slice(
        slice_id="slice_reinf2",
        occurred_at="2026-10-18T12:15:00+00:00",
        content="项目用 PySide6 作为表现层",
    )
    store.insert_raw_slice(slice_reinf2)
    res2 = engine.reconcile_slice(
        slice_reinf2,
        context={
            "target_existing_memory": "mem_pyside_s14",
            "episode_id": "ep_work_01",
            "occurred_at": "2026-10-18T12:15:00+00:00",
        },
    )[0]
    assert res2.action == "NOOP"
    assert res2.proof_delta == 0

    # Total reinforcements in ledger must remain exactly 1
    reinf_count = store.connection.execute(
        "SELECT count(*) FROM evidence_reinforcements WHERE memory_id = ?;",
        ("mem_pyside_s14",),
    ).fetchone()[0]
    assert reinf_count == 1


# ── Scenario 15: WP-2 lifecycle sees correct provenance after mutations ────────


def test_scenario_15_wp2_lifecycle_compatibility(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """15. WP-2 lifecycle sees correct provenance after mutations and can hard-delete."""
    slice_entity = make_test_slice(
        slice_id="slice_life_01",
        content="架构采用 FastAPI 后端服务",
    )
    store.insert_raw_slice(slice_entity)

    # Reconcile new memory
    res = engine.reconcile_slice(slice_entity)[0]
    assert res.action == "ADD"
    mem_id = res.affected_memory_ids[0]

    # Verify WP-2 LifecycleService and ProvenanceRepository
    lifecycle = LifecycleService(store)
    prov_repo = lifecycle.provenance_repo

    primary_mems = prov_repo.get_slice_primary_memories("slice_life_01")
    assert len(primary_mems) == 1
    assert primary_mems[0].memory_id == mem_id

    refs = store.get_provenance_refs_for_memory(mem_id)
    assert any(r["kind"] == "slice" and r["id"] == "slice_life_01" for r in refs)

    # Verify WP-2 atomic hard delete operates cleanly with full dependency closure
    delete_res = lifecycle.hard_delete_slice("slice_life_01")
    assert delete_res.success
    assert delete_res.foreign_key_check_passed

    # Memory was cleanly retracted/removed, zero orphan residues
    mem_after = store.get_semantic_memory(mem_id)
    assert mem_after is None or mem_after.validity_status == "invalidated"


# ── Scenario 16: No Observation/Hypothesis/Insight is generated ───────────────


def test_scenario_16_no_observation_hypothesis_insight_generated(
    store: ChronicleStoreV2,
    engine: ReconciliationEngine,
) -> None:
    """16. WP-4 must NOT generate Observation, Hypothesis, or Confirmed Insight."""
    slice_entity = make_test_slice(
        slice_id="slice_s16_no_leak",
        content="我平时的首选编程语言是 Python 和 Rust。",
    )
    store.insert_raw_slice(slice_entity)

    engine.reconcile_slice(slice_entity)

    # Strict isolation check: counts of WP-6 / slow-path tables must be 0
    obs_count = store.connection.execute("SELECT count(*) FROM observations;").fetchone()[0]
    hyp_count = store.connection.execute("SELECT count(*) FROM hypotheses;").fetchone()[0]
    ins_count = store.connection.execute("SELECT count(*) FROM confirmed_insights;").fetchone()[0]

    assert obs_count == 0
    assert hyp_count == 0
    assert ins_count == 0
