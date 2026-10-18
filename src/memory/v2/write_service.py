"""Raw Evidence Write Service for Coeva Memory V2.1 (Stage 2).

Provides validated, durable, idempotent, and privacy-sanitized write pathways for:
- User Slices (RawSliceEntity, Entity 1)
- Agent Event Skeletons (EventSkeletonEntity, Entity 2)

Core Invariants Enforced:
- ACKED WRITE MUST BE DURABLE: Success returned ONLY after SQLite commit.
- PRIVACY BOUNDARY: Prompts, CoT, tool outputs, stacktraces strictly stripped.
- WRITE IDEMPOTENCY: Same ID/key + same payload -> idempotent success.
- CONFLICT FAIL-CLOSED: Same ID/key + different payload -> raises WriteConflictError.
- CONTENT FIDELITY: Raw slice text preserved without LLM modification.
- NO DERIVED SIDE-EFFECTS: Raw evidence write does NOT alter derived memory tables.
- NO ROWID IDENTITY: Uses canonical UUID/hash identities exclusively.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from src.memory.v2.entities import (
    EventSkeletonEntity,
    RawSliceEntity,
    RawSliceSource,
    RetentionClass,
    Scope,
)
from src.memory.v2.store import ChronicleStoreV2


class WriteConflictError(Exception):
    """Raised when an incoming write conflicts with existing data of same identity (W-S07)."""

    pass


class WriteDurabilityError(Exception):
    """Raised when a raw evidence write fails to commit durably to SQLite (W-S02)."""

    pass


@dataclass(frozen=True)
class WriteSliceCommand:
    """Command to persist a canonical raw user slice."""

    content: str
    occurred_at: str | datetime | None = None
    source: RawSliceSource = "manual_feed"
    scope: Scope = "unresolved"
    project_id: str | None = None
    slice_id: str | None = None
    ingestion_dedup_key: str | None = None


@dataclass(frozen=True)
class WriteSliceResult:
    """Structured result of a raw slice write operation."""

    status: Literal["committed", "idempotent_replay"]
    entity: RawSliceEntity
    was_persisted: bool
    duration_ms: float


@dataclass(frozen=True)
class WriteEventCommand:
    """Command to persist an agent behavior telemetry event skeleton (privacy-sanitized)."""

    agent_id: str
    session_id: str
    event_type: str
    occurred_at: str | datetime | None = None
    tool_name: str = ""
    error_category: str = ""
    retention_class: RetentionClass = "transient"
    event_id: str | None = None


@dataclass(frozen=True)
class WriteEventResult:
    """Structured result of an event skeleton write operation."""

    status: Literal["committed", "idempotent_replay"]
    entity: EventSkeletonEntity
    was_persisted: bool
    duration_ms: float


class RawEvidenceWriteService:
    """Durable write service for canonical raw evidence (V2.1 Storage)."""

    def __init__(self, store: ChronicleStoreV2) -> None:
        self._store = store

    # ── User Slice Write Pipeline ────────────────────────────────────────────

    def write_slice(
        self,
        command: WriteSliceCommand | None = None,
        *,
        content: str | None = None,
        occurred_at: str | datetime | None = None,
        source: RawSliceSource = "manual_feed",
        scope: Scope = "unresolved",
        project_id: str | None = None,
        slice_id: str | None = None,
        ingestion_dedup_key: str | None = None,
    ) -> WriteSliceResult:
        """Write a canonical raw user slice, verifying idempotency and durability.

        Returns:
            WriteSliceResult with status='committed' or 'idempotent_replay'.

        Raises:
            WriteConflictError: If same slice_id or dedup_key exists with differing payload.
            WriteDurabilityError: If transaction fails to commit durably.
        """
        start_time = time.perf_counter()

        cmd = command or WriteSliceCommand(
            content=content or "",
            occurred_at=occurred_at,
            source=source,
            scope=scope,
            project_id=project_id,
            slice_id=slice_id,
            ingestion_dedup_key=ingestion_dedup_key,
        )

        # 1. Normalization & Content Fidelity
        # Preserve content byte-for-byte (INV-1: Evidence != Interpretation)
        raw_content = cmd.content

        # 2. Scope & Project ID Normalization (W-S04)
        norm_scope = cmd.scope
        norm_project_id: str | None = None

        if norm_scope == "global":
            norm_project_id = "global"
        elif norm_scope == "project":
            if cmd.project_id and cmd.project_id.strip():
                norm_project_id = cmd.project_id.strip()
            else:
                # Unknown / unassigned project fails safe to 'unresolved', NOT global
                norm_scope = "unresolved"
                norm_project_id = None
        else:  # unresolved or default
            norm_scope = "unresolved"
            norm_project_id = None

        # 3. Timestamp Normalization
        if isinstance(cmd.occurred_at, datetime):
            norm_occurred = cmd.occurred_at.astimezone(UTC).isoformat()
        elif isinstance(cmd.occurred_at, str) and cmd.occurred_at.strip():
            norm_occurred = cmd.occurred_at.strip()
        else:
            norm_occurred = datetime.now(UTC).isoformat()

        # 4. Identity & Ingestion Dedup Key Construction
        final_slice_id = cmd.slice_id or f"slice_{uuid4().hex}"
        if cmd.ingestion_dedup_key and cmd.ingestion_dedup_key.strip():
            final_dedup_key = cmd.ingestion_dedup_key.strip()
        else:
            # Deterministic SHA-256 fingerprint for write idempotency
            raw_hash_input = f"user:{cmd.source}:{raw_content}:{norm_occurred}".encode()
            final_dedup_key = hashlib.sha256(raw_hash_input).hexdigest()

        # 5. Idempotency & Conflict Check (W-S06, W-S07)
        # Check by slice_id first
        existing_by_id = self._store.get_raw_slice(final_slice_id)
        # Check by dedup_key
        existing_by_key = self._store.get_raw_slice_by_dedup_key(final_dedup_key)

        existing = existing_by_id or existing_by_key
        if existing is not None:
            # Verify payload equality
            payload_matches = (
                existing.content == raw_content
                and existing.source == cmd.source
                and existing.scope == norm_scope
                and existing.project_id == norm_project_id
            )
            if payload_matches:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return WriteSliceResult(
                    status="idempotent_replay",
                    entity=existing,
                    was_persisted=False,
                    duration_ms=duration_ms,
                )
            else:
                # Same identity but conflicting payload -> Fail-Closed
                raise WriteConflictError(
                    f"Write conflict on slice: existing payload for ID '{existing.slice_id}' "
                    f"differs from incoming write payload (W-S07)."
                )

        # 6. Construct Entity
        entity = RawSliceEntity(
            slice_id=final_slice_id,
            occurred_at=norm_occurred,
            content=raw_content,
            actor="user",
            source=cmd.source,
            scope=norm_scope,
            project_id=norm_project_id,
            ingestion_dedup_key=final_dedup_key,
            created_at=datetime.now(UTC).isoformat(),
        )

        # 7. Durable Commit Boundary (W-S01, W-S02: ACKED WRITE MUST BE DURABLE)
        try:
            with self._store.transaction():
                self._store.insert_raw_slice(entity)
        except Exception as exc:
            raise WriteDurabilityError(
                f"Failed to commit raw slice '{final_slice_id}' durably: {exc}"
            ) from exc

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return WriteSliceResult(
            status="committed",
            entity=entity,
            was_persisted=True,
            duration_ms=duration_ms,
        )

    # ── Event Skeleton Write Pipeline ────────────────────────────────────────

    def write_event(
        self,
        command: WriteEventCommand | None = None,
        *,
        agent_id: str = "",
        session_id: str = "",
        event_type: str = "",
        occurred_at: str | datetime | None = None,
        tool_name: str = "",
        error_category: str = "",
        retention_class: RetentionClass = "transient",
        event_id: str | None = None,
        **extra_payload_to_sanitize: Any,
    ) -> WriteEventResult:
        """Write an external agent behavior telemetry skeleton.

        Strictly enforces the Privacy Boundary (W-S05):
        Prompts, CoT, tool result bodies, stacktraces, or arbitrary JSON
        are permanently stripped and discarded before persistence.

        Returns:
            WriteEventResult with status='committed' or 'idempotent_replay'.

        Raises:
            WriteConflictError: If same event_id exists with differing payload.
            WriteDurabilityError: If transaction fails to commit durably.
        """
        start_time = time.perf_counter()

        cmd = command or WriteEventCommand(
            agent_id=agent_id,
            session_id=session_id,
            event_type=event_type,
            occurred_at=occurred_at,
            tool_name=tool_name,
            error_category=error_category,
            retention_class=retention_class,
            event_id=event_id,
        )

        # Privacy boundary: extra_payload_to_sanitize is intentionally ignored/dropped
        _ = extra_payload_to_sanitize

        # 1. Timestamp Normalization
        if isinstance(cmd.occurred_at, datetime):
            norm_occurred = cmd.occurred_at.astimezone(UTC).isoformat()
        elif isinstance(cmd.occurred_at, str) and cmd.occurred_at.strip():
            norm_occurred = cmd.occurred_at.strip()
        else:
            norm_occurred = datetime.now(UTC).isoformat()

        final_event_id = cmd.event_id or f"evt_{uuid4().hex}"

        # 2. Idempotency Check (W-S06, W-S07)
        existing = self._store.get_event_skeleton(final_event_id)
        if existing is not None:
            payload_matches = (
                existing.agent_id == cmd.agent_id
                and existing.session_id == cmd.session_id
                and existing.event_type == cmd.event_type
                and existing.tool_name == cmd.tool_name
                and existing.error_category == cmd.error_category
                and existing.retention_class == cmd.retention_class
            )
            if payload_matches:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return WriteEventResult(
                    status="idempotent_replay",
                    entity=existing,
                    was_persisted=False,
                    duration_ms=duration_ms,
                )
            else:
                raise WriteConflictError(
                    f"Write conflict on event skeleton: existing payload for ID '{final_event_id}' "
                    f"differs from incoming write payload (W-S07)."
                )

        # 3. Construct Privacy-Sanitized Skeleton
        entity = EventSkeletonEntity(
            event_id=final_event_id,
            occurred_at=norm_occurred,
            agent_id=cmd.agent_id,
            session_id=cmd.session_id,
            event_type=cmd.event_type,
            tool_name=cmd.tool_name,
            error_category=cmd.error_category,
            retention_class=cmd.retention_class,
            created_at=datetime.now(UTC).isoformat(),
        )

        # 4. Durable Commit Boundary (W-S01, W-S02)
        try:
            with self._store.transaction():
                self._store.insert_event_skeleton(entity)
        except Exception as exc:
            raise WriteDurabilityError(
                f"Failed to commit event skeleton '{final_event_id}' durably: {exc}"
            ) from exc

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return WriteEventResult(
            status="committed",
            entity=entity,
            was_persisted=True,
            duration_ms=duration_ms,
        )
