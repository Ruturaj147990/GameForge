"""Forge Handlers Registry and Handler Contract.

Handler Contract (AD-11):
1. Idempotent: a handler may be re-run after a crash, so it must not fail just because its output already exists.
2. Cancellable: poll ctx.cancel at least every 2 s in loops, and pass it to the toolchain (toolchain.cancel_event).
3. Fail closed: return StepOutcome(False, ...). Never raise for expected failures.
4. Evidence: artifacts are paths inside the project's Saved/GameForge/evidence/ or the run dir.
5. Use blocked=True for environment problems (engine missing, VRAM scheduler refusal, approval revoked).
"""
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Dict
from ..executor import Handler, StepContext, StepOutcome
from . import legacy_stages
from . import tool_call
from . import scenario
from . import content
from . import review


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
    return StepOutcome(True, data={"report_path": str(report_file)}, artifacts=artifacts)


HANDLERS: Dict[str, Handler] = {
    # Named stages
    "spec": legacy_stages.legacy_spec,
    "scaffold": legacy_stages.legacy_scaffold,
    "sources": legacy_stages.legacy_sources,
    "build_editor": legacy_stages.legacy_build,
    "assemble_level": legacy_stages.legacy_assemble,
    "automation_tests": legacy_stages.legacy_tests,
    "package": legacy_stages.legacy_package,
    "packaged_smoke": legacy_stages.legacy_smoke,
    "report": report_handler,
    # StepKind enums
    "design": legacy_stages.legacy_spec,
    "codegen": legacy_stages.legacy_sources,
    "build": legacy_stages.legacy_build,
    "content": content.content_handler,
    "assemble": legacy_stages.legacy_assemble,
    "automation": legacy_stages.legacy_tests,
    "scenario": scenario.scenario_handler,
    "review": review.review_handler,
    "tool_call": tool_call.tool_call_handler,
}


def register_handler(kind: str, handler: Handler) -> None:
    HANDLERS[kind] = handler
