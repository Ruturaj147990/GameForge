"""Integration tests evaluating the T2-008 Projectile Collision and Combat Damage in real Unreal Engine."""

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


def test_projectile_reference_solution_passes_pipeline(runner, ue_discovery):
    """Reference solution must pass all build, asset, and 12 projectile probes in real UE5."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    ref_dir = Path("graders/reference_solutions/unreal/t2_008_projectile")
    assert ref_dir.is_dir(), f"Reference solution directory missing: {ref_dir}"

    res = runner.run_task(
        task_id="t2-008-projectile-collision",
        engine_name="unreal",
        candidate_dir=ref_dir,
        candidate_id="reference_t2_008_unreal",
    )

    assert res["status"] == RunStatus.PASS.value, f"Expected PASS, got {res['status']}. Summary: {res['summary_text']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "PASS"
    assert rep["layers"]["saved_asset_checks"]["status"] == "PASS"

    probes = rep["probes"]
    mandatory_probes = [
        "probe_proj1_valid_hit_damage",
        "probe_proj2_duplicate_hit_prevention",
        "probe_proj3_owner_exclusion",
        "probe_proj4_invalid_target_safety",
        "probe_proj5_blocking_geometry_resolution",
        "probe_proj6_post_impact_cleanup",
        "probe_proj7_lifetime_cleanup",
        "probe_proj8_invulnerability_respected",
        "probe_proj9_post_expiry_hit",
        "probe_proj10_invalid_config_safety",
        "probe_proj11_death_and_zero_clamp",
        "probe_proj12_cross_system_parity",
    ]
    for p_id in mandatory_probes:
        assert p_id in probes, f"Mandatory probe '{p_id}' missing from report"
        assert probes[p_id]["passed"] is True, f"Probe '{p_id}' failed: {probes[p_id]}"


def test_projectile_no_damage_defect_is_rejected(runner, ue_discovery):
    """Candidate failing to apply damage on impact is rejected by Proj1 probe."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t2_008_failing_no_damage")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t2-008-projectile-collision",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_no_damage_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep.get("probes", {})
    assert "probe_proj1_valid_hit_damage" in probes
    assert probes["probe_proj1_valid_hit_damage"]["passed"] is False


def test_projectile_self_damage_defect_is_rejected(runner, ue_discovery):
    """Candidate damaging owner on initial overlap is rejected by Proj3 probe."""
    if not ue_discovery.is_installed:
        pytest.skip("Real Unreal Engine not installed in environment")

    defect_dir = Path("graders/reference_solutions/unreal/t2_008_failing_self_damage")
    assert defect_dir.is_dir(), f"Defect candidate directory missing: {defect_dir}"

    res = runner.run_task(
        task_id="t2-008-projectile-collision",
        engine_name="unreal",
        candidate_dir=defect_dir,
        candidate_id="defective_self_damage_candidate",
    )

    assert res["status"] == RunStatus.PARTIAL_BUILD.value, f"Expected PARTIAL_BUILD, got {res['status']}"
    rep = res["report"]
    assert rep["layers"]["build_import"]["status"] == "PASS"
    assert rep["layers"]["behavior_probes"]["status"] == "FAIL"

    probes = rep.get("probes", {})
    assert "probe_proj3_owner_exclusion" in probes
    assert probes["probe_proj3_owner_exclusion"]["passed"] is False
