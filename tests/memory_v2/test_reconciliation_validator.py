"""Unit tests for ReconciliationValidator (Memory V2.1 Lane E / WP-4).

Tests deterministic local validation rules:
- Rule-V1: Source Exists & Provenance Check
- Rule-V2: Unknown Scope Enforcement (S-14 Unknown != Global)
- Rule-V3: Claim-Sensitive Authority & Anti-Echo Guard
- Rule-V4: Fail-Closed Supersede Target Validity (False SUPERSEDE = 0)
- Rule-V5: Independent Evidence Fingerprint Collision Check (False REINFORCE = 0)
- Rule-V6: Privacy Pending Exclusion Gate
- Overriding untrusted model-suggested actions safely
"""

from __future__ import annotations

from typing import Any

import pytest

from src.memory.v2.echo_guard import EchoGuardResult
from src.memory.v2.entities import (
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.proposals import (
    AdmissionDecision,
    CandidateSemanticMemory,
)
from src.memory.v2.reconciliation_validator import (
    ReconciliationValidator,
    compute_independence_fingerprint,
    compute_independence_hash,
    normalize_content,
)
from src.memory.v2.store import ChronicleStoreV2


@pytest.fixture
def in_memory_store() -> ChronicleStoreV2:
    """Create an in-memory ChronicleStoreV2 for isolated validator tests."""
    return ChronicleStoreV2(":memory:")


def make_test_slice(
    slice_id: str,
    content: str,
    occurred_at: str = "2026-10-18T12:00:00+00:00",
    project_id: str | None = None,
    source: Any = "manual_feed",
) -> RawSliceEntity:
    """Helper to create a RawSliceEntity with unique dedup key."""
    return RawSliceEntity(
        slice_id=slice_id,
        occurred_at=occurred_at,
        content=content,
        actor="user",
        source=source,
        project_id=project_id,
        ingestion_dedup_key=f"dedup_{slice_id}",
    )


def test_rule_v1_source_must_exist(in_memory_store: ChronicleStoreV2) -> None:
    """Rule-V1: Missing source slice must fail closed with missing_provenance."""
    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="我的主显示器换成了 4K 144Hz 的 LG 27GP95R。",
        category="fact",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_nonexistent",
        suggested_action="ADD",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Valid fact")

    decision = validator.validate_claim(claim, admission)
    assert decision.action == "NOOP"
    assert not decision.is_valid
    assert decision.rejection_category == "missing_provenance"
    assert decision.proof_delta == 0


def test_rule_v2_unknown_scope_forced_to_unresolved(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Rule-V2: Unknown project scope must be forced to 'unresolved' (Unknown != Global)."""
    slice_entity = make_test_slice(
        slice_id="slice_01",
        content="把单元测试框架统一换成 pytest。",
    )
    in_memory_store.insert_raw_slice(slice_entity)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="把单元测试框架统一换成 pytest。",
        category="fact",
        scope="global",
        authority_class="user_asserted",
        source_slice_id="slice_01",
        project_id=None,
        suggested_action="ADD",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Valid fact")

    decision = validator.validate_claim(claim, admission)
    assert decision.action == "ADD"
    assert decision.scope == "unresolved"
    assert decision.project_id is None


def test_rule_v2_universal_marker_preserves_global_scope(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Rule-V2: Explicit universal marker allows global scope."""
    slice_entity = make_test_slice(
        slice_id="slice_universal",
        content="在任何项目里我都坚持 4 格缩进。",
    )
    in_memory_store.insert_raw_slice(slice_entity)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="在任何项目里我都坚持 4 格缩进。",
        category="preference",
        scope="global",
        authority_class="user_asserted",
        source_slice_id="slice_universal",
        project_id=None,
        suggested_action="ADD",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Universal preference")

    decision = validator.validate_claim(claim, admission)
    assert decision.action == "ADD"
    assert decision.scope == "global"


def test_rule_v3_telemetry_cannot_create_subjective_claims(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Rule-V3: Telemetry (system_observed) cannot create subjective preferences or rules."""
    slice_entity = make_test_slice(
        slice_id="slice_telem",
        content="System inferred preference",
    )
    in_memory_store.insert_raw_slice(slice_entity)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="用户偏好黑暗模式",
        category="preference",
        scope="global",
        authority_class="system_observed",
        source_slice_id="slice_telem",
        suggested_action="ADD",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Telemetry observation")

    decision = validator.validate_claim(claim, admission)
    assert decision.action == "NOOP"
    assert not decision.is_valid
    assert decision.rejection_category == "authority_violation"


def test_rule_v4_suggested_supersede_without_target_downgrades_to_add(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Rule-V4 / P0: Suggested SUPERSEDE without active target must NOT false-SUPERSEDE."""
    slice_entity = make_test_slice(
        slice_id="slice_lg",
        content="我的主显示器换成了 4K 144Hz 的 LG 27GP95R。",
    )
    in_memory_store.insert_raw_slice(slice_entity)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="我的主显示器换成了 4K 144Hz 的 LG 27GP95R。",
        category="fact",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_lg",
        suggested_action="SUPERSEDE",
        target_superseded_id="mem_nonexistent_display",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Valid fact")

    decision = validator.validate_claim(claim, admission)
    assert decision.action == "ADD"
    assert decision.target_memory_id is None
    assert decision.proof_delta == 1


def test_rule_v4_weak_contradiction_prefers_ambiguous(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Rule-V4 / P0: Weak contradiction against existing memory must prefer AMBIGUOUS."""
    slice_base = make_test_slice(
        slice_id="slice_base_indent",
        occurred_at="2025-01-01T00:00:00+00:00",
        content="代码缩进坚持 4 格",
    )
    in_memory_store.insert_raw_slice(slice_base)
    existing_mem = SemanticMemoryEntity(
        memory_id="mem_pref_indent_4",
        category="preference",
        statement="代码缩进坚持 4 格",
        authority_class="user_asserted",
        scope="global",
        valid_from="2025-01-01T00:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_base_indent",
    )
    in_memory_store.insert_semantic_memory(existing_mem)

    slice_new = make_test_slice(
        slice_id="slice_tab",
        content="偶尔在单文件临时脚本里用 Tab 制表符缩进其实也挺省事的。",
    )
    in_memory_store.insert_raw_slice(slice_new)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="偶尔在单文件临时脚本里用 Tab 制表符缩进其实也挺省事的。",
        category="preference",
        scope="global",
        authority_class="user_asserted",
        source_slice_id="slice_tab",
        suggested_action="SUPERSEDE",
        target_superseded_id="mem_pref_indent_4",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Tentative preference")

    decision = validator.validate_claim(claim, admission)
    assert decision.action == "AMBIGUOUS"
    assert decision.target_memory_id == "mem_pref_indent_4"
    assert decision.proof_delta == 0


def test_rule_v5_fingerprint_collision_degrades_to_noop(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Rule-V5: Replay or same-episode repetition fingerprint collision must become NOOP."""
    slice_base = make_test_slice(
        slice_id="slice_pyside_base",
        content="项目用 PySide6 作为表现层",
    )
    in_memory_store.insert_raw_slice(slice_base)
    existing_mem = SemanticMemoryEntity(
        memory_id="mem_fact_gui_pyside",
        category="fact",
        statement="项目用 PySide6 作为表现层",
        authority_class="user_asserted",
        scope="project",
        project_id="co-evolving-companion",
        valid_from="2026-10-18T12:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_pyside_base",
    )
    in_memory_store.insert_semantic_memory(existing_mem)

    # Pre-record reinforcement for episode ep_pyside_work
    fp = compute_independence_fingerprint(
        statement="项目用 PySide6 作为表现层",
        episode_id="ep_pyside_work",
    )
    in_memory_store.connection.execute(
        """
        INSERT INTO evidence_reinforcements (
            reinforcement_id, memory_id, slice_id, independence_fingerprint, occurred_at
        ) VALUES (?, ?, ?, ?, ?);
        """,
        ("reinf_01", "mem_fact_gui_pyside", "slice_pyside_base", fp, "2026-10-18T12:00:00+00:00"),
    )

    # User repeats in same episode ep_pyside_work on 2026-10-18
    slice_repeat = make_test_slice(
        slice_id="slice_pyside_repeat",
        occurred_at="2026-10-18T12:10:00+00:00",
        content="项目用 PySide6 作为表现层",
    )
    in_memory_store.insert_raw_slice(slice_repeat)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="项目用 PySide6 作为表现层",
        category="fact",
        scope="project",
        authority_class="user_asserted",
        source_slice_id="slice_pyside_repeat",
        suggested_action="REINFORCE",
        target_superseded_id="mem_fact_gui_pyside",
        temporal_anchor="2026-10-18T12:10:00+00:00",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Repeat assertion")

    decision = validator.validate_claim(
        claim,
        admission,
        context={"episode_id": "ep_pyside_work"},
    )
    assert decision.action == "NOOP"
    assert decision.proof_delta == 0
    assert decision.target_memory_id == "mem_fact_gui_pyside"


def test_rule_v5_new_episode_reinforces_successfully(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Rule-V5: Cross-episode new evidence generates new fingerprint and REINFORCE."""
    slice_base = make_test_slice(
        slice_id="slice_pyside_base2",
        content="项目用 PySide6 作为表现层",
    )
    in_memory_store.insert_raw_slice(slice_base)
    existing_mem = SemanticMemoryEntity(
        memory_id="mem_fact_gui_pyside2",
        category="fact",
        statement="项目用 PySide6 作为表现层",
        authority_class="user_asserted",
        scope="project",
        project_id="co-evolving-companion",
        valid_from="2026-10-18T12:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_pyside_base2",
    )
    in_memory_store.insert_semantic_memory(existing_mem)

    # Pre-record reinforcement for episode ep_pyside_work
    fp = compute_independence_fingerprint(
        statement="项目用 PySide6 作为表现层",
        episode_id="ep_pyside_work",
    )
    in_memory_store.connection.execute(
        """
        INSERT INTO evidence_reinforcements (
            reinforcement_id, memory_id, slice_id, independence_fingerprint, occurred_at
        ) VALUES (?, ?, ?, ?, ?);
        """,
        ("reinf_02", "mem_fact_gui_pyside2", "slice_pyside_base2", fp, "2026-10-18T12:00:00+00:00"),
    )

    # New slice in new episode 2 months later
    slice_reaf = make_test_slice(
        slice_id="slice_pyside_reaf",
        occurred_at="2026-12-17T12:00:00+00:00",
        content="项目用 PySide6 作为表现层",
    )
    in_memory_store.insert_raw_slice(slice_reaf)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="项目用 PySide6 作为表现层",
        category="fact",
        scope="project",
        authority_class="user_asserted",
        source_slice_id="slice_pyside_reaf",
        suggested_action="REINFORCE",
        target_superseded_id="mem_fact_gui_pyside2",
        temporal_anchor="2026-12-17T12:00:00+00:00",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Reaffirmation")

    decision = validator.validate_claim(
        claim,
        admission,
        context={"episode_id": "ep_months_later_review"},
    )
    assert decision.action == "REINFORCE"
    assert decision.proof_delta == 1
    assert decision.target_memory_id == "mem_fact_gui_pyside2"
    assert decision.independence_fingerprint is not None
    assert decision.independence_fingerprint != fp


def test_rule_v6_privacy_pending_gate_blocks_reconciliation(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Rule-V6: Privacy pending status blocks reconciliation completely."""
    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="敏感个人信息",
        category="fact",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_privacy",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Sensitive fact")

    decision = validator.validate_claim(
        claim,
        admission,
        context={"needs_privacy_redaction": True},
    )
    assert decision.action == "NOOP"
    assert not decision.is_valid
    assert decision.rejection_category == "privacy_pending"
    assert decision.proof_delta == 0


def test_echo_guard_pure_echo_results_in_noop(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Pure assistant echo acknowledgement produces NOOP with proof_delta=0."""
    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement="偏好深色主题",
        category="preference",
        scope="global",
        authority_class="user_asserted",
        source_slice_id="slice_echo",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Echo acknowledgement")
    echo_result = EchoGuardResult(
        has_echo_context=True,
        is_pure_echo=True,
        delta_text=None,
        overlap_ratio=1.0,
        has_contrast_marker=False,
        rationale="Pure echo parroting without user delta",
    )

    decision = validator.validate_claim(
        claim,
        admission,
        echo_result=echo_result,
    )
    assert decision.action == "NOOP"
    assert decision.proof_delta == 0


def test_independence_hash_same_episode_across_utc_midnight(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Same episode + same normalized content + different timestamps/days -> same hash, NOOP."""
    statement = "主显示器换成了 4K 显示器"
    ep_id = "ep_cross_midnight"

    # Compute hash on day 1 vs day 2 (crossing UTC midnight)
    hash_day1 = compute_independence_fingerprint(
        statement, episode_id=ep_id, source_day_utc="2026-10-18"
    )
    hash_day2 = compute_independence_fingerprint(
        statement, episode_id=ep_id, source_day_utc="2026-10-19"
    )
    canonical_hash = compute_independence_hash(statement, episode_id=ep_id)

    # Must be 100% identical regardless of timestamp or day
    assert hash_day1 == hash_day2 == canonical_hash

    # Seed base slice & memory at 23:55 UTC on 2026-10-18
    slice_day1 = make_test_slice(
        slice_id="slice_mid_01",
        occurred_at="2026-10-18T23:55:00+00:00",
        content=statement,
    )
    in_memory_store.insert_raw_slice(slice_day1)
    mem = SemanticMemoryEntity(
        memory_id="mem_mid_01",
        category="fact",
        statement=statement,
        authority_class="user_asserted",
        scope="unresolved",
        valid_from="2026-10-18T23:55:00+00:00",
        validity_status="active",
        source_slice_id="slice_mid_01",
    )
    in_memory_store.insert_semantic_memory(mem)

    # Record first reinforcement in ep_cross_midnight
    in_memory_store.connection.execute(
        """
        INSERT INTO evidence_reinforcements (
            reinforcement_id, memory_id, slice_id, independence_fingerprint, occurred_at
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (
            "reinf_mid_01",
            "mem_mid_01",
            "slice_mid_01",
            canonical_hash,
            "2026-10-18T23:55:00+00:00",
        ),
    )

    # Second mention at 00:05 UTC on next day (2026-10-19) in SAME episode
    slice_day2 = make_test_slice(
        slice_id="slice_mid_02",
        occurred_at="2026-10-19T00:05:00+00:00",
        content=statement,
    )
    in_memory_store.insert_raw_slice(slice_day2)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement=statement,
        category="fact",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_mid_02",
        suggested_action="REINFORCE",
        target_superseded_id="mem_mid_01",
        temporal_anchor="2026-10-19T00:05:00+00:00",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Next-day mention in same episode")

    decision = validator.validate_claim(
        claim,
        admission,
        context={"episode_id": ep_id},
    )

    # Same episode duplicate must be NOOP with proof_delta 0!
    assert decision.action == "NOOP"
    assert decision.proof_delta == 0
    assert decision.target_memory_id == "mem_mid_01"


def test_independence_hash_different_episodes_reinforce(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Different episode + same normalized content -> different hash, may REINFORCE."""
    statement = "主显示器换成了 4K 显示器"
    hash_ep1 = compute_independence_hash(statement, episode_id="ep_session_01")
    hash_ep2 = compute_independence_hash(statement, episode_id="ep_session_02")

    # Cross-episode hashes must be distinct
    assert hash_ep1 != hash_ep2

    slice_ep1 = make_test_slice(
        slice_id="slice_cross_01",
        occurred_at="2026-10-18T10:00:00+00:00",
        content=statement,
    )
    in_memory_store.insert_raw_slice(slice_ep1)
    mem = SemanticMemoryEntity(
        memory_id="mem_cross_01",
        category="fact",
        statement=statement,
        authority_class="user_asserted",
        scope="unresolved",
        valid_from="2026-10-18T10:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_cross_01",
    )
    in_memory_store.insert_semantic_memory(mem)
    in_memory_store.connection.execute(
        """
        INSERT INTO evidence_reinforcements (
            reinforcement_id, memory_id, slice_id, independence_fingerprint, occurred_at
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (
            "reinf_cross_01",
            "mem_cross_01",
            "slice_cross_01",
            hash_ep1,
            "2026-10-18T10:00:00+00:00",
        ),
    )

    # In ep_session_02:
    slice_ep2 = make_test_slice(
        slice_id="slice_cross_02",
        occurred_at="2026-10-19T10:00:00+00:00",
        content=statement,
    )
    in_memory_store.insert_raw_slice(slice_ep2)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement=statement,
        category="fact",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_cross_02",
        suggested_action="REINFORCE",
        target_superseded_id="mem_cross_01",
        temporal_anchor="2026-10-19T10:00:00+00:00",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Independent episode mention")

    decision = validator.validate_claim(
        claim,
        admission,
        context={"episode_id": "ep_session_02"},
    )
    assert decision.action == "REINFORCE"
    assert decision.proof_delta == 1
    assert decision.independence_fingerprint == hash_ep2


def test_independence_hash_normalization_equivalent_wording(
    in_memory_store: ChronicleStoreV2,
) -> None:
    """Same episode + normalization-equivalent wording -> same hash, second evidence NOOP."""
    wording_raw = "顺便说下，项目用 PySide6 作为表现层。"
    wording_clean = "项目用 PySide6 作为表现层"

    assert normalize_content(wording_raw) == normalize_content(wording_clean)

    hash_raw = compute_independence_hash(wording_raw, episode_id="ep_norm_01")
    hash_clean = compute_independence_hash(wording_clean, episode_id="ep_norm_01")
    assert hash_raw == hash_clean

    slice_clean = make_test_slice(
        slice_id="slice_norm_01",
        content=wording_clean,
    )
    in_memory_store.insert_raw_slice(slice_clean)
    mem = SemanticMemoryEntity(
        memory_id="mem_norm_01",
        category="fact",
        statement=wording_clean,
        authority_class="user_asserted",
        scope="project",
        project_id="co-evolving-companion",
        valid_from="2026-10-18T12:00:00+00:00",
        validity_status="active",
        source_slice_id="slice_norm_01",
    )
    in_memory_store.insert_semantic_memory(mem)
    in_memory_store.connection.execute(
        """
        INSERT INTO evidence_reinforcements (
            reinforcement_id, memory_id, slice_id, independence_fingerprint, occurred_at
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (
            "reinf_norm_01",
            "mem_norm_01",
            "slice_norm_01",
            hash_clean,
            "2026-10-18T12:00:00+00:00",
        ),
    )

    slice_filler = make_test_slice(
        slice_id="slice_norm_02",
        occurred_at="2026-10-18T12:05:00+00:00",
        content=wording_raw,
    )
    in_memory_store.insert_raw_slice(slice_filler)

    validator = ReconciliationValidator(in_memory_store)
    claim = CandidateSemanticMemory(
        statement=wording_raw,
        category="fact",
        scope="project",
        authority_class="user_asserted",
        source_slice_id="slice_norm_02",
        suggested_action="REINFORCE",
        target_superseded_id="mem_norm_01",
        temporal_anchor="2026-10-18T12:05:00+00:00",
    )
    admission = AdmissionDecision(decision="ADMIT", rationale="Filler wording duplicate")

    decision = validator.validate_claim(
        claim,
        admission,
        context={"episode_id": "ep_norm_01"},
    )
    assert decision.action == "NOOP"
    assert decision.proof_delta == 0
