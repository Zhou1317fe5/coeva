"""Human Calibration Service (WP-6): Immutable action log & consensus promotion.

Preserves frozen invariants:
- Canonical Calibration Actions: YES, PARTLY, NO, NOT_NOW.
- Immutable Calibration Events: Action log is canonical and cannot be erased (S6-10, S6-12).
- Zero-Provenance Ban: Confirmed insight MUST reference source hypothesis and calibration event.
- Rejected Guard: Rejected hypothesis CANNOT generate confirmed insight (S6-08).
- Deferral Guard: NOT_NOW preserves candidate state, records deferral, prevents nag (S6-09).
- Qualified Consensus: PARTLY preserves refinement without deleting history (S6-07).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from src.memory.v2.entities import (
    CalibrationEventEntity,
    ConfirmedInsightEntity,
    ConfirmedInsightStatus,
    HypothesisStatus,
)

if TYPE_CHECKING:
    from src.memory.v2.store import ChronicleStoreV2


class CalibrationResponse(StrEnum):
    """User response options during human calibration of emerging candidate hypotheses."""

    YES = "yes"
    PARTLY = "partly"
    NO = "no"
    NOT_NOW = "not_now"


class CalibrationError(ValueError):
    """Base error for calibration failures."""

    pass


class HypothesisNotFoundError(CalibrationError):
    """Raised when calibrating a non-existent hypothesis."""

    pass


class IllegalCalibrationError(CalibrationError):
    """Raised when attempting illegal calibration on rejected or invalid hypothesis."""

    pass


class ImmutableCalibrationError(CalibrationError):
    """Raised when an illegal mutation or deletion of calibration history is attempted (S6-10)."""

    pass


@dataclass(frozen=True)
class CalibrationDecision:
    """User-provided calibration action and optional refinement notes."""

    hypothesis_id: str
    response: CalibrationResponse | str
    user_note: str | None = None
    calibrated_statement: str | None = None
    calibrated_at: str | None = None


@dataclass(frozen=True)
class CalibrationResult:
    """Result of applying human calibration to a hypothesis."""

    action: str
    hypothesis_id: str
    calibration_event: CalibrationEventEntity | None
    confirmed_insight: ConfirmedInsightEntity | None
    hypothesis_status: HypothesisStatus
    refined_statement: str | None
    detail: str


class CalibrationService:
    """Manages human calibration workflows, consensus promotion, and immutable history."""

    def __init__(self, store: ChronicleStoreV2) -> None:
        self._store = store

    @property
    def store(self) -> ChronicleStoreV2:
        return self._store

    def calibrate(self, decision: CalibrationDecision) -> CalibrationResult:
        """Apply human calibration to a hypothesis.

        Enforces:
        - YES: record immutable event, produce confirmed insight, mark hypothesis calibrated.
        - PARTLY: record immutable event, produce qualified confirmed insight with user note,
                  preserve hypothesis history (S6-07).
        - NO: record immutable event, mark hypothesis rejected, produce ZERO insight (S6-08).
        - NOT_NOW: record deferral timestamp, preserve candidate state, produce ZERO insight,
                   prevent immediate re-prompting (S6-09).
        """
        hyp = self._store.get_hypothesis(decision.hypothesis_id)
        if not hyp:
            raise HypothesisNotFoundError(f"Hypothesis '{decision.hypothesis_id}' not found.")

        # Normalization
        raw_resp = str(decision.response).lower()
        try:
            resp = CalibrationResponse(raw_resp)
        except ValueError as err:
            raise CalibrationError(
                f"Unsupported calibration response: '{decision.response}'"
            ) from err

        # Disallow confirming an already rejected hypothesis
        if hyp.status == "rejected" and resp in (
            CalibrationResponse.YES,
            CalibrationResponse.PARTLY,
        ):
            raise IllegalCalibrationError(
                f"Cannot confirm rejected hypothesis '{hyp.hypothesis_id}'. "
                "Rejected hypotheses cannot generate confirmed insights (S6-08)."
            )

        now = decision.calibrated_at or datetime.now(UTC).isoformat()

        if resp == CalibrationResponse.YES:
            # 1. Record immutable calibration event (Entity 15)
            cal_id = f"cal_{uuid.uuid4().hex[:12]}"
            cal_entity = CalibrationEventEntity(
                calibration_id=cal_id,
                hypothesis_id=hyp.hypothesis_id,
                user_action="yes",
                calibrated_at=now,
                user_note=decision.user_note or "User explicitly confirmed hypothesis",
            )

            # 2. Spawn Confirmed Insight (Entity 16)
            ins_id = f"ins_{uuid.uuid4().hex[:12]}"
            ins_entity = ConfirmedInsightEntity(
                insight_id=ins_id,
                source_hypothesis_id=hyp.hypothesis_id,
                source_calibration_id=cal_id,
                statement=decision.calibrated_statement or hyp.statement,
                valid_from=now,
                invalidated_at=None,
                superseded_by=None,
                status="confirmed",
                created_at=now,
            )

            with self._store.transaction():
                self._store.insert_calibration_event(cal_entity)
                self._store.insert_confirmed_insight(ins_entity)
                self._store.update_hypothesis_status(
                    hyp.hypothesis_id,
                    status=hyp.status,
                    last_calibrated_at=now,
                )

            return CalibrationResult(
                action="yes",
                hypothesis_id=hyp.hypothesis_id,
                calibration_event=cal_entity,
                confirmed_insight=ins_entity,
                hypothesis_status=hyp.status,
                refined_statement=ins_entity.statement,
                detail="Hypothesis confirmed and promoted to Confirmed Insight (S6-06).",
            )

        elif resp == CalibrationResponse.PARTLY:
            # 1. Record immutable calibration event with correction note
            cal_id = f"cal_{uuid.uuid4().hex[:12]}"
            cal_entity = CalibrationEventEntity(
                calibration_id=cal_id,
                hypothesis_id=hyp.hypothesis_id,
                user_action="partly",
                calibrated_at=now,
                user_note=decision.user_note or "User qualified hypothesis",
            )

            # 2. Formulate refined consensus statement
            refined_statement = decision.calibrated_statement
            if not refined_statement:
                if decision.user_note:
                    refined_statement = f"{hyp.statement}（补充校准：{decision.user_note}）"
                else:
                    refined_statement = hyp.statement

            # 3. Spawn Confirmed Insight reflecting refined understanding
            ins_id = f"ins_{uuid.uuid4().hex[:12]}"
            ins_entity = ConfirmedInsightEntity(
                insight_id=ins_id,
                source_hypothesis_id=hyp.hypothesis_id,
                source_calibration_id=cal_id,
                statement=refined_statement,
                valid_from=now,
                invalidated_at=None,
                superseded_by=None,
                status="confirmed",
                created_at=now,
            )

            with self._store.transaction():
                self._store.insert_calibration_event(cal_entity)
                self._store.insert_confirmed_insight(ins_entity)
                self._store.update_hypothesis_status(
                    hyp.hypothesis_id,
                    status=hyp.status,
                    last_calibrated_at=now,
                )

            return CalibrationResult(
                action="partly",
                hypothesis_id=hyp.hypothesis_id,
                calibration_event=cal_entity,
                confirmed_insight=ins_entity,
                hypothesis_status=hyp.status,
                refined_statement=refined_statement,
                detail="Hypothesis partly confirmed; qualified Confirmed Insight created (S6-07).",
            )

        elif resp == CalibrationResponse.NO:
            # 1. Record immutable rejection event (Entity 15)
            cal_id = f"cal_{uuid.uuid4().hex[:12]}"
            cal_entity = CalibrationEventEntity(
                calibration_id=cal_id,
                hypothesis_id=hyp.hypothesis_id,
                user_action="no",
                calibrated_at=now,
                user_note=decision.user_note or "User explicitly rejected hypothesis",
            )

            with self._store.transaction():
                self._store.insert_calibration_event(cal_entity)
                self._store.update_hypothesis_status(
                    hyp.hypothesis_id,
                    status="rejected",
                    last_calibrated_at=now,
                )

            # S6-08: NO Confirmed Insight is produced!
            return CalibrationResult(
                action="no",
                hypothesis_id=hyp.hypothesis_id,
                calibration_event=cal_entity,
                confirmed_insight=None,
                hypothesis_status="rejected",
                refined_statement=None,
                detail="Hypothesis rejected; zero confirmed insight produced (S6-08).",
            )

        else:  # NOT_NOW
            # Postpone/defer: preserves candidate status, records deferral timestamp,
            # produces ZERO confirmed insight, and stops immediate resurfacing (S6-09).
            with self._store.transaction():
                self._store.update_hypothesis_status(
                    hyp.hypothesis_id,
                    status="candidate",
                    last_calibrated_at=now,
                )

            return CalibrationResult(
                action="not_now",
                hypothesis_id=hyp.hypothesis_id,
                calibration_event=None,
                confirmed_insight=None,
                hypothesis_status="candidate",
                refined_statement=None,
                detail="Hypothesis deferred; stays candidate with updated timestamp (S6-09).",
            )

    def get_calibration_history(self, hypothesis_id: str) -> list[CalibrationEventEntity]:
        """Fetch immutable calibration history for a hypothesis."""
        return self._store.list_calibration_events(hypothesis_id=hypothesis_id)

    def get_confirmed_insights(
        self,
        hypothesis_id: str | None = None,
        status: ConfirmedInsightStatus | None = None,
    ) -> list[ConfirmedInsightEntity]:
        """List confirmed insights, optionally filtered."""
        if hypothesis_id is not None:
            insights = self._store.get_confirmed_insights_by_hypothesis(hypothesis_id)
            if status is not None:
                return [i for i in insights if i.status == status]
            return insights
        return self._store.list_confirmed_insights(status=status)
