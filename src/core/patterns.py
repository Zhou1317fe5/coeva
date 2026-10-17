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
        """Detect whether user intervenes after errors, or lets the agent heal autonomously.

        Strict Temporal Causality Rule:
        A user intervention is ONLY counted when `user_prompt` occurs AFTER a `tool_failure`.
        An initial prompt starting the session does NOT count as error recovery.
        """
        intervened_episodes: list[str] = []
        autonomous_healing_episodes: list[str] = []

        for ep in episodes:
            rows = self.store._conn.execute(
                "SELECT event_type, timestamp FROM events "
                "WHERE session_id = ? "
                "ORDER BY timestamp ASC",
                (ep.session_id,),
            ).fetchall()

            has_failure = False
            user_intervened_after_fail = False

            for r in rows:
                etype = r["event_type"]
                if etype == "tool_failure":
                    has_failure = True
                elif has_failure and etype == "user_prompt":
                    user_intervened_after_fail = True
                    break

            if has_failure:
                if user_intervened_after_fail:
                    intervened_episodes.append(ep.session_id)
                else:
                    autonomous_healing_episodes.append(ep.session_id)

        if not intervened_episodes and not autonomous_healing_episodes:
            return None

        # Determine dominant pattern truthfully based on evidence ratio
        if len(intervened_episodes) >= len(autonomous_healing_episodes):
            return BehavioralPattern(
                pattern_id="pat_friction_recovery",
                category="friction_response",
                description="面对工具执行报错摩擦时，用户倾向于主动下发纠偏指令并调整边界。",
                supporting_episodes=tuple(intervened_episodes),
                counter_episodes=tuple(autonomous_healing_episodes),
                contexts=("coding", "tool_execution"),
                metadata={"failure_handling": "prompt_intervention"},
            )
        else:
            return BehavioralPattern(
                pattern_id="pat_agent_autonomous_recovery",
                category="friction_response",
                description=(
                    "面对工具执行报错摩擦时，倾向于给予 Agent 充分自主修复空间，不频繁介入打断。"
                ),
                supporting_episodes=tuple(autonomous_healing_episodes),
                counter_episodes=tuple(intervened_episodes),
                contexts=("coding", "autonomous_healing"),
                metadata={"failure_handling": "hands_off_delegation"},
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
        """Detect collaboration style: autonomous delegation vs active interactive steering.

        Causality metric:
        Computes user_prompt ratio against total events in the session.
        Low ratio (<= 15%) indicates hands-off delegation;
        higher ratio indicates interactive steering.
        """
        hands_off_episodes: list[str] = []
        interactive_episodes: list[str] = []

        for ep in episodes:
            if ep.event_count >= 5:
                user_prompts = self.store._conn.execute(
                    "SELECT COUNT(*) AS c FROM events "
                    "WHERE session_id = ? AND event_type = 'user_prompt'",
                    (ep.session_id,),
                ).fetchone()["c"]

                ratio = user_prompts / max(1, ep.event_count)
                if ratio <= 0.15:
                    hands_off_episodes.append(ep.session_id)
                else:
                    interactive_episodes.append(ep.session_id)

        if not hands_off_episodes and not interactive_episodes:
            return None

        if len(hands_off_episodes) >= len(interactive_episodes):
            return BehavioralPattern(
                pattern_id="pat_hands_off_delegation",
                category="tool_delegation",
                description="在长链路复杂任务执行中，倾向于充分委派 Agent 自主探索，不频繁打断。",
                supporting_episodes=tuple(hands_off_episodes),
                counter_episodes=tuple(interactive_episodes),
                contexts=("agent_delegation", "autonomous_execution"),
            )
        else:
            return BehavioralPattern(
                pattern_id="pat_interactive_steering",
                category="tool_delegation",
                description="在长链路复杂任务执行中，保持紧密的阶段性提示词引导与交互节奏。",
                supporting_episodes=tuple(interactive_episodes),
                counter_episodes=tuple(hands_off_episodes),
                contexts=("interactive_collaboration",),
            )
