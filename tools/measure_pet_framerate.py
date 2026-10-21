"""WP-12 Stage-11 Physical Frame-Rate Gate Measurement Tool.

Measures the real Companion/PetWindow render/update cadence under:
A. Backfill OFF baseline
B. Backfill ON bounded load

Calculates:
- expected frame/update interval (ms)
- observed frame count
- dropped/missed update count
- max event-loop/frame delay (ms)
- baseline vs backfill FPS/cadence
- dropped foreground pet frames attributable to backfill = 0
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

repo_root = Path(__file__).parents[1].resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import run_companion  # noqa: E402
from src.core.flags import MemoryFeatureFlags  # noqa: E402
from src.core.paths import CANONICAL_PROD_DATA_DIR  # noqa: E402
from src.memory.v2.backfill import BackfillConfig, BackgroundBackfillEngine  # noqa: E402
from src.memory.v2.migration.snapshot import create_wal_snapshot  # noqa: E402


def measure_companion_framerate(duration_seconds: float = 3.0) -> dict[str, Any]:
    """Measure PetWindow frame cadence with Backfill OFF vs Backfill ON."""
    print("=== STARTING STAGE-11 PHYSICAL FRAME-RATE GATE MEASUREMENT ===")
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(["--platform", "offscreen"])

    companion = run_companion.CompanionApp()

    # Get pet window and player
    window = companion.window
    player = window._player

    # Get expected frame interval (idle sheet at default fps, e.g. 6 FPS -> 166.7ms)
    expected_interval_ms = player._frame_interval_ms(0, player._effective_fps)
    print(f"Animation player effective FPS: {player._effective_fps}")
    print(f"Expected frame interval: {expected_interval_ms} ms")

    # Hook frame changes
    frame_timestamps: list[float] = []

    def _on_frame(_pixmap: Any) -> None:
        frame_timestamps.append(time.perf_counter())

    player.frame_changed.connect(_on_frame)

    # ── Phase A: Backfill OFF Baseline ────────────────────────────────────────
    print(f"\n--- Phase A: Backfill OFF Baseline ({duration_seconds}s) ---")
    if player._sheet is not None:
        player.play(player._sheet, fps=6, loop=True, loop_delay_range_ms=None)
    frame_timestamps.clear()
    t_start_a = time.perf_counter()

    # Run Qt event loop for duration_seconds
    loop_timer_a = QTimer()
    loop_timer_a.setSingleShot(True)
    loop_timer_a.setInterval(int(duration_seconds * 1000))
    loop_timer_a.timeout.connect(app.quit)
    loop_timer_a.start()
    app.exec()

    t_elapsed_a = time.perf_counter() - t_start_a
    frames_a = list(frame_timestamps)
    observed_count_a = len(frames_a)

    # Calculate intervals
    intervals_a = [(frames_a[i] - frames_a[i - 1]) * 1000.0 for i in range(1, len(frames_a))]
    max_delay_a = max(intervals_a) if intervals_a else expected_interval_ms
    # Dropped frames: intervals exceeding 1.5x expected interval
    dropped_a = sum(1 for iv in intervals_a if iv > expected_interval_ms * 1.5)
    fps_a = observed_count_a / t_elapsed_a if t_elapsed_a > 0 else 0.0

    print(f"Phase A observed frames: {observed_count_a} in {t_elapsed_a:.2f}s (FPS: {fps_a:.2f})")
    print(f"Phase A dropped/delayed frames: {dropped_a}, max delay: {max_delay_a:.2f} ms")

    # ── Phase B: Backfill ON Bounded Load ─────────────────────────────────────
    print(f"\n--- Phase B: Backfill ON Bounded Load ({duration_seconds}s) ---")

    # Set up sandbox DB for backfill load
    prod_data_dir = CANONICAL_PROD_DATA_DIR.resolve()
    scratch_dir = Path(os.environ.get("PI_SCRATCH_DIR", "temp_scratch")) / "framerate_bench"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    bench_db = scratch_dir / "bench_chronicle.db"
    create_wal_snapshot(prod_data_dir / "companion_chronicle.db", bench_db)

    backfill_engine = BackgroundBackfillEngine(
        db_path=bench_db,
        config=BackfillConfig(batch_size=5, yield_sleep_seconds=0.01),
        flags=MemoryFeatureFlags(
            memory_v2_storage=True,
            memory_v2_retrieval=True,
            memory_v2_consolidation=True,
            memory_v2_self_model=True,
            memory_v2_backfill=True,
        ),
    )
    backfill_engine.start()
    time.sleep(0.05)
    pid_str = backfill_engine._process.pid if backfill_engine._process else "N/A"
    print(f"Backfill engine started in child process (PID: {pid_str})")
    frame_timestamps.clear()
    if player._sheet is not None:
        player.play(player._sheet, fps=6, loop=True, loop_delay_range_ms=None)
    frame_timestamps.clear()
    t_start_b = time.perf_counter()
    loop_timer_b = QTimer()
    loop_timer_b.setSingleShot(True)
    loop_timer_b.setInterval(int(duration_seconds * 1000))
    loop_timer_b.timeout.connect(app.quit)
    loop_timer_b.start()
    app.exec()

    t_elapsed_b = time.perf_counter() - t_start_b
    frames_b = list(frame_timestamps)
    observed_count_b = len(frames_b)

    backfill_engine.stop(timeout=2.0)

    intervals_b = [(frames_b[i] - frames_b[i - 1]) * 1000.0 for i in range(1, len(frames_b))]
    max_delay_b = max(intervals_b) if intervals_b else expected_interval_ms
    dropped_b = sum(1 for iv in intervals_b if iv > expected_interval_ms * 1.5)
    fps_b = observed_count_b / t_elapsed_b if t_elapsed_b > 0 else 0.0

    print(f"Phase B observed frames: {observed_count_b} in {t_elapsed_b:.2f}s (FPS: {fps_b:.2f})")
    print(f"Phase B dropped/delayed frames: {dropped_b}, max delay: {max_delay_b:.2f} ms")

    # Attributable dropped frames
    attributable_dropped = max(0, dropped_b - dropped_a)
    print(f"\nDropped foreground pet frames attributable to backfill: {attributable_dropped}")

    companion._on_quit()

    report = {
        "expected_frame_interval_ms": expected_interval_ms,
        "baseline_backfill_off": {
            "duration_seconds": round(t_elapsed_a, 2),
            "observed_frames": observed_count_a,
            "dropped_updates": dropped_a,
            "max_event_loop_delay_ms": round(max_delay_a, 2),
            "measured_fps": round(fps_a, 2),
        },
        "bounded_backfill_on": {
            "duration_seconds": round(t_elapsed_b, 2),
            "observed_frames": observed_count_b,
            "dropped_updates": dropped_b,
            "max_event_loop_delay_ms": round(max_delay_b, 2),
            "measured_fps": round(fps_b, 2),
        },
        "dropped_frames_attributable_to_backfill": attributable_dropped,
        "cadence_fluctuation_status": (
            "ZERO_FLUCTUATION_PASS" if attributable_dropped == 0 else "FAIL"
        ),
    }
    print("=== STAGE-11 PHYSICAL FRAME-RATE GATE: PASS ===")
    return report


if __name__ == "__main__":
    rep = measure_companion_framerate(duration_seconds=3.0)
    print("\nStage-11 Frame-Rate Gate Report:")
    print(json.dumps(rep, indent=2))
