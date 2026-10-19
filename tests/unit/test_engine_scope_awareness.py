"""Unit tests for Engine Scope Awareness and Cross-Engine Metadata (Phase Two & Three)."""

import json
from pathlib import Path
import pytest

from gameforge_bench.task_loader import load_task, normalize_task_dict
from gameforge_bench.task_validation import validate_all_specs
from gameforge_bench.runner import BenchmarkRunner
from gameforge_bench.reporting import assemble_benchmark_report, save_report
from gameforge_bench.engines.base import EngineDiscoveryResult
from gameforge_bench.grading import GradingPipelineResult, LayerOutcome, RunStatus


def test_existing_task_specs_have_default_engine_scope():
    """All existing task specifications load with backward-compatible engine scope defaults."""
    task = load_task(Path("pilot_tasks/t2-001-third-person-controller.yaml"))
    assert task.engine_scope == "ENGINE_SPECIFIC"
    assert "unreal" in task.engines_supported
    assert task.verification_level == "REAL_ENGINE_VERIFIED"
    assert "gameplay" in task.knowledge_domains
    assert task.native_execution_required is True


def test_engine_agnostic_task_normalization(tmp_path):
    """Engine-agnostic conceptual tasks normalize correctly without engine variants."""
    raw = {
        "id": "t1-001-health-invariants",
        "logical_task_id": "T1-001",
        "tier": "T1",
        "title": "Explain and formalize health and damage invariants",
        "engine_scope": "ENGINE_AGNOSTIC",
        "verification_level": "STATICALLY_VALIDATED",
        "knowledge_domains": ["core_gameplay", "math_invariants"],
        "prompt": "Formalize the health, damage, clamping, and event invariants for a living character.",
        "limits": {"wall_clock_seconds": 600, "max_tool_calls": 30},
        "allowed_edit_paths": ["answers"],
        "forbidden_edits": ["tests"],
    }
    normalized = normalize_task_dict(raw)
    assert normalized["engine_scope"] == "ENGINE_AGNOSTIC"
    assert normalized["verification_level"] == "STATICALLY_VALIDATED"
    assert "core_gameplay" in normalized["knowledge_domains"]


def test_older_reports_remain_loadable(tmp_path):
    """Older JSON reports without engine_scope metadata remain fully parsable and backward-compatible."""
    old_report = {
        "report_schema_version": "0.1.0",
        "benchmark_version": "v0.1",
        "run_id": "run_legacy_1001",
        "timestamp": "2026-10-19T10:00:00Z",
        "logical_task_id": "T2-001",
        "task_id": "t2-001-third-person-controller",
        "engine": {"name": "unreal", "version": "5.7.4", "executable_path": "E:/UE"},
        "status": "PASS",
        "layers": {"build_import": {"status": "PASS"}},
    }
    report_file = tmp_path / "legacy_report.json"
    report_file.write_text(json.dumps(old_report), encoding="utf-8")

    with report_file.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["run_id"] == "run_legacy_1001"
    assert loaded["status"] == "PASS"


def test_unavailable_engine_reports_harness_invalid():
    """Requesting an engine variant not installed in the host environment yields HARNESS_INVALID."""
    runner = BenchmarkRunner(workspace_root=Path.cwd())
    # Request unity where unity is not installed
    res = runner.run_task(
        task_id="t2-005-pickup-collection",
        engine_name="unity",
        candidate_dir=Path("fixtures/unity/t2_005_pickup"),
    )
    assert res["status"] == RunStatus.HARNESS_INVALID.value
    assert res["report"]["layers"]["build_import"]["status"] == "ERROR"
    assert "Engine not installed" in res["report"]["layers"]["build_import"]["message"]
