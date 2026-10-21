"""Memory V2.1 feature flags, dependency matrix validation, and development diagnostics.

Part of Coeva Long-Term Memory V2.1 Stage 0 (WP-0).
Ensures all Memory V2 capabilities remain strictly OFF by default and that
illegal flag combinations fail closed during initialization (I-S05).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any

ENV_FLAG_PREFIX = "COEVA_FLAG_"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})

# Stage 0 default: zero V2 runtime capabilities are implemented
STAGE_0_CAPABILITIES: frozenset[str] = frozenset()

# Approved production capabilities available for V2 runtime routing
PRODUCTION_V2_CAPABILITIES: frozenset[str] = frozenset(
    {
        "storage_v2",
        "retrieval_v2",
        "consolidation_v2",
        "self_model_v2",
        "backfill_v2",
    }
)


class InvalidFlagConfigurationError(ValueError):
    """Raised when an illegal or unsupported combination of feature flags is configured (I-S05)."""

    pass


@dataclass(frozen=True)
class MemoryFeatureFlags:
    """Canonical definition of all Memory V2.1 feature flags.

    All flags strictly default to False (OFF).
    """

    memory_v2_storage: bool = False
    memory_v2_retrieval: bool = False
    memory_v2_consolidation: bool = False
    memory_v2_self_model: bool = False
    memory_v2_migration: bool = False
    memory_v2_backfill: bool = False

    def validate(
        self,
        *,
        runtime_mode: str = "companion",
        capabilities: frozenset[str] | None = None,
    ) -> None:
        """Validate feature flag dependency matrix, capability readiness, and runtime mode.

        Enforces:
        - Dependent capabilities cannot be enabled without prerequisites (I-S05).
        - Migration flag is maintenance-only and cannot run in normal companion runtime (S0-F01)
          or alongside active semantic flags (S0-F02).
        - Flag enabled != capability ready: enabling flags without capability fails closed (S0-F03).

        Raises:
            InvalidFlagConfigurationError: If any prerequisite or safety rule is violated.
        """
        # Rule 1: retrieval_v2 requires compatible storage/read capability
        if self.memory_v2_retrieval and not self.memory_v2_storage:
            raise InvalidFlagConfigurationError(
                "Invalid feature flag dependency: 'memory_v2_retrieval' is enabled "
                "but requires 'memory_v2_storage' to be enabled."
            )

        # Rule 2: consolidation_v2 requires storage capability
        if self.memory_v2_consolidation and not self.memory_v2_storage:
            raise InvalidFlagConfigurationError(
                "Invalid feature flag dependency: 'memory_v2_consolidation' is enabled "
                "but requires 'memory_v2_storage' to be enabled."
            )

        # Rule 3: self_model_v2 requires consolidation capability
        if self.memory_v2_self_model and not self.memory_v2_consolidation:
            raise InvalidFlagConfigurationError(
                "Invalid feature flag dependency: 'memory_v2_self_model' is enabled "
                "but requires 'memory_v2_consolidation' to be enabled."
            )

        # Rule 4: backfill_v2 requires both storage and consolidation capabilities
        has_storage_and_consolidation = self.memory_v2_storage and self.memory_v2_consolidation
        if self.memory_v2_backfill and not has_storage_and_consolidation:
            raise InvalidFlagConfigurationError(
                "Invalid feature flag dependency: 'memory_v2_backfill' is enabled "
                "but requires both 'memory_v2_storage' and 'memory_v2_consolidation' to be enabled."
            )

        # Rule 5: migration_v2 is maintenance-only and mutually constrained (S0-F01, S0-F02)
        if self.memory_v2_migration:
            if runtime_mode != "maintenance":
                raise InvalidFlagConfigurationError(
                    "Invalid feature flag configuration: 'memory_v2_migration' is "
                    f"maintenance-only and cannot be enabled during '{runtime_mode}' runtime."
                )
            has_incompatible_semantic_flags = any(
                [
                    self.memory_v2_retrieval,
                    self.memory_v2_consolidation,
                    self.memory_v2_self_model,
                    self.memory_v2_backfill,
                ]
            )
            if has_incompatible_semantic_flags:
                raise InvalidFlagConfigurationError(
                    "Invalid feature flag combination: 'memory_v2_migration' is maintenance-only "
                    "and cannot coexist with active semantic flags (retrieval, consolidation, "
                    "self_model, backfill)."
                )

        # Rule 6: Flag enabled != capability ready guard (S0-F03)
        if capabilities is not None:
            if self.memory_v2_storage and "storage_v2" not in capabilities:
                raise InvalidFlagConfigurationError(
                    "Capability 'storage_v2' is not implemented or ready in current runtime "
                    "(FLAG ENABLED != CAPABILITY READY)."
                )
            if self.memory_v2_retrieval and "retrieval_v2" not in capabilities:
                raise InvalidFlagConfigurationError(
                    "Capability 'retrieval_v2' is not implemented or ready in current runtime."
                )
            if self.memory_v2_consolidation and "consolidation_v2" not in capabilities:
                raise InvalidFlagConfigurationError(
                    "Capability 'consolidation_v2' is not implemented or ready in current runtime."
                )
            if self.memory_v2_self_model and "self_model_v2" not in capabilities:
                raise InvalidFlagConfigurationError(
                    "Capability 'self_model_v2' is not implemented or ready in current runtime."
                )
            if self.memory_v2_backfill and "backfill_v2" not in capabilities:
                raise InvalidFlagConfigurationError(
                    "Capability 'backfill_v2' is not implemented or ready in current runtime."
                )

    def to_dict(self) -> dict[str, bool]:
        """Return dictionary representation of all flags."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MemoryFeatureFlags:
        """Instantiate flags from an arbitrary dictionary (e.g. settings file)."""
        if not data:
            return cls()

        return cls(
            memory_v2_storage=bool(data.get("memory_v2_storage", False)),
            memory_v2_retrieval=bool(data.get("memory_v2_retrieval", False)),
            memory_v2_consolidation=bool(data.get("memory_v2_consolidation", False)),
            memory_v2_self_model=bool(data.get("memory_v2_self_model", False)),
            memory_v2_migration=bool(data.get("memory_v2_migration", False)),
            memory_v2_backfill=bool(data.get("memory_v2_backfill", False)),
        )


