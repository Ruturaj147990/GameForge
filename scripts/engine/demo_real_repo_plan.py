"""Demonstration B: Real Repository Task Multi-Step Planner.

Demonstrates:
1. Inspecting real repository files.
2. Formulating a valid dependency plan (DAG).
3. Applying a real non-destructive modification with approval gating.
4. Executing real unit tests (pytest).
5. Evaluating machine-checkable acceptance criteria over real state.
6. Reverting cleanly to preserve working tree integrity.

Usage:
    python scripts/engine/demo_real_repo_plan.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.gameforge_ide.backend.agent.plan_executor import PlanEvent, TaskPlanExecutor
from src.gameforge_ide.backend.agent.task_plan import TaskNode, TaskPlan
from src.gameforge_ide.backend.agent.task_state import TaskAcceptancePredicate
from src.gameforge_ide.backend.tools.gateway import ToolGateway


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--forge", action="store_true", help="Run with Forge executor")
    args = ap.parse_args()
    target_rel = "src/gameforge_ide/backend/agent/task_plan.py"
    target_abs = ROOT / target_rel

    if not target_abs.is_file():
        print(f"[DEMO B] BLOCKED: Target file not found: {target_abs}")
        return 2

    print(f"[DEMO B] Target Repository File: {target_rel}")
    original_text = target_abs.read_text(encoding="utf-8")

    marker_comment = f"# [GameForge Milestone 1 Verified - {int(time.time())}]\n"
    first_line = original_text.splitlines(keepends=True)[0]
    target_header = first_line
    replacement_header = f"{first_line}{marker_comment}"

    events_log = []
    def log_event(ev: PlanEvent):
        msg = f"[{ev.timestamp:.2f}] {ev.event_type} | task={ev.task_id} | status={ev.status} | {ev.message}"
        print(f"  -> {msg}")
        events_log.append(ev.model_dump())

    gateway = ToolGateway(ROOT)
    executor = TaskPlanExecutor(ROOT, tool_gateway=gateway, on_event=log_event)

    # Construct DAG plan for repo task
    plan = TaskPlan(
        goal="Apply non-destructive verification marker, run test suite, and verify acceptance",
        metadata={"target_file": target_rel, "demonstration": "B"},
    )

    # Task 1: Inspect target file
    t1 = TaskNode(
        task_id="t1_inspect",
        title=f"Inspect {target_rel}",
        objective=f"Verify {target_rel} exists on disk and is readable",
        expected_result="File existence and size confirmed",
        task_type="inspect",
        permitted_tools=["read_file"],
        dependency_ids=[],
        reversibility="read-only",
        tool_call={"name": "read_file", "arguments": {"subpath": target_rel}},
        acceptance=[
            TaskAcceptancePredicate(predicate_type="file_exists", target=target_rel),
        ],
    )

    # Task 2: Propose and apply modification
    t2 = TaskNode(
        task_id="t2_apply_change",
        title=f"Add verified milestone marker to {target_rel}",
        objective="Insert verification marker comment into module docstring",
        expected_result="File modified on disk with new marker",
        task_type="mutate",
        permitted_tools=["propose_edit", "apply_edit"],
        dependency_ids=["t1_inspect"],
        reversibility="transactional",
        requires_approval=True,
        tool_call={
            "name": "propose_edit",
            "arguments": {
                "subpath": target_rel,
                "target_content": target_header,
                "replacement_content": replacement_header,
            },
        },
        acceptance=[
            TaskAcceptancePredicate(predicate_type="file_changed", target=target_rel),
            TaskAcceptancePredicate(predicate_type="file_content_contains", target=target_rel, expected=marker_comment.strip()),
        ],
    )

    # Task 3: Execute real unit tests
    test_cmd = f"python -m pytest tests/unit/test_task_plan.py -q"
    t3 = TaskNode(
        task_id="t3_run_tests",
        title="Execute test suite on modified codebase",
        objective="Run pytest test_task_plan.py to verify 100% pass with exit code 0",
        expected_result="Tests pass with exit code 0",
        task_type="test",
        permitted_tools=["run_command"],
        dependency_ids=["t2_apply_change"],
        reversibility="read-only",
        tool_call={"name": "run_command", "arguments": {"command": test_cmd}},
        acceptance=[
            TaskAcceptancePredicate(predicate_type="command_exit_code", target=test_cmd, expected=0),
        ],
    )

    plan.add_task(t1)
    plan.add_task(t2)
    plan.add_task(t3)
    plan.final_acceptance = [
        TaskAcceptancePredicate(predicate_type="file_changed", target=target_rel),
        TaskAcceptancePredicate(predicate_type="command_exit_code", target=test_cmd, expected=0),
    ]

    valid, errs = plan.validate()
    print(f"[DEMO B] DAG Validation: valid={valid}, errors={errs}")
    if not valid:
        print(f"[DEMO B] FAILED: Invalid DAG: {errs}")
        return 1

    t0 = time.time()
    try:
        # Run plan
        if args.forge:
            from src.gameforge_ide.forge.plan_adapter import run_plan_on_forge
            result_plan = run_plan_on_forge(plan, ROOT, auto_approve_all=True, on_event=log_event)
        else:
            result_plan = executor.run_plan(plan, auto_approve_all=True)
    finally:
        # Always restore original content to preserve clean working tree
        target_abs.write_text(original_text, encoding="utf-8")
        print("[DEMO B] Working tree restored to original state.")

    elapsed = time.time() - t0
    print(f"[DEMO B] Execution completed in {elapsed:.2f}s with status: {result_plan.status}")

    all_ok = result_plan.status == "COMPLETED"
    report = {
        "demonstration": "Demonstration B: Real Repository Task",
        "target_file": target_rel,
        "elapsed_seconds": round(elapsed, 2),
        "status": result_plan.status,
        "all_tasks_completed": all(t.status == "COMPLETED" for t in result_plan.tasks.values()),
        "tasks": {
            tid: {
                "title": t.title,
                "status": t.status,
                "error": t.error_message,
                "acceptance": [p.model_dump() for p in t.acceptance],
                "evidence_count": len(t.evidence),
            }
            for tid, t in result_plan.tasks.items()
        },
        "events": events_log,
    }

    out_file = ROOT / "reports" / "milestone1_repo_demo.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[DEMO B] Report saved to {out_file}")

    for tid, tinfo in report["tasks"].items():
        print(f"  * {tid}: {tinfo['status']} (acceptance: {[p['satisfied'] for p in tinfo['acceptance']]})")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
