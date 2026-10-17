"""Unit tests for pet-bound personality system and AI dialogue coordination."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from src.connectors.settings import AgentSettingsStore
from src.core.llm_client import (
    CompanionAIEngine,
    LLMConfig,
    query_llm_sync,
    sanitize_reply,
)
from src.core.llm_client import (
    test_connection_sync as ping_llm_sync,
)
from src.core.personality import (
    GLOBAL_INVARIANTS,
    PersonalityProfile,
    build_system_prompt,
    load_personality,
    pick_fallback,
)

_app = QApplication.instance() or QApplication([])


def test_load_vasu_personality() -> None:
    profile = load_personality("vasu")
    assert profile.pet_id == "vasu"
    assert profile.display_name == "Vasu"
    assert "瓦苏德瓦" in profile.identity or "悉达多" in profile.identity
    assert "平静" in profile.traits
    assert len(profile.constraints) >= 2
    assert len(profile.few_shots) >= 3

    # Fallbacks should have non-empty pools
    assert len(profile.fallback.slice_normal) >= 2
    assert len(profile.fallback.slice_distressed) >= 2
    assert len(profile.fallback.poke) >= 2


def test_load_missing_personality_fallback() -> None:
    profile = load_personality("unknown_dragon_xyz")
    assert profile.pet_id == "unknown_dragon_xyz"
    assert isinstance(profile, PersonalityProfile)
    assert len(profile.fallback.slice_normal) >= 1


def test_build_system_prompt_includes_invariants_and_custom_suffix() -> None:
    profile = load_personality("vasu")
    prompt = build_system_prompt(profile, custom_user_suffix="多提醒我喝水")

    # Invariants must be in prompt
    for inv in GLOBAL_INVARIANTS:
        assert inv in prompt

    # Pet traits and custom suffix must be in prompt
    assert profile.identity in prompt
    assert "多提醒我喝水" in prompt


def test_pick_fallback_categories() -> None:
    profile = load_personality("vasu")
    line_normal = pick_fallback(profile, "slice_normal")
    assert line_normal in profile.fallback.slice_normal

    line_distressed = pick_fallback(profile, "slice_distressed")
    assert line_distressed in profile.fallback.slice_distressed

    line_poke = pick_fallback(profile, "poke")
    assert line_poke in profile.fallback.poke

    line_overwork = pick_fallback(profile, "state_care_overwork")
    assert line_overwork in profile.fallback.state_care_overwork

    line_late_night = pick_fallback(profile, "state_care_late_night")
    assert line_late_night in profile.fallback.state_care_late_night


def test_sanitize_reply_clean_and_truncate() -> None:
    # 1. Clean prefixes and quotes
    raw1 = 'Vasu: "好的，我已经记下了。"'
    clean1 = sanitize_reply(raw1)
    assert clean1 == "好的，我已经记下了。"

    # 2. Multiline taking first line
    raw2 = "第一行回答。\n第二行大段长篇大论小作文。"
    clean2 = sanitize_reply(raw2)
    assert clean2 == "第一行回答。"

    # 3. Excessive length truncated at punctuation
    raw3 = "这是一段非常非常长的文字，它企图在桌面的小气泡里面说很多很多话，超过了字数限制。"
    clean3 = sanitize_reply(raw3, max_chars=25)
    assert len(clean3) <= 25
    assert clean3.endswith("。")


def test_companion_ai_engine_disabled_fallback() -> None:
    profile = load_personality("vasu")
    cfg = LLMConfig(enabled=False)
    engine = CompanionAIEngine(config=cfg)

    received_replies: list[str] = []

    def _on_reply(text: str, tag: str) -> None:
        received_replies.append(text)

    engine.reply_ready.connect(_on_reply)
    engine.request_reply("今天写代码好累啊", profile, category="slice_distressed")

    QThreadPool.globalInstance().waitForDone(2000)
    QApplication.processEvents()
    assert len(received_replies) == 1
    assert received_replies[0] in profile.fallback.slice_distressed


def test_companion_ai_engine_enabled_query_success() -> None:
    profile = load_personality("vasu")
    assert profile.pet_id == "vasu"
    cfg = LLMConfig(enabled=True, base_url="http://mock-llm.local", api_key="secret")
    engine = CompanionAIEngine(config=cfg)
    assert engine.config.enabled is True

    mock_resp_body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "“事情理顺了就起身活动下。”",
                    }
                }
            ]
        }
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_body
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        reply = query_llm_sync("System prompt", "User prompt", cfg)
        assert reply == "事情理顺了就起身活动下。"


def test_llm_ping_connection_sync() -> None:
    cfg = LLMConfig(enabled=True, base_url="http://mock-llm.local")

    mock_resp_body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "pong",
                    }
                }
            ]
        }
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_body
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg, lat = ping_llm_sync(cfg)
        assert ok is True
        assert "pong" in msg
        assert lat >= 0


def test_agent_settings_store_llm_config_persistence(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    store = AgentSettingsStore(file_path=settings_file)

    # Initial default
    assert store.llm_config.enabled is False
    assert store.llm_config.base_url == "http://localhost:11434/v1"

    # Modify and save
    new_cfg = LLMConfig(
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test-key",
        model="deepseek-chat",
        temperature=0.5,
        custom_prompt_suffix="多提醒我注意眼睛",
    )
    store.set_llm_config(new_cfg)

    # Reload from disk
    reloaded_store = AgentSettingsStore(file_path=settings_file)
    assert reloaded_store.llm_config.enabled is True
    assert reloaded_store.llm_config.base_url == "https://api.deepseek.com/v1"
    assert reloaded_store.llm_config.api_key == "sk-test-key"
    assert reloaded_store.llm_config.custom_prompt_suffix == "多提醒我注意眼睛"


def test_speech_bubble_interactive_reply() -> None:
    from src.body.speech_bubble import SpeechBubble

    bubble = SpeechBubble()
    bubble.show_message("夜深了。剩下的明天再弄，它跑不了。")
    assert bubble.current_message == "夜深了。剩下的明天再弄，它跑不了。"
    assert bubble.isVisible() is True

    # Open reply mode
    bubble.open_reply_input()
    assert bubble._is_replying is True
    assert bubble._input_row.isVisible() is True

    replies: list[tuple[str, str]] = []

    def _on_reply(user_text: str, orig_pet: str) -> None:
        replies.append((user_text, orig_pet))

    bubble.user_replied.connect(_on_reply)
    bubble._input.setText("还有最后一行，写完就睡。")
    bubble._on_submit_reply()

    assert len(replies) == 1
    assert replies[0] == ("还有最后一行，写完就睡。", "夜深了。剩下的明天再弄，它跑不了。")
    bubble.close()
