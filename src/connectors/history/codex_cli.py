"""Parser for Codex CLI historical session logs (WSL and Windows)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.history.base import BaseSessionParser, HarvestedSession, normalize_timestamp

_ERROR_PATTERN = re.compile(
    r"(exit\s*code\s*[:=]?\s*[1-9]\d*|timed?\s*out|command not found|failed\s*with|traceback)",
    re.IGNORECASE,
)


class CodexCliParser(BaseSessionParser):
    """Parses Codex CLI session logs into normalized HarvestedSession objects."""

    DEFAULT_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

    def __init__(
        self,
        search_paths: list[Path] | None = None,
        *,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> None:
        self.max_file_size_bytes = max_file_size_bytes
        if search_paths is not None:
            self.search_paths = search_paths
        else:
            candidates: list[Path] = [
                # WSL Ubuntu default path via Windows UNC
                Path(r"\\wsl$\Ubuntu-24.04\home\zhou\.codex\sessions"),
                # Windows native codex sessions
                Path.home() / ".codex" / "sessions",
            ]
            self.search_paths = [p for p in candidates if p.is_dir()]

    @property
    def source_id(self) -> str:
        return "codex"

    def discover_targets(self) -> list[Path]:
        targets: list[Path] = []
        for base in self.search_paths:
            if not base.is_dir():
                continue
            for p in base.rglob("*.jsonl"):
                try:
                    if p.stat().st_size <= self.max_file_size_bytes:
                        targets.append(p)
                except OSError:
                    continue
        # Sort newest sessions first
        targets.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return targets

    def parse_session(self, target: Path | str) -> HarvestedSession | None:
        path = Path(target)
        if not path.is_file():
            return None

        session_id = path.stem
        started_at: str | None = None
        ended_at: str | None = None
        events: list[AgentEvent] = []
        call_id_to_tool: dict[str, str] = {}

        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    if (
                        "session_meta" not in line_str
                        and "response_item" not in line_str
                        and "task_complete" not in line_str
                    ):
                        continue
                    try:
                        record: dict[str, Any] = json.loads(line_str)
                    except json.JSONDecodeError:
                        continue

                    ts = normalize_timestamp(str(record.get("timestamp", "")))
                    if not started_at:
                        started_at = ts
                    ended_at = ts

                    rec_type = record.get("type")
                    payload = record.get("payload")
                    if not isinstance(payload, dict):
                        continue

                    # 1. Session start
                    if rec_type == "session_meta":
                        sid = str(payload.get("session_id") or payload.get("id") or session_id)
                        session_id = sid
                        events.append(
                            AgentEvent(
                                agent_id=self.source_id,
                                event_type=AgentEventType.SESSION_START,
                                session_id=session_id,
                                timestamp=ts,
                            )
                        )

                    # 2. Response items (messages, tool calls, tool outputs)
                    elif rec_type == "response_item":
                        pl_type = payload.get("type")

                        if pl_type == "message":
                            role = payload.get("role")
                            if role == "user":
                                # Privacy: Discard prompt content
                                events.append(
                                    AgentEvent(
                                        agent_id=self.source_id,
                                        event_type=AgentEventType.USER_PROMPT,
                                        session_id=session_id,
                                        timestamp=ts,
                                    )
                                )

                        elif pl_type in ("custom_tool_call", "function_call"):
                            tool_name = str(payload.get("name") or "tool")
                            call_id = str(payload.get("call_id") or payload.get("id") or "")
                            if call_id:
                                call_id_to_tool[call_id] = tool_name

                            events.append(
                                AgentEvent(
                                    agent_id=self.source_id,
                                    event_type=AgentEventType.PRE_TOOL_USE,
                                    session_id=session_id,
                                    timestamp=ts,
                                    tool_name=tool_name,
                                )
                            )

                        elif pl_type in ("custom_tool_call_output", "function_call_output"):
                            call_id = str(payload.get("call_id") or payload.get("id") or "")
                            tool_name = call_id_to_tool.get(call_id, "tool")
                            raw_out = str(payload.get("output", ""))

                            # Check for tool errors
                            is_err = bool(_ERROR_PATTERN.search(raw_out))
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

                    elif rec_type == "event_msg":
                        pl_type = payload.get("type")
                        if pl_type in ("task_complete", "task_completed"):
                            events.append(
                                AgentEvent(
                                    agent_id=self.source_id,
                                    event_type=AgentEventType.TASK_COMPLETE,
                                    session_id=session_id,
                                    timestamp=ts,
                                )
                            )

        except (OSError, UnicodeDecodeError):
            return None

        if not events:
            return None

        # Ensure session_end event
        final_ts = ended_at or events[-1].timestamp
        events.append(
            AgentEvent(
                agent_id=self.source_id,
                event_type=AgentEventType.SESSION_END,
                session_id=session_id,
                timestamp=final_ts,
            )
        )

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
