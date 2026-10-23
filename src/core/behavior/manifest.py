"""Pet Manifest and Capability Contract (Phase 2.5 WP-1).

Defines the declarative manifest domain model, visual binding indirection,
capability parity verification, and V1 backward-compatibility adapter.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.core.behavior.semantics import (
    OPTIONAL_BEHAVIOR_CATEGORIES,
    ActivityTrait,
    BehaviorCategory,
    BehaviorDirection,
    resolve_semantic_fallback,
)

_FORBIDDEN_ASSET_SUFFIXES = (".png", ".gif", ".webp", ".jpg", ".jpeg", ".bmp")


class LoopMode(StrEnum):
    """Animation looping behavior for a pet activity."""

    ONCE = "once"
    LOOP = "loop"
    HOLD_LAST = "hold_last"


@dataclass(frozen=True)
class VisualBinding:
    """Indirection layer binding a PetActivity to a presentation asset or animation state.

    Invariants:
    - PetActivity does NOT parse binary assets directly.
    - BehaviorCategory is NOT derived from visual reference names.
    """

    ref: str
    format: str | None = None
    mirror: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref.strip():
            msg = f"VisualBinding ref must be a non-empty string, got {self.ref!r}"
            raise ValueError(msg)
        if not isinstance(self.mirror, bool):
            msg = f"VisualBinding mirror must be a bool, got {self.mirror!r}"
            raise TypeError(msg)
        if self.format is not None and not isinstance(self.format, str):
            msg = f"VisualBinding format must be str or None, got {self.format!r}"
            raise TypeError(msg)


@dataclass(frozen=True)
class PetActivity:
    """Describes HOW a pet expresses a BehaviorCategory.

    Invariants:
    - ID has pet-local scope only; never consumed by Scheduler.
    - Category must be a frozen BehaviorCategory (WP-0).
    - Traits must be frozen ActivityTraits (WP-0).
    - Weight must be positive.
    - Duration if specified must be positive.
    """

    id: str
    category: BehaviorCategory
    visual: VisualBinding
    traits: frozenset[ActivityTrait] = frozenset()
    direction: BehaviorDirection = BehaviorDirection.NONE
    loop: LoopMode = LoopMode.LOOP
    interruptible: bool = True
    duration_ms: int | None = None
    weight: float = 1.0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            msg = f"PetActivity id must be a non-empty string, got {self.id!r}"
            raise ValueError(msg)

        if not isinstance(self.category, BehaviorCategory):
            c_name = type(self.category).__name__
            msg = f"PetActivity category must be BehaviorCategory, got {c_name}"
            raise TypeError(msg)

        if not isinstance(self.visual, VisualBinding):
            v_name = type(self.visual).__name__
            msg = f"PetActivity visual must be VisualBinding, got {v_name}"
            raise TypeError(msg)

        if not isinstance(self.direction, BehaviorDirection):
            d_name = type(self.direction).__name__
            msg = f"PetActivity direction must be BehaviorDirection, got {d_name}"
            raise TypeError(msg)

        if not isinstance(self.loop, LoopMode):
            l_name = type(self.loop).__name__
            msg = f"PetActivity loop must be LoopMode, got {l_name}"
            raise TypeError(msg)

        if not isinstance(self.interruptible, bool):
            i_name = type(self.interruptible).__name__
            msg = f"PetActivity interruptible must be bool, got {i_name}"
            raise TypeError(msg)

        if self.duration_ms is not None:
            if not isinstance(self.duration_ms, int) or isinstance(self.duration_ms, bool):
                msg = f"PetActivity duration_ms must be an integer, got {self.duration_ms!r}"
                raise TypeError(msg)
            if self.duration_ms <= 0:
                msg = f"PetActivity duration_ms must be positive, got {self.duration_ms}"
                raise ValueError(msg)

        if not isinstance(self.weight, (int, float)) or isinstance(self.weight, bool):
            msg = f"PetActivity weight must be a float, got {self.weight!r}"
            raise TypeError(msg)
        if self.weight <= 0.0:
            msg = f"PetActivity weight must be > 0.0, got {self.weight}"
            raise ValueError(msg)

        if isinstance(self.traits, Iterable) and not isinstance(self.traits, frozenset):
            object.__setattr__(self, "traits", frozenset(self.traits))

        for trait in self.traits:
            if not isinstance(trait, ActivityTrait):
                msg = f"All traits must be ActivityTrait instances, got {trait!r}"
                raise TypeError(msg)

        if isinstance(self.tags, Iterable) and not isinstance(self.tags, tuple):
            object.__setattr__(self, "tags", tuple(self.tags))

        for tag in self.tags:
            if not isinstance(tag, str):
                msg = f"All tags must be strings, got {tag!r}"
                raise TypeError(msg)
            lower_tag = tag.lower().strip()
            if any(lower_tag.endswith(suffix) for suffix in _FORBIDDEN_ASSET_SUFFIXES):
                msg = (
                    f"PetActivity tag {tag!r} references a visual asset file (INV-B1 violation)"
                )
                raise ValueError(msg)


@dataclass(frozen=True)
class PetManifest:
    """Canonical immutable manifest for a pet.

    Declared via `pet.json` (schema_version=2).
    """

    schema_version: int
    id: str
    name: str
    capabilities: frozenset[BehaviorCategory]
    activities: tuple[PetActivity, ...]
    description: str = ""
    format: str | None = None
    spritesheet_path: str | None = None
    theme_path: str | None = None
    native_idle_path: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            msg = f"schema_version must be integer, got {self.schema_version!r}"
            raise TypeError(msg)
        if self.schema_version <= 0:
            msg = f"schema_version must be >= 1, got {self.schema_version}"
            raise ValueError(msg)

        if not isinstance(self.id, str) or not self.id.strip():
            msg = f"PetManifest id must be non-empty string, got {self.id!r}"
            raise ValueError(msg)

        if not isinstance(self.name, str) or not self.name.strip():
            msg = f"PetManifest name must be non-empty string, got {self.name!r}"
            raise ValueError(msg)

        if isinstance(self.capabilities, Iterable) and not isinstance(
            self.capabilities, frozenset
        ):
            object.__setattr__(self, "capabilities", frozenset(self.capabilities))

        for cap in self.capabilities:
            if not isinstance(cap, BehaviorCategory):
                msg = f"All capabilities must be BehaviorCategory instances, got {cap!r}"
                raise TypeError(msg)

        if isinstance(self.activities, Iterable) and not isinstance(self.activities, tuple):
            object.__setattr__(self, "activities", tuple(self.activities))

        for act in self.activities:
            if not isinstance(act, PetActivity):
                msg = f"All activities must be PetActivity instances, got {act!r}"
                raise TypeError(msg)

    def has_capability(self, category: BehaviorCategory) -> bool:
        """Check if this pet declares support for a BehaviorCategory."""
        return category in self.capabilities

    def get_activities_for_category(
        self, category: BehaviorCategory
    ) -> tuple[PetActivity, ...]:
        """Return all activities declared by this pet for the given BehaviorCategory."""
        return tuple(act for act in self.activities if act.category == category)


@dataclass(frozen=True)
class ValidationResult:
    """Diagnostic outcome of validating a PetManifest."""

    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    pet_id: str = ""

    def summary(self) -> str:
        """Produce a human-readable summary of the validation result."""
        lines: list[str] = [f"Pet: {self.pet_id or 'unknown'}"]
        if self.valid:
            lines.append("Status: VALID")
        else:
            lines.append("Status: INVALID")

        if self.errors:
            lines.append("Errors:")
            for err in self.errors:
                lines.append(f"  - {err}")
        if self.warnings:
            lines.append("Warnings:")
            for warn in self.warnings:
                lines.append(f"  - {warn}")
        return "\n".join(lines)


def validate_pet_manifest(
    manifest: PetManifest, pet_dir: Path | None = None
) -> ValidationResult:
    """Strictly validate a PetManifest according to WP-1 rules.

    Checks:
    - Non-empty ID and Name;
    - No duplicate PetActivity IDs;
    - Capability-Activity Parity (every declared capability has >= 1 activity);
    - Required Baseline coverage (IDLE must have native activity; SLEEP and MOVE resolvable);
    - Fallback consistency;
    - Visual references existence (if pet_dir provided).
    """
    errors: list[str] = []
    warnings: list[str] = []
    pid = manifest.id

    # 1. Activity ID uniqueness
    seen_ids: set[str] = set()
    for act in manifest.activities:
        if act.id in seen_ids:
            errors.append(f"Pet '{pid}': duplicate activity id '{act.id}'")
        seen_ids.add(act.id)

    # 2. Capability-Activity Parity
    activity_categories = {act.category for act in manifest.activities}

    for cap in manifest.capabilities:
        if cap not in activity_categories:
            errors.append(
                f"Pet '{pid}': declared capability '{cap.value}' has no activities defined"
            )

    for act in manifest.activities:
        if act.category not in manifest.capabilities:
            msg = (
                f"Pet '{pid}': activity '{act.id}' has category '{act.category.value}' "
                "which is not in declared capabilities"
            )
            errors.append(msg)

    # 3. Required Baseline Safety (INV-M4)
    # IDLE must have a native activity
    idle_activities = manifest.get_activities_for_category(BehaviorCategory.IDLE)
    if not idle_activities:
        errors.append(
            f"Pet '{pid}': required capability 'idle' has no valid activity (INV-M4 violation)"
        )

    # SLEEP must either be declared & implemented, or fallback to IDLE
    if not manifest.has_capability(BehaviorCategory.SLEEP):
        sleep_fallback = resolve_semantic_fallback(
            BehaviorCategory.SLEEP, manifest.has_capability
        )
        if sleep_fallback is None:
            errors.append(
                f"Pet '{pid}': required capability 'sleep' is neither declared nor resolvable"
            )
        else:
            warnings.append(
                f"Pet '{pid}': required capability 'sleep' not natively declared; "
                f"falling back to '{sleep_fallback.value}'"
            )

    # MOVE check: if declared, must have activities; if not declared, holds position per WP-0
    if not manifest.has_capability(BehaviorCategory.MOVE):
        warnings.append(
            f"Pet '{pid}': 'move' not declared; runtime will hold position on move intents"
        )

    # 4. Optional Capabilities Missing (Normal, not an error per INV-B5)
    for opt_cap in OPTIONAL_BEHAVIOR_CATEGORIES:
        if not manifest.has_capability(opt_cap):
            pass

    # 5. Visual Asset Checks (if pet_dir provided)
    if pet_dir is not None and pet_dir.is_dir():
        if manifest.spritesheet_path:
            sheet_file = pet_dir / manifest.spritesheet_path
            if not sheet_file.is_file():
                errors.append(
                    f"Pet '{pid}': spritesheet_path '{manifest.spritesheet_path}' does not exist"
                )

        if manifest.theme_path:
            theme_file = pet_dir / manifest.theme_path
            if not theme_file.is_file():
                errors.append(
                    f"Pet '{pid}': configured theme_path '{manifest.theme_path}' does not exist"
                )

        if manifest.native_idle_path:
            idle_file = pet_dir / manifest.native_idle_path
            if not idle_file.is_file():
                errors.append(
                    f"Pet '{pid}': native_idle_path '{manifest.native_idle_path}' does not exist"
                )

        # Activity visual binding file checks when format is file-based
        for act in manifest.activities:
            if act.visual.format in ("apng", "gif", "file"):
                target = pet_dir / act.visual.ref
                target_in_assets = pet_dir / "assets" / act.visual.ref
                if not target.is_file() and not target_in_assets.is_file():
                    msg = (
                        f"Pet '{pid}': activity '{act.id}' visual ref '{act.visual.ref}' "
                        "not found in pet directory"
                    )
                    errors.append(msg)

    is_valid = len(errors) == 0
    return ValidationResult(
        valid=is_valid,
        errors=tuple(errors),
        warnings=tuple(warnings),
        pet_id=pid,
    )


def adapt_v1_pet_dict(data: Mapping[str, Any], pet_dir: Path | None = None) -> PetManifest:
    """Thin compatibility adapter converting legacy V1 pet data into a valid PetManifest (V2).

    Supports:
    - Vasu (Atlas spritesheet + native_idle.json);
    - Calico (Clawd on Desk theme.json);
    - Generic Petdex single spritesheet pets.
    """
    pid = str(data.get("id", "unknown")).strip()
    pname = str(data.get("displayName") or data.get("name") or pid).strip()
    pdesc = str(data.get("description", ""))
    pformat = str(data.get("format", "atlas"))

    capabilities: set[BehaviorCategory] = set()
    activities: list[PetActivity] = []
    spritesheet_path: str | None = None
    theme_path: str | None = None
    native_idle_path: str | None = None

    # Detect theme-based pet (e.g. Calico)
    is_theme = pformat == "theme" or (pet_dir is not None and (pet_dir / "theme.json").is_file())
    if is_theme and pet_dir is not None:
        t_path = pet_dir / str(data.get("themePath", "theme.json"))
        if t_path.is_file():
            theme_path = t_path.name
            try:
                t_data = json.loads(t_path.read_text(encoding="utf-8"))
                states = t_data.get("states", {})
                for state_name in states:
                    cat, traits, direction = _map_v1_theme_state_to_semantics(state_name)
                    capabilities.add(cat)
                    activities.append(
                        PetActivity(
                            id=f"calico_{state_name}",
                            category=cat,
                            visual=VisualBinding(ref=state_name, format="theme"),
                            traits=traits,
                            direction=direction,
                            loop=LoopMode.LOOP,
                        )
                    )
            except Exception:
                pass

    # Detect atlas-based pet (e.g. Vasu or standard Petdex 9-row)
    if not activities:
        if "spritesheetPath" in data:
            spritesheet_path = str(data["spritesheetPath"])
        elif pet_dir is not None and (pet_dir / "spritesheet.webp").is_file():
            spritesheet_path = "spritesheet.webp"

        if pet_dir is not None and (pet_dir / "native_idle.json").is_file():
            native_idle_path = "native_idle.json"

        # Map standard 9-row atlas behaviors
        idle_tr = frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY})
        move_tr = frozenset({ActivityTrait.ACTIVE, ActivityTrait.LOCOMOTIVE})
        social_tr = frozenset({ActivityTrait.SOCIAL, ActivityTrait.STATIONARY})
        play_tr = frozenset({ActivityTrait.ACTIVE, ActivityTrait.CASUAL})
        react_tr = frozenset({ActivityTrait.STATIONARY, ActivityTrait.CASUAL})
        work_tr = frozenset({
            ActivityTrait.QUIET,
            ActivityTrait.FOCUSED,
            ActivityTrait.STATIONARY,
        })

        atlas_mappings = [
            ("idle", BehaviorCategory.IDLE, idle_tr, BehaviorDirection.NONE),
            ("running_right", BehaviorCategory.MOVE, move_tr, BehaviorDirection.RIGHT),
            ("running_left", BehaviorCategory.MOVE, move_tr, BehaviorDirection.LEFT),
            ("waving", BehaviorCategory.GREET, social_tr, BehaviorDirection.NONE),
            ("jumping", BehaviorCategory.PLAY, play_tr, BehaviorDirection.NONE),
            ("failed", BehaviorCategory.REACT, react_tr, BehaviorDirection.NONE),
            ("waiting", BehaviorCategory.OBSERVE, idle_tr, BehaviorDirection.NONE),
            ("running", BehaviorCategory.MOVE, move_tr, BehaviorDirection.NONE),
            ("review", BehaviorCategory.WORK, work_tr, BehaviorDirection.NONE),
        ]

        for act_id, cat, traits, direction in atlas_mappings:
            capabilities.add(cat)
            activities.append(
                PetActivity(
                    id=f"{pid}_{act_id}",
                    category=cat,
                    visual=VisualBinding(ref=act_id.replace("_", "-"), format="spritesheet"),
                    traits=traits,
                    direction=direction,
                    loop=LoopMode.LOOP,
                )
            )

    return PetManifest(
        schema_version=2,
        id=pid,
        name=pname,
        description=pdesc,
        format=pformat,
        spritesheet_path=spritesheet_path,
        theme_path=theme_path,
        native_idle_path=native_idle_path,
        capabilities=frozenset(capabilities),
        activities=tuple(activities),
        metadata={"v1_adapted": True},
    )


def _map_v1_theme_state_to_semantics(
    state_name: str,
) -> tuple[BehaviorCategory, frozenset[ActivityTrait], BehaviorDirection]:
    """Map Clawd-on-Desk theme state names to WP-0 semantics."""
    s = state_name.lower().strip()
    if s in ("idle", "mini-idle"):
        return (
            BehaviorCategory.IDLE,
            frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY}),
            BehaviorDirection.NONE,
        )
    if s in ("sleeping", "mini-sleep", "dozing", "yawning", "collapsing"):
        return (
            BehaviorCategory.SLEEP if s in ("sleeping", "mini-sleep") else BehaviorCategory.REST,
            frozenset({ActivityTrait.QUIET, ActivityTrait.LOW_ENERGY, ActivityTrait.STATIONARY}),
            BehaviorDirection.NONE,
        )
    if s in ("roam", "mini-crabwalk", "mini-enter"):
        return (
            BehaviorCategory.MOVE,
            frozenset({ActivityTrait.ACTIVE, ActivityTrait.LOCOMOTIVE}),
            BehaviorDirection.NONE,
        )
    if s in ("working", "typing", "sweeping", "juggling", "carrying", "building", "conducting"):
        return (
            BehaviorCategory.WORK,
            frozenset({ActivityTrait.FOCUSED, ActivityTrait.STATIONARY}),
            BehaviorDirection.NONE,
        )
    if s in ("thinking", "mini-peek"):
        return (
            BehaviorCategory.OBSERVE,
            frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY}),
            BehaviorDirection.NONE,
        )
    if s in ("happy", "attention", "mini-happy"):
        return (
            BehaviorCategory.GREET,
            frozenset({ActivityTrait.SOCIAL, ActivityTrait.STATIONARY}),
            BehaviorDirection.NONE,
        )
    if s in ("error", "react-poke", "react-left", "react-drag", "mini-alert", "notification"):
        return (
            BehaviorCategory.REACT,
            frozenset({ActivityTrait.CASUAL, ActivityTrait.STATIONARY}),
            BehaviorDirection.NONE,
        )
    return (
        BehaviorCategory.IDLE,
        frozenset({ActivityTrait.QUIET, ActivityTrait.STATIONARY}),
        BehaviorDirection.NONE,
    )


def load_manifest_from_dict(
    data: Mapping[str, Any], pet_dir: Path | None = None
) -> PetManifest:
    """Load PetManifest from a dictionary, automatically handling V1 vs V2 formats."""
    schema_version = data.get("schema_version")
    if schema_version is None or int(schema_version) < 2:
        return adapt_v1_pet_dict(data, pet_dir)

    pid = str(data["id"]).strip()
    pname = str(data.get("name") or data.get("displayName") or pid).strip()
    pdesc = str(data.get("description", ""))

    raw_caps = data.get("capabilities", [])
    capabilities = frozenset(BehaviorCategory(c) for c in raw_caps)

    activities: list[PetActivity] = []
    for raw_act in data.get("activities", []):
        act_id = str(raw_act["id"])
        cat = BehaviorCategory(raw_act["category"])

        raw_visual = raw_act["visual"]
        visual = VisualBinding(
            ref=str(raw_visual["ref"]),
            format=raw_visual.get("format"),
            mirror=bool(raw_visual.get("mirror", False)),
        )

        raw_traits = raw_act.get("traits", [])
        traits = frozenset(ActivityTrait(t) for t in raw_traits)

        direction = BehaviorDirection(raw_act.get("direction", "none"))
        loop = LoopMode(raw_act.get("loop", "loop"))
        interruptible = bool(raw_act.get("interruptible", True))
        duration_ms = raw_act.get("duration_ms")
        weight = float(raw_act.get("weight", 1.0))
        tags = tuple(str(t) for t in raw_act.get("tags", ()))

        activities.append(
            PetActivity(
                id=act_id,
                category=cat,
                visual=visual,
                traits=traits,
                direction=direction,
                loop=loop,
                interruptible=interruptible,
                duration_ms=duration_ms,
                weight=weight,
                tags=tags,
            )
        )

    return PetManifest(
        schema_version=int(schema_version),
        id=pid,
        name=pname,
        description=pdesc,
        format=data.get("format"),
        spritesheet_path=data.get("spritesheet_path") or data.get("spritesheetPath"),
        theme_path=data.get("theme_path") or data.get("themePath"),
        native_idle_path=data.get("native_idle_path") or data.get("nativeIdlePath"),
        capabilities=capabilities,
        activities=tuple(activities),
        metadata=dict(data.get("metadata", {})),
    )


def load_pet_manifest(pet_dir: Path) -> PetManifest:
    """Load PetManifest from a pet directory containing `pet.json`."""
    pet_json = pet_dir / "pet.json"
    if not pet_json.is_file():
        msg = f"pet.json not found in pet directory '{pet_dir}'"
        raise FileNotFoundError(msg)

    data = json.loads(pet_json.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"pet.json content must be a JSON object, got {type(data).__name__}"
        raise TypeError(msg)

    return load_manifest_from_dict(data, pet_dir)


def validate_pet_directory(pet_dir: Path) -> ValidationResult:
    """Validate a pet directory end-to-end, parsing its manifest and checking files."""
    try:
        manifest = load_pet_manifest(pet_dir)
    except Exception as exc:
        return ValidationResult(
            valid=False,
            errors=(f"Failed to load pet manifest from '{pet_dir}': {exc}",),
            pet_id=pet_dir.name,
        )
    return validate_pet_manifest(manifest, pet_dir)
