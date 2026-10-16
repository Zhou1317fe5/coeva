"""Unit tests for the Phase 2A Chronicle Store and Attribution Gate.

Each test names the acceptance criterion it covers; see
docs/specs/phase-2-chronicle-and-growth-chapters/SPEC.md section 9.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.event_bus import LocalEventBus
from src.core.attribution import Provenance, RetentionClass, classify
from src.memory.store import ChronicleStore, SliceRecord, event_id


def _store() -> ChronicleStore:
    return ChronicleStore(Path(":memory:"))


def _event(
    event_type: AgentEventType, *, session: str = "s1", tool: str = "bash"
) -> AgentEvent:
    return AgentEvent.create("hermes", event_type, session_id=session, tool_name=tool)


def test_ac2_agent_autonomous_events_never_become_user_evidence() -> None:
    """AC-2: agent-only activity must not produce user-origin evidence."""
    store = _store()
    for index in range(30):
        event_type = (
            AgentEventType.PRE_TOOL_USE,
            AgentEventType.POST_TOOL_USE,
            AgentEventType.TOOL_FAILURE,
        )[index % 3]
        store.record_event(_event(event_type, tool=f"tool_{index}"))

    assert store.stats()["events"] == 30
    leaked = [
        row
        for row in store.list_evidence(limit=100)
        if row["provenance"] in (Provenance.USER_EXPLICIT, Provenance.USER_ACTION)
    ]
    assert leaked == []


def test_attribution_gate_mapping() -> None:
    """Section 5: only user_prompt carries user attribution."""
    assert classify(AgentEventType.USER_PROMPT) == (Provenance.USER_ACTION, RetentionClass.DURABLE)
    assert classify("pre_tool_use") == (Provenance.AGENT_CONTEXT, RetentionClass.TRANSIENT)
    # An unknown event type must fall to the conservative branch, not gain attribution.
    assert classify("some_future_event") == (Provenance.AGENT_CONTEXT, RetentionClass.TRANSIENT)


def test_ac1_events_persist_across_reconnect(tmp_path: Path) -> None:
    """AC-1: events survive a process restart (here: a reopen of the database)."""
    db_path = tmp_path / "chronicle.db"
    first = ChronicleStore(db_path)
    first.record_event(_event(AgentEventType.SESSION_START))
    first.record_event(_event(AgentEventType.USER_PROMPT))
    first.close()

    second = ChronicleStore(db_path)
    try:
        assert second.stats()["events"] == 2
    finally:
        second.close()


def test_ac3_import_is_idempotent(tmp_path: Path) -> None:
    """AC-3: repeated imports of the same jsonl leave the row count unchanged."""
    jsonl = tmp_path / "raw_slices.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(
                {
                    "id": f"slice_{i}",
                    "timestamp": f"2026-10-15T15:0{i}:00+00:00",
                    "actor": "user",
                    "source": "manual_feed",
                    "content": f"记录 {i}",
                    "mood_flag": "neutral",
                },
                ensure_ascii=False,
            )
            for i in range(3)
        )
        + "\n",
        encoding="utf-8",
    )

    store = _store()
    assert store.import_slices_jsonl(jsonl) == 3
    assert store.import_slices_jsonl(jsonl) == 0
    assert store.import_slices_jsonl(jsonl) == 0
    assert store.stats()["slices"] == 3


def test_import_skips_malformed_lines(tmp_path: Path) -> None:
    """A corrupt or incomplete line is skipped, not fatal."""
    jsonl = tmp_path / "raw_slices.jsonl"
    jsonl.write_text(
        '{"id": "ok", "timestamp": "t", "content": "fine"}\n'
        "{ this is not json }\n"
        '{"missing": "required fields"}\n',
        encoding="utf-8",
    )
    store = _store()
    assert store.import_slices_jsonl(jsonl) == 1
    assert store.stats()["slices"] == 1


def test_ac4_evidence_is_traceable_to_its_source_row() -> None:
    """AC-4: every evidence row carries the id and content of a real slices/events row."""
    store = _store()
    store.record_slice(
        SliceRecord(
            id="slice_a",
            timestamp="2026-10-15T10:00:00+00:00",
            content="用户原话",
            mood_flag="neutral",
        )
    )
    store.record_event(_event(AgentEventType.PRE_TOOL_USE, session="s9"))

    rows = store.list_evidence(limit=10)
    by_source: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_source.setdefault(str(row["source_type"]), []).append(row)
    assert set(by_source) == {"slice", "event"}

    # The slice-derived row must match the source row exactly.
    slice_rows = store.list_slices(limit=10)
    assert len(slice_rows) == 1
    assert by_source["slice"][0]["id"] == slice_rows[0].id
    assert by_source["slice"][0]["content"] == slice_rows[0].content

    # The event-derived row must resolve to the stored event.
    event_row = by_source["event"][0]
    assert event_row["id"] == event_id(_event(AgentEventType.PRE_TOOL_USE, session="s9"))
    assert event_row["content"] == "pre_tool_use:bash"


def test_ac5_chinese_two_character_keyword_is_found() -> None:
    """AC-5: LIKE search finds a 2-character Chinese word (FTS5 cannot, see section 4.4)."""
    store = _store()
    store.record_slice(
        SliceRecord(
            id="slice_b",
            timestamp="2026-10-15T10:00:00+00:00",
            content="突然觉得今天这个问题其实可以明天再继续。",
            mood_flag="reflective",
        )
    )
    hits = store.search_slices("明天")
    assert len(hits) == 1
    assert "明天" in hits[0].content
    assert store.search_slices("不存在的词") == []


def test_ac6_prune_drops_only_transient_events() -> None:
    """AC-6: prune removes expired transient events and never touches durable rows."""
    store = _store()
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    store.record_event(
        AgentEvent(
            agent_id="hermes",
            event_type=AgentEventType.PRE_TOOL_USE,
            session_id="s_old",
            timestamp=old,
            tool_name="bash",
        )
    )
    store.record_event(
        AgentEvent(
            agent_id="hermes",
            event_type=AgentEventType.USER_PROMPT,
            session_id="s_old",
            timestamp=old,
        )
    )
    store.record_event(_event(AgentEventType.PRE_TOOL_USE, session="s_new"))

    assert store.stats()["events"] == 3
    removed = store.prune(ttl_days=30)
    assert removed == 1  # only the old transient pre_tool_use
    assert store.stats()["events"] == 2  # durable user_prompt + recent transient kept


def test_episodes_group_by_session() -> None:
    """Section 6: an episode is one session_id."""
    store = _store()
    store.record_event(_event(AgentEventType.SESSION_START, session="alpha"))
    store.record_event(_event(AgentEventType.PRE_TOOL_USE, session="alpha", tool="read"))
    store.record_event(_event(AgentEventType.SESSION_START, session="beta"))

    episodes = {e.session_id: e for e in store.list_episodes(limit=10)}
    assert set(episodes) == {"alpha", "beta"}
    assert episodes["alpha"].event_count == 2
    assert episodes["alpha"].has_user_action is False

    store.record_event(_event(AgentEventType.USER_PROMPT, session="alpha", tool=""))
    again = {e.session_id: e for e in store.list_episodes(limit=10)}
    assert again["alpha"].has_user_action is True


def test_event_id_is_stable_for_redelivery() -> None:
    """Section 4.3: identical event content hashes to the same id, so re-inserts are ignored."""
    event = _event(AgentEventType.PRE_TOOL_USE)
    store = _store()
    assert store.record_event(event) is True
    assert store.record_event(event) is False
    assert store.stats()["events"] == 1
    assert event_id(event) == event_id(event)


def test_ac9_time_range_and_mood_query_stays_indexed() -> None:
    """AC-9: 10k slices, mood-filtered query stays well inside the 50ms guard."""
    store = _store()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(10_000):
        store.record_slice(
            SliceRecord(
                id=f"s{i}",
                timestamp=(base + timedelta(minutes=i)).isoformat(),
                content=f"记录 {i}",
                mood_flag="frustrated" if i % 3 == 0 else "neutral",
            )
        )

    samples: list[float] = []
    for _ in range(50):
        started = time.perf_counter()
        rows = store.list_slices(limit=50, mood="frustrated")
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95)]
    assert rows, "query returned nothing"
    assert p95 <= 50, f"P95 was {p95:.2f}ms, above the 50ms guard"


def test_bus_persists_events_when_a_store_is_attached() -> None:
    """Section 3 / step 3: the event bus writes to the Chronicle when wired."""
    store = _store()
    bus = LocalEventBus(store=store)
    bus.dispatch(_event(AgentEventType.PRE_TOOL_USE, tool="read"))
    bus.dispatch(_event(AgentEventType.USER_PROMPT, tool=""))
    assert store.stats()["events"] == 2

    # Without a store the bus must still work (Phase 1 behaviour).
    bare = LocalEventBus()
    bare.dispatch(_event(AgentEventType.PRE_TOOL_USE))
    assert len(bare.history) == 1
