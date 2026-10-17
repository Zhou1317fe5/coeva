"""Multi-Agent settings store and multi-environment instance filtering rules."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.llm_client import LLMConfig
from src.feeder.hotkey import DEFAULT_FEEDER_HOTKEY, parse_hotkey

DEFAULT_AGENTS: dict[str, dict[str, Any]] = {
    "pi-desktop": {
        "name": "PI-Desktop",
        "enabled": True,
        "allow_bubble": True,
        "allow_action": True,
        "description": "PI-Desktop 图形工作区扩展",
        "default_instances": [
            {"instance_id": "windows", "label": "Windows 桌面工作区", "enabled": True},
        ],
    },
    "pi-cli": {
        "name": "Pi CLI",
        "enabled": True,
        "allow_bubble": True,
        "allow_action": True,
        "description": "Pi 命令行终端智能体 (CLI)",
        "default_instances": [
            {"instance_id": "windows", "label": "Windows 控制台", "enabled": True},
            {"instance_id": "wsl:Ubuntu-24.04", "label": "WSL (Ubuntu-24.04)", "enabled": True},
        ],
    },
    "hermes": {
        "name": "Hermes Agent",
        "enabled": True,
        "allow_bubble": True,
        "allow_action": True,
        "description": "Hermes CLI 终端智能体",
        "default_instances": [
            {"instance_id": "windows", "label": "Windows 本地", "enabled": True},
            {"instance_id": "wsl:Ubuntu-24.04", "label": "WSL (Ubuntu-24.04)", "enabled": True},
        ],
    },
    "codex": {
        "name": "Codex CLI",
        "enabled": True,
        "allow_bubble": True,
        "allow_action": True,
        "description": "Codex 命令行代码助手",
        "default_instances": [
            {"instance_id": "windows", "label": "Windows 本地", "enabled": True},
            {"instance_id": "wsl:Ubuntu-24.04", "label": "WSL (Ubuntu-24.04)", "enabled": True},
        ],
    },
    "claude-code": {
        "name": "Claude Code",
        "enabled": False,
        "allow_bubble": True,
        "allow_action": True,
        "description": "Anthropic Claude Code CLI",
        "default_instances": [
            {"instance_id": "windows", "label": "Windows 本地", "enabled": True},
            {"instance_id": "wsl:Ubuntu-24.04", "label": "WSL (Ubuntu-24.04)", "enabled": True},
        ],
    },
}


@dataclass
class AgentInstanceConfig:
    """Represents a specific runtime environment instance of an Agent (Windows vs WSL)."""

    instance_id: str
    label: str
    enabled: bool = True
    last_seen: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentInstanceConfig:
        return cls(
            instance_id=str(data.get("instance_id", "default")),
            label=str(data.get("label", "默认实例")),
            enabled=bool(data.get("enabled", True)),
            last_seen=data.get("last_seen"),
        )


@dataclass
class AgentConfig:
    agent_id: str
    name: str
    enabled: bool = True
    allow_bubble: bool = True
    allow_action: bool = True
    description: str = ""
    last_seen: str | None = None
    instances: dict[str, AgentInstanceConfig] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["instances"] = {iid: inst.to_dict() for iid, inst in self.instances.items()}
        return d

    @classmethod
    def from_dict(cls, agent_id: str, data: dict[str, Any]) -> AgentConfig:
        raw_instances = data.get("instances", {})
        instances_map: dict[str, AgentInstanceConfig] = {}
        if isinstance(raw_instances, dict):
            for iid, idata in raw_instances.items():
                if isinstance(idata, dict):
                    instances_map[iid] = AgentInstanceConfig.from_dict(idata)
        elif isinstance(raw_instances, list):
            for idata in raw_instances:
                if isinstance(idata, dict):
                    inst = AgentInstanceConfig.from_dict(idata)
                    instances_map[inst.instance_id] = inst

        return cls(
            agent_id=agent_id,
            name=str(data.get("name", agent_id)),
            enabled=bool(data.get("enabled", True)),
            allow_bubble=bool(data.get("allow_bubble", True)),
            allow_action=bool(data.get("allow_action", True)),
            description=str(data.get("description", "")),
            last_seen=data.get("last_seen"),
            instances=instances_map,
        )


class AgentSettingsStore:
    """Manages persistent multi-agent preferences, instance environments and telemetry filters."""

    def __init__(self, file_path: Path | str = Path("data") / "agent_settings.json") -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._configs: dict[str, AgentConfig] = {}
        self.load()

    def load(self) -> None:
        """Load settings from JSON, initializing missing defaults and instance rows."""
        raw_data: dict[str, Any] = {}
        if self.file_path.is_file():
            try:
                with open(self.file_path, encoding="utf-8") as f:
                    raw_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                raw_data = {}

        self._selected_pet = str(raw_data.get("selected_pet", "vasu"))
        stored_hotkey = parse_hotkey(str(raw_data.get("feeder_hotkey", "")))
        self._feeder_hotkey = (
            stored_hotkey.spec if stored_hotkey is not None else DEFAULT_FEEDER_HOTKEY
        )
        llm_data = raw_data.get("llm")
        if isinstance(llm_data, dict) and llm_data.get("api_key"):
            self._llm_config = LLMConfig.from_dict(llm_data)
        else:
            self._llm_config = LLMConfig.load()
        agents_data = raw_data.get("agents", {})
        self._configs = {}

        # Merge defaults
        for aid, def_info in DEFAULT_AGENTS.items():
            if aid in agents_data:
                cfg = AgentConfig.from_dict(aid, agents_data[aid])
                # Ensure default instances exist
                for d_inst in def_info.get("default_instances", []):
                    iid = d_inst["instance_id"]
                    if iid not in cfg.instances:
                        cfg.instances[iid] = AgentInstanceConfig(
                            instance_id=iid,
                            label=d_inst["label"],
                            enabled=d_inst["enabled"],
                        )
                self._configs[aid] = cfg
            else:
                inst_map = {
                    d_inst["instance_id"]: AgentInstanceConfig(
                        instance_id=d_inst["instance_id"],
                        label=d_inst["label"],
                        enabled=d_inst["enabled"],
                    )
                    for d_inst in def_info.get("default_instances", [])
                }
                self._configs[aid] = AgentConfig(
                    agent_id=aid,
                    name=def_info["name"],
                    enabled=def_info["enabled"],
                    allow_bubble=def_info["allow_bubble"],
                    allow_action=def_info["allow_action"],
                    description=def_info["description"],
                    instances=inst_map,
                )

        # Include custom added agents
        for aid, data in agents_data.items():
            if aid not in self._configs and isinstance(data, dict):
                self._configs[aid] = AgentConfig.from_dict(aid, data)

        self.save()

    def save(self) -> None:
        """Save settings to disk."""
        payload = {
            "version": 2,
            "selected_pet": self._selected_pet,
            "feeder_hotkey": self._feeder_hotkey,
            "llm": self._llm_config.to_dict(),
            "agents": {aid: cfg.to_dict() for aid, cfg in self._configs.items()},
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def get_all(self) -> list[AgentConfig]:
        """Return all agent configs."""
        return list(self._configs.values())

    def get(self, agent_id: str) -> AgentConfig | None:
        """Get config for one agent."""
        return self._configs.get(agent_id)

    @property
    def selected_pet(self) -> str:
        """Return the ID of the selected desktop pet (e.g. 'calico')."""
        return self._selected_pet

    def set_selected_pet(self, pet_id: str) -> None:
        """Update and persist the selected desktop pet."""
        self._selected_pet = pet_id.strip() or "vasu"
        self.save()

    @property
    def feeder_hotkey(self) -> str:
        """Return the canonical global hotkey that summons the slice feeder."""
        return self._feeder_hotkey

    def set_feeder_hotkey(self, spec: str) -> None:
        """Persist a new feeder hotkey, rejecting anything unusable.

        An illegal combination raises rather than being written, so the value on
        disk is always one the listener can actually register.
        """
        parsed = parse_hotkey(spec)
        if parsed is None:
            raise ValueError(f"非法快捷键组合: {spec!r}")
        self._feeder_hotkey = parsed.spec
        self.save()

    @property
    def llm_config(self) -> LLMConfig:
        """Return current LLM configuration."""
        return self._llm_config

    def set_llm_config(self, config: LLMConfig) -> None:
        """Update and persist LLM configuration to both settings stores."""
        self._llm_config = config
        config.save()
        self.save()

    def is_agent_enabled(self, agent_id: str, instance_id: str | None = None) -> bool:
        """Check if an agent (and optionally its specific environment instance) is enabled."""
        cfg = self._configs.get(agent_id)
        if cfg is None:
            return True
        if not cfg.enabled:
            return False
        if instance_id and instance_id in cfg.instances:
            return cfg.instances[instance_id].enabled
        return True

    def can_show_bubble(self, agent_id: str) -> bool:
        """Check if agent is permitted to show speech bubbles."""
        cfg = self._configs.get(agent_id)
        return cfg.allow_bubble if cfg else True

    def can_perform_action(self, agent_id: str) -> bool:
        """Check if agent is permitted to drive pet animations."""
        cfg = self._configs.get(agent_id)
        return cfg.allow_action if cfg else True

    def update_agent(
        self,
        agent_id: str,
        *,
        enabled: bool | None = None,
        allow_bubble: bool | None = None,
        allow_action: bool | None = None,
    ) -> None:
        """Update global properties of an agent."""
        if agent_id not in self._configs:
            self._configs[agent_id] = AgentConfig(agent_id=agent_id, name=agent_id)

        cfg = self._configs[agent_id]
        if enabled is not None:
            cfg.enabled = enabled
        if allow_bubble is not None:
            cfg.allow_bubble = allow_bubble
        if allow_action is not None:
            cfg.allow_action = allow_action
        self.save()

    def update_instance(
        self,
        agent_id: str,
        instance_id: str,
        *,
        enabled: bool | None = None,
    ) -> None:
        """Update a specific environment instance of an agent (e.g. WSL vs Windows)."""
        cfg = self._configs.get(agent_id)
        if not cfg:
            return
        if instance_id not in cfg.instances:
            cfg.instances[instance_id] = AgentInstanceConfig(
                instance_id=instance_id,
                label=instance_id,
            )
        inst = cfg.instances[instance_id]
        if enabled is not None:
            inst.enabled = enabled
        self.save()

    def record_heartbeat(
        self,
        agent_id: str,
        platform: str | None = None,
        distro: str | None = None,
    ) -> None:
        """Record latest event timestamp for this agent and its specific environment instance."""
        now_str = datetime.now(UTC).isoformat()
        if agent_id not in self._configs:
            self._configs[agent_id] = AgentConfig(
                agent_id=agent_id,
                name=agent_id,
                enabled=True,
                last_seen=now_str,
            )
        cfg = self._configs[agent_id]
        cfg.last_seen = now_str

        # Resolve instance_id (e.g., 'windows' or 'wsl:Ubuntu-24.04')
        instance_id = "windows"
        if platform == "wsl":
            instance_id = f"wsl:{distro}" if distro else "wsl"

        if instance_id in cfg.instances:
            cfg.instances[instance_id].last_seen = now_str
        else:
            # Auto-register newly discovered instance
            label = "Windows 本地" if instance_id == "windows" else f"WSL ({distro or 'Linux'})"
            cfg.instances[instance_id] = AgentInstanceConfig(
                instance_id=instance_id,
                label=label,
                enabled=True,
                last_seen=now_str,
            )
        self.save()
