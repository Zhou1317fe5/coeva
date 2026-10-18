"""Admission Filter for Memory V2.1 Lane C.

Determines whether an incoming Raw Slice or Event Skeleton possesses
Durable Semantic Value for long-term retention.

Follows Frozen Consolidation Design & Epistemic Rules:
- NO blanket rejection of casual chat.
- Rejects low-entropy noise, transient operational status, third-person quotes,
  connector replays, and pure echo parroting.
- S-01: Single emotional complaints or transient bad states do NOT create durable semantic claims.
"""

from __future__ import annotations

import re
from typing import Any

from src.memory.v2.echo_guard import EchoGuard
from src.memory.v2.entities import EventSkeletonEntity, RawSliceEntity
from src.memory.v2.proposals import AdmissionDecision

# Patterns for low-entropy greetings & UI chatter
LOW_ENTROPY_PATTERNS = [
    re.compile(
        r"^(?:hi|hello|hey|你好|早安|早啊|晚上好|中午好|"
        r"测试|测试气泡|气泡测试|test|123|在吗|哈喽)[!！.。~ ]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:好的|好滴|收到|行|ok|k|yes|嗯嗯|嗯|嗯嗯好的|嗯好的|知道了)[!！.。~ ]*$",
        re.IGNORECASE,
    ),
]

# Ephemeral operational commands or short-lived daily status
TRANSIENT_STATUS_PATTERNS = [
    re.compile(
        r"(?:去吃(?:个)?(?:早|午|晚)?饭|吃(?:早|午|晚)饭|点外卖|去趟洗手间|去喝口水|休息半小时|睡个觉)"
    ),
    re.compile(r"(?:半小时后回来|一会儿回来|马上回来|离开一下|稍等一下)"),
    re.compile(r"(?:这次.*先临时别|临时先别|先别加|跑通就行|先把窗口关掉|放大一点)"),
]

# Third-person quote / attribution (not the user's own durable belief)
THIRD_PERSON_PATTERNS = [
    re.compile(r"(?:我室友说|我同事说|我朋友说|有人说|他觉得|她说|他们觉得|领导说|网上说)"),
    re.compile(r"(?:他极度讨厌|她极度讨厌|别人觉得)"),
]

# Single emotional complaints / ephemeral fatigue (S-01 guard)
EMOTIONAL_COMPLAINT_PATTERNS = [
    re.compile(r"(?:心力特别交瘁|完全不想动了|今天好累|烦死了|不想写代码|头好痛|崩溃了|太难受了)"),
]

# Durable indicators (carry lasting value even in informal/casual tone)
DURABLE_INDICATORS = [
    # Preferences & habits
    re.compile(r"(?:全面迁移到|不再用|换成了|坚持用|偏好|更喜欢|习惯于|只喜欢|不喜欢|倾向于)"),
    # Relationship rules & boundaries
    re.compile(r"(?:千万别|别在(?:我|专注)|请严肃打断|提醒我|以后我|以后别|请不要|一定要)"),
    # Enduring facts / tech stack
    re.compile(r"(?:我们用|主显示器|显卡|架构|重构为|决定采用|项目用的是|其实是.*不是|其实不是)"),
    # Retrospective biographical or deep realization
    re.compile(r"(?:小时候其实|我发现自己最近总是|事实证明|经过几个月|在任何项目里)"),
    # Conditional / explicit boundaries
    re.compile(r"(?:做实验代码时.*但做产品|科研实验.*生产架构|单文件.*不过)"),
]


