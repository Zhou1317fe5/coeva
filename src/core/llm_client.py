"""Lightweight, zero-heavy-SDK OpenAI-compatible LLM client and config persistence."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_LLM_CONFIG_PATH = Path("data") / "llm_config.json"

PRESET_PROVIDERS: dict[str, dict[str, str]] = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
    },
    "Ollama (本地)": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5:7b",
    },
    "vLLM / LM Studio (本地)": {
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
    },
    "OneAPI / NewAPI": {
        "base_url": "https://api.openai-proxy.com/v1",
        "default_model": "gpt-4o",
    },
}


@dataclass
class LLMConfig:
    """Configuration for connecting to an OpenAI-compatible LLM endpoint."""

    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout_seconds: float = 30.0
    enabled: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> LLMConfig:
        """Load configuration from disk, falling back to defaults if missing or invalid."""
        cfg_path = path or DEFAULT_LLM_CONFIG_PATH
        if cfg_path.is_file():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                return cls(
                    base_url=str(data.get("base_url", cls.base_url)),
                    api_key=str(data.get("api_key", "")),
                    model=str(data.get("model", cls.model)),
                    temperature=float(data.get("temperature", cls.temperature)),
                    max_tokens=int(data.get("max_tokens", cls.max_tokens)),
                    timeout_seconds=float(data.get("timeout_seconds", cls.timeout_seconds)),
                    enabled=bool(data.get("enabled", True)),
                )
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        return cls()

    def save(self, path: Path | None = None) -> None:
        """Persist configuration to disk."""
        cfg_path = path or DEFAULT_LLM_CONFIG_PATH
        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass


class LLMClient:
    """Lightweight, standard library-only client calling OpenAI-compatible chat completions."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.load()

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send chat messages and return the assistant response string."""
        base = self.config.base_url.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        url = f"{base}/chat/completions"
        mdl = model or self.config.model
        temp = temperature if temperature is not None else self.config.temperature

        payload_msgs: list[dict[str, str]] = []
        if system_prompt:
            payload_msgs.append({"role": "system", "content": system_prompt})
        payload_msgs.extend(messages)

        body: dict[str, Any] = {
            "model": mdl,
            "messages": payload_msgs,
            "temperature": temp,
            "max_tokens": self.config.max_tokens,
        }

        req_data = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Co-evolving-Companion/0.1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))
                choices = data.get("choices", [])
                if not choices:
                    return ""
                msg = choices[0].get("message", {})
                return str(msg.get("content", "")).strip()

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(f"LLM HTTP {e.code}: {e.reason} ({err_body[:200]})") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"LLM Connection failed: {e.reason}") from e
        except TimeoutError as e:
            raise RuntimeError("LLM Request timed out.") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Malformed LLM response: {e}") from e

    def test_connection(self) -> tuple[bool, str, float]:
        """Test API connectivity with a lightweight ping. Returns (success, message, latency_ms)."""
        t0 = time.time()
        try:
            reply = self.chat_completion(
                messages=[{"role": "user", "content": "ping"}],
                system_prompt="Reply with 'pong' only.",
                temperature=0.0,
            )
            latency = (time.time() - t0) * 1000
            snippet = reply[:30].replace("\n", " ")
            return True, f"连通成功 (返回: '{snippet}')", latency
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return False, str(e), latency
