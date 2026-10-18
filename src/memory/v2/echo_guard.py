"""Delta-Aware Echo Guard for Memory V2.1 Lane C.

Implements INV-10 (Memory Must Not Echo) and Delta-Aware Echo Isolation:
- Pure acknowledgements (Case E1) and echo parroting (Case E3) are filtered as NOOP_LONG_TERM.
- Echoes carrying a user-authored semantic delta or correction (Case E2) preserve the delta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ACK_PREFIXES = [
    "正如你刚才提到的",
    "正如你刚才所说",
    "正如你所说",
    "你说的对",
    "你说得对",
    "确实是这样",
    "没错就是这样",
    "对啊",
    "对的",
    "对",
    "是的",
    "没错",
    "确实",
    "嗯嗯",
    "嗯",
    "好的",
    "好",
    "ok",
    "yes",
    "yeah",
]

CONTRAST_MARKERS = [
    "不过现在",
    "不过",
    "但是",
    "但",
    "现在",
    "改用",
    "其实",
    "并不",
    "不是",
    "换成",
    "除了",
    "只是",
    "只在",
    "只有",
    "而非",
    "不再",
    "更喜欢",
    "更倾向",
    "反而",
    "相反",
]

ECHO_FENCE_PATTERN = re.compile(r"<!--\s*COEVA_ECHO_FENCE:\s*(.*?)\s*-->", re.DOTALL)


@dataclass(frozen=True)
class EchoGuardResult:
    """Outcome of Delta-Aware Echo Guard inspection."""

    has_echo_context: bool
    is_pure_echo: bool
    delta_text: str | None
    overlap_ratio: float
    has_contrast_marker: bool
    rationale: str


class EchoGuard:
    """Isolates assistant echo and extracts genuine user-authored semantic delta."""

    def __init__(self, overlap_threshold: float = 0.70) -> None:
        self.overlap_threshold = overlap_threshold

    def extract_echo_fence(self, text: str) -> tuple[str, str | None]:
        """Extract echo fence from text if embedded."""
        match = ECHO_FENCE_PATTERN.search(text)
        if match:
            fence_content = match.group(1).strip()
            clean_text = ECHO_FENCE_PATTERN.sub("", text).strip()
            return clean_text, fence_content
        return text, None

    def strip_ack_prefix(self, text: str) -> str:
        """Repeatedly strip conversational acknowledgment prefixes."""
        current = text.strip()
        changed = True
        while changed:
            changed = False
            # Strip leading punctuation/whitespace
            current = re.sub(r"^[\s,，.。!！?？~、:：\-_]+", "", current)
            for prefix in ACK_PREFIXES:
                if current.lower().startswith(prefix.lower()):
                    current = current[len(prefix) :].strip()
                    changed = True
                    break
        current = re.sub(r"^[\s,，.。!！?？~、:：\-_]+", "", current)
        return current

    def calculate_char_overlap(self, text_a: str, text_b: str) -> float:
        """Calculate character set overlap ratio between text_a and text_b."""
        chars_a = set(re.findall(r"[\u4e00-\u9fa5\w]", text_a.lower()))
        chars_b = set(re.findall(r"[\u4e00-\u9fa5\w]", text_b.lower()))
        if not chars_a or not chars_b:
            return 0.0
        intersection = chars_a.intersection(chars_b)
        return len(intersection) / float(len(chars_a))

    def inspect(
        self,
        user_content: str,
        echoed_proposition: str | None = None,
    ) -> EchoGuardResult:
        """Inspect user response against an echoed assistant proposition."""
        clean_content, embedded_fence = self.extract_echo_fence(user_content)
        fence = echoed_proposition or embedded_fence

        if not fence:
            # No echo proposition present: entirely user-authored
            return EchoGuardResult(
                has_echo_context=False,
                is_pure_echo=False,
                delta_text=clean_content,
                overlap_ratio=0.0,
                has_contrast_marker=False,
                rationale="No echo context attached.",
            )

        stripped = self.strip_ack_prefix(clean_content)

        # Case E1: pure acknowledgement with no residual semantic payload
        if not stripped:
            return EchoGuardResult(
                has_echo_context=True,
                is_pure_echo=True,
                delta_text=None,
                overlap_ratio=0.0,
                has_contrast_marker=False,
                rationale="Pure conversational acknowledgement without proposition (Case E1).",
            )

        # Check for contrast / qualification markers
        has_contrast = any(marker in clean_content for marker in CONTRAST_MARKERS)

        # Calculate overlap against the echoed proposition
        overlap = self.calculate_char_overlap(stripped, fence)

        # Case E3: Parroting without contrast or new assertion
        if overlap >= self.overlap_threshold and not has_contrast:
            return EchoGuardResult(
                has_echo_context=True,
                is_pure_echo=True,
                delta_text=None,
                overlap_ratio=overlap,
                has_contrast_marker=False,
                rationale=(
                    f"Parroting echoed proposition (overlap {overlap:.1%}) "
                    "without contrast marker (Case E3)."
                ),
            )

        # Case E2: Residual delta exists (either through contrast markers or new content)
        return EchoGuardResult(
            has_echo_context=True,
            is_pure_echo=False,
            delta_text=stripped if stripped else clean_content,
            overlap_ratio=overlap,
            has_contrast_marker=has_contrast,
            rationale="User response carries genuine semantic delta over echo (Case E2).",
        )
