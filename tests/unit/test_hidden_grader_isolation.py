"""Unit tests for Hidden-Grader Isolation and Anti-Tampering Defenses (Deliverable D & G)."""

import json
from pathlib import Path
import pytest

from gameforge_bench.policy import (
    check_candidate_policy,
    compute_file_hash,
    compute_snapshot_hash,
    freeze_candidate_snapshot,
    is_path_safe_relative,
    snapshot_directory_hashes,
    verify_snapshot_integrity,
)


def test_deterministic_snapshot_hashing(tmp_path):
    """Verifies that snapshot hashing is deterministic and SHA-256 backed."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "Source").mkdir()
    (proj / "Source" / "HealthComponent.cpp").write_text("class HealthComponent {};", encoding="utf-8")
    (proj / "Config").mkdir()
    (proj / "Config" / "DefaultGame.ini").write_text("[Game]", encoding="utf-8")

    hash1 = compute_snapshot_hash(proj)
    hash2 = compute_snapshot_hash(proj)
    assert hash1.startswith("sha256:")
    assert hash1 == hash2, "Snapshot hashes must be strictly deterministic across calls"


def test_freeze_and_integrity_verification(tmp_path):
    """Verifies candidate freezing and tamper detection."""
    candidate_src = tmp_path / "candidate"
    candidate_src.mkdir()
    (candidate_src / "file1.txt").write_text("hello", encoding="utf-8")

    frozen_dir = tmp_path / "frozen_snapshot"
    snapshot_id, inventory = freeze_candidate_snapshot(candidate_src, frozen_dir)

    assert "file1.txt" in inventory
    assert verify_snapshot_integrity(frozen_dir, snapshot_id) is True

    # Tampering: modify a file inside frozen snapshot
    (frozen_dir / "file1.txt").write_text("hacked content", encoding="utf-8")
    assert verify_snapshot_integrity(frozen_dir, snapshot_id) is False, "Modified snapshot must fail integrity check"


def test_unauthorized_edit_outside_allowlist(tmp_path):
    """Candidate modifying files outside allowed_edit_paths is rejected."""
    workspace = tmp_path / "workspace"
    candidate = workspace / "candidate"
    candidate.mkdir(parents=True)
    (candidate / "Source").mkdir()
    (candidate / "Source" / "HealthComponent.cpp").write_text("code", encoding="utf-8")
    (candidate / "UnauthorizedTool.exe").write_text("binary", encoding="utf-8")

    baseline = {
        "Source/HealthComponent.cpp": compute_file_hash(candidate / "Source" / "HealthComponent.cpp"),
    }

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate,
        allowed_edit_paths=["project gameplay source paths"],
        forbidden_paths=["tests", "graders"],
        baseline_hashes=baseline,
    )

    assert res.passed is False
    assert any("allowlist violation" in v.lower() for v in res.violations)


def test_candidate_attempting_to_modify_acceptance_criteria_rejected(tmp_path):
    """Candidate modifying acceptance criteria or protected directories is detected as tampering."""
    workspace = tmp_path / "workspace"
    candidate = workspace / "candidate"
    candidate.mkdir(parents=True)
    hacked_config = candidate / "configs" / "acceptance_criteria"
    hacked_config.mkdir(parents=True)
    (hacked_config / "t2_004_health_damage.json").write_text("{}", encoding="utf-8")

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate,
        allowed_edit_paths=["project gameplay source paths"],
        forbidden_paths=["tests", "graders", "configs/acceptance_criteria"],
    )

    assert res.passed is False
    assert any("tampering" in v.lower() or "protected" in v.lower() for v in res.violations)


def test_candidate_attempting_to_touch_graders_rejected(tmp_path):
    """Candidate modifying or creating files under graders/ is rejected."""
    workspace = tmp_path / "workspace"
    candidate = workspace / "candidate"
    candidate.mkdir(parents=True)
    hacked_grader = candidate / "graders" / "protected"
    hacked_grader.mkdir(parents=True)
    (hacked_grader / "test_health_damage_hidden.py").write_text("# fake grader", encoding="utf-8")

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate,
        allowed_edit_paths=["project gameplay source paths"],
        forbidden_paths=["tests", "graders"],
    )

    assert res.passed is False
    assert any("tampering" in v.lower() or "forbidden" in v.lower() for v in res.violations)


def test_fake_report_in_candidate_rejected(tmp_path):
    """Candidate providing pre-generated fake benchmark/test reports is rejected."""
    workspace = tmp_path / "workspace"
    candidate = workspace / "candidate"
    candidate.mkdir(parents=True)
    (candidate / "benchmark_report.json").write_text('{"status": "PASS"}', encoding="utf-8")

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate,
        allowed_edit_paths=["project gameplay source paths"],
        forbidden_paths=["tests", "graders"],
    )

    assert res.passed is False
    assert any("fake report" in v.lower() for v in res.violations)


def test_hidden_test_leak_detected(tmp_path):
    """Candidate having hidden tests in candidate working directory is flagged."""
    workspace = tmp_path / "workspace"
    candidate = workspace / "candidate"
    candidate.mkdir(parents=True)
    (candidate / "test_health_damage_hidden.py").write_text("import os", encoding="utf-8")

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate,
        allowed_edit_paths=["project gameplay source paths"],
        forbidden_paths=["tests", "graders"],
    )

    assert res.passed is False
    assert any("hidden test" in v.lower() for v in res.violations)


def test_path_traversal_protection(tmp_path):
    """Path traversal attempts are safely rejected."""
    base = tmp_path / "safe_dir"
    base.mkdir()

    is_safe, resolved = is_path_safe_relative(base, "legit/file.txt")
    assert is_safe is True

    is_safe, resolved = is_path_safe_relative(base, "../../etc/passwd")
    assert is_safe is False

    is_safe, resolved = is_path_safe_relative(base, "../other_dir")
    assert is_safe is False
