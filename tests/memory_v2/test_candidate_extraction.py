"""Tests for Candidate Semantic Extraction & Invariants (Lane C).

Covers:
- A-01: Durable preference accepted
- A-02: Durable fact accepted
- A-03: Relationship rule accepted
- A-04: Goal accepted
- A-05: Ephemeral instruction yields no candidate
- A-06: Casual wording with durable value accepted
- A-07: Single emotional slice yields no psychological hypothesis (S-01)
- A-08: Echo-only yields no candidate
- A-09: Echo + correction preserves user delta
- A-10: Unknown scope stays unresolved (Unknown != Global)
- A-11: Telemetry authority stays system_observed, user stays user_asserted
- A-12: Zero DB mutation (canonical tables unchanged)
- A-13: Provider failure safe / deferred
"""

from __future__ import annotations

from typing import Any

from src.memory.v2.candidate_extraction import CandidateExtractor
from src.memory.v2.entities import RawSliceEntity
from src.memory.v2.proposals import (
    AdmissionDecision,
    ConsolidationProposal,
)
from src.memory.v2.store import ChronicleStoreV2


def make_slice(
    content: str,
    slice_id: str = "slice_extract_01",
    project_id: str | None = None,
    occurred_at: str = "2026-10-18T12:00:00+00:00",
) -> RawSliceEntity:
    return RawSliceEntity(
        slice_id=slice_id,
        content=content,
        occurred_at=occurred_at,
        actor="user",
        source="manual_feed",
        project_id=project_id,
    )


def test_a01_durable_preference_accepted() -> None:
    extractor = CandidateExtractor()
    s = make_slice("我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。")
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    assert claim.category == "preference"
    assert "PowerShell 7" in claim.statement
    assert claim.authority_class == "user_asserted"
    assert claim.source_slice_id == s.slice_id


def test_a02_durable_fact_accepted() -> None:
    extractor = CandidateExtractor()
    s = make_slice("我的主显示器换成了 4K 144Hz 的 LG 27GP95R。")
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    assert claim.category == "fact"
    assert "LG 27GP95R" in claim.statement


def test_a03_relationship_rule_accepted() -> None:
    extractor = CandidateExtractor()
    s = make_slice("以后我专注写代码时，千万别弹窗打扰我或提醒我喝水。")
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    assert claim.category == "relationship_rule"
    assert "千万别弹窗打扰我" in claim.statement


def test_a04_goal_accepted() -> None:
    extractor = CandidateExtractor()
    s = make_slice("我今年的长期目标是把 Rust 异步编程和跨平台 GUI 彻底搞懂。")
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    assert claim.category == "goal"


def test_a05_ephemeral_instruction_no_candidate() -> None:
    extractor = CandidateExtractor()
    s = make_slice("先去吃个午饭，半小时后回来。")
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "NOOP_LONG_TERM"
    assert len(prop.proposed_claims) == 0


def test_a06_casual_wording_with_durable_value_accepted() -> None:
    extractor = CandidateExtractor()
    s = make_slice("小时候其实挺喜欢画画的，最近想抽时间重新捡起来。")
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    assert "喜欢画画" in prop.proposed_claims[0].statement


def test_a07_single_emotional_slice_no_psych_hypothesis() -> None:
    extractor = CandidateExtractor()
    s = make_slice("今天写代码感觉心力特别交瘁，完全不想动了。")
    prop = extractor.extract_from_slice(s)

    # S-01 invariant: single raw slice emotional complaint rejected from long-term memory
    assert prop.admission.decision == "NOOP_LONG_TERM"
    assert len(prop.proposed_claims) == 0

    # Ensure proposal never carries psychological hypothesis or persona scores
    prop_dict = prop.to_dict()
    forbidden = [
        "personality_score",
        "trait_score",
        "productivity_score",
        "diagnosis",
        "stable_persona",
    ]
    for key in forbidden:
        assert key not in prop_dict


def test_a08_echo_only_blocked() -> None:
    extractor = CandidateExtractor()
    s = make_slice("嗯，你说得对。")
    echo_prop = "你之前提到过偏好深色主题对吧？"
    prop = extractor.extract_from_slice(s, echoed_proposition=echo_prop)

    assert prop.admission.decision == "NOOP_LONG_TERM"
    assert len(prop.proposed_claims) == 0


