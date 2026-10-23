"""Activity Registry and Semantic Fallback Resolver (Phase 2.5 WP-3).

Provides an indexed query and deterministic resolution engine for a pet's
activities given a generic BehaviorIntent.

Invariants:
- Zero pet-specific names or assets in this module.
- Strict reuse of WP-0 SEMANTIC_FALLBACK_CHAINS.
- MOVE without native support yields structured no-op (never fake walk).
- Deterministic ranking; zero random selection.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.core.behavior.manifest import PetActivity, PetManifest
from src.core.behavior.semantics import (
    SEMANTIC_FALLBACK_CHAINS,
    ActivityTrait,
    BehaviorCategory,
    BehaviorDirection,
    BehaviorIntent,
)


@dataclass(frozen=True)
class ResolvedCandidate:
    """A matched activity with execution adaptation metadata and score."""

    activity: PetActivity
    mirror_required: bool = False
    match_score: float = 1.0


@dataclass(frozen=True)
class ActivityResolution:
    """Complete structural report of resolving a BehaviorIntent against a pet's registry."""

    requested_category: BehaviorCategory
    resolved_category: BehaviorCategory | None
    candidates: tuple[ResolvedCandidate, ...] = ()
    fallback_path: tuple[BehaviorCategory, ...] = ()
    degraded: bool = False
    no_op: bool = False
    reason: str = ""

    @property
    def primary_activity(self) -> PetActivity | None:
        """Top-ranked matched activity, or None if no candidate or no_op."""
        if not self.candidates or self.no_op:
            return None
        return self.candidates[0].activity

    @property
    def primary_mirror_required(self) -> bool:
        """Mirroring requirement for the top-ranked candidate."""
        if not self.candidates or self.no_op:
            return False
        return self.candidates[0].mirror_required


