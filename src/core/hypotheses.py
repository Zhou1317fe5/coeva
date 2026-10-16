"""Hypothesis Engine (Phase 2B): Synthesizes patterns into developmental hypotheses.

Adheres strictly to the Principles:
- Hypothesis != Truth: All newly synthesized insights start as `candidate`
- Development Lens != Psychological Score: Lenses classify and interpret patterns,
  never compress human growth into a single numerical score (SPEC 2.3).
- Counter Evidence is mandatory: every hypothesis must record counter examples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.patterns import BehavioralPattern


class DevelopmentLens(StrEnum):
    """The six lenses of psychological flexibility (ACT-informed, non-scoring)."""

    TEMPORAL_INTEGRATION = "temporal_integration"  # Present balance vs future obsession
    OPENNESS_TO_UNCERTAINTY = "openness_to_uncertainty"  # Tolerate unresolved problems
    REGULATORY_FLEXIBILITY = "regulatory_flexibility"  # Knowing when to persist vs pivot/stop
    AUTONOMOUS_ACTION = "autonomous_action"  # Values-aligned vs compulsory pressure
    EXPERIENTIAL_OPENNESS = "experiential_openness"  # Embracing vulnerability vs avoidance
    NARRATIVE_INTEGRATION = "narrative_integration"  # Coherent biographical meaning


class HypothesisStatus(StrEnum):
    """Lifecycle state of an emerging mental understanding (SPEC section 11)."""

    CANDIDATE = "candidate"  # Freshly synthesized by system; unconfirmed
    CALIBRATING = "calibrating"  # Currently presented for mutual calibration
    CONFIRMED = "confirmed"  # Verified by the user
    REJECTED = "rejected"  # Explicitly rejected by user; strictly forbidden from future use
    RETIRED = "retired"  # Outgrown by user; archived as historical growth footprint


class ConfidenceLevel(StrEnum):
    """Qualitative confidence based on supporting vs counter evidence."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


@dataclass(frozen=True)
class DevelopmentHypothesis:
    """An evidence-grounded, falsifiable interpretation of user developmental patterns."""

    hypothesis_id: str
    statement: str
    lenses: tuple[DevelopmentLens, ...]
    supporting_patterns: tuple[str, ...]
    supporting_episodes: tuple[str, ...]
    counter_episodes: tuple[str, ...]
    confidence: ConfidenceLevel = ConfidenceLevel.MODERATE
    status: HypothesisStatus = HypothesisStatus.CANDIDATE
    created_at: str = field(default_factory=lambda: date.today().isoformat())

    @property
    def has_counter_evidence(self) -> bool:
        """Section 12: Evidence Ledger must track contradictory signals."""
        return len(self.counter_episodes) > 0


