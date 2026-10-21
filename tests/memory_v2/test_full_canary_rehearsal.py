"""Full Canary Migration & Safety Rehearsal Integration Tests (Lane M Gate).

Enforces:
- Hard Gate: real production-data COPY + destructive adversarial rehearsal
- M-S01 ~ M-S18 = 18/18 PASS
- Data Loss = 0
- Source-set parity verified (no watermark)
- CNY-01 ~ CNY-08 Semantic smoke passes
- Crash matrix: 10 failure points recover cleanly
- Rollback safety: blind restore strictly forbidden on new canonical writes
- Production isolation: production files remain untouched
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.memory.v2.migration.swap import RollbackForbiddenDataLossError, rollback_cutover
from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import RawEvidenceWriteService, WriteSliceCommand
from tests.memory_v2.test_migration_assertions import create_v1_database
from tools.canary_memory_v2 import (
    execute_cny01_retrieval,
    execute_cny02_sanctuary,
    execute_cny03_consolidation,
    execute_cny04_understanding,
    execute_cny05_chapter_privacy,
    execute_cny06_narrative_firewall,
    execute_cny07_single_master,
    execute_cny08_compatibility,
    execute_crash_matrix,
    execute_ms_matrix,
    find_default_production_data_dir,
    run_full_canary_rehearsal,
)

EXPECTED_PROD_DB_HASH = "8b29f3c8714c1ae0ffc5db95a10e73cd299cf1ae74e01f5b8f402880a739df69"
EXPECTED_PROD_JSONL_HASH = "7f80bec3c8ca5bd4e214f470b132814f591b120e7c6174cd0700b1faf3639a6b"


def test_production_directory_isolation_and_hash_integrity() -> None:
    """Verify that real production files exist and remain byte-for-byte identical."""
    prod_dir = find_default_production_data_dir()
    db_file = prod_dir / "companion_chronicle.db"
    assert db_file.is_file(), f"Production DB missing at {db_file}"

    # Verify SHA-256
    db_hash = hashlib.sha256(db_file.read_bytes()).hexdigest().lower()
    assert db_hash == EXPECTED_PROD_DB_HASH, (
        f"Production DB hash mismatch: {db_hash} != {EXPECTED_PROD_DB_HASH}"
    )

    jsonl_file = prod_dir / "raw_slices.jsonl"
    if jsonl_file.is_file():
        jsonl_hash = hashlib.sha256(jsonl_file.read_bytes()).hexdigest().lower()
        assert jsonl_hash == EXPECTED_PROD_JSONL_HASH


def test_ms01_to_ms18_destructive_matrix(tmp_path: Path) -> None:
    """Execute complete M-S01 ~ M-S18 destructive safety matrix (18/18 PASS)."""
    passed, total = execute_ms_matrix(tmp_path)
    assert passed == 18
    assert total == 18


def test_crash_matrix_ten_scenarios(tmp_path: Path) -> None:
    """Validate 10 failure injection crash points with safe recovery and 0 data loss."""
    src = create_v1_database(tmp_path / "mock_prod.db", num_slices=10, num_events=10)
    crash_results = execute_crash_matrix(src, tmp_path)

    assert len(crash_results) == 10
    for r in crash_results:
        assert r.recovery_succeeded is True, f"Failed recovery for {r.scenario_name}"
        assert r.acked_writes_preserved is True, f"Data loss in {r.scenario_name}"
        assert r.manual_intervention_required is False


def test_rollback_safety_blind_restore_forbidden(tmp_path: Path) -> None:
    """Validate rollback safety: blind restore rejected if target has new canonical writes."""
    target = tmp_path / "target.db"
    backup = tmp_path / "target.db.pre_v2_backup"

    # Create V1 backup
    create_v1_database(backup, num_slices=5, num_events=5)

    # Create target V2 store
    store = ChronicleStoreV2(target)
    write_service = RawEvidenceWriteService(store)
    write_res = write_service.write_slice(
        WriteSliceCommand(content="New canonical V2 write", source="manual_feed")
    )
    assert write_res.status == "committed"
    store.close()

    # Attempt blind restore -> must raise RollbackForbiddenDataLossError
    with pytest.raises(RollbackForbiddenDataLossError) as exc_info:
        rollback_cutover(target, force_test_only=False)

    assert "Rollback forbidden" in str(exc_info.value)
    assert "Blind restore would discard ACKed data" in str(exc_info.value)


def test_semantic_smoke_cny01_to_cny08(tmp_path: Path) -> None:
    """Validate CNY-01 through CNY-08 integrated semantic smoke on V2."""
    project_root = Path(__file__).parents[2].resolve()

    # CNY-01 Retrieval Exact Metrics
    retrieval_metrics = execute_cny01_retrieval(project_root)
    assert retrieval_metrics["dev"]["passed"] == 27
    assert retrieval_metrics["holdout"]["passed"] == 15
    assert retrieval_metrics["holdout"]["total_retrieved"] == 15
    assert retrieval_metrics["holdout"]["candidate_precision_at_3"] == 12 / 15
    assert retrieval_metrics["holdout2"]["passed"] == 12

    # CNY-02 Sanctuary
    assert execute_cny02_sanctuary(project_root) is True

    # Setup isolated V2 store for CNY-03..CNY-08
    db_file = tmp_path / "smoke_v2.db"
    store = ChronicleStoreV2(db_file)

    # CNY-03 Consolidation
    assert execute_cny03_consolidation(store) is True
    # CNY-04 Understanding
    assert execute_cny04_understanding(store) is True
    # CNY-05 Chapter Privacy
    assert execute_cny05_chapter_privacy(store, tmp_path) is True
    # CNY-06 Narrative Firewall
    assert execute_cny06_narrative_firewall(store) is True
    # CNY-07 Single Master
    assert execute_cny07_single_master(store, tmp_path) is True
    # CNY-08 Compatibility
    assert execute_cny08_compatibility(store) is True

    store.close()


def test_full_canary_e2e_rehearsal_on_production_copy(tmp_path: Path) -> None:
    """Execute end-to-end full canary migration rehearsal on real production COPY."""
    prod_dir = find_default_production_data_dir()
    project_root = Path(__file__).parents[2].resolve()
    sandbox = tmp_path / "canary_sandbox"

    prod_db_file = prod_dir / "companion_chronicle.db"
    if not prod_db_file.is_file():
        pytest.skip(f"Production DB not found at {prod_db_file}")

    report = run_full_canary_rehearsal(
        prod_data_dir=prod_dir,
        sandbox_dir=sandbox,
        project_root=project_root,
    )

    # Invariants verification
    assert report.ms_assertions_pass_count == 18
    assert report.ms_assertions_total == 18
    assert report.data_loss_count == 0
    assert "Final canonical source-set parity verified (no watermark)" in report.parity_message
    assert report.raw_slice_fidelity_percent == 100.0
    assert report.legacy_hypothesis_promotions == 0
    assert report.foreign_key_violations == 0
    assert report.rollback_safety_verified is True
    assert report.flags_verified_false is True
    assert report.production_audit.untouched is True

    # Production DB byte-for-byte fidelity check
    h_after = hashlib.sha256(prod_db_file.read_bytes()).hexdigest().lower()
    assert h_after == EXPECTED_PROD_DB_HASH
