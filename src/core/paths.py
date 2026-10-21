"""Production and workspace path resolution helpers for Coeva Companion.

Part of WP-14 Phase A.5 (Production Runtime Deployment Proof).
Guarantees unambiguous path resolution between worktree code roots and
the canonical production data directory.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_DATA_DIR = "COEVA_DATA_DIR"
CANONICAL_PROD_DATA_DIR = Path("D:/CodeProjects/co-evolving-companion/data").resolve()


def get_data_dir(custom_path: Path | str | None = None) -> Path:
    """Resolve the authoritative production data root directory.

    Precedence:
    1. Explicit custom_path argument (e.g. from --data-dir CLI argument or programmatic caller).
    2. Environment variable COEVA_DATA_DIR.
    3. Canonical production data directory (D:/CodeProjects/co-evolving-companion/data)
       if it exists on disk.
    4. Local ./data directory (relative to current working directory).
    """
    if custom_path is not None:
        p = Path(custom_path).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    env_val = os.environ.get(ENV_DATA_DIR)
    if env_val:
        p = Path(env_val).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    if CANONICAL_PROD_DATA_DIR.is_dir():
        return CANONICAL_PROD_DATA_DIR

    local_data = Path("data").resolve()
    local_data.mkdir(parents=True, exist_ok=True)
    return local_data


def get_db_path(custom_data_dir: Path | str | None = None) -> Path:
    """Resolve path to companion_chronicle.db."""
    return get_data_dir(custom_data_dir) / "companion_chronicle.db"


def get_jsonl_path(custom_data_dir: Path | str | None = None) -> Path:
    """Resolve path to raw_slices.jsonl."""
    return get_data_dir(custom_data_dir) / "raw_slices.jsonl"


def get_settings_path(custom_data_dir: Path | str | None = None) -> Path:
    """Resolve path to agent_settings.json."""
    return get_data_dir(custom_data_dir) / "agent_settings.json"


def get_chapters_dir(custom_data_dir: Path | str | None = None) -> Path:
    """Resolve path to chapters/ directory."""
    d = get_data_dir(custom_data_dir) / "chapters"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_first_seen_path(custom_data_dir: Path | str | None = None) -> Path:
    """Resolve path to first_seen.json."""
    return get_data_dir(custom_data_dir) / "first_seen.json"


def get_body_position_path(custom_data_dir: Path | str | None = None) -> Path:
    """Resolve path to body_position.json."""
    return get_data_dir(custom_data_dir) / "body_position.json"


def get_feeder_position_path(custom_data_dir: Path | str | None = None) -> Path:
    """Resolve path to feeder_position.json."""
    return get_data_dir(custom_data_dir) / "feeder_position.json"
