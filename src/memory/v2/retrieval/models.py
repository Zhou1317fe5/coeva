"""Strongly typed data models for Memory V2.1 Technical Retrieval Pipeline.

Authoritative mapping to:
- docs/memory-v2/retrieval/technical-retrieval-design.md (§6, §16, §17)
- docs/memory-v2/retrieval/retrieval-decision-record.md (RDR-2026-01)
- docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal

RetrievalMode = Literal[
    "NO_MEMORY_NEEDED",
    "FACT_RECALL",
    "PREFERENCE_RECALL",
    "PROJECT_HISTORY",
    "EPISODIC_HISTORY",
    "EXPLICIT_PAST_QUERY",
    "RELATIONSHIP_RULE",
    "REFLECTIVE_RECALL",
    "TASK_CONTINUITY",
    "NARRATIVE_QUERY",
]

RetrievalStatus = Literal["SUCCESS", "NO_RELEVANT_MEMORY"]

# In accordance with DM-7 / S-10: Narrative never becomes provenance evidence.
EvidenceKind = Literal["slice", "event", "episode", "insight"]


@dataclass(frozen=True)
class ProvenanceRef:
    """Strongly typed provenance reference (IMPL-2).

    Enforces DM-7 / S-10: Narrative never becomes provenance evidence.
    Allowed evidence kinds are strictly 'slice', 'event', 'episode', or 'insight'.
    Chapters may be retrieved objects, but NEVER evidence provenance.
    """

    kind: EvidenceKind
    id: str  # Source entity primary key
    role: str = "supporting"  # 'supporting' | 'counter' | 'contextual'

    def __post_init__(self) -> None:
        if self.kind not in ("slice", "event", "episode", "insight"):
            raise ValueError(
                f"Invalid provenance kind: {self.kind!r}. "
                "Narrative / chapter must never become provenance evidence (DM-7 / S-10)."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalCandidateRecord:
    """Internal canonical candidate representation extracted from storage layer."""

    candidate_id: str
    # Types: semantic_memory | episode | confirmed_insight | chapter_metadata | raw_slice
    candidate_type: str
    category: str
    statement: str
    scope: str
    project_id: str | None
    valid_from: str
    validity_status: str
    authority_class: str
    proof_count: int = 1
    needs_privacy_redaction: int = 0
    expression_policy: str = "normal"
    provenance_refs: tuple[ProvenanceRef, ...] = ()
    importance: float = 0.5


@dataclass(frozen=True)
class RetrievedCandidate:
    """Final candidate returned by Technical Retrieval to Recall Gate (Technical Design §17)."""

    candidate_id: str
    candidate_type: str
    statement: str
    provenance_refs: tuple[ProvenanceRef, ...]
    scope: str
    project_id: str | None
    valid_from: str
    validity_status: str
    authority_class: str
    proof_count: int
    lexical_score: float
    surface_score: float
    final_score: float
    why_retrieved: str
    is_ambiguous: bool
    needs_privacy_redaction: int = 0
    expression_policy: str = "normal"
    category: str = "fact"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type,
            "statement": self.statement,
            "provenance_refs": [p.to_dict() for p in self.provenance_refs],
            "scope": self.scope,
            "project_id": self.project_id,
            "valid_from": self.valid_from,
            "validity_status": self.validity_status,
            "authority_class": self.authority_class,
            "proof_count": self.proof_count,
            "lexical_score": self.lexical_score,
            "surface_score": self.surface_score,
            "final_score": self.final_score,
            "why_retrieved": self.why_retrieved,
            "is_ambiguous": self.is_ambiguous,
            "needs_privacy_redaction": self.needs_privacy_redaction,
            "expression_policy": self.expression_policy,
            "category": self.category,
        }


@dataclass(frozen=True)
class RetrievalQueryContext:
    """Structured input context for Technical Retrieval Pipeline (Technical Design §6)."""

    query_text: str
    current_project_id: str | None = None
    current_session_id: str = ""
    current_episode_id: str | None = None
    sanctuary_active: bool = False
    requested_mode_hint: str | None = None
    explicit_historical_intent: bool = False
    temporal_constraint_date: date | None = None
    entity_hints: tuple[str, ...] = ()
    now: datetime | None = None


@dataclass(frozen=True)
class RetrievalResult:
    """Output contract of Technical Retrieval Pipeline."""

    status: str  # "SUCCESS" | "NO_RELEVANT_MEMORY"
    candidates: tuple[RetrievedCandidate, ...]
    query_context: RetrievalQueryContext
    retrieval_mode: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_silent(self) -> bool:
        return self.status == "NO_RELEVANT_MEMORY" or len(self.candidates) == 0

    def candidate_ids(self) -> list[str]:
        return [c.candidate_id for c in self.candidates]
