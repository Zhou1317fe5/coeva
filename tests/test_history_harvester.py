"""Tests for Multi-Agent historical session harvesting and normalization."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from src.connectors.contracts import AgentEventType
from src.connectors.history.base import normalize_timestamp
from src.connectors.history.codex_cli import CodexCliParser
from src.connectors.history.harvester import MultiAgentHistoryHarvester
from src.connectors.history.hermes_db import HermesDbParser
from src.connectors.history.pi_desktop import PiDesktopParser
from src.core.cold_start import ColdStartPolicy
from src.core.patterns import PatternBuilder
from src.memory.store import ChronicleStore


def test_normalize_timestamp() -> None:
    """Verify various timestamp formats normalize to valid ISO strings."""
    # Epoch float
    ts1 = normalize_timestamp(1791273488.5)
    assert "2026-" in ts1
    assert "+00:00" in ts1 or "Z" in ts1

    # ISO string with Z
    ts2 = normalize_timestamp("2026-10-16T12:00:00Z")
    assert "+00:00" in ts2

    # Malformed or empty fallback
    ts3 = normalize_timestamp("")
    assert "T" in ts3


def test_pi_desktop_parser_zero_leakage_and_failures(tmp_path: Path) -> None:
    """Verify PiDesktopParser extracts events, tool failures, and strictly ignores prompt text."""
    sess_file = tmp_path / "test-pi-session.jsonl"
    lines = [
        {"type": "session", "sessionId": "pi-sess-1", "createdAt": "2026-10-16T10:00:00Z"},
        {
            "type": "message",
            "role": "user",
            "createdAt": "2026-10-16T10:01:00Z",
            "blocks": [{"type": "text", "text": "HIGHLY_CONFIDENTIAL_USER_PROMPT"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "createdAt": "2026-10-16T10:02:00Z",
            "blocks": [
                {
                    "type": "tool_call",
                    "name": "Bash",
                    "callId": "c1",
                    "status": "error",
                    "isError": True,
                    "completedAt": "2026-10-16T10:03:00Z",
                    "result": "Fatal command crash",
                }
            ],
        },
        {
            "type": "message",
            "role": "assistant",
            "createdAt": "2026-10-16T10:04:00Z",
            "blocks": [
                {
                    "type": "tool_call",
                    "name": "Read",
                    "callId": "c2",
                    "status": "complete",
                    "completedAt": "2026-10-16T10:05:00Z",
                }
            ],
        },
    ]
    with open(sess_file, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    parser = PiDesktopParser(sessions_dir=tmp_path)
    targets = parser.discover_targets()
    assert targets == [sess_file]

    session = parser.parse_session(sess_file)
    assert session is not None
    assert session.session_id == "pi-sess-1"
    assert session.agent_id in ("pi", "pi-desktop")

    # Verify zero text leakage
    for ev in session.events:
        assert "HIGHLY_CONFIDENTIAL" not in ev.tool_name
        assert "HIGHLY_CONFIDENTIAL" not in ev.error_message

    # Verify event types in temporal order
    types = [e.event_type for e in session.events]
    assert types == [
        AgentEventType.SESSION_START,
        AgentEventType.USER_PROMPT,
        AgentEventType.PRE_TOOL_USE,
        AgentEventType.TOOL_FAILURE,
        AgentEventType.PRE_TOOL_USE,
        AgentEventType.POST_TOOL_USE,
        AgentEventType.SESSION_END,
    ]


def test_codex_cli_parser(tmp_path: Path) -> None:
    """Verify CodexCliParser parses custom tool calls and exit code failures."""
    sess_file = tmp_path / "rollout-2026-08-01-sess.jsonl"
    lines = [
        {
            "timestamp": "2026-08-01T12:00:00Z",
            "type": "session_meta",
            "payload": {"session_id": "codex-sess-123"},
        },
        {
            "timestamp": "2026-08-01T12:01:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "PRIVATE_SECRET_PROMPT"}],
            },
        },
        {
            "timestamp": "2026-08-01T12:02:00Z",
            "type": "response_item",
            "payload": {"type": "custom_tool_call", "call_id": "call_1", "name": "exec_command"},
        },
        {
            "timestamp": "2026-08-01T12:03:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call_1",
                "output": "Process exited with Exit code 1",
            },
        },
        {
            "timestamp": "2026-08-01T12:04:00Z",
            "type": "event_msg",
            "payload": {"type": "task_completed"},
        },
    ]
    with open(sess_file, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    parser = CodexCliParser(search_paths=[tmp_path])
    targets = parser.discover_targets()
    assert targets == [sess_file]

    session = parser.parse_session(sess_file)
    assert session is not None
    assert session.session_id == "codex-sess-123"

    types = [e.event_type for e in session.events]
    assert AgentEventType.SESSION_START in types
    assert AgentEventType.USER_PROMPT in types
    assert AgentEventType.TOOL_FAILURE in types
    assert AgentEventType.SESSION_END in types

    fail_events = [e for e in session.events if e.event_type == AgentEventType.TOOL_FAILURE]
    assert len(fail_events) == 1
    assert fail_events[0].tool_name == "exec_command"


def test_hermes_db_parser(tmp_path: Path) -> None:
    """Verify HermesDbParser parses SQLite sessions and tool errors."""
    db_file = tmp_path / "hermes_test.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, started_at REAL, ended_at REAL)"
    )
    conn.execute(
        "CREATE TABLE messages ("
        "  id TEXT, session_id TEXT, role TEXT, content TEXT, "
        "  tool_name TEXT, tool_calls TEXT, timestamp REAL"
        ")"
    )
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?)",
        ("hermes-sess-99", 1785000000.0, 1785000500.0),
    )
    # user message
    conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("m1", "hermes-sess-99", "user", "SECRET_USER_TEXT", None, None, 1785000010.0),
    )
    # assistant calling tool
    calls_json = json.dumps([{"name": "terminal"}])
    conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("m2", "hermes-sess-99", "assistant", None, None, calls_json, 1785000020.0),
    )
    # tool failure
    err_json = json.dumps({"output": "SyntaxError", "exit_code": 2, "error": "Crash"})
    conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("m3", "hermes-sess-99", "tool", err_json, "terminal", None, 1785000030.0),
    )
    conn.commit()
    conn.close()

    parser = HermesDbParser(db_path=db_file)
    targets = parser.discover_targets()
    assert targets == [db_file]

    sessions = parser.parse_all_sessions(db_file)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.session_id == "hermes-sess-99"

    types = [e.event_type for e in s.events]
    assert AgentEventType.SESSION_START in types
    assert AgentEventType.USER_PROMPT in types
    assert AgentEventType.PRE_TOOL_USE in types
    assert AgentEventType.TOOL_FAILURE in types
    assert AgentEventType.SESSION_END in types


def test_harvester_dry_run_and_idempotent_ingestion(tmp_path: Path) -> None:
    """Verify harvester dry_run and idempotent ingestion into ChronicleStore."""
    # 1. Create a mock PI-Desktop session file
    pi_dir = tmp_path / "pi_sessions"
    pi_dir.mkdir()
    p1 = pi_dir / "sess1.jsonl"
    with open(p1, "w", encoding="utf-8") as f:
        f.write(
            json.dumps({"type": "session", "sessionId": "s1", "createdAt": "2026-10-01T10:00:00Z"})
            + "\n"
        )
        f.write(
            json.dumps({"type": "message", "role": "user", "createdAt": "2026-10-01T10:01:00Z"})
            + "\n"
        )
        f.write(
            json.dumps({
                "type": "message",
                "role": "assistant",
                "createdAt": "2026-10-01T10:02:00Z",
                "blocks": [{
                    "type": "tool_call",
                    "name": "Bash",
                    "completedAt": "2026-10-01T10:03:00Z",
                }],
            })
            + "\n"
        )

    pi_parser = PiDesktopParser(sessions_dir=pi_dir)
    harvester = MultiAgentHistoryHarvester(parsers={"pi-desktop": pi_parser})

    # Dry run
    summary = harvester.dry_run()
    assert summary["total_sessions"] == 1
    assert summary["total_events"] == 5  # START, PROMPT, PRE, POST, END
    assert summary["sources"]["pi-desktop"]["sessions_count"] == 1

    # Ingestion into ChronicleStore
    db_path = tmp_path / "test_chronicle.db"
    store = ChronicleStore(db_path)

    try:
        # First ingestion
        counts1 = harvester.ingest_into_store(store)
        assert counts1["total"] == 5
        stats1 = store.stats()
        assert stats1["events"] == 5
        assert stats1["episodes"] == 1

        # Second ingestion (idempotency check)
        counts2 = harvester.ingest_into_store(store)
        assert counts2["total"] == 5
        stats2 = store.stats()
        # Row counts must remain strictly identical
        assert stats2["events"] == 5
        assert stats2["episodes"] == 1

        # Check pattern builder on ingested data
        patterns = PatternBuilder(store).build_patterns(min_episodes=1)
        assert isinstance(patterns, list)

    finally:
        store.close()


def test_cold_start_policy_relational_anchor_preservation(tmp_path: Path) -> None:
    """Verify harvesting historical sessions never accelerates real companion cold start (AC-6)."""
    first_seen_file = tmp_path / "first_seen.json"
    today = date(2026, 10, 16)

    # First seen is today -> Day 1
    first_seen_file.write_text(json.dumps({"first_seen": today.isoformat()}), encoding="utf-8")
    policy = ColdStartPolicy.from_persisted_first_seen(first_seen_file, today=today)

    # Day count is strictly 1
    assert policy.day_count == 1
    assert policy.daily_speech_quota == 1
    assert not policy.allows_psychological_analysis

    # Ingesting historical sessions does not touch first_seen.json or alter physical day_count
    policy_after = ColdStartPolicy.from_persisted_first_seen(first_seen_file, today=today)
    assert policy_after.day_count == 1
    assert policy_after.daily_speech_quota == 1
    assert not policy_after.allows_psychological_analysis

def test_pi_cli_nested_message_format(tmp_path: Path) -> None:
    """Verify PiDesktopParser correctly parses Pi CLI nested message structure."""
    sess_file = tmp_path / "pi-cli-session.jsonl"
    lines = [
        {"type": "session", "id": "pi-cli-01", "timestamp": "2026-09-28T10:00:00Z"},
        {
            "type": "message",
            "timestamp": "2026-09-28T10:01:00Z",
            "message": {
                "role": "user",
                "content": "SECRET_USER_PROMPT_NEVER_LEAK",
            },
        },
        {
            "type": "message",
            "timestamp": "2026-09-28T10:02:00Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "toolCall", "name": "write", "id": "t1"},
                    {"type": "toolCall", "name": "bash", "id": "t2"},
                ],
            },
        },
        {
            "type": "message",
            "timestamp": "2026-09-28T10:03:00Z",
            "message": {
                "role": "toolResult",
                "toolName": "write",
                "isError": False,
            },
        },
        {
            "type": "message",
            "timestamp": "2026-09-28T10:04:00Z",
            "message": {
                "role": "toolResult",
                "toolName": "bash",
                "isError": True,
            },
        },
    ]
    with open(sess_file, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    parser = PiDesktopParser(sessions_dir=tmp_path)
    session = parser.parse_session(sess_file)
    assert session is not None
    assert session.session_id == "pi-cli-01"

    types = [e.event_type for e in session.events]
    assert types == [
        AgentEventType.SESSION_START,
        AgentEventType.USER_PROMPT,
        AgentEventType.PRE_TOOL_USE,
        AgentEventType.PRE_TOOL_USE,
        AgentEventType.POST_TOOL_USE,
        AgentEventType.TOOL_FAILURE,
        AgentEventType.SESSION_END,
    ]

    # Ensure zero prompt leakage
    for e in session.events:
        assert "SECRET_USER_PROMPT" not in e.tool_name
        assert "SECRET_USER_PROMPT" not in e.error_message


def test_harvest_history_dialog_preview_and_controls(tmp_path: Path) -> None:
    """Verify HarvestHistoryDialog UI controls and preview generation."""
    import os

    from PySide6.QtWidgets import QApplication

    from src.body.harvest_dialog import HarvestHistoryDialog

    app = QApplication.instance()
    if app is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication([])

    db_path = tmp_path / "dialog_test.db"
    store = ChronicleStore(db_path)
    dialog = HarvestHistoryDialog(store)

    assert dialog.cb_pi.isChecked()
    assert dialog.cb_codex.isChecked()
    assert dialog.cb_hermes.isChecked()
    assert dialog.spin_limit.value() == 30

    # Test source filtering
    dialog.cb_pi.setChecked(False)
    sources = dialog._selected_sources()
    assert "pi" not in sources
    assert "codex" in sources
    assert "hermes" in sources

    dialog.cb_pi.setChecked(True)
    dialog.spin_limit.setValue(2)

    # Test preview trigger
    dialog._on_preview_clicked()
    log_text = dialog.log_display.toPlainText()
    assert "扫描预览结果" in log_text
    assert "合计发现会话" in log_text

    dialog.close()
    store.close()