class HypothesisEngine:
    """Interprets behavioral patterns through development lenses into candidate hypotheses."""

    def synthesize(self, patterns: list[BehavioralPattern]) -> list[DevelopmentHypothesis]:
        """Map observed behavioral patterns to candidate developmental hypotheses."""
        if not patterns:
            return []

        hypotheses: list[DevelopmentHypothesis] = []

        for pat in patterns:
            if pat.pattern_id == "pat_friction_recovery":
                # Maps to Regulatory Flexibility & Openness to Uncertainty
                conf = self._calculate_confidence(pat)
                hypotheses.append(
                    DevelopmentHypothesis(
                        hypothesis_id=f"hyp_{pat.pattern_id}",
                        statement="面对工具链执行挫折与报错摩擦时，倾向于主动缩小任务边界并理性介入，而非陷入机械死循环。",
                        lenses=(
                            DevelopmentLens.REGULATORY_FLEXIBILITY,
                            DevelopmentLens.OPENNESS_TO_UNCERTAINTY,
                        ),
                        supporting_patterns=(pat.pattern_id,),
                        supporting_episodes=pat.supporting_episodes,
                        counter_episodes=pat.counter_episodes,
                        confidence=conf,
                        status=HypothesisStatus.CANDIDATE,
                    )
                )

            elif pat.pattern_id == "pat_agent_autonomous_recovery":
                # Maps to Openness to Uncertainty: high tolerance for agent self-healing
                conf = self._calculate_confidence(pat)
                hypotheses.append(
                    DevelopmentHypothesis(
                        hypothesis_id=f"hyp_{pat.pattern_id}",
                        statement=(
                            "面对工具链报错摩擦时，倾向于给予 Agent 充分自主修复空间，"
                            "展现出对机器探索过程的高度包容。"
                        ),
                        lenses=(
                            DevelopmentLens.OPENNESS_TO_UNCERTAINTY,
                            DevelopmentLens.REGULATORY_FLEXIBILITY,
                        ),
                        supporting_patterns=(pat.pattern_id,),
                        supporting_episodes=pat.supporting_episodes,
                        counter_episodes=pat.counter_episodes,
                        confidence=conf,
                        status=HypothesisStatus.CANDIDATE,
                    )
                )

            elif pat.pattern_id == "pat_circadian_pacing":
                # Maps to Temporal Integration
                conf = self._calculate_confidence(pat)
                hypotheses.append(
                    DevelopmentHypothesis(
                        hypothesis_id=f"hyp_{pat.pattern_id}",
                        statement="在日常开发节律中，能够在常规作息时间前主动收尾会话，保持当下精力与长远健康的平衡。",
                        lenses=(DevelopmentLens.TEMPORAL_INTEGRATION,),
                        supporting_patterns=(pat.pattern_id,),
                        supporting_episodes=pat.supporting_episodes,
                        counter_episodes=pat.counter_episodes,
                        confidence=conf,
                        status=HypothesisStatus.CANDIDATE,
                    )
                )

            elif pat.pattern_id == "pat_hands_off_delegation":
                # Maps to Autonomous Action & Regulatory Flexibility
                conf = self._calculate_confidence(pat)
                hypotheses.append(
                    DevelopmentHypothesis(
                        hypothesis_id=f"hyp_{pat.pattern_id}",
                        statement=(
                            "在长链路复杂任务中，倾向于充分授权 Agent 自主执行，"
                            "宏观把控目标而不进行微观打断。"
                        ),
                        lenses=(
                            DevelopmentLens.AUTONOMOUS_ACTION,
                            DevelopmentLens.REGULATORY_FLEXIBILITY,
                        ),
                        supporting_patterns=(pat.pattern_id,),
                        supporting_episodes=pat.supporting_episodes,
                        counter_episodes=pat.counter_episodes,
                        confidence=conf,
                        status=HypothesisStatus.CANDIDATE,
                    )
                )

            elif pat.pattern_id == "pat_interactive_steering":
                # Maps to Autonomous Action
                conf = self._calculate_confidence(pat)
                hypotheses.append(
                    DevelopmentHypothesis(
                        hypothesis_id=f"hyp_{pat.pattern_id}",
                        statement="在深度复杂的工具代理长链路中，保持了基于自主意图的主动把控与导向节奏。",
                        lenses=(DevelopmentLens.AUTONOMOUS_ACTION,),
                        supporting_patterns=(pat.pattern_id,),
                        supporting_episodes=pat.supporting_episodes,
                        counter_episodes=pat.counter_episodes,
                        confidence=conf,
                        status=HypothesisStatus.CANDIDATE,
                    )
                )

        return hypotheses

    def _calculate_confidence(self, pattern: BehavioralPattern) -> ConfidenceLevel:
        ratio = pattern.support_ratio
        support_cnt = len(pattern.supporting_episodes)

        if support_cnt >= 4 and ratio >= 0.75:
            return ConfidenceLevel.HIGH
        if support_cnt >= 2 and ratio >= 0.5:
            return ConfidenceLevel.MODERATE
        return ConfidenceLevel.LOW
