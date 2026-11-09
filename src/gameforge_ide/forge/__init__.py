"""GameForge — Forge durable execution framework (Phase 2 & Phase 8)."""
from .model import (
    StepKind,
    StepStatus,
    StepSpec,
    StepRecord,
    RunSpec,
    RunState,
    canonical_hash,
)
from .executor import ForgeExecutor, StepContext, StepOutcome
from .store import RunStore
from .impact import PATH_IMPACT_MAP, ImpactReport, compute_dirty_steps, impact, prepare_incremental_state
from .validation import validate_stage_output
