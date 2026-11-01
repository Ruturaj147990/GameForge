"""Unit tests for Forge impact analysis and incremental rebuild (WI-8.2)."""
from __future__ import annotations

import pytest

from src.gameforge_ide.forge.impact import (
    ImpactReport,
    compute_effective_hashes,
    impact,
    prepare_incremental_state,
)
from src.gameforge_ide.forge.model import (
    RunSpec,
    RunState,
    StepKind,
    StepRecord,
    StepSpec,
    StepStatus,
)


def _make_sample_spec(level_1_hash: str = "v1", level_2_hash: str = "v1") -> RunSpec:
    steps = [
        StepSpec(
            step_id="design",
            kind=StepKind.DESIGN,
            title="Design: save GDS",
            inputs={"v": 1},
        ),
        StepSpec(
            step_id="scaffold",
            kind=StepKind.SCAFFOLD,
            title="Scaffold project",
            depends_on=["design"],
            inputs={"name": "TestGame"},
        ),
        StepSpec(
            step_id="build_editor",
            kind=StepKind.BUILD,
            title="Build editor",
            depends_on=["scaffold"],
            inputs={"target": "TestGameEditor"},
        ),
        StepSpec(
            step_id="assemble_level_1",
            kind=StepKind.ASSEMBLE,
            title="Assemble level_1",
            depends_on=["build_editor"],
            inputs={"level": "level_1", "plan_hash": level_1_hash},
        ),
        StepSpec(
            step_id="assemble_level_2",
            kind=StepKind.ASSEMBLE,
            title="Assemble level_2",
            depends_on=["build_editor"],
            inputs={"level": "level_2", "plan_hash": level_2_hash},
        ),
        StepSpec(
            step_id="package",
            kind=StepKind.PACKAGE,
            title="Package game",
            depends_on=["assemble_level_1", "assemble_level_2"],
            inputs={"config": "Development"},
        ),
        StepSpec(
            step_id="scenarios",
            kind=StepKind.SCENARIO,
            title="Run Scenarios",
            depends_on=["package"],
            inputs={"scenarios": ["smoke"]},
        ),
    ]
    return RunSpec(
        title="Test Run",
        workspace_dir="E:/GameForge/projects",
        steps=steps,
    )


def test_cold_run_impact_marks_all_new():
    spec = _make_sample_spec()
    rep = impact(previous_state=None, new_spec=spec)

    assert rep.rerun == []
    assert rep.skip == []
    assert len(rep.new) == len(spec.steps)
    assert rep.removed == []
    assert rep.estimated_minutes > 0.0
    assert "This change rebuilds" in rep.format_summary()


def test_unchanged_run_marks_all_skip():
    spec = _make_sample_spec()
    eff = compute_effective_hashes(spec)

    # Simulate completed run
    state = RunState.new(spec)
    for s in spec.steps:
        state.records[s.step_id] = StepRecord(
            step_id=s.step_id,
            status=StepStatus.DONE,
            ok=True,
            input_hash=eff[s.step_id],
            started_at=100.0,
            finished_at=130.0,
        )

    rep = impact(previous_state=state, new_spec=spec)
    assert rep.rerun == []
    assert rep.new == []
    assert rep.removed == []
    assert set(rep.skip) == {s.step_id for s in spec.steps}
    assert rep.estimated_minutes == 0.0
    assert "cached" in rep.format_summary()


def test_level_2_change_skips_level_1_rebuild():
    spec1 = _make_sample_spec(level_1_hash="v1", level_2_hash="v1")
    eff1 = compute_effective_hashes(spec1)

    state1 = RunState.new(spec1)
    for s in spec1.steps:
        state1.records[s.step_id] = StepRecord(
            step_id=s.step_id,
            status=StepStatus.DONE,
            ok=True,
            input_hash=eff1[s.step_id],
            started_at=100.0,
            finished_at=130.0,
        )

    # Change only level 2
    spec2 = _make_sample_spec(level_1_hash="v1", level_2_hash="v2_modified")
    rep = impact(previous_state=state1, new_spec=spec2)

    # Level 1 and earlier steps MUST be skipped
    assert "design" in rep.skip
    assert "scaffold" in rep.skip
    assert "build_editor" in rep.skip
    assert "assemble_level_1" in rep.skip

    # Level 2 and downstream steps MUST be rerun
    assert "assemble_level_2" in rep.rerun
    assert "package" in rep.rerun
    assert "scenarios" in rep.rerun

    assert rep.new == []
    assert rep.removed == []
    assert rep.estimated_minutes > 0.0
    summary = rep.format_summary()
    assert "Assemble level_2" in summary
    assert "Package" in summary


def test_prepare_incremental_state_primes_skip_records():
    spec1 = _make_sample_spec(level_1_hash="v1", level_2_hash="v1")
    eff1 = compute_effective_hashes(spec1)

    state1 = RunState.new(spec1)
    for s in spec1.steps:
        state1.records[s.step_id] = StepRecord(
            step_id=s.step_id,
            status=StepStatus.DONE,
            ok=True,
            input_hash=eff1[s.step_id],
            started_at=100.0,
            finished_at=130.0,
            data={"output_key": f"data_for_{s.step_id}"},
        )

    spec2 = _make_sample_spec(level_1_hash="v1", level_2_hash="v2_modified")
    inc_state, rep = prepare_incremental_state(previous_state=state1, new_spec=spec2)

    # Skipped steps should be primed as DONE with preserved outputs
    assert inc_state.records["assemble_level_1"].status == StepStatus.DONE
    assert inc_state.records["assemble_level_1"].data == {"output_key": "data_for_assemble_level_1"}

    # Rerun steps should remain PENDING
    assert inc_state.records["assemble_level_2"].status == StepStatus.PENDING
    assert inc_state.records["package"].status == StepStatus.PENDING
