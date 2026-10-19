"""Integration tests executing the real-engine grading pipeline."""

from pathlib import Path
import pytest
from gameforge_bench.engines.discovery import discover_unreal_engine
from gameforge_bench.grading import RunStatus
from gameforge_bench.runner import BenchmarkRunner


@pytest.fixture
def ue_discovery():
    return discover_unreal_engine()


@pytest.fixture
def runner():
    return BenchmarkRunner(workspace_root=Path.cwd())


def test_reference_solution_passes_pipeline(runner, ue_discovery):
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    ref_dir = Path("graders/reference_solutions/unreal/t2_001_controller")
    assert ref_dir.is_dir(), f"Reference solution directory missing: {ref_dir}"

    res = runner.run_task(
        task_id="t2-001-third-person-controller",
        engine_name="unreal",
        candidate_dir=ref_dir,
        candidate_id="reference_t2_001_unreal",
    )

    assert res["status"] == RunStatus.PASS.value, f"Expected PASS, got {res['status']}. Summary: {res['summary_text']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "PASS"
    assert rep["layers"]["saved_asset_checks"]["status"] == "PASS"

    # Verify specific probe values
    probes = rep["probes"]
    assert probes["max_run_speed_mps"]["passed"] is True
    assert probes["jump_apex_height_meters"]["passed"] is True
    assert probes["orbit_arm_length_meters"]["passed"] is True
    assert probes["camera_geometry_intersection"]["passed"] is True


def test_controlled_fault_candidate_is_rejected(runner, ue_discovery):
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    fault_dir = Path("graders/reference_solutions/unreal/t2_001_failing_speed")
    assert fault_dir.is_dir(), f"Fault candidate directory missing: {fault_dir}"

    res = runner.run_task(
        task_id="t2-001-third-person-controller",
        engine_name="unreal",
        candidate_dir=fault_dir,
        candidate_id="defective_speed_candidate",
    )

    # Must NOT pass: behavior matters more than compilation
    assert res["status"] == RunStatus.PARTIAL_BUILD.value
    assert res["report"]["first_mandatory_failure_layer"] == "behavior_probes"
    probes = res["report"]["probes"]
    assert probes["max_run_speed_mps"]["passed"] is False


def test_repeatability_and_determinism(runner, ue_discovery):
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    ref_dir = Path("graders/reference_solutions/unreal/t2_001_controller")

    # Run twice and check that outputs and statuses match identically
    res1 = runner.run_task(
        task_id="t2-001-third-person-controller",
        engine_name="unreal",
        candidate_dir=ref_dir,
        candidate_id="repeatability_run_1",
    )
    res2 = runner.run_task(
        task_id="t2-001-third-person-controller",
        engine_name="unreal",
        candidate_dir=ref_dir,
        candidate_id="repeatability_run_2",
    )

    assert res1["status"] == RunStatus.PASS.value
    assert res2["status"] == RunStatus.PASS.value
    assert res1["report"]["probes"]["max_run_speed_mps"]["measured_value"] == res2["report"]["probes"]["max_run_speed_mps"]["measured_value"]
    assert res1["report"]["probes"]["jump_apex_height_meters"]["measured_value"] == res2["report"]["probes"]["jump_apex_height_meters"]["measured_value"]
