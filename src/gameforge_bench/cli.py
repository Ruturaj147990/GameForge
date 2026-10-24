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

    # eval-baseline
    p_base = subparsers.add_parser("eval-baseline", help="Run model baseline evaluation across registered candidates")
    p_base.add_argument("--manifest", type=Path, default=Path("configs/baseline_release_manifest.json"), help="Baseline release manifest")
    p_base.add_argument("--register", type=Path, default=Path("configs/model_register.json"), help="Model register")
    p_base.add_argument("--task-id", action="append", dest="tasks", help="Specific task ID(s) to evaluate (optional)")
    p_base.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root directory")

    # validate-data
    p_vdata = subparsers.add_parser("validate-data", help="Validate a sample manifest against schema, provenance, rights, and contamination")
    p_vdata.add_argument("--manifest", type=Path, required=True, help="Path to sample manifest JSON file")
    p_vdata.add_argument("--source-register", type=Path, default=Path("configs/dataset_source_register.json"), help="Dataset source register")
    p_vdata.add_argument("--dry-run", action="store_true", default=True, help="Preview validation without updating dataset manifests (default: True)")
    p_vdata.add_argument("--no-dry-run", action="store_false", dest="dry_run", help="Disable dry-run mode")
    p_vdata.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root directory")

    # ingest-data
    p_ingest = subparsers.add_parser("ingest-data", help="Deterministic ingestion of local sample manifests into dataset splits")
    p_ingest.add_argument("--manifest", type=Path, required=True, help="Path to sample manifest JSON file")
    p_ingest.add_argument("--output-manifest", type=Path, default=None, help="Output dataset manifest JSON path")
    p_ingest.add_argument("--source-register", type=Path, default=Path("configs/dataset_source_register.json"), help="Dataset source register")
    p_ingest.add_argument("--dry-run", action="store_true", default=False, help="Preview ingestion decisions without writing")
    p_ingest.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root directory")

    # run-tests
    p_tests = subparsers.add_parser("run-tests", help="Execute canonical test workflow across unit, protected oracles, and integration")
    p_tests.add_argument("--suite", default="all", choices=["all", "unit", "protected", "integration"], help="Test suite subset to run")
    p_tests.add_argument("--collect-only", action="store_true", help="Collect and report unique test IDs without execution")
    p_tests.add_argument("--json", action="store_true", help="Output machine-readable execution summary JSON")
    p_tests.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root directory")

    # chat
    p_chat = subparsers.add_parser("chat", help="Interactive GameForge assistant chat session or single query")
    p_chat.add_argument("--model", default="gameforge-27b-sft", help="Target Ollama model name (default: gameforge-27b-sft)")
    p_chat.add_argument("--engine", default=None, help="Target game engine context (e.g. unreal, unity, godot)")
    p_chat.add_argument("--version-context", default=None, help="Target engine version context (e.g. 5.4, 2022.3, 4.3)")
    p_chat.add_argument("--no-retrieval", action="store_true", help="Disable local knowledge retrieval layer")
    p_chat.add_argument("--query", "-q", default=None, help="Single query to ask the model without entering interactive mode")

    # eval-model
    p_evalm = subparsers.add_parser("eval-model", help="Run GameForge evaluation suite against a local model")
    p_evalm.add_argument("--model", default="gameforge-27b-sft", help="Model name to evaluate (default: gameforge-27b-sft)")
    p_evalm.add_argument("--limit", type=int, default=5, help="Number of questions to evaluate (default: 5, 0 for all)")
    p_evalm.add_argument("--representative", action="store_true", help="Evaluate one representative prompt per domain across all 8 domains")
    p_evalm.add_argument("--output", type=Path, default=Path("reports/gameforge_v1_evaluation_report.json"), help="Output report path")

    # model-info
    p_minfo = subparsers.add_parser("model-info", help="Display GameForge V1 model specifications, configuration, and limitations")

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


def cmd_eval_baseline(args: argparse.Namespace) -> int:
    from .baseline_eval import BaselineEvaluator
    evaluator = BaselineEvaluator(
        workspace_root=args.workspace,
        manifest_path=args.manifest,
        register_path=args.register,
    )
    scorecard = evaluator.run_all(subset_task_ids=args.tasks)
    print("\n=======================================================")
    print(" BASELINE EVALUATION COMPLETE")
    print("=======================================================")
    for cand_id, data in scorecard["scorecard"].items():
        print(f"Candidate: {cand_id}")
        print(f"  Attempts: {data['attempts_count']} | Passes: {data['passes_count']} | Pass@1: {data['pass_at_1']}")
        print(f"  Domain Breakdown: {data['domain_scores']}")
        print(f"  Failure Taxonomy: {data['failure_taxonomy']}")
    return 0


