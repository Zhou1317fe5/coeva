"""Technical Retrieval V2.1 Pipeline (Assembly).

Authoritative mapping to:
- Prompt §2: Technical Retrieval Pipeline topology
- Prompt §10: Retrieval ≠ Injection ≠ Spoken (pure Candidate[] output, no injection, no speech)
- docs/memory-v2/retrieval/technical-retrieval-design.md
- docs/memory-v2/retrieval/retrieval-decision-record.md

Pipeline Flow:
    Query Context
         ↓
    Stage 1: Intent Resolution & Fast-Gate Precedence
         ↓
    Stage 2: Target Selection & Hard Eligibility Filters (IMPL-3, Scope, Validity)
         ↓
    Stage 3: Multi-Channel Candidate Generation (Lexical FTS5 + Surface Sim + Temporal)
         ↓
    Stage 4 & 5: Frozen Fusion Ranking & Threshold Gating (0.6 / 0.4 / 0.15)
         ↓
    RetrievalResult (RetrievedCandidate[] / NO_RELEVANT_MEMORY)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from src.memory.v2.retrieval.config import DEFAULT_RETRIEVAL_CONFIG, RetrievalConfig
from src.memory.v2.retrieval.eligibility import HardEligibilityFilter
from src.memory.v2.retrieval.fusion import FusionRanker
from src.memory.v2.retrieval.intent import IntentResolver
from src.memory.v2.retrieval.lexical import compute_lexical_score, tokenize_text
from src.memory.v2.retrieval.models import (
    CanonicalCandidateRecord,
    RetrievalQueryContext,
    RetrievalResult,
    RetrievedCandidate,
)
from src.memory.v2.retrieval.surface import SurfaceSimilarityChannel
from src.memory.v2.retrieval.temporal import TemporalContextualChannel

if TYPE_CHECKING:
    from src.memory.v2.retrieval.repository import (
        RetrievalRepository,
        StaticCandidateRepository,
    )


class TechnicalRetrievalPipeline:
    """The authoritative Technical Retrieval V2.1 Pipeline."""

    def __init__(
        self,
        repository: RetrievalRepository | StaticCandidateRepository,
        config: RetrievalConfig | None = None,
    ) -> None:
        self.repository = repository
        self.config = config or DEFAULT_RETRIEVAL_CONFIG

        self.intent_resolver = IntentResolver()
        self.eligibility_filter = HardEligibilityFilter()
        self.temporal_channel = TemporalContextualChannel()
        self.fusion_ranker = FusionRanker(self.config)

        # Build surface similarity channel from canonical candidates
        self._canonical_cache: list[CanonicalCandidateRecord] = []
        self.surface_channel = SurfaceSimilarityChannel()
        self.refresh_index()

    def refresh_index(self) -> None:
        """Reload canonical candidates and re-fit surface similarity vector space."""
        self._canonical_cache = self.repository.load_all_canonical_candidates()
        self.surface_channel = SurfaceSimilarityChannel(
            cand.statement for cand in self._canonical_cache
        )

    def retrieve(self, ctx: RetrievalQueryContext) -> RetrievalResult:
        """Execute the five-stage technical retrieval pipeline."""
        t_start = time.perf_counter()
        clean_q = ctx.query_text.strip()

        # Empty query -> Early return NO_RELEVANT_MEMORY
        if not clean_q:
            return self._build_no_memory_result(ctx, "NO_MEMORY_NEEDED", t_start, "EMPTY_QUERY")

        # ── Stage 1: Intent Resolution & Fast-Gate Precedence ──
        intent = self.intent_resolver.resolve(ctx)
        if intent.should_early_terminate:
            return self._build_no_memory_result(
                ctx, intent.mode, t_start, intent.early_termination_reason
            )

        # ── Stage 2: Temporal / Task Continuity Shortcut (P0) ──
        if intent.is_continuity:
            shortcut_ep = self.temporal_channel.find_recent_task_continuity_candidate(
                self._canonical_cache, ctx.current_project_id
            )
            if shortcut_ep is not None:
                # Wrap as single candidate
                cand = RetrievedCandidate(
                    candidate_id=shortcut_ep.candidate_id,
                    candidate_type=shortcut_ep.candidate_type,
                    statement=shortcut_ep.statement,
                    provenance_refs=shortcut_ep.provenance_refs,
                    scope=shortcut_ep.scope,
                    project_id=shortcut_ep.project_id,
                    valid_from=shortcut_ep.valid_from,
                    validity_status=shortcut_ep.validity_status,
                    authority_class=shortcut_ep.authority_class,
                    proof_count=shortcut_ep.proof_count,
                    lexical_score=1.0,
                    surface_score=1.0,
                    final_score=1.0,
                    why_retrieved="task_continuity_shortcut",
                    is_ambiguous=False,
                )
                lat_ms = (time.perf_counter() - t_start) * 1000.0
                return RetrievalResult(
                    status="SUCCESS",
                    candidates=(cand,),
                    query_context=ctx,
                    retrieval_mode=intent.mode,
                    diagnostics={"latency_ms": round(lat_ms, 3), "shortcut": True},
                )
            else:
                return self._build_no_memory_result(
                    ctx, intent.mode, t_start, "NO_CONTINUITY_EPISODE"
                )

        # ── Stage 3: Eligibility Filtering ──
        eligible_candidates: list[CanonicalCandidateRecord] = []
        for c in self._canonical_cache:
            if self.eligibility_filter.is_eligible(c, ctx, intent):
                eligible_candidates.append(c)

        if not eligible_candidates:
            return self._build_no_memory_result(ctx, intent.mode, t_start, "NO_ELIGIBLE_CANDIDATES")

        # ── Stage 4: Multi-Channel Scoring (Lexical + Surface) ──
        q_tokens = tokenize_text(clean_q)
        q_vec = self.surface_channel.vectorize(clean_q)

        scored: list[tuple[CanonicalCandidateRecord, float, float]] = []
        for c in eligible_candidates:
            d_tokens = tokenize_text(c.statement)
            lex_score = compute_lexical_score(
                q_tokens,
                d_tokens,
                bigram_weight=self.config.bigram_weight,
                unigram_weight=self.config.unigram_weight,
            )
            d_vec = self.surface_channel.vectorize(c.statement)
            surf_score = self.surface_channel.compute_similarity(q_vec, d_vec)
            scored.append((c, lex_score, surf_score))

        # ── Stage 5: Fusion Ranking & Threshold Gating ──
        final_candidates = self.fusion_ranker.rank_and_gate(scored, ctx, intent)

        lat_ms = (time.perf_counter() - t_start) * 1000.0
        if not final_candidates:
            return self._build_no_memory_result(
                ctx, intent.mode, t_start, "BELOW_CONFIDENCE_THRESHOLD"
            )

        return RetrievalResult(
            status="SUCCESS",
            candidates=tuple(final_candidates),
            query_context=ctx,
            retrieval_mode=intent.mode,
            diagnostics={
                "latency_ms": round(lat_ms, 3),
                "eligible_count": len(eligible_candidates),
                "returned_count": len(final_candidates),
            },
        )

    def _build_no_memory_result(
        self,
        ctx: RetrievalQueryContext,
        mode: str,
        t_start: float,
        reason: str,
        extra_diag: dict[str, Any] | None = None,
    ) -> RetrievalResult:
        lat_ms = (time.perf_counter() - t_start) * 1000.0
        diag = {"latency_ms": round(lat_ms, 3), "silence_reason": reason}
        if extra_diag:
            diag.update(extra_diag)
        return RetrievalResult(
            status="NO_RELEVANT_MEMORY",
            candidates=(),
            query_context=ctx,
            retrieval_mode=mode,
            diagnostics=diag,
        )
