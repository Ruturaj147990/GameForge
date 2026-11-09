"""CLI runner for GameForge Agentic Eval Suite (WI-9.1, Exit Gate 1)."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.evals.adapters import DeterministicMockAdapter, OllamaAdapter
from src.gameforge_ide.evals.report import format_markdown_summary, save_eval_report
from src.gameforge_ide.evals.runner import EvalRunner

CANONICAL_LOCAL_MODELS = [
    "gameforge-qwen3.5-9b:latest",
    "gameforge-qwen3.5-4b:latest",
    "gameforge-27b-sft:latest",
    "llama3.1:8b",
]


def get_git_sha() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True)
        return res.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GameForge Agentic Eval Suite")
    parser.add_argument("--model", type=str, default=None, help="Specific model name to evaluate")
    parser.add_argument("--all-local", action="store_true", help="Evaluate all 4 canonical local models")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock adapter")
    parser.add_argument("--host", type=str, default="127.0.0.1:11434", help="Ollama host")
    parser.add_argument("--limit-dd", type=int, default=15, help="Limit for design_draft tasks")
    parser.add_argument("--limit-gp", type=int, default=10, help="Limit for gds_patch tasks")
    parser.add_argument("--limit-cr", type=int, default=5, help="Limit for codegen_rule tasks")
    parser.add_argument("--limit-rep", type=int, default=10, help="Limit for cpp_repair tasks")
    args = parser.parse_args()

    git_sha = get_git_sha()
    runner = EvalRunner()
    limits = {
        "design_draft": args.limit_dd,
        "gds_patch": args.limit_gp,
        "codegen_rule": args.limit_cr,
        "cpp_repair": args.limit_rep,
    }

    if args.mock:
        models = ["mock-model:latest"]
    elif args.all_local:
        models = CANONICAL_LOCAL_MODELS
    elif args.model:
        models = [args.model]
    else:
        models = ["gameforge-qwen3.5-9b:latest"]

    all_reports = []
    print(f"Starting GameForge Agentic Evaluation Suite (git: {git_sha[:8]})...")
    print(f"Target models: {models}")
    print(f"Task limits per model: {limits}\n")

    reports_dir = REPO_ROOT / "reports" / "P9"
    reports_dir.mkdir(parents=True, exist_ok=True)

    for m in models:
        print(f"============================================================")
        print(f"Evaluating model: {m}")
        print(f"============================================================")
        if args.mock:
            adapter = DeterministicMockAdapter(m)
        else:
            adapter = OllamaAdapter(m, host=args.host)

        t_start = time.time()
        res = runner.run_suite(adapter, limits=limits)
        duration = time.time() - t_start

        report_file = save_eval_report(res, reports_dir=reports_dir, git_sha=git_sha)
        all_reports.append(res)

        ov = res["overall"]
        print(f"Completed in {duration:.2f}s | Pass Rate: {ov['pass_rate']}% | Valid JSON: {ov['valid_json_rate']}% | p90 Latency: {ov['p90_latency_s']}s")
        print(f"Saved report: {report_file}\n")

    summary_md = format_markdown_summary(all_reports)
    summary_path = reports_dir / "eval_summary.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    print("============================================================")
    print("EVALUATION SUMMARY")
    print("============================================================")
    print(summary_md)


if __name__ == "__main__":
    main()
