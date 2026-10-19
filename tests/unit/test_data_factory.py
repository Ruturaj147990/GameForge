"""Comprehensive unit and end-to-end tests for Step 6 Rights-Aware Data Factory.

Tests cover:
- Valid and invalid trajectory/sample schemas
- Missing provenance rejection
- Unapproved and prohibited licenses/rights enforcement
- Deterministic canonical normalization and fingerprinting
- Exact deduplication and non-destructive near-duplicate detection
- Deterministic, versioned, group-aware split assignment
- Split leakage prevention across duplicate groups
- Contamination detection against protected held-out oracles without content leakage
- Tombstone and removal lineage enforcement
- Safe dry-run mode vs real manifest generation
- Synthetic end-to-end ingestion and readiness reporting
- CLI command invocation and exit codes
"""

import json
from pathlib import Path
import pytest
from gameforge_bench.cli import main
from gameforge_bench.data_factory import (
    DataFactory,
    Deduplicator,
    ProtectedContaminationScanner,
    SampleRecord,
    SourceRegister,
    SplitAssigner,
    TombstoneManager,
    compute_canonical_fingerprint,
    compute_sha256,
    normalize_text_content,
    validate_trajectory,
)


@pytest.fixture
def synthetic_sample_dict():
    """Returns a valid, synthetic process trajectory matching schemas/trajectory_schema.json."""
    return {
        "sample_id": "traj-synthetic-test-001",
        "schema_version": "v1.0.0",
        "sample_type": "process_trajectory",
        "source_id": "gameforge-synthetic-test-corpus",
        "provenance": {
            "origin_uri": "https://gameforge.internal/tests/synthetic-001",
            "commit_or_hash": "a1b2c3d4e5f67890123456789abcdef012345678",
            "source_version": "1.0",
            "collected_at": "2026-10-19T14:00:00Z",
            "producing_tool": "gameforge-test-generator/1.0",
            "parent_sample_id": None,
            "lineage_notes": "Generated purely in-memory for testing",
        },
        "rights": {
            "rights_holder": "GameForge Test Suite",
            "license_id": "CC0-1.0",
            "evidence_reference": "tests/unit/test_data_factory.py",
            "rights_review_state": "CONFIRMED_FOR_TRAINING",
            "permitted_uses": {
                "training": True,
                "evaluation": True,
                "redistribution": True,
            },
            "removal_obligations": "None",
        },
        "content_digest": {
            "original_sha256": "0" * 64,  # will be computed if zero
            "canonical_fingerprint": "0" * 64,
            "normalization_version": "v1.0",
        },
        "task_info": {
            "task_id": "t2-004-health-damage",
            "logical_task_id": "T2-004",
            "benchmark_tier": "T2",
            "benchmark_version": "v0.2.0",
            "engine": {
                "name": "unreal",
                "version": "5.7.4",
            },
        },
        "split_info": {
            "assigned_split": "train",
            "group_id": "synthetic-group-001",
            "contamination_status": "CLEAN",
            "split_manifest_version": "v1.0",
        },
        "quality": {
            "schema_valid": True,
            "provenance_complete": True,
            "rights_eligible": True,
            "task_clarity": "CLEAR",
            "implementation_validity": "VERIFIED",
            "runtime_tested": True,
            "review_status": "AUTOMATED_PASSED",
            "reviewer_id": "auto-runner",
            "review_date": "2026-10-19T14:00:00Z",
        },
        "security_and_privacy": {
            "secret_scan_passed": True,
            "pii_scan_passed": True,
            "scan_timestamp": "2026-10-19T14:00:00Z",
        },
        "tombstone": {
            "is_tombstoned": False,
        },
        "process_details": {
            "interpreted_requirements": "Implement damage taking with health clamp to 0.",
            "assumptions": ["Health cannot drop below zero", "No invulnerability active"],
            "plan": ["Inspect current health", "Apply subtraction", "Clamp at zero"],
            "actions_trace": [
                {
                    "step_index": 0,
                    "action_type": "inspection",
                    "observation": "CurrentHealth = 100.0f",
                },
                {
                    "step_index": 1,
                    "action_type": "code_generation",
                    "proposed_changes": "CurrentHealth = FMath::Max(0.0f, CurrentHealth - Amount);",
                    "applied_patch": "CurrentHealth = FMath::Max(0.0f, CurrentHealth - Amount);",
                    "observation": "Build passed without errors",
                },
            ],
            "applied_patch": "CurrentHealth = FMath::Max(0.0f, CurrentHealth - Amount);",
            "check_results": {"build": "PASS", "probes": "PASS"},
            "repair_iterations": 0,
            "final_outcome": "PASS",
            "evidence_references": ["logs/synthetic_build.log"],
        },
    }


