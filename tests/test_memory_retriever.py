"""Unit and integration tests for cross-session long-term memory retrieval and prompt injection."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from src.core.personality import build_system_prompt, format_memory_snippet, load_personality
from src.memory.retriever import MemoryRetriever
from src.memory.store import ChronicleStore, SliceRecord


def _make_store(tmp_path: Path) -> ChronicleStore:
    db_path = tmp_path / "test_chronicle.db"
    return ChronicleStore(db_path)


def test_temporal_recall_yesterday(tmp_path: Path) -> None:
    """When user asks '昨天我们聊了什么', retriever accurately retrieves yesterday's slices."""
    store = _make_store(tmp_path)
    now_local = datetime.now()
    yesterday_local = (now_local - timedelta(days=1)).date()

    # Create UTC timestamps for yesterday and today
    yesterday_dt = datetime.combine(yesterday_local, time(14, 30)).astimezone(UTC)
    today_dt = datetime.combine(now_local.date(), time(10, 0)).astimezone(UTC)

    store.record_slice(
        SliceRecord(
            id="s_yest_1",
            timestamp=yesterday_dt.isoformat(),
            content="挺顺的，一直在开发桌宠项目",
            mood_flag="neutral",
        )
    )
    store.record_slice(
        SliceRecord(
            id="s_yest_2",
            timestamp=(yesterday_dt + timedelta(minutes=5)).isoformat(),
            content="目前在优化交流功能还有你的形象和行为",
            mood_flag="neutral",
        )
    )
    # Trivial slice on yesterday should be filtered out
    store.record_slice(
        SliceRecord(
            id="s_yest_trivial",
            timestamp=(yesterday_dt - timedelta(hours=1)).isoformat(),
            content="hi",
            mood_flag="neutral",
        )
    )
    # Today slice
    store.record_slice(
        SliceRecord(
            id="s_today_1",
            timestamp=today_dt.isoformat(),
            content="准备开始今天的工作",
            mood_flag="neutral",
        )
    )

    retriever = MemoryRetriever(store)
    recalled = retriever.recall("昨天我们聊了什么", limit=3, now=now_local)

    assert len(recalled) == 2
    assert any("一直在开发桌宠项目" in r for r in recalled)
    assert any("优化交流功能还有你的形象和行为" in r for r in recalled)
    assert not any("hi" in r for r in recalled)
    assert not any("准备开始今天的工作" in r for r in recalled)


def test_temporal_recall_day_before_yesterday(tmp_path: Path) -> None:
    """When user asks '前天聊了什么', retriever targets 2 days ago."""
    store = _make_store(tmp_path)
    now_local = datetime.now()
    two_days_ago = (now_local - timedelta(days=2)).date()

    dt_2d = datetime.combine(two_days_ago, time(16, 0)).astimezone(UTC)
    store.record_slice(
        SliceRecord(
            id="s_2d_ago",
            timestamp=dt_2d.isoformat(),
            content="重构了桌宠的状态机和动效引擎",
            mood_flag="neutral",
        )
    )

    retriever = MemoryRetriever(store)
    recalled = retriever.recall("前天聊了什么", limit=3, now=now_local)

    assert len(recalled) >= 1
    assert "重构了桌宠的状态机和动效引擎" in recalled[0]


