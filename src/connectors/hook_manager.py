# Companion Bridge hook manager for Agent sensors
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
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

CODEX_HOOK_PY = """# Companion Bridge hook for Codex CLI
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any
from urllib import request

COMPANION_URL = "http://127.0.0.1:17321/api/event"

EVENT_MAP = {
    "sessionstart": ("session_start", "🌱 Codex 会话启动"),
    "userpromptsubmit": ("user_prompt", "🤔 Codex 正在思考..."),
    "pretooluse": ("pre_tool_use", "⚙️ Codex 正在执行工具"),
    "posttooluse": ("task_complete", "🎉 Codex 工具执行完成"),
    "stop": ("turn_end", "💤 Codex 回合完成"),
    "sessionend": ("session_end", "👋 Codex 会话结束"),
}

def _post_event(payload: dict[str, Any]) -> None:
    raw_str = json.dumps(payload, ensure_ascii=False)
    try:
        req = request.Request(
            COMPANION_URL,
            data=raw_str.encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
            method="POST",
        )
        with request.urlopen(req, timeout=0.5):
            pass
    except Exception:
        # Fallback for WSL2 NAT mode using Windows curl.exe interop
        try:
            cmd = [
                "curl.exe", "-s", "-X", "POST", COMPANION_URL,
                "-H", "Content-Type: application/json", "-d", raw_str
            ]
            subprocess.run(cmd, timeout=1.0, capture_output=True, check=False)
        except Exception:
            pass

def main() -> None:
    raw_input = ""
    try:
        if not sys.stdin.isatty():
            raw_input = sys.stdin.read()
    except Exception:
        pass

    payload_in: dict[str, Any] = {}
    if raw_input.strip():
        try:
            payload_in = json.loads(raw_input)
        except Exception:
            pass

    event_name = ""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        event_name = sys.argv[1].strip()
    elif isinstance(payload_in, dict):
        event_name = str(payload_in.get("hook_event_name") or payload_in.get("event") or "")

    event_lower = event_name.lower()
    event_type, default_msg = EVENT_MAP.get(event_lower, ("pre_tool_use", f"⚙️ Codex: {event_name}"))

    session_id = "codex_session"
    tool_name = ""
    if isinstance(payload_in, dict):
        session_id = str(payload_in.get("session_id") or session_id)
        tool_name = str(payload_in.get("tool_name") or "")

    msg = default_msg
    if tool_name:
        msg = f"⚙️ Codex 运行: {tool_name}"

    is_wsl = bool(os.environ.get("WSL_DISTRO_NAME"))
    platform = "wsl" if is_wsl else "windows"
    distro = os.environ.get("WSL_DISTRO_NAME")

    _post_event({
        "agent_id": "codex",
        "platform": platform,
        "distro": distro,
        "event_type": event_type,
        "session_id": session_id,
        "tool_name": tool_name,
        "message": msg,
    })

if __name__ == "__main__":
    main()
"""