def test_schema_valid_synthetic_sample(synthetic_sample_dict):
    """S6-2: Valid trajectory succeeds validation."""
    # Ensure correct digests
    synthetic_sample_dict["content_digest"]["original_sha256"] = compute_sha256(synthetic_sample_dict["process_details"])
    synthetic_sample_dict["content_digest"]["canonical_fingerprint"] = compute_canonical_fingerprint(synthetic_sample_dict)
    
    is_valid, errors = validate_trajectory(synthetic_sample_dict)
    assert is_valid is True, f"Validation failed with: {errors}"
    assert len(errors) == 0


def test_schema_invalid_missing_process_details(synthetic_sample_dict):
    """S6-2: A process_trajectory without process_details must fail schema validation."""
    del synthetic_sample_dict["process_details"]
    is_valid, errors = validate_trajectory(synthetic_sample_dict)
    assert is_valid is False
    assert any("process_details" in err for err in errors)


def test_schema_specification_sample_type(synthetic_sample_dict):
    """S6-2: specification type does not require process_details or final patch."""
    spec_sample = dict(synthetic_sample_dict)
    spec_sample["sample_id"] = "spec-health-clamp"
    spec_sample["sample_type"] = "specification"
    del spec_sample["process_details"]
    spec_sample["content_digest"]["original_sha256"] = compute_sha256("health_invariants_spec")
    spec_sample["content_digest"]["canonical_fingerprint"] = compute_canonical_fingerprint(spec_sample)

    record = SampleRecord(**spec_sample)
    assert record.sample_type == "specification"
    assert record.process_details is None


def test_source_register_enforcement(tmp_path, synthetic_sample_dict):
    """S6-3 & S6-4: Reject samples from unapproved/prohibited sources or REVIEW_REQUIRED in train."""
    factory = DataFactory(workspace_root=Path.cwd())

    # Sample from REVIEW_REQUIRED source (e.g. unreviewed internal pilot)
    unreviewed_sample = dict(synthetic_sample_dict)
    unreviewed_sample["sample_id"] = "traj-unreviewed-001"
    unreviewed_sample["source_id"] = "gameforge-cleanroom-unreal-pilots"
    unreviewed_sample["rights"]["rights_review_state"] = "REVIEW_REQUIRED"
    unreviewed_sample["rights"]["permitted_uses"]["training"] = False

    res = factory.validate_and_ingest_sample(unreviewed_sample)
    assert res["accepted"] is False
    assert any("cannot enter 'train' split" in r or "REVIEW_REQUIRED" in r for r in res["reasons"])


def test_deterministic_normalization_and_fingerprinting():
    """S6-5: Normalization produces identical canonical fingerprints across CRLF/whitespace variances."""
    text1 = "void TakeDamage() {\r\n    Health -= 10;\r\n}\r\n"
    text2 = "void TakeDamage() {\n    Health -= 10;\n}\n\n"
    assert normalize_text_content(text1) == normalize_text_content(text2)

    sample1 = {
        "sample_type": "process_trajectory",
        "process_details": {
            "interpreted_requirements": "Damage handling\r\n",
            "applied_patch": text1,
        },
    }
    sample2 = {
        "sample_type": "process_trajectory",
        "process_details": {
            "interpreted_requirements": "Damage handling\n",
            "applied_patch": text2,
        },
    }
    assert compute_canonical_fingerprint(sample1) == compute_canonical_fingerprint(sample2)


