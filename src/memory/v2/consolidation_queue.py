"""Consolidation Queue for Memory V2.1 Lane F (WP-5).

Operational background job queue metadata for near-real-time consolidation.
Operates strictly on the canonical `consolidation_jobs` technical metadata table.
Strictly isolated from 21st Memory entities (I-S06):
- Queue rows are NEVER retrieval evidence.
- Queue rows NEVER contain prompts, CoT, tool outputs, or semantic text.
- Queue stores ONLY source pointers: (source_kind, source_id).
- Enqueue commit ACK != Consolidation complete.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from src.memory.v2.store import ChronicleStoreV2

JobStatus = Literal["pending", "running", "completed", "failed"]
QueueSourceKind = Literal["slice", "event"]

VALID_SOURCE_KINDS: frozenset[str] = frozenset({"slice", "event"})
VALID_JOB_STATUSES: frozenset[str] = frozenset({"pending", "running", "completed", "failed"})


class ConsolidationQueueError(Exception):
    """Base exception for consolidation queue operations."""

    pass


class InvalidSourceKindError(ConsolidationQueueError, ValueError):
    """Raised when an unsupported source_kind is enqueued."""

    pass


def compute_job_id(source_kind: str, source_id: str) -> str:
    """Compute deterministic collision-safe job_id from source_kind and source_id.

    Guarantees that re-enqueuing the same source identity targets the exact same
    canonical job row without relying on SQLite rowid.
    """
    digest = hashlib.sha256(f"{source_kind}:{source_id}".encode()).hexdigest()[:24]
    return f"cjob_{digest}"


@dataclass(frozen=True)
class ConsolidationJob:
    """Operational metadata record for a consolidation background job.

    Contains NO memory content, prompt, CoT, or semantic claims.
    Maps purely to (source_kind, source_id) durable raw evidence.
    """

    job_id: str
    source_kind: str
    source_id: str
    status: JobStatus = "pending"
    retry_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConsolidationQueue:
    """Technical operational queue repository managing `consolidation_jobs`."""

    def __init__(self, store: ChronicleStoreV2) -> None:
        self._store = store

    @property
    def store(self) -> ChronicleStoreV2:
        return self._store

    def enqueue(
        self,
        source_kind: str,
        source_id: str,
        *,
        now_ts: str | None = None,
        re_enqueue_failed: bool = False,
    ) -> ConsolidationJob:
        """Enqueue durable raw evidence for consolidation in an immediate transaction.

        Idempotent:
        - If a job for (source_kind, source_id) already exists:
          - If status is 'pending', 'running', or 'completed': returns existing job.
          - If status is 'failed':
            - if re_enqueue_failed is True: resets status to 'pending' and retry_count=0.
            - if re_enqueue_failed is False: returns existing failed job.
        - If new: commits a new row with status='pending', retry_count=0.
        """
        if source_kind not in VALID_SOURCE_KINDS:
            valid = sorted(VALID_SOURCE_KINDS)
            msg = f"Invalid source_kind '{source_kind}'. Must be one of {valid}"
            raise InvalidSourceKindError(msg)

        job_id = compute_job_id(source_kind, source_id)
        ts = now_ts or datetime.now(UTC).isoformat()

        with self._store.transaction():
            row = self._store.connection.execute(
                """
                SELECT job_id, source_kind, source_id, status, retry_count, created_at, updated_at
                  FROM consolidation_jobs
                 WHERE job_id = ?;
                """,
                (job_id,),
            ).fetchone()

            if row:
                current_status: JobStatus = row["status"]
                current_retry = int(row["retry_count"])
                if current_status == "failed" and re_enqueue_failed:
                    self._store.connection.execute(
                        """
                        UPDATE consolidation_jobs
                           SET status = 'pending',
                               retry_count = 0,
                               updated_at = ?
                         WHERE job_id = ?;
                        """,
                        (ts, job_id),
                    )
                    return ConsolidationJob(
                        job_id=job_id,
                        source_kind=source_kind,
                        source_id=source_id,
                        status="pending",
                        retry_count=0,
                        created_at=row["created_at"],
                        updated_at=ts,
                    )

                return ConsolidationJob(
                    job_id=row["job_id"],
                    source_kind=row["source_kind"],
                    source_id=row["source_id"],
                    status=current_status,
                    retry_count=current_retry,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

            self._store.connection.execute(
                """
                INSERT INTO consolidation_jobs (
                    job_id, source_kind, source_id, status, retry_count, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', 0, ?, ?);
                """,
                (job_id, source_kind, source_id, ts, ts),
            )
            return ConsolidationJob(
                job_id=job_id,
                source_kind=source_kind,
                source_id=source_id,
                status="pending",
                retry_count=0,
                created_at=ts,
                updated_at=ts,
            )

    def get_job(self, job_id: str) -> ConsolidationJob | None:
        """Fetch a consolidation job by job_id."""
        row = self._store.connection.execute(
            """
            SELECT job_id, source_kind, source_id, status, retry_count, created_at, updated_at
              FROM consolidation_jobs
             WHERE job_id = ?;
            """,
            (job_id,),
        ).fetchone()
        if not row:
            return None
        return ConsolidationJob(
            job_id=row["job_id"],
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            status=row["status"],
            retry_count=int(row["retry_count"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_job_by_source(self, source_kind: str, source_id: str) -> ConsolidationJob | None:
        """Fetch a consolidation job by source identity."""
        job_id = compute_job_id(source_kind, source_id)
        return self.get_job(job_id)

    def list_jobs(self, status: str | None = None, limit: int = 100) -> list[ConsolidationJob]:
        """List consolidation jobs, optionally filtered by status."""
        if status:
            rows = self._store.connection.execute(
                """
                SELECT job_id, source_kind, source_id, status, retry_count, created_at, updated_at
                  FROM consolidation_jobs
                 WHERE status = ?
                 ORDER BY created_at ASC
                 LIMIT ?;
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = self._store.connection.execute(
                """
                SELECT job_id, source_kind, source_id, status, retry_count, created_at, updated_at
                  FROM consolidation_jobs
                 ORDER BY created_at ASC
                 LIMIT ?;
                """,
                (limit,),
            ).fetchall()

        return [
            ConsolidationJob(
                job_id=r["job_id"],
                source_kind=r["source_kind"],
                source_id=r["source_id"],
                status=r["status"],
                retry_count=int(r["retry_count"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def count_jobs(self, status: str | None = None) -> int:
        """Count consolidation jobs, optionally filtered by status."""
        if status:
            row = self._store.connection.execute(
                "SELECT COUNT(*) FROM consolidation_jobs WHERE status = ?;",
                (status,),
            ).fetchone()
        else:
            row = self._store.connection.execute(
                "SELECT COUNT(*) FROM consolidation_jobs;",
            ).fetchone()
        return int(row[0]) if row else 0

    def claim_jobs(self, limit: int = 10, now_ts: str | None = None) -> list[ConsolidationJob]:
        """Atomically claim up to `limit` pending jobs in a short transaction."""
        ts = now_ts or datetime.now(UTC).isoformat()
        with self._store.transaction():
            rows = self._store.connection.execute(
                """
                SELECT job_id, source_kind, source_id, status, retry_count, created_at, updated_at
                  FROM consolidation_jobs
                 WHERE status = 'pending'
                 ORDER BY created_at ASC
                 LIMIT ?;
                """,
                (limit,),
            ).fetchall()

            if not rows:
                return []

            claimed: list[ConsolidationJob] = []
            for r in rows:
                job_id = r["job_id"]
                self._store.connection.execute(
                    """
                    UPDATE consolidation_jobs
                       SET status = 'running',
                           updated_at = ?
                     WHERE job_id = ? AND status = 'pending';
                    """,
                    (ts, job_id),
                )
                claimed.append(
                    ConsolidationJob(
                        job_id=job_id,
                        source_kind=r["source_kind"],
                        source_id=r["source_id"],
                        status="running",
                        retry_count=int(r["retry_count"]),
                        created_at=r["created_at"],
                        updated_at=ts,
                    )
                )
            return claimed

    def mark_completed(self, job_id: str, now_ts: str | None = None) -> None:
        """Mark a job as completed in a short transaction."""
        ts = now_ts or datetime.now(UTC).isoformat()
        with self._store.transaction():
            self._store.connection.execute(
                """
                UPDATE consolidation_jobs
                   SET status = 'completed',
                       updated_at = ?
                 WHERE job_id = ?;
                """,
                (ts, job_id),
            )

    def mark_failed(
        self,
        job_id: str,
        *,
        retry: bool = True,
        max_retries: int = 3,
        now_ts: str | None = None,
    ) -> JobStatus:
        """Handle failure for a running job in a short transaction.

        Increments retry_count.
        If retry is True and new_retry_count < max_retries:
            Sets status = 'pending' (retryable).
        Else:
            Sets status = 'failed' (terminal failure).
        """
        ts = now_ts or datetime.now(UTC).isoformat()
        with self._store.transaction():
            row = self._store.connection.execute(
                "SELECT retry_count FROM consolidation_jobs WHERE job_id = ?;",
                (job_id,),
            ).fetchone()
            if not row:
                return "failed"

            new_retry = int(row["retry_count"]) + 1
            new_status: JobStatus = "pending" if (retry and new_retry < max_retries) else "failed"

            self._store.connection.execute(
                """
                UPDATE consolidation_jobs
                   SET status = ?,
                       retry_count = ?,
                       updated_at = ?
                 WHERE job_id = ?;
                """,
                (new_status, new_retry, ts, job_id),
            )
            return new_status

    def reclaim_abandoned_jobs(
        self,
        *,
        timeout_seconds: float | None = None,
        now_ts: str | None = None,
    ) -> list[str]:
        """Reclaim abandoned 'running' jobs back to 'pending' for safe reprocessing.

        If timeout_seconds is provided, only jobs with updated_at older than
        (now - timeout_seconds) are reclaimed.
        If timeout_seconds is None, ALL currently running jobs are reclaimed
        (safe on single-worker restart/recovery).
        """
        ts = now_ts or datetime.now(UTC).isoformat()
        with self._store.transaction():
            if timeout_seconds is None:
                rows = self._store.connection.execute(
                    "SELECT job_id FROM consolidation_jobs WHERE status = 'running';",
                ).fetchall()
            else:
                now_dt = datetime.fromisoformat(ts)
                rows = self._store.connection.execute(
                    "SELECT job_id, updated_at FROM consolidation_jobs WHERE status = 'running';",
                ).fetchall()
                target_ids: list[str] = []
                for r in rows:
                    try:
                        job_dt = datetime.fromisoformat(r["updated_at"])
                        if (now_dt - job_dt).total_seconds() >= timeout_seconds:
                            target_ids.append(r["job_id"])
                    except Exception:
                        target_ids.append(r["job_id"])
                rows = [{"job_id": jid} for jid in target_ids]

            reclaimed_ids: list[str] = []
            for r in rows:
                jid = r["job_id"]
                self._store.connection.execute(
                    """
                    UPDATE consolidation_jobs
                       SET status = 'pending',
                           updated_at = ?
                     WHERE job_id = ? AND status = 'running';
                    """,
                    (ts, jid),
                )
                reclaimed_ids.append(jid)

            return reclaimed_ids
