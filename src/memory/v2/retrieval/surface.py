"""Surface Similarity Channel: Statistical text similarity via N-gram vector space.

Authoritative mapping to:
- docs/memory-v2/retrieval/technical-retrieval-design.md (§12 Surface Similarity Channel Design)
- docs/memory-v2/retrieval/retrieval-decision-record.md (Decision 3)

Features:
- Pure Python in-memory N-gram vectorizer.
- L2-normalized cosine similarity space.
- Zero external heavy ML / ONNX / PyTorch dependencies.
- Sub-millisecond latency (< 1.5ms).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from src.memory.v2.retrieval.lexical import tokenize_text


class SurfaceSimilarityChannel:
    """Lightweight statistical surface similarity channel using N-gram vector cosine space."""

    def __init__(self, corpus_texts: Iterable[str] | None = None) -> None:
        self.vocab: dict[str, int] = {}
        if corpus_texts is not None:
            self.fit(corpus_texts)

    def fit(self, texts: Iterable[str]) -> None:
        """Build or update vocabulary from document statements."""
        for text in texts:
            for token in tokenize_text(text):
                if token not in self.vocab:
                    self.vocab[token] = len(self.vocab)

    def vectorize(self, text: str) -> list[float]:
        """Convert text into L2-normalized token frequency vector."""
        if not self.vocab:
            return []

        toks = tokenize_text(text)
        vec = [0.0] * len(self.vocab)
        for t in toks:
            idx = self.vocab.get(t)
            if idx is not None:
                vec[idx] += 1.0

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            return [v / norm for v in vec]
        return vec

    def compute_similarity(self, q_vec: list[float], d_vec: list[float]) -> float:
        """Compute cosine similarity between two normalized vectors."""
        if not q_vec or not d_vec:
            return 0.0
        return sum(qv * dv for qv, dv in zip(q_vec, d_vec, strict=False))
