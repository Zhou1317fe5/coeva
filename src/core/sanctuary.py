"""Sanctuary Guard: Emotional meltdown protection mechanism."""

from __future__ import annotations

import re

# Trigger patterns representing frustration, venting, or need for solitude
NEGATIVE_KEYWORDS = [
    "烦死了",
    "全搞砸了",
    "搞砸了",
    "心累",
    "好累",
    "崩溃",
    "不想干了",
    "真他妈",
    "真烦",
    "讨厌",
    "恶心",
    "别烦我",
    "安静点",
    "垃圾",
    "抑郁",
    "痛苦",
    "绝望",
    "失控",
]

_COMPILED_PATTERN = re.compile("|".join(re.escape(w) for w in NEGATIVE_KEYWORDS))


class SanctuaryGuard:
    """Detects acute user distress and triggers silence meltdown.

    When active, all psychological interpretation and coaching intervention
    are 100% suppressed to preserve a peaceful, non-judgmental sanctuary.
    """

    def __init__(self) -> None:
        self._meltdown_active = False

    @property
    def is_active(self) -> bool:
        return self._meltdown_active

    def evaluate_text(self, text: str) -> bool:
        """Check if the text warrants activating Sanctuary mode."""
        clean = text.strip()
        if not clean:
            return False

        if _COMPILED_PATTERN.search(clean) is not None:
            self._meltdown_active = True
            return True
        return False

    def reset(self) -> None:
        """Manually clear meltdown status."""
        self._meltdown_active = False
