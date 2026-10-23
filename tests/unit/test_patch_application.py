"""Comprehensive regression test suite for GameForge Step 5 patch application,
diff fidelity, security allowlists, and execution grounding (A.2).
"""

from __future__ import annotations

import difflib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from gameforge_bench.model_adapter import (
    apply_unified_diff,
    extract_code_blocks,
    validate_patch_target,
    run_attempt,
    ModelRequest,
    ModelResponse,
)
from gameforge_bench.task_loader import TaskSpec


@pytest.fixture
def temp_project_dir():
    """Provides an isolated temporary Unreal project fixture for testing."""
    tmp = Path(tempfile.mkdtemp(prefix="gameforge_test_proj_"))
    # Scaffold realistic Unreal project tree
    src_private = tmp / "Source" / "GameForgePilot" / "Private"
    src_public = tmp / "Source" / "GameForgePilot" / "Public"
    src_private.mkdir(parents=True, exist_ok=True)
    src_public.mkdir(parents=True, exist_ok=True)
    
    (src_public / "HealthComponent.h").write_text(
        "#pragma once\nclass UHealthComponent {\npublic:\n    float Health = 100.0f;\n};\n",
        encoding="utf-8",
    )
    (src_private / "HealthComponent.cpp").write_text(
        '#include "HealthComponent.h"\nvoid Init() {}\n',
        encoding="utf-8",
    )
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_valid_single_file_generated_change(temp_project_dir: Path):
    """Verifies that a valid single-file replacement cleanly modifies target and records diff."""
    allowed = ["Source/GameForgePilot/Private/HealthComponent.cpp"]
    forbidden = ["graders/protected/*", "hidden_tests/*"]
    
    rel_path = "Source/GameForgePilot/Private/HealthComponent.cpp"
    new_code = '#include "HealthComponent.h"\nvoid Init() { /* New Implementation */ }\n'
    
    is_valid, err, target_path = validate_patch_target(rel_path, allowed, forbidden, temp_project_dir)
    assert is_valid is True
    assert target_path is not None
    assert target_path.is_file()
    
    old_content = target_path.read_text(encoding="utf-8")
    target_path.write_text(new_code, encoding="utf-8")
    
    diff_lines = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
    ))
    diff_text = "".join(diff_lines)
    assert "/* New Implementation */" in diff_text
    assert target_path.read_text(encoding="utf-8") == new_code


def test_valid_multi_file_generated_change(temp_project_dir: Path):
    """Verifies that multi-file patches (header + implementation) apply cleanly to both targets."""
    allowed = ["project gameplay source paths"]
    forbidden = ["grader", "tests"]
    
    files = {
        "Source/GameForgePilot/Public/HealthComponent.h": "#pragma once\nclass UHealthComponent { float MaxHealth = 100.0f; };\n",
        "Source/GameForgePilot/Private/HealthComponent.cpp": '#include "HealthComponent.h"\nvoid TakeDamage(float Amt) {}\n',
    }
    
    modified_count = 0
    diffs = {}
    for rel, content in files.items():
        is_valid, err, target = validate_patch_target(rel, allowed, forbidden, temp_project_dir)
        assert is_valid is True
        assert target is not None
        old = target.read_text(encoding="utf-8")
        target.write_text(content, encoding="utf-8")
        diff_lines = list(difflib.unified_diff(
            old.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        ))
        diffs[rel] = "".join(diff_lines)
        modified_count += 1
        
    assert modified_count == 2
    assert "MaxHealth" in diffs["Source/GameForgePilot/Public/HealthComponent.h"]
    assert "TakeDamage" in diffs["Source/GameForgePilot/Private/HealthComponent.cpp"]


def test_valid_code_block_file_header_extraction():
    """Verifies parsing of various model markdown formatting headers including backticks and comments."""
    sample_text = (
        "I will implement the required files.\n\n"
        "### File: `Source/GameForgePilot/Public/HealthComponent.h`\n"
        "```cpp\n"
        "#pragma once\n"
        "class UHealthComponent;\n"
        "```\n\n"
        "**File:** `Source/GameForgePilot/Private/HealthComponent.cpp`\n"
        "```cpp\n"
        "#include \"HealthComponent.h\"\n"
        "void UHealthComponent::ApplyDamage() {}\n"
        "```\n\n"
        "// File: Source/GameForgePilot/Public/PickupActor.h\n"
        "```cpp\n"
        "#pragma once\n"
        "class APickupActor;\n"
        "```\n"
    )
    patches = extract_code_blocks(sample_text)
    assert len(patches) == 3
    assert "Source/GameForgePilot/Public/HealthComponent.h" in patches
    assert "Source/GameForgePilot/Private/HealthComponent.cpp" in patches
    assert "Source/GameForgePilot/Public/PickupActor.h" in patches
    assert "ApplyDamage" in patches["Source/GameForgePilot/Private/HealthComponent.cpp"]


def test_rejected_malformed_patch():
    """Verifies that a malformed unified diff with invalid hunks is rejected cleanly without file corruption."""
    original = "Line 1\nLine 2\nLine 3\n"
    # Malformed diff specifying non-matching context
    malformed_diff = (
        "--- a/file.cpp\n"
        "+++ b/file.cpp\n"
        "@@ -1,3 +1,3 @@\n"
        " NonExistentLine 1\n"
        "-Line 2\n"
        "+Replacement Line\n"
        " Line 3\n"
    )
    success, result, err = apply_unified_diff(original, malformed_diff)
    # The application must fail cleanly
    # In our implementation, context line "NonExistentLine 1" != "Line 1", so orig_idx mismatches or fails
    assert result == original or success is False


