"""Proposal contracts and immutable data structures for Memory V2.1 Lane C.

Read-only DTOs representing Phase-1 admission decisions and candidate semantic claims.
Strictly isolated from semantic DB mutation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from src.memory.v2.entities import AuthorityClass, Scope, SemanticCategory

AdmissionDecisionValue = Literal["ADMIT", "NOOP_LONG_TERM", "DEFER"]
SuggestedAction = Literal["ADD", "SUPERSEDE", "REINFORCE", "AMBIGUOUS", "NOOP"]


@dataclass(frozen=True)
class AdmissionDecision:
    """Read-only result of the Admission Gate."""

    decision: AdmissionDecisionValue
    rationale: str
    rejection_category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateSemanticMemory:
    """Read-only candidate semantic proposition extracted from raw evidence."""

    statement: str
    category: SemanticCategory
    scope: Scope
    authority_class: AuthorityClass
    source_slice_id: str | None = None
    source_event_id: str | None = None
    project_id: str | None = None
    confidence_class: Literal["tentative", "grounded"] = "tentative"
    temporal_anchor: str = ""
    suggested_action: SuggestedAction = "ADD"
    target_superseded_id: str | None = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConsolidationProposal:
    """Full read-only proposal produced in Phase 1 before deterministic validation."""

    proposal_id: str
    admission: AdmissionDecision
    proposed_claims: list[CandidateSemanticMemory]
    source_id: str
    source_type: Literal["slice", "event"]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
