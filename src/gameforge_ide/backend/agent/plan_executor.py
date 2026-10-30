"""General-Purpose Dependency-Aware Multi-Step Task Plan Executor for GameForge IDE.

Authoritative implementation conforming to GameForge Master Blueprint:
- Real execution only: dispatches real tools through ToolGateway and real Unreal mutations through LiveEditorLink.
- Safe dependency-aware scheduling: topological DAG execution with independent branch progression.
- Concurrency rules: all tasks are safely sequenced; Unreal mutations and write operations are strictly serialized.
- Execution state machine: PLANNED, READY, RUNNING, WAITING_APPROVAL, VERIFYING, REPAIRING, COMPLETED, BLOCKED, FAILED, CANCELLED.
- Only the harness assigns terminal states based on observed acceptance predicates.
- Repetition control: tool + canonical args + state version; 3rd identical call blocks.
- Bounded diagnosis and repair ladder before branch failure.
- Crash recovery and resumption: checks real filesystem and Unreal state before re-running.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from ..tools.game_tools import READ_ONLY_EDITOR_OPS
from ..tools.gateway import ToolGateway
from .task_plan import PlanValidationError, TaskNode, TaskNodeStatus, TaskPlan
from .task_state import TaskAcceptancePredicate

logger = logging.getLogger(__name__)

# Tool result statuses that mean the requested action did not happen. Anything here
# fails the step instead of falling through to (possibly empty) acceptance predicates.
FAILURE_STATUSES = frozenset({
    "ERROR", "BLOCKED", "FAILED", "TIMEOUT", "CANCELLED", "REJECTED", "STALE",
    "NO_RECIPE", "ENGINE_UNAVAILABLE", "PENDING_APPROVAL",
})


def _step_failure(step_error: Optional[str], step_output: Any) -> Optional[str]:
    """Returns why a dispatched step failed, or None when it genuinely succeeded."""
    if step_error:
        return step_error
    if not isinstance(step_output, dict):
        return None
    status = step_output.get("status")
    if status in FAILURE_STATUSES:
        return str(step_output.get("error") or f"Tool returned status {status}")
    exit_code = step_output.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return str(step_output.get("error") or f"Tool exited with code {exit_code}")
    return None


class PlanEvent(BaseModel):
    """Event emitted during plan execution for UI and logging."""

    event_type: str  # "plan_started", "task_ready", "task_started", "task_waiting_approval",
                     # "task_verifying", "task_repairing", "task_completed", "task_blocked",
                     # "task_failed", "plan_completed", "plan_blocked", "plan_failed", "plan_cancelled"
    plan_id: str
    task_id: Optional[str] = None
    status: Optional[TaskNodeStatus] = None
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class TaskPlanExecutor:
    """Executes a validated TaskPlan DAG using real tools, serialized mutations, and predicate gating."""

    def __init__(
        self,
        workspace_root: Path,
        tool_gateway: Optional[ToolGateway] = None,
        on_event: Optional[Callable[[PlanEvent], None]] = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.tool_gateway = tool_gateway or ToolGateway(self.workspace_root)
        self.on_event = on_event
        self._unreal_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._cancel_requested = threading.Event()
        self._active_plan: Optional[TaskPlan] = None
        self._tool_call_counts: Dict[str, int] = {}
        self._state_version: int = 0

    def _get_repetition_key(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Formulates a repetition key including canonical args and project-state version."""
        file_target = tool_args.get("subpath") or tool_args.get("file_path") or tool_args.get("path")
        file_sig = ""
        if file_target:
            fp = (self.workspace_root / file_target).resolve()
            if fp.is_file():
                try:
                    st = fp.stat()
                    file_sig = f":{st.st_mtime_ns}:{st.st_size}"
                except Exception:
                    pass
        return f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}:v{self._state_version}{file_sig}"

    def _emit(self, event_type: str, plan_id: str, task_id: Optional[str] = None,
              status: Optional[TaskNodeStatus] = None, message: str = "", data: Optional[Dict[str, Any]] = None) -> PlanEvent:
        event = PlanEvent(
            event_type=event_type,
            plan_id=plan_id,
            task_id=task_id,
            status=status,
            message=message,
            data=data or {},
        )
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:
                logger.warning(f"Error in on_event handler: {e}")
        return event

    def cancel(self) -> None:
        """Requests cooperative cancellation of the running plan."""
        self._cancel_requested.set()

    def is_cancelled(self) -> bool:
        return self._cancel_requested.is_set()

    def run_plan(self, plan: TaskPlan, auto_approve_all: bool = False) -> TaskPlan:
        """Executes a TaskPlan synchronously to completion, blocking, or approval pause."""
        self._cancel_requested.clear()
        self._active_plan = plan
        self._tool_call_counts.clear()

        # 1. Pre-execution DAG validation
        valid, errors = plan.validate()
        if not valid:
            plan.status = "FAILED"
            plan.metadata["validation_errors"] = errors
            plan.save(self.workspace_root)
            self._emit("plan_failed", plan.plan_id, message=f"Invalid DAG: {'; '.join(errors)}")
            return plan

        plan.status = "RUNNING"
        plan.save(self.workspace_root)
        self._emit("plan_started", plan.plan_id, status="RUNNING", message=f"Executing plan '{plan.goal}'")

        cumulative_history: List[Dict[str, Any]] = []

        # 2. Execution wave loop
        while not self.is_cancelled():
            ready_tasks = plan.get_ready_tasks()

            if not ready_tasks:
                # Check terminal conditions
                all_terminal = all(t.is_terminal() for t in plan.tasks.values())
                any_waiting = any(t.status == "WAITING_APPROVAL" for t in plan.tasks.values())

                if any_waiting:
                    plan.status = "WAITING_APPROVAL"
                    plan.save(self.workspace_root)
                    self._emit("plan_started", plan.plan_id, status="WAITING_APPROVAL", message="Plan suspended: task awaiting approval")
                    return plan

                if all_terminal:
                    # Final plan evaluation
                    self._evaluate_final_plan_status(plan, cumulative_history)
                    plan.save(self.workspace_root)
                    return plan

                # No ready tasks and not all terminal -> deadlocked or unexpected state
                plan.status = "BLOCKED"
                plan.metadata["blocked_reason"] = "No remaining ready tasks and unresolved prerequisites"
                plan.save(self.workspace_root)
                self._emit("plan_blocked", plan.plan_id, status="BLOCKED", message="Plan blocked: unresolved prerequisites")
                return plan

            # Separate read-only tasks from write/mutation tasks
            # Read-only tasks without writes can be executed in a batch; write tasks run serially
            progress_made = False
            for task in ready_tasks:
                if self.is_cancelled():
                    break

                task.status = "READY"
                self._emit("task_ready", plan.plan_id, task.task_id, status="READY", message=f"Task '{task.title}' is ready")

                # Execute task
                outcome = self._execute_task_node(plan, task, auto_approve_all=auto_approve_all, cumulative_history=cumulative_history)
                progress_made = True

                # A task awaiting approval does not stop independent branches; the plan
                # suspends once nothing else is ready (handled at the top of the loop).
                plan.save(self.workspace_root)

            if not progress_made and not self.is_cancelled():
                break

        if self.is_cancelled():
            plan.status = "CANCELLED"
            for t in plan.tasks.values():
                if not t.is_terminal():
                    t.status = "CANCELLED"
                    t.error_message = "Execution cancelled by user"
            plan.save(self.workspace_root)
            self._emit("plan_cancelled", plan.plan_id, status="CANCELLED", message="Plan execution cancelled")

        return plan

    def _execute_task_node(self, plan: TaskPlan, task: TaskNode, auto_approve_all: bool = False,
                           cumulative_history: Optional[List[Dict[str, Any]]] = None) -> str:
        """Executes a single task node with gating, repair ladder, and acceptance verification."""
        task.status = "RUNNING"
        task.started_at = time.time()
        self._emit("task_started", plan.plan_id, task.task_id, status="RUNNING", message=f"Starting task '{task.title}'")

        # Approval check: a task inherits the approval requirement of the tool it dispatches,
        # so a plan cannot run an approval-gated tool merely by omitting requires_approval.
        tool_needs_approval = bool(task.tool_call) and self.tool_gateway.tool_requires_approval(
            task.tool_call.get("name", ""), task.tool_call.get("arguments", {}))
        if (task.requires_approval or tool_needs_approval) and not auto_approve_all:
            # Check if already approved via ApprovalStore
            if not task.approval_id:
                app_store = self.tool_gateway.game_tools.approvals
                rec = app_store.create(
                    tool=task.tool_call.get("name", "task_execution") if task.tool_call else "task_execution",
                    args=task.tool_call.get("arguments", {}) if task.tool_call else {"task_id": task.task_id},
                    summary=task.title,
                    consequence=f"Execution of task '{task.objective}'",
                    session_id=plan.session_id,
                    plan_id=plan.plan_id,
                )
                task.approval_id = rec["approval_id"]

            # Check status of approval
            rec = self.tool_gateway.game_tools.approvals.get(task.approval_id)
            if rec and rec.get("status") == "REJECTED":
                task.status = "CANCELLED"
                task.error_message = f"Approval {task.approval_id} rejected by user"
                task.completed_at = time.time()
                plan.block_descendants(task.task_id, task.error_message)
                self._emit("task_failed", plan.plan_id, task.task_id, status="CANCELLED",
                           message=task.error_message)
                return "CANCELLED"
            if not rec or rec.get("status") != "APPROVED":
                task.status = "WAITING_APPROVAL"
                self._emit("task_waiting_approval", plan.plan_id, task.task_id, status="WAITING_APPROVAL",
                           message=f"Task '{task.title}' awaiting approval (approval_id: {task.approval_id})",
                           data={"approval_id": task.approval_id})
                return "WAITING_APPROVAL"

        # Concurrency serialization
        is_write = task.reversibility != "read-only" or task.task_type in ("mutate", "build", "editor_op")
        is_unreal = task.task_type == "editor_op" or (task.tool_call and task.tool_call.get("name") == "unreal_editor")

        tool_history: List[Dict[str, Any]] = []

        while task.retry_count <= task.retry_limit:
            if self.is_cancelled():
                task.status = "CANCELLED"
                task.completed_at = time.time()
                return "CANCELLED"

            # Repetition control check
            if task.tool_call:
                t_name = task.tool_call.get("name", "")
                t_args = task.tool_call.get("arguments", {})
                canonical_key = self._get_repetition_key(t_name, t_args)
                count = self._tool_call_counts.get(canonical_key, 0) + 1
                self._tool_call_counts[canonical_key] = count
                if count >= 3:
                    task.status = "BLOCKED"
                    task.error_message = f"repetition_budget_exhausted: Tool '{t_name}' called 3 times with identical arguments"
                    task.completed_at = time.time()
                    plan.block_descendants(task.task_id, task.error_message)
                    self._emit("task_blocked", plan.plan_id, task.task_id, status="BLOCKED", message=task.error_message)
                    return "BLOCKED"

            # Run execution step
            step_error: Optional[str] = None
            step_output: Any = None

            try:
                if is_unreal:
                    with self._unreal_lock:
                        step_output = self._dispatch_tool_call(task)
                        self._state_version += 1
                elif is_write:
                    with self._write_lock:
                        step_output = self._dispatch_tool_call(task)
                        self._state_version += 1
                else:
                    step_output = self._dispatch_tool_call(task)
            except Exception as exc:
                step_error = str(exc)

            # Record evidence
            evidence_entry = {
                "timestamp": time.time(),
                "attempt": task.retry_count + 1,
                "tool_call": task.tool_call,
                "output": step_output,
                "error": step_error,
            }
            task.evidence.append(evidence_entry)

            if isinstance(step_output, dict):
                hist_entry = {
                    "tool_name": task.tool_call.get("name") if task.tool_call else "custom",
                    "arguments": task.tool_call.get("arguments") if task.tool_call else {},
                    "output": step_output,
                    "status": step_output.get("status", "SUCCESS" if not step_error else "ERROR"),
                    "exit_code": step_output.get("exit_code", 0 if not step_error else 1),
                }
                tool_history.append(hist_entry)
                if cumulative_history is not None:
                    cumulative_history.append(hist_entry)

            # Check for immediate tool-level error (fail closed on any non-success status)
            err_detail = _step_failure(step_error, step_output)
            if err_detail:
                task.error_message = err_detail

                # Attempt repair if within limit
                if task.retry_count < task.retry_limit and task.recovery_behavior in ("retry", "repair"):
                    task.retry_count += 1
                    task.status = "REPAIRING"
                    self._emit("task_repairing", plan.plan_id, task.task_id, status="REPAIRING",
                               message=f"Task '{task.title}' failed: {err_detail}. Attempting repair {task.retry_count}/{task.retry_limit}")
                    # Brief backoff before retry
                    time.sleep(0.5)
                    continue
                else:
                    task.status = "FAILED"
                    task.completed_at = time.time()
                    plan.block_descendants(task.task_id, task.error_message)
                    self._emit("task_failed", plan.plan_id, task.task_id, status="FAILED",
                               message=f"Task '{task.title}' FAILED: {task.error_message}")
                    return "FAILED"

            # Transition to VERIFYING state
            task.status = "VERIFYING"
            self._emit("task_verifying", plan.plan_id, task.task_id, status="VERIFYING",
                       message=f"Verifying acceptance predicates for task '{task.title}'")

            # Evaluate machine-checkable acceptance predicates over real observed state
            satisfied, unmet = self._evaluate_predicates(task.acceptance, tool_history)

            if satisfied:
                task.status = "COMPLETED"
                task.completed_at = time.time()
                self._emit("task_completed", plan.plan_id, task.task_id, status="COMPLETED",
                           message=f"Task '{task.title}' COMPLETED with verified acceptance")
                return "COMPLETED"
            else:
                task.error_message = f"Acceptance predicates unmet: {'; '.join(unmet)}"
                if task.retry_count < task.retry_limit and task.recovery_behavior in ("retry", "repair"):
                    task.retry_count += 1
                    task.status = "REPAIRING"
                    self._emit("task_repairing", plan.plan_id, task.task_id, status="REPAIRING",
                               message=f"Acceptance verification failed: {task.error_message}. Attempting repair {task.retry_count}/{task.retry_limit}")
                    time.sleep(0.5)
                    continue
                else:
                    task.status = "FAILED"
                    task.completed_at = time.time()
                    plan.block_descendants(task.task_id, task.error_message)
                    self._emit("task_failed", plan.plan_id, task.task_id, status="FAILED",
                               message=f"Task '{task.title}' FAILED acceptance: {task.error_message}")
                    return "FAILED"

        task.status = "FAILED"
        task.completed_at = time.time()
        plan.block_descendants(task.task_id, task.error_message or "Max retries exceeded")
        return "FAILED"

    def _dispatch_tool_call(self, task: TaskNode) -> Dict[str, Any]:
        """Dispatches the tool call attached to task node."""
        if not task.tool_call:
            # Inspection or custom task without tool call: evaluate predicates directly
            return {"status": "SUCCESS", "message": "No direct tool call, evaluation only"}

        tool_name = task.tool_call.get("name", "")
        tool_args = task.tool_call.get("arguments", {})

        # Security & permission boundary: tool must be permitted for this task
        if task.permitted_tools and tool_name not in task.permitted_tools:
            return {
                "status": "BLOCKED",
                "error": f"Tool '{tool_name}' not in permitted tools for task '{task.task_id}' ({task.permitted_tools})",
            }

        res = self.tool_gateway.execute_tool(
            tool_name,
            tool_args,
            approval_granted=True,  # Approval was checked at task node level
        )
        if tool_name == "propose_edit" and res.get("status") == "PENDING_APPROVAL" and res.get("diff_id"):
            # If the task node execution is approved, apply the diff to the filesystem
            apply_res = self.tool_gateway.execute_tool(
                "apply_edit",
                {"diff_id": res["diff_id"]},
                approval_granted=True,
            )
            apply_res["diff_id"] = res["diff_id"]
            apply_res["file_path"] = res.get("file_path")
            return apply_res
        return res

    def _evaluate_predicates(
        self, predicates: List[TaskAcceptancePredicate], tool_history: List[Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """Evaluates acceptance predicates against real observed state."""
        if not predicates:
            return True, []

        from .task_state import TaskState
        dummy_state = TaskState(session_id="eval", goal="eval", acceptance=predicates)
        modified_files: Set[str] = set()

        for th in tool_history:
            out = th.get("output", {})
            if isinstance(out, dict):
                if out.get("file_path"):
                    modified_files.add(out["file_path"])
                if out.get("affected_paths"):
                    modified_files.update(out["affected_paths"])

        satisfied, unmet = dummy_state.evaluate_acceptance(
            self.workspace_root, modified_files, tool_history
        )
        return satisfied, unmet

    def _evaluate_final_plan_status(self, plan: TaskPlan, cumulative_history: Optional[List[Dict[str, Any]]] = None) -> None:
        """Evaluates overall plan terminal status."""
        all_completed = all(t.status == "COMPLETED" for t in plan.tasks.values())
        any_failed = any(t.status == "FAILED" for t in plan.tasks.values())
        any_blocked = any(t.status == "BLOCKED" for t in plan.tasks.values())

        if plan.final_acceptance:
            final_ok, final_unmet = self._evaluate_predicates(plan.final_acceptance, cumulative_history or [])
            if not final_ok:
                plan.status = "FAILED"
                plan.metadata["final_acceptance_unmet"] = final_unmet
                self._emit("plan_failed", plan.plan_id, status="FAILED",
                           message=f"Plan completed subtasks but final acceptance criteria unmet: {'; '.join(final_unmet)}")
                return

        if all_completed:
            plan.status = "COMPLETED"
            self._emit("plan_completed", plan.plan_id, status="COMPLETED", message="Plan successfully COMPLETED")
        elif any_failed:
            plan.status = "FAILED"
            self._emit("plan_failed", plan.plan_id, status="FAILED", message="Plan FAILED due to subtask failures")
        elif any_blocked:
            plan.status = "BLOCKED"
            self._emit("plan_blocked", plan.plan_id, status="BLOCKED", message="Plan BLOCKED due to blocked subtasks")
        else:
            plan.status = "FAILED"

    def resume_plan(self, plan: TaskPlan, auto_approve_all: bool = False) -> TaskPlan:
        """Resumes an interrupted or persisted plan, reconciling in-flight state against real observations."""
        self._cancel_requested.clear()
        self._active_plan = plan

        # 1. State reconciliation for in-flight tasks
        for task in plan.tasks.values():
            if task.status in ("READY", "RUNNING", "VERIFYING", "REPAIRING"):
                # Check if task acceptance predicates are ALREADY satisfied on disk/engine
                if task.acceptance:
                    sat, _ = self._evaluate_predicates(task.acceptance, [])
                    if sat:
                        task.status = "COMPLETED"
                        task.completed_at = time.time()
                        continue
                # If non-idempotent and not satisfied, mark BLOCKED for manual review
                if task.reversibility in ("irreversible", "snapshot-only"):
                    task.status = "BLOCKED"
                    task.error_message = "Interrupted non-idempotent operation requires manual state reconciliation"
                else:
                    task.status = "PLANNED"  # Safe to retry from clean state

            elif task.status == "WAITING_APPROVAL":
                # Check base hash of any approval
                if task.approval_id:
                    app = self.tool_gateway.game_tools.approvals.get(task.approval_id)
                    # Re-queue decided approvals; _execute_task_node runs APPROVED and cancels REJECTED.
                    if app and app.get("status") in ("APPROVED", "REJECTED"):
                        task.status = "PLANNED"

        plan.save(self.workspace_root)
        return self.run_plan(plan, auto_approve_all=auto_approve_all)