def test_open_ended_memory_intent_and_noise_filtering(tmp_path: Path) -> None:
    """Open-ended questions like '你还记得什么' recall substantive memories, filtering noise."""
    store = _make_store(tmp_path)
    now_local = datetime.now()

    # Mix of trivial and substantive historical slices
    slices_data = [
        ("s1", "hi 你好", 10),
        ("s2", "你是谁", 9),
        ("s3", "测试气泡", 8),
        ("s4", "嗯嗯好的", 7),
        ("s5", "挺顺的，一直在开发桌宠项目", 6),
        ("s6", "目前在优化交流功能还有你的形象和行为", 5),
    ]
    for sid, content, hrs_ago in slices_data:
        store.record_slice(
            SliceRecord(
                id=sid,
                timestamp=(now_local - timedelta(hours=hrs_ago)).astimezone(UTC).isoformat(),
                content=content,
                mood_flag="neutral",
            )
        )

    retriever = MemoryRetriever(store)

    for query in ["你还记得什么", "我们之前聊过什么", "你了解我吗"]:
        recalled = retriever.recall(query, limit=2, now=now_local)
        assert len(recalled) == 2
        # Only meaningful slices must be present
        for item in recalled:
            assert not any(t in item for t in ["hi 你好", "你是谁", "测试气泡", "嗯嗯好的"])
            assert any(k in item for k in ["桌宠项目", "优化交流功能"])


def test_topic_keyword_recall(tmp_path: Path) -> None:
    """Semantic topic matching retrieves relevant past discussions."""
    store = _make_store(tmp_path)
    now_local = datetime.now()

    store.record_slice(
        SliceRecord(
            id="s_topic_1",
            timestamp=(now_local - timedelta(days=3)).astimezone(UTC).isoformat(),
            content="桌宠项目的透明通道在 Windows 下需要设置 WA_TranslucentBackground",
            mood_flag="neutral",
        )
    )
    store.record_slice(
        SliceRecord(
            id="s_topic_2",
            timestamp=(now_local - timedelta(days=2)).astimezone(UTC).isoformat(),
            content="今天去公园散步吹了吹晚风",
            mood_flag="neutral",
        )
    )

    retriever = MemoryRetriever(store)
    recalled = retriever.recall("桌宠项目的透明通道怎么弄的来着", limit=2, now=now_local)

    assert len(recalled) == 1
    assert "WA_TranslucentBackground" in recalled[0]


def test_exclude_ids_and_self_query(tmp_path: Path) -> None:
    """Current slice ID and duplicate self-inquiry text are never recalled into prompt."""
    store = _make_store(tmp_path)
    now_local = datetime.now()

    store.record_slice(
        SliceRecord(
            id="curr_slice",
            timestamp=now_local.astimezone(UTC).isoformat(),
            content="昨天我们聊了什么",
            mood_flag="neutral",
        )
    )
    store.record_slice(
        SliceRecord(
            id="past_slice",
            timestamp=(now_local - timedelta(days=1)).astimezone(UTC).isoformat(),
            content="昨天正在进行模型联调测试",
            mood_flag="neutral",
        )
    )

    retriever = MemoryRetriever(store)
    recalled = retriever.recall(
        "昨天我们聊了什么",
        limit=2,
        exclude_ids={"curr_slice"},
        now=now_local,
    )

    assert len(recalled) == 1
    assert "正在进行模型联调测试" in recalled[0]
    assert not any("昨天我们聊了什么" in r for r in recalled)


def test_system_prompt_injection() -> None:
    """System prompt correctly incorporates recalled memories and instructions."""
    profile = load_personality("vasu")
    memories = (
        "[2026-10-17] 用户提到: 挺顺的，一直在开发桌宠项目",
        "[2026-10-17] 用户提到: 目前在优化交流功能还有你的形象和行为",
    )
    prompt = build_system_prompt(profile, memories=memories)

    assert "【你与用户的过往真实经历记忆" in prompt
    assert "挺顺的，一直在开发桌宠项目" in prompt
    assert "目前在优化交流功能还有你的形象和行为" in prompt


def test_run_companion_retriever_wiring(tmp_path: Path) -> None:
    """CompanionApp integrates MemoryRetriever on startup."""
    import run_companion

    app = run_companion.CompanionApp.__new__(run_companion.CompanionApp)
    store = _make_store(tmp_path)
    app.chronicle = store

    # Call _recall_memories
    memories = app._recall_memories("昨天我们聊了什么")
    assert isinstance(memories, tuple)
    assert hasattr(app, "retriever")
    assert isinstance(app.retriever, MemoryRetriever)