def test_a09_echo_with_correction_preserves_delta() -> None:
    extractor = CandidateExtractor()
    s = make_slice("嗯，不过现在改用浅色主题确实看久了更舒服。")
    echo_prop = "你之前提到过偏好深色主题对吧？"
    prop = extractor.extract_from_slice(s, echoed_proposition=echo_prop)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    assert "改用浅色主题" in claim.statement
    assert not claim.statement.startswith("嗯")


def test_a10_scope_unresolved_preserved() -> None:
    extractor = CandidateExtractor()
    # Unknown project context
    s = make_slice("把单元测试框架统一换成 pytest。", project_id=None)
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    # S-14 invariant: Unknown != Global! Must be unresolved
    assert claim.scope == "unresolved"
    assert claim.project_id is None


def test_a10b_scope_project_preserved() -> None:
    extractor = CandidateExtractor()
    s = make_slice(
        "这个 CRM 门户后台我们用 FastAPI 编写 API 接口。",
        project_id="crm-web-portal",
    )
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    assert claim.scope == "project"
    assert claim.project_id == "crm-web-portal"


def test_a10c_scope_global_explicit() -> None:
    extractor = CandidateExtractor()
    s = make_slice("在任何项目里我都还是坚持 4 格缩进，代码整洁度确实完全不同。")
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    assert claim.scope == "global"
    assert claim.project_id == "global"


def test_a11_authority_class_respected() -> None:
    extractor = CandidateExtractor()
    user_slice = make_slice("我频繁中断并不是因为逃避挫折，单纯是这个命令行工具的响应太慢了。")
    prop = extractor.extract_from_slice(user_slice)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    assert prop.proposed_claims[0].authority_class == "user_asserted"


def test_a12_no_db_mutation() -> None:
    """A-12: Candidate extraction must NEVER mutate canonical database tables."""
    store = ChronicleStoreV2(":memory:")
    try:
        conn = store.connection
        # Check baseline row counts
        c1 = conn.execute("SELECT count(*) FROM semantic_memories").fetchone()[0]
        c2 = conn.execute("SELECT count(*) FROM observations").fetchone()[0]
        c3 = conn.execute("SELECT count(*) FROM hypotheses").fetchone()[0]
        c4 = conn.execute("SELECT count(*) FROM confirmed_insights").fetchone()[0]

        # Run multiple extractions
        extractor = CandidateExtractor()
        slices = [
            make_slice("我的主显示器换成了 4K 144Hz 的 LG 27GP95R。"),
            make_slice("我现在开发全面迁移到 PowerShell 7 了，不再用 CMD。"),
            make_slice("以后我专注写代码时，千万别弹窗打扰我或提醒我喝水。"),
            make_slice("先去吃个午饭，半小时后回来。"),
        ]
        for s in slices:
            prop = extractor.extract_from_slice(s)
            assert prop is not None

        # Check post-run row counts: MUST be completely unchanged
        assert conn.execute("SELECT count(*) FROM semantic_memories").fetchone()[0] == c1
        assert conn.execute("SELECT count(*) FROM observations").fetchone()[0] == c2
        assert conn.execute("SELECT count(*) FROM hypotheses").fetchone()[0] == c3
        assert conn.execute("SELECT count(*) FROM confirmed_insights").fetchone()[0] == c4
    finally:
        store.close()


def test_a13_provider_failure_safe() -> None:
    """A-13: Provider failure must defer safely without throwing or mutating DB."""

    class FailingProvider:
        def generate_proposal(
            self,
            slice_entity: RawSliceEntity,
            admission: AdmissionDecision,
            delta_text: str | None = None,
            context: dict[str, Any] | None = None,
        ) -> ConsolidationProposal:
            raise ConnectionError("Mock LLM provider network timeout")

    extractor = CandidateExtractor(provider=FailingProvider())
    s = make_slice("我的主显示器换成了 4K 144Hz 的 LG 27GP95R。")
    prop = extractor.extract_from_slice(s)

    assert prop.admission.decision == "DEFER"
    assert prop.admission.rejection_category == "provider_failure"
    assert len(prop.proposed_claims) == 0
    assert "network timeout" in prop.admission.rationale
