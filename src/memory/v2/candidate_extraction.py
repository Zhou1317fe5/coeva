"""Candidate Semantic Claim Extraction for Memory V2.1 Lane C.

Extracts normalized, typed candidate semantic propositions from admitted Raw Evidence.
Phase 1 Read-only: Does NOT mutate the database.
Enforces S-01 (Single Raw Slice must not create psychological hypothesis).
Enforces Scope Unresolved preservation (Unknown != Global).
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Protocol, runtime_checkable

from src.memory.v2.admission import AdmissionFilter
from src.memory.v2.entities import RawSliceEntity, Scope, SemanticCategory
from src.memory.v2.proposals import (
    AdmissionDecision,
    CandidateSemanticMemory,
    ConsolidationProposal,
    SuggestedAction,
)

# Forbidden fields that must never appear in semantic candidate proposals (S-01 Guard)
FORBIDDEN_PSYCH_FIELDS = {
    "personality_score",
    "trait_score",
    "productivity_score",
    "diagnosis",
    "stable_persona",
    "psychological_hypothesis",
}

# Fillers to strip during claim normalization
NORMALIZATION_STRIP_PREFIXES = [
    re.compile(r"^(?:顺便说下[，, ]*|顺便说一句[，, ]*|顺便提一下[，, ]*)"),
    re.compile(r"^(?:不好意思[，, ]*|对不起[，, ]*)"),
    re.compile(r"^(?:其实就是说[，, ]*|那个[，, ]*|就是说[，, ]*)"),
]


@runtime_checkable
class ProposalProvider(Protocol):
    """Protocol for Phase 1 read-only candidate proposal generators."""

    def generate_proposal(
        self,
        slice_entity: RawSliceEntity,
        admission: AdmissionDecision,
        delta_text: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ConsolidationProposal:
        """Generate a typed proposal. Must be strictly read-only."""
        ...


class RuleBasedProposalProvider:
    """Deterministic, local candidate proposal extractor for fast-path & offline usage."""

    def normalize_statement(self, text: str) -> str:
        """Clean conversational filler while strictly preserving qualifiers and conditionality."""
        cleaned = text.strip()
        for pattern in NORMALIZATION_STRIP_PREFIXES:
            cleaned = pattern.sub("", cleaned).strip()
        return cleaned

    def determine_scope(
        self,
        slice_entity: RawSliceEntity,
        text: str,
    ) -> tuple[Scope, str | None]:
        """Determine scope following the Unknown != Global invariant."""
        # 1. Explicitly bound to a project in the slice
        if slice_entity.project_id:
            return "project", slice_entity.project_id

        # 2. Explicit cross-project universality markers
        if any(marker in text for marker in ["在任何项目里", "所有项目", "跨工程", "写所有代码"]):
            return "global", "global"

        # 3. Default to unresolved: unknown project MUST stay unresolved (S-14)
        return "unresolved", None

    def determine_category(self, text: str) -> SemanticCategory:
        """Classify proposition into canonical semantic categories."""
        # Relationship rules
        rule_markers = [
            "千万别",
            "别在",
            "别提醒",
            "提醒我",
            "别打扰",
            "请严肃打断",
            "别说教",
        ]
        if any(marker in text for marker in rule_markers):
            return "relationship_rule"

        # Preferences & habits
        pref_markers = [
            "偏好",
            "喜欢",
            "更喜欢",
            "迁移到",
            "不再用",
            "缩进",
            "深灰调",
            "浅色主题",
            "边写边试",
            "边写边",
        ]
        if any(marker in text for marker in pref_markers):
            return "preference"

        # Goals
        goal_markers = ["长期目标", "目标是", "打算", "计划把", "要把"]
        if any(marker in text for marker in goal_markers):
            return "goal"

        # Enduring facts (default)
        return "fact"

    def determine_suggested_action(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[SuggestedAction, str | None]:
        """Suggest an intended reconciliation action (untrusted hint for Phase 2)."""
        ctx = context or {}
        target_id = ctx.get("target_existing_memory")

        # Explicit user correction
        correction_markers = ["刚才我说错了", "我说错了", "记错了", "其实是", "其实不是"]
        if any(marker in text for marker in correction_markers):
            return "SUPERSEDE", str(target_id) if target_id else None

        # Explicit migration / superseding
        migration_markers = ["全面迁移到", "不再用", "改用", "之前说"]
        if any(marker in text for marker in migration_markers):
            if target_id:
                return "SUPERSEDE", str(target_id)
            return "ADD", None

        # Weak contradiction / conditional preference (prefer AMBIGUOUS)
        weak_markers = ["偶尔", "有些", "看起来也挺", "有时候", "不如图形界面"]
        if any(marker in text for marker in weak_markers):
            if target_id:
                return "AMBIGUOUS", str(target_id)

        # Reaffirmation
        reaffirm_markers = ["事实证明", "经过几个月", "完全正确", "还是坚持"]
        if any(marker in text for marker in reaffirm_markers):
            if target_id:
                return "REINFORCE", str(target_id)

        return "ADD", None

    def generate_proposal(
        self,
        slice_entity: RawSliceEntity,
        admission: AdmissionDecision,
        delta_text: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ConsolidationProposal:
        """Extract typed candidate semantic claims from an admitted raw slice."""
        proposal_id = f"prop_{uuid.uuid4().hex[:12]}"

        if admission.decision != "ADMIT":
            return ConsolidationProposal(
                proposal_id=proposal_id,
                admission=admission,
                proposed_claims=[],
                source_id=slice_entity.slice_id,
                source_type="slice",
                created_at=slice_entity.occurred_at,
            )

        text_to_extract = delta_text or slice_entity.content
        normalized = self.normalize_statement(text_to_extract)
        scope, project_id = self.determine_scope(slice_entity, text_to_extract)
        category = self.determine_category(text_to_extract)
        action, target_id = self.determine_suggested_action(text_to_extract, context)

        # Tentative vs grounded
        is_grounded = "坚持" in text_to_extract or "事实证明" in text_to_extract
        confidence: Any = "grounded" if is_grounded else "tentative"

        claim = CandidateSemanticMemory(
            statement=normalized,
            category=category,
            scope=scope,
            authority_class="user_asserted",
            source_slice_id=slice_entity.slice_id,
            source_event_id=None,
            project_id=project_id,
            confidence_class=confidence,
            temporal_anchor=slice_entity.occurred_at,
            suggested_action=action,
            target_superseded_id=target_id,
            rationale=admission.rationale,
        )

        return ConsolidationProposal(
            proposal_id=proposal_id,
            admission=admission,
            proposed_claims=[claim],
            source_id=slice_entity.slice_id,
            source_type="slice",
            created_at=slice_entity.occurred_at,
        )


class CandidateExtractor:
    """High-level candidate extractor coordinating Admission and Proposal Provider."""

    def __init__(
        self,
        admission_filter: AdmissionFilter | None = None,
        provider: ProposalProvider | None = None,
    ) -> None:
        self.admission_filter = admission_filter or AdmissionFilter()
        self.provider = provider or RuleBasedProposalProvider()

    def extract_from_slice(
        self,
        slice_entity: RawSliceEntity,
        echoed_proposition: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ConsolidationProposal:
        """Admit and extract candidate semantic memory from a Raw User Slice.

        Safe / Non-mutating:
        - Catches provider failure and returns DEFER.
        - Enforces S-01 invariant (asserts no personality/hypothesis fields).
        """
        # Step 1: Admission Gate
        admission = self.admission_filter.evaluate_slice(
            slice_entity=slice_entity,
            echoed_proposition=echoed_proposition,
            context=context,
        )

        if admission.decision != "ADMIT":
            return ConsolidationProposal(
                proposal_id=f"prop_{uuid.uuid4().hex[:12]}",
                admission=admission,
                proposed_claims=[],
                source_id=slice_entity.slice_id,
                source_type="slice",
                created_at=slice_entity.occurred_at,
            )

        # Step 2: Delta text extraction from Echo Guard if applicable
        ctx_echo = context.get("echoed_proposition") if context else None
        echo_res = self.admission_filter.echo_guard.inspect(
            slice_entity.content,
            echoed_proposition or ctx_echo,
        )
        if echo_res.has_echo_context and echo_res.delta_text:
            delta_text = echo_res.delta_text
        else:
            delta_text = None

        # Step 3: Candidate Extraction via Proposal Provider
        try:
            proposal = self.provider.generate_proposal(
                slice_entity=slice_entity,
                admission=admission,
                delta_text=delta_text,
                context=context,
            )
        except Exception as exc:
            # Provider failure: defer extraction safely without dirty database write
            return ConsolidationProposal(
                proposal_id=f"prop_{uuid.uuid4().hex[:12]}",
                admission=AdmissionDecision(
                    decision="DEFER",
                    rationale=f"Proposal provider failed: {exc!s}. Deferred safely.",
                    rejection_category="provider_failure",
                ),
                proposed_claims=[],
                source_id=slice_entity.slice_id,
                source_type="slice",
                created_at=slice_entity.occurred_at,
            )

        # Step 4: S-01 Safety Check on Output
        for claim in proposal.proposed_claims:
            claim_dict = claim.to_dict()
            for forbidden in FORBIDDEN_PSYCH_FIELDS:
                if forbidden in claim_dict:
                    msg = f"S-01 Invariant Violated: Proposal contains '{forbidden}'"
                    raise ValueError(msg)

        return proposal
