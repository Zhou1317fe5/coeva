"""Shared Self Model & User Calibration (Phase 2C).

Implements the mutual consensus layer of the Co-evolving Companion:
- Hypothesis != Truth: Deep understandings require user calibration.
- Calibration feedback:
    * YES: Hypothesis promoted to Confirmed Insight.
    * PARTLY: Creates a Revised Hypothesis with user clarification.
    * NO: Hypothesis permanently rejected and archived.
    * NOT_NOW: Stays candidate; never auto-confirmed by silence.
- Insight Retirement: Users can outgrow their past models. Retired insights
  become historical growth footprints, ceasing to bias present inference.
- Active Growth Themes: Bounded to 1-3 active themes at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from src.core.hypotheses import (
    DevelopmentHypothesis,
    DevelopmentLens,
    HypothesisStatus,
)

if TYPE_CHECKING:
    pass


class CalibrationResponse(StrEnum):
    """User choice when reviewing an emerging candidate hypothesis (SPEC section 13)."""

    YES = "yes"  # Fully acknowledged -> Promotes to Confirmed Insight
    PARTLY = "partly"  # Acknowledged with nuance -> Spawns Revised Hypothesis
    NO = "no"  # Rejected -> Permanently marked rejected, forbidden from future use
    EXPLAIN = "explain"  # Expanded by user -> Turns into explicit user reflection
    NOT_NOW = "not_now"  # Postponed -> Stays candidate, never auto-promoted


class InsightStatus(StrEnum):
    """Lifecycle status of a confirmed mutual insight."""

    ACTIVE = "active"  # Actively shaping companion's understanding and care
    RETIRED = "retired"  # Outgrown; preserved as growth history only


class ThemeStatus(StrEnum):
    """Lifecycle status of a focal growth theme."""

    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


@dataclass(frozen=True)
class ConfirmedInsight:
    """A long-term understanding mutually agreed upon between human and companion."""

    insight_id: str
    statement: str
    lenses: tuple[DevelopmentLens, ...]
    supporting_patterns: tuple[str, ...]
    user_confirmation_text: str = ""
    valid_from: str = field(default_factory=lambda: date.today().isoformat())
    last_revalidated: str = field(default_factory=lambda: date.today().isoformat())
    status: InsightStatus = InsightStatus.ACTIVE


@dataclass(frozen=True)
class GrowthTheme:
    """A focal developmental topic (bounded to 1-3 active at a time)."""

    theme_id: str
    title: str
    lens: DevelopmentLens
    statement: str = ""
    status: ThemeStatus = ThemeStatus.ACTIVE
    created_at: str = field(default_factory=lambda: date.today().isoformat())


class SelfModelManager:
    """Coordinates mutual calibration, insight promotion/retirement, and active themes."""

    MAX_ACTIVE_THEMES = 3

    def __init__(self) -> None:
        pass

    def apply_calibration(
        self,
        hypothesis: DevelopmentHypothesis,
        response: CalibrationResponse,
        *,
        user_comment: str = "",
        today: str | None = None,
    ) -> tuple[DevelopmentHypothesis, ConfirmedInsight | None, DevelopmentHypothesis | None]:
        """Apply user calibration to a candidate hypothesis.

        Returns:
            (updated_hypothesis, new_confirmed_insight_or_None, revised_hypothesis_or_None)
        """
        now_date = today or date.today().isoformat()

        if response == CalibrationResponse.YES:
            # 1. Update hypothesis to confirmed
            updated_hyp = DevelopmentHypothesis(
                hypothesis_id=hypothesis.hypothesis_id,
                statement=hypothesis.statement,
                lenses=hypothesis.lenses,
                supporting_patterns=hypothesis.supporting_patterns,
                supporting_episodes=hypothesis.supporting_episodes,
                counter_episodes=hypothesis.counter_episodes,
                confidence=hypothesis.confidence,
                status=HypothesisStatus.CONFIRMED,
                created_at=hypothesis.created_at,
            )
            # 2. Spawn a Confirmed Insight
            insight = ConfirmedInsight(
                insight_id=f"ins_{hypothesis.hypothesis_id}",
                statement=hypothesis.statement,
                lenses=hypothesis.lenses,
                supporting_patterns=hypothesis.supporting_patterns,
                user_confirmation_text=user_comment or "用户确认认同该理解",
                valid_from=now_date,
                last_revalidated=now_date,
                status=InsightStatus.ACTIVE,
            )
            return updated_hyp, insight, None

        elif response == CalibrationResponse.PARTLY or response == CalibrationResponse.EXPLAIN:
            # Spawns a Revised Candidate Hypothesis incorporating user nuance
            revised_text = (
                f"{hypothesis.statement}（补充校准：{user_comment}）"
                if user_comment
                else hypothesis.statement
            )
            revised_hyp = DevelopmentHypothesis(
                hypothesis_id=f"{hypothesis.hypothesis_id}_revised",
                statement=revised_text,
                lenses=hypothesis.lenses,
                supporting_patterns=hypothesis.supporting_patterns,
                supporting_episodes=hypothesis.supporting_episodes,
                counter_episodes=hypothesis.counter_episodes,
                confidence=hypothesis.confidence,
                status=HypothesisStatus.CANDIDATE,
                created_at=now_date,
            )
            updated_hyp = DevelopmentHypothesis(
                hypothesis_id=hypothesis.hypothesis_id,
                statement=hypothesis.statement,
                lenses=hypothesis.lenses,
                supporting_patterns=hypothesis.supporting_patterns,
                supporting_episodes=hypothesis.supporting_episodes,
                counter_episodes=hypothesis.counter_episodes,
                confidence=hypothesis.confidence,
                status=HypothesisStatus.CALIBRATING,
                created_at=hypothesis.created_at,
            )
            return updated_hyp, None, revised_hyp

        elif response == CalibrationResponse.NO:
            # Permanently rejected
            rejected_hyp = DevelopmentHypothesis(
                hypothesis_id=hypothesis.hypothesis_id,
                statement=hypothesis.statement,
                lenses=hypothesis.lenses,
                supporting_patterns=hypothesis.supporting_patterns,
                supporting_episodes=hypothesis.supporting_episodes,
                counter_episodes=hypothesis.counter_episodes,
                confidence=hypothesis.confidence,
                status=HypothesisStatus.REJECTED,
                created_at=hypothesis.created_at,
            )
            return rejected_hyp, None, None

        else:  # NOT_NOW
            # Remains candidate; silence never auto-promotes (SPEC section 14)
            return hypothesis, None, None

    def retire_insight(
        self, insight: ConfirmedInsight, *, reason: str = ""
    ) -> ConfirmedInsight:
        """User has outgrown this model; archive it into historical growth footprints."""
        return ConfirmedInsight(
            insight_id=insight.insight_id,
            statement=insight.statement,
            lenses=insight.lenses,
            supporting_patterns=insight.supporting_patterns,
            user_confirmation_text=f"{insight.user_confirmation_text} [已退休: {reason}]"
            if reason
            else insight.user_confirmation_text,
            valid_from=insight.valid_from,
            last_revalidated=insight.last_revalidated,
            status=InsightStatus.RETIRED,
        )

    def validate_active_theme_quota(self, current_themes: list[GrowthTheme]) -> bool:
        """Check if adding another active theme violates the 1-3 limit (SPEC section 17)."""
        active_count = sum(1 for t in current_themes if t.status == ThemeStatus.ACTIVE)
        return active_count < self.MAX_ACTIVE_THEMES
