"""Tests for Admission Filter & Benchmark Subsets (Lane C).

Covers:
- Low-entropy noise rejection
- Ephemeral / transient status rejection (A-05)
- Third-person quote rejection
- Single emotional complaint rejection (A-07 / S-01)
- Casual wording carrying durable value (A-06)
- Event skeleton admission & connector replay rejection
- Relevant Frozen DEV benchmark cases (A-14)
- Relevant Frozen HOLDOUT benchmark cases (A-15)
"""

from __future__ import annotations

import json
from pathlib import Path

from src.memory.v2.admission import AdmissionFilter
from src.memory.v2.entities import EventSkeletonEntity, RawSliceEntity


def create_slice(
    content: str,
    slice_id: str = "slice_test_01",
    project_id: str | None = None,
    occurred_at: str = "2026-10-18T12:00:00+00:00",
) -> RawSliceEntity:
    return RawSliceEntity(
        slice_id=slice_id,
        content=content,
        occurred_at=occurred_at,
        actor="user",
        source="manual_feed",
        project_id=project_id,
    )


def test_low_entropy_rejection() -> None:
    filter_ = AdmissionFilter()
    for greeting in ["hi", "你好", "测试气泡", "早安", "嗯嗯好的", "123", "ok"]:
        decision = filter_.evaluate_slice(create_slice(greeting))
        assert decision.decision == "NOOP_LONG_TERM"
        assert decision.rejection_category == "low_entropy"


def test_transient_status_rejection() -> None:
    filter_ = AdmissionFilter()
    for transient in [
        "先去吃个午饭，半小时后回来。",
        "这次演示 demo 先临时别加复杂的错误重试逻辑了，跑通就行。",
        "去喝口水稍等一下",
    ]:
        decision = filter_.evaluate_slice(create_slice(transient))
        assert decision.decision == "NOOP_LONG_TERM"
        assert decision.rejection_category == "transient_status"


def test_third_person_quote_rejection() -> None:
    filter_ = AdmissionFilter()
    quote = "我室友说他极度讨厌 React，觉得 JSX 语法反人类。"
    decision = filter_.evaluate_slice(create_slice(quote))
    assert decision.decision == "NOOP_LONG_TERM"
    assert decision.rejection_category == "third_person_quote"


def test_single_emotional_complaint_rejection() -> None:
    filter_ = AdmissionFilter()
    complaint = "今天写代码感觉心力特别交瘁，完全不想动了。"
    decision = filter_.evaluate_slice(create_slice(complaint))
    assert decision.decision == "NOOP_LONG_TERM"
    assert decision.rejection_category == "single_emotional_complaint"


def test_casual_wording_with_durable_value_accepted() -> None:
    filter_ = AdmissionFilter()
    # Casual wording that must NOT be blanketly rejected (A-06)
    casual_slices = [
        "小时候其实挺喜欢画画的，后来才学的计算机。",
        "顺便说下，这台 4K 144Hz LG 显示器打代码确实比旧的舒服多了。",
        "我发现自己最近总是在晚上才真正进入深度专注状态。",
    ]
    for text in casual_slices:
        decision = filter_.evaluate_slice(create_slice(text))
        assert decision.decision == "ADMIT", f"Expected ADMIT for: {text}"


def test_relationship_rules_accepted() -> None:
    filter_ = AdmissionFilter()
    rule_slice = create_slice("以后我专注写代码时，千万别弹窗打扰我或提醒我喝水。")
    decision = filter_.evaluate_slice(rule_slice)
    assert decision.decision == "ADMIT"


def test_connector_replay_event_rejected() -> None:
    filter_ = AdmissionFilter()
    event = EventSkeletonEntity(
        event_id="evt_replay_01",
        occurred_at="2026-10-18T12:00:00+00:00",
        agent_id="test_agent",
        session_id="sess_104",
        event_type="tool_failure",
    )
    decision = filter_.evaluate_event(event, is_replay=True)
    assert decision.decision == "NOOP_LONG_TERM"
    assert decision.rejection_category == "replay"


def test_telemetry_event_admitted_as_evidence_only() -> None:
    filter_ = AdmissionFilter()
    event = EventSkeletonEntity(
        event_id="evt_01",
        occurred_at="2026-10-18T12:00:00+00:00",
        agent_id="test_agent",
        session_id="sess_104",
        event_type="tool_execution",
    )
    decision = filter_.evaluate_event(event, is_replay=False)
    assert decision.decision == "NOOP_LONG_TERM"
    assert decision.rejection_category == "telemetry_skeleton"


