"""Strongly typed Python entities and immutable dataclasses for Memory V2.1.

Strictly mapped to docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md
Contains:
- Exactly 20 Canonical Memory Entities
- 4 Technical Operational / Migration Metadata Entities (isolated from memory truth)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

# ============================================================================
# Enum Types & Constraint Literals
# ============================================================================

Scope = Literal["global", "project", "unresolved"]
RawSliceSource = Literal["manual_feed", "bubble_reply"]
RetentionClass = Literal["transient", "durable"]
EpisodeStatus = Literal["open", "closed", "archived"]
CurationSource = Literal["system", "user"]

SemanticCategory = Literal["preference", "fact", "relationship_rule", "goal"]
AuthorityClass = Literal["user_asserted", "system_observed", "user_confirmed"]
ValidityStatus = Literal["active", "superseded", "invalidated", "ambiguous"]
ExpressionPolicy = Literal["normal", "muted", "do_not_mention"]

ObservationStatus = Literal["active", "retracted"]
ObservationRole = Literal["supporting", "counter"]

HypothesisConfidence = Literal["tentative", "grounded"]
HypothesisStatus = Literal["candidate", "rejected", "revalidation_required", "retracted"]
HypothesisObservationRole = Literal["supporting", "counter", "contextual"]

UserCalibrationAction = Literal["yes", "partly", "no"]
ConfirmedInsightStatus = Literal["confirmed", "superseded", "revalidation_required", "retracted"]


# ============================================================================
# 1. Core Evidence & Experience Container Entities (5 Entities)
# ============================================================================


@dataclass(frozen=True)
class RawSliceEntity:
    """Canonical User Raw Input Evidence (Entity 1)."""

    slice_id: str
    occurred_at: str
    content: str
    actor: str = "user"
    source: RawSliceSource = "manual_feed"
    scope: Scope = "unresolved"
    project_id: str | None = None
    ingestion_dedup_key: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventSkeletonEntity:
    """External Agent Telemetry Skeleton (Entity 2)."""

    event_id: str
    occurred_at: str
    agent_id: str
    session_id: str
    event_type: str
    tool_name: str = ""
    error_category: str = ""
    retention_class: RetentionClass = "transient"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EpisodeEntity:
    """Experience Grouping Container (Entity 3, Non-Evidence)."""

    episode_id: str
    scope: Scope
    started_at: str
    title_hint: str
    status: EpisodeStatus = "open"
    project_id: str | None = None
    closed_at: str | None = None
    summary: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EpisodeSliceLinkEntity:
    """Typed Relation: Episode <-> Raw Slice (Entity 4)."""

    episode_id: str
    slice_id: str
    curation_source: CurationSource = "system"
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EpisodeEventLinkEntity:
    """Typed Relation: Episode <-> Event Skeleton (Entity 5)."""

    episode_id: str
    event_id: str
    curation_source: CurationSource = "system"
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# 2. Derived Facts & Understanding Belief Entities (7 Entities)
# ============================================================================


@dataclass(frozen=True)
class SemanticMemoryEntity:
    """Atomic Semantic Fact, Preference, Rule (Entity 6)."""

    memory_id: str
    category: SemanticCategory
    statement: str
    authority_class: AuthorityClass
    scope: Scope
    valid_from: str
    validity_status: ValidityStatus
    project_id: str | None = None
    source_slice_id: str | None = None
    source_event_id: str | None = None
    source_episode_id: str | None = None
    invalidated_at: str | None = None
    superseded_by: str | None = None
    expression_policy: ExpressionPolicy = "normal"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceReinforcementEntity:
    """Independent Evidence Ledger (Entity 7)."""

    reinforcement_id: str
    memory_id: str
    independence_fingerprint: str
    occurred_at: str
    slice_id: str | None = None
    event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationEntity:
    """Aggregated Objective Belief (Entity 8)."""

    observation_id: str
    scope: Scope
    statement: str
    proof_count: int = 1
    status: ObservationStatus = "active"
    project_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationSliceLinkEntity:
    """Typed Relation: Observation <-> Raw Slice (Entity 9)."""

    observation_id: str
    slice_id: str
    role: ObservationRole = "supporting"
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationEventLinkEntity:
    """Typed Relation: Observation <-> Event Skeleton (Entity 10, Retention Pinned)."""

    observation_id: str
    event_id: str
    role: ObservationRole = "supporting"
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationMemoryLinkEntity:
    """Typed Relation: Observation <-> Semantic Memory (Entity 11)."""

    observation_id: str
    memory_id: str
    role: ObservationRole = "supporting"
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationEpisodeLinkEntity:
    """Typed Relation: Observation <-> Episode Contextual Scope (Entity 12)."""

    observation_id: str
    episode_id: str
    role: Literal["contextual_scope"] = "contextual_scope"
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# 3. Hypotheses & Human Calibration Consensus Entities (4 Entities)
# ============================================================================


@dataclass(frozen=True)
class HypothesisEntity:
    """Candidate Development Hypothesis (Entity 13)."""

    hypothesis_id: str
    statement: str
    lenses: str
    confidence_class: HypothesisConfidence
    status: HypothesisStatus
    last_calibrated_at: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HypothesisObservationLinkEntity:
    """Typed Relation: Hypothesis <-> Observation (Entity 14)."""

    hypothesis_id: str
    observation_id: str
    role: HypothesisObservationRole = "supporting"
    is_primary: int = 0
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationEventEntity:
    """Immutable Human Calibration Action Log (Entity 15)."""

    calibration_id: str
    hypothesis_id: str
    user_action: UserCalibrationAction
    calibrated_at: str
    user_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfirmedInsightEntity:
    """Confirmed Self Model Consensus Entity (Entity 16)."""

    insight_id: str
    source_hypothesis_id: str
    source_calibration_id: str
    statement: str
    valid_from: str
    status: ConfirmedInsightStatus = "confirmed"
    invalidated_at: str | None = None
    superseded_by: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# 4. Narrative Metadata & Cross-Domain Links (4 Entities)
# ============================================================================


@dataclass(frozen=True)
class ChapterMetadataEntity:
    """Growth Chapter Index & Privacy Redaction Tracker (Entity 17)."""

    chapter_id: str
    title: str
    file_path: str
    time_span_start: str
    time_span_end: str
    needs_privacy_redaction: int = 0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChapterSliceLinkEntity:
    """Typed Relation: Chapter <-> Raw Slice (Entity 18)."""

    chapter_id: str
    slice_id: str
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChapterEpisodeLinkEntity:
    """Typed Relation: Chapter <-> Episode (Entity 19)."""

    chapter_id: str
    episode_id: str
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChapterInsightLinkEntity:
    """Typed Relation: Chapter <-> Confirmed Insight (Entity 20)."""

    chapter_id: str
    insight_id: str
    linked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# 5. Technical Operational & Migration Metadata (Isolated from Canonical Memory)
# ============================================================================


@dataclass(frozen=True)
class SchemaMigrationRecord:
    """Technical operational migration ledger entry."""

    migration_id: str
    source_version: int
    target_version: int
    started_at: str
    status: str
    completed_at: str | None = None
    checksum: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class LegacyHypothesisAuditRecord:
    """Technical migration audit metadata for legacy V1 hypotheses."""

    hypothesis_id: str
    original_statement: str
    original_status: str
    original_lenses: str
    migrated_at: str
    original_confidence: str | None = None
    supporting_episodes_raw: str | None = None


@dataclass(frozen=True)
class ConsolidationJobRecord:
    """Operational background job queue metadata."""

    job_id: str
    source_kind: str
    source_id: str
    status: str = "pending"
    retry_count: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class BackfillProgressRecord:
    """Operational progress tracker for background backfill."""

    task_name: str
    last_processed_id: str | None = None
    processed_count: int = 0
    status: str = "idle"
    updated_at: str = ""
