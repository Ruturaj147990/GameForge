"""Reporting and Diagnostic Summary Generation for GameForge Benchmark."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engines.base import EngineDiscoveryResult
from .grading import GradingPipelineResult, RunStatus
from .isolation import audit_os_isolation_capabilities
from .provenance import capture_environment
from .task_loader import TaskSpec


def compute_run_verification_level(
    task_spec: TaskSpec,
    engine_discovery: EngineDiscoveryResult,
    grading_result: GradingPipelineResult,
) -> str:
    """Computes truthful canonical verification level based on execution evidence."""
    is_engine_available = bool(
        engine_discovery.is_installed
        and engine_discovery.executable_path
        and engine_discovery.executable_path != "none"
    )

    if not is_engine_available or grading_result.overall_status == RunStatus.HARNESS_INVALID:
        return "UNVERIFIED"

    if grading_result.overall_status == RunStatus.PASS:
        if getattr(task_spec, "native_execution_required", True):
            return "REAL_ENGINE_VERIFIED"
        return getattr(task_spec, "verification_level", "STATICALLY_VALIDATED")
    elif grading_result.overall_status == RunStatus.PARTIAL_BUILD:
        return "UNIT_TESTED"
    elif grading_result.overall_status == RunStatus.FAIL_BUILD:
        if grading_result.layers.get("policy_checks", {}).status == "PASS":
            return "STATICALLY_VALIDATED"
        return "UNVERIFIED"
    elif grading_result.overall_status == RunStatus.POLICY_FAIL:
        return "UNVERIFIED"
    else:
        return "UNVERIFIED"


def assemble_benchmark_report(
    run_id: str,
    task_spec: TaskSpec,
    engine_discovery: EngineDiscoveryResult,
    grading_result: GradingPipelineResult,
    candidate_id: str = "reference_solution",
    candidate_type: str = "reference",
    snapshot_hash: str = "",
    diff_summary: Optional[str] = None,
    log_files: Optional[Dict[str, str]] = None,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Assembles a full machine-readable evaluation report conforming to report_schema.json."""
    env_rec = capture_environment(workspace_root)
    isolation_audit = audit_os_isolation_capabilities()

    project_version = engine_discovery.version or ("5.7" if engine_discovery.engine_name == "unreal" else "2022.3")

    report = {
        "report_schema_version": "0.1.0",
        "benchmark_version": "v0.1",
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "logical_task_id": task_spec.logical_task_id,
        "task_id": task_spec.id,
        "engine_scope": getattr(task_spec, "engine_scope", "ENGINE_SPECIFIC"),
        "verification_level": compute_run_verification_level(task_spec, engine_discovery, grading_result),
        "knowledge_domains": getattr(task_spec, "knowledge_domains", ["gameplay"]),
        "engine": {
            "name": engine_discovery.engine_name,
            "version": engine_discovery.version or "unverified",
            "executable_path": engine_discovery.executable_path or "none",
            "project_version": project_version,
        },
        "environment": {
            "os": f"{env_rec['os']} {env_rec['os_release']}",
            "python_version": env_rec["python_version"],
            "toolchain_versions": {
                "processor": env_rec["processor"],
                "python_executable": env_rec["python_executable"],
            },
            "git_commit": env_rec.get("git_commit"),
            "hardware": env_rec.get("hardware_notes", {}),
        },
        "candidate": {
            "candidate_id": candidate_id,
            "candidate_type": candidate_type,
            "snapshot_hash": snapshot_hash,
        },
        "budgets": {
            "wall_clock_seconds": task_spec.limits.wall_clock_seconds,
            "max_tool_calls": task_spec.limits.max_tool_calls,
            "max_model_tokens": task_spec.limits.max_model_tokens,
        },
        "reproducibility": {
            "fixed_timestep": task_spec.reproducibility.fixed_timestep_seconds,
            "seed": task_spec.reproducibility.random_seed,
        },
        "status": grading_result.overall_status.value if hasattr(grading_result.overall_status, "value") else str(grading_result.overall_status),
        "first_mandatory_failure_layer": grading_result.first_mandatory_failure_layer,
        "layers": {
            layer_name: {
                "status": outcome.status if hasattr(outcome, "status") else outcome.get("status"),
                "duration_seconds": outcome.duration_seconds if hasattr(outcome, "duration_seconds") else outcome.get("duration_seconds", 0.0),
                "message": outcome.message if hasattr(outcome, "message") else outcome.get("message", ""),
                "details": outcome.details if hasattr(outcome, "details") else outcome.get("details", {}),
            }
            for layer_name, outcome in grading_result.layers.items()
        },
        "probes": grading_result.probes,
        "diff_summary": diff_summary,
        "isolation": {
            "provider": "RestrictedProcessIsolationProvider",
            "classification": isolation_audit.default_classification,
            "runtime_version": isolation_audit.host_build,
            "network_restricted": False,
            "host_fs_restricted": False,
            "timeout_policy_seconds": 180.0,
            "cleanup_status": "DISPOSABLE_WORKSPACE_PER_RUN",
            "workspace_identity": "scratch/eval_runs",
            "residual_risks": [
                "Host user permissions retained by native C++ process",
                "OS-level sandbox (Hyper-V / Windows Sandbox) not active",
            ],
        },
        "logs": log_files or {},
        "duration_seconds": round(grading_result.duration_seconds, 3),
        "warnings": grading_result.warnings,
    }

    return report


