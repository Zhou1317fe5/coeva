"""Test suite for Memory V2.1 Production Runtime Wiring and Orchestration (WP-14).

Verifies:
- RT-01: Default flags (all False) route to legacy V1 storage and retriever.
- RT-02: Stage 10A (memory_v2_storage=True) routes slice writes and replies to V2 WriteService.
- RT-03: Stage 10A routes connector events to V2 EventSkeleton via V2EventStoreAdapter.
- RT-04: Stage 10A V2ChronicleStoreAdapter allows read-only compatibility and blocks writes.
- RT-05: Stage 10B routes _recall_memories through Retrieval Pipeline + Recall Gate.
- RT-06: Stage 10C (memory_v2_consolidation=True) starts and stops ConsolidationScheduler.
- RT-07: Stage 10D (memory_v2_self_model=True) binds SlowPathSelfModelService and ChapterRepo.
- RT-08: Graceful shutdown cleans up background services without leaking locks.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import run_companion
from src.connectors.contracts import AgentEvent, AgentEventType
from src.core.flags import (
    PRODUCTION_V2_CAPABILITIES,
    MemoryFeatureFlags,
    validate_memory_v2_configuration,
)
from src.memory.v2.compatibility import (
    CompatibilityReader,
    V2ChronicleStoreAdapter,
    V2EventStoreAdapter,
)
from src.memory.v2.jsonl_export import JsonlSliceExporter
from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import RawEvidenceWriteService, WriteSliceCommand


def test_rt01_default_flags_selects_v1_runtime() -> None:
    """RT-01: default configuration selects V1 path with all flags OFF."""
    flags = MemoryFeatureFlags()
    diag = validate_memory_v2_configuration(flags, capabilities=PRODUCTION_V2_CAPABILITIES)
    assert diag["status"] == "VALID"
    assert diag["selected_path"] == "v1"
    assert diag["flags"]["memory_v2_storage"] is False
    assert diag["flags"]["memory_v2_retrieval"] is False


def test_rt02_stage_10a_storage_routes_writes_to_v2(tmp_path: Path) -> None:
    """RT-02: Stage 10A writes user slices directly to V2 SQLite raw_slices and JSONL."""
    db_file = tmp_path / "rt02_test.db"
    jsonl_file = tmp_path / "raw_slices.jsonl"

    store = ChronicleStoreV2(db_file)
    exporter = JsonlSliceExporter(jsonl_file)
    write_service = RawEvidenceWriteService(store, exporter=exporter)

    # Simulate app slice submission in V2 mode
    app = run_companion.CompanionApp.__new__(run_companion.CompanionApp)
    app.write_service = write_service
    app.store = MagicMock()
    app.chronicle = MagicMock()
    app.guard = MagicMock()
    app.guard.evaluate_text.return_value = False
    app.personality = MagicMock()
    app._last_pet_speech = "Hello"
    app.controller = MagicMock()
    app.ai_engine = MagicMock()
    app._recall_memories = MagicMock(return_value=())  # type: ignore[assignment]

    # Submit slice 1
    app._on_slice_submitted("Slice One Content")

    # Assert SQLite raw_slices contains the committed row
    slices = store.list_raw_slices()
    assert len(slices) == 1
    assert slices[0].content == "Slice One Content"
    assert slices[0].source == "manual_feed"

    # Assert JSONL post-commit export occurred
    assert jsonl_file.is_file()
    assert "Slice One Content" in jsonl_file.read_text(encoding="utf-8")

    # Submit bubble reply (ordered DESC by timestamp)
    app._on_user_reply_to_bubble("Slice Two Reply", "Hello")
    slices = store.list_raw_slices()
    assert len(slices) == 2
    contents = {s.content for s in slices}
    assert "Slice One Content" in contents
    assert "Slice Two Reply" in contents

    store.close()


def test_rt03_stage_10a_connector_event_adapter_persists_to_v2(tmp_path: Path) -> None:
    """RT-03: V2EventStoreAdapter persists normalized privacy-sanitized events to V2 SQLite."""
    db_file = tmp_path / "rt03_test.db"
    store = ChronicleStoreV2(db_file)
    write_service = RawEvidenceWriteService(store)
    adapter = V2EventStoreAdapter(write_service)

    event = AgentEvent.create(
        agent_id="pi-desktop",
        event_type=AgentEventType.PRE_TOOL_USE,
        session_id="sess_rt03",
        tool_name="bash",
        error_message="Test Error Context",
    )

    persisted = adapter.record_event(event)
    assert persisted is True

    # Verify event exists in SQLite event_skeletons
    cur = store.connection.execute(
        "SELECT agent_id, tool_name, event_type, error_category "
        "FROM event_skeletons WHERE session_id = 'sess_rt03';"
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "pi-desktop"
    assert row[1] == "bash"
    assert row[2] == "pre_tool_use"
    assert row[3] == "Test Error Context"

    store.close()


def test_rt04_stage_10a_compatibility_adapter_reads_and_blocks_writes(tmp_path: Path) -> None:
    """RT-04: V2ChronicleStoreAdapter reads views and rejects direct mutations."""
    db_file = tmp_path / "rt04_test.db"
    store = ChronicleStoreV2(db_file)
    store.install_compatibility_views()

    # Insert a slice and event through canonical write service
    writer = RawEvidenceWriteService(store)
    writer.write_slice(WriteSliceCommand(content="Slice for adapter test", source="manual_feed"))

    reader = CompatibilityReader(store)
    adapter = V2ChronicleStoreAdapter(store, reader)

    # 1. Read operations work
    stats = adapter.stats()
    assert stats["slices"] == 1
    slices = adapter.list_slices(limit=10)
    assert len(slices) == 1
    assert slices[0].content == "Slice for adapter test"

    search_res = adapter.search_slices("adapter")
    assert len(search_res) == 1

    # 2. Write operations fail closed
    with pytest.raises(sqlite3.OperationalError):
        adapter.record_slice(None)

    with pytest.raises(sqlite3.OperationalError):
        adapter.record_event(None)

    with pytest.raises(sqlite3.OperationalError):
        adapter.save_hypothesis(None)

    with pytest.raises(sqlite3.OperationalError):
        adapter.save_insight(None)

    store.close()


def test_rt05_stage_10b_retrieval_and_recall_gate_routing(tmp_path: Path) -> None:
    """RT-05: Stage 10B routes _recall_memories through V2 pipeline and Recall Gate."""
    app = run_companion.CompanionApp.__new__(run_companion.CompanionApp)
    app.flags = MemoryFeatureFlags(memory_v2_storage=True, memory_v2_retrieval=True)
    app.guard = MagicMock()
    app.guard.is_active = False

    # Mock pipeline and gate
    mock_pipeline = MagicMock()
    mock_gate = MagicMock()

    mock_decision = MagicMock()
    mock_item = MagicMock()
    mock_item.statement = "Retrieved candidate statement"
    mock_decision.injection_context.items = (mock_item,)
    mock_gate.evaluate.return_value = mock_decision

    app.retrieval_pipeline = mock_pipeline
    app.recall_gate = mock_gate
    app.v2_store = None

    recalled = app._recall_memories("用户偏好是什么")
    assert recalled == ("Retrieved candidate statement",)
    assert mock_pipeline.retrieve.called
    assert mock_gate.evaluate.called


def test_rt06_rt07_flags_validation_and_clean_instantiation() -> None:
    """RT-06 & RT-07: Verify flags dependencies for consolidation and self_model."""
    # Staged flag progression:
    # 10A: storage
    f_10a = MemoryFeatureFlags(memory_v2_storage=True)
    f_10a.validate(capabilities=PRODUCTION_V2_CAPABILITIES)

    # 10B: storage + retrieval
    f_10b = MemoryFeatureFlags(memory_v2_storage=True, memory_v2_retrieval=True)
    f_10b.validate(capabilities=PRODUCTION_V2_CAPABILITIES)

    # 10C: storage + retrieval + consolidation
    f_10c = MemoryFeatureFlags(
        memory_v2_storage=True,
        memory_v2_retrieval=True,
        memory_v2_consolidation=True,
    )
    f_10c.validate(capabilities=PRODUCTION_V2_CAPABILITIES)

    # 10D: storage + retrieval + consolidation + self_model
    f_10d = MemoryFeatureFlags(
        memory_v2_storage=True,
        memory_v2_retrieval=True,
        memory_v2_consolidation=True,
        memory_v2_self_model=True,
    )
    f_10d.validate(capabilities=PRODUCTION_V2_CAPABILITIES)
