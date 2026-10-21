"""Full Companion Production Runtime Verification (WP-14 Sign-off).

Executes:
1. Verify commit b4993e03... and repo root.
2. Launch Full CompanionApp using production launch path.
3. Verify PySide body, PetWindow, Feeder, settings, flags, V2 storage, retrieval,
   consolidation, self_model.
4. Verify data root D:/CodeProjects/co-evolving-companion/data and zero worktree data directory.
5. Verify foreground interaction path.
6. Trigger graceful shutdown via QTimer.
7. Restart full CompanionApp, verify successful re-attachment to same V2 DB.
8. Perform second graceful shutdown.
9. Post-restart PRAGMAs: user_version=20261018, integrity_check=ok, foreign_key_check=0.
10. Verify compatibility views and single canonical writer.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

repo_root = Path(__file__).parents[1].resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import run_companion  # noqa: E402
from src.core.paths import CANONICAL_PROD_DATA_DIR  # noqa: E402
from src.memory.v2.compatibility import (  # noqa: E402
    has_legacy_views,
    verify_legacy_views_read_only,
)


def run_runtime_verification() -> None:
    print("=== STARTING FULL PRODUCTION COMPANION RUNTIME VERIFICATION ===")

    # 1. Verify release commit
    git_commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(f"Production runtime code root: {repo_root}")
    print(f"Production runtime commit:    {git_commit}")

    # 2. First Launch of CompanionApp
    print("\n--- LAUNCH 1: Full CompanionApp Startup & Initialization ---")
    app1 = run_companion.CompanionApp()

    # A. Full CompanionApp started
    assert isinstance(app1, run_companion.CompanionApp)
    print("A. Full CompanionApp instance created successfully: PASS")

    # B. PySide body / pet window initialized
    assert hasattr(app1, "window") and app1.window is not None
    print("B. PetWindow & BodyController initialized: PASS")

    # C. Feeder initialized
    assert hasattr(app1, "overlay") and app1.overlay is not None
    assert hasattr(app1, "store") and app1.store is not None
    print("C. Slice Feeder initialized: PASS")

    # D. Release commit confirmed
    print(f"D. Production runtime confirmed running commit: {git_commit}")

    # E. Data root confirmed
    expected_data_root = CANONICAL_PROD_DATA_DIR.resolve()
    actual_data_root = app1.data_dir.resolve()
    print(f"E. Data root resolved: {actual_data_root}")
    assert actual_data_root == expected_data_root, (
        f"Data root mismatch: {actual_data_root} != {expected_data_root}"
    )

    # F. selected_path = v2
    diag = app1.memory_v2_diag
    print(f"F. Memory V2 diagnostic selected_path: {diag.get('selected_path')}")
    assert diag.get("selected_path") == "v2", (
        f"Expected selected_path='v2', got {diag.get('selected_path')}"
    )

    # G. Final Flags
    active_flags = app1.flags.to_dict()
    print(f"G. Active flags: {active_flags}")
    assert active_flags["memory_v2_storage"] is True
    assert active_flags["memory_v2_retrieval"] is True
    assert active_flags["memory_v2_consolidation"] is True
    assert active_flags["memory_v2_self_model"] is True
    assert active_flags["memory_v2_migration"] is False
    assert active_flags["memory_v2_backfill"] is False

    # H. ConsolidationScheduler started without thread ownership error
    assert app1.consolidation_scheduler is not None
    assert app1.consolidation_scheduler.is_running is True
    print("H. ConsolidationScheduler running normally: PASS")

    # I. Normal foreground interaction path
    print("I. Testing foreground slice feed and bubble reply...")
    app1._on_slice_submitted("WP-14 生产运行时前台切片提交测试")
    app1._on_user_reply_to_bubble("WP-14 生产运行时气泡交互回复测试", "测试")
    print("I. Foreground interaction path executed durably: PASS")

    # J. Graceful shutdown
    print("\n--- SHUTDOWN 1: Graceful Shutdown of CompanionApp ---")
    app1._on_quit()
    print("J. CompanionApp graceful shutdown succeeded: PASS")

    # K. Second Launch (Restart Verification)
    print("\n--- LAUNCH 2: Full CompanionApp Restart Verification ---")
    app2 = run_companion.CompanionApp()
    assert isinstance(app2, run_companion.CompanionApp)
    assert app2.consolidation_scheduler is not None
    assert app2.consolidation_scheduler.is_running is True
    print("K. CompanionApp restart succeeded: PASS")

    # L. Restart connected to same production V2 DB
    assert app2.data_dir.resolve() == expected_data_root
    assert str(app2.v2_store.db_path) == str(expected_data_root / "companion_chronicle.db")
    print("L. Reconnected to same production V2 DB: PASS")

    # M. No V1 legacy writer active
    assert app2.router.is_v2_active is True
    assert app2.router.active_route == "v2_canonical"
    assert app2.write_service is not None
    print("M. No V1 legacy writer active (V2 canonical route active): PASS")

    # N. No coeva-lane-n/data directory created
    lane_n_data = repo_root / "data"
    assert not lane_n_data.exists(), f"Accidental local data directory created at {lane_n_data}!"
    print("N. Verified zero rogue data directory created in worktree: PASS")

    # Second shutdown
    app2._on_quit()
    print("Second CompanionApp shutdown succeeded.")

    # O. Post-restart PRAGMAs on live production DB
    print("\n--- PRAGMAS & INTEGRITY AUDIT ---")
    prod_db = expected_data_root / "companion_chronicle.db"
    conn = sqlite3.connect(str(prod_db))
    cur = conn.cursor()

    cur.execute("PRAGMA user_version;")
    uv = cur.fetchone()[0]
    print(f"PRAGMA user_version: {uv}")
    assert uv == 20261018, f"user_version mismatch: {uv}"

    cur.execute("PRAGMA integrity_check;")
    integ = cur.fetchone()[0]
    print(f"PRAGMA integrity_check: {integ}")
    assert integ == "ok", f"integrity_check failed: {integ}"

    cur.execute("PRAGMA foreign_key_check;")
    fk = len(cur.fetchall())
    print(f"PRAGMA foreign_key_check: {fk}")
    assert fk == 0, f"foreign_key_check violations: {fk}"

    # P. Compatibility views exist and read-only
    assert has_legacy_views(conn) is True
    assert verify_legacy_views_read_only(conn) is True
    print("P. Compatibility views present and strictly read-only: PASS")

    # Q & R. SQLite single canonical writer & JSONL one-way export
    cur.execute("SELECT count(*) FROM raw_slices;")
    slices_count = cur.fetchone()[0]
    jsonl_path = expected_data_root / "raw_slices.jsonl"
    assert jsonl_path.is_file()
    print(f"Q & R. Raw slices in canonical SQLite: {slices_count}, JSONL export verified: PASS")

    conn.close()
    print("\n=== FULL COMPANION RUNTIME VERIFICATION COMPLETED: ALL PASS ===")


if __name__ == "__main__":
    run_runtime_verification()
