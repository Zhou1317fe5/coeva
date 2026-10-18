"""Tests for Memory V2.1 feature flag dependency validation matrix and Fail-Closed enforcement.

Part of Stage 0 (WP-0, I-S05).
Covers S0-F01 ~ S0-F07 audit assertions.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.connectors.settings import AgentSettingsStore
from src.core.flags import (
    ENV_FLAG_PREFIX,
    InvalidFlagConfigurationError,
    MemoryFeatureFlags,
    override_flags,
    resolve_flags,
    validate_memory_v2_configuration,
)


def test_illegal_retrieval_without_storage_fails_closed() -> None:
    """I-S05: retrieval_v2 cannot be enabled if storage_v2 is disabled."""
    flags = MemoryFeatureFlags(memory_v2_retrieval=True, memory_v2_storage=False)
    with pytest.raises(InvalidFlagConfigurationError) as exc_info:
        flags.validate()
    assert "memory_v2_retrieval" in str(exc_info.value)
    assert "memory_v2_storage" in str(exc_info.value)


def test_illegal_consolidation_without_storage_fails_closed() -> None:
    """I-S05: consolidation_v2 cannot be enabled if storage_v2 is disabled."""
    flags = MemoryFeatureFlags(memory_v2_consolidation=True, memory_v2_storage=False)
    with pytest.raises(InvalidFlagConfigurationError) as exc_info:
        flags.validate()
    assert "memory_v2_consolidation" in str(exc_info.value)
    assert "memory_v2_storage" in str(exc_info.value)


def test_illegal_self_model_without_consolidation_fails_closed() -> None:
    """I-S05: self_model_v2 cannot be enabled if consolidation_v2 is disabled."""
    flags = MemoryFeatureFlags(
        memory_v2_storage=True,
        memory_v2_consolidation=False,
        memory_v2_self_model=True,
    )
    with pytest.raises(InvalidFlagConfigurationError) as exc_info:
        flags.validate()
    assert "memory_v2_self_model" in str(exc_info.value)
    assert "memory_v2_consolidation" in str(exc_info.value)


def test_illegal_backfill_without_storage_or_consolidation_fails_closed() -> None:
    """I-S05: backfill_v2 requires both storage and consolidation."""
    with pytest.raises(InvalidFlagConfigurationError):
        MemoryFeatureFlags(memory_v2_backfill=True).validate()

    with pytest.raises(InvalidFlagConfigurationError):
        MemoryFeatureFlags(memory_v2_storage=True, memory_v2_backfill=True).validate()

    with pytest.raises(InvalidFlagConfigurationError):
        MemoryFeatureFlags(memory_v2_consolidation=True, memory_v2_backfill=True).validate()


# ─────────────────────────────────────────────────────────────────────────────
# S0-F01 ~ S0-F07 Specific Audit Assertions
# ─────────────────────────────────────────────────────────────────────────────


def test_s0_f01_normal_runtime_migration_flag_fails_closed() -> None:
    """S0-F01: normal runtime + migration=true -> Fail-Closed."""
    flags = MemoryFeatureFlags(memory_v2_migration=True)

    # 1. Direct validation under companion runtime
    with pytest.raises(InvalidFlagConfigurationError) as exc_info:
        flags.validate(runtime_mode="companion")
    assert "maintenance-only" in str(exc_info.value)

    # 2. Startup validation under companion runtime
    with pytest.raises(InvalidFlagConfigurationError):
        validate_memory_v2_configuration(flags, runtime_mode="companion")


def test_s0_f02_maintenance_runtime_with_incompatible_semantic_flags_fails_closed() -> None:
    """S0-F02: maintenance runtime + incompatible semantic flags -> Fail-Closed."""
    # Migration is maintenance-only and cannot coexist with active runtime semantic flags
    flags_with_retrieval = MemoryFeatureFlags(
        memory_v2_migration=True,
        memory_v2_storage=True,
        memory_v2_retrieval=True,
    )
    with pytest.raises(InvalidFlagConfigurationError) as exc_info:
        flags_with_retrieval.validate(runtime_mode="maintenance")
    assert "cannot coexist with active semantic flags" in str(exc_info.value)

    flags_with_consolidation = MemoryFeatureFlags(
        memory_v2_migration=True,
        memory_v2_storage=True,
        memory_v2_consolidation=True,
    )
    with pytest.raises(InvalidFlagConfigurationError):
        flags_with_consolidation.validate(runtime_mode="maintenance")

    # Pure migration flag in maintenance mode is allowed
    pure_migration = MemoryFeatureFlags(memory_v2_migration=True)
    pure_migration.validate(runtime_mode="maintenance")


def test_s0_f03_storage_flag_without_storage_capability_fails_closed() -> None:
    """S0-F03: storage flag=true + storage capability=false -> Fail-Closed."""
    flags = MemoryFeatureFlags(memory_v2_storage=True)

    # In Stage 0, declared capabilities are empty (storage_v2 not yet implemented)
    with pytest.raises(InvalidFlagConfigurationError) as exc_info:
        flags.validate(capabilities=frozenset())
    assert "Capability 'storage_v2' is not implemented or ready" in str(exc_info.value)

    # Also startup validator must fail closed
    with pytest.raises(InvalidFlagConfigurationError):
        validate_memory_v2_configuration(flags, capabilities=frozenset())


def test_s0_f04_all_flags_off_with_capabilities_unavailable_selects_v1() -> None:
    """S0-F04: all flags OFF + capabilities unavailable -> selected_path=v1."""
    flags = MemoryFeatureFlags()
    diag = validate_memory_v2_configuration(flags, capabilities=frozenset())
    assert diag["status"] == "VALID"
    assert diag["selected_path"] == "v1"
    assert diag["flags"]["memory_v2_storage"] is False


def test_s0_f05_invalid_settings_update_fails_closed_and_leaves_persisted_file_unchanged() -> None:
    """S0-F05: invalid settings update -> raises -> persisted settings unchanged."""
    with TemporaryDirectory() as tmpdir:
        tmp_settings = Path(tmpdir) / "agent_settings.json"
        store = AgentSettingsStore(tmp_settings)

        # Baseline: all flags False on disk
        with open(tmp_settings, encoding="utf-8") as f:
            initial_raw = json.load(f)
        assert initial_raw["memory_v2_flags"]["memory_v2_storage"] is False
        assert initial_raw["memory_v2_flags"]["memory_v2_retrieval"] is False

        # Attempt illegal update: enable retrieval without storage
        with pytest.raises(InvalidFlagConfigurationError):
            store.set_memory_v2_flag("memory_v2_retrieval", True)

        # In-memory property must remain False
        assert store.memory_v2_flags.memory_v2_retrieval is False

        # Disk file must be strictly unchanged
        with open(tmp_settings, encoding="utf-8") as f:
            post_attempt_raw = json.load(f)
        assert post_attempt_raw["memory_v2_flags"] == initial_raw["memory_v2_flags"]
        assert post_attempt_raw["memory_v2_flags"]["memory_v2_retrieval"] is False


def test_s0_f06_invalid_env_boolean_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """S0-F06: invalid env boolean -> Fail-Closed (does not silently parse as False)."""
    # 1. Ambiguous/illegal value 'maybe'
    monkeypatch.setenv(f"{ENV_FLAG_PREFIX}MEMORY_V2_STORAGE", "maybe")
    with pytest.raises(InvalidFlagConfigurationError) as exc_info:
        resolve_flags()
    assert "Invalid boolean environment variable value" in str(exc_info.value)
    assert "maybe" in str(exc_info.value)

    # 2. Typo 'tru'
    monkeypatch.setenv(f"{ENV_FLAG_PREFIX}MEMORY_V2_STORAGE", "tru")
    with pytest.raises(InvalidFlagConfigurationError) as exc_info:
        resolve_flags()
    assert "tru" in str(exc_info.value)


def test_s0_f07_override_flags_scope_exits_restores_config_and_leaves_file_untouched() -> None:
    """S0-F07: override_flags exits -> original config restored -> persisted file unchanged."""
    with TemporaryDirectory() as tmpdir:
        tmp_settings = Path(tmpdir) / "agent_settings.json"
        store = AgentSettingsStore(tmp_settings)
        assert store.memory_v2_flags.memory_v2_storage is False

        with open(tmp_settings, encoding="utf-8") as f:
            disk_before = json.load(f)

        assert resolve_flags().memory_v2_storage is False

        # Enter scoped override
        with override_flags(memory_v2_storage=True):
            assert resolve_flags().memory_v2_storage is True
            # Verify file on disk was NOT touched by test override
            with open(tmp_settings, encoding="utf-8") as f:
                disk_during = json.load(f)
            assert disk_during["memory_v2_flags"]["memory_v2_storage"] is False

        # Scope exited: must be cleanly restored to False
        assert resolve_flags().memory_v2_storage is False

        # File on disk remains intact
        with open(tmp_settings, encoding="utf-8") as f:
            disk_after = json.load(f)
        assert disk_after == disk_before