def test_frozen_dev_benchmark_admission_subset() -> None:
    """A-14: Verify admission matches frozen labels on DEV benchmark cases."""
    cases_path = Path("docs/memory-v2/consolidation/consolidation-benchmark-cases.json")
    assert cases_path.exists()
    cases_data = json.loads(cases_path.read_text(encoding="utf-8"))
    dev_set = cases_data["dev_set"]

    filter_ = AdmissionFilter()

    for case in dev_set:
        case_id = case["id"]
        expected_admission = case["expected_admission"]

        if "input_slice" in case:
            slice_data = case["input_slice"]
            slice_entity = RawSliceEntity(
                slice_id=slice_data["id"],
                content=slice_data["content"],
                occurred_at=slice_data.get("occurred_at", "2026-10-18T12:00:00+00:00"),
                actor=slice_data.get("actor", "user"),
                source=slice_data.get("source", "manual_feed"),
                project_id=slice_data.get("project_id"),
            )
            echo_prop = slice_data.get("echoed_proposition")
            context = {"echoed_proposition": echo_prop} if echo_prop else {}
            if case.get("existing_key_matched"):
                # Duplicate transport / ingestion key match
                decision = filter_.evaluate_slice(
                    slice_entity,
                    context={"is_replay": True},
                )
                # DEV_B dup transport directly maps to NOOP_LONG_TERM
                assert decision.decision == expected_admission, f"Failed case {case_id}"
                continue

            decision = filter_.evaluate_slice(
                slice_entity,
                echoed_proposition=echo_prop,
                context=context,
            )
            assert decision.decision == expected_admission, (
                f"Failed case {case_id}: got {decision.decision}"
            )

        elif "input_event" in case:
            event_data = case["input_event"]
            event_entity = EventSkeletonEntity(
                event_id=event_data["event_id"],
                occurred_at="2026-10-18T12:00:00+00:00",
                agent_id="agent_01",
                session_id=event_data.get("session_id", "sess_01"),
                event_type=event_data.get("event_type", "generic"),
            )
            decision = filter_.evaluate_event(
                event_entity,
                is_replay=bool(event_data.get("is_replay")),
            )
            assert decision.decision == expected_admission, f"Failed case {case_id}"


def test_frozen_holdout_benchmark_admission_subset() -> None:
    """A-15: Verify admission matches frozen labels on HOLDOUT benchmark cases without tuning."""
    cases_path = Path("docs/memory-v2/consolidation/consolidation-benchmark-cases.json")
    cases_data = json.loads(cases_path.read_text(encoding="utf-8"))
    holdout_set = cases_data["holdout_set"]

    filter_ = AdmissionFilter()

    for case in holdout_set:
        case_id = case["id"]
        expected_admission = case["expected_admission"]

        if "input_slice" in case:
            slice_data = case["input_slice"]
            slice_entity = RawSliceEntity(
                slice_id=slice_data["id"],
                content=slice_data["content"],
                occurred_at=slice_data.get("occurred_at", "2026-10-18T12:00:00+00:00"),
                actor=slice_data.get("actor", "user"),
                source=slice_data.get("source", "manual_feed"),
                project_id=slice_data.get("project_id"),
            )
            echo_prop = slice_data.get("echoed_proposition")
            context = {"echoed_proposition": echo_prop} if echo_prop else {}

            decision = filter_.evaluate_slice(
                slice_entity,
                echoed_proposition=echo_prop,
                context=context,
            )
            assert decision.decision == expected_admission, (
                f"Failed holdout {case_id}: got {decision.decision}"
            )

        elif "input_event" in case:
            event_data = case["input_event"]
            event_entity = EventSkeletonEntity(
                event_id=event_data["event_id"],
                occurred_at="2026-10-18T12:00:00+00:00",
                agent_id="agent_01",
                session_id=event_data.get("session_id", "sess_01"),
                event_type="test_event",
            )
            decision = filter_.evaluate_event(
                event_entity,
                is_replay=bool(event_data.get("is_replay")),
            )
            assert decision.decision == expected_admission, f"Failed holdout {case_id}"
