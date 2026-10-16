"""Unit tests for Phase 2B PatternBuilder and HypothesisEngine."""

from __future__ import annotations

from pathlib import Path

from src.connectors.contracts import AgentEvent, AgentEventType
from src.core.hypotheses import (
    ConfidenceLevel,
    DevelopmentLens,
    HypothesisEngine,
    HypothesisStatus,
)
from src.core.patterns import PatternBuilder
from src.memory.store import ChronicleStore


def _store() -> ChronicleStore:
    return ChronicleStore(Path(":memory:"))


def _feed_session(
    store: ChronicleStore,
    session_id: str,
    *,
    has_failure: bool = False,
    has_user_prompt: bool = False,
    event_count: int = 6,
    hour: int = 14,
) -> None:
    # ISO: 2026-10-16T{hour:02d}:00:00
    ts_start = f"2026-10-16T{hour:02d}:00:00+00:00"
    ts_end = f"2026-10-16T{hour:02d}:20:00+00:00"

    store.record_event(
        AgentEvent(
            agent_id="pi-desktop",
            event_type=AgentEventType.SESSION_START,
            session_id=session_id,
            timestamp=ts_start,
        )
    )
    if has_user_prompt:
        store.record_event(
            AgentEvent(
                agent_id="pi-desktop",
                event_type=AgentEventType.USER_PROMPT,
                session_id=session_id,
                timestamp=ts_start,
            )
        )
    if has_failure:
        store.record_event(
            AgentEvent(
                agent_id="pi-desktop",
                event_type=AgentEventType.TOOL_FAILURE,
                session_id=session_id,
                timestamp=ts_start,
                tool_name="Bash",
                error_message="Exit 1",
            )
        )
    for i in range(event_count - 3):
        store.record_event(
            AgentEvent(
                agent_id="pi-desktop",
                event_type=AgentEventType.PRE_TOOL_USE,
                session_id=session_id,
                timestamp=ts_start,
                tool_name=f"tool_{i}",
            )
        )
    store.record_event(
        AgentEvent(
            agent_id="pi-desktop",
            event_type=AgentEventType.SESSION_END,
            session_id=session_id,
            timestamp=ts_end,
        )
    )


def test_insufficient_episodes_produce_silence() -> None:
    """SPEC 2.6: Silence is valid. When episodes < threshold, output zero patterns."""
    store = _store()
    builder = PatternBuilder(store)
    # 0 episodes -> empty
    assert builder.build_patterns(min_episodes=2) == []

    # 1 episode -> still empty
    _feed_session(store, "s1")
    assert builder.build_patterns(min_episodes=2) == []
    store.close()


def test_friction_recovery_pattern_and_counter_evidence() -> None:
    """Verify supporting vs counter episodes are extracted accurately without bias."""
    store = _store()
    builder = PatternBuilder(store)

    # Episode 1 & 2: Error occurred, and user intervened with prompt -> Supporting
    _feed_session(store, "ep_supp_1", has_failure=True, has_user_prompt=True)
    _feed_session(store, "ep_supp_2", has_failure=True, has_user_prompt=True)

    # Episode 3: Error occurred, but no user prompt intervention -> Counter example
    _feed_session(store, "ep_counter_1", has_failure=True, has_user_prompt=False)

    patterns = builder.build_patterns(min_episodes=2)
    friction_pats = [p for p in patterns if p.pattern_id == "pat_friction_recovery"]
    assert len(friction_pats) == 1
    pat = friction_pats[0]

    assert set(pat.supporting_episodes) == {"ep_supp_1", "ep_supp_2"}
    assert set(pat.counter_episodes) == {"ep_counter_1"}
    assert pat.support_ratio == 0.67

    # Synthesize with HypothesisEngine
    engine = HypothesisEngine()
    hypotheses = engine.synthesize(patterns)
    assert len(hypotheses) >= 1

    hyp = [h for h in hypotheses if h.hypothesis_id == "hyp_pat_friction_recovery"][0]
    # Invariants verification:
    assert hyp.status == HypothesisStatus.CANDIDATE
    assert hyp.has_counter_evidence is True
    assert hyp.confidence == ConfidenceLevel.MODERATE
    assert DevelopmentLens.REGULATORY_FLEXIBILITY in hyp.lenses
    assert DevelopmentLens.OPENNESS_TO_UNCERTAINTY in hyp.lenses
    store.close()


def test_circadian_pacing_pattern() -> None:
    """Verify healthy daytime boundaries vs midnight pushes."""
    store = _store()
    builder = PatternBuilder(store)

    # Daytime sessions (hour 14, 16)
    _feed_session(store, "day_1", hour=14)
    _feed_session(store, "day_2", hour=16)

    # Midnight session (hour 2)
    _feed_session(store, "night_1", hour=2)

    patterns = builder.build_patterns(min_episodes=2)
    pacing_pats = [p for p in patterns if p.pattern_id == "pat_circadian_pacing"]
    assert len(pacing_pats) == 1
    p = pacing_pats[0]

    assert "night_1" in p.counter_episodes
    assert "day_1" in p.supporting_episodes
    assert p.support_ratio == 0.67

    hypotheses = HypothesisEngine().synthesize([p])
    assert hypotheses[0].lenses == (DevelopmentLens.TEMPORAL_INTEGRATION,)
    assert hypotheses[0].status == HypothesisStatus.CANDIDATE
    store.close()


def test_hypotheses_on_real_chronicle_database() -> None:
    """Run pattern mining against the live database accumulated by real agents."""
    from src.memory.store import DEFAULT_DB_PATH

    if not DEFAULT_DB_PATH.is_file():
        return

    live_store = ChronicleStore(DEFAULT_DB_PATH)
    builder = PatternBuilder(live_store)
    patterns = builder.build_patterns(min_episodes=2)
    hypotheses = HypothesisEngine().synthesize(patterns)

    # Must execute safely without crashes on real wild data
    assert isinstance(patterns, list)
    assert isinstance(hypotheses, list)
    for h in hypotheses:
        # All candidate, no score, has provenance
        assert h.status == HypothesisStatus.CANDIDATE
        assert len(h.lenses) > 0
        assert len(h.supporting_episodes) > 0

    live_store.close()
