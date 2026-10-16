"""Agent Hook auto-detection, installation and removal manager inspired by Clawd on Desk."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PI_CLI_EXTENSION_MJS = """import http from "node:http";
import { execFile } from "node:child_process";

const COMPANION_PORT = 17321;
const isWSL = typeof process !== "undefined" &&
  (process.platform === "linux" && !!process.env.WSL_DISTRO_NAME);

function postEvent(payload) {
  try {
    const data = JSON.stringify(payload);
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: COMPANION_PORT,
        path: "/api/event",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(data),
          "Connection": "close",
        },
        timeout: 400,
      },
      (res) => {
        res.resume();
      }
    );
    req.on("error", () => {
      if (isWSL) {
        try {
          execFile("curl.exe", [
            "-s", "-X", "POST",
            `http://127.0.0.1:${COMPANION_PORT}/api/event`,
            "-H", "Content-Type: application/json",
            "-d", data
          ], () => {});
        } catch (_e) {}
      }
    });
    req.on("timeout", () => req.destroy());
    req.write(data);
    req.end();
  } catch (_err) {}
}

export default function companionBridge(pi) {
  if (!pi || typeof pi.on !== "function") return;
  const platform = isWSL ? "wsl" : "windows";
  const distro = process.env.WSL_DISTRO_NAME || (isWSL ? "Ubuntu" : null);

  pi.on("session_start", () => {
    postEvent({
      agent_id: "pi-cli", platform, distro,
      event_type: "session_start", session_id: "pi_cli_session",
      message: "🌱 Pi CLI 已接入"
    });
  });
  pi.on("before_agent_start", () => {
    postEvent({
      agent_id: "pi-cli", platform, distro,
      event_type: "user_prompt", session_id: "pi_cli_session",
      message: "🤔 Pi CLI 正在思考..."
    });
  });
  pi.on("tool_call", (event) => {
    const toolName = (event && event.toolName) || "tool";
    postEvent({
      agent_id: "pi-cli", platform, distro,
      event_type: "pre_tool_use", session_id: "pi_cli_session",
      tool_name: toolName, message: `⚙️ Pi 运行: ${toolName}`
    });
  });
  pi.on("tool_result", (event) => {
    if (event && event.isError) {
      const toolName = event.toolName || "tool";
      postEvent({
        agent_id: "pi-cli", platform, distro,
        event_type: "tool_failure", session_id: "pi_cli_session",
        tool_name: toolName, message: `⚠️ 工具报错: ${toolName}`
      });
    }
  });
  pi.on("turn_end", () => {
    postEvent({
      agent_id: "pi-cli", platform, distro,
      event_type: "task_complete", session_id: "pi_cli_session",
      message: "🎉 Pi CLI 回合完成"
    });
  });
  pi.on("session_shutdown", () => {
    postEvent({
      agent_id: "pi-cli", platform, distro,
      event_type: "session_end", session_id: "pi_cli_session"
    });
  });
}
"""

HERMES_PLUGIN_YAML = """name: companion-bridge
version: "0.1.0"
description: "Forward Hermes Agent lifecycle events to Co-evolving AI Companion."
author: "Co-evolving Companion"

hooks:
  - on_session_start
  - pre_llm_call
  - post_llm_call
  - pre_tool_call
  - post_tool_call
  - on_session_end
  - on_session_finalize
  - on_session_reset
"""

HERMES_INIT_PY = """# Companion Bridge plugin for Hermes Agent
from __future__ import annotations

import json
import subprocess
from typing import Any
from urllib import request

COMPANION_URL = "http://127.0.0.1:17321/api/event"

def _post_event(payload: dict[str, Any]) -> None:
    try:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            COMPANION_URL,
            data=raw,
            headers={"Content-Type": "application/json", "Connection": "close"},
            method="POST"
        )
        with request.urlopen(req, timeout=0.5):
            pass
    except Exception:
        # Fallback for WSL2 NAT mode using Windows curl.exe interop
        try:
            raw_str = json.dumps(payload, ensure_ascii=False)
            cmd = [
                "curl.exe", "-s", "-X", "POST", COMPANION_URL,
                "-H", "Content-Type: application/json", "-d", raw_str
            ]
            subprocess.run(cmd, timeout=1.0, capture_output=True, check=False)
        except Exception:
            pass

def on_session_start(session_id: str, **kwargs: Any) -> None:
    _post_event({
        "agent_id": "hermes", "event_type": "session_start",
        "session_id": session_id, "message": "🌱 Hermes 会话启动"
    })

def pre_llm_call(session_id: str, **kwargs: Any) -> None:
    _post_event({
        "agent_id": "hermes", "event_type": "user_prompt",
        "session_id": session_id, "message": "🤔 Hermes 思考中..."
    })

def pre_tool_call(session_id: str, tool_name: str, **kwargs: Any) -> None:
    _post_event({
        "agent_id": "hermes", "event_type": "pre_tool_use",
        "session_id": session_id, "tool_name": tool_name,
        "message": f"⚙️ Hermes 运行: {tool_name}"
    })

def post_tool_call(session_id: str, tool_name: str, is_error: bool = False, **kwargs: Any) -> None:
    if is_error:
        _post_event({
            "agent_id": "hermes", "event_type": "tool_failure",
            "session_id": session_id, "tool_name": tool_name,
            "message": f"⚠️ Hermes 工具报错: {tool_name}"
        })

def post_llm_call(session_id: str, **kwargs: Any) -> None:
    _post_event({
        "agent_id": "hermes", "event_type": "task_complete",
        "session_id": session_id, "message": "🎉 Hermes 回合完成"
    })

def on_session_end(session_id: str, **kwargs: Any) -> None:
    _post_event({"agent_id": "hermes", "event_type": "session_end", "session_id": session_id})

