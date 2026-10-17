"""Parser for Pi historical session logs (PI-Desktop and Pi CLI across Windows/WSL)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.history.base import BaseSessionParser, HarvestedSession, normalize_timestamp


class PiDesktopParser(BaseSessionParser):
    """Parses PI-Desktop and Pi CLI session logs into normalized HarvestedSession objects."""

    def __init__(
        self,
        search_paths: list[Path] | None = None,
        sessions_dir: Path | None = None,
    ) -> None:
        if sessions_dir is not None:
            self.search_paths = [sessions_dir]
        elif search_paths is not None:
            self.search_paths = search_paths
        else:
            candidates: list[Path] = [
                # Windows PI-Desktop
                Path.home() / ".pi-desktop" / "sessions",
                # WSL Pi CLI
                Path(r"\\wsl$\Ubuntu-24.04\home\zhou\.pi\agent\sessions"),
                # Linux/Windows local Pi CLI
                Path.home() / ".pi" / "agent" / "sessions",
            ]
            self.search_paths = [p for p in candidates if p.is_dir()]

    @property
    def source_id(self) -> str:
        return "pi"

    def discover_targets(self) -> list[Path]:
        targets: list[Path] = []
        for base in self.search_paths:
            if not base.is_dir():
                continue
            for p in base.rglob("*.jsonl"):
                # Exclude UI layout and revisions caches
                if p.name.endswith(".layout") or p.name.endswith(".revisions.jsonl"):
                    continue
                targets.append(p)
        targets.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return targets

    def parse_session(self, target: Path | str) -> HarvestedSession | None:
        path = Path(target)
        if not path.is_file():
            return None

        session_id = path.stem
        started_at: str | None = None
        events: list[AgentEvent] = []

        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    if '"session"' not in line_str and '"message"' not in line_str:
                        continue
                    try:
                        record: dict[str, Any] = json.loads(line_str)
                    except json.JSONDecodeError:
                        continue

                    rec_type = record.get("type")
                    if rec_type == "session":
                        sid = str(record.get("sessionId") or record.get("id") or session_id)
                        session_id = sid
                        raw_ts = str(record.get("createdAt") or record.get("timestamp") or "")
                        ts = normalize_timestamp(raw_ts)
                        if not started_at:
                            started_at = ts
                        events.append(
                            AgentEvent(
                                agent_id=self.source_id,
                                event_type=AgentEventType.SESSION_START,
                                session_id=session_id,
                                timestamp=ts,
                            )
                        )

                    elif rec_type == "message":
                        # Two formats:
                        # 1. Pi CLI format: record has "message": {"role": "...", "content": [...]}
                        # 2. PI-Desktop format: record has "role": "...", "blocks": [...]
                        nested_msg = record.get("message")
                        if isinstance(nested_msg, dict):
                            self._parse_pi_cli_message(record, nested_msg, session_id, events)
                        else:
                            self._parse_pi_desktop_message(record, session_id, events)

        except (OSError, UnicodeDecodeError):
            return None

        if not events:
            return None

        # Add session_end event if not explicitly present
        final_ts = events[-1].timestamp
        events.append(
            AgentEvent(
                agent_id=self.source_id,
                event_type=AgentEventType.SESSION_END,
                session_id=session_id,
                timestamp=final_ts,
            )
        )

        # Enforce strict temporal ordering
        events.sort(key=lambda e: e.timestamp)
        first_ts = started_at or events[0].timestamp
        last_ts = events[-1].timestamp
        return HarvestedSession(
            session_id=session_id,
            agent_id=self.source_id,
            started_at=first_ts,
            ended_at=last_ts,
            events=tuple(events),
        )

    def _parse_pi_cli_message(
        self,
        record: dict[str, Any],
        msg: dict[str, Any],
        session_id: str,
        events: list[AgentEvent],
    ) -> None:
        """Parse Pi CLI message format (role in message dict, toolResult as distinct role)."""
        role = msg.get("role")
        raw_ts = str(record.get("timestamp") or msg.get("timestamp") or "")
        ts = normalize_timestamp(raw_ts)

        if role == "user":
            # Privacy: Never capture prompt text
            events.append(
                AgentEvent(
                    agent_id=self.source_id,
                    event_type=AgentEventType.USER_PROMPT,
                    session_id=session_id,
                    timestamp=ts,
                )
            )

        elif role == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") in ("toolCall", "tool_call"):
                        tool_name = str(item.get("name") or item.get("toolName") or "tool")
                        events.append(
                            AgentEvent(
                                agent_id=self.source_id,
                                event_type=AgentEventType.PRE_TOOL_USE,
                                session_id=session_id,
                                timestamp=ts,
                                tool_name=tool_name,
                            )
                        )

        elif role == "toolResult":
            tool_name = str(msg.get("toolName") or "tool")
            is_err = bool(msg.get("isError"))
            if is_err:
                events.append(
                    AgentEvent(
                        agent_id=self.source_id,
                        event_type=AgentEventType.TOOL_FAILURE,
                        session_id=session_id,
                        timestamp=ts,
                        tool_name=tool_name,
                        error_message=f"{tool_name} failed",
                    )
                )
            else:
                events.append(
                    AgentEvent(
                        agent_id=self.source_id,
                        event_type=AgentEventType.POST_TOOL_USE,
                        session_id=session_id,
                        timestamp=ts,
                        tool_name=tool_name,
                    )
                )

    def _parse_pi_desktop_message(
        self,
        record: dict[str, Any],
        session_id: str,
        events: list[AgentEvent],
    ) -> None:
        role = record.get("role")
        created_at = normalize_timestamp(str(record.get("createdAt", "")))

        if role == "user":
            # Privacy: Never capture prompt text in blocks
            events.append(
                AgentEvent(
                    agent_id=self.source_id,
                    event_type=AgentEventType.USER_PROMPT,
                    session_id=session_id,
                    timestamp=created_at,
                )
            )

        elif role == "assistant":
            blocks = record.get("blocks", [])
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                btype = b.get("type")
                if btype == "tool_call":
                    tool_name = str(b.get("name", "unknown_tool"))
                    call_ts = created_at
                    events.append(
                        AgentEvent(
                            agent_id=self.source_id,
                            event_type=AgentEventType.PRE_TOOL_USE,
                            session_id=session_id,
                            timestamp=call_ts,
                            tool_name=tool_name,
                        )
                    )

                    completed_at_raw = b.get("completedAt")
                    comp_ts = (
                        normalize_timestamp(str(completed_at_raw)) if completed_at_raw else call_ts
                    )

                    is_err = bool(b.get("isError") or b.get("status") == "error")
                    if is_err:
                        events.append(
                            AgentEvent(
                                agent_id=self.source_id,
                                event_type=AgentEventType.TOOL_FAILURE,
                                session_id=session_id,
                                timestamp=comp_ts,
                                tool_name=tool_name,
                                error_message=f"{tool_name} failed",
                            )
                        )
                    else:
                        events.append(
                            AgentEvent(
                                agent_id=self.source_id,
                                event_type=AgentEventType.POST_TOOL_USE,
                                session_id=session_id,
                                timestamp=comp_ts,
                                tool_name=tool_name,
                            )
                        )


# Alias for backward compatibility
PiSessionParser = PiDesktopParser
