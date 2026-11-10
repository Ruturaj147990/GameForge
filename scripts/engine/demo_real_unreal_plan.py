"""Demonstration A: Real Unreal Workflow Multi-Step DAG Planner (UE 5.7.4).

Demonstrates:
1. Inspecting real project and editor identity.
2. Capturing relevant state.
3. Producing a valid multi-step dependency plan (DAG).
4. Performing a real supported Unreal mutation through real editor transport.
5. Reading back the actual resulting state.
6. Running a genuine final acceptance check.
7. Recording the result and evidence.

Usage:
    python scripts/engine/demo_real_unreal_plan.py [path/to/Probe.uproject]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gameforge_ide.backend.agent.plan_executor import PlanEvent, TaskPlanExecutor
from src.gameforge_ide.backend.agent.plan_generator import PlanGenerator
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.core.settings import get_settings


def _default_probe_project() -> str:
    try:
        return str(get_settings().require_dev("probe_project"))
    except Exception:
        try:
            val_root = get_settings().require_dev("validation_root")
        except Exception:
            val_root = ROOT / "scratch" / "validation"
        return str(val_root / "live_ops_probe" / "GFProbe.uproject")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("uproject", nargs="?", default=None)
    ap.add_argument("--forge", action="store_true", help="Run with Forge executor")
    args = ap.parse_args()

    uproject_str = args.uproject or _default_probe_project()
    uproject = Path(uproject_str)

    if not uproject.is_file():
        print(f"[DEMO A] BLOCKED: Unreal project not found at {uproject}")
        return 2

    print(f"[DEMO A] Target Unreal Project: {uproject}")

    events_log: List[Dict[str, Any]] = []

    def log_event(ev: PlanEvent) -> None:
        msg = f"[{ev.timestamp:.2f}] {ev.event_type} | task={ev.task_id} | status={ev.status} | {ev.message}"
        print(f"  -> {msg}")
        events_log.append(ev.model_dump())

    gateway = ToolGateway(ROOT)
    from src.gameforge_ide.forge.handlers.tool_call import _GATEWAY_CACHE
    _GATEWAY_CACHE[ROOT.resolve()] = gateway
    generator = PlanGenerator(ROOT, tool_gateway=gateway)
    executor = TaskPlanExecutor(ROOT, tool_gateway=gateway, on_event=log_event)

    actor_label = f"GF_M1_Actor_{int(time.time()) % 10000}"
    print(f"[DEMO A] Formulating plan to spawn and verify actor '{actor_label}'...")

    plan = generator.generate_unreal_mutation_plan(
        goal=f"Spawn marker actor '{actor_label}' in active level and verify editor state",
        uproject_path=str(uproject),
        actor_label=actor_label,
        location={"x": 200.0, "y": 100.0, "z": 50.0},
        static_mesh="/Engine/BasicShapes/Cube.Cube",
    )

    valid, errs = plan.validate()
    print(f"[DEMO A] DAG Validation: valid={valid}, errors={errs}")
    if not valid:
        print(f"[DEMO A] FAILED: Invalid DAG: {errs}")
        return 1

    print(f"[DEMO A] Topological Order: {plan.get_topological_order()}")

    t0 = time.monotonic()
    result_plan = plan
    try:
        # Run plan with approval granted for this demo run
        if args.forge:
            from src.gameforge_ide.forge.plan_adapter import run_plan_on_forge
            result_plan = run_plan_on_forge(plan, ROOT, auto_approve_all=True, on_event=log_event)
        else:
            result_plan = executor.run_plan(plan, auto_approve_all=True)
    finally:
        # Cleanly stop editors to avoid lingering background processes
        gateway.game_tools.close_editors()

    elapsed = time.monotonic() - t0
    print(f"[DEMO A] Execution completed in {elapsed:.2f}s with status: {result_plan.status}")

    # Inspect results
    all_ok = result_plan.status == "COMPLETED"
    report = {
        "demonstration": "Demonstration A: Real Unreal Workflow",
        "uproject": str(uproject),
        "actor_label": actor_label,
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

    out_file = ROOT / "reports" / "milestone1_unreal_demo.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_file.with_suffix(".tmp")
    tmp_out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    os.replace(tmp_out, out_file)
    print(f"[DEMO A] Report saved to {out_file}")

    for tid, tinfo in report["tasks"].items():
        print(f"  * {tid}: {tinfo['status']} (acceptance: {[p['satisfied'] for p in tinfo['acceptance']]})")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
