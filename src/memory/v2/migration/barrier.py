"""Option A Hard Quiesce MigrationBarrier for Memory V2.1.

Enforces the core invariant:
ACKED WRITE MUST BE DURABLE (M-S17, M-S18).

During migration quiescence:
- User Slices: blocked until migration completes OR rejected with
  transient MigrationInProgressError.
  NEVER reports success before durable canonical SQLite commit.
- Agent Events: paused / unacknowledged OR rejected with transient
  MigrationInProgressError.
  NEVER acknowledges volatile RAM-only work.
- Zero volatile RAM queueing that reports false success.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal


class MigrationBarrierError(Exception):
    """Base exception for migration barrier violations."""

    pass


class MigrationInProgressError(MigrationBarrierError):
    """Raised when an operation is attempted while MigrationBarrier is active.

    Indicates an unacknowledged transient state. Caller must NOT report success
    or consider the payload durably committed.
    """

    def __init__(
        self,
        message: str = "Migration barrier active: write withheld and unacknowledged.",
        *,
        write_type: str = "unknown",
        payload_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.write_type = write_type
        self.payload_id = payload_id


@dataclass(frozen=True)
class BarrierStatus:
    """Read-only snapshot of migration barrier state."""

    is_active: bool
    acquired_at: datetime | None
    reason: str
    quiesced_writers_count: int


class MigrationBarrier:
    """Option A Hard Quiesce barrier coordinator.

    Thread-safe coordination primitive ensuring zero unacknowledged data loss
    and strict quiescence across slices and agent events during migration.
    """

    def __init__(self, name: str = "default_barrier") -> None:
        self.name = name
        self._lock = threading.RLock()
        self._active: bool = False
        self._acquired_at: datetime | None = None
        self._reason: str = ""
        # _release_event is set when barrier is NOT active (i.e. writes can pass)
        self._release_event = threading.Event()
        self._release_event.set()
        self._listeners: list[Callable[[bool, str], None]] = []
        self._pending_blocked_writers: int = 0

    @property
    def is_active(self) -> bool:
        """Check if migration barrier is currently active."""
        with self._lock:
            return self._active

    def get_status(self) -> BarrierStatus:
        """Return a snapshot of current barrier status."""
        with self._lock:
            return BarrierStatus(
                is_active=self._active,
                acquired_at=self._acquired_at,
                reason=self._reason,
                quiesced_writers_count=self._pending_blocked_writers,
            )

    def register_listener(self, listener: Callable[[bool, str], None]) -> None:
        """Register a callback invoked when barrier state changes (is_active, reason)."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def unregister_listener(self, listener: Callable[[bool, str], None]) -> None:
        """Unregister a previously registered callback."""
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def acquire(self, reason: str = "Database migration in progress") -> None:
        """Acquire hard quiesce barrier.

        Subsequent writes will be blocked or withheld with MigrationInProgressError.
        """
        listeners_to_call: list[Callable[[bool, str], None]] = []
        with self._lock:
            if self._active:
                return
            self._active = True
            self._acquired_at = datetime.now(UTC)
            self._reason = reason
            self._release_event.clear()
            listeners_to_call = list(self._listeners)

        for listener in listeners_to_call:
            try:
                listener(True, reason)
            except Exception:
                pass

    def release(self) -> None:
        """Release hard quiesce barrier.

        Unblocks waiting writes and notifies listeners.
        """
        listeners_to_call: list[Callable[[bool, str], None]] = []
        with self._lock:
            if not self._active:
                return
            self._active = False
            self._acquired_at = None
            reason = self._reason
            self._reason = ""
            self._release_event.set()
            listeners_to_call = list(self._listeners)

        for listener in listeners_to_call:
            try:
                listener(False, reason)
            except Exception:
                pass

    @contextmanager
    def quiesce(self, reason: str = "Database migration in progress") -> Iterator[None]:
        """Context manager to acquire barrier, execute critical block, and release safely."""
        self.acquire(reason)
        try:
            yield
        finally:
            self.release()

    def guard_write(
        self,
        write_type: Literal["slice", "event"],
        payload_id: str | None = None,
        *,
        block: bool = False,
        timeout: float | None = 5.0,
    ) -> None:
        """Guard an incoming write against migration quiescence.

        Enforces ACKED WRITE MUST BE DURABLE:
        If barrier is active:
        - If block=True: wait on release event up to timeout.
          If timed out, raise MigrationInProgressError.
        - If block=False: immediately raise MigrationInProgressError.

        Never reports success before durable write can proceed.
        """
        with self._lock:
            is_active = self._active

        if not is_active:
            return

        if not block:
            raise MigrationInProgressError(
                f"Migration barrier is active ({self._reason}). Write rejected (unacknowledged).",
                write_type=write_type,
                payload_id=payload_id,
            )

        # Blocking path
        with self._lock:
            self._pending_blocked_writers += 1
        try:
            signaled = self._release_event.wait(timeout=timeout)
            if not signaled:
                raise MigrationInProgressError(
                    f"Migration barrier wait timed out ({timeout}s). Write unacknowledged.",
                    write_type=write_type,
                    payload_id=payload_id,
                )
        finally:
            with self._lock:
                self._pending_blocked_writers = max(0, self._pending_blocked_writers - 1)

    def guard_slice_write(
        self,
        slice_id: str | None = None,
        *,
        block: bool = False,
        timeout: float | None = 5.0,
    ) -> None:
        """Convenience guard hook for user slice writes."""
        self.guard_write("slice", payload_id=slice_id, block=block, timeout=timeout)

    def guard_event_write(
        self,
        event_id: str | None = None,
        *,
        block: bool = False,
        timeout: float | None = 5.0,
    ) -> None:
        """Convenience guard hook for agent event writes."""
        self.guard_write("event", payload_id=event_id, block=block, timeout=timeout)


# Global barrier singleton for process-level maintenance
_GLOBAL_BARRIER = MigrationBarrier("global_migration_barrier")


def get_global_barrier() -> MigrationBarrier:
    """Return the process-level MigrationBarrier singleton."""
    return _GLOBAL_BARRIER
