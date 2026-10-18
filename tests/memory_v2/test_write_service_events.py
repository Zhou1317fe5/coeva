"""Test Suite for Raw Evidence Event Skeleton Write Pipeline & Privacy Boundary (Stage 2).

Formal verification of:
- W-S05: Event Privacy Boundary
  (Prompts, CoT, tool output bodies, stacktrace dumps stripped; only structured skeleton persisted)
"""

from __future__ import annotations

from pathlib import Path

from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import RawEvidenceWriteService, WriteEventCommand


def test_w_s05_event_privacy_boundary(tmp_path: Path) -> None:
    """W-S05: sensitive prompt body, CoT, and tool outputs are strictly stripped from DB."""
    db_file = tmp_path / "event_privacy.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        # Simulate incoming external event containing prohibited sensitive payloads
        sensitive_prompt = "这是包含人类私密聊天与 API Token: sk-abc123456789 的完整 Prompt"
        sensitive_cot = "Agent 思考链: 准备尝试读取私钥并分析用户的敏感意图..."
        sensitive_tool_output = {
            "stdout": "cat ~/.ssh/id_rsa: -----BEGIN OPENSSH PRIVATE KEY-----",
            "exit_code": 1,
            "raw_stacktrace": "Traceback (most recent call last):\n  File 'evil.py', line 12",
        }

        cmd = WriteEventCommand(
            agent_id="pi-desktop",
            session_id="session_privacy_01",
            event_type="tool_execution",
            tool_name="bash",
            error_category="PermissionDenied",
            retention_class="transient",
            event_id="evt_privacy_01",
        )

        # Pass extra sensitive kwargs to the writer
        res = writer.write_event(
            cmd,
            prompt=sensitive_prompt,
            chain_of_thought=sensitive_cot,
            tool_output=sensitive_tool_output,
            raw_body="ANY ARBITRARY SENSITIVE DUMP",
        )

        assert res.status == "committed"
        assert res.was_persisted is True
        assert res.entity.event_id == "evt_privacy_01"
        assert res.entity.tool_name == "bash"
        assert res.entity.error_category == "PermissionDenied"

        # Verify physical database inspection: prohibited strings must be absent
        row = store.connection.execute(
            "SELECT * FROM event_skeletons WHERE event_id = 'evt_privacy_01';"
        ).fetchone()
        assert row is not None

        # Verify only exact 9 columns exist in schema table
        cols_query = "PRAGMA table_info(event_skeletons);"
        col_names = [d[0] for d in store.connection.execute(cols_query).fetchall()]
        assert "prompt" not in col_names
        assert "chain_of_thought" not in col_names
        assert "tool_output" not in col_names
        assert "body" not in col_names

        # Verify raw database text does NOT contain sensitive substrings
        full_row_text = " ".join(str(val) for val in row)
        assert "sk-abc123456789" not in full_row_text
        assert "OPENSSH PRIVATE KEY" not in full_row_text
        assert "思考链" not in full_row_text
    finally:
        store.close()
