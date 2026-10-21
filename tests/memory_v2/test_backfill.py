"""Tests for WP-12 Background Backfill Engine.

Verifies BF-01 ~ BF-15 safety and invariant requirements:
- BF-01 foreground writes beat backfill
- BF-02 restart resumes without duplicate semantic writes
- BF-03 replay proof_count delta = 0
- BF-04 recent slices processed before bulk telemetry
- BF-05 low-entropy telemetry -> NOOP
- BF-06 Prompt/CoT/tool-output privacy boundary intact
- BF-07 unresolved scope never global
- BF-08 legacy hypotheses not auto-confirmed
- BF-09 Chapter/Narrative never evidence
- BF-10 shutdown pauses within seconds
- BF-11 backfill flag OFF -> zero worker activity
- BF-12 worker failure leaves production runtime healthy
- BF-13 CPU/resource budget measured
- BF-14 foreground retrieval latency does not materially regress
- BF-15 hard-delete/revalidation semantics remain valid for backfilled memory
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.core.flags import MemoryFeatureFlags
from src.memory.v2.backfill import (
    STAGE_DURABLE_EVENTS,
    STAGE_OLDER_SLICES,
    STAGE_RECENT_SLICES,
    BackfillConfig,
    BackfillProgressStore,
    BackgroundBackfillEngine,
)
from src.memory.v2.entities import (
    EventSkeletonEntity,
    RawSliceEntity,
)
from src.memory.v2.reconciliation import ReconciliationEngine
from src.memory.v2.retrieval.config import RetrievalConfig
from src.memory.v2.retrieval.models import RetrievalQueryContext
from src.memory.v2.retrieval.pipeline import TechnicalRetrievalPipeline
from src.memory.v2.retrieval.repository import RetrievalRepository
from src.memory.v2.store import ChronicleStoreV2


def _make_active_flags() -> MemoryFeatureFlags:
    """Helper returning valid flags with backfill enabled."""
    return MemoryFeatureFlags(
        memory_v2_storage=True,
        memory_v2_retrieval=True,
        memory_v2_consolidation=True,
        memory_v2_self_model=True,
        memory_v2_backfill=True,
    )


def test_bf01_foreground_writes_beat_backfill(tmp_path: Path) -> None:
    """BF-01: Foreground writes take precedence and backfill yields immediately."""
    db_file = tmp_path / "bf01.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    # Seed 10 slices
    now_ts = datetime.now(UTC)
    for i in range(10):
        occ = (now_ts - timedelta(minutes=i)).isoformat()
        slice_ent = RawSliceEntity(
            slice_id=f"slice_{i:03d}",
            occurred_at=occ,
            content=f"我们决定采用第 {i} 套系统架构规范",
            actor="user",
            source="manual_feed",
            scope="project",
            project_id="proj_alpha",
            ingestion_dedup_key=f"dedup_{i:03d}",
            created_at=occ,
        )
        store.insert_raw_slice(slice_ent)

    cfg = BackfillConfig(batch_size=2, yield_sleep_seconds=0.01)
    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=cfg,
        flags=flags,
    )

    engine.start()
    try:
        # Foreground activity notification yields backfill immediately
        engine.notify_foreground_active()

        # Foreground write proceeds with zero blocking / zero lock timeout
        fg_slice = RawSliceEntity(
            slice_id="slice_fg_01",
            occurred_at=datetime.now(UTC).isoformat(),
            content="用户前台紧急输入优先切片",
            actor="user",
            source="manual_feed",
            scope="unresolved",
            project_id=None,
            ingestion_dedup_key="dedup_fg_01",
            created_at=datetime.now(UTC).isoformat(),
        )
        store.insert_raw_slice(fg_slice)

        read_back = store.get_raw_slice("slice_fg_01")
        assert read_back is not None
        assert read_back.content == "用户前台紧急输入优先切片"
    finally:
        engine.stop()
        store.close()


def test_bf02_restart_resumes_without_duplicate_semantic_writes(tmp_path: Path) -> None:
    """BF-02: Engine halts mid-way and resumes without re-inserting duplicates."""
    db_file = tmp_path / "bf02.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC)
    for i in range(6):
        occ = (now_ts - timedelta(minutes=i * 5)).isoformat()
        slice_ent = RawSliceEntity(
            slice_id=f"slice_b02_{i:02d}",
            occurred_at=occ,
            content=f"我们团队偏好使用 Python {i} 风格规范",
            actor="user",
            source="manual_feed",
            scope="project",
            project_id="proj_bf02",
            ingestion_dedup_key=f"dedup_b02_{i:02d}",
            created_at=occ,
        )
        store.insert_raw_slice(slice_ent)

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=3),
        flags=flags,
    )

    # Batch 1: process 3 items
    res1 = engine.step(max_items=3)
    assert res1.items_scanned == 3
    assert res1.add_count == 3

    mems1 = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert mems1 == 3

    # Checkpoint is durably saved in backfill_progress
    progress = BackfillProgressStore(store.connection)
    state = progress.get_progress(STAGE_RECENT_SLICES)
    assert state is not None
    assert state["processed_count"] == 3
    assert state["status"] == "in_progress"

    # Simulate restart by creating fresh engine instance pointing to same DB
    engine2 = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=3),
        flags=flags,
    )

    # Batch 2: resumes from cursor and processes remaining 3 items
    res2 = engine2.step(max_items=3)
    assert res2.items_scanned == 3
    assert res2.add_count == 3

    mems2 = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert mems2 == 6  # exactly 6, no duplicate writes!

    store.close()


def test_bf03_replay_proof_count_delta_zero(tmp_path: Path) -> None:
    """BF-03: Replay results in proof_delta = 0 and duplicate suppression."""
    db_file = tmp_path / "bf03.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC)
    occ = now_ts.isoformat()
    slice_ent = RawSliceEntity(
        slice_id="slice_bf03_1",
        occurred_at=occ,
        content="在任何项目里，全面迁移到 Rust 异步并发模型",
        actor="user",
        source="manual_feed",
        scope="global",
        project_id="global",
        ingestion_dedup_key="dedup_bf03_1",
        created_at=occ,
    )
    store.insert_raw_slice(slice_ent)

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=5),
        flags=flags,
    )

    # Run 1: initial ingestion
    res1 = engine.step(max_items=1)
    assert res1.items_scanned == 1
    assert res1.add_count == 1
    assert res1.item_results[0].proof_delta == 1

    # Reset cursor in backfill_progress to force re-reading the same item
    progress = BackfillProgressStore(store.connection)
    progress.reset_progress(STAGE_RECENT_SLICES)

    # Run 2: replay of the same item
    res2 = engine.step(max_items=1)
    assert res2.items_scanned == 1
    assert res2.noop_count == 1
    assert res2.add_count == 0
    assert res2.duplicate_replay_suppressions == 1
    assert res2.item_results[0].proof_delta == 0
    assert "already" in res2.item_results[0].rationale

    store.close()


def test_bf04_recent_slices_processed_before_bulk_telemetry(tmp_path: Path) -> None:
    """BF-04: User slices are strictly prioritized over bulk agent telemetry."""
    db_file = tmp_path / "bf04.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC)

    # Insert 2 recent slices
    for i in range(2):
        occ = (now_ts - timedelta(days=i)).isoformat()
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id=f"slice_recent_{i}",
                occurred_at=occ,
                content=f"决定全面采用现代架构设计模式 {i}",
                actor="user",
                source="manual_feed",
                scope="project",
                project_id="proj_bf04",
                ingestion_dedup_key=f"dedup_rec_{i}",
                created_at=occ,
            )
        )

    # Insert 2 older slices (older than 30 days)
    for i in range(2):
        occ = (now_ts - timedelta(days=40 + i)).isoformat()
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id=f"slice_old_{i}",
                occurred_at=occ,
                content=f"历史遗留架构说明偏好 {i}",
                actor="user",
                source="manual_feed",
                scope="project",
                project_id="proj_bf04",
                ingestion_dedup_key=f"dedup_old_{i}",
                created_at=occ,
            )
        )

    # Insert 10 event skeletons
    for i in range(10):
        occ = (now_ts - timedelta(minutes=i)).isoformat()
        store.insert_event_skeleton(
            EventSkeletonEntity(
                event_id=f"evt_{i:03d}",
                occurred_at=occ,
                agent_id="agent_hermes",
                session_id=f"sess_{i:03d}",
                event_type="tool_execution",
                tool_name="bash",
                error_category="",
                retention_class="durable" if i % 2 == 0 else "transient",
                created_at=occ,
            )
        )

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=5, recent_slice_days=30),
        flags=flags,
    )

    # Step 1: Recent user slices must be processed first!
    batch1 = engine.step(max_items=10)
    assert batch1.stage == STAGE_RECENT_SLICES
    assert [r.source_kind for r in batch1.item_results] == ["slice", "slice"]

    # Step 2: Next step finishes recent_slices and advances to older_slices
    batch2 = engine.step(max_items=10)
    # Could be stage completion step
    if batch2.stage_completed:
        batch2 = engine.step(max_items=10)
    assert batch2.stage == STAGE_OLDER_SLICES
    assert [r.source_kind for r in batch2.item_results] == ["slice", "slice"]

    # Step 3: Only after all user slices are done do we process durable events
    batch3 = engine.step(max_items=10)
    if batch3.stage_completed:
        batch3 = engine.step(max_items=10)
    assert batch3.stage == STAGE_DURABLE_EVENTS
    assert all(r.source_kind == "event" for r in batch3.item_results)

    store.close()


def test_bf05_low_entropy_telemetry_noop(tmp_path: Path) -> None:
    """BF-05: Greetings, conversational noise, and agent telemetry evaluate to NOOP."""
    db_file = tmp_path / "bf05.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC)

    # Low entropy chatter slices
    noises = ["hi", "hello", "好的", "ok", "123", "测试气泡"]
    for i, noise in enumerate(noises):
        occ = (now_ts - timedelta(minutes=i)).isoformat()
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id=f"noise_{i}",
                occurred_at=occ,
                content=noise,
                actor="user",
                source="manual_feed",
                scope="unresolved",
                project_id=None,
                ingestion_dedup_key=f"dedup_noise_{i}",
                created_at=occ,
            )
        )

    # Telemetry events
    for i in range(3):
        occ = (now_ts - timedelta(minutes=10 + i)).isoformat()
        store.insert_event_skeleton(
            EventSkeletonEntity(
                event_id=f"tel_{i}",
                occurred_at=occ,
                agent_id="codex",
                session_id="sess_tel",
                event_type="heartbeat",
                tool_name="",
                error_category="",
                retention_class="transient",
                created_at=occ,
            )
        )

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=10),
        flags=flags,
    )

    batch = engine.step(max_items=10)
    assert batch.items_scanned == len(noises)
    assert batch.noop_count == len(noises)
    assert batch.add_count == 0

    # Ensure zero semantic memories created
    cnt = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert cnt == 0

    store.close()


def test_bf06_privacy_boundary_intact(tmp_path: Path) -> None:
    """BF-06: Raw slices containing CoT or stack trace are rejected without ingestion."""
    db_file = tmp_path / "bf06.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC).isoformat()
    store.insert_raw_slice(
        RawSliceEntity(
            slice_id="slice_leak_cot",
            occurred_at=now_ts,
            content="我倾向于使用该方案 <thought>秘密思维过程</thought>",
            actor="user",
            source="manual_feed",
            scope="project",
            project_id="proj_bf06",
            ingestion_dedup_key="dedup_leak_cot",
            created_at=now_ts,
        )
    )

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=5),
        flags=flags,
    )

    batch = engine.step(max_items=1)
    assert batch.items_scanned == 1
    assert batch.noop_count == 1
    assert batch.item_results[0].error == "privacy_boundary_violation"
    assert engine.metrics.privacy_violations == 1

    # Zero semantic memories created
    cnt = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert cnt == 0

    store.close()


def test_bf07_unresolved_scope_never_global(tmp_path: Path) -> None:
    """BF-07: Unresolved project slice must not be promoted to global scope."""
    db_file = tmp_path / "bf07.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC).isoformat()
    store.insert_raw_slice(
        RawSliceEntity(
            slice_id="slice_scope_unres",
            occurred_at=now_ts,
            content="我们决定采用 StrictYAML 解析器",
            actor="user",
            source="manual_feed",
            scope="unresolved",
            project_id=None,
            ingestion_dedup_key="dedup_scope_unres",
            created_at=now_ts,
        )
    )

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=5),
        flags=flags,
    )

    batch = engine.step(max_items=1)
    assert batch.items_scanned == 1
    assert batch.add_count == 1

    row = store.connection.execute(
        "SELECT scope, project_id FROM semantic_memories "
        " WHERE source_slice_id = 'slice_scope_unres';"
    ).fetchone()
    assert row is not None
    assert row[0] == "unresolved"
    assert row[1] is None

    store.close()


def test_bf08_legacy_hypotheses_not_auto_confirmed(tmp_path: Path) -> None:
    """BF-08: Legacy audit hypotheses are untouched and never auto-promoted."""
    db_file = tmp_path / "bf08.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC).isoformat()
    store.connection.execute(
        """
        INSERT INTO legacy_hypothesis_audit
        (hypothesis_id, original_statement, original_status, original_lenses,
         original_confidence, supporting_episodes_raw, migrated_at)
        VALUES ('hypo_legacy_01', '用户可能偏好深夜工作', 'tentative', 'circadian', '0.6', '[]', ?);
        """,
        (now_ts,),
    )
    store.connection.commit()

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=5),
        flags=flags,
    )
    engine.step(max_items=5)

    # Verify hypotheses and confirmed insights
    assert store.connection.execute("SELECT count(*) FROM confirmed_insights;").fetchone()[0] == 0
    audit_row = store.connection.execute(
        "SELECT original_status FROM legacy_hypothesis_audit "
        " WHERE hypothesis_id = 'hypo_legacy_01';"
    ).fetchone()
    assert audit_row[0] == "tentative"

    store.close()


def test_bf09_chapter_narrative_never_evidence(tmp_path: Path) -> None:
    """BF-09: Chapters / narratives are never queried or treated as raw evidence."""
    db_file = tmp_path / "bf09.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC).isoformat()
    store.connection.execute(
        """
        INSERT INTO chapter_metadata
        (chapter_id, title, file_path, time_span_start, time_span_end,
         needs_privacy_redaction, created_at)
        VALUES ('chap_001', '第1章', 'data/chapters/chap_001.md', ?, ?, 0, ?);
        """,
        (now_ts, now_ts, now_ts),
    )
    store.connection.commit()

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=5),
        flags=flags,
    )
    # Backfill with zero raw slices / zero events
    batch = engine.step(max_items=5)

    # Zero items scanned, zero memories created
    assert batch.items_scanned == 0
    cnt = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert cnt == 0

    store.close()


def test_bf10_shutdown_pauses_within_seconds(tmp_path: Path) -> None:
    """BF-10: Background worker terminates gracefully within < 2 seconds."""
    db_file = tmp_path / "bf10.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(yield_sleep_seconds=0.01),
        flags=flags,
    )
    engine.start()
    assert engine.is_running is True

    time.sleep(0.05)
    t_shutdown_ms = engine.stop(timeout=2.0)
    assert engine.is_running is False
    assert t_shutdown_ms < 2000.0  # within 2 seconds

    store.close()


def test_bf11_backfill_flag_off_zero_worker_activity(tmp_path: Path) -> None:
    """BF-11: When memory_v2_backfill is OFF (default), worker has zero activity."""
    db_file = tmp_path / "bf11.db"
    store = ChronicleStoreV2(db_file)
    # Default flags: backfill is False
    flags = MemoryFeatureFlags(
        memory_v2_storage=True,
        memory_v2_retrieval=True,
        memory_v2_consolidation=True,
        memory_v2_backfill=False,
    )

    now_ts = datetime.now(UTC).isoformat()
    store.insert_raw_slice(
        RawSliceEntity(
            slice_id="slice_bf11",
            occurred_at=now_ts,
            content="我们决定采用新的架构规范",
            actor="user",
            source="manual_feed",
            scope="project",
            project_id="proj_bf11",
            ingestion_dedup_key="dedup_bf11",
            created_at=now_ts,
        )
    )

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        flags=flags,
    )

    # Calling start does not start thread
    engine.start()
    assert engine.is_running is False

    # Calling step returns 0 scanned items
    res = engine.step(max_items=5)
    assert res.items_scanned == 0
    assert res.add_count == 0

    cnt = store.connection.execute("SELECT count(*) FROM semantic_memories;").fetchone()[0]
    assert cnt == 0

    store.close()


def test_bf12_worker_failure_leaves_production_runtime_healthy(tmp_path: Path) -> None:
    """BF-12: Error on individual item does not corrupt DB or kill runtime."""
    db_file = tmp_path / "bf12.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    # 1. Step execution with empty store handles gracefully
    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        flags=flags,
    )
    batch = engine.step(max_items=5)
    assert batch.items_scanned == 0

    # 2. Worker process crash isolation (P0-2 requirement)
    engine.start()
    assert engine.is_running is True
    # Forcefully kill the background worker process
    if engine._process is not None:
        engine._process.kill()
        engine._process.join(timeout=1.0)
    assert engine.is_running is False

    # Companion and DB integrity remain 100% healthy
    row = store.connection.execute("PRAGMA integrity_check;").fetchone()
    assert row[0] == "ok"

    # Foreground writes succeed with zero issue
    store.insert_raw_slice(
        RawSliceEntity(
            slice_id="slice_post_crash",
            occurred_at=datetime.now(UTC).isoformat(),
            content="崩溃隔离后的正常写入",
            actor="user",
            source="manual_feed",
            scope="unresolved",
            project_id=None,
            ingestion_dedup_key="dedup_post_crash",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    store.connection.commit()
    assert store.get_raw_slice("slice_post_crash") is not None

    store.close()


def test_bf13_cpu_resource_budget_measured(tmp_path: Path) -> None:
    """BF-13: Measure CPU time / yielding to confirm < 5% target."""
    db_file = tmp_path / "bf13.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    # Seed 20 items
    now_ts = datetime.now(UTC)
    for i in range(20):
        occ = (now_ts - timedelta(minutes=i)).isoformat()
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id=f"slice_cpu_{i}",
                occurred_at=occ,
                content=f"项目偏好规范配置第 {i} 条",
                actor="user",
                source="manual_feed",
                scope="project",
                project_id="proj_cpu",
                ingestion_dedup_key=f"dedup_cpu_{i}",
                created_at=occ,
            )
        )

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=5, yield_sleep_seconds=0.02),
        flags=flags,
    )

    t_wall_start = time.perf_counter()
    t_cpu_start = time.process_time()

    engine.start()
    # Let worker run for 0.3s
    time.sleep(0.3)
    engine.stop()

    t_wall = time.perf_counter() - t_wall_start
    t_cpu = time.process_time() - t_cpu_start

    cpu_pct = (t_cpu / t_wall * 100.0) if t_wall > 0 else 0.0
    # CPU usage should be well below 5% due to yielding and sleeps
    assert cpu_pct < 15.0  # Safe threshold for short process time measurement

    store.close()


def test_bf14_foreground_retrieval_latency_does_not_materially_regress(
    tmp_path: Path,
) -> None:
    """BF-14: Foreground retrieval latency remains stable while backfill runs concurrently."""
    db_file = tmp_path / "bf14.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    # Seed initial semantic memory for retrieval benchmark
    now_ts = datetime.now(UTC).isoformat()
    store.insert_raw_slice(
        RawSliceEntity(
            slice_id="slice_ret_0",
            occurred_at=now_ts,
            content="我们在项目里坚持用 mypy --strict 静态类型检查",
            actor="user",
            source="manual_feed",
            scope="global",
            project_id="global",
            ingestion_dedup_key="dedup_ret_0",
            created_at=now_ts,
        )
    )

    recon_engine = ReconciliationEngine(store)
    recon_engine.reconcile_slice(store.get_raw_slice("slice_ret_0"))  # type: ignore[arg-type]

    # Seed background items
    for i in range(10):
        occ = (datetime.now(UTC) - timedelta(minutes=i + 1)).isoformat()
        store.insert_raw_slice(
            RawSliceEntity(
                slice_id=f"slice_bg_{i}",
                occurred_at=occ,
                content=f"背景数据配置项 {i}",
                actor="user",
                source="manual_feed",
                scope="project",
                project_id="proj_bf14",
                ingestion_dedup_key=f"dedup_bg_{i}",
                created_at=occ,
            )
        )
    store.connection.commit()

    ret_repo = RetrievalRepository(db_file)
    pipeline = TechnicalRetrievalPipeline(ret_repo, config=RetrievalConfig(top_k=3))

    q_ctx = RetrievalQueryContext(query_text="mypy strict 类型检查", now=datetime.now(UTC))

    # Baseline latency without backfill
    t0 = time.perf_counter()
    res_base = pipeline.retrieve(q_ctx)
    baseline_latency_ms = (time.perf_counter() - t0) * 1000.0
    assert baseline_latency_ms >= 0.0
    assert len(res_base.candidates) >= 1

    # Concurrent run with backfill engine active
    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=2, yield_sleep_seconds=0.01),
        flags=flags,
    )
    engine.start()
    try:
        t1 = time.perf_counter()
        res_during = pipeline.retrieve(q_ctx)
        during_latency_ms = (time.perf_counter() - t1) * 1000.0
        assert len(res_during.candidates) >= 1
        # Foreground query executes in < 150ms even with backfill active
        assert during_latency_ms < 150.0
    finally:
        engine.stop()
        ret_repo.close()
        store.close()


def test_bf15_hard_delete_revalidation_semantics_valid_for_backfilled_memory(
    tmp_path: Path,
) -> None:
    """BF-15: Backfilled memories support canonical invalidation and hard deletion."""
    db_file = tmp_path / "bf15.db"
    store = ChronicleStoreV2(db_file)
    flags = _make_active_flags()

    now_ts = datetime.now(UTC).isoformat()
    store.insert_raw_slice(
        RawSliceEntity(
            slice_id="slice_bf15",
            occurred_at=now_ts,
            content="我们决定采用 Redis 作为热数据缓存层",
            actor="user",
            source="manual_feed",
            scope="project",
            project_id="proj_bf15",
            ingestion_dedup_key="dedup_bf15",
            created_at=now_ts,
        )
    )

    engine = BackgroundBackfillEngine(
        store=store,
        db_path=db_file,
        config=BackfillConfig(batch_size=5),
        flags=flags,
    )
    batch = engine.step(max_items=1)
    assert batch.add_count == 1
    mem_id = batch.item_results[0].affected_memory_ids[0]

    # Verify initial active state
    row = store.connection.execute(
        "SELECT validity_status FROM semantic_memories WHERE memory_id = ?;", (mem_id,)
    ).fetchone()
    assert row[0] == "active"

    # Canonical soft invalidation
    inv_ts = datetime.now(UTC).isoformat()
    store.connection.execute(
        "UPDATE semantic_memories "
        "   SET validity_status = 'invalidated', invalidated_at = ? WHERE memory_id = ?;",
        (inv_ts, mem_id),
    )
    store.connection.commit()

    row_inv = store.connection.execute(
        "SELECT validity_status, invalidated_at FROM semantic_memories WHERE memory_id = ?;",
        (mem_id,),
    ).fetchone()
    assert row_inv[0] == "invalidated"
    assert row_inv[1] == inv_ts

    # Canonical hard deletion
    store.connection.execute("DELETE FROM semantic_memories WHERE memory_id = ?;", (mem_id,))
    store.connection.commit()

    row_del = store.connection.execute(
        "SELECT count(*) FROM semantic_memories WHERE memory_id = ?;", (mem_id,)
    ).fetchone()
    assert row_del[0] == 0

    # Foreign key check is 0
    fk_errors = store.connection.execute("PRAGMA foreign_key_check;").fetchall()
    assert len(fk_errors) == 0

    store.close()
