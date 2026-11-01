"""Reporting utilities for GameForge Agentic Eval Suite (WI-9.1)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def sanitize_model_name(model_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", model_name)


def save_eval_report(
    eval_result: Dict[str, Any],
    reports_dir: Optional[Path] = None,
    git_sha: Optional[str] = None,
) -> Path:
    """Save an evaluation report to reports/P9/."""
    r_dir = reports_dir or Path("reports/P9")
    r_dir.mkdir(parents=True, exist_ok=True)

    model_clean = sanitize_model_name(eval_result["model_id"])
    timestamp = time.strftime("%Y%m%dT%H%M%SZ")
    report_path = r_dir / f"eval_{model_clean}_{timestamp}.json"

    data = {
        "status": "PASS",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha or "HEAD",
        **eval_result,
    }

    report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return report_path


def format_markdown_summary(reports: List[Dict[str, Any]]) -> str:
    """Generate Markdown summary table across evaluated models."""
    lines = [
        "# GameForge Model Evaluation Summary",
        "",
        "| Model | Provider | Pass Rate (%) | Valid JSON (%) | First Try (%) | p90 Latency (s) | Speed (tok/s) |",
        "|---|---|---|---|---|---|---|",
    ]

    for rep in reports:
        model_id = rep.get("model_id", "unknown")
        provider = rep.get("provider_kind", "unknown")
        ov = rep.get("overall", {})
        pass_rate = ov.get("pass_rate", 0.0)
        valid_json = ov.get("valid_json_rate", 0.0)
        first_try = ov.get("first_try_valid_rate", 0.0)
        p90 = ov.get("p90_latency_s", 0.0)
        speed = ov.get("mean_tok_per_sec", 0.0)

        lines.append(
            f"| `{model_id}` | {provider} | **{pass_rate:.1f}%** | {valid_json:.1f}% | {first_try:.1f}% | {p90:.2f}s | {speed:.1f} |"
        )

    lines.append("")
    return "\n".join(lines)
