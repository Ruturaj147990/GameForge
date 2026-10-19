"""Unit tests for report schema assembly, diagnostic text, and multi-run aggregation."""

import json
from pathlib import Path
from gameforge_bench.engines.base import EngineDiscoveryResult
from gameforge_bench.grading import GradingPipelineResult, LayerOutcome, RunStatus
from gameforge_bench.reporting import (
    aggregate_reports,
    assemble_benchmark_report,
    format_report_summary,
    save_report,
)
from gameforge_bench.task_loader import TaskLimits, TaskSpec


def test_assemble_and_save_report(tmp_path):
    spec = TaskSpec(
        id="t2-001-third-person-controller",
        logical_task_id="T2-001",
        tier="T2",
        title="Third-person movement and camera",
        prompt="Implement controller",
        limits=TaskLimits(),
        allowed_edit_paths=["Source"],
        forbidden_edits=["tests"],
    )

    eng = EngineDiscoveryResult(
        engine_name="unreal",
        is_installed=True,
        version="5.7.4",
        executable_path=r"E:\UE\UE_5.7\Engine\Binaries\Win64\UnrealEditor-Cmd.exe",
    )

    grading = GradingPipelineResult(
        overall_status=RunStatus.PASS,
        first_mandatory_failure_layer=None,
        layers={"clean_start": LayerOutcome("PASS", message="OK")},
        probes={"speed": {"passed": True, "measured_value": 6.0, "target_value": 6.0, "unit": "m/s"}},
    )

    report = assemble_benchmark_report(
        run_id="run_test_001",
        task_spec=spec,
        engine_discovery=eng,
        grading_result=grading,
    )

    assert report["report_schema_version"] == "0.1.0"
    assert report["status"] == "PASS"
    assert report["engine"]["version"] == "5.7.4"

    # Save report
    rep_file = save_report(report, tmp_path)
    assert rep_file.is_file()

    # Formatted summary text
    text = format_report_summary(report)
    assert "GAMEFORGE EVALUATION REPORT: run_test_001" in text
    assert "PASS" in text

    # Multi-run aggregation
    summary = aggregate_reports(tmp_path)
    assert summary["total_runs"] == 1
    assert summary["counts_by_status"]["PASS"] == 1
