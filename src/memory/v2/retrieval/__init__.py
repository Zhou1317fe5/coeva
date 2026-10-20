"""Technical Retrieval V2.1 package for Co-evolving Companion.

Delivers:
- TechnicalRetrievalPipeline
- RetrievalQueryContext, RetrievedCandidate, ProvenanceRef, RetrievalResult
- RetrievalConfig, DEFAULT_RETRIEVAL_CONFIG
- RetrievalRepository, StaticCandidateRepository
- IntentResolver, HardEligibilityFilter, FusionRanker
"""

from __future__ import annotations

from src.memory.v2.retrieval.config import DEFAULT_RETRIEVAL_CONFIG, RetrievalConfig
from src.memory.v2.retrieval.eligibility import HardEligibilityFilter
from src.memory.v2.retrieval.fusion import FusionRanker
from src.memory.v2.retrieval.intent import IntentResolutionResult, IntentResolver
from src.memory.v2.retrieval.lexical import compute_lexical_score, tokenize_text
from src.memory.v2.retrieval.models import (
    CanonicalCandidateRecord,
    ProvenanceRef,
    RetrievalMode,
    RetrievalQueryContext,
    RetrievalResult,
    RetrievalStatus,
    RetrievedCandidate,
)
from src.memory.v2.retrieval.pipeline import TechnicalRetrievalPipeline
from src.memory.v2.retrieval.repository import RetrievalRepository, StaticCandidateRepository
from src.memory.v2.retrieval.surface import SurfaceSimilarityChannel
from src.memory.v2.retrieval.temporal import TemporalContextualChannel

__all__ = [
    "TechnicalRetrievalPipeline",
    "RetrievalQueryContext",
    "RetrievedCandidate",
    "ProvenanceRef",
    "RetrievalResult",
    "CanonicalCandidateRecord",
    "RetrievalMode",
    "RetrievalStatus",
    "RetrievalConfig",
    "DEFAULT_RETRIEVAL_CONFIG",
    "RetrievalRepository",
    "StaticCandidateRepository",
    "IntentResolver",
    "IntentResolutionResult",
    "HardEligibilityFilter",
    "FusionRanker",
    "SurfaceSimilarityChannel",
    "TemporalContextualChannel",
    "tokenize_text",
    "compute_lexical_score",
]
