"""Unit tests for Phase 2C Shared Self Model, Calibration, and Active Growth Themes."""

from __future__ import annotations

from pathlib import Path

from src.core.hypotheses import (
    ConfidenceLevel,
    DevelopmentHypothesis,
    DevelopmentLens,
    HypothesisStatus,
)
from src.core.self_model import (
    CalibrationResponse,
    ConfirmedInsight,
    GrowthTheme,
    InsightStatus,
    SelfModelManager,
    ThemeStatus,
)
from src.memory.store import ChronicleStore


def _sample_hypothesis() -> DevelopmentHypothesis:
    return DevelopmentHypothesis(
        hypothesis_id="hyp_test_01",
        statement="面对报错摩擦时，倾向于主动缩小任务边界。",
        lenses=(DevelopmentLens.REGULATORY_FLEXIBILITY,),
        supporting_patterns=("pat_friction",),
        supporting_episodes=("ep_1", "ep_2"),
        counter_episodes=("ep_3",),
        confidence=ConfidenceLevel.MODERATE,
        status=HypothesisStatus.CANDIDATE,
        created_at="2026-10-16",
    )


def test_calibration_yes_promotes_to_confirmed_insight() -> None:
    """User YES: Hypothesis becomes confirmed, and a ConfirmedInsight is spawned."""
    mgr = SelfModelManager()
    hyp = _sample_hypothesis()

    updated_hyp, insight, revised = mgr.apply_calibration(
        hyp,
        CalibrationResponse.YES,
        user_comment="确实如此，我最近开始更理智了",
        today="2026-10-16",
    )

    assert updated_hyp.status == HypothesisStatus.CONFIRMED
    assert revised is None
    assert insight is not None
    assert insight.insight_id == "ins_hyp_test_01"
    assert insight.statement == hyp.statement
    assert insight.status == InsightStatus.ACTIVE
    assert "更理智了" in insight.user_confirmation_text


def test_calibration_partly_spawns_revised_hypothesis() -> None:
    """User PARTLY: Original becomes calibrating, spawns a new revised candidate."""
    mgr = SelfModelManager()
    hyp = _sample_hypothesis()

    updated_hyp, insight, revised = mgr.apply_calibration(
        hyp,
        CalibrationResponse.PARTLY,
        user_comment="仅在工作日白天成立，深夜还是容易上头",
        today="2026-10-16",
    )

    assert updated_hyp.status == HypothesisStatus.CALIBRATING
    assert insight is None
    assert revised is not None
    assert revised.status == HypothesisStatus.CANDIDATE
    assert revised.hypothesis_id == "hyp_test_01_revised"
    assert "白天成立" in revised.statement


def test_calibration_no_rejects_hypothesis_permanently() -> None:
    """User NO: Hypothesis marked rejected, no insight created."""
    mgr = SelfModelManager()
    hyp = _sample_hypothesis()

    updated_hyp, insight, revised = mgr.apply_calibration(
        hyp,
        CalibrationResponse.NO,
    )

    assert updated_hyp.status == HypothesisStatus.REJECTED
    assert insight is None
    assert revised is None


def test_calibration_not_now_preserves_candidate() -> None:
    """SPEC 14: Silence is not consent. NOT_NOW keeps hypothesis as candidate."""
    mgr = SelfModelManager()
    hyp = _sample_hypothesis()

    updated_hyp, insight, revised = mgr.apply_calibration(
        hyp,
        CalibrationResponse.NOT_NOW,
    )

    assert updated_hyp.status == HypothesisStatus.CANDIDATE
    assert insight is None
    assert revised is None


def test_insight_retirement_lifecycle() -> None:
    """SPEC 16: Users outgrow past models; retired insights become historical footprints."""
    mgr = SelfModelManager()
    insight = ConfirmedInsight(
        insight_id="ins_01",
        statement="过去很难让未完成的事情过夜。",
        lenses=(DevelopmentLens.OPENNESS_TO_UNCERTAINTY,),
        supporting_patterns=("pat_old",),
        user_confirmation_text="早期确认",
        status=InsightStatus.ACTIVE,
    )

    retired = mgr.retire_insight(insight, reason="近期数据显示已自然接纳未闭环状态")
    assert retired.status == InsightStatus.RETIRED
    assert "已退休" in retired.user_confirmation_text
    assert retired.statement == insight.statement


def test_growth_theme_quota_guard() -> None:
    """SPEC 17: Max 1-3 active themes at a time."""
    mgr = SelfModelManager()
    themes = [
        GrowthTheme(theme_id="t1", title="主题1", lens=DevelopmentLens.TEMPORAL_INTEGRATION),
        GrowthTheme(theme_id="t2", title="主题2", lens=DevelopmentLens.OPENNESS_TO_UNCERTAINTY),
    ]
    assert mgr.validate_active_theme_quota(themes) is True

    # 3 active themes -> quota reached
    themes.append(
        GrowthTheme(theme_id="t3", title="主题3", lens=DevelopmentLens.REGULATORY_FLEXIBILITY)
    )
    assert mgr.validate_active_theme_quota(themes) is False

    # Completed or paused themes do not consume quota
    themes_with_completed = [
        GrowthTheme(theme_id="t1", title="主题1", lens=DevelopmentLens.TEMPORAL_INTEGRATION),
        GrowthTheme(
            theme_id="t2",
            title="主题2",
            lens=DevelopmentLens.OPENNESS_TO_UNCERTAINTY,
            status=ThemeStatus.COMPLETED,
        ),
    ]
    assert mgr.validate_active_theme_quota(themes_with_completed) is True


def test_store_self_model_persistence_roundtrip() -> None:
    """End-to-end SQLite persistence of hypotheses, insights, and growth themes."""
    store = ChronicleStore(Path(":memory:"))
    hyp = _sample_hypothesis()
    store.save_hypothesis(hyp)

    # 1. Hypotheses
    loaded_hyps = store.list_hypotheses()
    assert len(loaded_hyps) == 1
    assert loaded_hyps[0].hypothesis_id == "hyp_test_01"
    assert loaded_hyps[0].status == HypothesisStatus.CANDIDATE
    assert loaded_hyps[0].lenses == (DevelopmentLens.REGULATORY_FLEXIBILITY,)

    # 2. Insights
    insight = ConfirmedInsight(
        insight_id="ins_01",
        statement="能够理智止损。",
        lenses=(DevelopmentLens.REGULATORY_FLEXIBILITY,),
        supporting_patterns=("pat_01",),
        user_confirmation_text="确实",
    )
    store.save_insight(insight)
    assert len(store.list_insights()) == 1
    assert store.list_insights(status=InsightStatus.ACTIVE)[0].statement == "能够理智止损。"
    assert store.list_insights(status=InsightStatus.RETIRED) == []

    # 3. Growth Themes
    theme = GrowthTheme(
        theme_id="theme_01",
        title="允许事情留到明天",
        lens=DevelopmentLens.OPENNESS_TO_UNCERTAINTY,
        statement="聚焦在未完成任务上的焦虑脱敏",
    )
    store.save_theme(theme)
    assert len(store.list_themes()) == 1
    assert store.list_themes(status=ThemeStatus.ACTIVE)[0].title == "允许事情留到明天"

    store.close()
