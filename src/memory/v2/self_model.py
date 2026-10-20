"""Slow-Path Self-Model Service (WP-6): Coordinated slow-path understanding pipeline.

Preserves:
- Deliberate Low Frequency: Slow-path execution separated from raw evidence writes (Section 10).
- Epistemic Hierarchy: Evidence -> Observation -> Candidate Hypothesis -> Calibration -> Insight.
- Production Isolation & Flags: Defaults to OFF (`memory_v2_self_model=False`) (S6-19).
- Non-blocking Service Interface: Thin, callable service API for periodic background invocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.core.flags import resolve_flags
from src.memory.v2.calibration import CalibrationService
from src.memory.v2.hypothesis import HypothesisEngine
from src.memory.v2.observation import ObservationPipeline

if TYPE_CHECKING:
    from src.memory.v2.store import ChronicleStoreV2


@dataclass(frozen=True)
class SlowPathConfig:
    """Configuration for low-frequency self-model slow path."""

    min_observation_proof_count: int = 2
    min_hypothesis_evidence_count: int = 2
    defer_cooldown_seconds: int = 86400  # 24h
    max_observations_per_run: int = 10
    max_hypotheses_per_run: int = 5


@dataclass
class SlowPathRunReport:
    """Execution report from a slow-path cycle."""

    enabled: bool
    observations_created: list[str] = field(default_factory=list)
    hypotheses_proposed: list[str] = field(default_factory=list)
    recomputed_observations: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


class SlowPathSelfModelService:
    """Coordinates observation synthesis, hypothesis derivation, and human calibration.

    Provides a clean, callable slow-path interface for low-frequency background jobs.
    """

    def __init__(
        self,
        store: ChronicleStoreV2,
        *,
        config: SlowPathConfig | None = None,
        observation_pipeline: ObservationPipeline | None = None,
        hypothesis_engine: HypothesisEngine | None = None,
        calibration_service: CalibrationService | None = None,
    ) -> None:
        self._store = store
        self._config = config or SlowPathConfig()
        self._obs_pipeline = observation_pipeline or ObservationPipeline(
            store, min_psych_proof_count=self._config.min_observation_proof_count
        )
        self._hyp_engine = hypothesis_engine or HypothesisEngine(
            store, min_independent_evidence=self._config.min_hypothesis_evidence_count
        )
        self._calib_service = calibration_service or CalibrationService(store)

    @property
    def store(self) -> ChronicleStoreV2:
        return self._store

    @property
    def observation_pipeline(self) -> ObservationPipeline:
        return self._obs_pipeline

    @property
    def hypothesis_engine(self) -> HypothesisEngine:
        return self._hyp_engine

    @property
    def calibration_service(self) -> CalibrationService:
        return self._calib_service

    def is_feature_enabled(self) -> bool:
        """Check if memory_v2_self_model feature flag is enabled."""
        flags = resolve_flags()
        return bool(flags.memory_v2_self_model)

    def run_slow_path(
        self,
        *,
        force_enable: bool = False,
        project_id: str | None = None,
        now_ts: str | None = None,
    ) -> SlowPathRunReport:
        """Execute a slow-path cycle.

        Enforces:
        - If memory_v2_self_model is OFF and not force_enable, returns immediately (S6-19).
        - Recomputes observation support counts where needed.
        - Deliberately bounded, does not block main loop.
        """
        if not force_enable and not self.is_feature_enabled():
            return SlowPathRunReport(
                enabled=False,
                details=["Slow path skipped: memory_v2_self_model flag is OFF (default)."],
            )

        now = now_ts or datetime.now(UTC).isoformat()
        report = SlowPathRunReport(enabled=True)

        # 1. Maintenance: recompute active observations with weakened proof
        active_obs = self._obs_pipeline.list_observations(status="active", project_id=project_id)
        for obs in active_obs:
            old_count = obs.proof_count
            new_count = self._obs_pipeline.recompute_observation_proof(
                obs.observation_id, now_ts=now
            )
            if new_count != old_count:
                report.recomputed_observations.append(obs.observation_id)
                report.details.append(
                    f"Observation '{obs.observation_id}' proof updated: {old_count} -> {new_count}"
                )

        report.details.append(
            f"Slow path completed successfully at {now}. "
            f"Active observations checked: {len(active_obs)}."
        )
        return report
