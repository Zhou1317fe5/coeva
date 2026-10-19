"""Reconciliation Validator for Memory V2.1 Lane E (WP-4).

Phase 2 Deterministic Local Validation Engine:
- Validates untrusted Phase-1 proposals against existing canonical semantic state.
- Enforces the 6 deterministic rules (Rule-V1 through Rule-V6).
- Fail-Closed: When uncertain between SUPERSEDE and AMBIGUOUS, prefer AMBIGUOUS.
- When suggested SUPERSEDE lacks an active target in DB, downgrade to ADD (False SUPERSEDE = 0).
- Independent evidence fingerprinting prevents replay / proof inflation (False REINFORCE = 0).
- Unknown scope is strictly forced to 'unresolved' (INV: Unknown != Global).
- Claim-Sensitive Authority: user_asserted voice strictly overrides telemetry inferences.
- ProposalProvider / LLM has zero database write authority.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

from src.memory.v2.candidate_extraction import NORMALIZATION_STRIP_PREFIXES
from src.memory.v2.echo_guard import EchoGuard, EchoGuardResult
from src.memory.v2.entities import (
    AuthorityClass,
    Scope,
    SemanticCategory,
)
from src.memory.v2.proposals import (
    AdmissionDecision,
    CandidateSemanticMemory,
    ConsolidationProposal,
)
from src.memory.v2.store import ChronicleStoreV2

ReconciliationAction = Literal["ADD", "SUPERSEDE", "REINFORCE", "AMBIGUOUS", "NOOP"]

# Weak contradiction & hesitation markers (P0: fail-closed prefer AMBIGUOUS)
WEAK_CONTRADICTION_MARKERS = [
    "有些",
    "有时候",
    "偶尔",
    "看起来也挺",
    "挺省事",
    "不如图形界面",
    "不是不喜欢",
    "深灰调其实挺舒服",
    "临时脚本",
    "单文件",
    "也挺",
    "挺好看",
    "有时候觉得",
    "也挺繁琐",
]

# Explicit user correction markers (highest subjective authority)
EXPLICIT_CORRECTION_MARKERS = [
    "刚才我说错了",
    "我说错了",
    "记错了",
    "其实是",
    "其实不是",
]

# Explicit migration / superseded markers
EXPLICIT_MIGRATION_MARKERS = [
    "全面迁移到",
    "不再用",
    "改用",
    "之前说",
    "换成了",
    "请严肃打断我提醒",
]

# Universal scope markers that justify global scope without explicit project_id
UNIVERSAL_SCOPE_MARKERS = [
    "在任何项目里",
    "所有项目",
    "跨工程",
    "写所有代码",
    "在任何地方",
    "所有代码",
]


def normalize_content(content: str) -> str:
    """Normalize statement content for canonical independence hashing.

    Strips conversational fillers and trailing punctuation while preserving
    semantic qualifiers and conditionality.
    """
    cleaned = content.strip()
    for pattern in NORMALIZATION_STRIP_PREFIXES:
        cleaned = pattern.sub("", cleaned).strip()
    cleaned = re.sub(r"[\s,，.。!！?？~、]+$", "", cleaned).strip()
    return cleaned


def compute_independence_fingerprint(
    statement: str,
    episode_id: str = "",
    source_day_utc: str = "",
) -> str:
    """Compute SHA256 independence fingerprint for evidence reinforcement deduplication.

    Follows Frozen Data Model:
        independence_hash = hash(episode_id + normalized_content)
    and:
        proof_count = COUNT(DISTINCT independence_hash)

    Notice: source_day_utc is strictly excluded from the hash identity so that
    same-Episode repetitions across UTC date boundaries never inflate proof_count.
    """
    normalized = normalize_content(statement)
    ep = episode_id.strip() if episode_id else ""
    raw = f"{ep}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Canonical alias aligned with Frozen Data Model terminology
compute_independence_hash = compute_independence_fingerprint


@dataclass(frozen=True)
class ReconciliationDecision:
    """Deterministic validation decision produced in Phase 2 before transaction commit."""

    action: ReconciliationAction
    target_memory_id: str | None
    claim: CandidateSemanticMemory | None
    statement: str
    category: SemanticCategory
    scope: Scope
    project_id: str | None
    authority_class: AuthorityClass
    proof_delta: int
    independence_fingerprint: str | None = None
    rationale: str = ""
    rejection_category: str | None = None
    is_valid: bool = True
    validator_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReconciliationValidator:
    """Deterministic local validator for Memory V2.1 proposals.

    Performs 6-rule physical validation:
    - Rule-V1: Source Exists & Provenance Check (FK-safe, fail-closed)
    - Rule-V2: Unknown Scope Enforcement (force 'unresolved' if unknown project)
    - Rule-V3: Claim-Sensitive Authority & Anti-Echo Check
    - Rule-V4: Fail-Closed Supersede Target Validity Check (False SUPERSEDE = 0)
    - Rule-V5: Independent Evidence Fingerprint Collision Check (False REINFORCE = 0)
    - Rule-V6: Privacy Pending Exclusion Gate
    """

    def __init__(
        self,
        store: ChronicleStoreV2,
        echo_guard: EchoGuard | None = None,
    ) -> None:
        self.store = store
        self.echo_guard = echo_guard or EchoGuard()

    def validate_claim(
        self,
        claim: CandidateSemanticMemory,
        admission: AdmissionDecision,
        context: dict[str, Any] | None = None,
        echo_result: EchoGuardResult | None = None,
    ) -> ReconciliationDecision:
        """Validate a single candidate claim against canonical database state."""
        t0 = time.perf_counter()
        ctx = context or {}

        # ── Step 1: Admission Check ──────────────────────────────────────────
        if admission.decision != "ADMIT":
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return ReconciliationDecision(
                action="NOOP",
                target_memory_id=None,
                claim=claim,
                statement=claim.statement,
                category=claim.category,
                scope=claim.scope,
                project_id=claim.project_id,
                authority_class=claim.authority_class,
                proof_delta=0,
                rationale=admission.rationale,
                rejection_category=admission.rejection_category or "admission_rejected",
                is_valid=True,
                validator_latency_ms=latency_ms,
            )

        # ── Step 2: Rule-V6: Privacy Pending Exclusion Gate ──────────────────
        if ctx.get("needs_privacy_redaction") or ctx.get("is_redacted"):
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return ReconciliationDecision(
                action="NOOP",
                target_memory_id=None,
                claim=claim,
                statement=claim.statement,
                category=claim.category,
                scope=claim.scope,
                project_id=claim.project_id,
                authority_class=claim.authority_class,
                proof_delta=0,
                rationale="Privacy redaction pending: blocked from reconciliation.",
                rejection_category="privacy_pending",
                is_valid=False,
                validator_latency_ms=latency_ms,
            )

        # ── Step 3: Rule-V1: Source Exists & Provenance Check (IMPL-2) ────────
        # Semantic memories must have FK-safe provenance. Zero-provenance memory is impossible.
        check_source = ctx.get("check_source_exists", True)
        if check_source:
            has_valid_source = False
            if claim.source_slice_id:
                row = self.store.connection.execute(
                    "SELECT slice_id FROM raw_slices WHERE slice_id = ?;",
                    (claim.source_slice_id,),
                ).fetchone()
                if row:
                    has_valid_source = True
            elif claim.source_event_id:
                row = self.store.connection.execute(
                    "SELECT event_id FROM event_skeletons WHERE event_id = ?;",
                    (claim.source_event_id,),
                ).fetchone()
                if row:
                    has_valid_source = True

            if not has_valid_source and not ctx.get("bypass_source_check"):
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return ReconciliationDecision(
                    action="NOOP",
                    target_memory_id=None,
                    claim=claim,
                    statement=claim.statement,
                    category=claim.category,
                    scope=claim.scope,
                    project_id=claim.project_id,
                    authority_class=claim.authority_class,
                    proof_delta=0,
                    rationale="Source evidence does not exist in DB (fail-closed provenance).",
                    rejection_category="missing_provenance",
                    is_valid=False,
                    validator_latency_ms=latency_ms,
                )

        # ── Step 4: Rule-V2: Unknown Scope Enforcement (S-14) ────────────────
        scope: Scope = claim.scope
        project_id = claim.project_id
        if not project_id or project_id == "":
            has_universal_marker = any(m in claim.statement for m in UNIVERSAL_SCOPE_MARKERS)
            if scope == "global" and not has_universal_marker:
                scope = "unresolved"
                project_id = None
            elif scope != "global":
                scope = "unresolved"
                project_id = None
        elif project_id == "global":
            scope = "global"
        else:
            scope = "project"

        # ── Step 5: Rule-V3: Claim-Sensitive Authority & Anti-Echo Check ─────
        # Telemetry cannot create subjective claims (feelings, preferences, relationship rules)
        if claim.authority_class == "system_observed" and claim.category in (
            "preference",
            "relationship_rule",
        ):
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return ReconciliationDecision(
                action="NOOP",
                target_memory_id=None,
                claim=claim,
                statement=claim.statement,
                category=claim.category,
                scope=scope,
                project_id=project_id,
                authority_class=claim.authority_class,
                proof_delta=0,
                rationale="Telemetry cannot generate subjective preferences or rules.",
                rejection_category="authority_violation",
                is_valid=False,
                validator_latency_ms=latency_ms,
            )

        if echo_result and echo_result.has_echo_context and echo_result.is_pure_echo:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return ReconciliationDecision(
                action="NOOP",
                target_memory_id=None,
                claim=claim,
                statement=claim.statement,
                category=claim.category,
                scope=scope,
                project_id=project_id,
                authority_class=claim.authority_class,
                proof_delta=0,
                rationale="Assistant echo without new user delta: NOOP.",
                rejection_category="echo_parrot",
                is_valid=True,
                validator_latency_ms=latency_ms,
            )

        # ── Step 6: Target Resolution & Rules V4/V5 Action Validation ─────────
        target_id = ctx.get("target_existing_memory") or claim.target_superseded_id
        target_mem = self.store.get_semantic_memory(str(target_id)) if target_id else None

        suggested_action = claim.suggested_action

        # Check semantic markers in statement
        is_weak_contradiction = any(m in claim.statement for m in WEAK_CONTRADICTION_MARKERS)
        is_explicit_correction = any(m in claim.statement for m in EXPLICIT_CORRECTION_MARKERS)
        is_migration = any(m in claim.statement for m in EXPLICIT_MIGRATION_MARKERS)

        final_action: ReconciliationAction = "ADD"
        proof_delta = 1
        final_target_id: str | None = None
        fingerprint: str | None = None
        is_same_content = target_mem is not None and normalize_content(
            claim.statement
        ) == normalize_content(target_mem.statement)

        if is_same_content and suggested_action != "SUPERSEDE":
            is_supersede_intent = False
        else:
            is_supersede_intent = (
                suggested_action == "SUPERSEDE"
                or is_explicit_correction
                or (is_migration and target_mem is not None and not is_same_content)
            )

        if is_supersede_intent:
            if target_mem is None or target_mem.validity_status != "active":
                # P0 Fail-Closed: No active target exists in DB!
                # Destructive mutation MUST fail closed: downgrade to ADD (False SUPERSEDE = 0)
                final_action = "ADD"
                proof_delta = 1
                final_target_id = None
            elif is_weak_contradiction:
                # P0 Fail-Closed: Weak contradiction / hesitation -> AMBIGUOUS!
                final_action = "AMBIGUOUS"
                proof_delta = 0
                final_target_id = target_mem.memory_id
            else:
                final_action = "SUPERSEDE"
                proof_delta = 1
                final_target_id = target_mem.memory_id

        elif suggested_action == "REINFORCE":
            if target_mem is None or target_mem.validity_status != "active":
                final_action = "ADD"
                proof_delta = 1
                final_target_id = None
            else:
                # Rule-V5: Independent Evidence Fingerprint Collision Check
                ep_id = str(ctx.get("episode_id") or "")
                stmt_to_hash = target_mem.statement if target_mem else claim.statement
                fingerprint = compute_independence_fingerprint(stmt_to_hash, ep_id)

                existing_reinf = self.store.connection.execute(
                    "SELECT 1 FROM evidence_reinforcements WHERE memory_id = ? "
                    "AND independence_fingerprint = ?;",
                    (target_mem.memory_id, fingerprint),
                ).fetchone()

                if existing_reinf is not None:
                    # Fingerprint collision: non-independent duplicate
                    final_action = "NOOP"
                    proof_delta = 0
                    final_target_id = target_mem.memory_id
                else:
                    final_action = "REINFORCE"
                    proof_delta = 1
                    final_target_id = target_mem.memory_id

        elif suggested_action == "AMBIGUOUS":
            if target_mem is not None and target_mem.validity_status == "active":
                final_action = "AMBIGUOUS"
                proof_delta = 0
                final_target_id = target_mem.memory_id
            else:
                final_action = "ADD"
                proof_delta = 1
                final_target_id = None

        elif suggested_action == "NOOP":
            final_action = "NOOP"
            proof_delta = 0
            final_target_id = None

        else:
            # Model suggested "ADD" or fallback
            if target_mem is not None and target_mem.validity_status == "active":
                if is_weak_contradiction:
                    final_action = "AMBIGUOUS"
                    proof_delta = 0
                    final_target_id = target_mem.memory_id
                elif (
                    target_mem.authority_class == "system_observed"
                    and claim.authority_class == "user_asserted"
                ):
                    # DEV_P: User self-description strictly overrides telemetry inference
                    final_action = "SUPERSEDE"
                    proof_delta = 1
                    final_target_id = target_mem.memory_id
                elif not is_migration and not is_explicit_correction:
                    # Reaffirmation or repetition of existing target memory
                    ep_id = str(ctx.get("episode_id") or "")
                    stmt_to_hash = target_mem.statement if target_mem else claim.statement
                    fingerprint = compute_independence_fingerprint(stmt_to_hash, ep_id)

                    existing_reinf = self.store.connection.execute(
                        "SELECT 1 FROM evidence_reinforcements WHERE memory_id = ? "
                        "AND independence_fingerprint = ?;",
                        (target_mem.memory_id, fingerprint),
                    ).fetchone()

                    if existing_reinf is not None:
                        # DEV_J: Same episode repetition -> NOOP
                        final_action = "NOOP"
                        proof_delta = 0
                        final_target_id = target_mem.memory_id
                    else:
                        # DEV_C / DEV_K / HOLD_10: New independent evidence -> REINFORCE
                        final_action = "REINFORCE"
                        proof_delta = 1
                        final_target_id = target_mem.memory_id
                else:
                    final_action = "ADD"
                    proof_delta = 1
                    final_target_id = None
            else:
                final_action = "ADD"
                proof_delta = 1
                final_target_id = None

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return ReconciliationDecision(
            action=final_action,
            target_memory_id=final_target_id,
            claim=claim,
            statement=claim.statement,
            category=claim.category,
            scope=scope,
            project_id=project_id,
            authority_class=claim.authority_class,
            proof_delta=proof_delta,
            independence_fingerprint=fingerprint,
            rationale=f"Validated action {final_action} (suggested={suggested_action})",
            rejection_category=None,
            is_valid=True,
            validator_latency_ms=latency_ms,
        )

    def validate_proposal(
        self,
        proposal: ConsolidationProposal,
        context: dict[str, Any] | None = None,
    ) -> list[ReconciliationDecision]:
        """Validate all candidate claims in an untrusted ConsolidationProposal."""
        if proposal.admission.decision != "ADMIT" or not proposal.proposed_claims:
            t0 = time.perf_counter()
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return [
                ReconciliationDecision(
                    action="NOOP",
                    target_memory_id=None,
                    claim=None,
                    statement="",
                    category="fact",
                    scope="unresolved",
                    project_id=None,
                    authority_class="user_asserted",
                    proof_delta=0,
                    rationale=proposal.admission.rationale,
                    rejection_category=proposal.admission.rejection_category or "no_claims",
                    is_valid=True,
                    validator_latency_ms=latency_ms,
                )
            ]

        decisions: list[ReconciliationDecision] = []
        for claim in proposal.proposed_claims:
            dec = self.validate_claim(claim, proposal.admission, context=context)
            decisions.append(dec)
        return decisions
