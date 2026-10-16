"""Unit tests for ChronicleViewerWindow UI and store integration."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.body.chronicle_window import ChronicleViewerWindow
from src.connectors.contracts import AgentEvent, AgentEventType
from src.memory.store import ChronicleStore, SliceRecord

_app = QApplication.instance()
if _app is None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _app = QApplication([])


def _populated_store() -> ChronicleStore:
    store = ChronicleStore(Path(":memory:"))
    store.record_slice(
        SliceRecord(
            id="slice_001",
            timestamp="2026-10-16T10:00:00+00:00",
            content="这是一条包含关键词代码的测试切片",
            mood_flag="neutral",
        )
    )
    store.record_slice(
        SliceRecord(
            id="slice_002",
            timestamp="2026-10-16T11:00:00+00:00",
            content="今天调试有点烦死了😡",
            mood_flag="frustrated",
        )
    )
    # Add events for episodes
    store.record_event(
        AgentEvent.create("pi-desktop", AgentEventType.SESSION_START, session_id="session_alpha")
    )
    store.record_event(
        AgentEvent.create("pi-desktop", AgentEventType.USER_PROMPT, session_id="session_alpha")
    )
    store.record_event(
        AgentEvent.create("hermes", AgentEventType.PRE_TOOL_USE, session_id="session_beta")
    )
    return store


def test_chronicle_window_init_and_stats() -> None:
    """Test window builds pages and displays stats badge properly."""
    store = _populated_store()
    win = ChronicleViewerWindow(store)
    try:
        assert win.windowTitle() == "📖 记忆与切片档案 (Chronicle Archive)"
        assert "投喂切片: 2" in win.stats_badge.text()
        assert "遥测事件: 3" in win.stats_badge.text()
        assert "经历会话: 2" in win.stats_badge.text()

        # Page 1: Slices list
        assert win.slices_list.count() == 2
        first_item = win.slices_list.item(0)
        assert "调试有点烦死了" in first_item.text()

        # Selection updates detail box
        win._on_slice_selected(first_item)
        assert "调试有点烦死了" in win.slice_detail.toPlainText()
        assert "frustrated" in win.slice_detail.toPlainText()
    finally:
        win.close()
        store.close()


def test_chronicle_window_episodes_page() -> None:
    """Test switching to Episodes page lists session groups."""
    store = _populated_store()
    win = ChronicleViewerWindow(store)
    try:
        win.nav_list.setCurrentRow(1)
        assert win.stack.currentIndex() == 1
        assert win.episodes_list.count() == 2

        all_text = " ".join(win.episodes_list.item(i).text() for i in range(2))
        assert "session_alpha" in all_text
        assert "session_beta" in all_text
        assert "包含用户主动提示" in all_text
        assert "纯 Agent 自动执行" in all_text
    finally:
        win.close()
        store.close()


def test_chronicle_window_search_flow() -> None:
    """Test searching slices filters items dynamically."""
    store = _populated_store()
    win = ChronicleViewerWindow(store)
    try:
        win.nav_list.setCurrentRow(2)
        assert win.stack.currentIndex() == 2

        # 1. Search existing word
        win.search_input.setText("代码")
        win._do_search()
        assert win.search_results.count() == 1
        item = win.search_results.item(0)
        assert "测试切片" in item.text()

        win._on_search_selected(item)
        assert "这是一条包含关键词代码的测试切片" in win.search_detail.toPlainText()

        # 2. Search missing word
        win.search_input.setText("不存在的内容")
        win._do_search()
        assert win.search_results.count() == 1
        assert "未找到" in win.search_results.item(0).text()
    finally:
        win.close()
        store.close()