CLAUDE_HOOK_PY = """# Companion Bridge hook for Claude Code
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any
from urllib import request

COMPANION_URL = "http://127.0.0.1:17321/api/event"

EVENT_MAP = {
    "sessionstart": ("session_start", "🌱 Claude Code 会话启动"),
    "userpromptsubmit": ("user_prompt", "🤔 Claude Code 正在思考..."),
    "pretooluse": ("pre_tool_use", "⚙️ Claude Code 正在执行工具"),
    "posttooluse": ("task_complete", "🎉 Claude Code 工具执行完成"),
    "posttoolusefailure": ("tool_failure", "⚠️ Claude Code 工具报错"),
    "stop": ("turn_end", "💤 Claude Code 回合完成"),
    "sessionend": ("session_end", "👋 Claude Code 会话结束"),
}

def _post_event(payload: dict[str, Any]) -> None:
    raw_str = json.dumps(payload, ensure_ascii=False)
    try:
        req = request.Request(
            COMPANION_URL,
            data=raw_str.encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
            method="POST",
        )
        with request.urlopen(req, timeout=0.5):
            pass
    except Exception:
        # Fallback for WSL2 NAT mode using Windows curl.exe interop
        try:
            cmd = [
                "curl.exe", "-s", "-X", "POST", COMPANION_URL,
                "-H", "Content-Type: application/json", "-d", raw_str
            ]
            subprocess.run(cmd, timeout=1.0, capture_output=True, check=False)
        except Exception:
            pass

def main() -> None:
    raw_input = ""
    try:
        if not sys.stdin.isatty():
            raw_input = sys.stdin.read()
    except Exception:
        pass

    payload_in: dict[str, Any] = {}
    if raw_input.strip():
        try:
            payload_in = json.loads(raw_input)
        except Exception:
            pass

    event_name = ""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        event_name = sys.argv[1].strip()
    elif isinstance(payload_in, dict):
        event_name = str(payload_in.get("hook_event_name") or payload_in.get("event") or "")

    event_lower = event_name.lower()
    event_type, default_msg = EVENT_MAP.get(
        event_lower, ("pre_tool_use", f"⚙️ Claude Code: {event_name}")
    )

    session_id = "claude_code_session"
    tool_name = ""
    if isinstance(payload_in, dict):
        session_id = str(payload_in.get("session_id") or session_id)
        tool_name = str(payload_in.get("tool_name") or payload_in.get("tool") or "")

    msg = default_msg
    if tool_name:
        msg = f"⚙️ Claude Code 运行: {tool_name}"

    is_wsl = bool(os.environ.get("WSL_DISTRO_NAME"))
    platform = "wsl" if is_wsl else "windows"
    distro = os.environ.get("WSL_DISTRO_NAME")

    _post_event({
        "agent_id": "claude-code",
        "platform": platform,
        "distro": distro,
        "event_type": event_type,
        "session_id": session_id,
        "tool_name": tool_name,
        "message": msg,
    })

if __name__ == "__main__":
    main()
"""


