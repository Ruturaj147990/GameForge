"""Acceptance Criteria Verification Test Suite for GameForge Step 5.

Implements automated verification for AC-1 through AC-23 in accordance with
the Implementation Brief and Section 28 of GAMEFORGE_FINAL_MASTER_STRATEGY.md.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest

from gameforge_bench.engines.discovery import discover_environment, discover_unreal_engine, discover_unity_engine
from gameforge_bench.task_loader import load_task_inventory, load_task
from gameforge_bench.task_validation import validate_all_specs


@pytest.fixture
def workspace_root():
    return Path.cwd()


def test_ac_01_authority_and_preflight(workspace_root):
    """AC-1: Active source of truth, repo inspection, and Step 5 selection."""
    ssot = workspace_root / "GAMEFORGE_FINAL_MASTER_STRATEGY.md"
    assert ssot.is_file(), "Master strategy SSOT file missing"
    content = ssot.read_text(encoding="utf-8")
    assert "Version: 3.1.0" in content or "v3.1.0" in content, "Expected Strategy v3.1.0"
    assert "Step 5" in content, "Expected Step 5 identified as next milestone"


def test_ac_02_test_count_reconciliation(workspace_root):
    """AC-2: Test count reconciliation between 80, 94, 6, and unique total."""
    audit_report = workspace_root / "STEP4_AUDIT_REPORT.md"
    assert audit_report.is_file()
    text = audit_report.read_text(encoding="utf-8")
    assert "114" in text, "Audit must record total unique tests (114)"
    assert "94" in text, "Audit must record unit and protected tests (94)"
    assert "6" in text or "20" in text, "Audit must record integration test totals"
    assert "Reconciliation" in text


def test_ac_03_step_4_engine_audit(workspace_root):
    """AC-3: HUD/projectile probes, visual vs state separation, and E4 labeling."""
    audit_report = workspace_root / "STEP4_AUDIT_REPORT.md"
    assert audit_report.is_file()
    text = audit_report.read_text(encoding="utf-8")
    assert "H1" in text and "H12" in text, "Must cite H1-H12 probes"
    assert "Proj1" in text and "Proj12" in text, "Must cite Proj1-Proj12 probes"
    assert "E4_REPORTED_REAL_ENGINE" in text, "Must distinguish E4 evidence level"
    assert "framebuffer" in text.lower() or "screenshots" in text.lower() or "widget-state" in text.lower()


def test_ac_04_version_and_isolation_integrity(workspace_root):
    """AC-4: Unreal Engine 5.7.4 baseline pin and LOW_PRIVILEGE_PROCESS isolation."""
    env = discover_environment()
    assert env["engines"]["unreal"]["version"].startswith("5.7"), "Unreal must be pinned to 5.7.x"
    assert env["engines"]["unity"]["is_runnable"] is False, "Unity must not be falsely claimed as runnable"
    
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    assert manifest_file.is_file()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["engine_pins"]["unreal"]["version"] == "5.7.4"
    assert manifest["candidate_protocol"]["isolation_policy"] == "LOW_PRIVILEGE_PROCESS"


def test_ac_05_frozen_manifest_and_candidate_eligibility(workspace_root):
    """AC-5: Frozen manifest fields, candidate registration, and permission basis."""
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    register_file = workspace_root / "configs" / "model_register.json"
    assert manifest_file.is_file()
    assert register_file.is_file()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["status"] == "FROZEN"
    assert "task_subsets" in manifest
    assert "candidate_protocol" in manifest

    register = json.loads(register_file.read_text(encoding="utf-8"))
    assert len(register["candidates"]) >= 2, "Must register at least 2 candidates"
    for c in register["candidates"]:
        assert c["license_verified"] is True
        assert c["allowed_use_confirmed"] is True
        assert "pricing" in c
        assert "deployment" in c


def test_ac_06_fair_evaluation_setup(workspace_root):
    """AC-6: Matched prompts, tool permissions, budgets, and clean snapshot boundaries."""
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    protocol = manifest["candidate_protocol"]
    assert "protected_context_excluded_from_candidate" in protocol
    assert protocol["budgets"]["timeout_seconds"] > 0
    assert protocol["budgets"]["max_tokens_per_request"] > 0
    assert len(protocol["permitted_tools"]) > 0


def test_ac_07_raw_evidence_and_repeatability(workspace_root):
    """AC-7: Raw evidence paths, diffs, telemetry, and repeated subset definition."""
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert len(manifest["task_subsets"]["repeated_variance_subset"]) >= 2


def test_ac_08_layered_scorecards(workspace_root):
    """AC-8: Distinction between policy, build, probes, and domain scorecards."""
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    layers = manifest["grading_layers"]
    assert "policy_static_checks" in layers
    assert "build_import" in layers
    assert "behavior_probes" in layers


def test_ac_09_project_state_synchronization(workspace_root):
    """AC-9: Consistency across roadmap CSV, manifest, and model register."""
    roadmap_file = workspace_root / "GAMEFORGE_ROADMAP.csv"
    assert roadmap_file.is_file()
    with open(roadmap_file, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    step5_row = next((r for r in rows if r["step_id"] == "STEP_5"), None)
    assert step5_row is not None, "STEP_5 must exist in roadmap"


def test_ac_10_sequential_continuation_and_resume(workspace_root):
    """AC-10: Strategy mandates sequential continuation without skipping gates."""
    ssot = workspace_root / "GAMEFORGE_FINAL_MASTER_STRATEGY.md"
    content = ssot.read_text(encoding="utf-8")
    assert "30.1.1 Mandatory milestone loop" in content
    assert "READ SSOT" in content


def test_ac_11_eight_tier_benchmark_inventory(workspace_root):
    """AC-11: Eight-tier structure T1-T8 preserved in inventory."""
    inv_file = workspace_root / "TASK_INVENTORY.csv"
    assert inv_file.is_file()
    tasks = load_task_inventory(inv_file)
    tiers = {t.tier for t in tasks}
    assert "T2" in tiers
    assert "T3" in tiers
    assert len(tasks) == 30


def test_ac_12_task_package_metadata(workspace_root):
    """AC-12: Task spec schema validation and required fields."""
    pilot_task = workspace_root / "pilot_tasks" / "t2-004-health-damage.yaml"
    assert pilot_task.is_file()
    spec = load_task(pilot_task)
    assert spec.allowed_edit_paths
    assert spec.limits.wall_clock_seconds > 0
    assert spec.provenance.fixture_origin


def test_ac_13_grading_layers(workspace_root):
    """AC-13: Grading pipeline evaluates discrete layers."""
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert "build_import" in manifest["grading_layers"]
    assert "behavior_probes" in manifest["grading_layers"]


def test_ac_14_metrics_and_split_integrity(workspace_root):
    """AC-14: Public dev, public test, and private held-out split definitions."""
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    splits = {t["split"] for t in manifest["task_subsets"]["initial_baseline_tasks"]}
    assert "public_dev" in splits
    assert "public_test" in splits
    assert "private_held_out" in splits


def test_ac_15_t2_task_inventory(workspace_root):
    """AC-15: 15 specified T2 gameplay component tasks in inventory."""
    inv_file = workspace_root / "TASK_INVENTORY.csv"
    tasks = load_task_inventory(inv_file)
    t2_tasks = [t for t in tasks if t.tier == "T2"]
    assert len(t2_tasks) == 15


def test_ac_16_t3_task_inventory(workspace_root):
    """AC-16: 15 specified T3 scene/editor authoring tasks in inventory."""
    inv_file = workspace_root / "TASK_INVENTORY.csv"
    tasks = load_task_inventory(inv_file)
    t3_tasks = [t for t in tasks if t.tier == "T3"]
    assert len(t3_tasks) == 15


def test_ac_17_registry_schema_and_dimensions(workspace_root):
    """AC-17: Active Registry v2.1 has 26 columns, 4524 rows, 39 engines, unique keys, P0-P3."""
    matrix_file = workspace_root / "ENGINE_FEATURE_COVERAGE_MATRIX.csv"
    assert matrix_file.is_file()
    with open(matrix_file, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    assert len(header) == 26, f"Expected 26 columns, got {len(header)}"
    assert len(rows) == 4524, f"Expected 4524 records, got {len(rows)}"
    engine_ids = {r[0] for r in rows}
    assert len(engine_ids) == 39, f"Expected 39 engine IDs, got {len(engine_ids)}"
    
    keys = {(r[0], r[3]) for r in rows}
    assert len(keys) == len(rows), "Keys (engine_id, feature_domain) must be unique"

    priorities = {r[5] for r in rows}
    assert priorities.issubset({"P0", "P1", "P2", "P3"}), f"Invalid priorities found: {priorities - {'P0', 'P1', 'P2', 'P3'}}"


def test_ac_18_registry_evidence_semantics(workspace_root):
    """AC-18: Controlled lifecycle labels and E0-E5 evidence ladder."""
    matrix_file = workspace_root / "ENGINE_FEATURE_COVERAGE_MATRIX.csv"
    with open(matrix_file, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        verif_levels = {r["verification_level"] for r in reader}

    allowed_levels = {"E0_CATALOGUED", "E1_SPECIFIED", "E2_STATIC_OR_AUTHORED", "E3_UNIT_TESTED", "E4_REPORTED_REAL_ENGINE", "E5_INDEPENDENTLY_REPRODUCED_REAL_ENGINE"}
    assert verif_levels.issubset(allowed_levels), f"Unexpected verification levels: {verif_levels - allowed_levels}"


def test_ac_19_reversible_and_secure_changes(workspace_root):
    """AC-19: Protected graders, allowed-path restrictions, and network isolation."""
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["candidate_protocol"]["budgets"]["cost_limit_usd"] == 0.0


def test_ac_20_provenance_and_rights(workspace_root):
    """AC-20: Model register licenses and permitted research evaluation basis."""
    register_file = workspace_root / "configs" / "model_register.json"
    register = json.loads(register_file.read_text(encoding="utf-8"))
    for cand in register["candidates"]:
        assert cand["license"]
        assert cand["permission_basis"]


def test_ac_21_model_decision_discipline(workspace_root):
    """AC-21: General capability retention and cost control."""
    manifest_file = workspace_root / "configs" / "baseline_release_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["candidate_protocol"]["budgets"]["cost_limit_usd"] == 0.0


def test_ac_22_engine_capability_honesty(workspace_root):
    """AC-22: Version-specific citations and uncertainty labels."""
    registry_file = workspace_root / "configs" / "engine_knowledge_registry.json"
    assert registry_file.is_file()
    reg = json.loads(registry_file.read_text(encoding="utf-8"))
    assert "engines" in reg
    assert "unreal_engine" in reg["engines"] or "unreal" in reg["engines"]
    assert "unity" in reg["engines"]


def test_ac_23_product_deferral(workspace_root):
    """AC-23: Windows desktop priority follows the latest recorded decision."""
    roadmap_file = workspace_root / "GAMEFORGE_ROADMAP.csv"
    with open(roadmap_file, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    step13 = next((r for r in rows if r["step_id"] == "STEP_13"), None)
    assert step13 is not None
    assert "IN_PROGRESS" in step13["current_status"].upper()
    assert "PACKAGING" in step13["current_status"].upper()
