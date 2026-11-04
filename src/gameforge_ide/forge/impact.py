"""Impact analysis and incremental Forge DAG rebuild (WI-8.2).

Computes effective hash invalidation (P2 logic) between the previous RunState
and a newly composed RunSpec. Categorises steps into rerun, skip, new, and removed,
estimates rebuild duration from historical medians, and prepares incremental states.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .model import RunSpec, RunState, StepKind, StepRecord, StepSpec, StepStatus, canonical_hash


# Default durations in seconds if no run history exists
DEFAULT_KIND_DURATIONS_S: Dict[StepKind, float] = {
    StepKind.DESIGN: 6.0,
    StepKind.SCAFFOLD: 12.0,
    StepKind.CODEGEN: 30.0,
    StepKind.BUILD: 90.0,
    StepKind.CONTENT: 18.0,
    StepKind.ASSEMBLE: 60.0,
    StepKind.AUTOMATION: 30.0,
    StepKind.PACKAGE: 150.0,
    StepKind.SCENARIO: 48.0,
    StepKind.REVIEW: 12.0,
    StepKind.REPORT: 6.0,
    StepKind.TOOL_CALL: 10.0,
}


class ImpactReport(BaseModel):
    """Impact analysis comparing a new RunSpec against a prior RunState."""
    rerun: List[str] = Field(default_factory=list)
    skip: List[str] = Field(default_factory=list)
    new: List[str] = Field(default_factory=list)
    removed: List[str] = Field(default_factory=list)
    estimated_minutes: float = 0.0
    descriptions: Dict[str, str] = Field(default_factory=dict)

    def format_summary(self) -> str:
        """User-facing single line summary for UI dialogs and notifications."""
        to_rebuild = [self.descriptions.get(s, s) for s in (self.rerun + self.new)]
        if not to_rebuild:
            return "No steps need to be re-run; all outputs are cached."
        names = ", ".join(to_rebuild[:4])
        if len(to_rebuild) > 4:
            names += f", +{len(to_rebuild) - 4} more"
        return f"This change rebuilds: {names} (~ {self.estimated_minutes} min)"


def compute_effective_hashes(spec: RunSpec) -> Dict[str, str]:
    """Compute effective hashes (AD-11 / P2) for all steps in a RunSpec."""
    eff: Dict[str, str] = {}
    for step in spec.topo_order():
        dep_hashes = [eff[d] for d in sorted(step.depends_on) if d in eff]
        eff[step.step_id] = canonical_hash({"self": step.input_hash, "deps": dep_hashes})
    return eff


def impact(
    previous_state: Optional[RunState],
    new_spec: RunSpec,
    past_states: Optional[List[RunState]] = None,
) -> ImpactReport:
    """Analyze the impact of new_spec compared to previous_state.

    Returns an ImpactReport with rerun, skip, new, and removed step lists,
    along with estimated rebuild duration.
    """
    if previous_state is None:
        # Cold run: everything is new
        durations = _calculate_durations(past_states)
        total_s = sum(durations.get(s.kind, 30.0) for s in new_spec.steps)
        descs = {s.step_id: s.title for s in new_spec.steps}
        return ImpactReport(
            rerun=[],
            skip=[],
            new=[s.step_id for s in new_spec.steps],
            removed=[],
            estimated_minutes=round(total_s / 60.0, 1),
            descriptions=descs,
        )

    # 1. Effective hashes of the new spec
    new_eff = compute_effective_hashes(new_spec)
    prev_records = previous_state.records

    rerun: List[str] = []
    skip: List[str] = []
    new: List[str] = []
    invalidated_deps: set[str] = set()
    descs: Dict[str, str] = {s.step_id: s.title for s in new_spec.steps}

    for step in new_spec.topo_order():
        sid = step.step_id
        eff_hash = new_eff[sid]
        dep_invalidated = any(d in invalidated_deps for d in step.depends_on)
        if sid not in prev_records:
            new.append(sid)
            invalidated_deps.add(sid)
        else:
            prev_rec = prev_records[sid]
            # Must not have invalidated dependencies, must be DONE, have succeeded (ok is True), and matching effective hash
            if (
                not dep_invalidated
                and prev_rec.status == StepStatus.DONE
                and prev_rec.ok is True
                and prev_rec.input_hash == eff_hash
            ):
                skip.append(sid)
            else:
                rerun.append(sid)
                invalidated_deps.add(sid)

    # Steps in previous run no longer in new spec
    new_ids = {s.step_id for s in new_spec.steps}
    removed = [sid for sid in prev_records.keys() if sid not in new_ids]

    # Calculate estimated duration
    durations = _calculate_durations(past_states or [previous_state])
    spec_step_by_id = {s.step_id: s for s in new_spec.steps}
    rebuild_seconds = 0.0
    for sid in (rerun + new):
        step = spec_step_by_id.get(sid)
        if step:
            rebuild_seconds += durations.get(step.kind, 30.0)

    est_minutes = max(0.1, round(rebuild_seconds / 60.0, 1)) if (rerun or new) else 0.0

    return ImpactReport(
        rerun=rerun,
        skip=skip,
        new=new,
        removed=removed,
        estimated_minutes=est_minutes,
        descriptions=descs,
    )


def prepare_incremental_state(
    previous_state: Optional[RunState],
    new_spec: RunSpec,
    past_states: Optional[List[RunState]] = None,
) -> Tuple[RunState, ImpactReport]:
    """Prepare a RunState primed for incremental rebuild.

    Steps in skip are pre-populated with their successful records and input_hashes
    so ForgeExecutor will skip re-execution and reuse previous outputs.
    """
    report = impact(previous_state, new_spec, past_states)
    state = RunState.new(new_spec)
    new_eff = compute_effective_hashes(new_spec)

    if previous_state is not None:
        for sid in report.skip:
            old_rec = previous_state.records.get(sid)
            if old_rec is None:
                continue
            # Keep as DONE with effective input_hash and preserved data/artifacts
            state.records[sid] = StepRecord(
                step_id=sid,
                status=StepStatus.DONE,
                attempts=old_rec.attempts,
                input_hash=new_eff[sid],
                started_at=old_rec.started_at,
                finished_at=old_rec.finished_at,
                ok=True,
                data=dict(old_rec.data),
                errors=[],
                artifacts=list(old_rec.artifacts),
                checkpoint=old_rec.checkpoint,
            )

    return state, report


def _calculate_durations(past_states: Optional[List[RunState]]) -> Dict[StepKind, float]:
    """Calculate median duration per StepKind from past execution records."""
    durations: Dict[StepKind, List[float]] = {k: [] for k in StepKind}

    if past_states:
        for st in past_states:
            step_by_id = {s.step_id: s for s in st.run.steps}
            for sid, rec in st.records.items():
                if rec.status == StepStatus.DONE and rec.duration_s is not None and rec.duration_s > 0:
                    step = step_by_id.get(sid)
                    if step:
                        durations[step.kind].append(rec.duration_s)

    result: Dict[StepKind, float] = {}
    for kind, samples in durations.items():
        if samples:
            result[kind] = float(statistics.median(samples))
        else:
            result[kind] = DEFAULT_KIND_DURATIONS_S.get(kind, 30.0)

    return result
