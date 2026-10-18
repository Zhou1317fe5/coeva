"""Stage 1: Intent Resolution and Precedence Fast-Gate.

Authoritative mapping to:
- docs/memory-v2/retrieval/technical-retrieval-design.md (§7 Fast-Gate Precedence)
- docs/memory-v2/retrieval/retrieval-decision-record.md (Decision 1, Decision 5)

Precedence Order:
1. Privacy eligibility (IMPL-3)
2. Current task continuity ("和上次一样" / "又是刚才那个报错") -> ALLOW even under Sanctuary!
3. Sanctuary reflective block -> BLOCK reflective/self-model/past frustration
4. Explicit historical intent ("之前/曾经/以前") -> BEATS generic QA
5. Personal preference / relationship rule
6. Narrative intent
7. Generic QA fallback ("怎么排序/天气/量子力学" -> early return NO_MEMORY)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.memory.v2.retrieval.models import RetrievalQueryContext


@dataclass(frozen=True)
class IntentResolutionResult:
    """Outcome of intent resolution and early gating."""

    mode: str
    is_continuity: bool
    is_past_query: bool
    is_rule_query: bool
    is_narrative_query: bool
    is_reflective_query: bool
    is_yesterday: bool
    should_early_terminate: bool = False
    early_termination_reason: str = ""


# Regular expressions for generic QA and chit-chat that have no personal memory intent
GENERIC_QA_PATTERNS: tuple[str, ...] = (
    r"怎么(?:排序|实现|使用|配置|安装|操作)",
    r"天气怎么样",
    r"是什么意思",
    r"^还是算了$",
    r"量子力学",
    r"手感和.*有什么渊源",
    r"通常用什么技术",
)

# Markers for historical or superseded query intent
HISTORICAL_MARKERS: tuple[str, ...] = (
    "以前",
    "旧",
    "过去",
    "之前",
    "曾",
    "那次经历",
    "聊了什么",
    "写了什么",
    "弃用",
    "不用",
    "最初",
)

# Markers for weak reference or task continuity
CONTINUITY_MARKERS: tuple[str, ...] = (
    "和上次一样",
    "还是那个",
    "继续刚才的",
    "又是刚才那个",
    "刚才那个报错",
)

# Markers for companion relationship boundaries and rules
RULE_MARKERS: tuple[str, ...] = (
    "原则",
    "相处",
    "别这样",
    "不要对我",
    "规矩",
    "约束",
    "说教",
    "提醒我休息",
)

# Markers for narrative or life chapters
NARRATIVE_MARKERS: tuple[str, ...] = (
    "人生纪实",
    "章节",
    "第一章",
    "回忆录",
)

# Markers for psychological self-model or reflection
REFLECTIVE_MARKERS: tuple[str, ...] = (
    "容易烦躁",
    "心理",
    "性格",
    "工作模式",
    "心智",
    "心态",
    "情绪",
)

# Distress venting phrases
EMOTIONAL_VENTING_MARKERS: tuple[str, ...] = (
    "好烦啊",
    "心烦",
    "受不了",
    "崩溃了",
    "太累了",
)


class IntentResolver:
    """Precedence-guided intent resolver and early fast-gating engine."""

    def resolve(self, ctx: RetrievalQueryContext) -> IntentResolutionResult:
        clean_q = ctx.query_text.strip()

        # 1. Detect High-level Indicators
        is_past_query = ctx.explicit_historical_intent or any(
            w in clean_q for w in HISTORICAL_MARKERS
        )
        is_yesterday = "昨天" in clean_q or "昨日" in clean_q
        is_continuity = any(w in clean_q for w in CONTINUITY_MARKERS)
        is_rule_query = any(w in clean_q for w in RULE_MARKERS)
        is_narrative_query = any(w in clean_q for w in NARRATIVE_MARKERS)
        is_reflective_query = any(w in clean_q for w in REFLECTIVE_MARKERS)

        # 2. Sanctuary Emotional Guard (P0)
        if ctx.sanctuary_active:
            # P0: Reflective recall is strictly BLOCKED under Sanctuary
            if is_reflective_query:
                return IntentResolutionResult(
                    mode="REFLECTIVE_RECALL",
                    is_continuity=is_continuity,
                    is_past_query=is_past_query,
                    is_rule_query=is_rule_query,
                    is_narrative_query=is_narrative_query,
                    is_reflective_query=is_reflective_query,
                    is_yesterday=is_yesterday,
                    should_early_terminate=True,
                    early_termination_reason="SANCTUARY_BLOCKED_REFLECTIVE",
                )

            # Pure emotional venting without continuity -> Silent acceptance
            if any(w in clean_q for w in EMOTIONAL_VENTING_MARKERS) and not is_continuity:
                return IntentResolutionResult(
                    mode="NO_MEMORY_NEEDED",
                    is_continuity=is_continuity,
                    is_past_query=is_past_query,
                    is_rule_query=is_rule_query,
                    is_narrative_query=is_narrative_query,
                    is_reflective_query=is_reflective_query,
                    is_yesterday=is_yesterday,
                    should_early_terminate=True,
                    early_termination_reason="SANCTUARY_SILENT_VENTING",
                )

        # 3. Task Continuity Intent (Allowed even under Sanctuary!)
        if is_continuity:
            return IntentResolutionResult(
                mode="TASK_CONTINUITY",
                is_continuity=True,
                is_past_query=is_past_query,
                is_rule_query=is_rule_query,
                is_narrative_query=is_narrative_query,
                is_reflective_query=is_reflective_query,
                is_yesterday=is_yesterday,
                should_early_terminate=False,
            )

        # 4. Generic QA Fallback
        # Notice: Only evaluate generic QA if NOT past query, rule query,
        # narrative query, or yesterday!
        if not (is_past_query or is_rule_query or is_narrative_query or is_yesterday):
            if any(re.search(pat, clean_q) for pat in GENERIC_QA_PATTERNS):
                return IntentResolutionResult(
                    mode="NO_MEMORY_NEEDED",
                    is_continuity=is_continuity,
                    is_past_query=is_past_query,
                    is_rule_query=is_rule_query,
                    is_narrative_query=is_narrative_query,
                    is_reflective_query=is_reflective_query,
                    is_yesterday=is_yesterday,
                    should_early_terminate=True,
                    early_termination_reason="GENERIC_QA_FAST_GATE",
                )

        # Determine mode
        if is_narrative_query:
            mode = "NARRATIVE_QUERY"
        elif is_rule_query:
            mode = "RELATIONSHIP_RULE"
        elif is_past_query:
            mode = "EXPLICIT_PAST_QUERY"
        elif is_reflective_query:
            mode = "REFLECTIVE_RECALL"
        else:
            mode = ctx.requested_mode_hint or "FACT_RECALL"

        return IntentResolutionResult(
            mode=mode,
            is_continuity=is_continuity,
            is_past_query=is_past_query,
            is_rule_query=is_rule_query,
            is_narrative_query=is_narrative_query,
            is_reflective_query=is_reflective_query,
            is_yesterday=is_yesterday,
            should_early_terminate=False,
        )
