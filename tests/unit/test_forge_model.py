import pytest
from pydantic import ValidationError

from src.gameforge_ide.forge.model import (
    TERMINAL,
    ArtifactRef,
    RunSpec,
    RunState,
    StepKind,
    StepRecord,
    StepSpec,
    StepStatus,
    canonical_hash,
)


def test_step_spec_input_hash():
    s1 = StepSpec(
        step_id="step_a",
        kind=StepKind.BUILD,
        title="Build Title 1",
        inputs={"target": "Development", "clean": False},
    )
    s2 = StepSpec(
        step_id="step_a",
        kind=StepKind.BUILD,
        title="Completely Different Title",
        inputs={"target": "Development", "clean": False},
    )
    assert s1.input_hash == s2.input_hash

    # Modified input changes hash
    s3 = StepSpec(
        step_id="step_a",
        kind=StepKind.BUILD,
        title="Build Title 1",
        inputs={"target": "Development", "clean": True},
    )
    assert s1.input_hash != s3.input_hash

    # Changed kind changes hash
    s4 = StepSpec(
        step_id="step_a",
        kind=StepKind.PACKAGE,
        title="Build Title 1",
        inputs={"target": "Development", "clean": False},
    )
    assert s1.input_hash != s4.input_hash


def test_step_spec_validation():
    # Valid spec
    spec = StepSpec(step_id="step_1", kind=StepKind.SCAFFOLD, title="Scaffold")
    assert spec.step_id == "step_1"
    assert spec.timeout_s == 3600
    assert spec.checkpoint is True

    # Invalid step_id pattern (uppercase, starts with digit, or symbols)
    with pytest.raises(ValidationError):
        StepSpec(step_id="Step_1", kind=StepKind.SCAFFOLD, title="Scaffold")

    with pytest.raises(ValidationError):
        StepSpec(step_id="1_step", kind=StepKind.SCAFFOLD, title="Scaffold")

    with pytest.raises(ValidationError):
        StepSpec(step_id="step-one", kind=StepKind.SCAFFOLD, title="Scaffold")

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        StepSpec(step_id="step_1", kind=StepKind.SCAFFOLD, title="Scaffold", rogue_arg=123)


def test_run_spec_duplicate_step_id_rejected():
    s1 = StepSpec(step_id="dup_step", kind=StepKind.DESIGN, title="First")
    s2 = StepSpec(step_id="dup_step", kind=StepKind.BUILD, title="Second")
    with pytest.raises(ValidationError, match="duplicate step_id"):
        RunSpec(
            title="Test Run",
            workspace_dir="E:/GameForge",
            steps=[s1, s2],
        )


def test_run_spec_missing_dependency_rejected():
    s1 = StepSpec(step_id="step_a", kind=StepKind.DESIGN, title="First")
    s2 = StepSpec(step_id="step_b", kind=StepKind.BUILD, title="Second", depends_on=["nonexistent_step"])
    with pytest.raises(ValidationError, match="bad dependencies"):
        RunSpec(
            title="Test Run",
            workspace_dir="E:/GameForge",
            steps=[s1, s2],
        )


def test_run_spec_self_dependency_rejected():
    s1 = StepSpec(step_id="step_a", kind=StepKind.DESIGN, title="First", depends_on=["step_a"])
    with pytest.raises(ValidationError, match="bad dependencies"):
        RunSpec(
            title="Test Run",
            workspace_dir="E:/GameForge",
            steps=[s1],
        )


def test_run_spec_cycle_rejected():
    # 2-step cycle
    a = StepSpec(step_id="step_a", kind=StepKind.DESIGN, title="A", depends_on=["step_b"])
    b = StepSpec(step_id="step_b", kind=StepKind.BUILD, title="B", depends_on=["step_a"])
    with pytest.raises(ValidationError, match="dependency cycle"):
        RunSpec(
            title="Cycle Run",
            workspace_dir="E:/GameForge",
            steps=[a, b],
        )

    # 3-step cycle
    x = StepSpec(step_id="x", kind=StepKind.DESIGN, title="X", depends_on=["z"])
    y = StepSpec(step_id="y", kind=StepKind.CODEGEN, title="Y", depends_on=["x"])
    z = StepSpec(step_id="z", kind=StepKind.BUILD, title="Z", depends_on=["y"])
    with pytest.raises(ValidationError, match="dependency cycle"):
        RunSpec(
            title="3 Cycle Run",
            workspace_dir="E:/GameForge",
            steps=[x, y, z],
        )


