"""Unit tests for GameForge Agentic Eval Suite (WI-9.1)."""
from pathlib import Path
import json
import pytest

from src.gameforge_ide.evals.adapters import DeterministicMockAdapter, HostedAdapter
from src.gameforge_ide.evals.metrics import compute_task_metrics
from src.gameforge_ide.evals.report import format_markdown_summary, save_eval_report
from src.gameforge_ide.evals.runner import EvalRunner


def test_compute_task_metrics_empty():
    m = compute_task_metrics([])
    assert m["total_tasks"] == 0
    assert m["pass_rate"] == 0.0


def test_compute_task_metrics_calculation():
    results = [
        {"passed": True, "valid_json": True, "first_try_valid": True, "duration_s": 1.2, "tok_per_sec": 60.0, "tokens_in": 100, "tokens_out": 50},
        {"passed": True, "valid_json": True, "first_try_valid": False, "duration_s": 2.4, "tok_per_sec": 50.0, "tokens_in": 120, "tokens_out": 60},
        {"passed": False, "valid_json": True, "first_try_valid": True, "duration_s": 0.8, "tok_per_sec": 70.0, "tokens_in": 80, "tokens_out": 40},
        {"passed": False, "valid_json": False, "first_try_valid": False, "duration_s": 3.0, "tok_per_sec": 40.0, "tokens_in": 90, "tokens_out": 30},
    ]
    m = compute_task_metrics(results)
    assert m["total_tasks"] == 4
    assert m["passed_tasks"] == 2
    assert m["pass_rate"] == 50.0
    assert m["valid_json_rate"] == 75.0
    assert m["first_try_valid_rate"] == 50.0
    assert m["median_latency_s"] == 1.8
    assert m["p90_latency_s"] == 3.0
    assert m["total_tokens_in"] == 390
    assert m["total_tokens_out"] == 180


def test_eval_runner_mock_suite(tmp_path: Path):
    runner = EvalRunner()
    adapter = DeterministicMockAdapter("mock-test:latest")

    res = runner.run_suite(adapter, limits={"design_draft": 2, "gds_patch": 2, "codegen_rule": 2, "cpp_repair": 2})
    assert res["model_id"] == "mock-test:latest"
    assert res["overall"]["total_tasks"] == 8
    assert res["overall"]["pass_rate"] > 0.0
    assert "design_draft" in res["families"]
    assert "gds_patch" in res["families"]

    report_path = save_eval_report(res, reports_dir=tmp_path)
    assert report_path.is_file()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["status"] == "PASS"
    assert saved["model_id"] == "mock-test:latest"

    summary_md = format_markdown_summary([res])
    assert "| `mock-test:latest` |" in summary_md


def test_hosted_adapter_blocked_without_approval():
    adapter = HostedAdapter(provider_id="anthropic", model_id="claude-3-7-sonnet")
    res = adapter.complete("test prompt")
    assert "BLOCKED" in res["error"]
