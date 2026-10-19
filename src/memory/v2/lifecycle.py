"""Typed Provenance and Lifecycle Infrastructure for Memory V2.1.

Part of Coeva Long-Term Memory V2.1 Stage 3 (WP-2).
Implements:
- Strongly typed provenance references and reverse impact traversal
- Atomic Hard Delete dependency closure across 8 lifecycle steps (I-S07)
- Proof count recomputation and canonical retract/revalidate propagation
- Immediate privacy unreadability marker (IMPL-3 / needs_privacy_redaction = 1)
- Retention pin / unpin lifecycle semantics (IMPL-1: episode != pin, durable refs pin)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from src.memory.v2.provenance import ProvenanceRepository
from src.memory.v2.store import ChronicleStoreV2


class LifecycleError(RuntimeError):
    """Base exception for all lifecycle operations."""

    pass


class TargetNotFoundError(LifecycleError):
    """Raised when the target evidence entity is not found."""

    pass


class EventPinnedError(LifecycleError):
    """Raised when an attempt is made to purge or hard-delete a retention-pinned event."""

    pass


class DependencyClosureError(LifecycleError):
    """Raised when dependency closure fails referential integrity or foreign key constraints."""

    pass


@dataclass(frozen=True)
class LifecycleAction:
    """Record of a planned or executed lifecycle mutation step."""

    action_type: str
    target_type: str
    target_id: str
    detail: str = ""


@dataclass(frozen=True)
class ImpactReport:
    """Read-only dry-run analysis report of deleting an evidence entity."""

    target_type: Literal["slice", "event"]
    target_id: str
    exists: bool
    is_pinned: bool = False
    pin_reasons: list[str] = field(default_factory=list)
    affected_episodes: list[str] = field(default_factory=list)
    affected_semantic_memories: list[dict[str, Any]] = field(default_factory=list)
    affected_observations: list[dict[str, Any]] = field(default_factory=list)
    affected_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    affected_confirmed_insights: list[dict[str, Any]] = field(default_factory=list)
    affected_chapters: list[dict[str, Any]] = field(default_factory=list)
    planned_actions: list[LifecycleAction] = field(default_factory=list)
    can_delete: bool = True
    block_reason: str | None = None


@dataclass(frozen=True)
class HardDeleteResult:
    """Atomic execution result of a hard delete lifecycle transaction."""

    success: bool
    target_type: Literal["slice", "event"]
    target_id: str
    deleted_base_evidence: bool
    actions_performed: list[LifecycleAction] = field(default_factory=list)
    unpinned_events: list[str] = field(default_factory=list)
    retracted_observations: list[str] = field(default_factory=list)
    recomputed_observations: list[str] = field(default_factory=list)
    retracted_hypotheses: list[str] = field(default_factory=list)
    revalidated_hypotheses: list[str] = field(default_factory=list)
    retracted_insights: list[str] = field(default_factory=list)
    revalidated_insights: list[str] = field(default_factory=list)
    privacy_redacted_chapters: list[str] = field(default_factory=list)
    surviving_memories: list[str] = field(default_factory=list)
    removed_memories: list[str] = field(default_factory=list)
    foreign_key_check_passed: bool = True
    error: str | None = None


class LifecycleService:
    """Orchestrates typed provenance traversal and fail-closed Hard Delete lifecycle."""

    def __init__(self, store: ChronicleStoreV2) -> None:
        self._store = store
        self._prov_repo = ProvenanceRepository(store.connection)

    @property
    def store(self) -> ChronicleStoreV2:
        """Return the underlying ChronicleStoreV2 handle."""
        return self._store

    @property
    def provenance_repo(self) -> ProvenanceRepository:
        """Return the underlying ProvenanceRepository handle."""
        return self._prov_repo

    # ── Retention Pin APIs (IMPL-1) ───────────────────────────────────────────

    def is_event_pinned(self, event_id: str) -> bool:
        """Check whether an event is retention-pinned by active durable provenance."""
        return self._prov_repo.is_event_durable_pinned(event_id)

    def get_event_pin_reasons(self, event_id: str) -> list[str]:
        """Return human-readable descriptions of all durable links pinning an event."""
        reasons: list[str] = []
        conn = self._store.connection

        # 1. Active observations
        obs_rows = conn.execute(
            "SELECT obs.observation_id, obs.statement FROM observation_event_links oel "
            "JOIN observations obs ON oel.observation_id = obs.observation_id "
            "WHERE oel.event_id = ? AND obs.status = 'active';",
            (event_id,),
        ).fetchall()
        for r in obs_rows:
            reasons.append(f"active_observation:{r['observation_id']}")

        # 2. Active semantic memories (primary source)
        mem_rows = conn.execute(
            "SELECT memory_id, statement FROM semantic_memories "
            "WHERE source_event_id = ? AND validity_status = 'active';",
            (event_id,),
        ).fetchall()
        for r in mem_rows:
            reasons.append(f"active_semantic_memory:{r['memory_id']}")

        # 3. Active semantic memories (reinforcement)
        reinf_rows = conn.execute(
            "SELECT er.reinforcement_id, er.memory_id FROM evidence_reinforcements er "
            "JOIN semantic_memories sm ON er.memory_id = sm.memory_id "
            "WHERE er.event_id = ? AND sm.validity_status = 'active';",
            (event_id,),
        ).fetchall()
        for r in reinf_rows:
            reasons.append(f"active_reinforcement:{r['memory_id']}")

        return reasons

    # ── Dry-Run Impact Traversal (Read-Only) ───────────────────────────────────

    def analyze_slice_delete(
        self,
        slice_id: str,
        *,
        privacy_sensitive: bool = True,
    ) -> ImpactReport:
        """Dry-run impact analysis of deleting a raw slice.

        Does not mutate the database. Traverses the 8-step dependency graph.
        """
        conn = self._store.connection
        slice_row = conn.execute(
            "SELECT slice_id FROM raw_slices WHERE slice_id = ?;", (slice_id,)
        ).fetchone()

        if not slice_row:
            return ImpactReport(
                target_type="slice",
                target_id=slice_id,
                exists=False,
                can_delete=False,
                block_reason="Raw slice not found",
            )

        planned_actions: list[LifecycleAction] = []

        # 1. Affected Chapters
        chap_links = self._prov_repo.get_slice_chapter_links(slice_id)
        affected_chapters: list[dict[str, Any]] = []
        for cl in chap_links:
            affected_chapters.append(
                {
                    "chapter_id": cl.chapter_id,
                    "privacy_redacted": privacy_sensitive,
                }
            )
            if privacy_sensitive:
                planned_actions.append(
                    LifecycleAction(
                        action_type="privacy_block_chapter",
                        target_type="chapter",
                        target_id=cl.chapter_id,
                        detail="Set needs_privacy_redaction = 1",
                    )
                )
            planned_actions.append(
                LifecycleAction(
                    action_type="unlink_chapter_slice",
                    target_type="chapter_slice_link",
                    target_id=f"{cl.chapter_id}:{slice_id}",
                    detail="Unlink slice citation from chapter",
                )
            )

        # 2. Affected Episodes
        ep_links = self._prov_repo.get_slice_episode_links(slice_id)
        affected_episodes = [el.episode_id for el in ep_links]
        for ep_id in affected_episodes:
            planned_actions.append(
                LifecycleAction(
                    action_type="unlink_episode_slice",
                    target_type="episode_slice_link",
                    target_id=f"{ep_id}:{slice_id}",
                    detail="Unlink slice from episode container",
                )
            )

        # 3. Direct Reinforcements on slice
        slice_reinfs = self._prov_repo.get_slice_reinforcements(slice_id)
        for sr in slice_reinfs:
            planned_actions.append(
                LifecycleAction(
                    action_type="delete_reinforcement",
                    target_type="evidence_reinforcement",
                    target_id=sr.reinforcement_id,
                    detail=f"Delete reinforcement on memory {sr.memory_id}",
                )
            )

        # 4. Affected Semantic Memories
        primary_mems = self._prov_repo.get_slice_primary_memories(slice_id)
        mem_ids_to_check = {m.memory_id for m in primary_mems}
        mem_ids_to_check.update(sr.memory_id for sr in slice_reinfs)

        affected_mems: list[dict[str, Any]] = []
        dying_mem_ids: set[str] = set()

        for mid in sorted(mem_ids_to_check):
            mem = self._store.get_semantic_memory(mid)
            if not mem:
                continue
            # Check surviving reinforcements
            reinfs = self._prov_repo.get_memory_reinforcements(mid)
            surviving_reinfs = [r for r in reinfs if r.slice_id != slice_id]

            if surviving_reinfs:
                # Survives by promoting next reinforcement
                next_r = surviving_reinfs[0]
                affected_mems.append(
                    {
                        "memory_id": mid,
                        "surviving": True,
                        "promoted_provenance": next_r.slice_id or next_r.event_id,
                        "remaining_reinforcements_count": len(surviving_reinfs) - 1,
                    }
                )
                planned_actions.append(
                    LifecycleAction(
                        action_type="promote_reinforcement",
                        target_type="semantic_memory",
                        target_id=mid,
                        detail=f"Promote reinforcement {next_r.reinforcement_id} as primary source",
                    )
                )
            else:
                # Memory has no other provenance -> cannot survive
                affected_mems.append(
                    {
                        "memory_id": mid,
                        "surviving": False,
                        "promoted_provenance": None,
                        "remaining_reinforcements_count": 0,
                    }
                )
                dying_mem_ids.add(mid)
                planned_actions.append(
                    LifecycleAction(
                        action_type="delete_memory",
                        target_type="semantic_memory",
                        target_id=mid,
                        detail="Remove memory with zero remaining evidence",
                    )
                )

        # 5. Affected Observations
        obs_links = self._prov_repo.get_slice_observation_links(slice_id)
        affected_obs_ids = {ol.observation_id for ol in obs_links}

        # Also observations citing dying memories
        for dmid in dying_mem_ids:
            obs_mem_links = self._prov_repo.get_memory_observation_links(dmid)
            for oml in obs_mem_links:
                affected_obs_ids.add(oml.observation_id)

        affected_observations: list[dict[str, Any]] = []
        retracted_obs_ids: set[str] = set()

        for oid in sorted(affected_obs_ids):
            obs = self._store.get_observation(oid)
            if not obs:
                continue

            # Simulate remaining supporting count
            remaining_proof = self._prov_repo.count_observation_supporting_evidence(
                oid,
                excluding_slice_id=slice_id,
            )
            # Subtract dying memories if they were supporting
            for dmid in dying_mem_ids:
                row = conn.execute(
                    "SELECT COUNT(*) FROM observation_memory_links WHERE observation_id = ? "
                    "AND memory_id = ? AND role = 'supporting';",
                    (oid, dmid),
                ).fetchone()
                if row and int(row[0]) > 0:
                    remaining_proof = max(0, remaining_proof - int(row[0]))

            will_retract = remaining_proof == 0
            if will_retract:
                retracted_obs_ids.add(oid)

            affected_observations.append(
                {
                    "observation_id": oid,
                    "old_proof_count": obs.proof_count,
                    "new_proof_count": remaining_proof,
                    "will_retract": will_retract,
                }
            )
            if will_retract:
                planned_actions.append(
                    LifecycleAction(
                        action_type="retract_observation",
                        target_type="observation",
                        target_id=oid,
                        detail="Proof count reached 0 -> retract observation",
                    )
                )
            else:
                planned_actions.append(
                    LifecycleAction(
                        action_type="recompute_observation",
                        target_type="observation",
                        target_id=oid,
                        detail=f"Update proof count from {obs.proof_count} to {remaining_proof}",
                    )
                )

        # 6. Affected Hypotheses
        affected_hyp_ids: set[str] = set()
        for roid in retracted_obs_ids:
            hyp_links = self._prov_repo.get_observation_hypothesis_links(roid)
            for hl in hyp_links:
                if hl.role == "supporting":
                    affected_hyp_ids.add(hl.hypothesis_id)

        affected_hypotheses: list[dict[str, Any]] = []
        retracted_hyp_ids: set[str] = set()

        for hid in sorted(affected_hyp_ids):
            hyp = self._store.get_hypothesis(hid)
            if not hyp:
                continue
            # Simulate remaining active supporting observations
            active_obs_count = self._prov_repo.count_hypothesis_active_observations(
                hid, excluding_observation_id=None
            )
            # Subtract retracted observations
            for roid in retracted_obs_ids:
                row = conn.execute(
                    "SELECT COUNT(*) FROM hypothesis_observation_links WHERE hypothesis_id = ? "
                    "AND observation_id = ? AND role = 'supporting';",
                    (hid, roid),
                ).fetchone()
                if row and int(row[0]) > 0:
                    active_obs_count = max(0, active_obs_count - int(row[0]))

            new_status = "retracted" if active_obs_count == 0 else "revalidation_required"
            if new_status == "retracted":
                retracted_hyp_ids.add(hid)

            affected_hypotheses.append(
                {
                    "hypothesis_id": hid,
                    "old_status": hyp.status,
                    "new_status": new_status,
                    "remaining_active_observations": active_obs_count,
                }
            )
            planned_actions.append(
                LifecycleAction(
                    action_type="update_hypothesis_status",
                    target_type="hypothesis",
                    target_id=hid,
                    detail=f"Update status {hyp.status} -> {new_status}",
                )
            )

        # 7. Affected Confirmed Insights
        affected_insights: list[dict[str, Any]] = []
        for hid in sorted(affected_hyp_ids):
            insights = self._prov_repo.get_hypothesis_confirmed_insights(hid)
            for ins in insights:
                new_ins_status = (
                    "retracted" if hid in retracted_hyp_ids else "revalidation_required"
                )
                affected_insights.append(
                    {
                        "insight_id": ins.insight_id,
                        "source_hypothesis_id": hid,
                        "old_status": ins.status,
                        "new_status": new_ins_status,
                    }
                )
                planned_actions.append(
                    LifecycleAction(
                        action_type="update_insight_status",
                        target_type="confirmed_insight",
                        target_id=ins.insight_id,
                        detail=(
                            f"Update status {ins.status} -> {new_ins_status} "
                            "(calibration preserved)"
                        ),
                    )
                )

        planned_actions.append(
            LifecycleAction(
                action_type="delete_slice",
                target_type="raw_slice",
                target_id=slice_id,
                detail="Physically delete base evidence",
            )
        )

        return ImpactReport(
            target_type="slice",
            target_id=slice_id,
            exists=True,
            is_pinned=False,
            pin_reasons=[],
            affected_episodes=affected_episodes,
            affected_semantic_memories=affected_mems,
            affected_observations=affected_observations,
            affected_hypotheses=affected_hypotheses,
            affected_confirmed_insights=affected_insights,
            affected_chapters=affected_chapters,
            planned_actions=planned_actions,
            can_delete=True,
        )

    def analyze_event_delete(
        self,
        event_id: str,
        *,
        cascade: bool = False,
    ) -> ImpactReport:
        """Dry-run impact analysis of deleting or purging an event skeleton."""
        conn = self._store.connection
        evt_row = conn.execute(
            "SELECT event_id FROM event_skeletons WHERE event_id = ?;", (event_id,)
        ).fetchone()

        if not evt_row:
            return ImpactReport(
                target_type="event",
                target_id=event_id,
                exists=False,
                can_delete=False,
                block_reason="Event skeleton not found",
            )

        is_pinned = self.is_event_pinned(event_id)
        pin_reasons = self.get_event_pin_reasons(event_id)

        # Affected Episodes
        ep_links = self._prov_repo.get_event_episode_links(event_id)
        affected_episodes = [el.episode_id for el in ep_links]

        planned_actions: list[LifecycleAction] = []
        for ep_id in affected_episodes:
            planned_actions.append(
                LifecycleAction(
                    action_type="unlink_episode_event",
                    target_type="episode_event_link",
                    target_id=f"{ep_id}:{event_id}",
                    detail="Unlink event from episode container",
                )
            )

        if is_pinned and not cascade:
            return ImpactReport(
                target_type="event",
                target_id=event_id,
                exists=True,
                is_pinned=True,
                pin_reasons=pin_reasons,
                affected_episodes=affected_episodes,
                planned_actions=planned_actions,
                can_delete=False,
                block_reason=f"Event is retention-pinned by {', '.join(pin_reasons)}",
            )

        # If cascade, analyze downstream dependents
        event_reinfs = self._prov_repo.get_event_reinforcements(event_id)
        primary_mems = self._prov_repo.get_event_primary_memories(event_id)
        mem_ids_to_check = {m.memory_id for m in primary_mems}
        mem_ids_to_check.update(er.memory_id for er in event_reinfs)

        affected_mems: list[dict[str, Any]] = []
        dying_mem_ids: set[str] = set()

        for mid in sorted(mem_ids_to_check):
            mem = self._store.get_semantic_memory(mid)
            if not mem:
                continue
            reinfs = self._prov_repo.get_memory_reinforcements(mid)
            surviving = [r for r in reinfs if r.event_id != event_id]
            if surviving:
                affected_mems.append({"memory_id": mid, "surviving": True})
            else:
                affected_mems.append({"memory_id": mid, "surviving": False})
                dying_mem_ids.add(mid)

        obs_links = self._prov_repo.get_event_observation_links(event_id)
        affected_obs_ids = {ol.observation_id for ol in obs_links}
        for dmid in dying_mem_ids:
            for oml in self._prov_repo.get_memory_observation_links(dmid):
                affected_obs_ids.add(oml.observation_id)

        affected_observations: list[dict[str, Any]] = []
        for oid in sorted(affected_obs_ids):
            obs = self._store.get_observation(oid)
            if not obs:
                continue
            rem = self._prov_repo.count_observation_supporting_evidence(
                oid, excluding_event_id=event_id
            )
            affected_observations.append(
                {
                    "observation_id": oid,
                    "old_proof_count": obs.proof_count,
                    "new_proof_count": rem,
                    "will_retract": rem == 0,
                }
            )

        planned_actions.append(
            LifecycleAction(
                action_type="delete_event",
                target_type="event_skeleton",
                target_id=event_id,
                detail="Physically delete event skeleton",
            )
        )

        return ImpactReport(
            target_type="event",
            target_id=event_id,
            exists=True,
            is_pinned=is_pinned,
            pin_reasons=pin_reasons,
            affected_episodes=affected_episodes,
            affected_semantic_memories=affected_mems,
            affected_observations=affected_observations,
            planned_actions=planned_actions,
            can_delete=True,
        )

    # ── Atomic Hard Delete Execution ──────────────────────────────────────────

    def hard_delete_slice(
        self,
        slice_id: str,
        *,
        privacy_sensitive: bool = True,
        before_physical_delete_hook: Callable[[str], None] | None = None,
    ) -> HardDeleteResult:
        """Atomically hard-delete a raw slice with full 8-step dependency closure.

        Executes in one single SQLite transaction. Rollbacks completely on any failure.
        """
        conn = self._store.connection

        # Pre-check existence
        row = conn.execute(
            "SELECT slice_id FROM raw_slices WHERE slice_id = ?;", (slice_id,)
        ).fetchone()
        if not row:
            raise TargetNotFoundError(f"Raw slice '{slice_id}' does not exist.")

        actions_performed: list[LifecycleAction] = []
        privacy_redacted_chapters: list[str] = []
        surviving_memories: list[str] = []
        removed_memories: list[str] = []
        retracted_observations: list[str] = []
        recomputed_observations: list[str] = []
        retracted_hypotheses: list[str] = []
        revalidated_hypotheses: list[str] = []
        retracted_insights: list[str] = []
        revalidated_insights: list[str] = []
        unpinned_events: list[str] = []

        now_ts = datetime.now(UTC).isoformat()

        with self._store.transaction():
            # ── Step 1: Growth Chapters & Narrative Citations ────────────────
            chap_links = self._prov_repo.get_slice_chapter_links(slice_id)
            for cl in chap_links:
                if privacy_sensitive:
                    conn.execute(
                        "UPDATE chapter_metadata SET needs_privacy_redaction = 1 "
                        "WHERE chapter_id = ?;",
                        (cl.chapter_id,),
                    )
                    privacy_redacted_chapters.append(cl.chapter_id)
                    actions_performed.append(
                        LifecycleAction(
                            action_type="privacy_block_chapter",
                            target_type="chapter_metadata",
                            target_id=cl.chapter_id,
                            detail="Set needs_privacy_redaction = 1 synchronously",
                        )
                    )
                conn.execute(
                    "DELETE FROM chapter_slice_links WHERE chapter_id = ? AND slice_id = ?;",
                    (cl.chapter_id, slice_id),
                )
                actions_performed.append(
                    LifecycleAction(
                        action_type="unlink_chapter_slice",
                        target_type="chapter_slice_link",
                        target_id=f"{cl.chapter_id}:{slice_id}",
                    )
                )

            # ── Step 2: Episode Container Membership ────────────────────────
            ep_links = self._prov_repo.get_slice_episode_links(slice_id)
            for el in ep_links:
                conn.execute(
                    "DELETE FROM episode_slice_links WHERE episode_id = ? AND slice_id = ?;",
                    (el.episode_id, slice_id),
                )
                actions_performed.append(
                    LifecycleAction(
                        action_type="unlink_episode_slice",
                        target_type="episode_slice_link",
                        target_id=f"{el.episode_id}:{slice_id}",
                    )
                )

            # ── Step 3: Direct Evidence Reinforcements ──────────────────────
            slice_reinfs = self._prov_repo.get_slice_reinforcements(slice_id)
            for sr in slice_reinfs:
                conn.execute(
                    "DELETE FROM evidence_reinforcements WHERE reinforcement_id = ?;",
                    (sr.reinforcement_id,),
                )
                actions_performed.append(
                    LifecycleAction(
                        action_type="delete_reinforcement",
                        target_type="evidence_reinforcement",
                        target_id=sr.reinforcement_id,
                    )
                )

            # ── Step 4: Semantic Memories ───────────────────────────────────
            primary_mems = self._prov_repo.get_slice_primary_memories(slice_id)
            mem_ids_to_process = {m.memory_id for m in primary_mems}
            mem_ids_to_process.update(sr.memory_id for sr in slice_reinfs)

            affected_observations_to_recompute: set[str] = set()

            for mid in sorted(mem_ids_to_process):
                mem = self._store.get_semantic_memory(mid)
                if not mem:
                    continue

                remaining_reinfs = self._prov_repo.get_memory_reinforcements(mid)

                if remaining_reinfs:
                    # Promote first remaining reinforcement to primary source
                    first_r = remaining_reinfs[0]
                    if first_r.slice_id:
                        conn.execute(
                            "UPDATE semantic_memories SET source_slice_id = ?, "
                            "source_event_id = NULL WHERE memory_id = ?;",
                            (first_r.slice_id, mid),
                        )
                    elif first_r.event_id:
                        conn.execute(
                            "UPDATE semantic_memories SET source_slice_id = NULL, "
                            "WHERE memory_id = ?;",
                            (first_r.event_id, mid),
                        )
                    # Delete the promoted reinforcement row so it's not duplicated
                    conn.execute(
                        "DELETE FROM evidence_reinforcements WHERE reinforcement_id = ?;",
                        (first_r.reinforcement_id,),
                    )
                    surviving_memories.append(mid)
                    actions_performed.append(
                        LifecycleAction(
                            action_type="promote_reinforcement",
                            target_type="semantic_memory",
                            target_id=mid,
                            detail=f"Promoted {first_r.reinforcement_id} as primary source",
                        )
                    )
                else:
                    # Zero remaining independent evidence -> memory cannot remain active
                    # First unlink from observation_memory_links so FK check passes
                    om_links = self._prov_repo.get_memory_observation_links(mid)
                    for oml in om_links:
                        affected_observations_to_recompute.add(oml.observation_id)
                        conn.execute(
                            "DELETE FROM observation_memory_links "
                            "WHERE observation_id = ? AND memory_id = ?;",
                            (oml.observation_id, mid),
                        )
                        actions_performed.append(
                            LifecycleAction(
                                action_type="unlink_observation_memory",
                                target_type="observation_memory_link",
                                target_id=f"{oml.observation_id}:{mid}",
                            )
                        )

                    # Physically remove memory from active storage
                    conn.execute("DELETE FROM semantic_memories WHERE memory_id = ?;", (mid,))
                    removed_memories.append(mid)
                    actions_performed.append(
                        LifecycleAction(
                            action_type="delete_semantic_memory",
                            target_type="semantic_memory",
                            target_id=mid,
                            detail="Removed unsupported active memory",
                        )
                    )

            # ── Step 5: Observations ────────────────────────────────────────
            direct_obs_links = self._prov_repo.get_slice_observation_links(slice_id)
            for dol in direct_obs_links:
                affected_observations_to_recompute.add(dol.observation_id)
                conn.execute(
                    "DELETE FROM observation_slice_links "
                    "WHERE observation_id = ? AND slice_id = ?;",
                    (dol.observation_id, slice_id),
                )
                actions_performed.append(
                    LifecycleAction(
                        action_type="unlink_observation_slice",
                        target_type="observation_slice_link",
                        target_id=f"{dol.observation_id}:{slice_id}",
                    )
                )

            retracted_obs_set: set[str] = set()

            for oid in sorted(affected_observations_to_recompute):
                obs = self._store.get_observation(oid)
                if not obs:
                    continue

                remaining_proof = self._prov_repo.count_observation_supporting_evidence(oid)
                if remaining_proof == 0:
                    conn.execute(
                        "UPDATE observations SET proof_count = 0, status = 'retracted', "
                        "updated_at = ? WHERE observation_id = ?;",
                        (now_ts, oid),
                    )
                    retracted_observations.append(oid)
                    retracted_obs_set.add(oid)
                    actions_performed.append(
                        LifecycleAction(
                            action_type="retract_observation",
                            target_type="observation",
                            target_id=oid,
                            detail="Proof count reached 0 -> retracted",
                        )
                    )
                else:
                    conn.execute(
                        "UPDATE observations SET proof_count = ?, updated_at = ? "
                        "WHERE observation_id = ?;",
                        (remaining_proof, now_ts, oid),
                    )
                    recomputed_observations.append(oid)
                    actions_performed.append(
                        LifecycleAction(
                            action_type="recompute_observation",
                            target_type="observation",
                            target_id=oid,
                            detail=f"Recomputed proof count -> {remaining_proof}",
                        )
                    )

            # ── Step 6: Hypotheses ──────────────────────────────────────────
            hyp_ids_to_check: set[str] = set()
            for roid in retracted_obs_set:
                h_links = self._prov_repo.get_observation_hypothesis_links(roid)
                for hl in h_links:
                    if hl.role == "supporting":
                        hyp_ids_to_check.add(hl.hypothesis_id)

            retracted_hyp_set: set[str] = set()

            for hid in sorted(hyp_ids_to_check):
                hyp = self._store.get_hypothesis(hid)
                if not hyp:
                    continue

                active_obs_count = self._prov_repo.count_hypothesis_active_observations(hid)
                if active_obs_count == 0:
                    conn.execute(
                        "UPDATE hypotheses SET status = 'retracted' WHERE hypothesis_id = ?;",
                        (hid,),
                    )
                    retracted_hypotheses.append(hid)
                    retracted_hyp_set.add(hid)
                    actions_performed.append(
                        LifecycleAction(
                            action_type="retract_hypothesis",
                            target_type="hypothesis",
                            target_id=hid,
                            detail="Zero active supporting observations remain -> retracted",
                        )
                    )
                else:
                    conn.execute(
                        "UPDATE hypotheses SET status = 'revalidation_required' "
                        "WHERE hypothesis_id = ?;",
                        (hid,),
                    )
                    revalidated_hypotheses.append(hid)
                    actions_performed.append(
                        LifecycleAction(
                            action_type="revalidate_hypothesis",
                            target_type="hypothesis",
                            target_id=hid,
                            detail=(
                                f"Support weakened ({active_obs_count} remaining) "
                                "-> revalidation_required"
                            ),
                        )
                    )

            # ── Step 7: Confirmed Insights & Calibration History ────────────
            for hid in sorted(hyp_ids_to_check):
                insights = self._prov_repo.get_hypothesis_confirmed_insights(hid)
                for ins in insights:
                    if hid in retracted_hyp_set:
                        conn.execute(
                            "UPDATE confirmed_insights SET status = 'retracted', "
                            "invalidated_at = ? WHERE insight_id = ? "
                            "AND status != 'retracted';",
                            (now_ts, ins.insight_id),
                        )
                        retracted_insights.append(ins.insight_id)
                        actions_performed.append(
                            LifecycleAction(
                                action_type="retract_insight",
                                target_type="confirmed_insight",
                                target_id=ins.insight_id,
                                detail=(
                                    "Source hypothesis retracted -> insight retracted "
                                    "(calibration log preserved)"
                                ),
                            )
                        )
                    else:
                        conn.execute(
                            "UPDATE confirmed_insights SET status = 'revalidation_required' "
                            "WHERE insight_id = ? AND status = 'confirmed';",
                            (ins.insight_id,),
                        )
                        revalidated_insights.append(ins.insight_id)
                        actions_performed.append(
                            LifecycleAction(
                                action_type="revalidate_insight",
                                target_type="confirmed_insight",
                                target_id=ins.insight_id,
                                detail=(
                                    "Source hypothesis weakened -> insight revalidation_required"
                                ),
                            )
                        )

            # ── Step 8: Retention Pin Updates for Events ────────────────────
            for roid in retracted_obs_set:
                # Find event links that were associated with this observation
                e_rows = conn.execute(
                    "SELECT event_id FROM observation_event_links WHERE observation_id = ?;",
                    (roid,),
                ).fetchall()
                for er in e_rows:
                    eid = er["event_id"]
                    if not self._prov_repo.is_event_durable_pinned(eid):
                        unpinned_events.append(eid)
                        actions_performed.append(
                            LifecycleAction(
                                action_type="unpin_event",
                                target_type="event_skeleton",
                                target_id=eid,
                                detail="Last durable provenance removed -> event unpinned",
                            )
                        )
            if before_physical_delete_hook:
                before_physical_delete_hook(slice_id)

            # ── Step 9: Physically Delete Base Evidence ─────────────────────
            conn.execute("DELETE FROM raw_slices WHERE slice_id = ?;", (slice_id,))
            actions_performed.append(
                LifecycleAction(
                    action_type="delete_raw_slice",
                    target_type="raw_slice",
                    target_id=slice_id,
                    detail="Base evidence physically deleted",
                )
            )

            # ── Step 10: Fail-Closed Foreign Key Verification ───────────────
            fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
            if fk_violations:
                raise DependencyClosureError(
                    f"Dependency closure failed: FK check violations: {fk_violations}"
                )

        return HardDeleteResult(
            success=True,
            target_type="slice",
            target_id=slice_id,
            deleted_base_evidence=True,
            actions_performed=actions_performed,
            unpinned_events=unpinned_events,
            retracted_observations=retracted_observations,
            recomputed_observations=recomputed_observations,
            retracted_hypotheses=retracted_hypotheses,
            revalidated_hypotheses=revalidated_hypotheses,
            retracted_insights=retracted_insights,
            revalidated_insights=revalidated_insights,
            privacy_redacted_chapters=privacy_redacted_chapters,
            surviving_memories=surviving_memories,
            removed_memories=removed_memories,
            foreign_key_check_passed=True,
        )

    def hard_delete_event(
        self,
        event_id: str,
        *,
        cascade: bool = False,
        before_physical_delete_hook: Callable[[str], None] | None = None,
    ) -> HardDeleteResult:
        """Atomically hard-delete or purge an event skeleton.

        If cascade=False:
            If event is pinned by durable provenance, fails closed with EventPinnedError.
            If event is only in episodes, unlinks episode membership and purges event cleanly.
        If cascade=True:
            Cascades full dependency closure across memories, observations, hypotheses, insights.
        """
        conn = self._store.connection

        row = conn.execute(
            "SELECT event_id FROM event_skeletons WHERE event_id = ?;", (event_id,)
        ).fetchone()
        if not row:
            raise TargetNotFoundError(f"Event skeleton '{event_id}' does not exist.")

        is_pinned = self.is_event_pinned(event_id)
        if is_pinned and not cascade:
            pin_reasons = self.get_event_pin_reasons(event_id)
            raise EventPinnedError(
                f"Cannot purge retention-pinned event '{event_id}'. "
                f"Active durable references exist: {pin_reasons}"
            )

        actions_performed: list[LifecycleAction] = []
        retracted_observations: list[str] = []
        recomputed_observations: list[str] = []
        retracted_hypotheses: list[str] = []
        revalidated_hypotheses: list[str] = []
        retracted_insights: list[str] = []
        revalidated_insights: list[str] = []
        surviving_memories: list[str] = []
        removed_memories: list[str] = []

        now_ts = datetime.now(UTC).isoformat()

        with self._store.transaction():
            # 1. Unlink from Episode Containers (IMPL-1: episode membership != pin)
            ep_links = self._prov_repo.get_event_episode_links(event_id)
            for el in ep_links:
                conn.execute(
                    "DELETE FROM episode_event_links WHERE episode_id = ? AND event_id = ?;",
                    (el.episode_id, event_id),
                )
                actions_performed.append(
                    LifecycleAction(
                        action_type="unlink_episode_event",
                        target_type="episode_event_link",
                        target_id=f"{el.episode_id}:{event_id}",
                    )
                )

            if cascade:
                # 2. Reinforcements
                event_reinfs = self._prov_repo.get_event_reinforcements(event_id)
                for er in event_reinfs:
                    conn.execute(
                        "DELETE FROM evidence_reinforcements WHERE reinforcement_id = ?;",
                        (er.reinforcement_id,),
                    )
                    actions_performed.append(
                        LifecycleAction(
                            action_type="delete_reinforcement",
                            target_type="evidence_reinforcement",
                            target_id=er.reinforcement_id,
                        )
                    )

                # 3. Semantic Memories
                primary_mems = self._prov_repo.get_event_primary_memories(event_id)
                mem_ids_to_process = {m.memory_id for m in primary_mems}
                mem_ids_to_process.update(er.memory_id for er in event_reinfs)

                affected_obs_set: set[str] = set()

                for mid in sorted(mem_ids_to_process):
                    mem = self._store.get_semantic_memory(mid)
                    if not mem:
                        continue
                    remaining_reinfs = self._prov_repo.get_memory_reinforcements(mid)
                    if remaining_reinfs:
                        first_r = remaining_reinfs[0]
                        if first_r.slice_id:
                            conn.execute(
                                "UPDATE semantic_memories SET source_slice_id = ?, "
                                "source_event_id = NULL WHERE memory_id = ?;",
                                (first_r.slice_id, mid),
                            )
                        elif first_r.event_id:
                            conn.execute(
                                "UPDATE semantic_memories SET source_slice_id = NULL, "
                                "source_event_id = ? WHERE memory_id = ?;",
                                (first_r.event_id, mid),
                            )
                        conn.execute(
                            "DELETE FROM evidence_reinforcements WHERE reinforcement_id = ?;",
                            (first_r.reinforcement_id,),
                        )
                        surviving_memories.append(mid)
                    else:
                        om_links = self._prov_repo.get_memory_observation_links(mid)
                        for oml in om_links:
                            affected_obs_set.add(oml.observation_id)
                            conn.execute(
                                "DELETE FROM observation_memory_links "
                                "WHERE observation_id = ? AND memory_id = ?;",
                                (oml.observation_id, mid),
                            )
                        conn.execute("DELETE FROM semantic_memories WHERE memory_id = ?;", (mid,))
                        removed_memories.append(mid)

                # 4. Observations
                direct_obs_links = self._prov_repo.get_event_observation_links(event_id)
                for dol in direct_obs_links:
                    affected_obs_set.add(dol.observation_id)
                    conn.execute(
                        "DELETE FROM observation_event_links "
                        "WHERE observation_id = ? AND event_id = ?;",
                        (dol.observation_id, event_id),
                    )

                retracted_obs_set: set[str] = set()
                for oid in sorted(affected_obs_set):
                    obs = self._store.get_observation(oid)
                    if not obs:
                        continue
                    rem_proof = self._prov_repo.count_observation_supporting_evidence(oid)
                    if rem_proof == 0:
                        conn.execute(
                            "UPDATE observations SET proof_count = 0, status = 'retracted', "
                            "updated_at = ? WHERE observation_id = ?;",
                            (now_ts, oid),
                        )
                        retracted_observations.append(oid)
                        retracted_obs_set.add(oid)
                    else:
                        conn.execute(
                            "UPDATE observations SET proof_count = ?, updated_at = ? "
                            "WHERE observation_id = ?;",
                            (rem_proof, now_ts, oid),
                        )
                        recomputed_observations.append(oid)

                # 5. Hypotheses
                hyp_ids: set[str] = set()
                for roid in retracted_obs_set:
                    for hl in self._prov_repo.get_observation_hypothesis_links(roid):
                        if hl.role == "supporting":
                            hyp_ids.add(hl.hypothesis_id)

                retracted_hyp_set: set[str] = set()
                for hid in sorted(hyp_ids):
                    active_count = self._prov_repo.count_hypothesis_active_observations(hid)
                    if active_count == 0:
                        conn.execute(
                            "UPDATE hypotheses SET status = 'retracted' WHERE hypothesis_id = ?;",
                            (hid,),
                        )
                        retracted_hypotheses.append(hid)
                        retracted_hyp_set.add(hid)
                    else:
                        conn.execute(
                            "UPDATE hypotheses SET status = 'revalidation_required' "
                            "WHERE hypothesis_id = ?;",
                            (hid,),
                        )
                        revalidated_hypotheses.append(hid)

                # 6. Confirmed Insights
                for hid in sorted(hyp_ids):
                    for ins in self._prov_repo.get_hypothesis_confirmed_insights(hid):
                        if hid in retracted_hyp_set:
                            conn.execute(
                                "UPDATE confirmed_insights SET status = 'retracted', "
                                "invalidated_at = ? WHERE insight_id = ? "
                                "AND status != 'retracted';",
                                (now_ts, ins.insight_id),
                            )
                            retracted_insights.append(ins.insight_id)
                        else:
                            conn.execute(
                                "UPDATE confirmed_insights SET status = 'revalidation_required' "
                                "WHERE insight_id = ? AND status = 'confirmed';",
                                (ins.insight_id,),
                            )
                            revalidated_insights.append(ins.insight_id)
            if before_physical_delete_hook:
                before_physical_delete_hook(event_id)

            # Physically delete event skeleton
            conn.execute("DELETE FROM event_skeletons WHERE event_id = ?;", (event_id,))
            actions_performed.append(
                LifecycleAction(
                    action_type="delete_event_skeleton",
                    target_type="event_skeleton",
                    target_id=event_id,
                    detail="Physically deleted event skeleton",
                )
            )

            # Fail-closed foreign key verification
            fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
            if fk_violations:
                raise DependencyClosureError(
                    f"Dependency closure failed: FK check violations: {fk_violations}"
                )

        return HardDeleteResult(
            success=True,
            target_type="event",
            target_id=event_id,
            deleted_base_evidence=True,
            actions_performed=actions_performed,
            retracted_observations=retracted_observations,
            recomputed_observations=recomputed_observations,
            retracted_hypotheses=retracted_hypotheses,
            revalidated_hypotheses=revalidated_hypotheses,
            retracted_insights=retracted_insights,
            revalidated_insights=revalidated_insights,
            surviving_memories=surviving_memories,
            removed_memories=removed_memories,
            foreign_key_check_passed=True,
        )

    def purge_event(self, event_id: str) -> HardDeleteResult:
        """Purge an unpinned event skeleton.

        Fails closed with EventPinnedError if the event is currently retention-pinned.
        """
        return self.hard_delete_event(event_id, cascade=False)


# Canonical alias for compatibility
MemoryLifecycleManager = LifecycleService
