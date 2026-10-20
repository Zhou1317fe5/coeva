"""Temporal and Contextual Continuity Channel.

Authoritative mapping to:
- docs/memory-v2/retrieval/technical-retrieval-design.md (§13 Temporal & Contextual Channel Design)

Features:
- Context Continuity Shortcut: Weak reference and task error continuity
  ("和上次一样" / "又是刚才那个报错") directly shortcuts to latest project episode.
- Relative date constraints: Resolves yesterday, day before yesterday, last week.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.memory.v2.retrieval.models import CanonicalCandidateRecord


class TemporalContextualChannel:
    """Handles task continuity shortcuts and temporal date window filtering."""

    def resolve_relative_date(
        self,
        query: str,
        now: datetime | None = None,
    ) -> date | None:
        """Resolve explicit relative dates from query text."""
        ref_now = now or datetime.now(UTC)
        ref_date = ref_now.date()

        if "昨天" in query or "昨日" in query:
            return ref_date - timedelta(days=1)
        if "前天" in query:
            return ref_date - timedelta(days=2)
        if "大前天" in query:
            return ref_date - timedelta(days=3)
        return None

    def find_recent_task_continuity_candidate(
        self,
        candidates: Sequence[CanonicalCandidateRecord],
        current_project_id: str | None,
    ) -> CanonicalCandidateRecord | None:
        """Find the most recent project episode for task continuity shortcut."""
        if not current_project_id:
            return None

        matching_eps = [
            c
            for c in candidates
            if c.candidate_type == "episode"
            and c.scope == "project"
            and c.project_id == current_project_id
        ]
        if not matching_eps:
            return None

        # Sort by valid_from descending to get the most recent episode
        matching_eps.sort(key=lambda x: x.valid_from, reverse=True)
        return matching_eps[0]
