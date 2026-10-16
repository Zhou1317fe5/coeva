"""Parser for PI-Desktop JSONL historical session logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.history.base import BaseSessionParser, HarvestedSession, normalize_timestamp


class PiDesktopParser(BaseSessionParser):
    """Parses ~/.pi-desktop/sessions/*.jsonl into normalized HarvestedSession objects."""

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self.sessions_dir = sessions_dir or (Path.home() / ".pi-desktop" / "sessions")

    @property
    def source_id(self) -> str:
        return "pi-desktop"

    def discover_targets(self) -> list[Path]:
        if not self.sessions_dir.is_dir():
            return []
        targets: list[Path] = []
        for p in self.sessions_dir.glob("*.jsonl"):
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
        ended_at: str | None = None
        events: list[AgentEvent] = []

        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        record: dict[str, Any] = json.loads(line_str)
                    except json.JSONDecodeError:
                        continue

                    rec_type = record.get("type")
                    if rec_type == "session":
                        sid = str(record.get("sessionId") or session_id)
                        session_id = sid
                        ts = normalize_timestamp(str(record.get("createdAt", "")))
                        if not started_at:
                            started_at = ts
                        ended_at = ts
                        events.append(
                            AgentEvent(
                                agent_id=self.source_id,
                                event_type=AgentEventType.SESSION_START,
                                session_id=session_id,
                                timestamp=ts,
                            )
                        )

                    elif rec_type == "message":
                        role = record.get("role")
                        created_at = normalize_timestamp(str(record.get("createdAt", "")))
                        if not started_at:
                            started_at = created_at
                        ended_at = created_at

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
                                        normalize_timestamp(str(completed_at_raw))
                                        if completed_at_raw
                                        else call_ts
                                    )
                                    ended_at = comp_ts

                                    is_err = bool(
                                        b.get("isError") or b.get("status") == "error"
                                    )
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

        except (OSError, UnicodeDecodeError):
            return None

        if not events:
            return None

        # Add session_end event if not explicitly present
        final_ts = ended_at or (events[-1].timestamp if events else normalize_timestamp(""))
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