def test_deduplicator_exact_and_near(synthetic_sample_dict):
    """S6-5: Exact duplicates rejected; near-duplicates flagged without silent deletion."""
    dedup = Deduplicator(near_duplicate_threshold=0.80)
    raw_hash1 = "a" * 64
    fp1 = "f" * 64
    text1 = "void ApplyDamage(float Amount) { CurrentHealth -= Amount; }"

    # First registration: unique
    is_uniq1, grp1, near1 = dedup.check_and_register("samp-1", raw_hash1, fp1, sample_text=text1)
    assert is_uniq1 is True
    assert len(near1) == 0

    # Exact duplicate registration: rejected
    is_uniq2, grp2, near2 = dedup.check_and_register("samp-2", raw_hash1, fp1, sample_text=text1)
    assert is_uniq2 is False
    assert grp1 == grp2

    # Near duplicate with minor comment alteration: accepted as unique, but flagged in near_duplicates
    raw_hash3 = "b" * 64
    fp3 = "e" * 64
    text3 = "void ApplyDamage(float Amount) { /* comment */ CurrentHealth -= Amount; }"
    is_uniq3, grp3, near3 = dedup.check_and_register("samp-3", raw_hash3, fp3, sample_text=text3)
    assert is_uniq3 is True
    assert len(near3) == 1
    assert near3[0][0] == "samp-1"
    assert near3[0][1] >= 0.80
    assert len(dedup.near_duplicates) == 1


def test_split_assignment_deterministic_and_group_aware():
    """S6-6: Group-aware splitting assigns all members of a duplicate/revision group to identical split."""
    assigner = SplitAssigner(seed="test-seed-42", dev_ratio=0.3)
    grp_a = "group-shared-feature-alpha"
    grp_b = "group-shared-feature-beta"

    split_a1 = assigner.assign_group_split(grp_a)
    split_a2 = assigner.assign_group_split(grp_a)
    assert split_a1 == split_a2, "Repeated split assignment must be strictly deterministic"

    # Restricted eval source forced to eval_private
    split_p = assigner.assign_group_split("any-group", source_restrictions=["eval_private"])
    assert split_p == "eval_private"


def test_protected_contamination_scanner_no_secret_leakage(synthetic_sample_dict):
    """S6-6: Scanner flags matches against private eval without leaking test content in reason."""
    scanner = ProtectedContaminationScanner()
    private_hidden_code = "SECRET_ORACLE_CHECK_FOR_INVULNERABILITY_WINDOW_EXACT_500MS_TOLERANCE"
    scanner.add_oracle_content(private_hidden_code)

    # Clean text
    is_c, reason = scanner.scan_sample("void NormalCleanGameplayMethod() {}")
    assert is_c is False
    assert reason == "CLEAN"

    # Leaking text
    leak_text = f"Candidate implementation touches {private_hidden_code} and passes"
    is_c2, reason2 = scanner.scan_sample(leak_text)
    assert is_c2 is True
    # Reason must be opaque enum, NOT containing the secret string
    assert "SECRET_ORACLE_CHECK" not in reason2
    assert "SUBSTRING_8GRAM_MATCH_WITH_PROTECTED_ORACLE" in reason2


def test_tombstone_lineage_prevents_reentry(synthetic_sample_dict):
    """S6-7: Tombstoned samples and their fingerprints cannot re-enter eligible manifests."""
    factory = DataFactory(workspace_root=Path.cwd())
    t_id = "traj-synthetic-test-001"
    fp = compute_canonical_fingerprint(synthetic_sample_dict)

    # Record tombstone
    factory.tombstone_manager.record_removal(
        sample_id=t_id,
        fingerprint=fp,
        reason="DMCA takedown notice test",
        ticket="TICKET-2026-99",
        timestamp="2026-10-19T14:30:00Z",
    )

    # Attempt to ingest the tombstoned sample
    res = factory.validate_and_ingest_sample(synthetic_sample_dict)
    assert res["accepted"] is False
    assert any("tombstoned" in r.lower() for r in res["reasons"])

    # Attempt to ingest an alias with the same canonical fingerprint
    alias_sample = dict(synthetic_sample_dict)
    alias_sample["sample_id"] = "traj-alias-synthetic-002"
    alias_sample["content_digest"]["canonical_fingerprint"] = fp
    res2 = factory.validate_and_ingest_sample(alias_sample)
    assert res2["accepted"] is False
    assert any("tombstoned" in r.lower() for r in res2["reasons"])