class AdmissionFilter:
    """Evaluates whether raw evidence is eligible for long-term semantic extraction."""

    def __init__(self, echo_guard: EchoGuard | None = None) -> None:
        self.echo_guard = echo_guard or EchoGuard()

    def evaluate_slice(
        self,
        slice_entity: RawSliceEntity,
        echoed_proposition: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AdmissionDecision:
        """Evaluate an incoming Raw User Slice."""
        content = slice_entity.content.strip()
        # 0. Check duplicate transport / ingestion dedup key collision (DEV_B)
        if context and (
            context.get("existing_key_matched")
            or context.get("is_replay")
            or context.get("is_duplicate")
        ):
            return AdmissionDecision(
                decision="NOOP_LONG_TERM",
                rationale="Duplicate transport / ingestion dedup key collision (DEV_B).",
                rejection_category="duplicate_transport",
            )

        # 1. Check Echo Guard
        echo_prop = echoed_proposition
        if not echo_prop and context and "echoed_proposition" in context:
            echo_prop = str(context["echoed_proposition"])

        echo_res = self.echo_guard.inspect(content, echo_prop)
        if echo_res.has_echo_context and echo_res.is_pure_echo:
            return AdmissionDecision(
                decision="NOOP_LONG_TERM",
                rationale=echo_res.rationale,
                rejection_category="echo_parrot",
            )

        # Work on the effective delta if echo was isolated
        if echo_res.has_echo_context and echo_res.delta_text:
            eval_text = echo_res.delta_text
        else:
            eval_text = content

        # 2. Check Low Entropy / Empty
        if not eval_text or any(p.match(eval_text) for p in LOW_ENTROPY_PATTERNS):
            return AdmissionDecision(
                decision="NOOP_LONG_TERM",
                rationale="Low-entropy noise, greeting, or pure conversational acknowledgement.",
                rejection_category="low_entropy",
            )

        # 3. Third-person quote filter (HOLD_02)
        if any(p.search(eval_text) for p in THIRD_PERSON_PATTERNS):
            if not any(
                marker in eval_text for marker in ["我赞同", "我也觉得", "但我觉得", "我不认同"]
            ):
                return AdmissionDecision(
                    decision="NOOP_LONG_TERM",
                    rationale="Third-person quote without user self-adoption.",
                    rejection_category="third_person_quote",
                )

        # 4. Single emotional / fatigue complaint (S-01 / HOLD_15)
        if any(p.search(eval_text) for p in EMOTIONAL_COMPLAINT_PATTERNS):
            if not any(p.search(eval_text) for p in DURABLE_INDICATORS):
                return AdmissionDecision(
                    decision="NOOP_LONG_TERM",
                    rationale="Single raw slice transient fatigue complaint (S-01 guard).",
                    rejection_category="single_emotional_complaint",
                )

        # 5. Transient operational commands or short-lived schedule (DEV_G / HOLD_04)
        if any(p.search(eval_text) for p in TRANSIENT_STATUS_PATTERNS):
            if not any(p.search(eval_text) for p in DURABLE_INDICATORS):
                return AdmissionDecision(
                    decision="NOOP_LONG_TERM",
                    rationale="Ephemeral operational status without lasting semantic value.",
                    rejection_category="transient_status",
                )

        # 6. Check for durable semantic indicators or substantial self-disclosure
        if any(p.search(eval_text) for p in DURABLE_INDICATORS):
            return AdmissionDecision(
                decision="ADMIT",
                rationale="Contains durable semantic indicators (preference, rule, or fact).",
            )

        # 7. Substantial content check for casual sentences with durable value
        if len(eval_text) >= 10:
            return AdmissionDecision(
                decision="ADMIT",
                rationale="Substantial self-authored statement with potential durable value.",
            )

        # Default fallback for short ambiguous fragments
        return AdmissionDecision(
            decision="DEFER",
            rationale="Short context-dependent fragment deferred for session context aggregation.",
            rejection_category="ambiguous_fragment",
        )

    def evaluate_event(
        self,
        event_entity: EventSkeletonEntity,
        is_replay: bool = False,
        context: dict[str, Any] | None = None,
    ) -> AdmissionDecision:
        """Evaluate an incoming Agent Event Skeleton."""
        replay_flag = is_replay
        if not replay_flag and context and context.get("is_replay"):
            replay_flag = True

        if replay_flag:
            return AdmissionDecision(
                decision="NOOP_LONG_TERM",
                rationale="External connector replay or duplicate telemetry event.",
                rejection_category="replay",
            )

        return AdmissionDecision(
            decision="NOOP_LONG_TERM",
            rationale="Agent telemetry event retained as evidence, does not spawn claims directly.",
            rejection_category="telemetry_skeleton",
        )
