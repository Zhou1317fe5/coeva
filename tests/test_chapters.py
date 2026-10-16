"""Automated tests for Phase 2D Growth Chapters, LLM Client, and Narrative Firewall."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.connectors.contracts import AgentEvent, AgentEventType
from src.core.chapters import (
    ChapterEligibilityGate,
    ChapterGenerator,
    GrowthChapter,
    NarrativeFirewall,
)
from src.core.llm_client import LLMClient, LLMConfig
from src.memory.store import ChronicleStore


def test_llm_config_load_save(tmp_path: Path) -> None:
    """Verify LLMConfig serialization and round-trip persistence."""
    cfg_file = tmp_path / "llm_config.json"
    cfg = LLMConfig(
        base_url="https://api.custom.com/v1",
        api_key="sk-test-secret",
        model="gemini-3.8-flash",
        temperature=0.4,
        max_tokens=1024,
    )
    cfg.save(cfg_file)
    assert cfg_file.is_file()

    loaded = LLMConfig.load(cfg_file)
    assert loaded.base_url == "https://api.custom.com/v1"
    assert loaded.api_key == "sk-test-secret"
    assert loaded.model == "gemini-3.8-flash"
    assert loaded.temperature == 0.4
    assert loaded.max_tokens == 1024


def test_llm_client_mock_completion() -> None:
    """Verify LLMClient builds OpenAI-compatible payloads and extracts response content."""
    cfg = LLMConfig(base_url="https://mock.api/v1", api_key="sk-mock", model="mock-model")
    client = LLMClient(cfg)

    mock_resp_json = {
        "choices": [
            {"message": {"role": "assistant", "content": "Mock Chapter Content"}}
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_resp_json).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        res = client.chat_completion(messages=[{"role": "user", "content": "hello"}])
        assert res == "Mock Chapter Content"

        # Assert Request parameters
        args, _ = mock_urlopen.call_args
        req = args[0]
        assert req.full_url == "https://mock.api/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer sk-mock"
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["model"] == "mock-model"
        assert payload["messages"] == [{"role": "user", "content": "hello"}]


def test_narrative_firewall_sanitization() -> None:
    """Verify NarrativeFirewall censors flattery and preaching phrases."""
    dirty_text = "你太棒了，展现了卓越的智慧与令人钦佩的毅力。你应该放松，建议你以后多休息。"
    clean_text = NarrativeFirewall.sanitize_narrative(dirty_text)

    assert "你太棒了" not in clean_text
    assert "卓越的智慧" not in clean_text
    assert "令人钦佩" not in clean_text
    assert "你应该放松" not in clean_text
    assert "建议你以后" not in clean_text
    assert "踏实的投入" in clean_text


def test_chapter_eligibility_gate_thresholds(tmp_path: Path) -> None:
    """Verify 4 eligibility gates reject insufficient history and pass mature history."""
    store = ChronicleStore(tmp_path / "test_chronicle.db")
    gate = ChapterEligibilityGate()

    # 1. Empty database -> Not eligible
    eligible, report = gate.evaluate(store)
    assert not eligible
    assert not report["sustained"]["passed"]
    assert not report["structural"]["passed"]

    # 2. Feed 35 episodes spanning 30 days and 2 agents
    for i in range(35):
        day = (i % 30) + 1
        ts_start = f"2026-06-{day:02d}T10:00:00+00:00"
        ts_end = f"2026-06-{day:02d}T11:00:00+00:00"
        sid = f"sess_{i}"
        agent = "pi" if i % 2 == 0 else "codex"
        store.record_event(
            AgentEvent(
                agent_id=agent,
                event_type=AgentEventType.SESSION_START,
                session_id=sid,
                timestamp=ts_start,
            )
        )
        store.record_event(
            AgentEvent(
                agent_id=agent,
                event_type=AgentEventType.TOOL_FAILURE,
                session_id=sid,
                timestamp=ts_start,
                tool_name="Bash",
                error_message="Exit 1",
            )
        )
        store.record_event(
            AgentEvent(
                agent_id=agent,
                event_type=AgentEventType.SESSION_END,
                session_id=sid,
                timestamp=ts_end,
            )
        )

    eligible_now, report_now = gate.evaluate(store)
    assert eligible_now
    assert report_now["sustained"]["passed"]
    assert report_now["structural"]["passed"]
    assert report_now["diversity"]["passed"]
    store.close()


def test_growth_chapter_rendering_and_file_io(tmp_path: Path) -> None:
    """Verify GrowthChapter to_markdown structure and persistence."""
    chap = GrowthChapter(
        chapter_id="01_test",
        title="在长链路委派与边界收放之间",
        period_start="2026-06-09",
        period_end="2026-10-16",
        primary_lenses=("regulatory_flexibility", "autonomous_action"),
        the_shift="从即时逐条确认转向大段放权与阶段纠偏。",
        evidence_footprints="在 66 次会话中显现充分委派，在 51 次报错摩擦中边界重校。",
        mutual_understanding="节点看结果，报错即校准，过程不微观打断。",
        human_reflection="我们并肩作战的第一份真实印记。",
    )

    md = chap.to_markdown()
    assert "# 在长链路委派与边界收放之间" in md
    assert "## 1. 伴生体的观察与心智转移（The Shift）" in md
    assert "## 2. 客观经历与阻力足迹（Evidence Footprints）" in md
    assert "## 3. 我们的共同默契（Mutual Understanding）" in md
    assert "## 4. 用户手记（Human Reflection · 留白共创）" in md
    assert "我们并肩作战的第一份真实印记。" in md

    save_dir = tmp_path / "chapters"
    fpath = chap.save(save_dir)
    assert fpath.is_file()

    # Verify reloading through ChapterGenerator.list_chapters()
    store = ChronicleStore(tmp_path / "dummy.db")
    gen = ChapterGenerator(store, chapters_dir=save_dir)
    loaded_list = gen.list_chapters()
    assert len(loaded_list) == 1
    loaded = loaded_list[0]
    assert loaded.title == "在长链路委派与边界收放之间"
    assert loaded.period_start == "2026-06-09"
    assert loaded.human_reflection == "我们并肩作战的第一份真实印记。"
    store.close()
