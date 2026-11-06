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
from .report import report_handler
from .scaffold import scaffold_handler


HANDLERS: Dict[str, Handler] = {
    # Named stages
    "spec": legacy_stages.legacy_spec,
    "scaffold": scaffold_handler,
    "sources": legacy_stages.legacy_sources,
    "build_editor": legacy_stages.legacy_build,
    "assemble_level": legacy_stages.legacy_assemble,
    "assemble_level_1": legacy_stages.legacy_assemble,
    "scenario_gen": scenario.scenario_gen_handler,
    "automation_tests": legacy_stages.legacy_tests,
    "package": legacy_stages.legacy_package,
    "scenarios": scenario.scenario_handler,
    "packaged_smoke": legacy_stages.legacy_smoke,
    "report": report_handler,
    # StepKind enums
    "design": legacy_stages.legacy_spec,
    "scaffold": scaffold_handler,
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
