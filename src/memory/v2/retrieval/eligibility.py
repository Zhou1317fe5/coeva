"""Stage 3: Hard Eligibility Filters and Scope Resolution.

Authoritative mapping to:
- docs/memory-v2/retrieval/technical-retrieval-design.md (§8 Scope Resolution, §14 Hard Filters)
- docs/memory-v2/retrieval/retrieval-decision-record.md (Decision 1, Decision 5)

Enforces:
1. IMPL-3: Privacy redaction pending (needs_privacy_redaction == 1) is physically unreadable.
2. Invalidation: validity_status == 'invalidated' is dropped.
3. Target selection & Sanctuary restrictions:
   - Narrative mode only selects chapter_metadata.
   - Non-narrative mode excludes chapter_metadata unless past narrative is explicit.
   - Sanctuary active drops confirmed_insights and 'do_not_mention' (frustration/distress).
4. Project Scope Isolation:
   - 'project' scope strictly requires project_id == current_project_id
     (or explicit cross-project match).
   - 'unresolved' scope is isolated from project context, never smuggled to global.
5. Validity & Supersession:
   - Current status queries drop validity_status == 'superseded'.
6. Temporal Constraints:
   - Explicit relative dates (e.g. yesterday) strictly bound calendar ranges.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.memory.v2.retrieval.intent import IntentResolutionResult
    from src.memory.v2.retrieval.models import CanonicalCandidateRecord, RetrievalQueryContext


class HardEligibilityFilter:
    """Deterministic filter evaluating candidates against frozen hard eligibility criteria."""

    def is_eligible(
        self,
        candidate: CanonicalCandidateRecord,
        ctx: RetrievalQueryContext,
        intent: IntentResolutionResult,
    ) -> bool:
        # ── Filter 1: IMPL-3 Privacy Redaction Pending ──
        if candidate.needs_privacy_redaction == 1:
            return False

        # ── Filter 2: Invalidation ──
        if candidate.validity_status == "invalidated":
            return False

        # ── Filter 3: Target Selection & Sanctuary Target Guard ──
        if intent.is_narrative_query:
            if candidate.candidate_type != "chapter_metadata":
                return False
        else:
            # Normal queries do not target chapter_metadata unless explicitly requested
            if candidate.candidate_type == "chapter_metadata":
                return False

        if ctx.sanctuary_active:
            # Psychological self-models / confirmed insights are strictly blocked under Sanctuary
            if candidate.candidate_type == "confirmed_insight":
                return False
            # Historical frustration/distress items marked do_not_mention are strictly blocked
            if candidate.expression_policy == "do_not_mention":
                return False

        # ── Filter 4: Scope Resolution & Isolation ──
        if candidate.scope == "unresolved":
            # Unresolved scope is never smuggled into current active project context
            return False
        elif candidate.scope == "project":
            if ctx.current_project_id is None:
                return False
            if candidate.project_id != ctx.current_project_id:
                # Project mismatch: check if query explicitly mentions the other project
                if not (candidate.project_id and candidate.project_id in ctx.query_text):
                    return False
        elif candidate.scope == "global":
            pass  # Global scope is universally readable
        else:
            return False

        # ── Filter 5: Temporal Validity & Supersession ──
        # Current state queries must NOT recall superseded historical records
        if not intent.is_past_query and candidate.validity_status == "superseded":
            return False

        # ── Filter 6: Temporal Calendar Constraints ──
        now = ctx.now or datetime.now(UTC)
        if intent.is_yesterday:
            try:
                cand_dt = datetime.fromisoformat(candidate.valid_from)
                diff_days = (now.date() - cand_dt.date()).days
                if diff_days != 1:
                    return False
            except (ValueError, TypeError):
                return False

        return True
