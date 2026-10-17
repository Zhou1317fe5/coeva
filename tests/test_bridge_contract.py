"""Guards on the PI-Desktop bridge source (plugins/pi-companion-bridge).

The bridge is JavaScript and is not imported by the test suite, so its contract
is checked by reading the source. These assertions exist because the previous
version silently collapsed every PI-Desktop session into one episode and
reported every finished turn as a completed task -- both invisible from Python.
"""

from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("plugins") / "pi-companion-bridge" / "extensions" / "bridge.mjs"


def _source() -> str:
    assert BRIDGE.is_file(), f"bridge source missing at {BRIDGE}"
    return BRIDGE.read_text(encoding="utf-8")


def test_bridge_no_longer_hardcodes_the_session_id() -> None:
    """A fixed session_id made cross-session episodes impossible."""
    source = _source()
    literal = re.findall(r'session_id:\s*"([^"]*)"', source)
    assert literal == [], f"session_id is still hardcoded: {literal}"
    assert "session_id: sessionId" in source
    assert "randomUUID" in source, "session ids must be generated per session"


def test_bridge_generates_a_new_session_id_on_each_session_start() -> None:
    """Each session_start must begin a new episode boundary."""
    source = _source()
    start_block = re.search(r'pi\.on\("session_start".*?\}\);', source, re.S)
    assert start_block is not None, "no session_start handler found"
    assert "sessionId = newSessionId()" in start_block.group(0), (
        "session_start must mint a fresh id"
    )


def test_bridge_does_not_report_turn_end_as_task_complete() -> None:
    """A finished exchange is not a finished task."""
    source = _source()
    turn_block = re.search(r'pi\.on\("turn_end".*?\}\);', source, re.S)
    assert turn_block is not None, "no turn_end handler found"
    assert '"turn_end"' in turn_block.group(0)
    assert "task_complete" not in turn_block.group(0), (
        "turn_end must not masquerade as task_complete"
    )


def test_bridge_reports_successful_tool_calls() -> None:
    """Successful tool results used to emit nothing at all."""
    source = _source()
    assert '"post_tool_use"' in source, "successful tool results must be reported"
    result_block = re.search(r'pi\.on\("tool_result".*?\n  \}\);', source, re.S)
    assert result_block is not None, "no tool_result handler found"
    block = result_block.group(0)
    assert "isError" in block and "tool_failure" in block and "post_tool_use" in block


def test_bridge_still_fails_silently_when_the_companion_is_down() -> None:
    """PI-Desktop must never be blocked or slowed by a missing companion."""
    source = _source()
    assert 'req.on("error"' in source
    assert "timeout" in source


def test_every_event_type_the_bridge_sends_is_a_known_contract_type() -> None:
    """Guard the wire contract: the bridge must not invent event types."""
    from src.connectors.contracts import AgentEventType

    known = {member.value for member in AgentEventType}
    sent = set(re.findall(r'event_type:\s*"([^"]+)"', _source()))
    assert sent, "no event_type literals found; did the bridge change shape?"
    unknown = sent - known
    assert unknown == set(), f"bridge sends unknown event types: {sorted(unknown)}"
