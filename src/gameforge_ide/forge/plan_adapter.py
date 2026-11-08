"""plan_adapter: Bidirectional translation between TaskPlan DAG and Forge RunSpec/RunState (AD-11)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from ..backend.agent.plan_executor import PlanEvent
from ..backend.agent.task_plan import TaskNode, TaskPlan
from ..backend.tools.game_tools import READ_ONLY_EDITOR_OPS
from ..core.events import EventBus, default_bus
from .executor import ForgeExecutor
from .handlers import HANDLERS
from .model import RunSpec, RunState, StepKind, StepRecord, StepSpec, StepStatus
from .store import RunStore



# Tools whose effects are irreversible or leave the workspace: a plan step that uses them is
# always routed through the executor's per-step user approval, whatever the plan declared.
_APPROVAL_GATED_TOOLS = {"run_command", "delete_file", "unreal_package", "play_game", "create_game"}


def _tool_is_approval_gated(tool_name: str, tool_args: dict) -> bool:
    if not tool_name:
        return False
    if tool_name in _APPROVAL_GATED_TOOLS:
        return True
    if tool_name == "unreal_editor":
        return (tool_args or {}).get("op", "") not in READ_ONLY_EDITOR_OPS
    return False

def plan_to_run(plan: TaskPlan, workspace: Union[Path, str]) -> RunSpec:
    """Translate a TaskPlan into a Forge RunSpec."""
    ws = Path(workspace).resolve()
    steps: List[StepSpec] = []

    for task_id, task in plan.tasks.items():
        tool_name = task.tool_call.get("name", "") if task.tool_call else ""
        tool_args = task.tool_call.get("arguments", {}) if task.tool_call else {}
        op = tool_args.get("op", "") if tool_name == "unreal_editor" else ""
        is_readonly_op = op in READ_ONLY_EDITOR_OPS

        inputs = {
            "tool": tool_name,
            "arguments": tool_args,
            "acceptance": [p.model_dump() for p in task.acceptance],
            "permitted_tools": list(task.permitted_tools),
            "repetition_limit": 3,
            "task_type": task.task_type,
            "task_id": task.task_id,
        }

        step = StepSpec(
            step_id=task.task_id,
            kind=StepKind.TOOL_CALL,
            title=task.title,
            depends_on=list(task.dependency_ids),
            inputs=inputs,
            approval="step" if (task.requires_approval or _tool_is_approval_gated(tool_name, tool_args)) else "none",
            engine_lock=(tool_name == "unreal_editor" and not is_readonly_op),
            timeout_s=float(task.timeout_seconds),
            max_attempts=max(1, int(task.retry_limit) + 1),
            checkpoint=False,
        )
        steps.append(step)

    project_dir = ws if (ws / f"{ws.name}.uproject").exists() else None
    return RunSpec(
        run_id=plan.plan_id,
        title=plan.goal,
        project_dir=str(project_dir) if project_dir else None,
        workspace_dir=str(ws),
        steps=steps,
        created_at=plan.created_at,
    )


def run_state_to_task_plan(state: RunState, plan: TaskPlan) -> TaskPlan:
    """Reflect Forge RunState back into TaskPlan node statuses and evidence."""
    for task_id, task in plan.tasks.items():
        rec = state.records.get(task_id)
        if rec is None:
            continue
        if rec.status == StepStatus.DONE:
            task.status = "COMPLETED"
        elif rec.status == StepStatus.FAILED:
            task.status = "FAILED"
        elif rec.status == StepStatus.BLOCKED:
            task.status = "BLOCKED"
        elif rec.status == StepStatus.CANCELLED:
            task.status = "CANCELLED"
        elif rec.status == StepStatus.WAITING_APPROVAL:
            task.status = "WAITING_APPROVAL"
        elif rec.status == StepStatus.RUNNING:
            task.status = "RUNNING"
        else:
            task.status = "PLANNED"

        if rec.errors:
            task.error_message = "; ".join(rec.errors)

        if rec.data:
            if "acceptance" in rec.data and rec.data["acceptance"]:
                from ..backend.agent.task_state import TaskAcceptancePredicate
                task.acceptance = [TaskAcceptancePredicate.model_validate(p) for p in rec.data["acceptance"]]
            ev = {
                "timestamp": rec.finished_at or time.time(),
                "attempt": rec.attempts,
                "tool_call": task.tool_call,
                "output": rec.data.get("output"),
                "error": task.error_message,
            }
            task.evidence.append(ev)

    if all(t.status == "COMPLETED" for t in plan.tasks.values()):
        plan.status = "COMPLETED"
    elif any(t.status == "CANCELLED" for t in plan.tasks.values()) or state.status == "CANCELLED":
        plan.status = "CANCELLED"
    elif any(t.status == "WAITING_APPROVAL" for t in plan.tasks.values()) or state.status == "WAITING_APPROVAL":
        plan.status = "WAITING_APPROVAL"
    elif any(t.status == "FAILED" for t in plan.tasks.values()) or state.status == "FAILED":
        plan.status = "FAILED"
    elif any(t.status == "BLOCKED" for t in plan.tasks.values()) or state.status == "BLOCKED":
        plan.status = "BLOCKED"
    else:
        plan.status = "RUNNING"

    plan.updated_at = time.time()
    return plan


def run_plan_on_forge(
    plan: TaskPlan,
    workspace_root: Union[Path, str],
    auto_approve_all: bool = False,
    bus: Optional[EventBus] = None,
    on_event: Optional[Callable[[PlanEvent], None]] = None,
) -> TaskPlan:
    """Execute a TaskPlan using the Forge executor and update the plan state."""
    from ..backend.tools.game_tools import ApprovalStore

    ws = Path(workspace_root).resolve()
    app_store = ApprovalStore(ws)
    run_spec = plan_to_run(plan, ws)
    store = RunStore(project_dir=Path(run_spec.project_dir) if run_spec.project_dir else None, workspace_dir=ws)
    state = RunState.new(run_spec)

    # Check existing approvals in ApprovalStore
    for task_id, task in plan.tasks.items():
        if task.approval_id:
            rec = app_store.get(task.approval_id)
            if rec and rec.get("status") == "APPROVED":
                state.approvals[task_id] = task.approval_id
            elif rec and rec.get("status") == "REJECTED":
                if task_id in state.records:
                    state.records[task_id].status = StepStatus.CANCELLED

    if auto_approve_all:
        state.approvals["run"] = "auto_approved"
        for s in run_spec.steps:
            state.approvals[s.step_id] = f"auto_{s.step_id}"

    event_bus = bus or default_bus()

    def _bus_listener(topic: str, ev: Dict[str, Any]) -> None:
        if on_event is None:
            return
        kind = ev.get("kind")
        sid = ev.get("step_id")
        t = plan.tasks.get(sid) if sid else None
        title = t.title if t else ""

        if kind == "step_started":
            on_event(
                PlanEvent(
                    event_type="task_started",
                    plan_id=plan.plan_id,
                    task_id=sid,
                    status="RUNNING",
                    message=f"Starting task '{title}'",
                )
            )
        elif kind == "step_finished":
            ok = ev.get("ok", False)
            st = "COMPLETED" if ok else ev.get("status", "FAILED")
            ev_type = "task_completed" if ok else ("task_blocked" if st == "BLOCKED" else "task_failed")
            on_event(
                PlanEvent(
                    event_type=ev_type,
                    plan_id=plan.plan_id,
                    task_id=sid,
                    status=st,
                    message=f"Task '{title}' {st}",
                )
            )
        elif kind == "approval_needed":
            key = ev.get("key")
            on_event(
                PlanEvent(
                    event_type="task_waiting_approval",
                    plan_id=plan.plan_id,
                    task_id=key,
                    status="WAITING_APPROVAL",
                    message=f"Task '{key}' awaiting approval",
                )
            )

    unsub = event_bus.subscribe("forge", _bus_listener)
    try:
        if on_event:
            on_event(PlanEvent(event_type="plan_started", plan_id=plan.plan_id, status="RUNNING", message="Plan started"))
        executor = ForgeExecutor(HANDLERS, bus=event_bus)
        state = executor.run(state, store)
    finally:
        unsub()

    result_plan = run_state_to_task_plan(state, plan)

    # If any task is WAITING_APPROVAL, ensure it has an approval_id in ApprovalStore
    for task_id, task in result_plan.tasks.items():
        if task.status == "WAITING_APPROVAL" and not task.approval_id:
            rec = app_store.create(
                tool=task.tool_call.get("name", "task_execution") if task.tool_call else "task_execution",
                args=task.tool_call.get("arguments", {}) if task.tool_call else {"task_id": task.task_id},
                summary=task.title,
                consequence=f"Execution of task '{task.objective}'",
                session_id=plan.session_id,
                plan_id=plan.plan_id,
            )
            task.approval_id = rec["approval_id"]

    result_plan.save(ws)

    if on_event:
        final_ev = "plan_completed" if result_plan.status == "COMPLETED" else f"plan_{result_plan.status.lower()}"
        on_event(PlanEvent(event_type=final_ev, plan_id=plan.plan_id, status=result_plan.status, message=f"Plan {result_plan.status}"))

    return result_plan
