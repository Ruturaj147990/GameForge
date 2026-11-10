"""GameForge — Forge durable execution framework (Phase 2 & Phase 8)."""
from .checkpoints import CheckpointError, ProjectRepo
from .executor import ForgeExecutor, StepContext, StepOutcome
from .impact import (
    PATH_IMPACT_MAP,
    ImpactReport,
    compute_dirty_steps,
    compute_effective_hashes,
    impact,
    prepare_incremental_state,
)
from .model import (
    TERMINAL,
    ArtifactRef,
    RunSpec,
    RunState,
    RunStatus,
    StepKind,
    StepRecord,
    StepSpec,
    StepStatus,
    canonical_hash,
)
from .project_graph import GeneratedBy, ProjectGraph, ProjectNode
from .reconciliation import (
    ActorConflict,
    AssetConflict,
    ReconciliationPlan,
    apply_resolutions,
    plan_reconciliation,
    reconcile_interrupted_runs,
)
from .store import RunStore
from .validation import validate_stage_output

__all__ = [
    "ActorConflict",
    "ArtifactRef",
    "AssetConflict",
    "CheckpointError",
    "ForgeExecutor",
    "GeneratedBy",
    "ImpactReport",
    "PATH_IMPACT_MAP",
    "ProjectGraph",
    "ProjectNode",
    "ProjectRepo",
    "ReconciliationPlan",
    "RunSpec",
    "RunState",
    "RunStatus",
    "RunStore",
    "StepContext",
    "StepKind",
    "StepOutcome",
    "StepRecord",
    "StepSpec",
    "StepStatus",
    "TERMINAL",
    "apply_resolutions",
    "canonical_hash",
    "compute_dirty_steps",
    "compute_effective_hashes",
    "impact",
    "plan_reconciliation",
    "prepare_incremental_state",
    "reconcile_interrupted_runs",
    "validate_stage_output",
]
