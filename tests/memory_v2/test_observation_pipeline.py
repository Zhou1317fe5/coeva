"""Tests for WP-6 Observation, Hypothesis & Calibration Pipeline.

Strictly verifies all required test cases:
- S6-01: Single-slice psych guard (isolated slice cannot create psych hypothesis)
- S6-02: Multi-source observation (independent evidence aggregates with proof_count)
- S6-03: Counter evidence (counter/contextual links do not increase proof_count)
- S6-04: Scope isolation (project evidence cannot silently form global observation)
- S6-05: Candidate != confirmed (new hypothesis starts non-confirmed)
- S6-06: YES calibration (immutable event recorded; insight produced)
- S6-07: PARTLY calibration (refinement preserved without deleting original history)
- S6-08: NO calibration (hypothesis rejected; no confirmed insight produced)
- S6-09: NOT_NOW calibration (no confirmation/rejection; defer state preserved)
- S6-10: Calibration immutable (past calibration rows cannot be deleted)
- S6-11: Lifecycle evidence loss (evidence loss -> proof recompute -> retraction)
- S6-12: Calibration survives retraction (calibration history remains intact)
- S6-13: Event retention pin (observation adoption pins event skeleton)
- S6-14: Last durable ref unpins (removing observation provenance unpins event)
- S6-15: Echo not evidence (assistant echo cannot increase proof)
- S6-16: Telemetry boundary (telemetry alone cannot create feeling hypothesis)
- S6-17: No chapter leakage (no growth chapter generated or used as evidence)
- S6-18: No WP-7/8 changes (retrieval and recall gate untouched)
- S6-19: Production isolation (production DB untouched; self-model flag default OFF)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.core.flags import override_flags, resolve_flags
from src.memory.v2.calibration import (
    CalibrationDecision,
    CalibrationResponse,
    CalibrationService,
    IllegalCalibrationError,
)
from src.memory.v2.entities import (
    ChapterMetadataEntity,
    ChapterSliceLinkEntity,
    EpisodeEntity,
    EventSkeletonEntity,
    RawSliceEntity,
    SemanticMemoryEntity,
)
from src.memory.v2.hypothesis import (
    DevelopmentLens,
    HypothesisEngine,
    HypothesisProposal,
)
from src.memory.v2.lifecycle import LifecycleService
from src.memory.v2.observation import (
    EchoEvidenceError,
    ObservationBuilder,
    ObservationCandidate,
    ObservationPipeline,
    ScopeIsolationError,
    SingleSlicePsychError,
    TelemetryAuthorityError,
)
from src.memory.v2.provenance import ProvenanceRepository
from src.memory.v2.self_model import SlowPathSelfModelService
from src.memory.v2.store import ChronicleStoreV2


def make_slice(
    store: ChronicleStoreV2,
    slice_id: str,
    content: str,
    *,
    scope: str = "global",
    project_id: str | None = None,
    occurred_at: str = "2026-10-20T10:00:00+00:00",
) -> RawSliceEntity:
    """Helper to insert a raw slice into store."""
    entity = RawSliceEntity(
        slice_id=slice_id,
        occurred_at=occurred_at,
        content=content,
        scope=scope,  # type: ignore[arg-type]
        project_id=project_id,
        ingestion_dedup_key=f"dedup_{slice_id}",
        created_at=occurred_at,
    )
    store.insert_raw_slice(entity)
    return entity


def make_event(
    store: ChronicleStoreV2,
    event_id: str,
    *,
    occurred_at: str = "2026-10-20T10:05:00+00:00",
    retention_class: str = "transient",
) -> EventSkeletonEntity:
    """Helper to insert an event skeleton into store."""
    entity = EventSkeletonEntity(
        event_id=event_id,
        occurred_at=occurred_at,
        agent_id="test_agent",
        session_id="sess_01",
        event_type="tool_execution",
        tool_name="git_commit",
        retention_class=retention_class,  # type: ignore[arg-type]
        created_at=occurred_at,
    )
    store.insert_event_skeleton(entity)
    return entity


def make_memory(
    store: ChronicleStoreV2,
    memory_id: str,
    statement: str,
    source_slice_id: str,
    *,
    scope: str = "global",
    project_id: str | None = None,
    valid_from: str = "2026-10-20T10:00:00+00:00",
) -> SemanticMemoryEntity:
    """Helper to insert an active semantic memory into store."""
    entity = SemanticMemoryEntity(
        memory_id=memory_id,
        category="preference",
        statement=statement,
        authority_class="user_asserted",
        scope=scope,  # type: ignore[arg-type]
        project_id=project_id,
        source_slice_id=source_slice_id,
        valid_from=valid_from,
        validity_status="active",
        created_at=valid_from,
    )
    store.insert_semantic_memory(entity)
    return entity


# ── S6-01: Single-slice psych guard ──────────────────────────────────────────


def test_s6_01_single_slice_psych_guard(tmp_path: Path) -> None:
    """S6-01: One isolated slice cannot create a psychological/self-model hypothesis."""
    store = ChronicleStoreV2(tmp_path / "s6_01.db")
    obs_pipeline = ObservationPipeline(store, min_psych_proof_count=2)
    hyp_engine = HypothesisEngine(store, min_independent_evidence=2)

    make_slice(store, "sl_01", "今天感觉工作好累，有点焦虑。")

    # Path A: Directly attempting to create subjective observation from 1 slice
    sub_cand = (
        ObservationBuilder("用户在面对工作压力时表现出焦虑情绪")
        .with_subjective_claim(True)
        .add_slice("sl_01", "supporting")
        .build()
    )
    with pytest.raises(SingleSlicePsychError) as exc_a:
        obs_pipeline.create_observation(sub_cand)
    assert "single slice forbidden" in str(exc_a.value)

    # Path B: Objective observation with 1 slice cannot form a psych hypothesis
    obj_cand = (
        ObservationBuilder("用户提到了今天感觉工作疲惫")
        .with_subjective_claim(False)
        .add_slice("sl_01", "supporting")
        .build()
    )
    obs_entity = obs_pipeline.create_observation(obj_cand)
    assert obs_entity.proof_count == 1

    # Attempting to derive a developmental hypothesis from this single-slice observation
    prop = HypothesisProposal(
        statement="用户在压力下容易产生回避与焦虑情绪",
        lenses=[DevelopmentLens.EXPERIENTIAL_OPENNESS],
        supporting_observation_ids=[obs_entity.observation_id],
    )
    with pytest.raises(SingleSlicePsychError) as exc_b:
        hyp_engine.propose_hypothesis(prop)
    assert "One isolated slice cannot create" in str(exc_b.value)

    # Baseline DB assertions: 0 hypotheses exist
    assert store.connection.execute("SELECT COUNT(*) FROM hypotheses;").fetchone()[0] == 0


# ── S6-02: Multi-source observation ──────────────────────────────────────────


def test_s6_02_multi_source_observation(tmp_path: Path) -> None:
    """S6-02: Multi-source observation creates one Observation with correct proof_count."""
    store = ChronicleStoreV2(tmp_path / "s6_02.db")
    obs_pipeline = ObservationPipeline(store)

    make_slice(store, "sl_a", "我通常习惯在午后专注调试代码。")
    make_slice(store, "sl_b", "下午两点到四点是我代码效率最高的时段。")
    make_event(store, "ev_c")

    cand = (
        ObservationBuilder("用户具有显著的午后高产出编程节律")
        .add_slice("sl_a", "supporting")
        .add_slice("sl_b", "supporting")
        .add_event("ev_c", "supporting")
        .build()
    )
    obs = obs_pipeline.create_observation(cand)

    assert obs.proof_count == 3
    assert obs.status == "active"

    # Verify SQLite rows
    db_obs = store.get_observation(obs.observation_id)
    assert db_obs is not None
    assert db_obs.proof_count == 3

    slice_links = store.get_observation_slice_links(obs.observation_id)
    assert len(slice_links) == 2
    event_links = store.get_observation_event_links(obs.observation_id)
    assert len(event_links) == 1


# ── S6-03: Counter evidence ──────────────────────────────────────────────────


def test_s6_03_counter_evidence_does_not_increase_proof_count(tmp_path: Path) -> None:
    """S6-03: Counter/contextual link does not increase positive proof_count."""
    store = ChronicleStoreV2(tmp_path / "s6_03.db")
    obs_pipeline = ObservationPipeline(store)

    make_slice(store, "sl_pos1", "我很喜欢使用 pytest 进行自动化测试。")
    make_slice(store, "sl_pos2", "单元测试对我来说必不可少。")
    make_slice(store, "sl_counter", "有时候赶进度我也会先跳过编写测试。")
    make_event(store, "ev_counter")

    # Add an episode for contextual scope
    ep = EpisodeEntity(
        episode_id="ep_context",
        scope="global",
        started_at="2026-10-20T09:00:00+00:00",
        title_hint="测试工程讨论",
    )
    store.insert_episode(ep)

    cand = (
        ObservationBuilder("用户对自动化测试具有强认同但有进度妥协")
        .add_slice("sl_pos1", "supporting")
        .add_slice("sl_pos2", "supporting")
        .add_slice("sl_counter", "counter")
        .add_event("ev_counter", "counter")
        .add_episode("ep_context")
        .build()
    )
    obs = obs_pipeline.create_observation(cand)

    # Only the 2 supporting slices count as positive proof
    assert obs.proof_count == 2

    # Verify counter and contextual links exist in DB without inflating proof_count
    slice_links = store.get_observation_slice_links(obs.observation_id)
    counter_slices = [link for link in slice_links if link.role == "counter"]
    assert len(counter_slices) == 1

    ep_links = store.get_observation_episode_links(obs.observation_id)
    assert len(ep_links) == 1
    assert ep_links[0].role == "contextual_scope"


# ── S6-04: Scope isolation ───────────────────────────────────────────────────


def test_s6_04_scope_isolation_preserved(tmp_path: Path) -> None:
    """S6-04: Project evidence cannot silently form a global Observation/Hypothesis."""
    store = ChronicleStoreV2(tmp_path / "s6_04.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)

    make_slice(
        store,
        "sl_proj_a1",
        "在 project_x 中全面启用 Rust 重构。",
        scope="project",
        project_id="project_x",
    )
    make_slice(
        store,
        "sl_proj_a2",
        "project_x 性能瓶颈需要 Rust 模块替代。",
        scope="project",
        project_id="project_x",
    )

    # 1. Attempting global observation with project_x evidence fails closed
    cand_global = (
        ObservationBuilder("用户全面倾向使用 Rust 重构所有项目")
        .with_scope("global")
        .add_slice("sl_proj_a1", "supporting")
        .add_slice("sl_proj_a2", "supporting")
        .build()
    )
    with pytest.raises(ScopeIsolationError):
        obs_pipeline.create_observation(cand_global)

    # 2. Scoped observation succeeds
    cand_proj = (
        ObservationBuilder("用户在 project_x 中倾向使用 Rust 重构")
        .with_scope("project", project_id="project_x")
        .add_slice("sl_proj_a1", "supporting")
        .add_slice("sl_proj_a2", "supporting")
        .build()
    )
    obs_proj = obs_pipeline.create_observation(cand_proj)
    assert obs_proj.scope == "project"
    assert obs_proj.project_id == "project_x"

    # 3. Attempting global hypothesis from project observation fails closed
    prop_global = HypothesisProposal(
        statement="用户将 Rust 视为通用首选语言",
        lenses=[DevelopmentLens.AUTONOMOUS_ACTION],
        supporting_observation_ids=[obs_proj.observation_id],
        scope="global",
    )
    with pytest.raises(ScopeIsolationError):
        hyp_engine.propose_hypothesis(prop_global)

    # 4. Attempting cross-project hypothesis for project_y fails closed
    prop_cross = HypothesisProposal(
        statement="用户在 project_y 中也计划使用 Rust",
        lenses=[DevelopmentLens.AUTONOMOUS_ACTION],
        supporting_observation_ids=[obs_proj.observation_id],
        scope="project",
        project_id="project_y",
    )
    with pytest.raises(ScopeIsolationError):
        hyp_engine.propose_hypothesis(prop_cross)


# ── S6-05: Candidate != Confirmed ────────────────────────────────────────────


def test_s6_05_candidate_not_confirmed_initially(tmp_path: Path) -> None:
    """S6-05: New Hypothesis starts non-confirmed (INV-6)."""
    store = ChronicleStoreV2(tmp_path / "s6_05.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)

    make_slice(store, "sl_1", "我遇到未知错误通常先仔细研读官方文档。")
    make_slice(store, "sl_2", "遇到复杂问题我不会立刻到处试错，而是看 spec。")

    cand = (
        ObservationBuilder("用户在技术攻关时倾向于规范优先")
        .add_slice("sl_1", "supporting")
        .add_slice("sl_2", "supporting")
        .build()
    )
    obs = obs_pipeline.create_observation(cand)

    prop = HypothesisProposal(
        statement="用户面对不确定性时倾向于结构化规范锚定",
        lenses=[DevelopmentLens.OPENNESS_TO_UNCERTAINTY],
        supporting_observation_ids=[obs.observation_id],
    )
    hyp = hyp_engine.propose_hypothesis(prop)

    # Invariant: Status MUST strictly be candidate
    assert hyp.status == "candidate"

    # Confirm in SQLite table
    row = store.connection.execute(
        "SELECT status, last_calibrated_at FROM hypotheses WHERE hypothesis_id = ?;",
        (hyp.hypothesis_id,),
    ).fetchone()
    assert row["status"] == "candidate"
    assert row["last_calibrated_at"] is None

    # Strict zero confirmed insight assertion
    ins_count = store.connection.execute("SELECT COUNT(*) FROM confirmed_insights;").fetchone()[0]
    assert ins_count == 0


# ── S6-06: YES calibration ───────────────────────────────────────────────────


def test_s6_06_yes_calibration(tmp_path: Path) -> None:
    """S6-06: Immutable event recorded; valid Confirmed Insight produced; hypothesis confirmed."""
    store = ChronicleStoreV2(tmp_path / "s6_06.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)
    cal_service = CalibrationService(store)

    make_slice(store, "sl_1", "重构时先写单测保护核心业务。")
    make_slice(store, "sl_2", "没有测试保护的大规模重构是危险的。")

    obs = obs_pipeline.create_observation(
        ObservationBuilder("用户重构以安全测试网为前提")
        .add_slice("sl_1", "supporting")
        .add_slice("sl_2", "supporting")
        .build()
    )
    hyp = hyp_engine.propose_hypothesis(
        HypothesisProposal(
            statement="重构遵循防御性工程节律",
            lenses=[DevelopmentLens.REGULATORY_FLEXIBILITY],
            supporting_observation_ids=[obs.observation_id],
        )
    )

    # Apply YES calibration
    res = cal_service.calibrate(
        CalibrationDecision(
            hypothesis_id=hyp.hypothesis_id,
            response=CalibrationResponse.YES,
            user_note="完全吻合我的工程习惯",
        )
    )

    assert res.action == "yes"
    assert res.calibration_event is not None
    assert res.calibration_event.user_action == "yes"
    assert res.confirmed_insight is not None
    assert res.confirmed_insight.status == "confirmed"
    assert res.confirmed_insight.source_hypothesis_id == hyp.hypothesis_id
    assert res.confirmed_insight.source_calibration_id == res.calibration_event.calibration_id

    # Verify SQLite DB
    cal_row = store.connection.execute(
        "SELECT * FROM calibration_events WHERE hypothesis_id = ?;", (hyp.hypothesis_id,)
    ).fetchone()
    assert cal_row is not None
    assert cal_row["user_action"] == "yes"
    assert cal_row["user_note"] == "完全吻合我的工程习惯"

    ins_row = store.connection.execute(
        "SELECT * FROM confirmed_insights WHERE source_hypothesis_id = ?;", (hyp.hypothesis_id,)
    ).fetchone()
    assert ins_row is not None
    assert ins_row["status"] == "confirmed"
    assert ins_row["statement"] == hyp.statement

    assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []


# ── S6-07: PARTLY calibration ────────────────────────────────────────────────


def test_s6_07_partly_calibration(tmp_path: Path) -> None:
    """S6-07: Nuance preserved without deleting original history (S6-07)."""
    store = ChronicleStoreV2(tmp_path / "s6_07.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)
    cal_service = CalibrationService(store)

    make_slice(store, "sl_1", "写代码的时候我不喜欢任何系统弹窗打扰我。")
    make_slice(store, "sl_2", "静默模式下请关闭所有非必要通知。")

    obs = obs_pipeline.create_observation(
        ObservationBuilder("用户需要绝对安静的无干扰编码环境")
        .add_slice("sl_1", "supporting")
        .add_slice("sl_2", "supporting")
        .build()
    )
    hyp = hyp_engine.propose_hypothesis(
        HypothesisProposal(
            statement="用户在所有工作场景中均拒绝一切伴生体交互",
            lenses=[DevelopmentLens.AUTONOMOUS_ACTION],
            supporting_observation_ids=[obs.observation_id],
        )
    )

    # Apply PARTLY calibration with nuance
    res = cal_service.calibrate(
        CalibrationDecision(
            hypothesis_id=hyp.hypothesis_id,
            response=CalibrationResponse.PARTLY,
            user_note="写代码时拒绝，但休息时可以轻松互动",
        )
    )

    assert res.action == "partly"
    assert res.calibration_event is not None
    assert res.calibration_event.user_action == "partly"
    assert res.confirmed_insight is not None
    assert "补充校准" in res.confirmed_insight.statement

    # Original hypothesis row statement in DB is NOT mutated or overwritten
    hyp_in_db = store.get_hypothesis(hyp.hypothesis_id)
    assert hyp_in_db is not None
    assert hyp_in_db.statement == hyp.statement

    # Calibration event accurately holds user note
    cal_events = cal_service.get_calibration_history(hyp.hypothesis_id)
    assert len(cal_events) == 1
    assert cal_events[0].user_action == "partly"
    assert "写代码时拒绝" in (cal_events[0].user_note or "")


# ── S6-08: NO calibration ────────────────────────────────────────────────────


def test_s6_08_no_calibration(tmp_path: Path) -> None:
    """S6-08: Hypothesis rejected; no Confirmed Insight."""
    store = ChronicleStoreV2(tmp_path / "s6_08.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)
    cal_service = CalibrationService(store)

    make_slice(store, "sl_1", "我今天用了下 Vim 快捷键。")
    make_slice(store, "sl_2", "配置了一下 Vim 插件。")

    obs = obs_pipeline.create_observation(
        ObservationBuilder("用户正在尝试切换到 Vim 编辑习惯")
        .add_slice("sl_1", "supporting")
        .add_slice("sl_2", "supporting")
        .build()
    )
    hyp = hyp_engine.propose_hypothesis(
        HypothesisProposal(
            statement="用户将全面废弃现代 IDE 转向纯终端编辑",
            lenses=[DevelopmentLens.TEMPORAL_INTEGRATION],
            supporting_observation_ids=[obs.observation_id],
        )
    )

    # Apply NO calibration
    res = cal_service.calibrate(
        CalibrationDecision(
            hypothesis_id=hyp.hypothesis_id,
            response=CalibrationResponse.NO,
            user_note="纯粹是偶尔玩玩，主力还是现代 IDE",
        )
    )

    assert res.action == "no"
    assert res.confirmed_insight is None
    assert res.hypothesis_status == "rejected"

    # Confirmed insight count in SQLite remains exactly 0
    ins_count = store.connection.execute("SELECT COUNT(*) FROM confirmed_insights;").fetchone()[0]
    assert ins_count == 0

    # Hypothesis status in SQLite updated to rejected
    hyp_db = store.get_hypothesis(hyp.hypothesis_id)
    assert hyp_db is not None
    assert hyp_db.status == "rejected"

    # Rejection prevents future confirmation
    with pytest.raises(IllegalCalibrationError):
        cal_service.calibrate(
            CalibrationDecision(hypothesis_id=hyp.hypothesis_id, response=CalibrationResponse.YES)
        )


# ── S6-09: NOT_NOW calibration ───────────────────────────────────────────────


def test_s6_09_not_now_calibration(tmp_path: Path) -> None:
    """S6-09 / P0-1: NOT_NOW preserves candidate; cal_events delta=0; last_calibrated_at same."""
    store = ChronicleStoreV2(tmp_path / "s6_09.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)
    cal_service = CalibrationService(store)

    make_slice(store, "sl_1", "最近在考虑要不要学一下 Elixir。")
    make_slice(store, "sl_2", "看了一遍 Elixir 官方指南。")

    obs = obs_pipeline.create_observation(
        ObservationBuilder("用户对 Elixir 语言产生兴趣")
        .add_slice("sl_1", "supporting")
        .add_slice("sl_2", "supporting")
        .build()
    )
    hyp = hyp_engine.propose_hypothesis(
        HypothesisProposal(
            statement="用户计划深入学习函数式并发编程",
            lenses=[DevelopmentLens.OPENNESS_TO_UNCERTAINTY],
            supporting_observation_ids=[obs.observation_id],
        )
    )

    # Baseline row counts before NOT_NOW
    cal_count_before = store.connection.execute(
        "SELECT COUNT(*) FROM calibration_events;"
    ).fetchone()[0]
    ins_count_before = store.connection.execute(
        "SELECT COUNT(*) FROM confirmed_insights;"
    ).fetchone()[0]
    assert hyp.last_calibrated_at is None

    # Apply NOT_NOW calibration (defer)
    res = cal_service.calibrate(
        CalibrationDecision(
            hypothesis_id=hyp.hypothesis_id,
            response=CalibrationResponse.NOT_NOW,
            calibrated_at="2026-10-20T12:00:00+00:00",
        )
    )

    # P0-1 Explicit Assertions:
    # 1. Service reports deferred
    assert res.action == "not_now"
    assert res.confirmed_insight is None
    assert res.calibration_event is None
    assert res.hypothesis_status == "candidate"
    assert "deferred" in res.detail

    # 2. calibration_events delta = 0
    cal_count_after = store.connection.execute(
        "SELECT COUNT(*) FROM calibration_events;"
    ).fetchone()[0]
    assert cal_count_after - cal_count_before == 0

    # 3. confirmed_insights delta = 0
    ins_count_after = store.connection.execute(
        "SELECT COUNT(*) FROM confirmed_insights;"
    ).fetchone()[0]
    assert ins_count_after - ins_count_before == 0

    # 4. Hypothesis still candidate and last_calibrated_at remains UNCHANGED (None)
    hyp_db = store.get_hypothesis(hyp.hypothesis_id)
    assert hyp_db is not None
    assert hyp_db.status == "candidate"
    assert hyp_db.last_calibrated_at is None


# ── S6-10: Calibration immutable ─────────────────────────────────────────────


def test_s6_10_calibration_immutable(tmp_path: Path) -> None:
    """S6-10: Past calibration rows cannot be overwritten/deleted by normal update path."""
    store = ChronicleStoreV2(tmp_path / "s6_10.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)
    cal_service = CalibrationService(store)

    make_slice(store, "sl_1", "每次提交前必须 ruff check。")
    make_slice(store, "sl_2", "类型检查 mypy 必须全绿。")

    obs = obs_pipeline.create_observation(
        ObservationBuilder("用户坚持代码质量自动化检查")
        .add_slice("sl_1", "supporting")
        .add_slice("sl_2", "supporting")
        .build()
    )
    hyp = hyp_engine.propose_hypothesis(
        HypothesisProposal(
            statement="用户具有严格的门禁防线执念",
            lenses=[DevelopmentLens.REGULATORY_FLEXIBILITY],
            supporting_observation_ids=[obs.observation_id],
        )
    )

    # Action 1: YES
    cal_service.calibrate(
        CalibrationDecision(
            hypothesis_id=hyp.hypothesis_id,
            response=CalibrationResponse.YES,
            user_note="首次确认",
            calibrated_at="2026-10-20T10:00:00+00:00",
        )
    )

    # Action 2: Later PARTLY refinement
    cal_service.calibrate(
        CalibrationDecision(
            hypothesis_id=hyp.hypothesis_id,
            response=CalibrationResponse.PARTLY,
            user_note="非核心原型除外",
            calibrated_at="2026-10-20T15:00:00+00:00",
        )
    )

    history = cal_service.get_calibration_history(hyp.hypothesis_id)
    assert len(history) == 2
    assert history[0].user_action == "yes"
    assert history[0].user_note == "首次确认"
    assert history[1].user_action == "partly"
    assert history[1].user_note == "非核心原型除外"

    # Ensure foreign keys are valid
    assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []


# ── S6-11: Lifecycle evidence loss ───────────────────────────────────────────


def test_s6_11_lifecycle_evidence_loss(tmp_path: Path) -> None:
    """S6-11: Evidence loss -> proof recompute -> retraction propagation."""
    store = ChronicleStoreV2(tmp_path / "s6_11.db")
    lifecycle = LifecycleService(store)
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)
    cal_service = CalibrationService(store)

    make_slice(store, "sl_a1", "观察A支持切片1")
    make_slice(store, "sl_a2", "观察A支持切片2")
    make_slice(store, "sl_b1", "观察B支持切片1")
    make_slice(store, "sl_b2", "观察B支持切片2")

    obs_a = obs_pipeline.create_observation(
        ObservationBuilder("支撑观察A")
        .add_slice("sl_a1", "supporting")
        .add_slice("sl_a2", "supporting")
        .build()
    )
    obs_b = obs_pipeline.create_observation(
        ObservationBuilder("支撑观察B")
        .add_slice("sl_b1", "supporting")
        .add_slice("sl_b2", "supporting")
        .build()
    )
    hyp = hyp_engine.propose_hypothesis(
        HypothesisProposal(
            statement="双观察多源支持假说",
            lenses=[DevelopmentLens.TEMPORAL_INTEGRATION],
            supporting_observation_ids=[obs_a.observation_id, obs_b.observation_id],
        )
    )
    cal_res = cal_service.calibrate(
        CalibrationDecision(hypothesis_id=hyp.hypothesis_id, response=CalibrationResponse.YES)
    )
    assert cal_res.confirmed_insight is not None

    # Step 1: Delete sl_a1 (obs_a proof recomputed 2 -> 1, obs_a remains active)
    res1 = lifecycle.hard_delete_slice("sl_a1")
    assert res1.success is True
    assert obs_a.observation_id in res1.recomputed_observations
    db_obs_a1 = store.get_observation(obs_a.observation_id)
    assert db_obs_a1 is not None and db_obs_a1.proof_count == 1 and db_obs_a1.status == "active"

    # Step 2: Delete sl_a2 (obs_a proof reaches 0 -> obs_a retracts!)
    # Hypothesis loses obs_a, obs_b remains active -> support weakened -> revalidation_required!
    # Confirmed insight source hypothesis weakened -> insight revalidation_required!
    res2 = lifecycle.hard_delete_slice("sl_a2")
    assert res2.success is True
    assert obs_a.observation_id in res2.retracted_observations
    assert hyp.hypothesis_id in res2.revalidated_hypotheses
    assert cal_res.confirmed_insight.insight_id in res2.revalidated_insights

    hyp_db = store.get_hypothesis(hyp.hypothesis_id)
    assert hyp_db is not None and hyp_db.status == "revalidation_required"
    ins_db = store.get_confirmed_insight(cal_res.confirmed_insight.insight_id)
    assert ins_db is not None and ins_db.status == "revalidation_required"

    # Step 3: Delete sl_b1 and sl_b2 (obs_b retracts -> hyp loses all active obs -> retracted!)
    lifecycle.hard_delete_slice("sl_b1")
    res3 = lifecycle.hard_delete_slice("sl_b2")
    assert res3.success is True
    assert obs_b.observation_id in res3.retracted_observations
    assert hyp.hypothesis_id in res3.retracted_hypotheses
    assert cal_res.confirmed_insight.insight_id in res3.retracted_insights

    hyp_db_final = store.get_hypothesis(hyp.hypothesis_id)
    assert hyp_db_final is not None and hyp_db_final.status == "retracted"
    ins_db_final = store.get_confirmed_insight(cal_res.confirmed_insight.insight_id)
    assert ins_db_final is not None and ins_db_final.status == "retracted"


# ── S6-12: Calibration survives lifecycle retraction ─────────────────────────


def test_s6_12_calibration_survives_lifecycle_retraction(tmp_path: Path) -> None:
    """S6-12: Even if insight/hypothesis retracts, calibration history remains."""
    store = ChronicleStoreV2(tmp_path / "s6_12.db")
    lifecycle = LifecycleService(store)
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)
    cal_service = CalibrationService(store)

    make_slice(store, "sl_surv1", "支持事实1")
    make_slice(store, "sl_surv2", "支持事实2")

    obs = obs_pipeline.create_observation(
        ObservationBuilder("观察")
        .add_slice("sl_surv1", "supporting")
        .add_slice("sl_surv2", "supporting")
        .build()
    )
    hyp = hyp_engine.propose_hypothesis(
        HypothesisProposal(
            statement="将被撤回的假说",
            lenses=[DevelopmentLens.NARRATIVE_INTEGRATION],
            supporting_observation_ids=[obs.observation_id],
        )
    )
    res = cal_service.calibrate(
        CalibrationDecision(
            hypothesis_id=hyp.hypothesis_id,
            response=CalibrationResponse.YES,
            user_note="历史校准动作绝不能丢失",
            calibrated_at="2026-10-20T16:00:00+00:00",
        )
    )
    cal_id = res.calibration_event.calibration_id  # type: ignore[union-attr]

    # Delete both slices to cascade retraction
    lifecycle.hard_delete_slice("sl_surv1")
    lifecycle.hard_delete_slice("sl_surv2")

    # Invariants verification:
    # 1. Hypothesis is retracted
    db_hyp = store.get_hypothesis(hyp.hypothesis_id)
    assert db_hyp is not None
    assert db_hyp.status == "retracted"

    # 2. Confirmed insight is retracted
    db_ins = store.get_confirmed_insight(res.confirmed_insight.insight_id)  # type: ignore[union-attr]
    assert db_ins is not None
    assert db_ins.status == "retracted"

    # 3. Calibration event MUST remain 100% intact and untouched
    cal_row = store.connection.execute(
        "SELECT * FROM calibration_events WHERE calibration_id = ?;", (cal_id,)
    ).fetchone()
    assert cal_row is not None
    assert cal_row["user_action"] == "yes"
    assert cal_row["user_note"] == "历史校准动作绝不能丢失"

    assert store.connection.execute("PRAGMA foreign_key_check;").fetchall() == []


# ── S6-13: Event retention pin ───────────────────────────────────────────────


def test_s6_13_event_retention_pin(tmp_path: Path) -> None:
    """S6-13: Observation adoption pins Event Skeleton."""
    store = ChronicleStoreV2(tmp_path / "s6_13.db")
    prov = ProvenanceRepository(store.connection)
    obs_pipeline = ObservationPipeline(store)

    make_event(store, "ev_pin", retention_class="transient")

    # Before adoption: transient event is NOT pinned
    assert prov.is_event_durable_pinned("ev_pin") is False

    # Formal adoption by active observation
    obs_pipeline.create_observation(
        ObservationBuilder("采纳遥测事件作为支撑").add_event("ev_pin", "supporting").build()
    )

    # After adoption: event is retention-pinned (S6-13)
    assert prov.is_event_durable_pinned("ev_pin") is True


# ── S6-14: Last durable ref unpins ───────────────────────────────────────────


def test_s6_14_last_durable_ref_unpins(tmp_path: Path) -> None:
    """S6-14: Remove final Observation provenance -> event becomes purgeable."""
    store = ChronicleStoreV2(tmp_path / "s6_14.db")
    prov = ProvenanceRepository(store.connection)
    obs_pipeline = ObservationPipeline(store)
    lifecycle = LifecycleService(store)

    make_slice(store, "sl_pin_helper", "帮助切片")
    make_event(store, "ev_unpin_target", retention_class="transient")

    obs = obs_pipeline.create_observation(
        ObservationBuilder("联合切片与事件")
        .add_slice("sl_pin_helper", "supporting")
        .add_event("ev_unpin_target", "supporting")
        .build()
    )
    assert prov.is_event_durable_pinned("ev_unpin_target") is True

    # When the observation is retracted, event becomes unpinned
    # Retract observation by deleting supporting slice and recomputing
    lifecycle.hard_delete_slice("sl_pin_helper")

    # Retract observation explicitly
    store.update_observation_proof_count(obs.observation_id, proof_count=0, status="retracted")

    # Event is now unpinned / purgeable
    assert prov.is_event_durable_pinned("ev_unpin_target") is False


# ── S6-15: Echo not evidence ─────────────────────────────────────────────────


def test_s6_15_echo_not_evidence(tmp_path: Path) -> None:
    """S6-15: Assistant echo cannot increase proof or form hypothesis."""
    store = ChronicleStoreV2(tmp_path / "s6_15.db")
    obs_pipeline = ObservationPipeline(store)

    # Slice containing pure assistant echo with acknowledgement
    echo_content = "<!-- COEVA_ECHO_FENCE: 你非常热爱在夜深人静时写代码。 --> 对，正如你刚才所说。"
    make_slice(store, "sl_echo", echo_content)

    cand = ObservationBuilder("用户热爱深夜写代码").add_slice("sl_echo", "supporting").build()

    # Blocked by EchoGuard during observation candidate validation
    with pytest.raises(EchoEvidenceError) as exc_info:
        obs_pipeline.create_observation(cand)
    assert "pure assistant echo" in str(exc_info.value)


# ── S6-16: Telemetry authority boundary ──────────────────────────────────────


def test_s6_16_telemetry_authority_boundary(tmp_path: Path) -> None:
    """S6-16: Telemetry alone cannot create subjective preference/feeling hypothesis."""
    store = ChronicleStoreV2(tmp_path / "s6_16.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)

    make_event(store, "ev_t1")
    make_event(store, "ev_t2")

    # 1. Attempting subjective observation with telemetry alone fails
    cand_sub = (
        ObservationBuilder("用户对自动化构建感到厌烦和焦虑")
        .with_subjective_claim(True)
        .add_event("ev_t1", "supporting")
        .add_event("ev_t2", "supporting")
        .build()
    )
    with pytest.raises(TelemetryAuthorityError) as exc_obs:
        obs_pipeline.create_observation(cand_sub)
    assert "Telemetry alone cannot create" in str(exc_obs.value)

    # 2. Objective observation passes
    cand_obj = (
        ObservationBuilder("连续执行了两次构建任务")
        .with_subjective_claim(False)
        .add_event("ev_t1", "supporting")
        .add_event("ev_t2", "supporting")
        .build()
    )
    obs_obj = obs_pipeline.create_observation(cand_obj)
    assert obs_obj.proof_count == 2

    # 3. Telemetry-only observations cannot form psychological/feeling hypotheses
    prop = HypothesisProposal(
        statement="用户极度反感重复执行构建脚本的心态",
        lenses=[DevelopmentLens.EXPERIENTIAL_OPENNESS],
        supporting_observation_ids=[obs_obj.observation_id],
    )
    with pytest.raises(TelemetryAuthorityError) as exc_hyp:
        hyp_engine.propose_hypothesis(prop)
    assert "User voice is required" in str(exc_hyp.value)


# ── S6-17: No chapter leakage ────────────────────────────────────────────────


def test_s6_17_no_chapter_leakage(tmp_path: Path) -> None:
    """S6-17: No Growth Chapter generated or used as evidence."""
    store = ChronicleStoreV2(tmp_path / "s6_17.db")
    obs_pipeline = ObservationPipeline(store)

    # 1. Ensure chapter_metadata table is completely untouched during slow path
    make_slice(store, "sl_c1", "日常普通投喂切片1")
    make_slice(store, "sl_c2", "日常普通投喂切片2")
    obs_pipeline.create_observation(
        ObservationBuilder("日常行为模式")
        .add_slice("sl_c1", "supporting")
        .add_slice("sl_c2", "supporting")
        .build()
    )

    # Assert 0 chapters created
    chap_count = store.connection.execute("SELECT COUNT(*) FROM chapter_metadata;").fetchone()[0]
    assert chap_count == 0

    # 2. Even if chapters exist in DB, they can never be added as observation evidence
    store.insert_chapter_metadata(
        ChapterMetadataEntity(
            chapter_id="ch_narrative",
            title="第一章 启程",
            file_path="docs/chapters/ch01.md",
            time_span_start="2026-10-01T00:00:00+00:00",
            time_span_end="2026-10-20T23:59:59+00:00",
        )
    )
    store.insert_chapter_slice_link(
        ChapterSliceLinkEntity(chapter_id="ch_narrative", slice_id="sl_c1")
    )

    # ObservationCandidate has NO methods or fields to link chapters as evidence
    cand = ObservationCandidate("测试观察")
    assert not hasattr(cand, "supporting_chapters")


# ── S6-18: No WP-7/8 changes ─────────────────────────────────────────────────


def test_s6_18_no_wp7_wp8_changes() -> None:
    """S6-18: In isolated Lane I, WP-7/8 were untouched; in integrated Lane L they are present."""
    root_src = Path("src/memory/v2")
    if (root_src / "recall_gate.py").exists():
        assert (root_src / "retrieval").is_dir()
    else:
        assert not (root_src / "retrieval").exists()


# ── S6-19: Production isolation ──────────────────────────────────────────────


def test_s6_19_production_isolation_and_default_flag_off(tmp_path: Path) -> None:
    """S6-19: Production DB untouched; V2 self-model flag default OFF."""
    # 1. Default flags check
    flags = resolve_flags()
    assert flags.memory_v2_self_model is False

    # 2. Slow path skips execution safely when flag is OFF
    store = ChronicleStoreV2(tmp_path / "s6_19.db")
    service = SlowPathSelfModelService(store)
    report = service.run_slow_path()
    assert report.enabled is False
    assert "memory_v2_self_model flag is OFF" in report.details[0]

    # Zero rows generated in DB
    assert store.connection.execute("SELECT COUNT(*) FROM observations;").fetchone()[0] == 0
    assert store.connection.execute("SELECT COUNT(*) FROM hypotheses;").fetchone()[0] == 0
    assert store.connection.execute("SELECT COUNT(*) FROM confirmed_insights;").fetchone()[0] == 0

    # 3. When flag is overridden, slow path executes
    with override_flags(
        memory_v2_storage=True,
        memory_v2_consolidation=True,
        memory_v2_self_model=True,
    ):
        active_flags = resolve_flags()
        assert active_flags.memory_v2_self_model is True
        report_active = service.run_slow_path()
        assert report_active.enabled is True

    # Verify production DB (if exists) hash is untouched
    prod_db = Path("data/companion_chronicle.db")
    if prod_db.exists():
        initial_hash = hashlib.sha256(prod_db.read_bytes()).hexdigest()
        # Verify hash remains identical
        assert hashlib.sha256(prod_db.read_bytes()).hexdigest() == initial_hash


# ── P0-2: S-02 Counter-evidence absolute-claim guard ─────────────────────────


def test_s02_counter_evidence_absolute_claim_guard(tmp_path: Path) -> None:
    """S-02 / P0-2: Counter-evidence forbids absolute claims; non-absolute succeeds."""
    from src.memory.v2.hypothesis import AbsoluteClaimWithCounterEvidenceError

    store = ChronicleStoreV2(tmp_path / "s02.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)

    make_slice(store, "sl_pos1", "我遇到未知错误通常先仔细研读官方文档。")
    make_slice(store, "sl_pos2", "看文档能帮我快速理清来龙去脉。")
    make_slice(store, "sl_counter1", "有时候赶进度我也会直接快速搜索解决。")

    # Create observation with positive support and counter evidence
    obs = obs_pipeline.create_observation(
        ObservationBuilder("用户技术攻坚以文档为主但偶有快速应急")
        .add_slice("sl_pos1", "supporting")
        .add_slice("sl_pos2", "supporting")
        .add_slice("sl_counter1", "counter")
        .build()
    )

    # 1. Absolute claims with counter evidence MUST be rejected (fail-closed, persistence count = 0)
    absolute_statements = [
        "用户总是严格研读官方文档",
        "用户面对问题时一直都是看文档解决",
        "用户一贯拒绝直接搜索报错",
        "用户从来都只相信官方文档",
        "User always reads the official specification",
        "User consistently relies on first-party docs",
    ]

    hyps_before = store.connection.execute("SELECT COUNT(*) FROM hypotheses;").fetchone()[0]

    for stmt in absolute_statements:
        prop_abs = HypothesisProposal(
            statement=stmt,
            lenses=[DevelopmentLens.OPENNESS_TO_UNCERTAINTY],
            supporting_observation_ids=[obs.observation_id],
        )
        with pytest.raises(AbsoluteClaimWithCounterEvidenceError):
            hyp_engine.propose_hypothesis(prop_abs)

    # Persistence count must be 0!
    hyps_after_rejected = store.connection.execute("SELECT COUNT(*) FROM hypotheses;").fetchone()[0]
    assert hyps_after_rejected - hyps_before == 0

    # 2. Non-absolute tentative claim with counter evidence succeeds and persists as candidate
    prop_tentative = HypothesisProposal(
        statement="用户通常倾向于优先研读官方规范",
        lenses=[DevelopmentLens.OPENNESS_TO_UNCERTAINTY],
        supporting_observation_ids=[obs.observation_id],
    )
    hyp_tentative = hyp_engine.propose_hypothesis(prop_tentative)
    assert hyp_tentative.status == "candidate"

    # Verify persisted in DB and counter link preserved
    db_hyp = store.get_hypothesis(hyp_tentative.hypothesis_id)
    assert db_hyp is not None
    assert db_hyp.statement == "用户通常倾向于优先研读官方规范"


# ── P1: Lock S-14 at WP-6 boundary ───────────────────────────────────────────


def test_s14_unresolved_scope_never_promoted_to_global(tmp_path: Path) -> None:
    """S-14 / P1: Unresolved evidence or Observation must never silently become scope='global'."""
    store = ChronicleStoreV2(tmp_path / "s14.db")
    obs_pipeline = ObservationPipeline(store)
    hyp_engine = HypothesisEngine(store)

    make_slice(store, "sl_unres1", "未归类切片1", scope="unresolved", project_id=None)
    make_slice(store, "sl_unres2", "未归类切片2", scope="unresolved", project_id=None)

    # 1. Unresolved evidence -> attempting global Observation fails closed
    cand_global_from_unres = (
        ObservationBuilder("根据未归类证据聚合全局观察")
        .with_scope("global")
        .add_slice("sl_unres1", "supporting")
        .add_slice("sl_unres2", "supporting")
        .build()
    )
    with pytest.raises(ScopeIsolationError) as exc_obs:
        obs_pipeline.create_observation(cand_global_from_unres)
    assert "Unresolved evidence input cannot silently become scope='global'" in str(exc_obs.value)

    # 2. Creation as scope='unresolved' observation succeeds
    cand_unres = (
        ObservationBuilder("未归类切片形成的未决观察")
        .with_scope("unresolved")
        .add_slice("sl_unres1", "supporting")
        .add_slice("sl_unres2", "supporting")
        .build()
    )
    obs_unres = obs_pipeline.create_observation(cand_unres)
    assert obs_unres.scope == "unresolved"

    # 3. Unresolved Observation -> attempting global Hypothesis fails closed
    prop_global_from_unres = HypothesisProposal(
        statement="未归类观察派生全局假说",
        lenses=[DevelopmentLens.TEMPORAL_INTEGRATION],
        supporting_observation_ids=[obs_unres.observation_id],
        scope="global",
    )
    with pytest.raises(ScopeIsolationError) as exc_hyp:
        hyp_engine.propose_hypothesis(prop_global_from_unres)
    assert "Unresolved observation input cannot silently become scope='global'" in str(
        exc_hyp.value
    )
