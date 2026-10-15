"""Unit tests for Slice Feeder components."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.feeder.contracts import RawSlice
from src.feeder.overlay import SliceFeederOverlay
from src.feeder.storage import SliceStore

_app = QApplication.instance()
if _app is None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _app = QApplication([])


def test_raw_slice_creation_and_dict() -> None:
    """Test RawSlice creation with default and custom mood."""
    slice_item = RawSlice.create("今天读《悉达多》有感，允许河流经过。", mood_flag="reflective")
    assert slice_item.actor == "user"
    assert slice_item.source == "manual_feed"
    assert "河流" in slice_item.content
    assert slice_item.mood_flag == "reflective"
    assert slice_item.id.startswith("slice_")

    data = slice_item.to_dict()
    assert data["id"] == slice_item.id
    assert data["content"] == slice_item.content


def test_slice_store_save_and_load(tmp_path: Path) -> None:
    """Test SliceStore appending to jsonl file."""
    db_path = tmp_path / "raw_slices.jsonl"
    store = SliceStore(db_path)

    assert store.count() == 0
    assert store.load_recent() == []

    s1 = RawSlice.create("思考 1")
    s2 = RawSlice.create("思考 2", mood_flag="frustrated")

    store.save(s1)
    store.save(s2)

    assert store.count() == 2
    loaded = store.load_recent(10)
    assert len(loaded) == 2
    assert loaded[0].content == "思考 1"
    assert loaded[1].content == "思考 2"
    assert loaded[1].mood_flag == "frustrated"


def test_feeder_overlay_signal_flow() -> None:
    """Test SliceFeederOverlay submit and cancel signals."""
    overlay = SliceFeederOverlay()
    submitted = []
    cancelled = []

    overlay.slice_submitted.connect(lambda s: submitted.append(s))
    overlay.cancelled.connect(lambda: cancelled.append(True))

    # Test submit
    overlay._input.setPlainText("测试切片内容")
    overlay._on_submit()
    assert len(submitted) == 1
    assert submitted[0] == "测试切片内容"

    # Test cancel
    overlay._on_cancel()
    assert len(cancelled) == 1
    overlay.close()
