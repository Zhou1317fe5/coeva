"""Typed provenance primitives and traversal models for Memory V2.1.

Part of Coeva Long-Term Memory V2.1 Stage 3 (WP-2).
Implements typed, non-polymorphic provenance references and relationship lookup.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from src.memory.v2.entities import (
    ChapterInsightLinkEntity,
    ChapterSliceLinkEntity,
    ConfirmedInsightEntity,
    EpisodeEventLinkEntity,
    EpisodeSliceLinkEntity,
    EvidenceReinforcementEntity,
    HypothesisObservationLinkEntity,
    ObservationEventLinkEntity,
    ObservationMemoryLinkEntity,
    ObservationSliceLinkEntity,
    SemanticMemoryEntity,
)

ProvenanceKind = Literal["slice", "event", "episode", "semantic_memory", "observation", "insight"]
ProvenanceRole = Literal[
    "primary_source",
    "reinforcement",
    "contextual_source",
    "supporting",
    "counter",
    "contextual",
    "citation",
]


@dataclass(frozen=True)
class ProvenanceRef:
    """Strongly typed pointer to an evidence or provenance node."""

    kind: ProvenanceKind
    target_id: str
    role: ProvenanceRole
    detail: str = ""


class ProvenanceRepository:
    """Typed traversal and relationship querying across canonical memory entities.

    Provides typed access to:
    - Raw slice dependents across episodes, semantic memories, observations, chapters
    - Event skeleton dependents across episodes, semantic memories, observations
    - Semantic memory dependents and reinforcement ledgers
    - Observation dependents across hypotheses and confirmed insights
    - Direct foreign-key safe reverse queries
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Raw Slice Dependents ──────────────────────────────────────────────────

    def get_slice_episode_links(self, slice_id: str) -> list[EpisodeSliceLinkEntity]:
        """Fetch all episode links citing a raw slice."""
        rows = self._conn.execute(
            "SELECT episode_id, slice_id, curation_source, linked_at "
            "FROM episode_slice_links WHERE slice_id = ?;",
            (slice_id,),
        ).fetchall()
        return [
            EpisodeSliceLinkEntity(
                episode_id=r["episode_id"],
                slice_id=r["slice_id"],
                curation_source=r["curation_source"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def get_slice_reinforcements(self, slice_id: str) -> list[EvidenceReinforcementEntity]:
        """Fetch all evidence reinforcements backed by this slice."""
        rows = self._conn.execute(
            "SELECT reinforcement_id, memory_id, slice_id, event_id, "
            "independence_fingerprint, occurred_at "
            "FROM evidence_reinforcements WHERE slice_id = ?;",
            (slice_id,),
        ).fetchall()
        return [
            EvidenceReinforcementEntity(
                reinforcement_id=r["reinforcement_id"],
                memory_id=r["memory_id"],
                slice_id=r["slice_id"],
                event_id=r["event_id"],
                independence_fingerprint=r["independence_fingerprint"],
                occurred_at=r["occurred_at"],
            )
            for r in rows
        ]

    def get_slice_primary_memories(self, slice_id: str) -> list[SemanticMemoryEntity]:
        """Fetch all semantic memories where this slice is the primary source."""
        rows = self._conn.execute(
            "SELECT * FROM semantic_memories WHERE source_slice_id = ?;",
            (slice_id,),
        ).fetchall()
        return [
            SemanticMemoryEntity(
                memory_id=r["memory_id"],
                category=r["category"],
                statement=r["statement"],
                authority_class=r["authority_class"],
                scope=r["scope"],
                valid_from=r["valid_from"],
                validity_status=r["validity_status"],
                project_id=r["project_id"],
                source_slice_id=r["source_slice_id"],
                source_event_id=r["source_event_id"],
                source_episode_id=r["source_episode_id"],
                invalidated_at=r["invalidated_at"],
                superseded_by=r["superseded_by"],
                expression_policy=r["expression_policy"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_slice_observation_links(self, slice_id: str) -> list[ObservationSliceLinkEntity]:
        """Fetch all observation links citing a raw slice."""
        rows = self._conn.execute(
            "SELECT observation_id, slice_id, role, linked_at "
            "FROM observation_slice_links WHERE slice_id = ?;",
            (slice_id,),
        ).fetchall()
        return [
            ObservationSliceLinkEntity(
                observation_id=r["observation_id"],
                slice_id=r["slice_id"],
                role=r["role"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def get_slice_chapter_links(self, slice_id: str) -> list[ChapterSliceLinkEntity]:
        """Fetch all chapter links citing a raw slice."""
        rows = self._conn.execute(
            "SELECT chapter_id, slice_id, linked_at FROM chapter_slice_links WHERE slice_id = ?;",
            (slice_id,),
        ).fetchall()
        return [
            ChapterSliceLinkEntity(
                chapter_id=r["chapter_id"],
                slice_id=r["slice_id"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    # ── Event Skeleton Dependents ─────────────────────────────────────────────

    def get_event_episode_links(self, event_id: str) -> list[EpisodeEventLinkEntity]:
        """Fetch all episode links citing an event skeleton."""
        rows = self._conn.execute(
            "SELECT episode_id, event_id, curation_source, linked_at "
            "FROM episode_event_links WHERE event_id = ?;",
            (event_id,),
        ).fetchall()
        return [
            EpisodeEventLinkEntity(
                episode_id=r["episode_id"],
                event_id=r["event_id"],
                curation_source=r["curation_source"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def get_event_reinforcements(self, event_id: str) -> list[EvidenceReinforcementEntity]:
        """Fetch all evidence reinforcements backed by this event skeleton."""
        rows = self._conn.execute(
            "SELECT reinforcement_id, memory_id, slice_id, event_id, "
            "independence_fingerprint, occurred_at "
            "FROM evidence_reinforcements WHERE event_id = ?;",
            (event_id,),
        ).fetchall()
        return [
            EvidenceReinforcementEntity(
                reinforcement_id=r["reinforcement_id"],
                memory_id=r["memory_id"],
                slice_id=r["slice_id"],
                event_id=r["event_id"],
                independence_fingerprint=r["independence_fingerprint"],
                occurred_at=r["occurred_at"],
            )
            for r in rows
        ]

    def get_event_primary_memories(self, event_id: str) -> list[SemanticMemoryEntity]:
        """Fetch all semantic memories where this event is the primary source."""
        rows = self._conn.execute(
            "SELECT * FROM semantic_memories WHERE source_event_id = ?;",
            (event_id,),
        ).fetchall()
        return [
            SemanticMemoryEntity(
                memory_id=r["memory_id"],
                category=r["category"],
                statement=r["statement"],
                authority_class=r["authority_class"],
                scope=r["scope"],
                valid_from=r["valid_from"],
                validity_status=r["validity_status"],
                project_id=r["project_id"],
                source_slice_id=r["source_slice_id"],
                source_event_id=r["source_event_id"],
                source_episode_id=r["source_episode_id"],
                invalidated_at=r["invalidated_at"],
                superseded_by=r["superseded_by"],
                expression_policy=r["expression_policy"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_event_observation_links(self, event_id: str) -> list[ObservationEventLinkEntity]:
        """Fetch all observation links citing an event skeleton."""
        rows = self._conn.execute(
            "SELECT observation_id, event_id, role, linked_at "
            "FROM observation_event_links WHERE event_id = ?;",
            (event_id,),
        ).fetchall()
        return [
            ObservationEventLinkEntity(
                observation_id=r["observation_id"],
                event_id=r["event_id"],
                role=r["role"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    # ── Semantic Memory Dependents & Provenance ───────────────────────────────

    def get_memory_reinforcements(self, memory_id: str) -> list[EvidenceReinforcementEntity]:
        """Fetch all reinforcement entries for a semantic memory."""
        rows = self._conn.execute(
            "SELECT reinforcement_id, memory_id, slice_id, event_id, "
            "independence_fingerprint, occurred_at "
            "FROM evidence_reinforcements WHERE memory_id = ?;",
            (memory_id,),
        ).fetchall()
        return [
            EvidenceReinforcementEntity(
                reinforcement_id=r["reinforcement_id"],
                memory_id=r["memory_id"],
                slice_id=r["slice_id"],
                event_id=r["event_id"],
                independence_fingerprint=r["independence_fingerprint"],
                occurred_at=r["occurred_at"],
            )
            for r in rows
        ]

    def get_memory_observation_links(self, memory_id: str) -> list[ObservationMemoryLinkEntity]:
        """Fetch all observation links citing this semantic memory."""
        rows = self._conn.execute(
            "SELECT observation_id, memory_id, role, linked_at "
            "FROM observation_memory_links WHERE memory_id = ?;",
            (memory_id,),
        ).fetchall()
        return [
            ObservationMemoryLinkEntity(
                observation_id=r["observation_id"],
                memory_id=r["memory_id"],
                role=r["role"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    # ── Observation Dependents ────────────────────────────────────────────────

    def get_observation_hypothesis_links(
        self, observation_id: str
    ) -> list[HypothesisObservationLinkEntity]:
        """Fetch all hypothesis links citing an observation."""
        rows = self._conn.execute(
            "SELECT hypothesis_id, observation_id, role, is_primary, linked_at "
            "FROM hypothesis_observation_links WHERE observation_id = ?;",
            (observation_id,),
        ).fetchall()
        return [
            HypothesisObservationLinkEntity(
                hypothesis_id=r["hypothesis_id"],
                observation_id=r["observation_id"],
                role=r["role"],
                is_primary=r["is_primary"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    def count_observation_supporting_evidence(
        self,
        observation_id: str,
        *,
        excluding_slice_id: str | None = None,
        excluding_event_id: str | None = None,
        excluding_memory_id: str | None = None,
    ) -> int:
        """Count remaining valid independent supporting links for an observation.

        Notice: Only role='supporting' counts toward proof_count.
        Counter ('counter') and contextual links do NOT count as positive proof.
        """
        # 1. Slices
        slice_query = (
            "SELECT COUNT(*) FROM observation_slice_links osl "
            "JOIN raw_slices rs ON osl.slice_id = rs.slice_id "
            "WHERE osl.observation_id = ? AND osl.role = 'supporting'"
        )
        params: list[str] = [observation_id]
        if excluding_slice_id:
            slice_query += " AND osl.slice_id != ?"
            params.append(excluding_slice_id)
        slice_count = int(self._conn.execute(slice_query, tuple(params)).fetchone()[0])

        # 2. Events
        event_query = (
            "SELECT COUNT(*) FROM observation_event_links oel "
            "JOIN event_skeletons es ON oel.event_id = es.event_id "
            "WHERE oel.observation_id = ? AND oel.role = 'supporting'"
        )
        e_params: list[str] = [observation_id]
        if excluding_event_id:
            event_query += " AND oel.event_id != ?"
            e_params.append(excluding_event_id)
        event_count = int(self._conn.execute(event_query, tuple(e_params)).fetchone()[0])

        # 3. Active Semantic Memories
        mem_query = (
            "SELECT COUNT(*) FROM observation_memory_links oml "
            "JOIN semantic_memories sm ON oml.memory_id = sm.memory_id "
            "WHERE oml.observation_id = ? AND oml.role = 'supporting' "
            "AND sm.validity_status = 'active'"
        )
        m_params: list[str] = [observation_id]
        if excluding_memory_id:
            mem_query += " AND oml.memory_id != ?"
            m_params.append(excluding_memory_id)
        mem_count = int(self._conn.execute(mem_query, tuple(m_params)).fetchone()[0])

        return slice_count + event_count + mem_count

    # ── Hypothesis & Confirmed Insights ───────────────────────────────────────

    def get_hypothesis_confirmed_insights(self, hypothesis_id: str) -> list[ConfirmedInsightEntity]:
        """Fetch all confirmed insights derived from this hypothesis."""
        rows = self._conn.execute(
            "SELECT * FROM confirmed_insights WHERE source_hypothesis_id = ?;",
            (hypothesis_id,),
        ).fetchall()
        return [
            ConfirmedInsightEntity(
                insight_id=r["insight_id"],
                source_hypothesis_id=r["source_hypothesis_id"],
                source_calibration_id=r["source_calibration_id"],
                statement=r["statement"],
                valid_from=r["valid_from"],
                invalidated_at=r["invalidated_at"],
                superseded_by=r["superseded_by"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def count_hypothesis_active_observations(
        self,
        hypothesis_id: str,
        *,
        excluding_observation_id: str | None = None,
    ) -> int:
        """Count active supporting observations for a hypothesis."""
        query = (
            "SELECT COUNT(*) FROM hypothesis_observation_links hol "
            "JOIN observations obs ON hol.observation_id = obs.observation_id "
            "WHERE hol.hypothesis_id = ? AND hol.role = 'supporting' "
            "AND obs.status = 'active'"
        )
        params: list[str] = [hypothesis_id]
        if excluding_observation_id:
            query += " AND hol.observation_id != ?"
            params.append(excluding_observation_id)
        return int(self._conn.execute(query, tuple(params)).fetchone()[0])

    def get_insight_chapter_links(self, insight_id: str) -> list[ChapterInsightLinkEntity]:
        """Fetch all chapter links citing a confirmed insight."""
        rows = self._conn.execute(
            "SELECT chapter_id, insight_id, linked_at "
            "FROM chapter_insight_links WHERE insight_id = ?;",
            (insight_id,),
        ).fetchall()
        return [
            ChapterInsightLinkEntity(
                chapter_id=r["chapter_id"],
                insight_id=r["insight_id"],
                linked_at=r["linked_at"],
            )
            for r in rows
        ]

    # ── Event Retention Pinning Determination ─────────────────────────────────

    def is_event_durable_pinned(self, event_id: str) -> bool:
        """Determine whether an event is retention-pinned by durable provenance.

        Enforces IMPL-1:
        - Episode membership alone does NOT pin an event (episode_event_links only -> NOT pinned).
        - Direct adoption by active Observation (observation_event_links) pins the event.
        - Primary source or reinforcement of active Semantic Memory pins the event.
        """
        # Check active observations referencing this event
        obs_count = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM observation_event_links oel "
                "JOIN observations obs ON oel.observation_id = obs.observation_id "
                "WHERE oel.event_id = ? AND obs.status = 'active';",
                (event_id,),
            ).fetchone()[0]
        )
        if obs_count > 0:
            return True

        # Check active semantic memories having this event as primary source
        mem_count = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM semantic_memories "
                "WHERE source_event_id = ? AND validity_status = 'active';",
                (event_id,),
            ).fetchone()[0]
        )
        if mem_count > 0:
            return True

        # Check active semantic memories reinforced by this event
        reinf_count = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM evidence_reinforcements er "
                "JOIN semantic_memories sm ON er.memory_id = sm.memory_id "
                "WHERE er.event_id = ? AND sm.validity_status = 'active';",
                (event_id,),
            ).fetchone()[0]
        )
        if reinf_count > 0:
            return True

        return False