def test_run_spec_topo_order_stable():
    # Diamond: a -> b, a -> c, [b, c] -> d
    a = StepSpec(step_id="a", kind=StepKind.DESIGN, title="A")
    b = StepSpec(step_id="b", kind=StepKind.CODEGEN, title="B", depends_on=["a"])
    c = StepSpec(step_id="c", kind=StepKind.CONTENT, title="C", depends_on=["a"])
    d = StepSpec(step_id="d", kind=StepKind.BUILD, title="D", depends_on=["b", "c"])

    # Declaration order: a, b, c, d -> topo order must be [a, b, c, d]
    run1 = RunSpec(title="Run 1", workspace_dir="E:/GameForge", steps=[a, b, c, d])
    assert [s.step_id for s in run1.topo_order()] == ["a", "b", "c", "d"]

    # Declaration order: a, c, b, d -> topo order must be [a, c, b, d]
    run2 = RunSpec(title="Run 2", workspace_dir="E:/GameForge", steps=[a, c, b, d])
    assert [s.step_id for s in run2.topo_order()] == ["a", "c", "b", "d"]

    # Multiple independent ready steps preserve declaration order
    s1 = StepSpec(step_id="first", kind=StepKind.DESIGN, title="1")
    s2 = StepSpec(step_id="second", kind=StepKind.DESIGN, title="2")
    s3 = StepSpec(step_id="third", kind=StepKind.DESIGN, title="3")
    run3 = RunSpec(title="Run 3", workspace_dir="E:/GameForge", steps=[s2, s3, s1])
    assert [s.step_id for s in run3.topo_order()] == ["second", "third", "first"]


def test_run_state_and_step_record():
    s1 = StepSpec(step_id="step_1", kind=StepKind.SCAFFOLD, title="Scaffold")
    s2 = StepSpec(step_id="step_2", kind=StepKind.BUILD, title="Build", depends_on=["step_1"])
    run = RunSpec(title="Run", workspace_dir="E:/GameForge", steps=[s1, s2])

    state = RunState.new(run)
    assert state.status == "PENDING"
    assert "step_1" in state.records
    assert "step_2" in state.records
    assert state.records["step_1"].status == StepStatus.PENDING

    # Test duration_s
    rec = state.records["step_1"]
    assert rec.duration_s is None
    rec.started_at = 100.0
    rec.finished_at = 112.45
    assert rec.duration_s == 12.5

    # Check terminal statuses
    assert StepStatus.DONE in TERMINAL
    assert StepStatus.FAILED in TERMINAL
    assert StepStatus.CANCELLED in TERMINAL
    assert StepStatus.RUNNING not in TERMINAL
    assert StepStatus.PENDING not in TERMINAL


def test_serialization_round_trip():
    s = StepSpec(
        step_id="step_1",
        kind=StepKind.BUILD,
        title="Build",
        inputs={"opt": True, "num": 42},
    )
    run = RunSpec(
        title="Full Run",
        workspace_dir="E:/GameForge/projects",
        project_dir="E:/GameForge/projects/MyGame",
        steps=[s],
    )
    state = RunState.new(run)
    state.records["step_1"].status = StepStatus.DONE
    state.records["step_1"].ok = True
    state.records["step_1"].checkpoint = "a1b2c3d4"
    state.records["step_1"].artifacts.append(
        ArtifactRef(path="output.log", kind="log", sha256="abc123")
    )

    json_str = state.model_dump_json()
    loaded = RunState.model_validate_json(json_str)

    assert loaded.run.run_id == state.run.run_id
    assert loaded.run.steps[0].step_id == "step_1"
    assert loaded.records["step_1"].status == StepStatus.DONE
    assert loaded.records["step_1"].checkpoint == "a1b2c3d4"
    assert len(loaded.records["step_1"].artifacts) == 1
    assert loaded.records["step_1"].artifacts[0].sha256 == "abc123"