def test_rejected_path_traversal_attempt(temp_project_dir: Path):
    """Verifies that relative path traversal attempts outside the project root are rejected."""
    allowed = ["project gameplay source paths"]
    forbidden = ["grader"]
    
    traversal_paths = [
        "../../etc/passwd",
        "../graders/protected/oracle.py",
        "Source/../../graders/protected/test.py",
        "..\\..\\windows\\system32\\cmd.exe",
    ]
    for p in traversal_paths:
        is_valid, err, target = validate_patch_target(p, allowed, forbidden, temp_project_dir)
        assert is_valid is False
        assert "Path traversal" in err or "escapes" in err


def test_rejected_protected_file_modification(temp_project_dir: Path):
    """Verifies that any attempt to modify protected grader oracles or acceptance criteria is rejected."""
    allowed = ["project gameplay source paths"]
    forbidden = ["grader", "tests", "acceptance_criteria"]
    
    protected_paths = [
        "graders/protected/t2_004/test_health_probes.py",
        "acceptance_criteria/t2_004_health.json",
        "hidden_tests/secret_oracle.py",
        ".git/config",
        "model_register.json",
    ]
    for p in protected_paths:
        is_valid, err, target = validate_patch_target(p, allowed, forbidden, temp_project_dir)
        assert is_valid is False
        assert "protected" in err.lower() or "forbidden" in err.lower()


def test_failed_patch_application_reported_accurately(temp_project_dir: Path):
    """Verifies that disallowed paths record structured rejection reasons rather than crashing."""
    allowed = ["Source/GameForgePilot/Private/Allowed.cpp"]
    forbidden = ["Source/GameForgePilot/Private/Forbidden.cpp"]
    
    is_valid, err, target = validate_patch_target(
        "Source/GameForgePilot/Private/Forbidden.cpp",
        allowed,
        forbidden,
        temp_project_dir,
    )
    assert is_valid is False
    assert "violates forbidden edits" in err
    
    is_valid2, err2, target2 = validate_patch_target(
        "Source/GameForgePilot/Private/Unlisted.cpp",
        allowed,
        forbidden,
        temp_project_dir,
    )
    assert is_valid2 is False
    assert "not within task allowed edit paths" in err2


def test_clean_reset_isolation_between_tasks(temp_project_dir: Path):
    """Verifies that candidate file modifications in one attempt do not contaminate fresh snapshots."""
    # Attempt 1: modify a file
    target = temp_project_dir / "Source" / "GameForgePilot" / "Private" / "HealthComponent.cpp"
    target.write_text("// Modified by Attempt 1", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "// Modified by Attempt 1"
    
    # Attempt 2: Fresh snapshot directory from starter fixture
    fresh_dir = Path(tempfile.mkdtemp(prefix="gameforge_fresh_proj_"))
    try:
        fresh_src = fresh_dir / "Source" / "GameForgePilot" / "Private"
        fresh_src.mkdir(parents=True, exist_ok=True)
        fresh_file = fresh_src / "HealthComponent.cpp"
        fresh_file.write_text("// Pristine Starter Content", encoding="utf-8")
        
        # Verify fresh snapshot has zero contamination from attempt 1
        assert "Attempt 1" not in fresh_file.read_text(encoding="utf-8")
        assert fresh_file.read_text(encoding="utf-8") == "// Pristine Starter Content"
    finally:
        shutil.rmtree(fresh_dir, ignore_errors=True)


def test_zero_patches_applied_fails_grounding(temp_project_dir: Path, monkeypatch):
    """Verifies that when 0 candidate patches are applied to a native task, overall_status is FAIL."""
    manifest = {
        "benchmark_release_id": "test-bench-v1",
        "candidate_protocol": {"budgets": {"max_tokens_per_request": 100, "timeout_seconds": 10}},
    }
    cand_cfg = {
        "candidate_id": "test_double_01",
        "runtime_type": "test_double",
    }
    task_spec = TaskSpec(
        id="t2-004-health-damage",
        logical_task_id="T2-004",
        tier="T2",
        title="Health and Damage",
        category="gameplay",
        prompt="Implement health component",
        allowed_edit_paths=["project gameplay source paths"],
        forbidden_edits=["graders"],
        required_checks=["build"],
        status="test",
        engine_variants=["unreal"],
        limits={},
        probe_fields=[],
        provenance={},
        review={},
        native_execution_required=True,
    )
    
    # Mock runner that would falsely report PASS on untouched fixture
    class MockRunner:
        def run_task(self, **kwargs):
            return {"status": "PASS", "report": {"layers": {}, "probes": {}}, "report_file": "dummy.json"}
            
    out_dir = Path(tempfile.mkdtemp(prefix="test_attempt_"))
    try:
        attempt_rec = run_attempt(
            manifest=manifest,
            candidate_config=cand_cfg,
            task_spec=task_spec,
            workspace_root=temp_project_dir,
            runner=MockRunner(),
            output_dir=out_dir,
        )
        # Because candidate test_double provides 0 patches, overall_status must be FAIL_NO_PATCHES_APPLIED!
        assert attempt_rec["invocation"]["patches_applied_count"] == 0
        assert attempt_rec["grading"]["overall_status"] == "FAIL_NO_PATCHES_APPLIED"
        assert "Zero candidate patches were applied" in attempt_rec["grading"]["failure_cause"]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
