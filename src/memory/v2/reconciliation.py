"""Reconciliation Engine for Memory V2.1 Lane E (WP-4).

Coordinates Phase 2 Deterministic Validation and Single Atomic Transaction Commit:
- Phase 1 read-only proposal is validated against DB state.
- Executes five canonical actions: ADD, SUPERSEDE, REINFORCE, AMBIGUOUS, NOOP.
- Every semantic mutation is executed in a single atomic SQLite transaction.
- Rolls back completely on failure with zero partial semantic state.
- Strictly isolated: Does NOT generate hypotheses, observations, or confirmed insights.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.memory.v2.candidate_extraction import CandidateExtractor
from src.memory.v2.entities import (
    EvidenceReinforcementEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.proposals import (
    ConsolidationProposal,
)
from src.memory.v2.reconciliation_validator import (
    ReconciliationAction,
    ReconciliationDecision,
    ReconciliationValidator,
)
from src.memory.v2.store import ChronicleStoreV2


@dataclass(frozen=True)
class MutationPlan:
    """Prepared, validated database mutations to apply in one atomic transaction."""

    action: ReconciliationAction
    new_memory: SemanticMemoryEntity | None = None
    superseded_memory_id: str | None = None
    superseded_invalidated_at: str | None = None
    superseded_by_id: str | None = None
    reinforcement: EvidenceReinforcementEntity | None = None
    ambiguous_memory: SemanticMemoryEntity | None = None
    proof_delta: int = 0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReconciliationResult:
    """Execution outcome of a validated reconciliation mutation."""

    success: bool
    action: ReconciliationAction
    decision: ReconciliationDecision
    plan: MutationPlan
    affected_memory_ids: list[str] = field(default_factory=list)
    proof_delta: int = 0
    error: str | None = None
    execution_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReconciliationEngine:
    """Orchestrates Phase-2 validation and atomic commit for Long-Term Memory V2.1."""

    def __init__(
        self,
        store: ChronicleStoreV2,
        validator: ReconciliationValidator | None = None,
        candidate_extractor: CandidateExtractor | None = None,
    ) -> None:
        self.store = store
        self.validator = validator or ReconciliationValidator(store)
        self.extractor = candidate_extractor or CandidateExtractor()

    def build_mutation_plan(
        self,
        decision: ReconciliationDecision,
        source_slice_id: str | None = None,
        source_event_id: str | None = None,
        source_episode_id: str | None = None,
        occurred_at: str | None = None,
        custom_memory_id: str | None = None,
    ) -> MutationPlan:
        """Construct the atomic mutation plan for a validated decision."""
        now_ts = occurred_at or datetime.now(UTC).isoformat()

        if decision.action == "NOOP" or not decision.is_valid:
            return MutationPlan(
                action="NOOP",
                proof_delta=0,
                rationale=decision.rationale,
            )

        if decision.action == "ADD":
            mem_id = custom_memory_id or f"mem_{uuid.uuid4().hex[:12]}"
            new_mem = SemanticMemoryEntity(
                memory_id=mem_id,
                category=decision.category,
                statement=decision.statement,
                authority_class=decision.authority_class,
                scope=decision.scope,
                project_id=decision.project_id,
                source_slice_id=source_slice_id,
                source_event_id=source_event_id,
                source_episode_id=source_episode_id,
                valid_from=now_ts,
                invalidated_at=None,
                superseded_by=None,
                validity_status="active",
                expression_policy="normal",
                created_at=now_ts,
            )
            return MutationPlan(
                action="ADD",
                new_memory=new_mem,
                proof_delta=1,
                rationale=decision.rationale,
            )

        if decision.action == "SUPERSEDE":
            if not decision.target_memory_id:
                msg = "SUPERSEDE mutation plan requires a valid target_memory_id."
                raise ValueError(msg)
            new_mem_id = custom_memory_id or f"mem_{uuid.uuid4().hex[:12]}"
            new_mem = SemanticMemoryEntity(
                memory_id=new_mem_id,
                category=decision.category,
                statement=decision.statement,
                authority_class=decision.authority_class,
                scope=decision.scope,
                project_id=decision.project_id,
                source_slice_id=source_slice_id,
                source_event_id=source_event_id,
                source_episode_id=source_episode_id,
                valid_from=now_ts,
                invalidated_at=None,
                superseded_by=None,
                validity_status="active",
                expression_policy="normal",
                created_at=now_ts,
            )
            return MutationPlan(
                action="SUPERSEDE",
                new_memory=new_mem,
                superseded_memory_id=decision.target_memory_id,
                superseded_invalidated_at=now_ts,
                superseded_by_id=new_mem_id,
                proof_delta=1,
                rationale=decision.rationale,
            )

        if decision.action == "REINFORCE":
            if not decision.target_memory_id:
                msg = "REINFORCE mutation plan requires a valid target_memory_id."
                raise ValueError(msg)
            reinf_id = f"reinf_{uuid.uuid4().hex[:12]}"
            fingerprint = decision.independence_fingerprint or f"fp_{uuid.uuid4().hex[:12]}"
            reinf = EvidenceReinforcementEntity(
                reinforcement_id=reinf_id,
                memory_id=decision.target_memory_id,
                slice_id=source_slice_id,
                event_id=source_event_id,
                independence_fingerprint=fingerprint,
                occurred_at=now_ts,
            )
            return MutationPlan(
                action="REINFORCE",
                reinforcement=reinf,
                proof_delta=1,
                rationale=decision.rationale,
            )

        if decision.action == "AMBIGUOUS":
            mem_id = custom_memory_id or f"mem_{uuid.uuid4().hex[:12]}"
            amb_mem = SemanticMemoryEntity(
                memory_id=mem_id,
                category=decision.category,
                statement=decision.statement,
                authority_class=decision.authority_class,
                scope=decision.scope,
                project_id=decision.project_id,
                source_slice_id=source_slice_id,
                source_event_id=source_event_id,
                source_episode_id=source_episode_id,
                valid_from=now_ts,
                invalidated_at=None,
                superseded_by=None,
                validity_status="ambiguous",
                expression_policy="normal",
                created_at=now_ts,
            )
            return MutationPlan(
                action="AMBIGUOUS",
                ambiguous_memory=amb_mem,
                proof_delta=0,
                rationale=decision.rationale,
            )

        return MutationPlan(action="NOOP", proof_delta=0, rationale=decision.rationale)

    def execute_plan(
        self,
        plan: MutationPlan,
        decision: ReconciliationDecision,
    ) -> ReconciliationResult:
        """Execute a MutationPlan inside one single atomic SQLite transaction."""
        t0 = time.perf_counter()

        if plan.action == "NOOP":
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return ReconciliationResult(
                success=True,
                action="NOOP",
                decision=decision,
                plan=plan,
                affected_memory_ids=[],
                proof_delta=0,
                error=None,
                execution_latency_ms=latency_ms,
            )

        affected: list[str] = []

        try:
            with self.store.transaction():
                if plan.action == "ADD" and plan.new_memory:
                    self.store.insert_semantic_memory(plan.new_memory)
                    affected.append(plan.new_memory.memory_id)

                elif plan.action == "SUPERSEDE":
                    if plan.new_memory:
                        self.store.insert_semantic_memory(plan.new_memory)
                        affected.append(plan.new_memory.memory_id)

                    if plan.superseded_memory_id:
                        self.store.connection.execute(
                            """
                            UPDATE semantic_memories
                               SET validity_status = 'superseded',
                                   invalidated_at = ?,
                                   superseded_by = ?
                             WHERE memory_id = ?;
                            """,
                            (
                                plan.superseded_invalidated_at,
                                plan.superseded_by_id,
                                plan.superseded_memory_id,
                            ),
                        )
                        affected.append(plan.superseded_memory_id)

                elif plan.action == "REINFORCE" and plan.reinforcement:
                    self.store.insert_evidence_reinforcement(plan.reinforcement)
                    affected.append(plan.reinforcement.memory_id)

                elif plan.action == "AMBIGUOUS" and plan.ambiguous_memory:
                    self.store.insert_semantic_memory(plan.ambiguous_memory)
                    affected.append(plan.ambiguous_memory.memory_id)

            latency_ms = (time.perf_counter() - t0) * 1000.0
            return ReconciliationResult(
                success=True,
                action=plan.action,
                decision=decision,
                plan=plan,
                affected_memory_ids=affected,
                proof_delta=plan.proof_delta,
                error=None,
                execution_latency_ms=latency_ms,
            )

        except Exception as exc:
            # Transaction was rolled back by self.store.transaction()
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return ReconciliationResult(
                success=False,
                action=plan.action,
                decision=decision,
                plan=plan,
                affected_memory_ids=[],
                proof_delta=0,
                error=str(exc),
                execution_latency_ms=latency_ms,
            )

    def reconcile_proposal(
        self,
        proposal: ConsolidationProposal,
        context: dict[str, Any] | None = None,
    ) -> list[ReconciliationResult]:
        """Validate untrusted proposal and apply mutations in atomic commits."""
        ctx = context or {}
        decisions = self.validator.validate_proposal(proposal, context=ctx)
        results: list[ReconciliationResult] = []

        source_slice_id = proposal.source_id if proposal.source_type == "slice" else None
        source_event_id = proposal.source_id if proposal.source_type == "event" else None
        source_episode_id = str(ctx.get("episode_id")) if ctx.get("episode_id") else None

        for dec in decisions:
            custom_id = str(ctx.get("target_id")) if ctx.get("target_id") else None
            plan = self.build_mutation_plan(
                decision=dec,
                source_slice_id=source_slice_id,
                source_event_id=source_event_id,
                source_episode_id=source_episode_id,
                occurred_at=proposal.created_at,
                custom_memory_id=custom_id,
            )
            res = self.execute_plan(plan, dec)
            results.append(res)

        return results

    def reconcile_slice(
        self,
        slice_entity: RawSliceEntity,
        echoed_proposition: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[ReconciliationResult]:
        """Full end-to-end reconciliation for an incoming Raw User Slice."""
        ctx = context or {}
        proposal = self.extractor.extract_from_slice(
            slice_entity=slice_entity,
            echoed_proposition=echoed_proposition,
            context=ctx,
        )
        return self.reconcile_proposal(proposal, context=ctx)
