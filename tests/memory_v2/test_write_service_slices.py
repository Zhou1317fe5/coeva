"""Test Suite for Raw Evidence Slice Write Pipeline (Stage 2).

Formal verification of:
- W-S01: Slice Commit Before ACK
- W-S03: Slice Content Fidelity
- W-S04: Unresolved Scope Normalization (Unknown project -> unresolved, NOT global)
- W-S12: No Derived Memory Side Effects
"""

from __future__ import annotations

from pathlib import Path

from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import RawEvidenceWriteService, WriteSliceCommand


def test_w_s01_slice_commit_before_ack(tmp_path: Path) -> None:
    """W-S01: write_slice returns success only after SQLite commit is durable."""
    db_file = tmp_path / "slice_commit.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        res = writer.write_slice(
            content="明天下午三点讨论架构设计",
            source="manual_feed",
            scope="global",
        )
        assert res.status == "committed"
        assert res.was_persisted is True
        assert res.entity.content == "明天下午三点讨论架构设计"
        assert res.entity.project_id == "global"

        # Verify durable read directly from a new connection on disk
        new_store = ChronicleStoreV2(db_file)
        persisted = new_store.get_raw_slice(res.entity.slice_id)
        assert persisted is not None
        assert persisted.content == "明天下午三点讨论架构设计"
        new_store.close()
    finally:
        store.close()


def test_w_s03_slice_content_fidelity(tmp_path: Path) -> None:
    """W-S03: content fidelity preserved without LLM modification, trimming, or truncation."""
    db_file = tmp_path / "content_fidelity.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        raw_text = (
            "【原始笔记】\n"
            "• 测试多行换行与特殊符号: !@#$%^&*()_+\n"
            "• 中文、Emoji: 🚀 🌟 💡\n"
            "• 包含未转义的代码块:\n"
            "```python\n"
            "print('Hello World')\n"
            "```"
        )
        res = writer.write_slice(content=raw_text, source="bubble_reply")
        assert res.status == "committed"

        # Byte-for-byte exact equality
        persisted = store.get_raw_slice(res.entity.slice_id)
        assert persisted is not None
        assert persisted.content == raw_text
    finally:
        store.close()


def test_w_s04_unresolved_scope_never_promotes_to_global(tmp_path: Path) -> None:
    """W-S04: unknown/empty project remains 'unresolved' and NEVER promotes to 'global'."""
    db_file = tmp_path / "scope_isolation.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        # Case A: Scope unspecified / default
        res_a = writer.write_slice(content="无明确归属的杂记")
        assert res_a.entity.scope == "unresolved"
        assert res_a.entity.project_id is None

        # Case B: Scope specified as 'project' but project_id is empty/whitespace
        cmd_b = WriteSliceCommand(
            content="项目记录但项目名称为空",
            scope="project",
            project_id="   ",
        )
        res_b = writer.write_slice(cmd_b)
        # Fails safe to unresolved, NOT global
        assert res_b.entity.scope == "unresolved"
        assert res_b.entity.project_id is None

        # Case C: Valid project specification
        cmd_c = WriteSliceCommand(
            content="归属于具体工程的任务",
            scope="project",
            project_id="coeva-project",
        )
        res_c = writer.write_slice(cmd_c)
        assert res_c.entity.scope == "project"
        assert res_c.entity.project_id == "coeva-project"

        # Case D: Explicit global scope
        cmd_d = WriteSliceCommand(
            content="全局通用常识偏好",
            scope="global",
        )
        res_d = writer.write_slice(cmd_d)
        assert res_d.entity.scope == "global"
        assert res_d.entity.project_id == "global"
    finally:
        store.close()


def test_w_s12_no_derived_memory_side_effects(tmp_path: Path) -> None:
    """W-S12: writing raw slice strictly writes raw_slices; derived tables remain 100% empty."""
    db_file = tmp_path / "no_side_effects.db"
    store = ChronicleStoreV2(db_file)
    writer = RawEvidenceWriteService(store)
    try:
        # Write slice
        writer.write_slice(
            content="我喜欢在晚饭后散步半小时",
            source="manual_feed",
            scope="global",
        )

        # Verify derived tables are completely untouched (0 rows)
        c = store.connection
        assert c.execute("SELECT COUNT(*) FROM semantic_memories;").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM observations;").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM hypotheses;").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM confirmed_insights;").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM episodes;").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM chapter_metadata;").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM evidence_reinforcements;").fetchone()[0] == 0
    finally:
        store.close()
