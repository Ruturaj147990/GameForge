"""Forge step handler for pipeline report generation (AD-11)."""
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Dict, Any

from ..executor import StepContext, StepOutcome
from ..validation import validate_stage_output


def report_handler(ctx: StepContext) -> StepOutcome:
    """Compile final build and test evidence report (pipeline_report.json and .md)."""
    pdir = Path(ctx.project_dir) if ctx.project_dir else Path(ctx.workspace_dir)
    evidence_dir = pdir / "Saved" / "GameForge"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_file = evidence_dir / "pipeline_report.json"
    md_file = evidence_dir / "pipeline_report.md"

    report_payload = {
        "run_id": ctx.run.run_id,
        "title": ctx.run.title,
        "project_dir": str(pdir),
        "steps_completed": len(ctx.shared),
        "stages": [{"stage": sid, "data": data} for sid, data in ctx.shared.items()],
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    report_file.write_text(json.dumps(report_payload, indent=2, default=str), encoding="utf-8")

    md_lines = [
        f"# Build & Test Report: {ctx.run.title}",
        f"- Run ID: `{ctx.run.run_id}`",
        f"- Project: `{pdir.name}`",
        f"- Date: {report_payload['finished']}",
        "\n## Completed Stages:",
    ]
    for sid in ctx.shared.keys():
        md_lines.append(f"- **{sid}**: OK")
    md_file.write_text("\n".join(md_lines), encoding="utf-8")

    ctx.log(f"Final pipeline report written to {report_file}")
    artifacts = [
        {"path": str(report_file), "kind": "report"},
        {"path": str(md_file), "kind": "report"},
    ]
    outcome_data = {"report_path": str(report_file)}
    valid, issues = validate_stage_output("report", outcome_data, project_dir=pdir)
    if not valid:
        return StepOutcome(False, data=outcome_data, errors=issues, artifacts=artifacts)

    return StepOutcome(True, data=outcome_data, artifacts=artifacts)
