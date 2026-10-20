"""Recall Gate and Sanctuary Mode Policy Integration for Memory V2.1.

Authoritative mapping to:
- Prompt §1: WP-8 Recall Gate & Sanctuary Mode Integration
- Prompt §2: Authoritative Sanctuary semantics (Frozen/errata behavior)
- Prompt §3: Defense in depth (Second policy boundary, fail closed)
- Prompt §4: Recall decision model (RecallDecision, RecallDisposition, InjectionContext)
- Prompt §5: Minimal injection principle
- Prompt §6: 80 / 15 / 5 policy boundary (Silence first-class, observability categories)
- Prompt §7: Explicit user requests (Outside vs Inside Sanctuary)
- Prompt §8: Privacy & deletion (IMPL-3, TOCTOU safety)
- Prompt §9: Anti-echo safety (origin metadata distinction)
- Prompt §10: No retrieval retuning (Pure policy gating)
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from src.memory.v2.injection_policy import (
    InjectionContext,
    MinimalInjectionPolicy,
)
from src.memory.v2.retrieval.intent import (
    CONTINUITY_MARKERS,
    GENERIC_QA_PATTERNS,
    HISTORICAL_MARKERS,
    REFLECTIVE_MARKERS,
    RULE_MARKERS,
)
from src.memory.v2.retrieval.models import (
    RetrievalQueryContext,
    RetrievalResult,
    RetrievedCandidate,
)

if TYPE_CHECKING:
    from src.memory.v2.store import ChronicleStoreV2


class RecallDisposition(StrEnum):
    """Authoritative disposition choices for recall policy gating."""

    ALLOW = "ALLOW"
    SUPPRESS = "SUPPRESS"
    TASK_CONTINUITY_ONLY = "TASK_CONTINUITY_ONLY"
    NO_MEMORY = "NO_MEMORY"


class RecallReason:
    """Standard machine-readable reason codes (Prompt §4)."""

    PRIVACY_PENDING = "privacy_pending"
    SANCTUARY_REFLECTIVE_BLOCK = "sanctuary_reflective_block"
    SANCTUARY_PAST_FRUSTRATION_BLOCK = "sanctuary_past_frustration_block"
    TASK_CONTINUITY_ALLOWED = "task_continuity_allowed"
    EXPLICIT_HISTORY_ALLOWED = "explicit_history_allowed"
    EXPLICIT_RULE_ALLOWED = "explicit_rule_allowed"
    EXPLICIT_PREFERENCE_ALLOWED = "explicit_preference_allowed"
    FACTUAL_ALLOWED = "factual_allowed"
    REFLECTIVE_ALLOWED = "reflective_allowed"
    GENERIC_QA_SUPPRESSED = "generic_qa_suppressed"
    WEAK_RELEVANCE_SUPPRESSED = "weak_relevance_suppressed"
    SCOPE_MISMATCH = "scope_mismatch"
    UNRESOLVED_SCOPE_SUPPRESSED = "unresolved_scope_suppressed"
    INVALIDATED_SUPPRESSED = "invalidated_suppressed"
    SUPERSEDED_SUPPRESSED = "superseded_suppressed"
    REDUNDANT_SUPPRESSED = "redundant_suppressed"
    NO_CANDIDATES = "no_candidates"
    EMPTY_QUERY = "empty_query"


ObservabilityCategory = Literal[
    "silent",
    "factual_context",
    "reflective_context",
    "task_continuity",
]


@dataclass(frozen=True)
class RecallContext:
    """Evaluation context provided to Recall Gate."""

    query_text: str
    current_project_id: str | None = None
    sanctuary_active: bool = False
    explicit_historical_intent: bool = False
    current_session_id: str = ""
    now: datetime | None = None
    # Live hooks for TOCTOU checks
    live_validator: Callable[[str], Any] | None = None
    store: ChronicleStoreV2 | None = None

    @classmethod
    def from_query_context(
        cls,
        ctx: RetrievalQueryContext,
        live_validator: Callable[[str], Any] | None = None,
        store: ChronicleStoreV2 | None = None,
    ) -> RecallContext:
        """Convenience constructor from Technical Retrieval query context."""
        return cls(
            query_text=ctx.query_text,
            current_project_id=ctx.current_project_id,
            sanctuary_active=ctx.sanctuary_active,
            explicit_historical_intent=ctx.explicit_historical_intent,
            current_session_id=ctx.current_session_id,
            now=ctx.now,
            live_validator=live_validator,
            store=store,
        )


@dataclass(frozen=True)
class RecallDecision:
    """Output of Recall Gate decision boundary (Prompt §4)."""

    disposition: RecallDisposition
    reason: str
    observability_category: ObservabilityCategory
    allowed_candidates: tuple[RetrievedCandidate, ...]
    suppressed_candidates: tuple[RetrievedCandidate, ...]
    injection_context: InjectionContext

    @property
    def is_silent(self) -> bool:
        return (
            self.disposition in (RecallDisposition.SUPPRESS, RecallDisposition.NO_MEMORY)
            or len(self.allowed_candidates) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": str(self.disposition.value),
            "reason": self.reason,
            "observability_category": self.observability_category,
            "allowed_candidate_ids": [c.candidate_id for c in self.allowed_candidates],
            "suppressed_candidate_ids": [c.candidate_id for c in self.suppressed_candidates],
            "injection_context": self.injection_context.to_dict(),
        }


# Markers indicating historical frustration / distress / venting
FRUSTRATION_STATEMENT_MARKERS: tuple[str, ...] = (
    "烦躁",
    "崩溃",
    "受不了",
    "好烦",
    "心烦",
    "太累",
    "焦虑",
    "抱怨",
    "生气",
    "争吵",
    "死锁",
    "挫败",
)


def _is_task_continuity_query(text: str) -> bool:
    return any(w in text for w in CONTINUITY_MARKERS)


def _is_reflective_query(text: str) -> bool:
    return any(w in text for w in REFLECTIVE_MARKERS)


def _is_historical_query(text: str) -> bool:
    return any(w in text for w in HISTORICAL_MARKERS)


def _is_rule_query(text: str) -> bool:
    return any(w in text for w in RULE_MARKERS)


RECALL_GATE_GENERIC_QA_PATTERNS: tuple[str, ...] = (
    *GENERIC_QA_PATTERNS,
    r"怎么.*(?:排序|实现|使用|配置|安装|操作|反转)",
    r"如何.*(?:排序|实现|使用|配置|安装|操作|反转)",
)


def _is_generic_qa_query(text: str) -> bool:
    if _is_historical_query(text) or _is_rule_query(text) or _is_task_continuity_query(text):
        return False
    return any(re.search(pat, text) for pat in RECALL_GATE_GENERIC_QA_PATTERNS)


class RecallGate:
    """Second policy boundary enforcing Sanctuary mode, privacy, scope, and minimal injection."""

    def __init__(
        self,
        injection_policy: MinimalInjectionPolicy | None = None,
        min_relevance_threshold: float = 0.16,
    ) -> None:
        self.injection_policy = injection_policy or MinimalInjectionPolicy()
        self.min_relevance_threshold = min_relevance_threshold

    def evaluate(
        self,
        candidates: Sequence[RetrievedCandidate] | RetrievalResult,
        context: RecallContext | RetrievalQueryContext,
    ) -> RecallDecision:
        """Evaluate candidates against current context and Sanctuary policy, returning a
        strongly typed RecallDecision.
        """
        # Normalize context
        if isinstance(context, RetrievalQueryContext):
            rc_ctx = RecallContext.from_query_context(context)
        else:
            rc_ctx = context

        # Normalize candidates
        if isinstance(candidates, RetrievalResult):
            cands: Sequence[RetrievedCandidate] = candidates.candidates
        else:
            cands = candidates

        clean_q = rc_ctx.query_text.strip()

        # Step 0: Check empty query or empty candidates
        if not clean_q:
            return self._build_decision(
                disposition=RecallDisposition.NO_MEMORY,
                reason=RecallReason.EMPTY_QUERY,
                category="silent",
                allowed=(),
                suppressed=cands,
                injected_items=(),
            )

        if not cands:
            return self._build_decision(
                disposition=RecallDisposition.NO_MEMORY,
                reason=RecallReason.NO_CANDIDATES,
                category="silent",
                allowed=(),
                suppressed=(),
                injected_items=(),
            )

        # Step 1: Query-level policy fast gates
        is_continuity = _is_task_continuity_query(clean_q)
        is_reflective_q = _is_reflective_query(clean_q)
        is_past_q = rc_ctx.explicit_historical_intent or _is_historical_query(clean_q)
        is_rule_q = _is_rule_query(clean_q)

        # Sanctuary Mode: Reflective curiosity is strictly blocked
        if rc_ctx.sanctuary_active and is_reflective_q and not is_continuity:
            return self._build_decision(
                disposition=RecallDisposition.SUPPRESS,
                reason=RecallReason.SANCTUARY_REFLECTIVE_BLOCK,
                category="silent",
                allowed=(),
                suppressed=cands,
                injected_items=(),
            )

        # Generic QA check: generic queries without personal/historical markers remain silent
        if _is_generic_qa_query(clean_q):
            return self._build_decision(
                disposition=RecallDisposition.SUPPRESS,
                reason=RecallReason.GENERIC_QA_SUPPRESSED,
                category="silent",
                allowed=(),
                suppressed=cands,
                injected_items=(),
            )

        # Step 2: Candidate-by-candidate defense in depth checks (fail closed)
        passed_candidates: list[RetrievedCandidate] = []
        suppressed_candidates: list[RetrievedCandidate] = []
        suppression_reasons: list[str] = []

        for cand in cands:
            allowed, block_reason = self._check_candidate(cand, rc_ctx, is_past_q, is_continuity)
            if allowed:
                passed_candidates.append(cand)
            else:
                suppressed_candidates.append(cand)
                suppression_reasons.append(block_reason)

        # Step 3: Gating outcome resolution
        if not passed_candidates:
            # All candidates suppressed; select highest priority suppression reason
            primary_reason = self._select_primary_suppression_reason(suppression_reasons)
            return self._build_decision(
                disposition=RecallDisposition.SUPPRESS,
                reason=primary_reason,
                category="silent",
                allowed=(),
                suppressed=tuple(suppressed_candidates),
                injected_items=(),
            )

        # Candidates passed candidate-level checks! Now resolve disposition and category
        if rc_ctx.sanctuary_active:
            # Under Sanctuary, only minimal task continuity is allowed
            disposition = RecallDisposition.TASK_CONTINUITY_ONLY
            reason = RecallReason.TASK_CONTINUITY_ALLOWED
            category: ObservabilityCategory = "task_continuity"
            is_continuity_mode = True
        elif is_continuity:
            disposition = RecallDisposition.TASK_CONTINUITY_ONLY
            reason = RecallReason.TASK_CONTINUITY_ALLOWED
            category = "task_continuity"
            is_continuity_mode = True
        elif is_past_q:
            disposition = RecallDisposition.ALLOW
            reason = RecallReason.EXPLICIT_HISTORY_ALLOWED
            category = "factual_context"
            is_continuity_mode = False
        elif is_rule_q:
            disposition = RecallDisposition.ALLOW
            reason = RecallReason.EXPLICIT_RULE_ALLOWED
            category = "factual_context"
            is_continuity_mode = False
        elif is_reflective_q:
            disposition = RecallDisposition.ALLOW
            reason = RecallReason.REFLECTIVE_ALLOWED
            category = "reflective_context"
            is_continuity_mode = False
        else:
            # Factual or preference recall
            disposition = RecallDisposition.ALLOW
            if any(getattr(c, "category", "") == "preference" for c in passed_candidates):
                reason = RecallReason.EXPLICIT_PREFERENCE_ALLOWED
            else:
                reason = RecallReason.FACTUAL_ALLOWED
            category = "factual_context"
            is_continuity_mode = False

        # Step 4: Apply Minimal Injection Policy (deduplicate propositions & apply limit)
        injected_items, redundant_cands = self.injection_policy.process(
            passed_candidates, is_task_continuity=is_continuity_mode
        )

        all_suppressed = list(suppressed_candidates) + list(redundant_cands)

        # If deduplication or limits pruned everything (rare edge case), fall back to silent
        if not injected_items:
            return self._build_decision(
                disposition=RecallDisposition.SUPPRESS,
                reason=RecallReason.REDUNDANT_SUPPRESSED,
                category="silent",
                allowed=(),
                suppressed=tuple(all_suppressed),
                injected_items=(),
            )

        # Allowed candidates that actually made it into injected items
        injected_ids = {item.candidate_id for item in injected_items}
        final_allowed = tuple(c for c in passed_candidates if c.candidate_id in injected_ids)

        return self._build_decision(
            disposition=disposition,
            reason=reason,
            category=category,
            allowed=final_allowed,
            suppressed=tuple(all_suppressed),
            injected_items=injected_items,
        )

    def _check_candidate(
        self,
        cand: RetrievedCandidate,
        ctx: RecallContext,
        is_past_query: bool,
        is_continuity_query: bool,
    ) -> tuple[bool, str]:
        """Evaluate a single candidate against defense-in-depth policy invariants.

        Returns:
            (is_allowed, reason_code)
        """
        # 1. IMPL-3: Privacy Redaction Pending
        if getattr(cand, "needs_privacy_redaction", 0) == 1:
            return False, RecallReason.PRIVACY_PENDING

        # 2. TOCTOU & Live Store Validation
        live_block_reason = self._check_live_status(cand.candidate_id, ctx)
        if live_block_reason is not None:
            return False, live_block_reason

        # 3. Validity Status: Invalidated / Retracted
        if cand.validity_status in ("invalidated", "retracted"):
            return False, RecallReason.INVALIDATED_SUPPRESSED

        # 4. Temporal Supersession: Superseded items not allowed for current queries
        if not is_past_query and cand.validity_status == "superseded":
            return False, RecallReason.SUPERSEDED_SUPPRESSED

        # 5. Scope Isolation
        if cand.scope == "unresolved":
            return False, RecallReason.UNRESOLVED_SCOPE_SUPPRESSED

        if cand.scope == "project":
            if ctx.current_project_id is None:
                return False, RecallReason.SCOPE_MISMATCH
            if cand.project_id != ctx.current_project_id:
                # Disallow unless query explicitly references the other project ID
                if not (cand.project_id and cand.project_id in ctx.query_text):
                    return False, RecallReason.SCOPE_MISMATCH

        # 6. Minimum Confidence / Relevance Gating
        if cand.final_score < self.min_relevance_threshold:
            return False, RecallReason.WEAK_RELEVANCE_SUPPRESSED

        # 7. Sanctuary Mode Policy
        if ctx.sanctuary_active:
            # Block reflective / psychological / self-model recall
            if cand.candidate_type in ("confirmed_insight", "hypothesis"):
                return False, RecallReason.SANCTUARY_REFLECTIVE_BLOCK
            if _is_reflective_query(cand.statement):
                return False, RecallReason.SANCTUARY_REFLECTIVE_BLOCK

            # Block proactive past-frustration comparison & do_not_mention items
            if getattr(cand, "expression_policy", "normal") == "do_not_mention":
                return False, RecallReason.SANCTUARY_PAST_FRUSTRATION_BLOCK
            if getattr(cand, "category", "") in ("past_frustration", "frustration", "distress"):
                return False, RecallReason.SANCTUARY_PAST_FRUSTRATION_BLOCK
            if any(w in cand.statement for w in FRUSTRATION_STATEMENT_MARKERS):
                # If statement specifically describes past frustration/distress
                if "报错" not in cand.statement and "bug" not in cand.statement.lower():
                    return False, RecallReason.SANCTUARY_PAST_FRUSTRATION_BLOCK

            # Under Sanctuary, allow current task continuity, block unrelated proactive recall
            is_continuity_item = (
                cand.candidate_type == "episode"
                or getattr(cand, "category", "") == "task_continuity"
                or is_continuity_query
            )
            if not is_continuity_item:
                # Non-continuity memory suppressed under Sanctuary to preserve tranquility
                return False, RecallReason.SANCTUARY_REFLECTIVE_BLOCK

            return True, RecallReason.TASK_CONTINUITY_ALLOWED

        # 8. Outside Sanctuary Policies
        # Confirmed insights / self-model require explicit reflective intent (higher-gated)
        if cand.candidate_type in ("confirmed_insight", "hypothesis"):
            if not _is_reflective_query(ctx.query_text):
                return False, RecallReason.WEAK_RELEVANCE_SUPPRESSED

        # do_not_mention items outside sanctuary are also suppressed
        if getattr(cand, "expression_policy", "normal") == "do_not_mention":
            return False, RecallReason.WEAK_RELEVANCE_SUPPRESSED

        return True, ""

    def _check_live_status(self, candidate_id: str, context: RecallContext) -> str | None:
        """Check candidate against live store or validator for TOCTOU changes."""
        if context.live_validator is not None:
            val = context.live_validator(candidate_id)
            if isinstance(val, str):
                return val
            elif val is False:
                return RecallReason.INVALIDATED_SUPPRESSED

        if context.store is not None:
            mem = context.store.get_semantic_memory(candidate_id)
            if mem is not None:
                if mem.validity_status in ("invalidated", "retracted"):
                    return RecallReason.INVALIDATED_SUPPRESSED
                if mem.expression_policy == "do_not_mention" and context.sanctuary_active:
                    return RecallReason.SANCTUARY_PAST_FRUSTRATION_BLOCK
                return None

            insight = context.store.get_confirmed_insight(candidate_id)
            if insight is not None:
                if insight.status in ("invalidated", "retracted"):
                    return RecallReason.INVALIDATED_SUPPRESSED
                if context.sanctuary_active:
                    return RecallReason.SANCTUARY_REFLECTIVE_BLOCK
                return None

            chap = context.store.get_chapter_metadata(candidate_id)
            if chap is not None:
                if chap.needs_privacy_redaction == 1:
                    return RecallReason.PRIVACY_PENDING
                return None

            ep = context.store.get_episode(candidate_id)
            if ep is not None:
                return None

            # Not found in any table -> hard-deleted after retrieval
            return RecallReason.INVALIDATED_SUPPRESSED

        return None

    def _select_primary_suppression_reason(self, reasons: list[str]) -> str:
        """Determine deterministic primary suppression reason by priority."""
        priority_order = [
            RecallReason.PRIVACY_PENDING,
            RecallReason.SANCTUARY_REFLECTIVE_BLOCK,
            RecallReason.SANCTUARY_PAST_FRUSTRATION_BLOCK,
            RecallReason.INVALIDATED_SUPPRESSED,
            RecallReason.SCOPE_MISMATCH,
            RecallReason.UNRESOLVED_SCOPE_SUPPRESSED,
            RecallReason.SUPERSEDED_SUPPRESSED,
            RecallReason.WEAK_RELEVANCE_SUPPRESSED,
            RecallReason.GENERIC_QA_SUPPRESSED,
            RecallReason.REDUNDANT_SUPPRESSED,
        ]
        for p in priority_order:
            if p in reasons:
                return p
        return reasons[0] if reasons else RecallReason.WEAK_RELEVANCE_SUPPRESSED

    def _build_decision(
        self,
        disposition: RecallDisposition,
        reason: str,
        category: ObservabilityCategory,
        allowed: Sequence[RetrievedCandidate],
        suppressed: Sequence[RetrievedCandidate],
        injected_items: Sequence[Any],
    ) -> RecallDecision:
        """Construct an immutable RecallDecision."""
        inj_ctx = InjectionContext(
            items=tuple(injected_items),
            disposition=str(disposition.value),
            reason=reason,
            observability_category=category,
        )
        return RecallDecision(
            disposition=disposition,
            reason=reason,
            observability_category=category,
            allowed_candidates=tuple(allowed),
            suppressed_candidates=tuple(suppressed),
            injection_context=inj_ctx,
        )
