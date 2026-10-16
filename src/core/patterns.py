"""Pattern Builder (Phase 2B): Extracts cross-episode behavioral patterns.

Adheres strictly to the Principle:
- Evidence != Pattern != Hypothesis != Insight != Narrative
- A pattern must describe behavioral structure across MULTIPLE episodes.
- No direct psychological projection (e.g. forbid "User has high control desire").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.memory.store import ChronicleStore, Episode


@dataclass(frozen=True)
class BehavioralPattern:
    """An objective recurring behavioral structure observed across multiple episodes."""

    pattern_id: str
    category: str  # e.g. "friction_response", "pacing_boundary", "tool_delegation"
    description: str
    supporting_episodes: tuple[str, ...]
    counter_episodes: tuple[str, ...]
    contexts: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def support_ratio(self) -> float:
        """Proportion of supporting episodes over total relevant episodes."""
        total = len(self.supporting_episodes) + len(self.counter_episodes)
        if total == 0:
            return 0.0
        return round(len(self.supporting_episodes) / total, 2)


class PatternBuilder:
    """Mines behavioral patterns from historical episodes and telemetry."""

    def __init__(self, store: ChronicleStore) -> None:
        self.store = store

    def build_patterns(self, *, min_episodes: int = 2) -> list[BehavioralPattern]:
        """Analyze historical episodes and extract active behavioral patterns."""
        episodes: list[Episode] = self.store.list_episodes(limit=100)
        if len(episodes) < min_episodes:
            # Silence is valid: insufficient data must produce zero patterns (SPEC 2.6)
            return []

        patterns: list[BehavioralPattern] = []

        # 1. Pattern: Friction Response (How user reacts when tools fail)
        friction_pat = self._detect_friction_response(episodes)
        if friction_pat:
            patterns.append(friction_pat)

        # 2. Pattern: Pacing & Boundaries (Nighttime & long session boundaries)
        pacing_pat = self._detect_pacing_boundaries(episodes)
        if pacing_pat:
            patterns.append(pacing_pat)

        # 3. Pattern: Autonomous Action vs Heavy Delegation
        delegation_pat = self._detect_delegation_ratio(episodes)
        if delegation_pat:
            patterns.append(delegation_pat)

        return patterns

    def _detect_friction_response(self, episodes: list[Episode]) -> BehavioralPattern | None:
        """Detect whether user actively intervenes or pauses after tool failures."""
        supporting: list[str] = []
        counter: list[str] = []

        for ep in episodes:
            # Query tool failures in this session
            fails = self.store._conn.execute(
                "SELECT COUNT(*) AS c FROM events "
                "WHERE session_id = ? AND event_type = 'tool_failure'",
                (ep.session_id,),
            ).fetchone()["c"]

            if fails > 0:
                # Did user provide active prompt or pause?
                user_prompts = self.store._conn.execute(
                    "SELECT COUNT(*) AS c FROM events "
                    "WHERE session_id = ? AND event_type = 'user_prompt'",
                    (ep.session_id,),
                ).fetchone()["c"]

                if user_prompts > 0:
                    supporting.append(ep.session_id)
                else:
                    counter.append(ep.session_id)

        if not supporting and not counter:
            return None

        return BehavioralPattern(
            pattern_id="pat_friction_recovery",
            category="friction_response",
            description="当 Agent 执行遇到报错摩擦时，用户倾向于主动下发纠偏指令并调整边界。",
            supporting_episodes=tuple(supporting),
            counter_episodes=tuple(counter),
            contexts=("coding", "tool_execution"),
            metadata={"failure_handling": "prompt_intervention"},
        )

    def _detect_pacing_boundaries(self, episodes: list[Episode]) -> BehavioralPattern | None:
        """Detect whether user concludes sessions within healthy boundaries."""
        supporting: list[str] = []
        counter: list[str] = []

        for ep in episodes:
            # Check session ended_at hour
            try:
                # ISO timestamp: YYYY-MM-DDTHH:MM:SS
                time_part = ep.ended_at[11:19]
                hour = int(time_part.split(":")[0])
            except (ValueError, IndexError):
                continue

            # Healthy boundary: wrapped before midnight [07:00 ~ 23:00]
            # Midnight push: [00:00 ~ 05:00]
            if 0 <= hour <= 5:
                counter.append(ep.session_id)
            else:
                supporting.append(ep.session_id)

        if not supporting and not counter:
            return None

        return BehavioralPattern(
            pattern_id="pat_circadian_pacing",
            category="pacing_boundary",
            description="用户大部分开发任务在常规作息时间内完成并主动收尾。",
            supporting_episodes=tuple(supporting),
            counter_episodes=tuple(counter),
            contexts=("daily_routine", "night_work"),
            metadata={"preferred_window": "daytime_evening"},
        )

    def _detect_delegation_ratio(self, episodes: list[Episode]) -> BehavioralPattern | None:
        """Detect collaboration style: autonomous guidance vs dense tool usage."""
        supporting: list[str] = []
        counter: list[str] = []

        for ep in episodes:
            if ep.event_count > 5:
                if ep.has_user_action:
                    supporting.append(ep.session_id)
                else:
                    counter.append(ep.session_id)

        if not supporting and not counter:
            return None

        return BehavioralPattern(
            pattern_id="pat_interactive_steering",
            category="tool_delegation",
            description="在较长链路的任务执行中，用户保持了主动的提示词引导与监控节奏。",
            supporting_episodes=tuple(supporting),
            counter_episodes=tuple(counter),
            contexts=("agent_delegation",),
        )