def save_report(report: Dict[str, Any], output_dir: Path | str) -> Path:
    """Saves report JSON to disk."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = report.get("run_id", f"run_{int(time.time())}")
    report_file = out_dir / f"{run_id}.json"
    with report_file.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report_file


def format_report_summary(report: Dict[str, Any]) -> str:
    """Generates a human-readable diagnostic text summary of a run report."""
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f" GAMEFORGE EVALUATION REPORT: {report.get('run_id', 'UNKNOWN')}")
    lines.append("=" * 80)
    lines.append(f"Task:            {report.get('task_id', 'N/A')} ({report.get('logical_task_id', 'N/A')})")
    eng = report.get("engine", {})
    lines.append(f"Engine:          {eng.get('name', 'N/A')} (v{eng.get('version', 'N/A')})")
    cand = report.get("candidate", {})
    lines.append(f"Candidate:       {cand.get('candidate_id', 'N/A')} ({cand.get('candidate_type', 'N/A')})")
    lines.append(f"Status:          {report.get('status', 'UNKNOWN')}")
    if "isolation" in report:
        iso = report["isolation"]
        lines.append(f"Isolation:       {iso.get('classification', 'UNVERIFIED')} ({iso.get('provider', 'none')})")
    if report.get("first_mandatory_failure_layer"):
        lines.append(f"First Failure:   {report['first_mandatory_failure_layer']}")
    lines.append(f"Total Duration:  {report.get('duration_seconds', 0.0)}s")
    lines.append("-" * 80)
    lines.append("GRADING LAYERS:")
    for layer, data in report.get("layers", {}).items():
        st = data.get("status", "UNKNOWN") if isinstance(data, dict) else getattr(data, "status", "UNKNOWN")
        msg = data.get("message", "") if isinstance(data, dict) else getattr(data, "message", "")
        dur = data.get("duration_seconds", 0.0) if isinstance(data, dict) else getattr(data, "duration_seconds", 0.0)
        lines.append(f"  [{st:^7}] {layer:<22} ({dur:.2f}s) - {msg}")

    probes = report.get("probes", {})
    if probes:
        lines.append("-" * 80)
        lines.append("BEHAVIOR PROBES:")
        for pid, pdata in probes.items():
            pst = "PASS" if pdata.get("passed") else "FAIL"
            m = pdata.get("measured_value")
            t = pdata.get("target_value")
            tol = pdata.get("tolerance")
            unit = pdata.get("unit", "")
            tol_str = f" +/- {tol}" if tol is not None else ""
            lines.append(f"  [{pst:^5}] {pid:<32}: measured={m} {unit} | target={t}{tol_str}")

    if report.get("warnings"):
        lines.append("-" * 80)
        lines.append("WARNINGS:")
        for w in report["warnings"]:
            lines.append(f"  * {w}")

    lines.append("=" * 80)
    return "\n".join(lines)


def aggregate_reports(report_dir: Path | str) -> Dict[str, Any]:
    """Summarizes all reports in a directory."""
    r_dir = Path(report_dir)
    summary: Dict[str, Any] = {
        "total_runs": 0,
        "counts_by_status": {
            "PASS": 0,
            "PARTIAL_BUILD": 0,
            "FAIL_BUILD": 0,
            "POLICY_FAIL": 0,
            "HARNESS_INVALID": 0,
            "FLAKY_QUARANTINED": 0,
        },
        "pass_rate_pct": 0.0,
        "average_duration_seconds": 0.0,
        "runs": [],
    }

    if not r_dir.is_dir():
        return summary

    total_dur = 0.0
    for r_file in sorted(r_dir.glob("*.json")):
        try:
            with r_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            st = data.get("status", "UNKNOWN")
            summary["total_runs"] += 1
            if st not in summary["counts_by_status"]:
                summary["counts_by_status"][st] = 0
            summary["counts_by_status"][st] += 1

            dur = float(data.get("duration_seconds", 0.0))
            total_dur += dur

            summary["runs"].append({
                "run_id": data.get("run_id"),
                "task_id": data.get("task_id"),
                "engine": data.get("engine", {}).get("name"),
                "status": st,
                "first_failure": data.get("first_mandatory_failure_layer"),
                "duration": dur,
            })
        except Exception:
            pass

    if summary["total_runs"] > 0:
        summary["pass_rate_pct"] = round((summary["counts_by_status"].get("PASS", 0) / summary["total_runs"]) * 100, 2)
        summary["average_duration_seconds"] = round(total_dur / summary["total_runs"], 3)

    return summary