class ActivityRegistry:
    """Immutable, indexed activity catalog for a single pet manifest."""

    def __init__(self, manifest: PetManifest) -> None:
        if not isinstance(manifest, PetManifest):
            msg = f"manifest must be PetManifest, got {type(manifest).__name__}"
            raise TypeError(msg)
        self._manifest = manifest

        # Build category -> tuple[PetActivity, ...] index
        by_category: dict[BehaviorCategory, list[PetActivity]] = {
            cat: [] for cat in BehaviorCategory
        }
        for act in manifest.activities:
            by_category[act.category].append(act)

        self._by_category: Mapping[BehaviorCategory, tuple[PetActivity, ...]] = {
            cat: tuple(acts) for cat, acts in by_category.items()
        }

    @property
    def manifest(self) -> PetManifest:
        """Underlying pet manifest."""
        return self._manifest

    def activities_for(self, category: BehaviorCategory) -> tuple[PetActivity, ...]:
        """Return all activities declared by this pet for the given BehaviorCategory."""
        if not isinstance(category, BehaviorCategory):
            msg = f"category must be BehaviorCategory, got {type(category).__name__}"
            raise TypeError(msg)
        return self._by_category.get(category, ())

    def supports_category(self, category: BehaviorCategory) -> bool:
        """Check if pet natively has one or more activities for category."""
        return len(self.activities_for(category)) > 0

    def resolve(self, intent: BehaviorIntent) -> ActivityResolution:
        """Resolve a BehaviorIntent into structured candidates with deterministic fallback."""
        if not isinstance(intent, BehaviorIntent):
            msg = f"intent must be BehaviorIntent, got {type(intent).__name__}"
            raise TypeError(msg)

        req_cat = intent.category

        # 1. Native probe
        if self.supports_category(req_cat):
            candidates = self._score_and_filter_candidates(
                self.activities_for(req_cat), intent
            )
            if candidates:
                return ActivityResolution(
                    requested_category=req_cat,
                    resolved_category=req_cat,
                    candidates=candidates,
                    fallback_path=(req_cat,),
                    degraded=False,
                    no_op=False,
                    reason="native_match",
                )

        # 2. Check MOVE special hold-position rule (INV-B5 & WP-0 Section 12)
        if req_cat == BehaviorCategory.MOVE:
            return ActivityResolution(
                requested_category=req_cat,
                resolved_category=None,
                candidates=(),
                fallback_path=(req_cat,),
                degraded=True,
                no_op=True,
                reason="move_not_supported_hold_position",
            )

        # 3. Chain fallback via canonical WP-0 SEMANTIC_FALLBACK_CHAINS
        path: list[BehaviorCategory] = [req_cat]
        for fallback_cat in SEMANTIC_FALLBACK_CHAINS.get(req_cat, ()):
            path.append(fallback_cat)
            if self.supports_category(fallback_cat):
                candidates = self._score_and_filter_candidates(
                    self.activities_for(fallback_cat), intent
                )
                if candidates:
                    return ActivityResolution(
                        requested_category=req_cat,
                        resolved_category=fallback_cat,
                        candidates=candidates,
                        fallback_path=tuple(path),
                        degraded=True,
                        no_op=False,
                        reason=f"fallback_to_{fallback_cat.value}",
                    )

        # 4. Fallback exhausted without viable candidate
        return ActivityResolution(
            requested_category=req_cat,
            resolved_category=None,
            candidates=(),
            fallback_path=tuple(path),
            degraded=True,
            no_op=True,
            reason="all_fallbacks_unsupported",
        )

    def _score_and_filter_candidates(
        self,
        pool: tuple[PetActivity, ...],
        intent: BehaviorIntent,
    ) -> tuple[ResolvedCandidate, ...]:
        """Score candidate activities against direction & traits, returning sorted tuple."""
        scored: list[ResolvedCandidate] = []
        preferred_traits_set = set(intent.preferred_traits)

        for act in pool:
            match_score, mirror_required, is_viable = self._evaluate_match(
                act, intent.direction, preferred_traits_set
            )
            if is_viable:
                # Add tiny deterministic tie-breaker based on activity.weight
                final_score = match_score + (0.01 * act.weight)
                scored.append(
                    ResolvedCandidate(
                        activity=act,
                        mirror_required=mirror_required,
                        match_score=round(final_score, 4),
                    )
                )

        # Deterministic sorting: match_score descending, then activity.id ascending (stable)
        scored.sort(key=lambda c: (-c.match_score, c.activity.id))
        return tuple(scored)

    @staticmethod
    def _evaluate_match(
        activity: PetActivity,
        req_direction: BehaviorDirection,
        preferred_traits: set[ActivityTrait],
    ) -> tuple[float, bool, bool]:
        """Evaluate direction viability and calculate match score for a single activity.

        Returns (score, mirror_required, is_viable).
        """
        score = 0.0
        mirror_required = False

        # Direction match logic
        if req_direction == BehaviorDirection.NONE:
            score += 10.0
        elif req_direction == activity.direction:
            # Exact direction match (e.g. RIGHT == RIGHT)
            score += 15.0
        elif activity.direction == BehaviorDirection.NONE:
            # Directionless activity can fit left/right request
            score += 8.0
        elif (
            req_direction == BehaviorDirection.LEFT
            and activity.direction == BehaviorDirection.RIGHT
            and activity.visual.mirror
        ):
            # Mirrored match
            score += 12.0
            mirror_required = True
        elif (
            req_direction == BehaviorDirection.RIGHT
            and activity.direction == BehaviorDirection.LEFT
            and activity.visual.mirror
        ):
            # Mirrored match
            score += 12.0
            mirror_required = True
        else:
            # Direction conflict that cannot be resolved via mirror
            return (0.0, False, False)

        # Preferred traits score
        if preferred_traits:
            for trait in activity.traits:
                if trait in preferred_traits:
                    score += 2.0

        return (score, mirror_required, True)
