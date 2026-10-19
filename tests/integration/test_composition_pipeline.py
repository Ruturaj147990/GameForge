"""Integration tests evaluating the T3-016 Player Composition System in real Unreal Engine."""

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


def test_composition_reference_solution_passes_pipeline(runner, ue_discovery):
    """Reference solution must pass all build, asset, and 9 composition probes in real UE5."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    ref_dir = Path("graders/reference_solutions/unreal/t3_016_composition")
    assert ref_dir.is_dir(), f"Reference solution directory missing: {ref_dir}"

    res = runner.run_task(
        task_id="t3-016-player-composition",
        engine_name="unreal",
        candidate_dir=ref_dir,
        candidate_id="reference_t3_016_unreal",
    )

    assert res["status"] == RunStatus.PASS.value, f"Expected PASS, got {res['status']}. Summary: {res['summary_text']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "PASS"
    assert rep["layers"]["saved_asset_checks"]["status"] == "PASS"

    probes = rep["probes"]
    mandatory_probes = [
        "probe_c1_component_completeness",
        "probe_c2_component_uniqueness",
        "probe_c3_valid_references",
        "probe_c4_end_to_end_health_interaction",
        "probe_c5_end_to_end_stamina_interaction",
        "probe_c6_movement_parity",
        "probe_c7_health_parity",
        "probe_c8_scene_integrity",
        "probe_c9_spawn_and_cleanup",
    ]
    for p_id in mandatory_probes:
        assert p_id in probes, f"Mandatory probe '{p_id}' missing from report"
        assert probes[p_id]["passed"] is True, f"Probe '{p_id}' failed: {probes[p_id]}"


def test_composition_missing_component_is_rejected(runner, ue_discovery):
    """Candidate missing StaminaComponent is rejected by saved asset or behavior checks."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t3_016_failing_missing_comp")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t3-016-player-composition",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_missing_stamina_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"

    probes = rep.get("probes", {})
    asset_check = rep["layers"]["saved_asset_checks"]["status"]
    probe_check = rep["layers"]["behavior_probes"]["status"]
    assert asset_check == "FAIL" or probe_check == "FAIL"
    if "probe_c1_component_completeness" in probes:
        assert probes["probe_c1_component_completeness"]["passed"] is False


def test_composition_movement_regression_is_rejected(runner, ue_discovery):
    """Candidate with degraded walk speed is rejected by C6 movement parity probe."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t3_016_failing_movement")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t3-016-player-composition",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_movement_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep["probes"]
    assert probes["probe_c6_movement_parity"]["passed"] is False
