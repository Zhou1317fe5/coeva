"""Tests for Memory V2.1 feature flag definitions, hierarchy, and overrides.

Part of Stage 0 (WP-0).
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.connectors.settings import AgentSettingsStore
from src.core.flags import (
    ENV_FLAG_PREFIX,
    MemoryFeatureFlags,
    override_flags,
    resolve_flags,
)


def test_default_all_flags_off() -> None:
    """Verify that all Memory V2.1 feature flags default to False (OFF)."""
    flags = MemoryFeatureFlags()
    assert flags.memory_v2_storage is False
    assert flags.memory_v2_retrieval is False
    assert flags.memory_v2_consolidation is False
    assert flags.memory_v2_self_model is False
    assert flags.memory_v2_migration is False
    assert flags.memory_v2_backfill is False
    # Validation must pass cleanly for all-off
    flags.validate()


def test_from_dict_and_to_dict() -> None:
    """Verify serialization to and from dictionary."""
    data = {
        "memory_v2_storage": True,
        "memory_v2_retrieval": False,
        "memory_v2_consolidation": False,
        "memory_v2_self_model": False,
        "memory_v2_migration": False,
        "memory_v2_backfill": False,
    }
    flags = MemoryFeatureFlags.from_dict(data)
    assert flags.memory_v2_storage is True
    assert flags.memory_v2_retrieval is False
    assert flags.to_dict()["memory_v2_storage"] is True


def test_environment_variable_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that environment variables (COEVA_FLAG_*) take precedence over defaults."""
    monkeypatch.setenv(f"{ENV_FLAG_PREFIX}MEMORY_V2_STORAGE", "1")
    monkeypatch.setenv(f"{ENV_FLAG_PREFIX}MEMORY_V2_RETRIEVAL", "true")

    flags = resolve_flags()
    assert flags.memory_v2_storage is True
    assert flags.memory_v2_retrieval is True
    assert flags.memory_v2_consolidation is False


def test_override_flags_context_manager() -> None:
    """Verify that override_flags context manager modifies active flags safely and restores."""
    assert resolve_flags().memory_v2_storage is False

    with override_flags(memory_v2_storage=True):
        assert resolve_flags().memory_v2_storage is True

    # Must be restored after context exit
    assert resolve_flags().memory_v2_storage is False


def test_agent_settings_store_persistence() -> None:
    """Verify that AgentSettingsStore loads, persists, and updates feature flags."""
    with TemporaryDirectory() as tmpdir:
        tmp_settings = Path(tmpdir) / "agent_settings.json"
        store = AgentSettingsStore(tmp_settings)

        # Defaults should be all False
        assert store.memory_v2_flags.memory_v2_storage is False

        # Set storage flag and verify persistence
        store.set_memory_v2_flag("memory_v2_storage", True)
        assert store.memory_v2_flags.memory_v2_storage is True

        # Re-read from disk
        store2 = AgentSettingsStore(tmp_settings)
        assert store2.memory_v2_flags.memory_v2_storage is True
        assert store2.memory_v2_flags.memory_v2_retrieval is False

        with pytest.raises(KeyError):
            store2.set_memory_v2_flag("non_existent_flag", True)
