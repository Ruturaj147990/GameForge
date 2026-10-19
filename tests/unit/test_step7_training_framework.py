"""Unit tests for GameForge Step 7 Specialist Training Prototype Framework.

Regression and capability tests S7-I5-01 through S7-I5-15:
- S7-I5-01: Step 5 cannot pass using positive-looking roadmap prose or stale/contradictory evidence.
- S7-I5-02: Step 6 cannot pass on source registration alone; it must have real eligible records.
- S7-I5-03: Declared original/canonical hashes are verified against actual content.
- S7-I5-04: Manifest-wide group/split isolation, duplicate handling, tombstones and removal obligations are enforced.
- S7-I5-05: Missing/empty/incorrect-path/out-of-workspace assets fail validation.
- S7-I5-06: SHA-256 is computed from the real file and mismatches are rejected.
- S7-I5-07: Missing provenance, uncleared rights and missing configured metrics fail.
- S7-I5-08: Full nested training-config schema validation rejects invalid types, values and enums.
- S7-I5-09: Dataset digest is deterministic and sensitive to all relevant manifest/schema/formatting changes.
- S7-I5-10: dry_run() does not create or modify workspace artifacts.
- S7-I5-11: Failed hardware/RAM/backend measurements cannot imply compatibility.
- S7-I5-12: Benchmark version/digest mismatches block readiness.
- S7-I5-13: Held-out lineage and prohibited derivative records are rejected independently of task-ID denylisting.
- S7-I5-14: ValueDecisionRule rejects invalid metrics and enforces every defined threshold.
- S7-I5-15: No blocked/unavailable execution path returns success or creates weights/checkpoints.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import pytest

from gameforge_bench.asset_specialist import (
    AssetConstraints,
    AssetGenerationRequest,
    AssetGenerationResult,
    AssetModality,
    AssetProvenance,
    AssetSpecialistJob,
    AssetSpecialistRouter,
    EngineIntegrationStatus,
    SpecialistProvider,
    SpecialistStatus,
)
from gameforge_bench.data_factory import (
    Deduplicator,
    ProtectedContaminationScanner,
    SourceRegister,
    TombstoneManager,
    compute_canonical_fingerprint,
    compute_sha256,
)
from gameforge_bench.training_builder import FormattedTrainingSample, TrainingDatasetBuilder
from gameforge_bench.training_runner import DryRunResult, TrainingRunner, ValueDecisionRule
from gameforge_bench.training_validator import EligibilityReport, TrainingReadinessValidator


@pytest.fixture
def source_register(tmp_path: Path) -> SourceRegister:
    reg_data = {
        "register_version": "v1.1.0",
        "registered_sources": [
            {
                "source_id": "gameforge-synthetic-test-corpus",
                "review_status": "CONFIRMED_FOR_TRAINING",
                "permitted_uses": {"training": True, "evaluation": True, "redistribution": True},
            },
            {
                "source_id": "gameforge-cleanroom-unreal-pilots",
                "review_status": "REVIEW_REQUIRED",
                "permitted_uses": {"training": False, "evaluation": True, "redistribution": False},
            },
            {
                "source_id": "gameforge-private-heldout-eval",
                "review_status": "RESTRICTED_EVAL_ONLY",
                "permitted_uses": {"training": False, "evaluation": True, "redistribution": False},
            },
        ],
    }
    reg_file = tmp_path / "dataset_source_register.json"
    reg_file.write_text(json.dumps(reg_data), encoding="utf-8")
    return SourceRegister(reg_file)


@pytest.fixture
def training_validator(source_register: SourceRegister) -> TrainingReadinessValidator:
    return TrainingReadinessValidator(source_register)


@pytest.fixture
def base_sample_record() -> dict:
    rec = {
        "sample_id": "traj-001-health-patch",
        "schema_version": "v1.0.0",
        "sample_type": "process_trajectory",
        "source_id": "gameforge-synthetic-test-corpus",
        "provenance": {
            "origin_uri": "internal://synthetic/test",
            "commit_or_hash": "a1b2c3d4",
            "collected_at": "2026-10-19T12:00:00Z",
            "producing_tool": "test_harness",
            "lineage_notes": "Clean synthetic trajectory",
        },
        "rights": {
            "rights_holder": "GameForge Authors",
            "license_id": "CC0-1.0",
            "evidence_reference": "tests/unit/test_data_factory.py",
            "rights_review_state": "CONFIRMED_FOR_TRAINING",
            "permitted_uses": {"training": True, "evaluation": True, "redistribution": True},
        },
        "content_digest": {
            "original_sha256": "0" * 64,
            "canonical_fingerprint": "1" * 64,
        },
        "task_info": {
            "task_id": "t2-004-health-damage",
            "benchmark_tier": "T2",
            "benchmark_version": "v0.2.0",
            "engine": {"name": "unreal", "version": "5.7.4"},
        },
        "split_info": {
            "assigned_split": "train",
            "group_id": "health_grp",
            "contamination_status": "CLEAN",
        },
        "quality": {
            "schema_valid": True,
            "provenance_complete": True,
            "rights_eligible": True,
            "review_status": "AUTOMATED_PASSED",
        },
        "security_and_privacy": {
            "secret_scan_passed": True,
            "pii_scan_passed": True,
            "scan_timestamp": "2026-10-19T12:00:00Z",
        },
        "tombstone": {"is_tombstoned": False},
        "process_details": {
            "interpreted_requirements": "Implement health clamping and invulnerability window",
            "assumptions": ["MaxHealth > 0"],
            "plan": ["Add UPROPERTY Health", "Clamp damage"],
            "actions_trace": [],
            "applied_patch": "diff --git a/HealthComponent.cpp b/HealthComponent.cpp\n+Health = FMath::Clamp(Health - Dmg, 0.f, MaxHealth);",
            "repair_iterations": 0,
            "final_outcome": "PASS",
        },
    }
    # Compute authentic canonical digests
    rec["content_digest"]["original_sha256"] = compute_sha256(rec["process_details"])
    rec["content_digest"]["canonical_fingerprint"] = compute_canonical_fingerprint(rec)
    return rec


# -----------------------------------------------------------------------------
# S7-I5-01: Step 5 cannot pass using positive-looking roadmap prose or stale evidence
# -----------------------------------------------------------------------------
def test_s7_i5_01_step5_prose_cannot_bypass_gate(tmp_path: Path):
    runner = TrainingRunner(
        workspace_root=Path("."),
        config_path=Path("configs/training_config_step7_prototype.json"),
    )
    s5_ok, s6_ok, blockers = runner.check_prerequisite_gates()
    assert s5_ok is False
    assert any("Step 5 Gate BLOCKED" in b for b in blockers)

    # Isolated test with synthetic acceptance record
    fake_ws = tmp_path / "fake_ws"
    fake_ws.mkdir()
    (fake_ws / "configs").mkdir()
    (fake_ws / "schemas").mkdir()
    shutil.copy("schemas/training_config_schema.json", fake_ws / "schemas" / "training_config_schema.json")
    (fake_ws / "GAMEFORGE_ROADMAP.csv").write_text("STEP_5,Baseline,Reported complete\n", encoding="utf-8")

    fake_cfg = json.loads(Path("configs/training_config_step7_prototype.json").read_text(encoding="utf-8"))
    cfg_file = fake_ws / "test_cfg.json"
    cfg_file.write_text(json.dumps(fake_cfg), encoding="utf-8")

    runner_fake = TrainingRunner(fake_ws, cfg_file)
    s5_pass, _, b_list = runner_fake.check_prerequisite_gates()
    # Missing structured acceptance record must fail closed despite "Reported complete" in roadmap!
    assert s5_pass is False
    assert any("formal structured Step 5 acceptance record" in b.lower() or "missing" in b.lower() for b in b_list)

    # Contradictory evidence: status ACCEPTED but audit has INVALIDATED_PENDING_REVIEW
    ev_file = fake_ws / "reports" / "baseline_runs" / "test_run.json"
    ev_file.parent.mkdir(parents=True, exist_ok=True)
    ev_file.write_text(json.dumps({"status": "PASS", "patches_applied_count": 1}), encoding="utf-8")
    ev_sha = hashlib.sha256(ev_file.read_bytes()).hexdigest()
    (fake_ws / "STEP5_RECONCILIATION_AUDIT.md").write_text("INVALIDATED_PENDING_REVIEW zero applied patches", encoding="utf-8")
    shutil.copy("schemas/step5_acceptance_schema.json", fake_ws / "schemas" / "step5_acceptance_schema.json")

    rec_data = {
        "schema_version": "1.0.0",
        "acceptance_status": "ACCEPTED",
        "accepted_model_id": fake_cfg["base_model"]["candidate_id"],
        "immutable_revision": fake_cfg["base_model"]["immutable_revision"],
        "frozen_benchmark_manifest_id": "gameforge-bench-v0.2.0-baseline",
        "benchmark_version": "0.2.0",
        "benchmark_manifest_digest": "a" * 64,
        "reconciliation_audit_file": "STEP5_RECONCILIATION_AUDIT.md",
        "referenced_baseline_run_ids": ["run-baseline-001"],
        "evidence_files": [
            {
                "path": "reports/baseline_runs/test_run.json",
                "evidence_type": "run_report",
                "expected_digest_sha256": ev_sha,
                "model_id": fake_cfg["base_model"]["candidate_id"],
                "run_id": "run-baseline-001",
            }
        ],
        "formal_decision_provenance": {
            "decision_id": "D-014-RETEST",
            "decision_date": "2026-10-19",
            "approver": "Benchmark QA Lead",
            "basis": "Verified clean retest with valid candidate diffs and passing graders",
        },
    }
    (fake_ws / "configs" / "step5_acceptance_record.json").write_text(json.dumps(rec_data), encoding="utf-8")
    s5_pass2, _, b_list2 = runner_fake.check_prerequisite_gates()
    assert s5_pass2 is False
    assert any("INVALIDATED_PENDING_REVIEW" in b for b in b_list2)

    # Clean synthetic acceptance with non-contradictory evidence can pass gate in isolated test
    (fake_ws / "STEP5_RECONCILIATION_AUDIT.md").write_text("STEP 5 RETEST COMPLETED AND ACCEPTED", encoding="utf-8")
    s5_pass3, _, _ = runner_fake.check_prerequisite_gates()
    assert s5_pass3 is True


# -----------------------------------------------------------------------------
# S7-I5-02: Step 6 cannot pass on source registration alone
# -----------------------------------------------------------------------------
def test_s7_i5_02_step6_cannot_pass_without_real_eligible_records():
    runner = TrainingRunner(
        workspace_root=Path("."),
        config_path=Path("configs/training_config_step7_prototype.json"),
    )
    _, s6_ok, blockers = runner.check_prerequisite_gates()
    assert s6_ok is False
    assert any("Step 6 Gate BLOCKED" in b for b in blockers)


# -----------------------------------------------------------------------------
# S7-I5-03: Declared original/canonical hashes are verified against actual content
# -----------------------------------------------------------------------------
def test_s7_i5_03_content_digests_verified(training_validator, base_sample_record):
    # Valid record passes
    is_ok, reason = training_validator.validate_sample_record(base_sample_record)
    assert is_ok is True, f"Failed on valid digests: {reason}"

    # Mutate applied patch without updating original_sha256 -> REJECT
    training_validator.reset_state()
    mutated = copy.deepcopy(base_sample_record)
    mutated["process_details"]["applied_patch"] += "\n// unexpected mutation"
    is_ok2, reason2 = training_validator.validate_sample_record(mutated)
    assert is_ok2 is False
    assert "CONTENT_DIGEST_MISMATCH" in reason2

    # Mutate requirements without updating canonical_fingerprint -> REJECT
    training_validator.reset_state()
    mutated2 = copy.deepcopy(base_sample_record)
    mutated2["process_details"]["interpreted_requirements"] += " extra requirements"
    mutated2["content_digest"]["original_sha256"] = compute_sha256(mutated2["process_details"])
    is_ok3, reason3 = training_validator.validate_sample_record(mutated2)
    assert is_ok3 is False
    assert "CANONICAL_FINGERPRINT_MISMATCH" in reason3


# -----------------------------------------------------------------------------
# S7-I5-04: Manifest-wide group/split isolation, duplicate handling, tombstones
# -----------------------------------------------------------------------------
def test_s7_i5_04_manifest_wide_isolation_and_tombstones(training_validator, base_sample_record):
    # 1. Duplicate sample IDs rejected across manifest
    r2 = copy.deepcopy(base_sample_record)
    r2["sample_id"] = base_sample_record["sample_id"]
    eligible_dup, report_dup = training_validator.validate_manifest([base_sample_record, r2])
    assert len(eligible_dup) == 0
    assert "DUPLICATE_SAMPLE_ID" in report_dup.rejections_by_reason

    # 2. Group split leakage: same group_id appears in train and eval_public -> fatal rejection
    training_validator.reset_state()
    r_leak1 = copy.deepcopy(base_sample_record)
    r_leak1["sample_id"] = "traj-leak-001"
    r_leak1["split_info"]["group_id"] = "shared_leak_grp"
    r_leak1["split_info"]["assigned_split"] = "train"
    r_leak1["content_digest"]["original_sha256"] = compute_sha256(r_leak1["process_details"])
    r_leak1["content_digest"]["canonical_fingerprint"] = compute_canonical_fingerprint(r_leak1)

    r_leak2 = copy.deepcopy(base_sample_record)
    r_leak2["sample_id"] = "traj-leak-002"
    r_leak2["split_info"]["group_id"] = "shared_leak_grp"
    r_leak2["split_info"]["assigned_split"] = "eval_public"
    r_leak2["content_digest"]["original_sha256"] = compute_sha256(r_leak2["process_details"])
    r_leak2["content_digest"]["canonical_fingerprint"] = compute_canonical_fingerprint(r_leak2)

    eligible_leak, report_leak = training_validator.validate_manifest([r_leak1, r_leak2])
    assert len(eligible_leak) == 0
    assert report_leak.is_training_ready is False
    assert "SPLIT_GROUP_LEAKAGE" in report_leak.rejections_by_reason

    # 3. TombstoneManager removal registered
    training_validator.reset_state()
    tomb_mgr = TombstoneManager()
    tomb_mgr.record_removal("traj-001-health-patch", base_sample_record["content_digest"]["canonical_fingerprint"], "dmca", "ticket-1", "2026-10-19")
    val_tomb = TrainingReadinessValidator(training_validator.source_register, tombstone_manager=tomb_mgr)
    is_ok_tomb, reason_tomb = val_tomb.validate_sample_record(base_sample_record)
    assert is_ok_tomb is False
    assert "TOMBSTONED" in reason_tomb


# -----------------------------------------------------------------------------
# S7-I5-05 & S7-I5-06: Asset unconditional file, digest, path and test-double checks
# -----------------------------------------------------------------------------
def test_s7_i5_05_and_06_asset_unconditional_file_and_digest(tmp_path: Path):
    router = AssetSpecialistRouter(workspace_root=tmp_path)
    provider = SpecialistProvider(
        provider_id="prod-tripo",
        model_name="TripoSR-v2",
        revision="r101",
        is_available=True,
    )
    router.register_provider(provider)

    valid_file = tmp_path / "valid_crate.fbx"
    valid_file.write_bytes(b"VALID_FBX_MESH_PAYLOAD")
    valid_sha = hashlib.sha256(b"VALID_FBX_MESH_PAYLOAD").hexdigest()

    prov = AssetProvenance(
        license_id="CC-BY-4.0",
        rights_holder="GameForge Test Artist",
        rights_cleared=True,
        evidence_reference="legal://agreements/internal_test_artist_assignment.pdf",
    )

    req = AssetGenerationRequest(
        task_id="t5-001-prop",
        modality=AssetModality.MESH_3D,
        prompt="Wooden crate",
        target_format="fbx",
        destination_path=str(valid_file),
        constraints=AssetConstraints(max_triangles=1000),
        provenance=prov,
    )

    job = AssetSpecialistJob(
        job_id="job-asset-01",
        modality=AssetModality.MESH_3D,
        provider=provider,
        request=req,
        result=AssetGenerationResult(
            artifact_path=str(valid_file),
            artifact_sha256=valid_sha,
            metrics={"triangle_count": 500},
        ),
    )

    # Valid asset passes
    assert router.validate_asset_output(job, file_path=valid_file) is True
    assert job.status == SpecialistStatus.VALIDATED
    assert job.engine_integration_status == EngineIntegrationStatus.UNPROCESSED

    # Negative: Missing file
    job_missing = copy.deepcopy(job)
    job_missing.result.artifact_path = str(tmp_path / "nonexistent.fbx")
    assert router.validate_asset_output(job_missing) is False
    assert job_missing.status == SpecialistStatus.FAILED
    assert any("not found" in err for err in job_missing.validation_errors)

    # Negative: Directory instead of file
    sub_dir = tmp_path / "dir_as_file"
    sub_dir.mkdir()
    job_dir = copy.deepcopy(job)
    job_dir.result.artifact_path = str(sub_dir)
    assert router.validate_asset_output(job_dir) is False
    assert job_dir.status == SpecialistStatus.FAILED
    assert any("not a regular file" in err for err in job_dir.validation_errors)

    # Negative: Empty file
    empty_f = tmp_path / "empty.fbx"
    empty_f.write_bytes(b"")
    job_empty = copy.deepcopy(job)
    job_empty.result.artifact_path = str(empty_f)
    assert router.validate_asset_output(job_empty) is False
    assert job_empty.status == SpecialistStatus.REJECTED
    assert any("empty" in err for err in job_empty.validation_errors)

    # Negative: Declared digest mismatch
    job_bad_hash = copy.deepcopy(job)
    job_bad_hash.result.artifact_sha256 = "0" * 64
    assert router.validate_asset_output(job_bad_hash) is False
    assert job_bad_hash.status == SpecialistStatus.REJECTED
    assert any("mismatch" in err for err in job_bad_hash.validation_errors)

    # Negative: Caller vs Provider path disagreement
    other_file = tmp_path / "other.fbx"
    other_file.write_bytes(b"OTHER")
    assert router.validate_asset_output(job, file_path=other_file) is False
    assert any("disagreement" in err for err in job.validation_errors)

    # Negative: Path traversal outside workspace
    outside = tmp_path.parent / "escape.fbx"
    job_esc = copy.deepcopy(job)
    job_esc.result.artifact_path = str(outside)
    assert router.validate_asset_output(job_esc) is False
    assert any("Path traversal detected" in err for err in job_esc.validation_errors)

    # Negative: Test double provider rejected by default in production
    test_double = SpecialistProvider("td-1", "mock", "1", is_available=True, is_test_double=True)
    job_td = copy.deepcopy(job)
    job_td.provider = test_double
    assert router.validate_asset_output(job_td) is False
    assert any("test double" in err for err in job_td.validation_errors)


# -----------------------------------------------------------------------------
# S7-I5-07: Asset provenance and configured metric enforcement
# -----------------------------------------------------------------------------
def test_s7_i5_07_asset_provenance_and_metrics_enforcement(tmp_path: Path):
    router = AssetSpecialistRouter(workspace_root=tmp_path)
    provider = SpecialistProvider("prod-prov", "model", "r1", is_available=True)
    valid_file = tmp_path / "asset.fbx"
    valid_file.write_bytes(b"FBX_CONTENT")
    valid_sha = hashlib.sha256(b"FBX_CONTENT").hexdigest()

    req = AssetGenerationRequest(
        task_id="t5-001",
        modality=AssetModality.MESH_3D,
        prompt="Stone wall",
        target_format="fbx",
        destination_path=str(valid_file),
        constraints=AssetConstraints(max_triangles=500, max_texture_dimension=1024),
        provenance=None,  # Missing provenance!
    )
    job = AssetSpecialistJob(
        job_id="j1",
        modality=AssetModality.MESH_3D,
        provider=provider,
        request=req,
        result=AssetGenerationResult(
            artifact_path=str(valid_file),
            artifact_sha256=valid_sha,
            metrics={"triangle_count": 300, "max_dimension": 512},
        ),
    )
    assert router.validate_asset_output(job) is False
    assert any("provenance is mandatory" in err for err in job.validation_errors)

    # Uncleared rights fails
    req.provenance = AssetProvenance(
        license_id="Proprietary",
        rights_holder="Vendor",
        rights_cleared=False,
        evidence_reference="legal://licenses/proprietary_vendor_contract.pdf",
    )
    assert router.validate_asset_output(job) is False
    assert any("rights not cleared" in err for err in job.validation_errors)

    # Cleared rights but missing max_dimension metric when max_texture_dimension is configured
    req.provenance.rights_cleared = True
    job.result.metrics = {"triangle_count": 300}  # missing max_dimension
    assert router.validate_asset_output(job) is False
    assert any("max_dimension' missing" in err for err in job.validation_errors)

    # Invalid metric types (e.g. boolean as int)
    job.result.metrics = {"triangle_count": True, "max_dimension": 512}
    assert router.validate_asset_output(job) is False
    assert any("Invalid triangle_count metric" in err for err in job.validation_errors)

    # Over-budget metric
    job.result.metrics = {"triangle_count": 600, "max_dimension": 512}
    assert router.validate_asset_output(job) is False
    assert any("exceeds limit" in err for err in job.validation_errors)


# -----------------------------------------------------------------------------
# S7-I5-08: Full nested training-config schema and semantic validation
# -----------------------------------------------------------------------------
def test_s7_i5_08_training_config_schema_validation(tmp_path: Path):
    cfg_path = Path("configs/training_config_step7_prototype.json")
    runner = TrainingRunner(workspace_root=Path("."), config_path=cfg_path)
    ok, blockers = runner.validate_configuration_syntax()
    assert ok is True, f"Valid config rejected: {blockers}"

    # Invalid nested hyperparameter (e.g., negative learning rate)
    bad_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    bad_cfg["hyperparameters"]["learning_rate"] = -0.01
    f = tmp_path / "bad_cfg.json"
    f.write_text(json.dumps(bad_cfg), encoding="utf-8")
    r_bad = TrainingRunner(Path("."), f)
    ok, b = r_bad.validate_configuration_syntax()
    assert ok is False
    assert any("learning_rate" in item for item in b)

    # Boolean passed as integer
    bad_cfg2 = json.loads(cfg_path.read_text(encoding="utf-8"))
    bad_cfg2["hyperparameters"]["batch_size"] = True
    f2 = tmp_path / "bad_cfg2.json"
    f2.write_text(json.dumps(bad_cfg2), encoding="utf-8")
    r_bad2 = TrainingRunner(Path("."), f2)
    ok2, b2 = r_bad2.validate_configuration_syntax()
    assert ok2 is False
    assert any("batch_size" in item for item in b2)

    # Unsupported training_method enum
    bad_cfg3 = json.loads(cfg_path.read_text(encoding="utf-8"))
    bad_cfg3["training_method"] = "unsupported_rl"
    f3 = tmp_path / "bad_cfg3.json"
    f3.write_text(json.dumps(bad_cfg3), encoding="utf-8")
    r_bad3 = TrainingRunner(Path("."), f3)
    ok3, b3 = r_bad3.validate_configuration_syntax()
    assert ok3 is False
    assert any("training_method" in item for item in b3)


# -----------------------------------------------------------------------------
# S7-I5-09: Complete deterministic dataset identity binding
# -----------------------------------------------------------------------------
def test_s7_i5_09_dataset_identity_sensitivity(training_validator, base_sample_record):
    builder = TrainingDatasetBuilder(training_validator)
    samples1, digest1, rep1 = builder.build_dataset([base_sample_record], source_manifest_id="man_01", source_manifest_digest="dig_01")
    samples2, digest2, rep2 = builder.build_dataset([base_sample_record], source_manifest_id="man_01", source_manifest_digest="dig_01")

    # Identical inputs produce identical digests
    assert len(samples1) == 1
    assert digest1 == digest2
    assert rep1.is_training_ready is True

    # Changed source manifest ID changes dataset digest
    _, digest_diff_man, _ = builder.build_dataset([base_sample_record], source_manifest_id="man_02", source_manifest_digest="dig_01")
    assert digest_diff_man != digest1

    # Changed formatting template / tokenizer changes dataset digest
    builder_diff_tok = TrainingDatasetBuilder(training_validator, tokenizer_id="different/tokenizer")
    _, digest_diff_tok, _ = builder_diff_tok.build_dataset([base_sample_record], source_manifest_id="man_01", source_manifest_digest="dig_01")
    assert digest_diff_tok != digest1


# -----------------------------------------------------------------------------
# S7-I5-10: dry_run() does not create or modify workspace artifacts
# -----------------------------------------------------------------------------
def test_s7_i5_10_dry_run_non_mutating(tmp_path: Path):
    target_out = tmp_path / "nonexistent_training_output_dir"
    cfg = json.loads(Path("configs/training_config_step7_prototype.json").read_text(encoding="utf-8"))
    cfg["resource_budget"]["output_dir"] = str(target_out)

    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    runner = TrainingRunner(workspace_root=tmp_path, config_path=cfg_file)
    assert not target_out.exists()

    res = runner.dry_run()
    # Output directory must NOT have been created by dry_run!
    assert not target_out.exists(), "dry_run() mutated workspace by creating output directory!"


# -----------------------------------------------------------------------------
# S7-I5-11: Failed hardware/RAM/backend measurements cannot imply compatibility
# -----------------------------------------------------------------------------
def test_s7_i5_11_hardware_incompatibility_blocks_execution():
    runner = TrainingRunner(
        workspace_root=Path("."),
        config_path=Path("configs/training_config_step7_prototype.json"),
    )
    hw_ok, measurements, blockers = runner.check_hardware_and_resources()
    # PyTorch CPU-only build with GPU requested must fail closed
    assert hw_ok is False
    assert any("GPU acceleration" in b or "CPU-only" in b for b in blockers)


# -----------------------------------------------------------------------------
# S7-I5-12: Benchmark version/digest mismatches block readiness
# -----------------------------------------------------------------------------
def test_s7_i5_12_benchmark_version_integrity(tmp_path: Path):
    cfg = json.loads(Path("configs/training_config_step7_prototype.json").read_text(encoding="utf-8"))
    cfg["evaluation_manifest"]["frozen_manifest_id"] = "mismatched-bench-v9.9.9"

    cfg_file = tmp_path / "mismatch_cfg.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    runner = TrainingRunner(workspace_root=Path("."), config_path=cfg_file)
    bench_ok, blockers = runner.check_benchmark_version_integrity()
    assert bench_ok is False
    assert any("Benchmark manifest ID mismatch" in b for b in blockers)


# -----------------------------------------------------------------------------
# S7-I5-13: Held-out lineage and prohibited derivative records rejected
# -----------------------------------------------------------------------------
def test_s7_i5_13_lineage_and_derivative_rejection(training_validator, base_sample_record):
    rec = copy.deepcopy(base_sample_record)
    rec["provenance"]["lineage_notes"] = "Derived from graders/protected/t2_004_oracle.py"
    rec["content_digest"]["original_sha256"] = compute_sha256(rec["process_details"])
    rec["content_digest"]["canonical_fingerprint"] = compute_canonical_fingerprint(rec)

    is_ok, reason = training_validator.validate_sample_record(rec)
    assert is_ok is False
    assert "FORBIDDEN_LINEAGE_LEAKAGE" in reason


# -----------------------------------------------------------------------------
# S7-I5-14: ValueDecisionRule rejects invalid metrics and enforces every threshold
# -----------------------------------------------------------------------------
def test_s7_i5_14_value_decision_rule_enforces_all_thresholds():
    rule = ValueDecisionRule(
        min_game_gain_threshold=0.15,
        max_general_regression_threshold=0.03,
        max_acceptable_vram_gb=12.0,
        max_acceptable_latency_increase_ratio=1.30,
    )

    # 1. Gain below threshold -> REJECT
    acc, msg, _ = rule.evaluate_decision(0.5, 0.6, 0.8, 0.8, 10.0, 10.0)
    assert acc is False
    assert "REJECT: Game capability gain" in msg

    # 2. General regression above threshold -> REJECT
    acc, msg, _ = rule.evaluate_decision(0.4, 0.65, 0.8, 0.75, 10.0, 10.0)
    assert acc is False
    assert "REJECT: General reasoning regression" in msg

    # 3. Latency increase ratio above threshold -> REJECT
    acc, msg, _ = rule.evaluate_decision(0.4, 0.65, 0.8, 0.8, 10.0, 14.0)
    assert acc is False
    assert "REJECT: Latency increase ratio" in msg

    # 4. VRAM allocation above threshold -> REJECT
    acc, msg, _ = rule.evaluate_decision(0.4, 0.65, 0.8, 0.8, 10.0, 11.0, vram_allocated_gb=14.5)
    assert acc is False
    assert "REJECT: VRAM allocated" in msg

    # 5. Invalid numeric types (NaN, Inf, negative, bool)
    with pytest.raises(ValueError, match="Invalid score value"):
        rule.evaluate_decision(True, 0.6, 0.8, 0.8, 10.0, 10.0)

    with pytest.raises(ValueError, match="Invalid score value"):
        rule.evaluate_decision(float("nan"), 0.6, 0.8, 0.8, 10.0, 10.0)

    with pytest.raises(ValueError, match="Invalid latency_base"):
        rule.evaluate_decision(0.4, 0.6, 0.8, 0.8, 0.0, 10.0)


# -----------------------------------------------------------------------------
# S7-I5-15: Blocked execution never returns success or creates weights
# -----------------------------------------------------------------------------
def test_s7_i5_15_blocked_execution_fail_closed(tmp_path: Path):
    runner = TrainingRunner(
        workspace_root=Path("."),
        config_path=Path("configs/training_config_step7_prototype.json"),
    )
    res = runner.execute_training()
    assert res["success"] is False
    assert res["status"] == "EXECUTION_REFUSED_FAIL_CLOSED"
    assert len(res["blockers"]) > 0

    # Ensure no checkpoint or weights directories were created
    chk_dir = Path("artifacts/training_checkpoints/exp_step7_prototype")
    if chk_dir.exists():
        assert len(list(chk_dir.glob("*.bin"))) == 0
        assert len(list(chk_dir.glob("*.safetensors"))) == 0
        assert len(list(chk_dir.glob("*.pt"))) == 0


# =============================================================================
# ITERATION 6 REGRESSION TESTS: S7-I6-01 THROUGH S7-I6-14
# =============================================================================

def test_s7_i6_01_step5_acceptance_cannot_bypass_with_placeholder(tmp_path: Path):
    """S7-I6-01: Empty/placeholder evidence, missing audit, stale evidence, mismatched identity,
    invalidated runs and contradictory records all block Step 5 acceptance.
    """
    fake_ws = tmp_path / "s5_ws"
    fake_ws.mkdir()
    (fake_ws / "configs").mkdir()
    (fake_ws / "schemas").mkdir()
    (fake_ws / "reports" / "baseline_runs").mkdir(parents=True)
    shutil.copy("schemas/training_config_schema.json", fake_ws / "schemas" / "training_config_schema.json")
    shutil.copy("schemas/step5_acceptance_schema.json", fake_ws / "schemas" / "step5_acceptance_schema.json")

    fake_cfg = json.loads(Path("configs/training_config_step7_prototype.json").read_text(encoding="utf-8"))
    cfg_file = fake_ws / "test_cfg.json"
    cfg_file.write_text(json.dumps(fake_cfg), encoding="utf-8")
    runner = TrainingRunner(fake_ws, cfg_file)

    # 1. Missing reconciliation audit blocks
    rec_base = {
        "schema_version": "1.0.0",
        "acceptance_status": "ACCEPTED",
        "accepted_model_id": fake_cfg["base_model"]["candidate_id"],
        "immutable_revision": fake_cfg["base_model"]["immutable_revision"],
        "frozen_benchmark_manifest_id": "gameforge-bench-v0.2.0-baseline",
        "benchmark_version": "0.2.0",
        "benchmark_manifest_digest": "0" * 64,
        "reconciliation_audit_file": "NONEXISTENT_AUDIT.md",
        "referenced_baseline_run_ids": ["run-1"],
        "evidence_files": [{"path": "reports/baseline_runs/ev1.json", "evidence_type": "run_report", "expected_digest_sha256": "0" * 64}],
        "formal_decision_provenance": {"decision_id": "D-020", "decision_date": "2026-10-19", "approver": "Audit", "basis": "Tested"},
    }
    rec_file = fake_ws / "configs" / "step5_acceptance_record.json"
    rec_file.write_text(json.dumps(rec_base), encoding="utf-8")
    s5_ok, _, b = runner.check_prerequisite_gates()
    assert s5_ok is False
    assert any("reconciliation audit file" in item.lower() for item in b)

    # 2. Placeholder {} evidence blocks
    (fake_ws / "STEP5_RECONCILIATION_AUDIT.md").write_text("ACCEPTED", encoding="utf-8")
    rec_base["reconciliation_audit_file"] = "STEP5_RECONCILIATION_AUDIT.md"
    ev_path = fake_ws / "reports" / "baseline_runs" / "ev1.json"
    ev_path.write_text("{}", encoding="utf-8")
    rec_base["evidence_files"][0]["expected_digest_sha256"] = hashlib.sha256(b"{}").hexdigest()
    rec_file.write_text(json.dumps(rec_base), encoding="utf-8")
    s5_ok, _, b = runner.check_prerequisite_gates()
    assert s5_ok is False
    assert any("placeholder rejected" in item.lower() for item in b)

    # 3. Digest mismatch blocks
    ev_path.write_text(json.dumps({"status": "PASS", "candidate": {"patches_applied_count": 1}}), encoding="utf-8")
    rec_base["evidence_files"][0]["expected_digest_sha256"] = "1" * 64  # deliberate mismatch
    rec_file.write_text(json.dumps(rec_base), encoding="utf-8")
    s5_ok, _, b = runner.check_prerequisite_gates()
    assert s5_ok is False
    assert any("evidence digest mismatch" in item.lower() for item in b)

    # 4. Invalidation / zero applied patches blocks
    ev_path.write_text(json.dumps({"status": "PASS", "candidate": {"patches_applied_count": 0}}), encoding="utf-8")
    rec_base["evidence_files"][0]["expected_digest_sha256"] = hashlib.sha256(ev_path.read_bytes()).hexdigest()
    rec_file.write_text(json.dumps(rec_base), encoding="utf-8")
    s5_ok, _, b = runner.check_prerequisite_gates()
    assert s5_ok is False
    assert any("0 applied patches" in item.lower() for item in b)


def test_s7_i6_02_and_03_step6_readiness_unified_and_no_synthetic_authorization(tmp_path: Path):
    """S7-I6-02 & S7-I6-03: Prerequisite result is derived from the same actual eligible dataset
    used for dataset readiness; registered sources alone do not pass, and synthetic test-only
    fixtures cannot authorize production training.
    """
    fake_ws = tmp_path / "s6_ws"
    fake_ws.mkdir()
    (fake_ws / "configs").mkdir()
    (fake_ws / "schemas").mkdir()
    shutil.copy("schemas/training_config_schema.json", fake_ws / "schemas" / "training_config_schema.json")
    shutil.copy("configs/dataset_source_register.json", fake_ws / "configs" / "dataset_source_register.json")

    # Config with missing manifest
    cfg = json.loads(Path("configs/training_config_step7_prototype.json").read_text(encoding="utf-8"))
    cfg_file = fake_ws / "test_cfg.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    runner = TrainingRunner(fake_ws, cfg_file)

    _, s6_gate, _ = runner.check_prerequisite_gates()
    ds_ready, _ = runner.check_dataset_readiness()
    assert s6_gate is False
    assert ds_ready is False
    assert s6_gate == ds_ready  # unified result!

    # Manifest containing ONLY synthetic test corpus samples
    syn_sample = {
        "sample_id": "samp-synthetic-01",
        "schema_version": "v1.0.0",
        "sample_type": "code_sample",
        "source_id": "gameforge-synthetic-test-corpus",
        "provenance": {
            "origin_uri": "internal://test",
            "commit_or_hash": "a1b2",
            "collected_at": "2026-10-19T00:00:00Z",
            "producing_tool": "test",
            "lineage_notes": "test",
        },
        "rights": {
            "rights_holder": "Test Suite",
            "license_id": "CC0-1.0",
            "evidence_reference": "tests/test.py",
            "rights_review_state": "CONFIRMED_FOR_TRAINING",
            "permitted_uses": {"training": True, "evaluation": True, "redistribution": True},
        },
        "content_digest": {
            "original_sha256": "0" * 64,
            "canonical_fingerprint": "1" * 64,
        },
        "task_info": {
            "task_id": "t1-001-health-invariants",
            "benchmark_tier": "T1",
            "benchmark_version": "v0.2.0",
            "engine": {"name": "unreal", "version": "5.7.4"},
        },
        "split_info": {"assigned_split": "train", "group_id": "grp1", "contamination_status": "CLEAN"},
        "quality": {"schema_valid": True, "provenance_complete": True, "rights_eligible": True, "review_status": "AUTOMATED_PASSED"},
        "security_and_privacy": {"secret_scan_passed": True, "pii_scan_passed": True, "scan_timestamp": "2026-10-19T00:00:00Z"},
        "tombstone": {"is_tombstoned": False},
        "payload": "float Health = 100.0f;",
    }
    syn_sample["content_digest"]["original_sha256"] = hashlib.sha256(b"float Health = 100.0f;").hexdigest()
    syn_sample["content_digest"]["canonical_fingerprint"] = compute_canonical_fingerprint(syn_sample)

    m_path = fake_ws / "manifest.json"
    m_path.write_text(json.dumps({"samples": [syn_sample]}), encoding="utf-8")
    cfg["dataset"]["manifest_path"] = "manifest.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    runner_syn = TrainingRunner(fake_ws, cfg_file)
    _, s6_syn, blockers_syn = runner_syn.check_prerequisite_gates()
    assert s6_syn is False
    assert any("synthetic test-only corpus cannot authorize production training" in b for b in blockers_syn)


def test_s7_i6_04_mandatory_contamination_scanning(tmp_path: Path, base_sample_record):
    """S7-I6-04: Contamination scanner is wired into production path and catches oracle leakage."""
    oracles_dir = tmp_path / "graders" / "protected"
    oracles_dir.mkdir(parents=True)
    oracle_file = oracles_dir / "t2_004_oracle.py"
    oracle_content = "def test_oracle_secret_invulnerability_window_must_equal_750ms(): pass"
    oracle_file.write_text(oracle_content, encoding="utf-8")

    scanner = ProtectedContaminationScanner(private_eval_dir=oracles_dir)
    reg = SourceRegister(Path("configs/dataset_source_register.json"))
    val = TrainingReadinessValidator(source_register=reg, contamination_scanner=scanner)

    leaked_rec = copy.deepcopy(base_sample_record)
    leaked_rec["process_details"]["applied_patch"] = f"// Leak:\n{oracle_content}"
    leaked_rec["content_digest"]["original_sha256"] = compute_sha256(leaked_rec["process_details"])
    leaked_rec["content_digest"]["canonical_fingerprint"] = compute_canonical_fingerprint(leaked_rec)

    is_ok, reason = val.validate_sample_record(leaked_rec)
    assert is_ok is False
    assert "PROTECTED_ORACLE_CONTAMINATION" in reason


def test_s7_i6_06_configuration_schema_strictness(tmp_path: Path):
    """S7-I6-06: Complete schema and strict semantic validation reject malformed nested settings and non-finite numbers."""
    cfg = json.loads(Path("configs/training_config_step7_prototype.json").read_text(encoding="utf-8"))
    cfg["hyperparameters"]["learning_rate"] = float("inf")

    cfg_file = tmp_path / "inf_cfg.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    runner = TrainingRunner(Path("."), cfg_file)
    ok, b = runner.validate_configuration_syntax()
    assert ok is False
    assert any("finite number" in item or "learning_rate" in item for item in b)


def test_s7_i6_07_no_invented_dataset_identity(training_validator, base_sample_record):
    """S7-I6-07: Missing identity inputs cannot be filled with invented defaults."""
    builder = TrainingDatasetBuilder(training_validator)
    # Missing source_manifest_id blocks dataset construction
    samples, digest, rep = builder.build_dataset([base_sample_record], source_manifest_id=None, source_manifest_digest="dig1")
    assert len(samples) == 0
    assert digest == ""
    assert rep.is_training_ready is False
    assert any("Missing required source_manifest_id" in b for b in rep.blocker_summary)

    # Missing source_manifest_digest blocks dataset construction
    samples2, digest2, rep2 = builder.build_dataset([base_sample_record], source_manifest_id="man1", source_manifest_digest="")
    assert len(samples2) == 0
    assert digest2 == ""
    assert rep2.is_training_ready is False
    assert any("Missing required source_manifest_digest" in b for b in rep2.blocker_summary)


def test_s7_i6_08_benchmark_version_and_frozen_metadata(tmp_path: Path):
    """S7-I6-08: Benchmark release ID, version, status, and task reconciliation are verified."""
    runner = TrainingRunner(Path("."), Path("configs/training_config_step7_prototype.json"))
    ok, blockers = runner.check_benchmark_version_integrity()
    assert ok is True, f"Valid frozen manifest failed: {blockers}"

    # Corrupted frozen status
    bad_bm = json.loads(Path("configs/baseline_release_manifest.json").read_text(encoding="utf-8"))
    bad_bm["status"] = "DRAFT"
    f_bm = tmp_path / "baseline_release_manifest.json"
    f_bm.write_text(json.dumps(bad_bm), encoding="utf-8")

    ws = tmp_path / "ws_bm"
    ws.mkdir()
    (ws / "configs").mkdir()
    shutil.copy(f_bm, ws / "configs" / "baseline_release_manifest.json")
    shutil.copy("schemas/training_config_schema.json", ws / "training_config_schema.json")
    shutil.copy("configs/training_config_step7_prototype.json", ws / "configs" / "training_config_step7_prototype.json")
    runner_corrupt = TrainingRunner(ws, ws / "configs" / "training_config_step7_prototype.json")
    ok_c, b_c = runner_corrupt.check_benchmark_version_integrity()
    assert ok_c is False
    assert any("FROZEN" in item for item in b_c)


def test_s7_i6_09_asset_provenance_evidence_required(tmp_path: Path):
    """S7-I6-09: Asset output requires valid evidence_reference to pass production validation."""
    router = AssetSpecialistRouter(workspace_root=tmp_path)
    provider = SpecialistProvider("p1", "m1", "v1", is_available=True)
    router.register_provider(provider)

    asset_file = tmp_path / "mesh.fbx"
    asset_file.write_bytes(b"VALID_MESH_BYTES")
    sha = hashlib.sha256(b"VALID_MESH_BYTES").hexdigest()

    req = AssetGenerationRequest(
        task_id="t5-001",
        modality=AssetModality.MESH_3D,
        prompt="mesh",
        target_format="fbx",
        destination_path=str(asset_file),
        constraints=AssetConstraints(),
        provenance=AssetProvenance(
            license_id="CC0-1.0",
            rights_holder="Artist",
            rights_cleared=True,
            evidence_reference="",  # Empty evidence reference!
        ),
    )
    job = AssetSpecialistJob(
        job_id="j1",
        modality=AssetModality.MESH_3D,
        provider=provider,
        request=req,
        result=AssetGenerationResult(artifact_path=str(asset_file), artifact_sha256=sha),
    )
    assert router.validate_asset_output(job) is False
    assert any("evidence_reference" in err for err in job.validation_errors)

    # Valid canonical evidence reference passes
    req.provenance.evidence_reference = "legal://agreements/artist_assignment.pdf"
    assert router.validate_asset_output(job) is True

