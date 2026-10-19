"""Integration tests evaluating the T2-004 Health and Damage System in real Unreal Engine."""

from pathlib import Path
import pytest
from gameforge_bench.engines.discovery import discover_unity_engine, discover_unreal_engine
from gameforge_bench.grading import RunStatus
from gameforge_bench.runner import BenchmarkRunner


@pytest.fixture
def ue_discovery():
    return discover_unreal_engine()


@pytest.fixture
def runner():
    return BenchmarkRunner(workspace_root=Path.cwd())


def test_health_reference_solution_passes_pipeline(runner, ue_discovery):
    """Reference solution must pass all build, asset, and 16 behavioral probes in real UE5."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    ref_dir = Path("graders/reference_solutions/unreal/t2_004_health")
    assert ref_dir.is_dir(), f"Reference solution directory missing: {ref_dir}"

    res = runner.run_task(
        task_id="t2-004-health-damage",
        engine_name="unreal",
        candidate_dir=ref_dir,
        candidate_id="reference_t2_004_unreal",
    )

    assert res["status"] == RunStatus.PASS.value, f"Expected PASS, got {res['status']}. Summary: {res['summary_text']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "PASS"
    assert rep["layers"]["saved_asset_checks"]["status"] == "PASS"

    probes = rep["probes"]
    # Verify mandatory probes from Section 7 acceptance table
    mandatory_probes = [
        "probe_initial_state",
        "probe_basic_damage",
        "probe_invulnerability_immediate",
        "probe_pre_expiry_boundary",
        "probe_post_expiry_boundary",
        "probe_no_timer_extension",
        "probe_healing",
        "probe_healing_clamp",
        "probe_healing_at_max_health",
        "probe_zero_damage",
        "probe_negative_damage",
        "probe_non_finite_input",
        "probe_lethal_damage",
        "probe_repeated_damage_after_death",
        "probe_healing_after_death",
        "probe_callback_reentrancy",
    ]
    for p_id in mandatory_probes:
        assert p_id in probes, f"Mandatory probe '{p_id}' missing from report"
        assert probes[p_id]["passed"] is True, f"Probe '{p_id}' failed: {probes[p_id]}"


def test_health_failing_invulnerability_is_rejected(runner, ue_discovery):
    """Candidate with defective invulnerability window compiles but is rejected by runtime probes."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t2_004_failing_invulnerability")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t2-004-health-damage",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_invulnerability_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep["probes"]
    assert probes["probe_invulnerability_immediate"]["passed"] is False or probes["probe_pre_expiry_boundary"]["passed"] is False


def test_health_failing_duplicate_death_is_rejected(runner, ue_discovery):
    """Candidate with duplicate death broadcast compiles but is rejected by runtime probe."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t2_004_failing_duplicate_death")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t2-004-health-damage",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_duplicate_death_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep["probes"]
    assert probes["probe_repeated_damage_after_death"]["passed"] is False


def test_unity_counterpart_reports_unverified_when_uninstalled(runner):
    """Verifies that requesting Unity when uninstalled correctly yields UNVERIFIED without false claims."""
    unity_disc = discover_unity_engine()
    if unity_disc.is_installed:
        pytest.skip("Unity is installed in environment")

    res = runner.run_task(
        task_id="t2-004-health-damage",
        engine_name="unity",
        candidate_dir="fixtures/unity/t2_004_health",
        candidate_id="unity_reference_uninstalled",
    )

    assert res["status"] == RunStatus.HARNESS_INVALID.value
    rep = res["report"]
    assert rep["status"] == RunStatus.HARNESS_INVALID.value
    assert rep["engine"]["version"] == "unverified"
    assert rep["layers"]["build_import"]["details"]["is_infrastructure_failure"] is True
