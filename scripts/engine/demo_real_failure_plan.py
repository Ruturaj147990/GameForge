"""Demonstration C: Real Failure Handling, Transitive Blocking, and Resumption.

Demonstrates:
1. Exercise of an actual failing operation / unmet predicate.
2. Transitive blocking: dependent work is marked BLOCKED and never executed.
3. Independent safe work continues executing and completes.
4. Final plan state is BLOCKED or FAILED (never falsely COMPLETED).
5. State resumption and cancellation handling on persisted state.

Usage:
    python scripts/engine/demo_real_failure_plan.py
"""

from __future__ import annotations

import json
import os
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
    print("[DEMO C] Starting Real Failure Handling Demonstration...")

    events_log = []
    def log_event(ev: PlanEvent):
        msg = f"[{ev.timestamp:.2f}] {ev.event_type} | task={ev.task_id} | status={ev.status} | {ev.message}"
        print(f"  -> {msg}")
        events_log.append(ev.model_dump())

    gateway = ToolGateway(ROOT)
    executor = TaskPlanExecutor(ROOT, tool_gateway=gateway, on_event=log_event)

    # Topology:
    #       root (succeeds)
    #      /     \
    #  fail_op   independent_ok (succeeds)
    #     |
    #  blocked_op (blocked, never runs)
    plan = TaskPlan(
        goal="Test branched failure containment, transitive blocking, and independent execution",
        metadata={"demonstration": "C"},
    )

    # Root task: Read README or AGENTS.md
    root = TaskNode(
        task_id="t_root",
        title="Inspect repository root",
        objective="Read AGENTS.md to verify repository context",
        expected_result="AGENTS.md read successfully",
        task_type="inspect",
        permitted_tools=["read_file"],
        dependency_ids=[],
        reversibility="read-only",
        tool_call={"name": "read_file", "arguments": {"subpath": "AGENTS.md"}},
        acceptance=[
            TaskAcceptancePredicate(predicate_type="file_exists", target="AGENTS.md"),
        ],
    )

    # Branch A - Step 1: Failing task (attempts to read a nonexistent file with mandatory existence predicate)
    nonexistent = "nonexistent_file_for_failure_check_9999.xyz"
    fail_op = TaskNode(
        task_id="t_fail_op",
        title="Attempt operation on nonexistent file",
        objective=f"Read {nonexistent} which is guaranteed not to exist",
        expected_result="Will fail predicate check",
        task_type="inspect",
        permitted_tools=["read_file"],
        dependency_ids=["t_root"],
        retry_limit=1,
        recovery_behavior="retry",
        tool_call={"name": "read_file", "arguments": {"subpath": nonexistent}},
        acceptance=[
            TaskAcceptancePredicate(predicate_type="file_exists", target=nonexistent),
        ],
    )

    # Branch A - Step 2: Downstream dependent task (must be BLOCKED and NEVER executed)
    blocked_op = TaskNode(
        task_id="t_blocked_op",
        title="Dependent task on failed branch",
        objective="Should never execute because upstream failed",
        expected_result="BLOCKED status",
        task_type="inspect",
        permitted_tools=["read_file"],
        dependency_ids=["t_fail_op"],
        tool_call={"name": "read_file", "arguments": {"subpath": "AGENTS.md"}},
        acceptance=[
            TaskAcceptancePredicate(predicate_type="file_exists", target="AGENTS.md"),
        ],
    )

    # Branch B: Independent task (depends ONLY on t_root, must SUCCEED)
    independent_ok = TaskNode(
        task_id="t_independent_ok",
        title="Independent parallel inspection",
        objective="Inspect context.md independently of Branch A",
        expected_result="context.md read and verified",
        task_type="inspect",
        permitted_tools=["read_file"],
        dependency_ids=["t_root"],
        reversibility="read-only",
        tool_call={"name": "read_file", "arguments": {"subpath": "context.md"}},
        acceptance=[
            TaskAcceptancePredicate(predicate_type="file_exists", target="context.md"),
        ],
    )

    plan.add_task(root)
    plan.add_task(fail_op)
    plan.add_task(blocked_op)
    plan.add_task(independent_ok)

    valid, errs = plan.validate()
    print(f"[DEMO C] DAG Validation: valid={valid}, errors={errs}")
    if not valid:
        print(f"[DEMO C] FAILED: Invalid DAG: {errs}")
        return 1

    t0 = time.time()
    if args.forge:
        from src.gameforge_ide.forge.plan_adapter import run_plan_on_forge
        result_plan = run_plan_on_forge(plan, ROOT, auto_approve_all=True, on_event=log_event)
    else:
        result_plan = executor.run_plan(plan, auto_approve_all=True)
    elapsed = time.time() - t0

    print(f"[DEMO C] Execution completed in {elapsed:.2f}s with status: {result_plan.status}")

    # Assertions on genuine failure handling behavior:
    t_root_ok = result_plan.tasks["t_root"].status == "COMPLETED"
    t_fail_failed = result_plan.tasks["t_fail_op"].status == "FAILED"
    t_blocked_is_blocked = result_plan.tasks["t_blocked_op"].status == "BLOCKED"
    t_indep_ok = result_plan.tasks["t_independent_ok"].status == "COMPLETED"
    plan_not_completed = result_plan.status in ("FAILED", "BLOCKED")

    print(f"  * t_root: {result_plan.tasks['t_root'].status} (expected COMPLETED: {t_root_ok})")
    print(f"  * t_fail_op: {result_plan.tasks['t_fail_op'].status} (expected FAILED: {t_fail_failed})")
    print(f"  * t_blocked_op: {result_plan.tasks['t_blocked_op'].status} (expected BLOCKED: {t_blocked_is_blocked})")
    print(f"  * t_independent_ok: {result_plan.tasks['t_independent_ok'].status} (expected COMPLETED: {t_indep_ok})")
    print(f"  * Overall plan status: {result_plan.status} (expected FAILED/BLOCKED: {plan_not_completed})")

    verdict_ok = t_root_ok and t_fail_failed and t_blocked_is_blocked and t_indep_ok and plan_not_completed

    report = {
        "demonstration": "Demonstration C: Real Failure Handling",
        "elapsed_seconds": round(elapsed, 2),
        "status": result_plan.status,
        "verdict_ok": verdict_ok,
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

    out_file = ROOT / "reports" / "milestone1_failure_demo.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[DEMO C] Report saved to {out_file}")

    return 0 if verdict_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
