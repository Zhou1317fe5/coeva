"""Centralized configuration and weights for Technical Retrieval V2.1.

Authoritative mapping to:
- docs/memory-v2/retrieval/retrieval-decision-record.md (Decision 6)
- docs/memory-v2/retrieval/technical-retrieval-design.md (§15, §16)
No scattered magic numbers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalConfig:
    """Frozen tuning parameters and operational bounds (V2.1 Frozen Calibration)."""

    # Fusion weights
    lexical_weight: float = 0.6
    surface_weight: float = 0.4

    # Confidence threshold for NO_RELEVANT_MEMORY gating
    confidence_threshold: float = 0.16

    # Intent category boosts (proven frozen baseline calibration)
    rule_intent_boost: float = 0.30
    historical_superseded_boost: float = 0.20
    past_episode_boost: float = 0.25
    project_tech_boost: float = 0.15

    # Top-K candidate capacity delivered to Recall Gate
    top_k: int = 3

    # FTS5 lexical parameters
    bigram_weight: float = 2.0
    unigram_weight: float = 0.5


DEFAULT_RETRIEVAL_CONFIG = RetrievalConfig()
