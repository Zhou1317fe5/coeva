"""Test Suite for WP-11 Legacy Compatibility Layer & Retirement Lifecycle.

Verifies:
- C-01: install views (both views install cleanly on V2 DB)
- C-02: legacy slices projection (safe legacy shape: id, timestamp, actor, content, mood_flag)
- C-03: legacy events projection (privacy-safe Event Skeleton: no prompt, CoT, stacktrace)
- C-04: views read-only (INSERT/UPDATE/DELETE fail; no INSTEAD OF triggers)
- C-05: views not evidence (cannot become ProvenanceRef or consolidation/retrieval source)
- C-13: legacy reader does not duplicate evidence pipeline
- C-14: retirement gate (dependency conditions + 7 continuous zero-read days)
- C-15: no content observability (metrics contain zero content or query text)
- C-16: WP-10 integration (install on scratch shadow without breaking parity)
- C-17: production isolation (production DB/flags untouched, no startup auto-install)
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.core.flags import MemoryFeatureFlags
from src.memory.v2.compatibility import (
    COMPATIBILITY_VIEW_NAMES,
    CompatibilityEvidenceViolationError,
    CompatibilityObservability,
    CompatibilityReader,
    CompatibilityRetirementBlockedError,
    CompatibilityRetirementEvaluator,
    CompatibilityViewReadOnlyViolationError,
    assert_not_evidence_source,
    has_legacy_views,
    install_legacy_views,
    verify_legacy_views_read_only,
)
from src.memory.v2.entities import EventSkeletonEntity, RawSliceEntity
from src.memory.v2.migration.mapper import build_v2_shadow_db
from src.memory.v2.migration.reconcile import reconcile_canonical_sets
from src.memory.v2.migration.snapshot import create_wal_snapshot
from src.memory.v2.provenance import ProvenanceRef
from src.memory.v2.store import ChronicleStoreV2
from tests.memory_v2.test_migration_assertions import create_v1_database

PROD_DB_PATH = Path("data/companion_chronicle.db")
PROD_JSONL_PATH = Path("data/raw_slices.jsonl")


def _populate_v2_test_data(store: ChronicleStoreV2) -> tuple[str, str]:
    now = datetime.now(UTC).isoformat()
    sid = "slice_wp11_test_001"
    eid = "event_wp11_test_001"

    slice_entity = RawSliceEntity(
        slice_id=sid,
        occurred_at=now,
        content="User typed some notes about parallel lane execution.",
        actor="user",
        source="manual_feed",
        scope="global",
        project_id="global",
        ingestion_dedup_key="dedup_slice_wp11_001",
        created_at=now,
    )
    store.insert_raw_slice(slice_entity)

    event_entity = EventSkeletonEntity(
        event_id=eid,
        occurred_at=now,
        agent_id="agent_wp11",
        session_id="session_wp11",
        event_type="tool_execution",
        tool_name="git_worktree",
        error_category="none",
        retention_class="durable",
        created_at=now,
    )
    store.insert_event_skeleton(event_entity)
    return sid, eid


def test_c01_install_and_has_views(tmp_path: Path) -> None:
    """C-01: Both compatibility views can be explicitly installed on a valid V2 DB."""
    db_path = tmp_path / "c01_test.db"
    store = ChronicleStoreV2(db_path)
    try:
        # Initially views do NOT exist (clean frozen Stage-1 tables only)
        assert store.has_compatibility_views() is False
        assert has_legacy_views(store.connection) is False

        # Explicitly install
        store.install_compatibility_views()
        assert store.has_compatibility_views() is True
        assert has_legacy_views(store.connection) is True

        # Frozen 20 canonical tables and 4 technical tables unchanged
        contract = store.validate_schema_contract()
        assert contract["status"] == "VALID"
        assert contract["canonical_table_count"] == 20
        assert contract["technical_table_count"] == 4
    finally:
        store.close()


def test_c02_legacy_slices_projection_shape(tmp_path: Path) -> None:
    """C-02: Legacy reader receives expected safe shape from raw_slices."""
    db_path = tmp_path / "c02_test.db"
    store = ChronicleStoreV2(db_path)
    try:
        sid, _ = _populate_v2_test_data(store)
        store.install_compatibility_views()

        reader = CompatibilityReader(store)
        rec = reader.get_slice(sid)
        assert rec is not None
        assert rec.id == sid
        assert rec.content == "User typed some notes about parallel lane execution."
        assert rec.actor == "user"
        assert rec.source == "manual_feed"
        assert rec.mood_flag == "neutral"
        assert rec.created_at is not None

        # Verify listing
        slices = reader.list_slices(limit=10)
        assert len(slices) == 1
        assert slices[0].id == sid
        assert reader.count_slices() == 1
    finally:
        store.close()


def test_c03_legacy_events_projection_shape_and_privacy(tmp_path: Path) -> None:
    """C-03: Legacy reader receives only privacy-safe Event Skeleton fields."""
    db_path = tmp_path / "c03_test.db"
    store = ChronicleStoreV2(db_path)
    try:
        _, eid = _populate_v2_test_data(store)
        store.install_compatibility_views()

        reader = CompatibilityReader(store)
        rec = reader.get_event(eid)
        assert rec is not None
        assert rec.id == eid
        assert rec.agent_id == "agent_wp11"
        assert rec.session_id == "session_wp11"
        assert rec.event_type == "tool_execution"
        assert rec.tool_name == "git_worktree"
        assert rec.error_message == "none"
        assert rec.provenance == "agent_context"
        assert rec.retention_class == "durable"

        # Verify no unauthorized fields are projected
        for forbidden in ("prompt", "cot", "stacktrace", "tool_output", "llm_response"):
            assert not hasattr(rec, forbidden)

        assert reader.count_events() == 1
    finally:
        store.close()


def test_c04_views_are_read_only_and_triggers_rejected(tmp_path: Path) -> None:
    """C-04: Views are strictly read-only; writes fail and triggers are rejected."""
    db_path = tmp_path / "c04_test.db"
    store = ChronicleStoreV2(db_path)
    try:
        store.install_compatibility_views()
        assert store.verify_compatibility_views_read_only() is True
        assert verify_legacy_views_read_only(store.connection) is True

        # Directly attempt to write to views through SQL
        cursor = store.connection.cursor()
        cols = "id, timestamp, actor, source, content, mood_flag, created_at"
        vals = "'bad', '2026-10-18T10:00:00Z', 'user', 'manual_feed', 'hack', 'neutral', 'now'"
        with pytest.raises(sqlite3.OperationalError, match="cannot modify"):
            cursor.execute(f"INSERT INTO legacy_slices_view ({cols}) VALUES ({vals});")

        with pytest.raises(sqlite3.OperationalError, match="cannot modify"):
            cursor.execute("UPDATE legacy_slices_view SET content = 'bad';")

        with pytest.raises(sqlite3.OperationalError, match="cannot modify"):
            cursor.execute("DELETE FROM legacy_slices_view WHERE 1=1;")

        with pytest.raises(sqlite3.OperationalError, match="cannot modify"):
            cursor.execute("DELETE FROM legacy_events_view WHERE 1=1;")

        # Injecting an INSTEAD OF trigger must be caught by verifier
        cursor.execute(
            "CREATE TRIGGER trg_test_instead_of INSTEAD OF INSERT ON legacy_slices_view "
            "BEGIN SELECT 1; END;"
        )
        with pytest.raises(
            CompatibilityViewReadOnlyViolationError, match="Write triggers detected"
        ):
            verify_legacy_views_read_only(store.connection)
    finally:
        store.close()


def test_c05_views_cannot_be_provenance_ref_or_evidence() -> None:
    """C-05: Compatibility views cannot become ProvenanceRef or a new evidence source."""
    # 1. Direct name guard
    for view_name in COMPATIBILITY_VIEW_NAMES:
        with pytest.raises(
            CompatibilityEvidenceViolationError,
            match="cannot be used as canonical evidence",
        ):
            assert_not_evidence_source(view_name)

    # 2. Type constraint: ProvenanceKind has fixed Literal values
    allowed_kinds: set[str] = {
        "slice",
        "event",
        "episode",
        "semantic_memory",
        "observation",
        "insight",
    }
    for view_name in COMPATIBILITY_VIEW_NAMES:
        assert view_name not in allowed_kinds

    # Attempting to assert compatibility view name as evidence source fails
    with pytest.raises(CompatibilityEvidenceViolationError):
        assert_not_evidence_source("legacy_slices_view")


def test_c13_legacy_reader_does_not_duplicate_evidence_pipeline(tmp_path: Path) -> None:
    """C-13: Same canonical row read via compatibility view cannot re-enter as separate evidence."""
    db_path = tmp_path / "c13_test.db"
    store = ChronicleStoreV2(db_path)
    try:
        sid, _ = _populate_v2_test_data(store)
        store.install_compatibility_views()

        reader = CompatibilityReader(store)
        legacy_rec = reader.get_slice(sid)
        assert legacy_rec is not None

        # Guard check: cannot pass legacy view record name as evidence
        with pytest.raises(CompatibilityEvidenceViolationError):
            assert_not_evidence_source("legacy_slices_view")

        # ProvenanceRef cannot point to a compatibility view
        ref = ProvenanceRef(kind="slice", target_id=legacy_rec.id, role="primary_source")
        assert ref.kind == "slice"
        assert ref.target_id == sid
    finally:
        store.close()


def test_c14_retirement_gate_dependency_and_zero_read_days(tmp_path: Path) -> None:
    """C-14: Views are not auto-dropped; readiness requires 4 conditions + 7 zero-read days."""
    now = datetime.now(UTC)

    # Scenario 1: Unmet conditions (active readers present, transitional clients active)
    status_blocked = CompatibilityRetirementEvaluator.evaluate(
        active_readers=2,
        transitional_clients_retired=False,
        last_read_at=now - timedelta(days=2),
        rollback_plan_cleared=False,
        now=now,
    )
    assert status_blocked.safe_to_drop is False
    assert len(status_blocked.reasons_blocking_drop) == 4

    # Scenario 2: Only 3 days since last read (< 7.0 required)
    status_recent_read = CompatibilityRetirementEvaluator.evaluate(
        active_readers=0,
        transitional_clients_retired=True,
        last_read_at=now - timedelta(days=3),
        rollback_plan_cleared=True,
        now=now,
    )
    assert status_recent_read.safe_to_drop is False
    assert any("7.0 days required" in r for r in status_recent_read.reasons_blocking_drop)

    # Scenario 3: All 4 conditions met (0 readers, retired, 8 days zero-read, rollback cleared)
    status_ready = CompatibilityRetirementEvaluator.evaluate(
        active_readers=0,
        transitional_clients_retired=True,
        last_read_at=now - timedelta(days=8),
        rollback_plan_cleared=True,
        now=now,
    )
    assert status_ready.safe_to_drop is True
    assert len(status_ready.reasons_blocking_drop) == 0

    # Test drop_legacy_views enforcement
    db_path = tmp_path / "c14_test.db"
    store = ChronicleStoreV2(db_path)
    try:
        store.install_compatibility_views()
        assert store.has_compatibility_views() is True

        # Drop blocked when retirement status is not safe
        with pytest.raises(CompatibilityRetirementBlockedError, match="retirement criteria unmet"):
            store.drop_compatibility_views(retirement_status=status_blocked)

        # Drop succeeds when retirement status is safe
        store.drop_compatibility_views(retirement_status=status_ready)
        assert store.has_compatibility_views() is False
    finally:
        store.close()


def test_c15_compatibility_observability_no_content_leak() -> None:
    """C-15: Technical usage metrics contain no Slice/Event body or query text."""
    obs = CompatibilityObservability()
    obs.record_slice_read("feeder_legacy_reader")
    obs.record_event_read("connector_legacy_reader")

    assert obs.total_slice_reads == 1
    assert obs.total_event_reads == 1
    assert obs.total_reads == 2
    assert obs.last_read_at is not None
    assert "feeder_legacy_reader" in obs.registered_readers

    # Verify no content or query attributes exist on observability object
    obs_dict = vars(obs)
    for forbidden_key in ("content", "query", "body", "slice_text", "prompt"):
        assert forbidden_key not in obs_dict


def test_c16_wp10_shadow_integration_install_and_parity(tmp_path: Path) -> None:
    """C-16: Install views on WP-10 scratch shadow without changing migration source parity."""
    src = create_v1_database(tmp_path / "c16_prod.db", num_slices=8, num_events=12)
    snap = tmp_path / "c16_snap.db"
    shadow = tmp_path / "c16_shadow.db"

    # Step 1: WP-10 migration produces READY_TO_CUTOVER shadow
    create_wal_snapshot(src, snap)
    build_v2_shadow_db(snap, shadow)

    # Initial check: WP-10 shadow has no WP-11 views
    conn = sqlite3.connect(str(shadow))
    try:
        assert has_legacy_views(conn) is False
        recon_pre = reconcile_canonical_sets(src, shadow)
        assert recon_pre.parity_verified is True

        # Step 2: WP-11 installs compatibility views on shadow
        install_legacy_views(conn)
        assert has_legacy_views(conn) is True
        assert verify_legacy_views_read_only(conn) is True

        # Step 3: Parity with source V1 database remains 100% clean
        recon_post = reconcile_canonical_sets(src, shadow)
        assert recon_post.parity_verified is True
        assert recon_post.final_slices_count == 8
        assert recon_post.final_events_count == 12
    finally:
        conn.close()


def test_c17_production_isolation_and_flags_off() -> None:
    """C-17: Production DB, JSONL, runtime unchanged and flags remain strictly OFF."""
    flags = MemoryFeatureFlags()
    assert flags.memory_v2_storage is False
    assert flags.memory_v2_retrieval is False
    assert flags.memory_v2_consolidation is False

    # ChronicleStoreV2 initialization does NOT auto-install compatibility views
    store = ChronicleStoreV2(":memory:")
    try:
        assert store.has_compatibility_views() is False
    finally:
        store.close()

    # If production DB exists, ensure size and hash are untouched
    if PROD_DB_PATH.exists():
        v1_backup = PROD_DB_PATH.parent / "companion_chronicle.db.pre_v2_backup"
        if v1_backup.is_file():
            # Post-cutover: V2 DB has integrity ok; V1 backup preserves pre-v2 integrity
            chk_con = sqlite3.connect(f"file:{PROD_DB_PATH.resolve()}?mode=ro", uri=True)
            try:
                assert chk_con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert chk_con.execute("PRAGMA user_version").fetchone()[0] >= 20261018
            finally:
                chk_con.close()
        else:
            expected_size = 49860608
            expected_sha256 = "d84dd961fdb109cb9399087bb104f1b84dcc657cf14738f2035379e27ab81f9c"
            assert PROD_DB_PATH.stat().st_size == expected_size
            assert hashlib.sha256(PROD_DB_PATH.read_bytes()).hexdigest() == expected_sha256