def on_session_finalize(session_id: str, **kwargs: Any) -> None:
    _post_event({"agent_id": "hermes", "event_type": "session_end", "session_id": session_id})

def on_session_reset(session_id: str, **kwargs: Any) -> None:
    _post_event({"agent_id": "hermes", "event_type": "session_start", "session_id": session_id})
"""


class AgentHookManager:
    """Manages one-click deployment, inspection and removal of Agent sensor hooks."""

    @staticmethod
    def get_wsl_distros() -> list[str]:
        """Enumerate active/installed WSL distribution names."""
        if sys.platform != "win32":
            return []
        try:
            res = subprocess.run(
                ["wsl.exe", "-l", "-q"],
                capture_output=True,
                check=False,
                timeout=2.0,
            )
            # wsl.exe -l -q outputs UTF-16LE or ASCII with nulls
            text = res.stdout.decode("utf-16le", errors="ignore").replace("\x00", "")
            if not text.strip():
                text = res.stdout.decode("utf-8", errors="ignore")
            distros = [line.strip() for line in text.splitlines() if line.strip()]
            return distros
        except Exception:
            return []

    @staticmethod
    def get_wsl_user_home(distro: str) -> Path | None:
        """Find the default non-root user home directory inside a WSL distro."""
        base_path = Path(rf"\\wsl$\{distro}\home")
        if not base_path.is_dir():
            return None
        try:
            users = [p for p in base_path.iterdir() if p.is_dir()]
            if users:
                # Return the first user or prioritize non-root
                return users[0]
        except Exception:
            pass
        return None

    # ── Inspection ──
    def check_hook_status(self, agent_id: str, instance_id: str) -> dict[str, Any]:
        """Return hook status: 'installed', 'not_installed', or 'unsupported'."""
        target_dir = self._resolve_target_dir(agent_id, instance_id)
        if target_dir is None:
            return {"installed": False, "status": "unsupported", "target_dir": None}

        if agent_id == "pi-cli":
            file_path = target_dir / "index.mjs"
            is_ins = file_path.is_file()
            return {
                "installed": is_ins,
                "status": "installed" if is_ins else "not_installed",
                "target_dir": str(target_dir),
            }

        if agent_id == "hermes":
            file_path = target_dir / "plugin.yaml"
            is_ins = file_path.is_file()
            return {
                "installed": is_ins,
                "status": "installed" if is_ins else "not_installed",
                "target_dir": str(target_dir),
            }

        if agent_id == "pi-desktop":
            reg_file = Path.home() / ".pi-desktop" / "plugins" / "registry.json"
            is_ins = False
            if reg_file.is_file():
                try:
                    with open(reg_file, encoding="utf-8") as f:
                        plugins = json.load(f)
                    is_ins = any(p.get("id") == "pi.companion-bridge" for p in plugins)
                except Exception:
                    pass
            return {
                "installed": is_ins,
                "status": "installed" if is_ins else "not_installed",
                "target_dir": str(target_dir),
            }

        return {"installed": False, "status": "not_installed", "target_dir": str(target_dir)}

    # ── Installation ──
    def install_hook(self, agent_id: str, instance_id: str) -> dict[str, Any]:
        """Deploy hook sensor files into the agent's environment."""
        target_dir = self._resolve_target_dir(agent_id, instance_id)
        if target_dir is None:
            return {"ok": False, "error": f"Unsupported or unreachable instance: {instance_id}"}

        try:
            target_dir.mkdir(parents=True, exist_ok=True)

            if agent_id == "pi-cli":
                (target_dir / "index.mjs").write_text(PI_CLI_EXTENSION_MJS, encoding="utf-8")
                return {"ok": True, "message": f"Pi CLI 扩展已成功部署至 {target_dir}"}

            if agent_id == "hermes":
                (target_dir / "plugin.yaml").write_text(HERMES_PLUGIN_YAML, encoding="utf-8")
                (target_dir / "__init__.py").write_text(HERMES_INIT_PY, encoding="utf-8")
                return {"ok": True, "message": f"Hermes 插件已成功部署至 {target_dir}"}

            return {"ok": False, "error": f"No automatic installer for {agent_id}"}
        except Exception as err:
            return {"ok": False, "error": str(err)}

    # ── Removal ──
    def uninstall_hook(self, agent_id: str, instance_id: str) -> dict[str, Any]:
        """Cleanly remove deployed hook sensor files."""
        target_dir = self._resolve_target_dir(agent_id, instance_id)
        if target_dir is None or not target_dir.exists():
            return {"ok": True, "message": "Nothing to uninstall (target directory not present)"}

        try:
            shutil.rmtree(target_dir, ignore_errors=True)
            return {"ok": True, "message": f"已成功移除 {agent_id} ({instance_id}) 的 Hook 扩展"}
        except Exception as err:
            return {"ok": False, "error": str(err)}

    def _resolve_target_dir(self, agent_id: str, instance_id: str) -> Path | None:
        """Resolve physical filesystem target directory for the hook."""
        is_wsl = instance_id.startswith("wsl")
        distro = instance_id.split(":", 1)[1] if ":" in instance_id else "Ubuntu-24.04"

        home_dir: Path | None = None
        if is_wsl:
            home_dir = self.get_wsl_user_home(distro)
        else:
            home_dir = Path.home()

        if home_dir is None:
            return None

        if agent_id == "pi-cli":
            return home_dir / ".pi" / "agent" / "extensions" / "companion-bridge"

        if agent_id == "hermes":
            return home_dir / ".hermes" / "plugins" / "companion-bridge"

        if agent_id == "pi-desktop":
            return Path.home() / ".pi-desktop" / "plugins" / "installed" / "pi.companion-bridge"

        return None
