"""Hypothesis Layer (WP-6): Subjective companion developmental inferences grounded in observations.

Preserves frozen invariants:
- Hypothesis != Truth: All newly synthesized hypotheses strictly start as `candidate` (S6-05).
- Single Raw Slice Guard: Single slice cannot create a self-model hypothesis (S6-01).
- Telemetry Authority Boundary: Telemetry alone cannot infer user thoughts (S6-16).
- Typed Provenance: Reverse-traversable links in `hypothesis_observation_links`.
- Lenses != Scores: Classifies behavioral flexibility (ACT-informed), never a numerical score.
- No Chapter Leakage: Narrative chapters are never evidence (S6-17).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from src.memory.v2.entities import (
    HypothesisConfidence,
    HypothesisEntity,
    HypothesisObservationLinkEntity,
    HypothesisStatus,
    Scope,
)
from src.memory.v2.observation import (
    ScopeIsolationError,
    SingleSlicePsychError,
    TelemetryAuthorityError,
)

if TYPE_CHECKING:
    from src.memory.v2.store import ChronicleStoreV2


class DevelopmentLens(StrEnum):
    """The six lenses of psychological flexibility (ACT-informed, non-scoring)."""

    TEMPORAL_INTEGRATION = "temporal_integration"
    OPENNESS_TO_UNCERTAINTY = "openness_to_uncertainty"
    REGULATORY_FLEXIBILITY = "regulatory_flexibility"
    AUTONOMOUS_ACTION = "autonomous_action"
    EXPERIENTIAL_OPENNESS = "experiential_openness"
    NARRATIVE_INTEGRATION = "narrative_integration"


class HypothesisValidationError(ValueError):
    """Raised when hypothesis proposal violates epistemic or structural rules."""

    pass


@dataclass
class HypothesisProposal:
    """Pre-commit proposal for an emerging developmental hypothesis."""

    statement: str
    lenses: list[DevelopmentLens | str] | str
    supporting_observation_ids: list[str]
    counter_observation_ids: list[str] = field(default_factory=list)
    contextual_observation_ids: list[str] = field(default_factory=list)
    primary_observation_id: str | None = None
    confidence_class: HypothesisConfidence = "tentative"
    scope: Scope = "global"
    project_id: str | None = None

    def normalized_lenses(self) -> str:
        """Format lenses as a comma-separated string."""
        if isinstance(self.lenses, str):
            return self.lenses
        return ",".join(str(lens) for lens in self.lenses)


class HypothesisEngine:
    """Derives candidate developmental hypotheses grounded in active observations."""

    def __init__(
        self,
        store: ChronicleStoreV2,
        *,
        min_independent_evidence: int = 2,
    ) -> None:
        self._store = store
        self._min_independent_evidence = min_independent_evidence

    @property
    def store(self) -> ChronicleStoreV2:
        return self._store

    def validate_proposal(self, proposal: HypothesisProposal) -> None:
        """Validate proposal against frozen invariants."""
        if not proposal.statement.strip():
            raise HypothesisValidationError("Hypothesis statement cannot be empty.")

        if not proposal.supporting_observation_ids:
            raise HypothesisValidationError(
                "Candidate hypothesis requires at least one active supporting Observation."
            )

        # Collect underlying evidence across all supporting observations
        all_slice_ids: set[str] = set()
        all_event_ids: set[str] = set()
        all_memory_ids: set[str] = set()
        observation_scopes: set[tuple[str, str | None]] = set()

        for obs_id in proposal.supporting_observation_ids:
            obs = self._store.get_observation(obs_id)
            if not obs:
                raise HypothesisValidationError(f"Supporting observation '{obs_id}' not found.")
            if obs.status != "active":
                raise HypothesisValidationError(
                    f"Supporting observation '{obs_id}' is {obs.status}; must be active."
                )

            observation_scopes.add((obs.scope, obs.project_id))

            # Retrieve underlying evidence links
            slice_links = self._store.get_observation_slice_links(obs_id)
            for sl in slice_links:
                if sl.role == "supporting":
                    all_slice_ids.add(sl.slice_id)

            event_links = self._store.get_observation_event_links(obs_id)
            for el in event_links:
                if el.role == "supporting":
                    all_event_ids.add(el.event_id)

            memory_links = self._store.get_observation_memory_links(obs_id)
            for ml in memory_links:
                if ml.role == "supporting":
                    all_memory_ids.add(ml.memory_id)

        total_independent_evidence = len(all_slice_ids) + len(all_event_ids) + len(all_memory_ids)

        # Invariant 1: Single-slice psych guard (S6-01)
        # An isolated single raw slice cannot create a psychological/self-model hypothesis
        if len(all_slice_ids) == 1 and total_independent_evidence < self._min_independent_evidence:
            raise SingleSlicePsychError(
                "One isolated slice cannot create a psychological/self-model hypothesis (S6-01). "
                f"Requires at least {self._min_independent_evidence} independent positive supports."
            )

        if total_independent_evidence < self._min_independent_evidence:
            raise SingleSlicePsychError(
                f"Candidate hypothesis requires evidence diversity (at least "
                f"{self._min_independent_evidence} independent positive supports), "
                f"got {total_independent_evidence}."
            )

        # Invariant 2: Telemetry authority boundary (S6-16)
        # Telemetry alone cannot infer why user felt/thought something
        has_user_voice = bool(all_slice_ids or all_memory_ids)
        if not has_user_voice and all_event_ids:
            raise TelemetryAuthorityError(
                "Telemetry alone cannot create subjective preference/feeling hypothesis (S6-16). "
                "User voice is required."
            )

        # Invariant 3: Scope isolation (S6-04)
        project_ids = {
            pid for scp, pid in observation_scopes if scp == "project" and pid is not None
        }
        if len(project_ids) > 1:
            raise ScopeIsolationError(
                f"Supporting observations span multiple projects: {project_ids} (S6-04)."
            )

        if project_ids:
            sole_project = next(iter(project_ids))
            if proposal.scope == "global":
                raise ScopeIsolationError(
                    f"Project observations ({sole_project}) cannot form global hypothesis (S6-04)."
                )
            if proposal.scope == "project" and proposal.project_id != sole_project:
                raise ScopeIsolationError(
                    f"Observations from project '{sole_project}' cannot form "
                    f"hypothesis for project '{proposal.project_id}'."
                )

    def propose_hypothesis(
        self,
        proposal: HypothesisProposal,
        *,
        now_ts: str | None = None,
    ) -> HypothesisEntity:
        """Validate and create a new candidate hypothesis."""
        self.validate_proposal(proposal)

        now = now_ts or datetime.now(UTC).isoformat()
        hyp_id = f"hyp_{uuid.uuid4().hex[:12]}"

        # Primary observation determination
        primary_id = proposal.primary_observation_id or (
            proposal.supporting_observation_ids[0] if proposal.supporting_observation_ids else None
        )

        # Invariant: Starts strictly as candidate (S6-05)
        entity = HypothesisEntity(
            hypothesis_id=hyp_id,
            statement=proposal.statement,
            lenses=proposal.normalized_lenses(),
            confidence_class=proposal.confidence_class,
            status="candidate",
            last_calibrated_at=None,
            created_at=now,
        )

        with self._store.transaction():
            # 1. Insert hypothesis record
            self._store.insert_hypothesis(entity)

            # 2. Insert supporting observation links
            for obs_id in proposal.supporting_observation_ids:
                is_primary = 1 if obs_id == primary_id else 0
                self._store.insert_hypothesis_observation_link(
                    HypothesisObservationLinkEntity(
                        hypothesis_id=hyp_id,
                        observation_id=obs_id,
                        role="supporting",
                        is_primary=is_primary,
                        linked_at=now,
                    )
                )

            # 3. Insert counter observation links
            for obs_id in proposal.counter_observation_ids:
                self._store.insert_hypothesis_observation_link(
                    HypothesisObservationLinkEntity(
                        hypothesis_id=hyp_id,
                        observation_id=obs_id,
                        role="counter",
                        is_primary=0,
                        linked_at=now,
                    )
                )

            # 4. Insert contextual observation links
            for obs_id in proposal.contextual_observation_ids:
                self._store.insert_hypothesis_observation_link(
                    HypothesisObservationLinkEntity(
                        hypothesis_id=hyp_id,
                        observation_id=obs_id,
                        role="contextual",
                        is_primary=0,
                        linked_at=now,
                    )
                )

        return entity

    def get_hypothesis(self, hypothesis_id: str) -> HypothesisEntity | None:
        """Fetch hypothesis by ID."""
        return self._store.get_hypothesis(hypothesis_id)

    def list_hypotheses(self, status: HypothesisStatus | None = None) -> list[HypothesisEntity]:
        """List hypotheses, optionally filtered by status."""
        return self._store.list_hypotheses(status=status)
