"""Parser for Hermes SQLite historical session logs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.history.base import BaseSessionParser, HarvestedSession, normalize_timestamp


class HermesDbParser(BaseSessionParser):
    """Parses Hermes state.db into normalized HarvestedSession objects."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is not None:
            self.db_path = db_path
        else:
            default_path = Path(r"\\wsl$\Ubuntu-24.04\home\zhou\.hermes\state.db")
            self.db_path = default_path

    @property
    def source_id(self) -> str:
        return "hermes"

    def discover_targets(self) -> list[Path]:
        if self.db_path.is_file():
            return [self.db_path]
        return []

    def _open_connection(self, path: Path) -> sqlite3.Connection | None:
        """Open SQLite connection with read-only & immutable mode to bypass network locks."""
        # Convert to URI
        clean_path = str(path).replace("\\", "/")
        if clean_path.startswith("//"):
            uri = f"file://{clean_path}?mode=ro&immutable=1"
        else:
            uri = f"file:///{clean_path}?mode=ro&immutable=1"
        try:
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error:
            try:
                # Fallback to direct connect
                conn = sqlite3.connect(str(path))
                conn.row_factory = sqlite3.Row
                return conn
            except sqlite3.Error:
                return None

    def parse_session(self, target: Path | str) -> HarvestedSession | None:
        """Parse all sessions from the database or a specific session."""
        # For HermesDbParser, parse_all_sessions returns all sessions in the DB.
        # parse_session parses the first session or session matching target if target is session_id.
        path = self.db_path
        conn = self._open_connection(path)
        if conn is None:
            return None

        try:
            sessions = self.parse_all_sessions(path)
            if not sessions:
                return None
            target_str = str(target)
            for s in sessions:
                if s.session_id == target_str or target_str == str(path):
                    return s
            return sessions[0]
        finally:
            conn.close()

    def parse_all_sessions(self, db_file: Path | None = None) -> list[HarvestedSession]:
        """Extract all sessions and their normalized events from Hermes database."""
        path = db_file or self.db_path
        conn = self._open_connection(path)
        if conn is None:
            return []

        harvested: list[HarvestedSession] = []
        try:
            # Query all sessions
            session_rows = conn.execute(
                "SELECT id, started_at, ended_at FROM sessions ORDER BY started_at ASC"
            ).fetchall()

            for srow in session_rows:
                sid = str(srow["id"])
                started_at_raw = srow["started_at"]
                ended_at_raw = srow["ended_at"]

                # Fetch all messages for this session
                msg_rows = conn.execute(
                    "SELECT role, content, tool_name, tool_calls, timestamp "
                    "FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
                    (sid,),
                ).fetchall()

                if not msg_rows:
                    continue

                events: list[AgentEvent] = []
                s_start_ts = (
                    normalize_timestamp(started_at_raw)
                    if started_at_raw
                    else normalize_timestamp(msg_rows[0]["timestamp"])
                )
                events.append(
                    AgentEvent(
                        agent_id=self.source_id,
                        event_type=AgentEventType.SESSION_START,
                        session_id=sid,
                        timestamp=s_start_ts,
                    )
                )

                for m in msg_rows:
                    role = m["role"]
                    ts = normalize_timestamp(m["timestamp"])
                    tool_name = str(m["tool_name"] or "")

                    if role == "user":
                        # Privacy: Prompt text is completely ignored
                        events.append(
                            AgentEvent(
                                agent_id=self.source_id,
                                event_type=AgentEventType.USER_PROMPT,
                                session_id=sid,
                                timestamp=ts,
                            )
                        )

                    elif role == "assistant":
                        calls_raw = m["tool_calls"]
                        if calls_raw:
                            try:
                                calls = json.loads(calls_raw)
                                if isinstance(calls, list):
                                    for c in calls:
                                        tname = str(
                                            c.get("function", {}).get("name")
                                            or c.get("name")
                                            or "tool"
                                        )
                                        events.append(
                                            AgentEvent(
                                                agent_id=self.source_id,
                                                event_type=AgentEventType.PRE_TOOL_USE,
                                                session_id=sid,
                                                timestamp=ts,
                                                tool_name=tname,
                                            )
                                        )
                            except (json.JSONDecodeError, TypeError):
                                pass

                    elif role == "tool":
                        content_raw = str(m["content"] or "")
                        is_err = False
                        try:
                            cdata: dict[str, Any] = json.loads(content_raw)
                            if isinstance(cdata, dict):
                                ec = cdata.get("exit_code")
                                err = cdata.get("error")
                                if (ec is not None and ec != 0) or err:
                                    is_err = True
                        except Exception:
                            # Heuristic check
                            if "error" in content_raw.lower() or "failed" in content_raw.lower():
                                is_err = True

                        if is_err:
                            events.append(
                                AgentEvent(
                                    agent_id=self.source_id,
                                    event_type=AgentEventType.TOOL_FAILURE,
                                    session_id=sid,
                                    timestamp=ts,
                                    tool_name=tool_name or "tool",
                                    error_message=f"{tool_name or 'tool'} error",
                                )
                            )
                        else:
                            events.append(
                                AgentEvent(
                                    agent_id=self.source_id,
                                    event_type=AgentEventType.POST_TOOL_USE,
                                    session_id=sid,
                                    timestamp=ts,
                                    tool_name=tool_name or "tool",
                                )
                            )

                s_end_ts = (
                    normalize_timestamp(ended_at_raw)
                    if ended_at_raw
                    else normalize_timestamp(msg_rows[-1]["timestamp"])
                )
                events.append(
                    AgentEvent(
                        agent_id=self.source_id,
                        event_type=AgentEventType.SESSION_END,
                        session_id=sid,
                        timestamp=s_end_ts,
                    )
                )

                events.sort(key=lambda e: e.timestamp)
                harvested.append(
                    HarvestedSession(
                        session_id=sid,
                        agent_id=self.source_id,
                        started_at=events[0].timestamp,
                        ended_at=events[-1].timestamp,
                        events=tuple(events),
                    )
                )

        finally:
            conn.close()

        return harvested
