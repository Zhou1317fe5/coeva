"""Lightweight, non-blocking LLM client compatible with OpenAI / Ollama protocols."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from src.core.personality import (
    PersonalityProfile,
    build_system_prompt,
    pick_fallback,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_TIMEOUT_SECONDS = 25.0
MAX_REPLY_LENGTH = 32
DEFAULT_LLM_CONFIG_PATH = Path("data") / "llm_config.json"

PRESET_PROVIDERS: dict[str, dict[str, str]] = {
    "Ollama (本地)": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5:3b",
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "vLLM / LM Studio": {
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
    },
    "OneAPI / NewAPI": {
        "base_url": "https://api.openai-proxy.com/v1",
        "default_model": "gpt-4o-mini",
    },
}


@dataclass
class LLMConfig:
    """Configuration for connecting to an OpenAI-compatible endpoint."""

    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = DEFAULT_MODEL
    temperature: float = 0.6
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_tokens: int = 80
    custom_prompt_suffix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMConfig:
        return cls(
            enabled=bool(data.get("enabled", False)),
            base_url=str(data.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
            api_key=str(data.get("api_key", "")).strip(),
            model=str(data.get("model") or DEFAULT_MODEL).strip(),
            temperature=float(data.get("temperature", 0.6)),
            timeout_seconds=float(data.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
            max_tokens=int(data.get("max_tokens", 80)),
            custom_prompt_suffix=str(data.get("custom_prompt_suffix", "")).strip(),
        )
    @classmethod
    def load(cls, path: Path | None = None) -> LLMConfig:
        """Load LLM config from disk, falling back to defaults if missing or broken."""
        if path is not None:
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return cls.from_dict(data)
                except (json.JSONDecodeError, OSError):
                    pass
            return cls()

        # Default resolution order: llm_config.json -> agent_settings.json
        if DEFAULT_LLM_CONFIG_PATH.is_file():
            try:
                data = json.loads(DEFAULT_LLM_CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("api_key"):
                    return cls.from_dict(data)
            except (json.JSONDecodeError, OSError):
                pass
        agent_settings_file = Path("data") / "agent_settings.json"
        if agent_settings_file.is_file():
            try:
                as_data = json.loads(agent_settings_file.read_text(encoding="utf-8"))
                if (
                    isinstance(as_data, dict)
                    and "llm" in as_data
                    and isinstance(as_data["llm"], dict)
                ):
                    return cls.from_dict(as_data["llm"])
            except (json.JSONDecodeError, OSError):
                pass
        return cls()

    def save(self, path: Path | None = None) -> None:
        """Persist configuration to disk."""
        cfg_path = path or DEFAULT_LLM_CONFIG_PATH
        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass


class LLMClient:
    """Convenience synchronous client wrapping test_connection for backward compatibility."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.load()

    def test_connection(self) -> tuple[bool, str, float]:
        return test_connection_sync(self.config)

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Execute chat completion and return response string for chapter generation."""
        sys_p = system_prompt or ""
        user_parts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        user_p = "\n\n".join(user_parts) if user_parts else "ping"
        cfg = LLMConfig(
            enabled=True,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            model=model or self.config.model,
            temperature=temperature if temperature is not None else self.config.temperature,
            timeout_seconds=self.config.timeout_seconds,
        )
        return query_llm_sync(sys_p, user_p, cfg)


def sanitize_reply(raw_text: str, max_chars: int = MAX_REPLY_LENGTH) -> str:
    """Clean LLM output into a crisp, single-line companion speech bubble text."""
    text = raw_text.strip()
    if not text:
        return ""

    # Remove code blocks or markdown quotes if any
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
    # Remove leading quotes or prefixes like "Vasu:", "回复:", "【答】"
    text = re.sub(r"^(?:Vasu[:：]|瓦苏[:：]|回复[:：]|【.*?】)\s*", "", text).strip()
    text = text.strip("\"'“”「」")
    # Collapse multiple whitespaces and newlines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        text = lines[0]  # Take only the first sentence/line

    # If sentence exceeds limit, cut at natural punctuation
    if len(text) > max_chars:
        punct_matches = list(re.finditer(r"[。！？!?；;]", text[:max_chars]))
        if punct_matches:
            last_end = punct_matches[-1].end()
            if last_end >= 10:  # meaningful sentence
                text = text[:last_end]
            else:
                text = text[: max_chars - 1].rstrip("，,、 ") + "。"
        else:
            text = text[: max_chars - 1].rstrip("，,、 ") + "。"

    return text.strip()


def query_llm_sync(
    system_prompt: str,
    user_prompt: str,
    config: LLMConfig,
    *,
    timeout_seconds: float | None = None,
) -> str:
    """Execute a synchronous HTTP POST request to an OpenAI-compatible endpoint."""
    base = config.base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Co-evolving-Companion/0.1.0",
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": 80,
        "stream": False,
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

    effective_timeout = timeout_seconds or config.timeout_seconds
    with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
        resp_body = resp.read().decode("utf-8")
        data = json.loads(resp_body)
        choices = data.get("choices", [])
        if choices and isinstance(choices, list):
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str):
                    return sanitize_reply(content)

    return ""


def test_connection_sync(config: LLMConfig) -> tuple[bool, str, float]:
    """Test API connectivity with a lightweight ping. Returns (success, message, latency_ms)."""
    t0 = time.time()
    try:
        reply = query_llm_sync(
            system_prompt="Reply with 'pong' only.",
            user_prompt="ping",
            config=config,
            timeout_seconds=5.0,
        )
        latency = (time.time() - t0) * 1000
        return True, f"连通成功: '{reply}'", latency
    except Exception as e:
        latency = (time.time() - t0) * 1000
        return False, str(e), latency


class _WorkerSignals(QObject):
    finished = Signal(str, str)  # (reply_text, context_tag)
    failed = Signal(str, str)  # (error_message, context_tag)


class _GenerateRunnable(QRunnable):
    """QRunnable task executing the LLM query off the Qt GUI thread."""

    def __init__(
        self,
        system_prompt: str,
        user_prompt: str,
        config: LLMConfig,
        context_tag: str,
        fallback_fn: Callable[[], str],
        signals: _WorkerSignals,
    ) -> None:
        super().__init__()
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.config = config
        self.context_tag = context_tag
        self.fallback_fn = fallback_fn
        self.signals = signals

    def run(self) -> None:
        if not self.config.enabled:
            fallback_text = self.fallback_fn()
            self.signals.finished.emit(fallback_text, self.context_tag)
            return

        try:
            reply = query_llm_sync(
                self.system_prompt,
                self.user_prompt,
                self.config,
                timeout_seconds=self.config.timeout_seconds,
            )
            if reply:
                self.signals.finished.emit(reply, self.context_tag)
            else:
                fallback_text = self.fallback_fn()
                self.signals.finished.emit(fallback_text, self.context_tag)
        except Exception as err:
            logger.debug("LLM query failed (%s); using fallback.", err)
            fallback_text = self.fallback_fn()
            self.signals.finished.emit(fallback_text, self.context_tag)


class CompanionAIEngine(QObject):
    """Asynchronous, thread-safe AI dialogue coordinator for the desktop companion."""

    reply_ready = Signal(str, str)  # (final_text, context_tag)

    def __init__(
        self,
        config: LLMConfig | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config or LLMConfig()
        self._thread_pool = QThreadPool.globalInstance()

    def update_config(self, new_config: LLMConfig) -> None:
        self.config = new_config

    def request_reply(
        self,
        user_context: str,
        profile: PersonalityProfile,
        category: str = "slice_normal",
        *,
        context_tag: str = "",
        memories: tuple[str, ...] = (),
    ) -> None:
        """Asynchronously dispatch an LLM request or immediately provide fallback off-thread."""
        signals = _WorkerSignals()
        signals.finished.connect(self._on_worker_finished)

        system_prompt = build_system_prompt(
            profile,
            custom_user_suffix=self.config.custom_prompt_suffix,
            memories=memories,
        )
        task = _GenerateRunnable(
            system_prompt=system_prompt,
            user_prompt=user_context,
            config=self.config,
            context_tag=context_tag,
            fallback_fn=lambda: pick_fallback(profile, category),
            signals=signals,
        )
        self._thread_pool.start(task)

    def _on_worker_finished(self, reply: str, tag: str) -> None:
        self.reply_ready.emit(reply, tag)
