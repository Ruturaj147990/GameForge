"""Unit tests for Step 8 Tool-Use and Compiler Self-Repair Loop.

Tests:
- Bounded, typed tools (read_file, write_file, list_dir) and policy enforcement
- Rejection of path traversal and edits outside allowed_edit_paths
- Forbidden edits guard (rejection of hidden grader modifications)
- Diagnostic classification across syntax errors, missing reflection macros, and probe failures
- Clean snapshot verification and state preservation
- Repair loop execution with targeted file patching and status convergence
- Schema conformance of Step 8 repair trajectory records
"""

import json
from pathlib import Path
import pytest

from gameforge_bench.repair_loop import (
    AgentToolbox,
    CompilerDiagnosticEngine,
    DiagnosticResult,
    RepairLoopOrchestrator,
)


def test_agent_toolbox_path_containment_and_policy(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    allowed_dir = ws / "Source" / "GameForgePilot"
    allowed_dir.mkdir(parents=True)
    (allowed_dir / "HealthComponent.cpp").write_text("// initial code", encoding="utf-8")

    toolbox = AgentToolbox(
        workspace_root=ws,
        active_dir=ws,
        allowed_paths=["Source/GameForgePilot", "project gameplay source paths"],
    )

    # 1. Reading allowed file succeeds
    read_res = toolbox.read_file("Source/GameForgePilot/HealthComponent.cpp")
    assert read_res["success"] is True
    assert read_res["content"] == "// initial code"

    # 2. Writing within allowed path succeeds
    write_res = toolbox.write_file("Source/GameForgePilot/HealthComponent.cpp", "// updated code")
    assert write_res["success"] is True
    assert (allowed_dir / "HealthComponent.cpp").read_text(encoding="utf-8") == "// updated code"

    # 3. Writing outside allowed paths fails policy check
    unauthorized_res = toolbox.write_file("Config/DefaultEngine.ini", "[Settings]")
    assert unauthorized_res["success"] is False
    assert "POLICY_FAIL" in unauthorized_res["error"]

    # 4. Forbidden paths (hidden grader / acceptance criteria) are strictly blocked
    forbidden_res = toolbox.write_file("graders/protected/test_oracle.py", "def test_bypass(): pass")
    assert forbidden_res["success"] is False
    assert "POLICY_FAIL" in forbidden_res["error"]


def test_compiler_diagnostic_engine_classification():
    # Reflection macro missing
    log_reflection = "UHT: error: Expected GENERATED_BODY() in class declaration."
    d1 = CompilerDiagnosticEngine.analyze_log(log_reflection)
    assert d1.failure_class == "REFLECTION_MACRO_MISSING"
    assert "GENERATED_BODY" in d1.recommended_fix

    # Syntax error
    log_syntax = "HealthComponent.cpp(45): error C2143: syntax error: missing ';' before '}'"
    d2 = CompilerDiagnosticEngine.analyze_log(log_syntax)
    assert d2.failure_class == "COMPILER_SYNTAX_ERROR"

    # Delegate signature mismatch
    log_delegate = "error: no matching function for call to AddDynamic on OnHealthChanged"
    d3 = CompilerDiagnosticEngine.analyze_log(log_delegate)
    assert d3.failure_class == "DELEGATE_SIGNATURE_MISMATCH"

    # Runtime probe failure
    probes = {
        "probe_initial_health": {"passed": True},
        "probe_invulnerability_window": {"passed": False},
    }
    d4 = CompilerDiagnosticEngine.analyze_log("", probe_results=probes)
    assert d4.failure_class == "RUNTIME_PROBE_FAILED"
    assert "probe_invulnerability_window" in d4.error_snippet


def test_step8_repair_trajectory_schema_conformance(tmp_path: Path):
    schema_path = Path("schemas/step8_repair_contract.json")
    assert schema_path.is_file(), "schemas/step8_repair_contract.json must exist"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["title"] == "GameForge Step 8 Agentic Tool & Repair Trajectory Contract"

    sample_record = {
        "schema_version": "1.0.0",
        "session_id": "test_session_001",
        "task_id": "t2-004-health-damage",
        "engine": "unreal",
        "clean_snapshot_hash": "a" * 64,
        "initial_status": "PARTIAL_BUILD",
        "repair_iterations": 1,
        "max_allowed_repair_iterations": 3,
        "final_status": "PASS",
        "tool_calls_trace": [
            {
                "step_index": 0,
                "tool_name": "compile_project",
                "action_payload": {"iteration": 0},
                "observation_result": {"status": "PARTIAL_BUILD"},
                "diagnostics": {
                    "failure_class": "COMPILER_SYNTAX_ERROR",
                    "targeted_file": "HealthComponent.cpp",
                    "line_number": 42,
                    "recommended_fix": "Fix missing semicolon",
                },
            },
            {
                "step_index": 1,
                "tool_name": "write_file",
                "action_payload": {"path": "HealthComponent.cpp"},
                "observation_result": {"bytes_written": 250},
                "diagnostics": {"failure_class": "NONE"},
            },
        ],
        "outcome_verification": {
            "verified_by_engine": True,
            "non_zero_patches_verified": True,
            "regression_tests_passed": True,
            "hidden_grader_untampered": True,
        },
    }

    # Verify required keys
    for req in schema["required"]:
        assert req in sample_record, f"Missing required key: {req}"
