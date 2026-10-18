"""Tests that V1 companion behavior remains 100% unchanged under default Stage 0 flags.

Part of Stage 0 (WP-0, Section 8).
Ensures:
- Default startup selects V1 path
- Slice write uses existing V1 dual-write path
- Event write uses existing V1 event table
- MemoryRetriever uses existing V1 regex/LIKE path
- Sanctuary guard remains operational
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.event_bus import LocalEventBus
from src.core.flags import resolve_flags, validate_memory_v2_configuration
from src.core.sanctuary import SanctuaryGuard
from src.feeder.contracts import RawSlice
from src.feeder.storage import SliceStore
from src.memory.retriever import MemoryRetriever
from src.memory.store import ChronicleStore, SliceRecord


def test_v1_path_selected_when_all_flags_default() -> None:
    """Verify that default resolved flags select the V1 legacy path."""
    flags = resolve_flags()
    assert flags.memory_v2_storage is False
    assert flags.memory_v2_retrieval is False
    assert flags.memory_v2_consolidation is False
    assert flags.memory_v2_self_model is False
    assert flags.memory_v2_migration is False
    assert flags.memory_v2_backfill is False

    diag = validate_memory_v2_configuration(flags)
    assert diag["status"] == "VALID"
    assert diag["selected_path"] == "v1"


def test_v1_slice_and_event_persistence_remains_operational() -> None:
    """Verify that V1 ChronicleStore and SliceStore operate normally in Stage 0."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_chronicle.db"
        jsonl_path = Path(tmpdir) / "test_slices.jsonl"

        store = ChronicleStore(db_path)
        try:
            slice_store = SliceStore(jsonl_path)
            # 1. User slice dual-write
            slice_item = RawSlice.create("V1 默认行为验证切片：今天天气很好", mood_flag="neutral")
            slice_store.save(slice_item)
            store.record_slice(
                SliceRecord(
                    id=slice_item.id,
                    timestamp=slice_item.timestamp,
                    content=slice_item.content,
                    mood_flag=slice_item.mood_flag,
                )
            )

            assert slice_store.count() == 1
            assert store.stats()["slices"] == 1
            slices = store.list_slices()
            assert len(slices) == 1
            assert slices[0].content == "V1 默认行为验证切片：今天天气很好"

            # 2. Agent event write through event bus
            bus = LocalEventBus(store=store)
            evt = AgentEvent(
                timestamp=datetime.now(UTC).isoformat(),
                event_type=AgentEventType.TASK_COMPLETE,
                agent_id="pi-desktop",
                session_id="sess_v1_test",
                tool_name="test_tool",
                error_message="",
            )
            bus.dispatch(evt)
            assert store.stats()["events"] == 1

            # 3. MemoryRetriever operates normally on V1 store
            retriever = MemoryRetriever(store)
            recalled = retriever.recall("今天天气", limit=3)
            assert len(recalled) == 1
            assert "今天天气很好" in recalled[0]
        finally:
            store.close()


def test_v1_sanctuary_guard_remains_operational() -> None:
    """Verify that SanctuaryGuard operates normally without interference."""
    guard = SanctuaryGuard()
    assert guard.is_active is False

    # Distress text triggers sanctuary
    is_distressed = guard.evaluate_text("烦死了，这个bug搞了一整天")
    assert is_distressed is True
    assert guard.is_active is True

    # Neutral text does not trigger
    guard.reset()
    assert guard.is_active is False
    assert guard.evaluate_text("写完了，准备测试") is False