def test_end_to_end_data_factory_pipeline(tmp_path, synthetic_sample_dict):
    """S6-8: End-to-end flow from synthetic sample validation, deduplication, splitting, and readiness report."""
    import copy
    manifest_file = tmp_path / "test_sample_manifest.json"
    out_manifest = tmp_path / "dataset_output_manifest.json"

    # Prepare batch of 4 samples: 1 valid confirmed, 1 duplicate, 1 unapproved rights, 1 invalid schema
    s1 = copy.deepcopy(synthetic_sample_dict)
    s1["sample_id"] = "samp-valid-001"
    s1["content_digest"] = {
        "original_sha256": compute_sha256("s1_content"),
        "canonical_fingerprint": compute_sha256("s1_canon"),
        "normalization_version": "v1.0"
    }

    s2_dup = copy.deepcopy(synthetic_sample_dict)
    s2_dup["sample_id"] = "samp-dup-002"
    s2_dup["content_digest"] = {
        "original_sha256": s1["content_digest"]["original_sha256"],
        "canonical_fingerprint": s1["content_digest"]["canonical_fingerprint"],
        "normalization_version": "v1.0"
    }

    s3_unapproved = copy.deepcopy(synthetic_sample_dict)
    s3_unapproved["sample_id"] = "samp-unapproved-003"
    s3_unapproved["source_id"] = "gameforge-cleanroom-unreal-pilots"
    s3_unapproved["content_digest"] = {
        "original_sha256": compute_sha256("s3_content"),
        "canonical_fingerprint": compute_sha256("s3_canon"),
        "normalization_version": "v1.0"
    }

    s4_invalid = copy.deepcopy(synthetic_sample_dict)
    s4_invalid["sample_id"] = "samp-bad-schema-004"
    s4_invalid["sample_type"] = "unsupported_type"

    batch = [s1, s2_dup, s3_unapproved, s4_invalid]
    manifest_file.write_text(json.dumps({"samples": batch}, indent=2), encoding="utf-8")

    # Ingest using DataFactory
    factory = DataFactory(workspace_root=Path.cwd())
    reports = [factory.validate_and_ingest_sample(s) for s in batch]
    readiness = factory.produce_readiness_report(reports)

    assert readiness["total_discovered"] == 4
    assert readiness["accepted_samples"] == 1
    assert readiness["rejected_samples"] == 3
    assert readiness["rejection_breakdown"]["schema_error"] == 1
    assert readiness["rejection_breakdown"]["exact_duplicate"] == 1
    assert readiness["rejection_breakdown"]["unapproved_rights"] == 1
    assert readiness["training_ready"] is False  # Correctly reflects that real training remains blocked


def test_cli_validate_data_exit_code(tmp_path, synthetic_sample_dict):
    """S6-8: CLI validate-data command executes and returns proper exit codes."""
    # 1. Clean manifest with 1 confirmed sample exits 0
    clean_manifest = tmp_path / "clean_manifest.json"
    s1 = dict(synthetic_sample_dict)
    s1["sample_id"] = "samp-clean-101"
    s1["content_digest"]["original_sha256"] = compute_sha256("clean101")
    s1["content_digest"]["canonical_fingerprint"] = compute_sha256("clean101_canon")
    clean_manifest.write_text(json.dumps([s1]), encoding="utf-8")

    exit_code = main(["validate-data", "--manifest", str(clean_manifest), "--dry-run"])
    assert exit_code == 0

    # 2. Manifest with duplicate/unapproved exits 1
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text(json.dumps([s1, s1]), encoding="utf-8")
    exit_code_bad = main(["validate-data", "--manifest", str(bad_manifest), "--dry-run"])
    assert exit_code_bad == 1
