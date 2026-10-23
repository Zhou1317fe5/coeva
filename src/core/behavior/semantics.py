"""Pet Behavior Semantics (Phase 2.5 WP-0).

Core ontology and domain models for behavior semantics, independent of any specific
pet identity or visual animation asset.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

_FORBIDDEN_ASSET_SUFFIXES = (".png", ".gif", ".webp", ".jpg", ".jpeg", ".bmp")


class BehaviorCategory(StrEnum):
    """Core top-level behavior categories shared across all Coeva pets."""

    IDLE = "idle"
    REST = "rest"
    SLEEP = "sleep"
    WORK = "work"
    OBSERVE = "observe"
    PLAY = "play"
    MOVE = "move"
    GREET = "greet"
    REACT = "react"


REQUIRED_BEHAVIOR_CATEGORIES: frozenset[BehaviorCategory] = frozenset(
    {
        BehaviorCategory.IDLE,
        BehaviorCategory.SLEEP,
        BehaviorCategory.MOVE,
    }
)

OPTIONAL_BEHAVIOR_CATEGORIES: frozenset[BehaviorCategory] = frozenset(
    {
        BehaviorCategory.REST,
        BehaviorCategory.WORK,
        BehaviorCategory.OBSERVE,
        BehaviorCategory.PLAY,
        BehaviorCategory.GREET,
        BehaviorCategory.REACT,
    }
)


class ActivityTrait(StrEnum):
    """Traits describing the qualitative style and energy of an activity."""

    QUIET = "quiet"
    ACTIVE = "active"
    STATIONARY = "stationary"
    LOCOMOTIVE = "locomotive"
    SOCIAL = "social"
    SOLITARY = "solitary"
    FOCUSED = "focused"
    CASUAL = "casual"
    LOW_ENERGY = "low_energy"
    MEDIUM_ENERGY = "medium_energy"
    HIGH_ENERGY = "high_energy"


class BehaviorDirection(StrEnum):
    """Directional parameter for locomotion and orientation behaviors."""

    NONE = "none"
    LEFT = "left"
    RIGHT = "right"


SEMANTIC_FALLBACK_CHAINS: Mapping[BehaviorCategory, tuple[BehaviorCategory, ...]] = {
    BehaviorCategory.WORK: (BehaviorCategory.OBSERVE, BehaviorCategory.IDLE),
    BehaviorCategory.PLAY: (BehaviorCategory.OBSERVE, BehaviorCategory.IDLE),
    BehaviorCategory.REST: (BehaviorCategory.IDLE,),
    BehaviorCategory.OBSERVE: (BehaviorCategory.IDLE,),
    BehaviorCategory.GREET: (BehaviorCategory.REACT, BehaviorCategory.IDLE),
    BehaviorCategory.REACT: (BehaviorCategory.IDLE,),
    BehaviorCategory.SLEEP: (BehaviorCategory.IDLE,),
    # MOVE holds position when unsupported; never fall back to fake animation.
    BehaviorCategory.MOVE: (),
    BehaviorCategory.IDLE: (),
}


@dataclass(frozen=True)
class BehaviorIntent:
    """Runtime representation of WHAT the pet should do and WHY.

    Invariants (Phase 2.5 WP-0):
    - INV-B1: Must NOT reference visual asset filenames or spritesheet rows.
    - INV-B2: Must NOT reference pet-specific activity IDs.
    - Intensity must be bounded in [0.0, 1.0].
    """

    category: BehaviorCategory
    source: str = "life_scheduler"
    preferred_traits: tuple[ActivityTrait, ...] = ()
    direction: BehaviorDirection = BehaviorDirection.NONE
    intensity: float = 1.0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (0.0 <= self.intensity <= 1.0):
            raise ValueError(
                f"BehaviorIntent intensity must be between 0.0 and 1.0, got {self.intensity}"
            )

        if not isinstance(self.category, BehaviorCategory):
            msg = f"category must be BehaviorCategory, got {type(self.category).__name__}"
            raise TypeError(msg)

        if not isinstance(self.direction, BehaviorDirection):
            msg = f"direction must be BehaviorDirection, got {type(self.direction).__name__}"
            raise TypeError(msg)

        if isinstance(self.preferred_traits, Iterable) and not isinstance(
            self.preferred_traits, tuple
        ):
            object.__setattr__(self, "preferred_traits", tuple(self.preferred_traits))

        for trait in self.preferred_traits:
            if not isinstance(trait, ActivityTrait):
                raise TypeError(
                    f"All preferred_traits must be ActivityTrait instances, got {trait!r}"
                )

        if isinstance(self.tags, Iterable) and not isinstance(self.tags, tuple):
            object.__setattr__(self, "tags", tuple(self.tags))

        for tag in self.tags:
            if not isinstance(tag, str):
                raise TypeError(f"All tags must be strings, got {tag!r}")
            lower_tag = tag.lower().strip()
            if any(lower_tag.endswith(suffix) for suffix in _FORBIDDEN_ASSET_SUFFIXES):
                msg = (
                    f"BehaviorIntent tag {tag!r} references a visual asset file (INV-B1 violation)"
                )
                raise ValueError(msg)


def resolve_semantic_fallback(
    category: BehaviorCategory,
    is_supported: Callable[[BehaviorCategory], bool],
) -> BehaviorCategory | None:
    """Resolve a behavior category through the standard semantic fallback chain.

    Returns the original category if supported, the first supported fallback category in the chain,
    or None if neither the category nor any of its fallbacks are supported.
    """
    if is_supported(category):
        return category

    for fallback in SEMANTIC_FALLBACK_CHAINS.get(category, ()):
        if is_supported(fallback):
            return fallback

    return None
