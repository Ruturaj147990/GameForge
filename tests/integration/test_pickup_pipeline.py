"""Integration tests evaluating the T2-005 Pickup Collection System in real Unreal Engine."""

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


def test_pickup_reference_solution_passes_pipeline(runner, ue_discovery):
    """Reference solution must pass all build, asset, and 12 behavioral probes in real UE5."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    ref_dir = Path("graders/reference_solutions/unreal/t2_005_pickup")
    assert ref_dir.is_dir(), f"Reference solution directory missing: {ref_dir}"

    res = runner.run_task(
        task_id="t2-005-pickup-collection",
        engine_name="unreal",
        candidate_dir=ref_dir,
        candidate_id="reference_t2_005_unreal",
    )

    assert res["status"] == RunStatus.PASS.value, f"Expected PASS, got {res['status']}. Summary: {res['summary_text']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "PASS"
    assert rep["layers"]["saved_asset_checks"]["status"] == "PASS"

    probes = rep["probes"]
    mandatory_probes = [
        "probe_p1_valid_health_collection",
        "probe_p2_repeated_overlap",
        "probe_p3_reentry_after_collection",
        "probe_p4_full_health",
        "probe_p5_valid_stamina_collection",
        "probe_p6_resource_clamping",
        "probe_p7_invalid_target",
        "probe_p8_dead_player",
        "probe_p9_invalid_pickup_amount",
        "probe_p10_collection_race",
        "probe_p11_reentrancy",
        "probe_p12_collision_shutdown",
    ]
    for p_id in mandatory_probes:
        assert p_id in probes, f"Mandatory probe '{p_id}' missing from report"
        assert probes[p_id]["passed"] is True, f"Probe '{p_id}' failed: {probes[p_id]}"


def test_pickup_failing_duplicate_consumption_is_rejected(runner, ue_discovery):
    """Candidate with duplicate consumption defect compiles but is rejected by runtime probe P2."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t2_005_failing_duplicate")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t2-005-pickup-collection",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_duplicate_consumption_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep["probes"]
    assert probes["probe_p2_repeated_overlap"]["passed"] is False


def test_pickup_failing_full_resource_is_rejected(runner, ue_discovery):
    """Candidate that consumes pickup on full resource compiles but is rejected by runtime probe P4."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t2_005_failing_full_resource")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t2-005-pickup-collection",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_full_resource_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep["probes"]
    assert probes["probe_p4_full_health"]["passed"] is False


def test_pickup_failing_wrong_target_is_rejected(runner, ue_discovery):
    """Candidate that swaps stamina and health targets compiles but is rejected by runtime probe P5."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t2_005_failing_wrong_target")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t2-005-pickup-collection",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_wrong_target_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep["probes"]
    assert probes["probe_p5_valid_stamina_collection"]["passed"] is False
