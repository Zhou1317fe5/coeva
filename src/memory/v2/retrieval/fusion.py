"""Stage 4 & Stage 5: Multi-Channel Fusion, Ranking, and Deterministic Gating.

Authoritative mapping to:
- docs/memory-v2/retrieval/technical-retrieval-design.md
  (§15 Fusion & Ranking, §16 NO_MEMORY Policy)
- docs/memory-v2/retrieval/retrieval-decision-record.md (Decision 6)

Fusion Formula (Frozen Technical Defaults):
    Score = 0.6 * Lexical + 0.4 * Surface + Category_Boost
    Category Boosts:
    - Relationship rule match on rule query: +0.30
    - Past episode/narrative match on historical debug query: +0.25
    - Active project tech stack query: +0.15

Threshold Gating:
    final_score >= confidence_threshold (default 0.15)
    If below threshold or candidate list empty -> NO_RELEVANT_MEMORY
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.memory.v2.retrieval.models import RetrievedCandidate

if TYPE_CHECKING:
    from src.memory.v2.retrieval.config import RetrievalConfig
    from src.memory.v2.retrieval.intent import IntentResolutionResult
    from src.memory.v2.retrieval.models import CanonicalCandidateRecord, RetrievalQueryContext


class FusionRanker:
    """Combines lexical and surface similarity channels,
    applies intent boosts, and gates candidates.
    """

    def __init__(self, config: RetrievalConfig) -> None:
        self.config = config

    def get_boost_policy(self) -> dict[str, float]:
        """Enumerate the active boost policy.

        Strictly frozen explicit ranking boosts:
        - rule_intent_boost: 0.30
        - historical_superseded_boost: 0.20
        """
        return {
            "rule_intent_boost": self.config.rule_intent_boost,
            "historical_superseded_boost": self.config.historical_superseded_boost,
        }

    def rank_and_gate(
        self,
        scored_candidates: list[tuple[CanonicalCandidateRecord, float, float]],
        ctx: RetrievalQueryContext,
        intent: IntentResolutionResult,
    ) -> list[RetrievedCandidate]:
        """Apply fusion weighting, category boosts, threshold gating,
        and return top-K candidates.
        """
        fused_list: list[tuple[float, float, float, float, CanonicalCandidateRecord]] = []
        for record, lex_score, surf_score in scored_candidates:
            channel_score = (
                self.config.lexical_weight * lex_score + self.config.surface_weight * surf_score
            )

            # Strictly frozen explicit ranking boosts only:
            cat_boost = 0.0
            if intent.is_rule_query and record.category == "relationship_rule":
                cat_boost += self.config.rule_intent_boost
            if (
                intent.is_past_query
                and record.validity_status == "superseded"
                and channel_score > 0.05
            ):
                cat_boost += self.config.historical_superseded_boost

            final_score = channel_score + cat_boost

            if round(final_score, 2) >= self.config.confidence_threshold:
                fused_list.append((final_score, lex_score, surf_score, cat_boost, record))

        # Sort descending by final score
        fused_list.sort(key=lambda x: x[0], reverse=True)

        # Select Top-K
        top_candidates = fused_list[: self.config.top_k]

        results: list[RetrievedCandidate] = []
        for final_score, lex, surf, boost, rec in top_candidates:
            why = (
                f"fusion(score={final_score:.3f}, lex={lex:.3f}, "
                f"surf={surf:.3f}, boost={boost:.2f})"
            )
            cand = RetrievedCandidate(
                candidate_id=rec.candidate_id,
                candidate_type=rec.candidate_type,
                statement=rec.statement,
                provenance_refs=rec.provenance_refs,
                scope=rec.scope,
                project_id=rec.project_id,
                valid_from=rec.valid_from,
                validity_status=rec.validity_status,
                authority_class=rec.authority_class,
                proof_count=rec.proof_count,
                lexical_score=round(lex, 4),
                surface_score=round(surf, 4),
                final_score=round(final_score, 4),
                why_retrieved=why,
                is_ambiguous=(rec.validity_status == "ambiguous"),
            )
            results.append(cand)

        return results
