"""Automated unit test suite enforcing training gate validation and fail-closed security (Workstream C).

Verifies that training is strictly refused under all negative conditions:
- Source is REVIEW_REQUIRED
- Source is evaluation-only or test/CI-only
- Sample lacks required provenance
- Sample's training permission is missing
- Manifest metadata/hash is invalid
- Compute environment is incompatible
And demonstrates positive preflight using an explicitly identified synthetic fixture.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from scripts.models.train_gameforge_v2_qlora import (
    audit_hardware_and_environment,
    validate_dataset_provenance,
    run_training_pipeline,
)


@pytest.fixture
def mock_reg_and_manifest():
    """Scaffolds temporary registers and manifests for isolated testing."""
    tmp = Path(tempfile.mkdtemp(prefix="gameforge_train_gate_test_"))
    
    reg_path = tmp / "dataset_source_register.json"
    reg_data = {
        "register_version": "v1.1.0",
        "registered_sources": [
            {
                "source_id": "src-unapproved-review",
                "review_status": "REVIEW_REQUIRED",
                "permitted_uses": {"training": False, "evaluation": True},
                "intended_uses": ["EVALUATION"],
            },
            {
                "source_id": "gameforge-synthetic-test-corpus",
                "review_status": "CONFIRMED_FOR_TRAINING",
                "permitted_uses": {"training": True, "evaluation": True},
                "intended_uses": ["TRAINING_TEST"],
            },
            {
                "source_id": "gameforge-private-heldout-eval",
                "review_status": "RESTRICTED_EVAL_ONLY",
                "permitted_uses": {"training": False, "evaluation": True},
                "intended_uses": ["PRIVATE_EVALUATION"],
            },
            {
                "source_id": "hypothetical-authorized-fixture",
                "review_status": "CONFIRMED_FOR_TRAINING",
                "permitted_uses": {"training": True, "evaluation": True},
                "intended_uses": ["TRAINING"],
            },
        ],
    }
    reg_path.write_text(json.dumps(reg_data, indent=2), encoding="utf-8")

    yield tmp, reg_path
    shutil.rmtree(tmp, ignore_errors=True)


def test_refusal_when_source_review_required(mock_reg_and_manifest):
    tmp, reg_path = mock_reg_and_manifest
    manifest_path = tmp / "manifest_review.json"
    manifest_data = {
        "manifest_id": "test-review",
        "stats": {"manifest_sha256": "fake_sha_123"},
        "samples": [
            {
                "sample_id": "s-01",
                "source_id": "src-unapproved-review",
                "split": "train",
                "conversations": [{"role": "user", "content": "hi"}],
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    
    is_valid, blockers, stats = validate_dataset_provenance(manifest_path, reg_path)
    assert is_valid is False
    assert any("not confirmed for training" in b for b in blockers)
    assert stats["unauthorized_train_samples"] == 1


def test_refusal_when_source_test_ci_only(mock_reg_and_manifest):
    tmp, reg_path = mock_reg_and_manifest
    manifest_path = tmp / "manifest_test_ci.json"
    manifest_data = {
        "manifest_id": "test-ci-corpus",
        "stats": {"manifest_sha256": "fake_sha_123"},
        "samples": [
            {
                "sample_id": "s-ci-01",
                "source_id": "gameforge-synthetic-test-corpus",
                "split": "train",
                "conversations": [{"role": "user", "content": "hi"}],
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    
    is_valid, blockers, stats = validate_dataset_provenance(manifest_path, reg_path)
    assert is_valid is False
    assert any("Test/CI fixture" in b for b in blockers)
    assert stats["test_fixture_violations"] == 1


def test_refusal_when_source_eval_only(mock_reg_and_manifest):
    tmp, reg_path = mock_reg_and_manifest
    manifest_path = tmp / "manifest_eval.json"
    manifest_data = {
        "manifest_id": "test-eval-heldout",
        "stats": {"manifest_sha256": "fake_sha_123"},
        "samples": [
            {
                "sample_id": "s-eval-01",
                "source_id": "gameforge-private-heldout-eval",
                "split": "train",
                "conversations": [{"role": "user", "content": "hi"}],
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    
    is_valid, blockers, stats = validate_dataset_provenance(manifest_path, reg_path)
    assert is_valid is False
    assert any("Private held-out eval" in b for b in blockers)
    assert stats["private_eval_violations"] == 1


def test_refusal_when_sample_lacks_provenance(mock_reg_and_manifest):
    tmp, reg_path = mock_reg_and_manifest
    manifest_path = tmp / "manifest_missing_src.json"
    manifest_data = {
        "manifest_id": "test-missing-src",
        "stats": {"manifest_sha256": "fake_sha_123"},
        "samples": [
            {
                "sample_id": "s-no-source",
                "source_id": "unregistered-unknown-source-999",
                "split": "train",
                "conversations": [{"role": "user", "content": "hi"}],
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    
    is_valid, blockers, stats = validate_dataset_provenance(manifest_path, reg_path)
    assert is_valid is False
    assert any("unregistered or missing source_id" in b for b in blockers)


def test_refusal_when_manifest_metadata_invalid(mock_reg_and_manifest):
    tmp, reg_path = mock_reg_and_manifest
    manifest_path = tmp / "manifest_bad_meta.json"
    manifest_data = {
        "manifest_id": "test-no-hash",
        "stats": {},  # Missing manifest_sha256
        "samples": [],  # Zero samples
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    
    is_valid, blockers, stats = validate_dataset_provenance(manifest_path, reg_path)
    assert is_valid is False
    assert any("zero samples" in b for b in blockers)


def test_refusal_when_hardware_incompatible(monkeypatch):
    """Verifies that missing CUDA or insufficient VRAM triggers explicit blockers."""
    # Test environment report
    audit = audit_hardware_and_environment()
    # In current CPU environment, cuda_available should be False or hardware_adequate False
    assert audit["hardware_adequate_for_27b_qlora"] is False
    assert len(audit["blockers"]) > 0


def test_positive_preflight_synthetic_fixture(mock_reg_and_manifest):
    """Demonstrates that gate cleanly accepts a valid hypothetical test fixture without starting training."""
    tmp, reg_path = mock_reg_and_manifest
    manifest_path = tmp / "manifest_positive_fixture.json"
    manifest_data = {
        "manifest_id": "test-positive-fixture",
        "stats": {
            "manifest_sha256": "synthetic_positive_sha256_mock_hash",
            "total_samples": 2,
            "train_samples": 1,
            "dev_samples": 1,
        },
        "samples": [
            {
                "sample_id": "syn-train-01",
                "source_id": "hypothetical-authorized-fixture",
                "split": "train",
                "conversations": [{"role": "user", "content": "Implement clamp."}],
            },
            {
                "sample_id": "syn-dev-01",
                "source_id": "hypothetical-authorized-fixture",
                "split": "dev",
                "conversations": [{"role": "user", "content": "Explain clamp."}],
            },
        ],
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    
    is_valid, blockers, stats = validate_dataset_provenance(manifest_path, reg_path)
    assert is_valid is True
    assert len(blockers) == 0
    assert stats["train_samples"] == 1
    assert stats["dev_samples"] == 1
    assert stats["unauthorized_train_samples"] == 0

    # Also verify that training runner fails closed if running in full mode under local hardware
    cfg_path = tmp / "train_config.json"
    cfg_data = {
        "dataset": {
            "manifest_path": str(manifest_path),
            "source_register_path": str(reg_path),
        },
        "base_model": {
            "local_path": "E:/GameForge/models/hf/Qwen3.8-27B",
        },
    }
    cfg_path.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")

    # In --preflight-only mode, it must exit 0 and report staging status
    code_preflight = run_training_pipeline(cfg_path, preflight_only=True)
    assert code_preflight == 0

    # In real training mode, it MUST exit with code 2 because local hardware has CPU PyTorch / 12GB VRAM
    code_train = run_training_pipeline(cfg_path, preflight_only=False)
    assert code_train == 2
