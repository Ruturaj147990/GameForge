"""Integration tests evaluating the T3-017 Health and Stamina UMG HUD Widget in real Unreal Engine."""

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


def test_hud_reference_solution_passes_pipeline(runner, ue_discovery):
    """Reference solution must pass all build, asset, and 12 HUD probes in real UE5."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    ref_dir = Path("graders/reference_solutions/unreal/t3_017_hud")
    assert ref_dir.is_dir(), f"Reference solution directory missing: {ref_dir}"

    res = runner.run_task(
        task_id="t3-017-health-hud",
        engine_name="unreal",
        candidate_dir=ref_dir,
        candidate_id="reference_t3_017_unreal",
    )

    assert res["status"] == RunStatus.PASS.value, f"Expected PASS, got {res['status']}. Summary: {res['summary_text']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "PASS"
    assert rep["layers"]["saved_asset_checks"]["status"] == "PASS"

    probes = rep["probes"]
    mandatory_probes = [
        "probe_h1_initial_display",
        "probe_h2_damage_update",
        "probe_h3_heal_update",
        "probe_h4_health_pickup_update",
        "probe_h5_stamina_pickup_update",
        "probe_h6_display_clamping",
        "probe_h7_death_state_display",
        "probe_h8_null_player_safety",
        "probe_h9_duplicate_subscription_guard",
        "probe_h10_clean_unsubscription",
        "probe_h11_reinitialization",
        "probe_h12_rebind_to_new_player",
    ]
    for p_id in mandatory_probes:
        resolved_id = p_id
        if resolved_id not in probes and resolved_id == "probe_h5_stamina_pickup_update":
            resolved_id = "probe_h5_stamina_update"
        assert resolved_id in probes, f"Mandatory probe '{p_id}' missing from report"
        assert probes[resolved_id]["passed"] is True, f"Probe '{resolved_id}' failed: {probes[resolved_id]}"


def test_hud_duplicate_subscription_defect_is_rejected(runner, ue_discovery):
    """Candidate with duplicate subscriptions is rejected by H9 probe."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t3_017_failing_duplicate_sub")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t3-017-health-hud",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_duplicate_sub_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep.get("probes", {})
    assert "probe_h9_duplicate_subscription_guard" in probes
    assert probes["probe_h9_duplicate_subscription_guard"]["passed"] is False


def test_hud_clamping_defect_is_rejected(runner, ue_discovery):
    """Candidate with broken display clamping is rejected by H6 probe."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t3_017_failing_clamping")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t3-017-health-hud",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_clamping_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep.get("probes", {})
    assert "probe_h6_display_clamping" in probes
    assert probes["probe_h6_display_clamping"]["passed"] is False
