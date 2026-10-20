"""Standalone maintenance entry point for Coeva Long-Term Memory V2.1 Migration Tool."""

from __future__ import annotations

import sys

from src.memory.v2.migration.cli import main

if __name__ == "__main__":
    sys.exit(main())