def _parse_bool_env(env_name: str) -> bool | None:
    """Parse environment variable into boolean or None if not set.

    Raises InvalidFlagConfigurationError if an invalid or ambiguous value is provided (S0-F06).
    """
    val = os.environ.get(env_name)
    if val is None:
        return None
    val_clean = val.strip().lower()
    if val_clean in _TRUE_VALUES:
        return True
    if val_clean in _FALSE_VALUES:
        return False
    raise InvalidFlagConfigurationError(
        f"Invalid boolean environment variable value for {env_name}: {val!r}. "
        "Expected one of true/false/1/0/yes/no/on/off."
    )


# Global test override holder
_OVERRIDDEN_FLAGS: MemoryFeatureFlags | None = None


def resolve_flags(settings_dict: dict[str, Any] | None = None) -> MemoryFeatureFlags:
    """Resolve active feature flags following the strict precedence hierarchy:

    1. Default: All False
    2. Settings dict (e.g. from agent_settings.json)
    3. Environment variables (COEVA_FLAG_*)
    4. Active test override context (highest precedence for unit tests)

    Enforces validation on the final resolved instance before returning.
    """
    global _OVERRIDDEN_FLAGS
    if _OVERRIDDEN_FLAGS is not None:
        _OVERRIDDEN_FLAGS.validate()
        return _OVERRIDDEN_FLAGS

    # 1. Base from settings or defaults
    base = MemoryFeatureFlags.from_dict(settings_dict)

    # 2. Layer environment variable overrides
    env_storage = _parse_bool_env(f"{ENV_FLAG_PREFIX}MEMORY_V2_STORAGE")
    env_retrieval = _parse_bool_env(f"{ENV_FLAG_PREFIX}MEMORY_V2_RETRIEVAL")
    env_consolidation = _parse_bool_env(f"{ENV_FLAG_PREFIX}MEMORY_V2_CONSOLIDATION")
    env_self_model = _parse_bool_env(f"{ENV_FLAG_PREFIX}MEMORY_V2_SELF_MODEL")
    env_migration = _parse_bool_env(f"{ENV_FLAG_PREFIX}MEMORY_V2_MIGRATION")
    env_backfill = _parse_bool_env(f"{ENV_FLAG_PREFIX}MEMORY_V2_BACKFILL")

    resolved = MemoryFeatureFlags(
        memory_v2_storage=base.memory_v2_storage if env_storage is None else env_storage,
        memory_v2_retrieval=base.memory_v2_retrieval if env_retrieval is None else env_retrieval,
        memory_v2_consolidation=(
            base.memory_v2_consolidation if env_consolidation is None else env_consolidation
        ),
        memory_v2_self_model=(
            base.memory_v2_self_model if env_self_model is None else env_self_model
        ),
        memory_v2_migration=base.memory_v2_migration if env_migration is None else env_migration,
        memory_v2_backfill=base.memory_v2_backfill if env_backfill is None else env_backfill,
    )

    resolved.validate()
    return resolved


@contextmanager
def override_flags(**overrides: bool) -> Iterator[MemoryFeatureFlags]:
    """Context manager for tests to temporarily override active feature flags.

    Example:
        with override_flags(memory_v2_storage=True):
            ...
    """
    global _OVERRIDDEN_FLAGS
    prev = _OVERRIDDEN_FLAGS

    # Compute target flags
    current = resolve_flags() if prev is None else prev
    d = current.to_dict()
    d.update(overrides)
    target = MemoryFeatureFlags.from_dict(d)
    target.validate()

    _OVERRIDDEN_FLAGS = target
    try:
        yield target
    finally:
        _OVERRIDDEN_FLAGS = prev


def validate_memory_v2_configuration(
    flags: MemoryFeatureFlags | None = None,
    settings_dict: dict[str, Any] | None = None,
    *,
    runtime_mode: str = "companion",
    capabilities: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Thin startup validator for Memory V2 configuration (DEV observability).

    Does not print sensitive prompts, user content, or secrets.

    Returns:
        Structured diagnostic summary dictionary.

    Raises:
        InvalidFlagConfigurationError: If illegal combination detected.
    """
    active = flags if flags is not None else resolve_flags(settings_dict)
    # Stage 0 default: no V2 capabilities ready yet unless explicitly declared
    active_capabilities = capabilities if capabilities is not None else STAGE_0_CAPABILITIES
    active.validate(runtime_mode=runtime_mode, capabilities=active_capabilities)

    selected_path = "v2" if active.memory_v2_storage else "v1"

    return {
        "status": "VALID",
        "selected_path": selected_path,
        "flags": active.to_dict(),
        "runtime_mode": runtime_mode,
    }