class AgentHookManager:
    """Manages one-click deployment, inspection and removal of Agent sensor hooks."""

    CODEX_EVENTS: tuple[str, ...] = (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "Stop",
        "SessionEnd",
    )

    CLAUDE_EVENTS: tuple[str, ...] = (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
        "SessionEnd",
    )

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

        if agent_id == "codex":
            file_path = target_dir / "codex_hook.py"
            hooks_file = target_dir.parent / "hooks.json"
            is_ins = file_path.is_file()
            if is_ins and hooks_file.is_file():
                try:
                    with open(hooks_file, encoding="utf-8") as f:
                        text = f.read()
                    is_ins = "companion-bridge" in text
                except Exception:
                    is_ins = False
            return {
                "installed": is_ins,
                "status": "installed" if is_ins else "not_installed",
                "target_dir": str(target_dir),
            }

        if agent_id == "claude-code":
            file_path = target_dir / "claude_hook.py"
            settings_file = target_dir.parent / "settings.json"
            is_ins = file_path.is_file()
            if is_ins and settings_file.is_file():
                try:
                    with open(settings_file, encoding="utf-8") as f:
                        text = f.read()
                    is_ins = "companion-bridge" in text
                except Exception:
                    is_ins = False
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
                    is_ins = any(
                        isinstance(p, dict) and p.get("id") == "pi.companion-bridge"
                        for p in plugins
                    )
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

            if agent_id == "codex":
                (target_dir / "codex_hook.py").write_text(CODEX_HOOK_PY, encoding="utf-8")
                hooks_file = target_dir.parent / "hooks.json"
                hooks_data: dict[str, Any] = {}
                if hooks_file.is_file():
                    try:
                        with open(hooks_file, encoding="utf-8") as f:
                            hooks_data = json.load(f)
                    except Exception:
                        hooks_data = {}
                if not isinstance(hooks_data, dict):
                    hooks_data = {}
                hooks_map = hooks_data.setdefault("hooks", {})
                if not isinstance(hooks_map, dict):
                    hooks_map = {}
                    hooks_data["hooks"] = hooks_map

                is_wsl = instance_id.startswith("wsl")
                distro = instance_id.split(":", 1)[1] if ":" in instance_id else "Ubuntu-24.04"
                if is_wsl:
                    wsl_user = self.get_wsl_user_home(distro)
                    user_name = wsl_user.name if wsl_user else "user"
                    script_posix = f"/home/{user_name}/.codex/companion-bridge/codex_hook.py"
                    for ev in self.CODEX_EVENTS:
                        event_list = hooks_map.setdefault(ev, [])
                        if not isinstance(event_list, list):
                            event_list = []
                            hooks_map[ev] = event_list
                        already = any("companion-bridge" in json.dumps(item) for item in event_list)
                        if not already:
                            event_list.append(
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": f"python3 {script_posix} {ev}",
                                            "timeout": 10,
                                        }
                                    ]
                                }
                            )
                else:
                    win_path = str(target_dir / "codex_hook.py")
                    for ev in self.CODEX_EVENTS:
                        event_list = hooks_map.setdefault(ev, [])
                        if not isinstance(event_list, list):
                            event_list = []
                            hooks_map[ev] = event_list
                        already = any("companion-bridge" in json.dumps(item) for item in event_list)
                        if not already:
                            event_list.append(
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": f'python "{win_path}" {ev}',
                                            "commandWindows": f'python "{win_path}" {ev}',
                                            "timeout": 10,
                                        }
                                    ]
                                }
                            )
                hooks_file.write_text(
                    json.dumps(hooks_data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                return {"ok": True, "message": f"Codex CLI Hook 已成功部署至 {target_dir}"}

            if agent_id == "claude-code":
                (target_dir / "claude_hook.py").write_text(CLAUDE_HOOK_PY, encoding="utf-8")
                settings_file = target_dir.parent / "settings.json"
                settings_data: dict[str, Any] = {}
                if settings_file.is_file():
                    try:
                        with open(settings_file, encoding="utf-8") as f:
                            settings_data = json.load(f)
                    except Exception:
                        settings_data = {}
                if not isinstance(settings_data, dict):
                    settings_data = {}
                hooks_map = settings_data.setdefault("hooks", {})
                if not isinstance(hooks_map, dict):
                    hooks_map = {}
                    settings_data["hooks"] = hooks_map

                is_wsl = instance_id.startswith("wsl")
                distro = instance_id.split(":", 1)[1] if ":" in instance_id else "Ubuntu-24.04"
                if is_wsl:
                    wsl_user = self.get_wsl_user_home(distro)
                    user_name = wsl_user.name if wsl_user else "user"
                    script_posix = f"/home/{user_name}/.claude/companion-bridge/claude_hook.py"
                    for ev in self.CLAUDE_EVENTS:
                        event_list = hooks_map.setdefault(ev, [])
                        if not isinstance(event_list, list):
                            event_list = []
                            hooks_map[ev] = event_list
                        already = any("companion-bridge" in json.dumps(item) for item in event_list)
                        if not already:
                            event_list.append(
                                {
                                    "matcher": "",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": f"python3 {script_posix} {ev}",
                                            "async": True,
                                            "timeout": 5,
                                        }
                                    ],
                                }
                            )
                else:
                    win_path = str(target_dir / "claude_hook.py")
                    for ev in self.CLAUDE_EVENTS:
                        event_list = hooks_map.setdefault(ev, [])
                        if not isinstance(event_list, list):
                            event_list = []
                            hooks_map[ev] = event_list
                        already = any("companion-bridge" in json.dumps(item) for item in event_list)
                        if not already:
                            event_list.append(
                                {
                                    "matcher": "",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "shell": "powershell",
                                            "command": f'python "{win_path}" {ev}',
                                            "async": True,
                                            "timeout": 5,
                                        }
                                    ],
                                }
                            )
                settings_file.write_text(
                    json.dumps(settings_data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                return {"ok": True, "message": f"Claude Code Hook 已成功部署至 {target_dir}"}

            if agent_id == "pi-desktop":
                reg_file = Path.home() / ".pi-desktop" / "plugins" / "registry.json"
                source_dir = (
                    Path(__file__).resolve().parent.parent.parent
                    / "plugins"
                    / "pi-companion-bridge"
                )
                if source_dir.is_dir():
                    shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
                reg_data: list[dict[str, Any]] = []
                if reg_file.is_file():
                    try:
                        with open(reg_file, encoding="utf-8") as f:
                            reg_data = json.load(f)
                    except Exception:
                        reg_data = []
                if not isinstance(reg_data, list):
                    reg_data = []
                if not any(
                    isinstance(p, dict) and p.get("id") == "pi.companion-bridge" for p in reg_data
                ):
                    reg_data.append(
                        {
                            "id": "pi.companion-bridge",
                            "name": "桌面伴生体心跳桥接",
                            "version": "0.1.0",
                            "enabled": True,
                            "scope": {"mode": "global", "projects": []},
                            "source": "installed",
                            "bundled": False,
                            "status": "ready",
                            "permissions": ["ui.panel", "agent.extension"],
                            "path": str(target_dir),
                            "capabilities": ["panel", "commands", "agentExtension"],
                            "description": (
                                "实时同步 PI-Desktop 的思考、工具调用与完成状态至"
                                "桌面伴生体（Co-evolving AI Companion）。"
                            ),
                            "author": "Co-evolving Companion",
                            "installedAt": datetime.now(UTC).isoformat(),
                            "updatedAt": datetime.now(UTC).isoformat(),
                            "autoUpdate": False,
                            "ui": {
                                "panel": "renderer/index.html",
                                "width": 460,
                                "height": 560,
                                "title": {"en": "Companion Bridge", "zh-CN": "桌面伴生体控制台"},
                            },
                        }
                    )
                    reg_file.parent.mkdir(parents=True, exist_ok=True)
                    reg_file.write_text(
                        json.dumps(reg_data, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                return {"ok": True, "message": f"PI-Desktop 插件已成功安装至 {target_dir}"}

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
            if agent_id == "codex":
                hooks_file = target_dir.parent / "hooks.json"
                if hooks_file.is_file():
                    try:
                        with open(hooks_file, encoding="utf-8") as f:
                            hooks_data = json.load(f)
                        if isinstance(hooks_data, dict) and isinstance(
                            hooks_data.get("hooks"), dict
                        ):
                            for ev, groups in list(hooks_data["hooks"].items()):
                                if isinstance(groups, list):
                                    new_groups = []
                                    for grp in groups:
                                        if isinstance(grp, dict) and isinstance(
                                            grp.get("hooks"), list
                                        ):
                                            filtered_hooks = [
                                                h
                                                for h in grp["hooks"]
                                                if isinstance(h, dict)
                                                and "companion-bridge" not in json.dumps(h)
                                            ]
                                            if filtered_hooks:
                                                grp["hooks"] = filtered_hooks
                                                new_groups.append(grp)
                                        elif "companion-bridge" not in json.dumps(grp):
                                            new_groups.append(grp)
                                    hooks_data["hooks"][ev] = new_groups
                            hooks_file.write_text(
                                json.dumps(hooks_data, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                    except Exception:
                        pass

            elif agent_id == "claude-code":
                settings_file = target_dir.parent / "settings.json"
                if settings_file.is_file():
                    try:
                        with open(settings_file, encoding="utf-8") as f:
                            settings_data = json.load(f)
                        if isinstance(settings_data, dict) and isinstance(
                            settings_data.get("hooks"), dict
                        ):
                            for ev, groups in list(settings_data["hooks"].items()):
                                if isinstance(groups, list):
                                    new_groups = []
                                    for grp in groups:
                                        if isinstance(grp, dict) and isinstance(
                                            grp.get("hooks"), list
                                        ):
                                            filtered_hooks = [
                                                h
                                                for h in grp["hooks"]
                                                if isinstance(h, dict)
                                                and "companion-bridge" not in json.dumps(h)
                                            ]
                                            if filtered_hooks:
                                                grp["hooks"] = filtered_hooks
                                                new_groups.append(grp)
                                        elif "companion-bridge" not in json.dumps(grp):
                                            new_groups.append(grp)
                                    settings_data["hooks"][ev] = new_groups
                            settings_file.write_text(
                                json.dumps(settings_data, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                    except Exception:
                        pass

            elif agent_id == "pi-desktop":
                reg_file = Path.home() / ".pi-desktop" / "plugins" / "registry.json"
                if reg_file.is_file():
                    try:
                        with open(reg_file, encoding="utf-8") as f:
                            reg_data = json.load(f)
                        if isinstance(reg_data, list):
                            reg_data = [
                                p
                                for p in reg_data
                                if isinstance(p, dict) and p.get("id") != "pi.companion-bridge"
                            ]
                            reg_file.write_text(
                                json.dumps(reg_data, indent=2, ensure_ascii=False), encoding="utf-8"
                            )
                    except Exception:
                        pass

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

        if agent_id == "codex":
            return home_dir / ".codex" / "companion-bridge"

        if agent_id == "claude-code":
            return home_dir / ".claude" / "companion-bridge"

        if agent_id == "pi-desktop":
            return Path.home() / ".pi-desktop" / "plugins" / "installed" / "pi.companion-bridge"

        return None
