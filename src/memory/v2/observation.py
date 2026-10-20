"""Observation Pipeline (WP-6): Derived belief intermediate with independent support count.
Preserves the frozen epistemic hierarchy:
- Evidence != Observation
- Observation != Hypothesis
- Hypothesis != Confirmed Insight

Enforces:
- S6-01: Single raw slice cannot create psychological/self-model observations or hypotheses.
- S6-02: Multi-source evidence aggregation with independent positive proof counting.
- S6-03: Counter/contextual evidence does NOT count towards positive proof_count.
- S6-04: Scope isolation preserved: project evidence cannot silently form global observations.
- S6-13: Event retention pinning: formal adoption by an active observation pins event skeletons.
- S6-15: Assistant echo and retrieved memory context cannot become evidence.
- S6-16: Telemetry boundary: telemetry alone cannot infer user intent/feeling/value claims.
- S6-17: Chapter isolation: narrative chapters are never used as evidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.memory.v2.echo_guard import EchoGuard
from src.memory.v2.entities import (
    ObservationEntity,
    ObservationEpisodeLinkEntity,
    ObservationEventLinkEntity,
    ObservationMemoryLinkEntity,
    ObservationRole,
    ObservationSliceLinkEntity,
    ObservationStatus,
    Scope,
)
from src.memory.v2.provenance import ProvenanceRepository

if TYPE_CHECKING:
    from src.memory.v2.store import ChronicleStoreV2


class ObservationValidationError(ValueError):
    """Base error for invalid observation creation or evidence linking."""

    pass


class ScopeIsolationError(ObservationValidationError):
    """Raised when project evidence leaks into global observation or across projects (S6-04)."""

    pass


class TelemetryAuthorityError(ObservationValidationError):
    """Raised when telemetry alone attempts to support subjective intent/feeling claims (S6-16)."""

    pass


class SingleSlicePsychError(ObservationValidationError):
    """Raised when an isolated single raw slice attempts to form psych/self-model belief (S6-01)."""

    pass


class EchoEvidenceError(ObservationValidationError):
    """Raised when assistant echo is presented as positive proof (S6-15)."""

    pass


@dataclass
class ObservationCandidate:
    """Pre-commit candidate structure for an aggregated objective belief intermediate."""

    statement: str
    scope: Scope = "global"
    project_id: str | None = None
    supporting_slices: list[str] = field(default_factory=list)
    counter_slices: list[str] = field(default_factory=list)
    supporting_events: list[str] = field(default_factory=list)
    counter_events: list[str] = field(default_factory=list)
    supporting_memories: list[str] = field(default_factory=list)
    counter_memories: list[str] = field(default_factory=list)
    contextual_episodes: list[str] = field(default_factory=list)
    is_subjective_claim: bool = False

    @property
    def positive_proof_count(self) -> int:
        """Count independent positive supports only.

        Counter evidence and contextual episodes strictly do NOT count.
        """
        unique_slices = len(set(self.supporting_slices))
        unique_events = len(set(self.supporting_events))
        unique_memories = len(set(self.supporting_memories))
        return unique_slices + unique_events + unique_memories

    @property
    def has_counter_evidence(self) -> bool:
        """Return True if any counter evidence is linked."""
        return bool(self.counter_slices or self.counter_events or self.counter_memories)

    @property
    def total_evidence_count(self) -> int:
        """Total distinct evidence items (supporting + counter)."""
        return (
            len(set(self.supporting_slices))
            + len(set(self.counter_slices))
            + len(set(self.supporting_events))
            + len(set(self.counter_events))
            + len(set(self.supporting_memories))
            + len(set(self.counter_memories))
        )


class ObservationBuilder:
    """Fluent builder for constructing ObservationCandidate instances."""

    def __init__(self, statement: str = "") -> None:
        self._candidate = ObservationCandidate(statement=statement)

    def with_statement(self, statement: str) -> ObservationBuilder:
        self._candidate.statement = statement
        return self

    def with_scope(self, scope: Scope, project_id: str | None = None) -> ObservationBuilder:
        self._candidate.scope = scope
        self._candidate.project_id = project_id
        return self

    def with_subjective_claim(self, is_subjective: bool = True) -> ObservationBuilder:
        self._candidate.is_subjective_claim = is_subjective
        return self

    def add_slice(self, slice_id: str, role: ObservationRole = "supporting") -> ObservationBuilder:
        if role == "supporting":
            if slice_id not in self._candidate.supporting_slices:
                self._candidate.supporting_slices.append(slice_id)
        else:
            if slice_id not in self._candidate.counter_slices:
                self._candidate.counter_slices.append(slice_id)
        return self

    def add_event(self, event_id: str, role: ObservationRole = "supporting") -> ObservationBuilder:
        if role == "supporting":
            if event_id not in self._candidate.supporting_events:
                self._candidate.supporting_events.append(event_id)
        else:
            if event_id not in self._candidate.counter_events:
                self._candidate.counter_events.append(event_id)
        return self

    def add_memory(
        self, memory_id: str, role: ObservationRole = "supporting"
    ) -> ObservationBuilder:
        if role == "supporting":
            if memory_id not in self._candidate.supporting_memories:
                self._candidate.supporting_memories.append(memory_id)
        else:
            if memory_id not in self._candidate.counter_memories:
                self._candidate.counter_memories.append(memory_id)
        return self

    def add_episode(self, episode_id: str) -> ObservationBuilder:
        if episode_id not in self._candidate.contextual_episodes:
            self._candidate.contextual_episodes.append(episode_id)
        return self

    def build(self) -> ObservationCandidate:
        return self._candidate


class ObservationPipeline:
    """Validates and persists derived observations with typed multi-source provenance."""

    def __init__(
        self,
        store: ChronicleStoreV2,
        *,
        echo_guard: EchoGuard | None = None,
        min_psych_proof_count: int = 2,
    ) -> None:
        self._store = store
        self._echo_guard = echo_guard or EchoGuard()
        self._min_psych_proof_count = min_psych_proof_count

    @property
    def store(self) -> ChronicleStoreV2:
        return self._store

    def validate_candidate(self, candidate: ObservationCandidate) -> None:
        """Validate candidate against frozen epistemic invariants before persistence."""
        if not candidate.statement.strip():
            raise ObservationValidationError("Observation statement cannot be empty.")

        # Invariant 1: Independent positive proof count must be at least 1
        proof_count = candidate.positive_proof_count
        if proof_count < 1:
            raise ObservationValidationError(
                f"Observation requires at least 1 independent positive support, got {proof_count}. "
                "Counter and contextual evidence cannot serve as positive proof (S6-03)."
            )

        # Invariant 2: Single-slice psych/self-model guard (S6-01)
        if candidate.is_subjective_claim and proof_count < self._min_psych_proof_count:
            raise SingleSlicePsychError(
                f"Subjective observation requires at least {self._min_psych_proof_count} "
                f"independent positive supports; single slice forbidden (S6-01)."
            )

        # Invariant 3: Telemetry authority boundary (S6-16)
        # Subjective intent/feeling/value claims MUST have user voice evidence
        if candidate.is_subjective_claim:
            has_user_voice = bool(candidate.supporting_slices or candidate.supporting_memories)
            if not has_user_voice and candidate.supporting_events:
                raise TelemetryAuthorityError(
                    "Telemetry alone cannot create subjective preference/feeling observations "
                    "(S6-16). User voice (slices or user-confirmed memories) is required."
                )

        # Invariant 4: Echo Guard (S6-15)
        # Assistant echo and retrieved memory context cannot become evidence
        for slice_id in candidate.supporting_slices:
            slice_entity = self._store.get_raw_slice(slice_id)
            if slice_entity:
                res = self._echo_guard.inspect(slice_entity.content)
                if res.is_pure_echo:
                    raise EchoEvidenceError(
                        f"Slice '{slice_id}' is pure assistant echo and cannot be evidence (S6-15)."
                    )
        # Invariant 5: Scope isolation (S6-04)
        # Project evidence cannot silently form a global observation.
        # Check scopes of all supporting evidence items.
        evidence_scopes: list[tuple[str, str | None]] = []

        for sid in candidate.supporting_slices + candidate.counter_slices:
            s_entity = self._store.get_raw_slice(sid)
            if s_entity:
                evidence_scopes.append((s_entity.scope, s_entity.project_id))

        for mid in candidate.supporting_memories + candidate.counter_memories:
            m_entity = self._store.get_semantic_memory(mid)
            if m_entity:
                evidence_scopes.append((m_entity.scope, m_entity.project_id))

        # Check for cross-project contamination or silent escalation to global
        project_ids_in_evidence = {
            pid for scp, pid in evidence_scopes if scp == "project" and pid is not None
        }

        if len(project_ids_in_evidence) > 1:
            raise ScopeIsolationError(
                f"Cross-project evidence contamination detected: {project_ids_in_evidence} (S6-04)."
            )

        if project_ids_in_evidence:
            sole_project = next(iter(project_ids_in_evidence))
            if candidate.scope == "global":
                raise ScopeIsolationError(
                    f"Project evidence ({sole_project}) cannot form global observation (S6-04)."
                )
            if candidate.scope == "project" and candidate.project_id != sole_project:
                raise ScopeIsolationError(
                    f"Evidence from '{sole_project}' cannot match project '{candidate.project_id}'."
                )

        # Invariant 6: Lock S-14 at WP-6 boundary (Unresolved evidence -> global forbidden)
        has_unresolved_evidence = any(scp == "unresolved" for scp, _ in evidence_scopes)
        if has_unresolved_evidence and candidate.scope == "global":
            raise ScopeIsolationError(
                "Unresolved evidence input cannot silently become scope='global' (S-14)."
            )

    def create_observation(
        self,
        candidate: ObservationCandidate,
        *,
        now_ts: str | None = None,
    ) -> ObservationEntity:
        """Validate candidate, record typed relations, and persist observation."""
        self.validate_candidate(candidate)

        now = now_ts or datetime.now(UTC).isoformat()
        obs_id = f"obs_{uuid.uuid4().hex[:12]}"

        # Calculate proof_count from positive supporting links only (S6-02, S6-03)
        proof_count = candidate.positive_proof_count

        obs_entity = ObservationEntity(
            observation_id=obs_id,
            scope=candidate.scope,
            project_id=candidate.project_id,
            statement=candidate.statement,
            proof_count=proof_count,
            status="active",
            created_at=now,
            updated_at=now,
        )

        with self._store.transaction():
            # 1. Insert observation entity
            self._store.insert_observation(obs_entity)

            # 2. Insert slice links
            for sid in candidate.supporting_slices:
                self._store.insert_observation_slice_link(
                    ObservationSliceLinkEntity(
                        observation_id=obs_id,
                        slice_id=sid,
                        role="supporting",
                        linked_at=now,
                    )
                )
            for sid in candidate.counter_slices:
                self._store.insert_observation_slice_link(
                    ObservationSliceLinkEntity(
                        observation_id=obs_id,
                        slice_id=sid,
                        role="counter",
                        linked_at=now,
                    )
                )

            # 3. Insert event links (Adoption retention-pins the event skeletons: S6-13)
            for eid in candidate.supporting_events:
                self._store.insert_observation_event_link(
                    ObservationEventLinkEntity(
                        observation_id=obs_id,
                        event_id=eid,
                        role="supporting",
                        linked_at=now,
                    )
                )
            for eid in candidate.counter_events:
                self._store.insert_observation_event_link(
                    ObservationEventLinkEntity(
                        observation_id=obs_id,
                        event_id=eid,
                        role="counter",
                        linked_at=now,
                    )
                )

            # 4. Insert semantic memory links
            for mid in candidate.supporting_memories:
                self._store.insert_observation_memory_link(
                    ObservationMemoryLinkEntity(
                        observation_id=obs_id,
                        memory_id=mid,
                        role="supporting",
                        linked_at=now,
                    )
                )
            for mid in candidate.counter_memories:
                self._store.insert_observation_memory_link(
                    ObservationMemoryLinkEntity(
                        observation_id=obs_id,
                        memory_id=mid,
                        role="counter",
                        linked_at=now,
                    )
                )

            # 5. Insert contextual episode links (contextual_scope only)
            for ep_id in candidate.contextual_episodes:
                self._store.insert_observation_episode_link(
                    ObservationEpisodeLinkEntity(
                        observation_id=obs_id,
                        episode_id=ep_id,
                        role="contextual_scope",
                        linked_at=now,
                    )
                )

        return obs_entity

    def recompute_observation_proof(
        self,
        observation_id: str,
        *,
        now_ts: str | None = None,
    ) -> int:
        """Recompute independent supporting proof_count using ProvenanceRepository.

        If proof_count reaches 0, observation is retracted (S6-11).
        """
        now = now_ts or datetime.now(UTC).isoformat()
        prov = ProvenanceRepository(self._store.connection)
        remaining_proof = prov.count_observation_supporting_evidence(observation_id)

        status: ObservationStatus = "retracted" if remaining_proof == 0 else "active"
        self._store.update_observation_proof_count(
            observation_id=observation_id,
            proof_count=remaining_proof,
            status=status,
            updated_at=now,
        )
        return remaining_proof

    def get_observation(self, observation_id: str) -> ObservationEntity | None:
        """Fetch observation by ID."""
        return self._store.get_observation(observation_id)

    def list_observations(
        self,
        scope: Scope | None = None,
        project_id: str | None = None,
        status: ObservationStatus | None = None,
    ) -> list[ObservationEntity]:
        """List observations filtered by criteria."""
        return self._store.list_observations(scope=scope, project_id=project_id, status=status)
