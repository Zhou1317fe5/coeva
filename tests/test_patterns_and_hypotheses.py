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
    prompt_after_failure: bool = False,
    event_count: int = 6,
    hour: int = 14,
) -> None:
    # ISO timestamps with distinct, ordered minutes
    ts_start = f"2026-10-16T{hour:02d}:00:00+00:00"
    ts_prompt_init = f"2026-10-16T{hour:02d}:01:00+00:00"
    ts_fail = f"2026-10-16T{hour:02d}:05:00+00:00"
    ts_prompt_after = f"2026-10-16T{hour:02d}:08:00+00:00"
    ts_end = f"2026-10-16T{hour:02d}:20:00+00:00"

    store.record_event(
        AgentEvent(
            agent_id="pi-desktop",
            event_type=AgentEventType.SESSION_START,
            session_id=session_id,
            timestamp=ts_start,
        )
    )
    # The session starts with an initial user prompt
    store.record_event(
        AgentEvent(
            agent_id="pi-desktop",
            event_type=AgentEventType.USER_PROMPT,
            session_id=session_id,
            timestamp=ts_prompt_init,
        )
    )
    if has_failure:
        store.record_event(
            AgentEvent(
                agent_id="pi-desktop",
                event_type=AgentEventType.TOOL_FAILURE,
                session_id=session_id,
                timestamp=ts_fail,
                tool_name="Bash",
                error_message="Exit 1",
            )
        )
    if prompt_after_failure:
        # User actively stepped in AFTER the tool failed
        store.record_event(
            AgentEvent(
                agent_id="pi-desktop",
                event_type=AgentEventType.USER_PROMPT,
                session_id=session_id,
                timestamp=ts_prompt_after,
            )
        )
    for i in range(max(1, event_count - 4)):
        ts_tool = f"2026-10-16T{hour:02d}:{10 + i:02d}:00+00:00"
        store.record_event(
            AgentEvent(
                agent_id="pi-desktop",
                event_type=AgentEventType.PRE_TOOL_USE,
                session_id=session_id,
                timestamp=ts_tool,
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

    # Episode 1 & 2: Error occurred, and user intervened with prompt afterwards -> Supporting
    _feed_session(store, "ep_supp_1", has_failure=True, prompt_after_failure=True)
    _feed_session(store, "ep_supp_2", has_failure=True, prompt_after_failure=True)

    # Episode 3: Error occurred, but user never prompted after failure -> Counter example
    _feed_session(store, "ep_counter_1", has_failure=True, prompt_after_failure=False)

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


def test_agent_autonomous_recovery_when_user_does_not_intervene() -> None:
    """When user lets the agent fail and heal on its own, attribute hands-off delegation."""
    store = _store()
    builder = PatternBuilder(store)

    # User started the session, tool failed, but user NEVER stepped in -> Agent self-healing
    _feed_session(store, "ep_auto_1", has_failure=True, prompt_after_failure=False)
    _feed_session(store, "ep_auto_2", has_failure=True, prompt_after_failure=False)

    patterns = builder.build_patterns(min_episodes=2)
    auto_pats = [p for p in patterns if p.pattern_id == "pat_agent_autonomous_recovery"]
    assert len(auto_pats) == 1
    pat = auto_pats[0]
    assert "充分自主修复空间" in pat.description
    assert set(pat.supporting_episodes) == {"ep_auto_1", "ep_auto_2"}

    hypotheses = HypothesisEngine().synthesize(patterns)
    auto_hyps = [h for h in hypotheses if h.hypothesis_id == "hyp_pat_agent_autonomous_recovery"]
    assert len(auto_hyps) == 1
    assert DevelopmentLens.OPENNESS_TO_UNCERTAINTY in auto_hyps[0].lenses
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

    v1_backup = DEFAULT_DB_PATH.parent / "companion_chronicle.db.pre_v2_backup"
    target_db = v1_backup if v1_backup.is_file() else DEFAULT_DB_PATH
    if not target_db.is_file():
        return

    live_store = ChronicleStore(target_db)
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