def cmd_validate_data(args: argparse.Namespace) -> int:
    from .data_factory import DataFactory
    manifest_path = args.manifest
    if not manifest_path.is_file():
        print(f"Error: Manifest file not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        samples_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(samples_data, dict) and "samples" in samples_data:
            samples_list = samples_data["samples"]
        elif isinstance(samples_data, list):
            samples_list = samples_data
        else:
            print("Error: Manifest must be a list of samples or an object with 'samples' key", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"Error reading manifest JSON: {exc}", file=sys.stderr)
        return 1

    factory = DataFactory(workspace_root=args.workspace, source_register_path=args.source_register)
    sample_reports = []
    for s in samples_list:
        rep = factory.validate_and_ingest_sample(s, dry_run=args.dry_run)
        sample_reports.append(rep)

    readiness = factory.produce_readiness_report(sample_reports)

    print("=" * 75)
    print(" GAMEFORGE DATA FACTORY — VALIDATION & READINESS REPORT")
    print("=" * 75)
    print(f"Total Discovered Samples:        {readiness['total_discovered']}")
    print(f"Schema Valid:                    {readiness['schema_valid']}")
    print(f"Provenance Complete:             {readiness['provenance_complete']}")
    print(f"Sources Training Confirmed:      {readiness['sources_training_confirmed']}")
    print(f"Sources Awaiting Rights Review:  {readiness['sources_review_required']}")
    print(f"Sources Restricted (Eval Only):  {readiness['sources_restricted_eval']}")
    print("-" * 75)
    print(f"Accepted Samples:                {readiness['accepted_samples']}")
    print(f"Rejected Samples:                {readiness['rejected_samples']}")
    if readiness["rejection_breakdown"]:
        print("Rejection Breakdown:")
        for cat, cnt in readiness["rejection_breakdown"].items():
            print(f"  * {cat:<25}: {cnt}")
    print("-" * 75)
    print(f"Eligible Split Allocation:       {readiness['split_allocation']}")
    print(f"Tombstones / Removals Recorded:  {readiness['tombstones_recorded']}")
    print(f"Training Ready?                  {'YES' if readiness['training_ready'] else 'NO (BLOCKED)'}")
    if not readiness["training_ready"]:
        print(f"Blocker:                         {readiness['training_block_reason']}")
    print("=" * 75)

    # Return non-zero if any samples were rejected or training is blocked when expected
    return 0 if readiness["rejected_samples"] == 0 else 1


def cmd_ingest_data(args: argparse.Namespace) -> int:
    from .data_factory import DataFactory
    manifest_path = args.manifest
    if not manifest_path.is_file():
        print(f"Error: Manifest file not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        samples_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        samples_list = samples_data.get("samples", samples_data) if isinstance(samples_data, dict) else samples_data
    except Exception as exc:
        print(f"Error reading manifest: {exc}", file=sys.stderr)
        return 1

    factory = DataFactory(workspace_root=args.workspace, source_register_path=args.source_register)
    accepted_records = []
    rejected_records = []

    for s in samples_list:
        rep = factory.validate_and_ingest_sample(s, dry_run=args.dry_run)
        if rep["accepted"]:
            s_copy = dict(s)
            s_copy.setdefault("split_info", {})["assigned_split"] = rep["assigned_split"]
            s_copy["split_info"]["group_id"] = rep.get("group_id", "default")
            accepted_records.append(s_copy)
        else:
            rejected_records.append({"sample_id": rep["sample_id"], "reasons": rep["reasons"]})

    print(f"Ingestion complete: {len(accepted_records)} accepted, {len(rejected_records)} rejected.")
    if not args.dry_run and args.output_manifest:
        out_data = {
            "dataset_version": "v1.0.0",
            "total_samples": len(accepted_records),
            "samples": accepted_records,
        }
        args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.output_manifest.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        print(f"Saved dataset manifest to {args.output_manifest}")

    return 0 if len(rejected_records) == 0 else 1


def cmd_run_tests(args: argparse.Namespace) -> int:
    import subprocess
    workspace = args.workspace
    suite = args.suite
    collect_only = args.collect_only

    suite_configs = {
        "unit": {"label": "Unit Tests", "path": "tests/unit"},
        "protected": {"label": "Protected Oracles (grdr)", "path": "graders/protected"},
        "integration": {"label": "Integration Tests (UE 5.7.4)", "path": "tests/integration"},
    }

    targets = [suite] if suite != "all" else ["unit", "protected", "integration"]
    summary_results = {}
    overall_exit_code = 0

    print("=" * 75)
    print(" GAMEFORGE CANONICAL TEST RUNNER — SUITE ORCHESTRATION")
    print("=" * 75)

    for tgt in targets:
        cfg = suite_configs[tgt]
        cmd = [sys.executable, "-m", "pytest", cfg["path"]]
        if collect_only:
            cmd.extend(["--collect-only", "-q"])
        else:
            cmd.extend(["-q"])

        res = subprocess.run(cmd, cwd=str(workspace), capture_output=True, text=True)
        stdout = res.stdout.strip()
        stderr = res.stderr.strip()

        # Parse test count from output
        count = 0
        status = "PASSED" if res.returncode == 0 else "FAILED"
        if res.returncode != 0:
            overall_exit_code = res.returncode

        # Parse lines
        lines = stdout.splitlines()
        last_line = lines[-1] if lines else ""

        summary_results[tgt] = {
            "label": cfg["label"],
            "path": cfg["path"],
            "exit_code": res.returncode,
            "status": status,
            "output_summary": last_line,
        }

        print(f"[{status:<6}] {cfg['label']:<32} -> {last_line}")

    print("=" * 75)
    if args.json:
        print(json.dumps(summary_results, indent=2))

    return overall_exit_code


def cmd_chat(args: argparse.Namespace) -> int:
    from .gameforge_cli import run_interactive_chat, query_ollama
    from .knowledge_retrieval import GameForgeKnowledgeBase

    if args.query:
        kb = GameForgeKnowledgeBase()
        snippets = kb.query_knowledge(args.query, engine_filter=args.engine, max_results=2) if not args.no_retrieval else []
        retrieval_text = kb.format_retrieval_context(snippets)
        prompt = f"{retrieval_text}\nUser Question: {args.query}" if retrieval_text else args.query

        res = query_ollama(
            prompt=prompt,
            model_name=args.model,
        )
        if res.get("success"):
            print("=" * 80)
            print(f"GameForge LLM ({args.model}) Response:")
            print("=" * 80)
            print(res.get("response", "").strip())
            print("-" * 80)
            print(f"Generation Stats: {res.get('completion_tokens', 0)} tokens in {res.get('total_duration_seconds', 0.0):.2f}s ({res.get('tokens_per_second', 0.0):.2f} tok/s)")
            return 0
        else:
            print(f"Error querying model: {res.get('error')}", file=sys.stderr)
            return 1
    else:
        run_interactive_chat(
            model=args.model,
            engine=args.engine,
        )
        return 0


def cmd_eval_model(args: argparse.Namespace) -> int:
    from .gameforge_cli import run_model_evaluation

    run_model_evaluation(
        model=args.model,
        limit=args.limit,
        representative=args.representative,
        output_file=str(args.output),
    )
    return 0


def cmd_model_info(args: argparse.Namespace) -> int:
    print("=" * 75)
    print(" GAMEFORGE LLM V1 — MODEL ARCHITECTURE & OPERATIONAL PROFILE")
    print("=" * 75)
    print("Base Architecture:     Qwen 2.5 / Qwen3.8 27B Parameter Model")
    print("Quantization:          Q4_K_M (4-bit Medium Quantization)")
    print("Model Size:            ~17.1 GB on E:\\GameForge\\models\\ollama")
    print("Local Serving:         Ollama v0.40.6 on 127.0.0.1:11434")
    print("GPU / VRAM Target:     AMD Radeon RX 7700 XT (12 GB VRAM) + System RAM")
    print("Execution Context:     4,096 tokens (num_ctx 4096)")
    print("Specialist Prompt:     Multi-Engine (Unreal Engine 5.7, Unity, Godot,")
    print("                       Roblox, UEFN, Bevy, GameMaker, Custom C++/Vulkan)")
    print("Knowledge Layer:       Local version-aware indexed excerpts with provenance")
    print("Hardware Profile:      Hybrid VRAM offload (ROCm/Vulkan) + System DDR5 RAM")
    print("Measured Speed:        ~5.9 - 6.0 tokens/second generation, 240+ prompt tok/s")
    print("-" * 75)
    print("Operational Boundaries & Strict Gate Notice:")
    print(" - Modelfile customization changes system prompt and sampling parameters.")
    print(" - It does NOT modify base neural weights (SFT/LoRA remains gated pending legal).")
    print(" - Benchmark suites remain segregated; test data is never leaked to model.")
    print("=" * 75)
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
    elif args.command == "eval-baseline":
        return cmd_eval_baseline(args)
    elif args.command == "validate-data":
        return cmd_validate_data(args)
    elif args.command == "ingest-data":
        return cmd_ingest_data(args)
    elif args.command == "run-tests":
        return cmd_run_tests(args)
    elif args.command == "chat":
        return cmd_chat(args)
    elif args.command == "eval-model":
        return cmd_eval_model(args)
    elif args.command == "model-info":
        return cmd_model_info(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
