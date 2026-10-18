"""Routing boundary abstraction between legacy V1 storage and V2.1 Write Service.

Part of Stage 2 (WP-2).
Enforces:
- Normal companion runtime defaults strictly to legacy V1 storage path (W-S09).
- Explicit isolated Stage 2 test runtime with storage capability routes to V2 (W-S10).
- Production DB remains 100% untouched pre-cutover (W-S11).
"""

from __future__ import annotations

from typing import Any

from src.core.flags import MemoryFeatureFlags, resolve_flags
from src.memory.v2.write_service import RawEvidenceWriteService


class RawEvidenceRouter:
    """Thin router delegating evidence writes to V1 or V2 according to active feature flags."""

    def __init__(
        self,
        flags: MemoryFeatureFlags | None = None,
        *,
        v1_store: Any = None,
        v2_service: RawEvidenceWriteService | None = None,
    ) -> None:
        self._flags = flags if flags is not None else resolve_flags()
        self._v1_store = v1_store
        self._v2_service = v2_service

    @property
    def is_v2_active(self) -> bool:
        """Return True only if memory_v2_storage flag is ON and V2 service is bound."""
        return bool(self._flags.memory_v2_storage and self._v2_service is not None)

    @property
    def active_route(self) -> str:
        """Return human-readable identifier of active route ('v1_legacy' or 'v2_canonical')."""
        return "v2_canonical" if self.is_v2_active else "v1_legacy"

    @property
    def v1_store(self) -> Any:
        return self._v1_store

    @property
    def v2_service(self) -> RawEvidenceWriteService | None:
        return self._v2_service
