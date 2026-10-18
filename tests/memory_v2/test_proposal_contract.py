"""Tests for Proposal Contracts and Epistemic Invariants (Lane C).

Validates:
- Immutability of proposal dataclasses
- Complete to_dict() schema serialization
- S-01 Invariant: prevention of psychological hypothesis / persona scores
- Suggested action remains untrusted hint (no write authority)
- Telemetry event skeletons cannot produce subjective claims
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from src.memory.v2.admission import AdmissionFilter
from src.memory.v2.candidate_extraction import CandidateExtractor
from src.memory.v2.entities import EventSkeletonEntity, RawSliceEntity
from src.memory.v2.proposals import (
    AdmissionDecision,
    CandidateSemanticMemory,
    ConsolidationProposal,
)


def test_proposal_immutability() -> None:
    claim = CandidateSemanticMemory(
        statement="PowerShell 7 是主要终端",
        category="preference",
        scope="global",
        authority_class="user_asserted",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        # Mutating frozen dataclass must raise FrozenInstanceError
        claim.statement = "CMD"  # type: ignore[misc]

    decision = AdmissionDecision(decision="ADMIT", rationale="Valid preference")
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.decision = "NOOP_LONG_TERM"  # type: ignore[misc]

    prop = ConsolidationProposal(
        proposal_id="prop_001",
        admission=decision,
        proposed_claims=[claim],
        source_id="slice_001",
        source_type="slice",
        created_at="2026-10-18T12:00:00+00:00",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        prop.proposal_id = "prop_002"  # type: ignore[misc]


def test_proposal_schema_to_dict_fidelity() -> None:
    claim = CandidateSemanticMemory(
        statement="主显示器为 LG 27GP95R",
        category="fact",
        scope="unresolved",
        authority_class="user_asserted",
        source_slice_id="slice_123",
        suggested_action="ADD",
        rationale="Hardware fact",
    )
    d = claim.to_dict()
    assert d["statement"] == "主显示器为 LG 27GP95R"
    assert d["category"] == "fact"
    assert d["scope"] == "unresolved"
    assert d["authority_class"] == "user_asserted"
    assert d["suggested_action"] == "ADD"

    prop = ConsolidationProposal(
        proposal_id="prop_123",
        admission=AdmissionDecision(decision="ADMIT", rationale="Durable fact"),
        proposed_claims=[claim],
        source_id="slice_123",
        source_type="slice",
        created_at="2026-10-18T12:00:00+00:00",
    )
    p_dict = prop.to_dict()
    assert p_dict["proposal_id"] == "prop_123"
    assert p_dict["admission"]["decision"] == "ADMIT"
    assert len(p_dict["proposed_claims"]) == 1
    assert p_dict["proposed_claims"][0]["statement"] == "主显示器为 LG 27GP95R"


def test_s01_forbidden_psychological_fields_rejected() -> None:
    """S-01: Invariant check against psychological hypothesis or persona scoring."""

    class BadProvider:
        def generate_proposal(
            self,
            slice_entity: RawSliceEntity,
            admission: AdmissionDecision,
            delta_text: str | None = None,
            context: dict[str, Any] | None = None,
        ) -> ConsolidationProposal:
            # Illegal injection of psychological hypothesis
            claim = CandidateSemanticMemory(
                statement="用户具有回避型人格",
                category="fact",
                scope="global",
                authority_class="user_asserted",
            )
            # Inject forbidden attribute into dict
            object.__setattr__(claim, "personality_score", 0.95)
            return ConsolidationProposal(
                proposal_id="prop_bad",
                admission=admission,
                proposed_claims=[claim],
                source_id=slice_entity.slice_id,
                source_type="slice",
                created_at=slice_entity.occurred_at,
            )

    extractor = CandidateExtractor(provider=BadProvider())
    s = RawSliceEntity(
        slice_id="slice_bad",
        content="今天写代码感觉心力特别交瘁，完全不想动了。",
        occurred_at="2026-10-18T12:00:00+00:00",
    )
    # The extractor's admission gate rejects this slice first (NOOP_LONG_TERM)
    prop = extractor.extract_from_slice(s)
    assert prop.admission.decision == "NOOP_LONG_TERM"
    assert len(prop.proposed_claims) == 0


def test_suggested_action_untrusted_boundary() -> None:
    """Suggested actions in proposal are strictly untrusted hints; WP-3 never commits."""
    extractor = CandidateExtractor()
    s = RawSliceEntity(
        slice_id="slice_corr",
        content="刚才我说错了，那个项目用的其实是 PySide6 不是 PyQt5。",
        occurred_at="2026-10-18T12:00:00+00:00",
    )
    context = {"target_existing_memory": "mem_fact_gui_pyqt5"}
    prop = extractor.extract_from_slice(s, context=context)

    assert prop.admission.decision == "ADMIT"
    assert len(prop.proposed_claims) == 1
    claim = prop.proposed_claims[0]
    # In Phase 1 proposal, suggested_action is a hint
    assert claim.suggested_action == "SUPERSEDE"
    assert claim.target_superseded_id == "mem_fact_gui_pyqt5"
    # But no database connection or commit was executed
    assert not hasattr(extractor, "store")


def test_telemetry_event_cannot_spawn_subjective_claims() -> None:
    """Telemetry events cannot infer subjective user emotions or produce personality candidates."""
    filter_ = AdmissionFilter()
    event = EventSkeletonEntity(
        event_id="evt_timeout_01",
        occurred_at="2026-10-18T12:00:00+00:00",
        agent_id="test_agent",
        session_id="sess_104",
        event_type="tool_timeout",
        tool_name="bash",
    )
    decision = filter_.evaluate_event(event)
    assert decision.decision == "NOOP_LONG_TERM"
    assert decision.rejection_category == "telemetry_skeleton"
