"""Injection Policy and Minimal Context Formatting for Memory V2.1.

Authoritative mapping to:
- WP-8 Recall Gate & Sanctuary Mode Integration
- Core invariant: Retrieved != Injected != Spoken
- Minimal injection principle: smallest sufficient candidate set, no duplicate
  propositions, no unrelated historical context, preserve provenance IDs,
  no technical metadata tables, no raw external Agent prompt/CoT/tool output.
- Anti-echo safety: distinguishable origin (retrieved_memory_context != user_evidence).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from src.memory.v2.retrieval.models import ProvenanceRef, RetrievedCandidate

InjectedOrigin = Literal["retrieved_memory_context"]


@dataclass(frozen=True)
class InjectedMemoryItem:
    """Sanitized, policy-approved memory item allowed into downstream model context.

    Carries declarative statement and provenance identity, strictly excluding
    all technical retrieval metadata tables (lexical/surface scores, why_retrieved,
    internal token vectors, SQL columns).
    """

    candidate_id: str
    statement: str
    candidate_type: str
    provenance_refs: tuple[ProvenanceRef, ...]
    authority_class: str
    scope: str
    project_id: str | None = None
    origin: InjectedOrigin = "retrieved_memory_context"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "statement": self.statement,
            "candidate_type": self.candidate_type,
            "provenance_refs": [p.to_dict() for p in self.provenance_refs],
            "authority_class": self.authority_class,
            "scope": self.scope,
            "project_id": self.project_id,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class InjectionContext:
    """Structured context containing only allowed memory items ready for downstream use."""

    items: tuple[InjectedMemoryItem, ...]
    disposition: str
    reason: str
    observability_category: str

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0

    def candidate_ids(self) -> list[str]:
        return [item.candidate_id for item in self.items]

    def format_for_prompt(self) -> str:
        """Format allowed memory items for model prompt without any technical metadata."""
        if not self.items:
            return ""
        lines = ["[Retrieved Memory Context]"]
        for item in self.items:
            lines.append(f"- {item.statement}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "reason": self.reason,
            "observability_category": self.observability_category,
            "items": [item.to_dict() for item in self.items],
            "formatted_context": self.format_for_prompt(),
        }


def _normalize_statement(text: str) -> str:
    """Normalize statement for duplicate proposition detection."""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower())
    return cleaned if cleaned else text.strip().lower()


def _proposition_similarity(a: str, b: str) -> float:
    """Compute character bigram Jaccard similarity between two propositions."""
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 1.0 if a == b else 0.0
    bigrams_a = {a[i : i + 2] for i in range(len(a) - 1)}
    bigrams_b = {b[i : i + 2] for i in range(len(b) - 1)}
    union = bigrams_a | bigrams_b
    if not union:
        return 0.0
    return len(bigrams_a & bigrams_b) / len(union)


class MinimalInjectionPolicy:
    """Enforces the minimal injection principle and proposition deduplication."""

    def __init__(
        self,
        max_items: int = 3,
        max_continuity_items: int = 1,
        duplicate_similarity_threshold: float = 0.85,
    ) -> None:
        self.max_items = max_items
        self.max_continuity_items = max_continuity_items
        self.duplicate_similarity_threshold = duplicate_similarity_threshold

    def process(
        self,
        allowed_candidates: Sequence[RetrievedCandidate],
        is_task_continuity: bool = False,
    ) -> tuple[tuple[InjectedMemoryItem, ...], tuple[RetrievedCandidate, ...]]:
        """Deduplicate redundant propositions, enforce budget limits, and construct
        clean InjectedMemoryItem tuples.

        Returns:
            (injected_items, redundant_or_overflow_candidates)
        """
        if not allowed_candidates:
            return (), ()

        limit = self.max_continuity_items if is_task_continuity else self.max_items

        chosen_candidates: list[RetrievedCandidate] = []
        redundant_candidates: list[RetrievedCandidate] = []
        seen_statements: list[str] = []

        for cand in allowed_candidates:
            norm = _normalize_statement(cand.statement)
            # Check for duplicate proposition against already accepted candidates
            is_dup = False
            for seen in seen_statements:
                if (
                    norm == seen
                    or _proposition_similarity(norm, seen) >= self.duplicate_similarity_threshold
                ):
                    is_dup = True
                    break

            if is_dup:
                redundant_candidates.append(cand)
                continue

            if len(chosen_candidates) < limit:
                chosen_candidates.append(cand)
                seen_statements.append(norm)
            else:
                redundant_candidates.append(cand)

        # Build InjectedMemoryItem items strictly stripping all scores & technical metadata
        injected_items: list[InjectedMemoryItem] = []
        for cand in chosen_candidates:
            injected_items.append(
                InjectedMemoryItem(
                    candidate_id=cand.candidate_id,
                    statement=cand.statement,
                    candidate_type=cand.candidate_type,
                    provenance_refs=cand.provenance_refs,
                    authority_class=cand.authority_class,
                    scope=cand.scope,
                    project_id=cand.project_id,
                    origin="retrieved_memory_context",
                )
            )

        return tuple(injected_items), tuple(redundant_candidates)
