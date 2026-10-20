"""Memory V2.1 Migration Package.

Option A Hard Quiesce + Option D Canonical ID Set Difference.
"""

from __future__ import annotations

from src.memory.v2.migration.barrier import (
    BarrierStatus,
    MigrationBarrier,
    MigrationBarrierError,
    MigrationInProgressError,
    get_global_barrier,
)
from src.memory.v2.migration.executor import (
    MigrationExecutionReport,
    MigrationExecutor,
)
from src.memory.v2.migration.mapper import (
    MapperError,
    MappingReport,
    PrivacySanitizationError,
    build_v2_shadow_db,
    initialize_v2_schema,
    sanitize_error_category,
)
from src.memory.v2.migration.preflight import (
    DiskSpacePlan,
    IncompatibleSourceSchemaError,
    InsufficientDiskSpaceError,
    PreflightError,
    PreflightReport,
    SourceIntegrityCheckError,
    compute_disk_space_plan,
    run_preflight_checks,
    validate_source_schema_and_integrity,
)
from src.memory.v2.migration.reconcile import (
    MigrationConflictError,
    ReconciliationError,
    ReconciliationReport,
    reconcile_canonical_sets,
)
from src.memory.v2.migration.snapshot import (
    SnapshotError,
    create_wal_snapshot,
)
from src.memory.v2.migration.swap import (
    MidSwapRecoveryError,
    RollbackForbiddenDataLossError,
    SwapError,
    SwapPlan,
    SwapResult,
    WindowsFileLockError,
    execute_atomic_swap,
    prepare_swap_plan,
    recover_mid_swap_failure,
    rollback_cutover,
)

__all__ = [
    "BarrierStatus",
    "MigrationBarrier",
    "MigrationBarrierError",
    "MigrationInProgressError",
    "get_global_barrier",
    "DiskSpacePlan",
    "PreflightError",
    "InsufficientDiskSpaceError",
    "IncompatibleSourceSchemaError",
    "SourceIntegrityCheckError",
    "PreflightReport",
    "compute_disk_space_plan",
    "validate_source_schema_and_integrity",
    "run_preflight_checks",
    "SnapshotError",
    "create_wal_snapshot",
    "MapperError",
    "PrivacySanitizationError",
    "MappingReport",
    "sanitize_error_category",
    "initialize_v2_schema",
    "build_v2_shadow_db",
    "ReconciliationError",
    "MigrationConflictError",
    "ReconciliationReport",
    "reconcile_canonical_sets",
    "SwapError",
    "WindowsFileLockError",
    "MidSwapRecoveryError",
    "RollbackForbiddenDataLossError",
    "SwapPlan",
    "SwapResult",
    "prepare_swap_plan",
    "execute_atomic_swap",
    "recover_mid_swap_failure",
    "rollback_cutover",
    "MigrationExecutor",
    "MigrationExecutionReport",
]
