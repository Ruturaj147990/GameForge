"""Command Line Interface for GameForge Benchmark Foundation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .engines.discovery import discover_environment
from .reporting import aggregate_reports
from .runner import BenchmarkRunner
from .task_loader import load_task_inventory
from .task_validation import validate_all_specs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gameforge-bench",
        description="GameForge Benchmark Foundation: Cross-Engine Evaluation Framework",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Inspect local engines, compilers, and toolchains")
    p_doctor.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # list-tasks
    p_list = subparsers.add_parser("list-tasks", help="List logical benchmark tasks and available variants")
    p_list.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root directory")

    # validate-specs
    p_val = subparsers.add_parser("validate-specs", help="Validate task schema, pilot YAMLs, and inventory CSV")
    p_val.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root directory")

    # run
    p_run = subparsers.add_parser("run", help="Run benchmark evaluation pipeline on a task")
    p_run.add_argument("--task-id", required=True, help="Task ID (e.g. t2-001-third-person-controller)")
    p_run.add_argument("--engine", default="auto", choices=["auto", "unreal", "unity"], help="Target engine")
    p_run.add_argument("--candidate-dir", type=Path, default=None, help="Path to candidate project")
    p_run.add_argument("--candidate-id", default="reference_solution", help="Identifier for evaluated model/candidate")
    p_run.add_argument("--report-dir", type=Path, default=Path("reports"), help="Output directory for reports")
    p_run.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root directory")

    # summarize
    p_sum = subparsers.add_parser("summarize", help="Aggregate evaluation reports across runs")
    p_sum.add_argument("--report-dir", type=Path, default=Path("reports"), help="Reports directory")

    return parser


def cmd_doctor(args: argparse.Namespace) -> int:
    env_info = discover_environment()
    if args.json:
        print(json.dumps(env_info, indent=2))
        return 0

    print("=" * 70)
    print(" GAMEFORGE BENCHMARK DOCTOR — ENVIRONMENT & ENGINE AUDIT")
    print("=" * 70)
    print(f"Python Version:   {env_info['toolchains']['python']}")
    print(f".NET SDK:         {env_info['toolchains']['dotnet'] or 'Not found'}")
    print(f"MSBuild:          {env_info['toolchains']['msbuild'] or 'Not found'}")
    print(f"MSVC Version:     {env_info['toolchains']['msvc'] or 'Not found'}")
    print(f"Git Version:      {env_info['toolchains']['git'] or 'Not found'}")
    print("-" * 70)
    print("GAME ENGINES:")
    for eng_name, eng in env_info["engines"].items():
        st = "INSTALLED & RUNNABLE" if eng["is_runnable"] else "NOT DETECTED"
        print(f"  * {eng_name.upper():<8}: [{st}]")
        if eng["is_installed"]:
            print(f"      Version:    {eng['version']}")
            print(f"      Executable: {eng['executable_path']}")
        else:
            print(f"      Notes:      {eng['notes']}")
    print("=" * 70)
    return 0


def cmd_list_tasks(args: argparse.Namespace) -> int:
    inv_file = args.workspace / "TASK_INVENTORY.csv"
    pilot_dir = args.workspace / "pilot_tasks"

    if not inv_file.is_file():
        print(f"Error: Inventory file not found at {inv_file}", file=sys.stderr)
        return 1

    try:
        tasks = load_task_inventory(inv_file)
    except Exception as exc:
        print(f"Error loading inventory: {exc}", file=sys.stderr)
        return 1

    pilot_files = {p.stem: p for p in pilot_dir.glob("*.yaml")} if pilot_dir.is_dir() else {}

    print(f"{'ID':<10} {'Tier':<6} {'Category':<18} {'Pilot?':<8} {'YAML Variant Found':<25} {'Title'}")
    print("-" * 95)
    for t in tasks:
        # Check if corresponding pilot file exists
        yaml_match = None
        for stem in pilot_files:
            if t.id.lower() in stem.lower():
                yaml_match = stem
                break

        pilot_str = "YES" if t.pilot else "NO"
        yaml_str = yaml_match if yaml_match else "(none)"
        print(f"{t.id:<10} {t.tier:<6} {t.category:<18} {pilot_str:<8} {yaml_str:<25} {t.title}")

    print("-" * 95)
    print(f"Total Logical Tasks: {len(tasks)} | Implemented Pilot Drafts: {len(pilot_files)}")
    return 0


def cmd_validate_specs(args: argparse.Namespace) -> int:
    print("Validating benchmark specifications and task inventory...")
    result = validate_all_specs(args.workspace)

    print("=" * 80)
    print(f" SPECIFICATION VALIDATION REPORT: {'PASSED' if result.is_valid else 'FAILED'}")
    print("=" * 80)
    print(f"Total Logical Tasks Checked: {result.total_inventory_tasks}")
    print(f"Total Pilot YAMLs Checked:   {result.total_specs_checked}")
    print(f"Total Errors Found:          {len(result.errors)}")
    print(f"Total Warnings:              {len(result.warnings)}")
    print(f"Total Discrepancies:         {len(result.discrepancies)}")
    print("-" * 80)

    for issue in result.issues:
        prefix = f"[{issue.severity}]"
        print(f"{prefix:<15} {issue.source} -> {issue.field_name}: {issue.message}")

    print("=" * 80)
    return 0 if result.is_valid else 1


def cmd_run(args: argparse.Namespace) -> int:
    runner = BenchmarkRunner(workspace_root=args.workspace, reports_dir=args.report_dir)
    try:
        res = runner.run_task(
            task_id=args.task_id,
            engine_name=args.engine,
            candidate_dir=args.candidate_dir,
            candidate_id=args.candidate_id,
        )
        print(res["summary_text"])
        print(f"\nReport written to: {res['report_file']}")
        return 0 if res["status"] == "PASS" else 1
    except Exception as exc:
        print(f"Fatal Runner Error: {exc}", file=sys.stderr)
        return 2


def cmd_summarize(args: argparse.Namespace) -> int:
    summary = aggregate_reports(args.report_dir)
    print("=" * 70)
    print(" GAMEFORGE BENCHMARK EVALUATION RUNS SUMMARY")
    print("=" * 70)
    print(f"Total Evaluated Runs: {summary['total_runs']}")
    print("-" * 70)
    print("Status Breakdown:")
    for status, count in summary["counts_by_status"].items():
        print(f"  {status:<20}: {count}")
    print("-" * 70)
    print("Individual Runs:")
    for r in summary["runs"]:
        print(f"  * {r['run_id']} | Task: {r['task_id']} | Engine: {r['engine']} | Status: {r['status']}")
    print("=" * 70)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return cmd_doctor(args)
    elif args.command == "list-tasks":
        return cmd_list_tasks(args)
    elif args.command == "validate-specs":
        return cmd_validate_specs(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "summarize":
        return cmd_summarize(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
