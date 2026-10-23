"""Behavior system package for Coeva (Phase 2.5).

Exports the core semantics layer (WP-0), Pet Manifest & Capability contract (WP-1),
Activity Registry & Fallback resolver (WP-3), Behavior Arbiter (WP-4),
Life Scheduler (WP-5), and Context Modulation (WP-6).
"""

from __future__ import annotations

from src.core.behavior.arbiter import (
    ArbiterAction,
    BehaviorArbiter,
    BehaviorDecision,
    BehaviorPriority,
    BehaviorRequest,
    BehaviorSource,
    ProtectionLevel,
    TransitionRecord,
)
from src.core.behavior.context import (
    ContextModulator,
    LifeContext,
    SchedulerModulation,
)
from src.core.behavior.manifest import (
    LoopMode,
    PetActivity,
    PetManifest,
    ValidationResult,
    VisualBinding,
    adapt_v1_pet_dict,
    load_manifest_from_dict,
    load_pet_manifest,
    validate_pet_directory,
    validate_pet_manifest,
)
from src.core.behavior.registry import (
    ActivityRegistry,
    ActivityResolution,
    ResolvedCandidate,
)
from src.core.behavior.scheduler import (
    AUTONOMOUS_CATEGORIES,
    AutonomousHistoryEntry,
    LifeScheduler,
    SchedulerConfig,
)
from src.core.behavior.semantics import (
    OPTIONAL_BEHAVIOR_CATEGORIES,
    REQUIRED_BEHAVIOR_CATEGORIES,
    SEMANTIC_FALLBACK_CHAINS,
    ActivityTrait,
    BehaviorCategory,
    BehaviorDirection,
    BehaviorIntent,
    resolve_semantic_fallback,
)

__all__ = [
    "AUTONOMOUS_CATEGORIES",
    "OPTIONAL_BEHAVIOR_CATEGORIES",
    "REQUIRED_BEHAVIOR_CATEGORIES",
    "SEMANTIC_FALLBACK_CHAINS",
    "ActivityRegistry",
    "ActivityResolution",
    "ActivityTrait",
    "ArbiterAction",
    "AutonomousHistoryEntry",
    "BehaviorArbiter",
    "BehaviorCategory",
    "BehaviorDecision",
    "BehaviorDirection",
    "BehaviorIntent",
    "BehaviorPriority",
    "BehaviorRequest",
    "BehaviorSource",
    "ContextModulator",
    "LifeContext",
    "LifeScheduler",
    "LoopMode",
    "PetActivity",
    "PetManifest",
    "ProtectionLevel",
    "ResolvedCandidate",
    "SchedulerConfig",
    "SchedulerModulation",
    "TransitionRecord",
    "ValidationResult",
    "VisualBinding",
    "adapt_v1_pet_dict",
    "load_manifest_from_dict",
    "load_pet_manifest",
    "resolve_semantic_fallback",
    "validate_pet_directory",
    "validate_pet_manifest",
]
