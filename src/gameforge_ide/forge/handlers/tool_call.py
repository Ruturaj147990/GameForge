"""Forge handler for TOOL_CALL steps (AD-11, Blueprint §8.1)."""
from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import json
from pathlib import Path
import threading
from typing import Any, Callable, Dict, List, Optional

from ...backend.agent.plan_executor import _step_failure
from ...backend.agent.task_state import TaskAcceptancePredicate, TaskState
from ...backend.tools.gateway import ToolGateway
from ..executor import StepContext, StepOutcome

__all__ = ["get_gateway", "make_tool_call_handler", "tool_call_handler"]

_GATEWAY_LOCK = threading.Lock()
_GATEWAY_CACHE: Dict[Path, ToolGateway] = {}
_SHARED_LOCK = threading.Lock()


def _is_cancelled(ctx: StepContext) -> bool:
    cancel = getattr(ctx, "cancel", None)
    return cancel is not None and cancel.is_set() is True


def get_gateway(workspace_dir: Path) -> ToolGateway:
    ws = Path(workspace_dir).resolve()
    with _GATEWAY_LOCK:
        gw = _GATEWAY_CACHE.get(ws)
        if gw is None:
            gw = ToolGateway(ws)
            _GATEWAY_CACHE[ws] = gw
        return gw


def _resolve_maybe_awaitable(value: Any) -> Any:
    """Resolve value if it is a coroutine or awaitable, supporting both sync and running-loop contexts."""
    if not inspect.isawaitable(value):
        return value
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, value)
            return future.result()
    return asyncio.run(value)


def make_tool_call_handler(gateway: Optional[Any] = None) -> Callable[[StepContext], StepOutcome]:
    """Return a step handler bound to an optional custom/async gateway instance."""
    def _handler(ctx: StepContext) -> StepOutcome:
        return tool_call_handler(ctx, gateway=gateway)
    return _handler


def tool_call_handler(ctx: StepContext, gateway: Optional[Any] = None) -> StepOutcome:
    """Executes a single tool call or evaluation step, verifies acceptance predicates, and records evidence."""
    if _is_cancelled(ctx):
        return StepOutcome(False, errors=["Cancelled by user"])

    inputs = ctx.step.inputs
    tool = inputs.get("tool") or ""
    raw_arguments = inputs.get("arguments")
    if raw_arguments is None:
        arguments: Dict[str, Any] = {}
    elif isinstance(raw_arguments, dict):
        arguments = raw_arguments
    else:
        return StepOutcome(
            False,
            errors=[f"tool_call 'arguments' must be a dict, got {type(raw_arguments).__name__}"],
            repairable=True,
        )
    acceptance_raw = inputs.get("acceptance") or []
    permitted_tools = inputs.get("permitted_tools") or []
    try:
        repetition_limit = max(1, int(inputs.get("repetition_limit", 3)))
    except (TypeError, ValueError):
        return StepOutcome(False, errors=["Invalid repetition_limit value"], repairable=True)

    # Repetition budget control
    if tool:
        canonical_key = f"{tool}:{json.dumps(arguments, sort_keys=True, default=str)}"
        with _SHARED_LOCK:
            repetition = ctx.shared.setdefault("_repetition", {})
            count = repetition.get(canonical_key, 0) + 1
            repetition[canonical_key] = count
        if count >= repetition_limit:
            return StepOutcome(
                False,
                errors=[f"repetition_budget_exhausted: Tool '{tool}' called {count} times with identical arguments"],
                blocked=True,
            )

    # Permitted tools boundary
    if permitted_tools and tool and tool not in permitted_tools:
        return StepOutcome(
            False,
            errors=[f"Tool '{tool}' not in permitted tools ({permitted_tools})"],
            blocked=True,
        )

    # Empty task without acceptance or approval
    if not tool and not acceptance_raw and ctx.step.approval == "none":
        return StepOutcome(
            False,
            errors=["NO_EVIDENCE: task declares neither a tool call nor acceptance predicates"],
            blocked=True,
        )

    gw = gateway or inputs.get("gateway") or get_gateway(ctx.workspace_dir)

    step_output: Any = None
    step_error: Optional[str] = None

    # Approval comes only from the user: the executor holds a step with approval "step"/"run"
    # until the user approves it in the UI. A step declared with approval "none" (e.g. by a
    # model-generated plan) must NOT silently grant approval for an approval-gated tool.
    user_approved = getattr(ctx.step, "approval", "none") in ("step", "run")

    if tool:
        ctx.log(f"Executing tool '{tool}' with args {list(arguments.keys())}")
        try:
            raw_out = gw.execute_tool(
                tool,
                arguments,
                approval_granted=user_approved,
            )
            step_output = _resolve_maybe_awaitable(raw_out)
            if (
                isinstance(step_output, dict)
                and step_output.get("status") in ("PENDING_APPROVAL", "AWAITING_APPROVAL")
                and not user_approved
                and tool != "propose_edit"
            ):
                return StepOutcome(
                    False,
                    errors=[
                        f"APPROVAL_REQUIRED: tool '{tool}' needs user approval but step "
                        f"'{ctx.step.step_id}' was not declared with approval='step'"
                    ],
                    data={"output": step_output},
                    blocked=True,
                )
            if (
                tool == "propose_edit"
                and isinstance(step_output, dict)
                and step_output.get("status") == "PENDING_APPROVAL"
                and step_output.get("diff_id")
            ):
                raw_apply = gw.execute_tool(
                    "apply_edit",
                    {"diff_id": step_output["diff_id"]},
                    approval_granted=user_approved,
                )
                apply_res = _resolve_maybe_awaitable(raw_apply)
                if isinstance(apply_res, dict):
                    apply_res["diff_id"] = step_output["diff_id"]
                    apply_res["file_path"] = step_output.get("file_path")
                step_output = apply_res
        except Exception as exc:
            step_error = f"{type(exc).__name__}: {exc}"
    else:
        step_output = {"status": "SUCCESS", "message": "Evaluation only"}

    # Record in shared cumulative tool history
    hist_entry = {
        "tool_name": tool or "custom",
        "arguments": arguments,
        "output": step_output,
        "status": (
            step_output.get("status", "SUCCESS" if not step_error else "ERROR")
            if isinstance(step_output, dict)
            else "SUCCESS"
        ),
        "exit_code": (
            step_output.get("exit_code", 0 if not step_error else 1)
            if isinstance(step_output, dict)
            else 0
        ),
    }
    with _SHARED_LOCK:
        tool_history: List[Dict[str, Any]] = ctx.shared.setdefault("_tool_history", [])
        tool_history.append(hist_entry)

        modified_files: set[str] = ctx.shared.setdefault("_modified_files", set())
        if isinstance(step_output, dict):
            fp = step_output.get("file_path") or step_output.get("path")
            if fp:
                modified_files.add(str(fp))
        modified_snapshot = set(modified_files)
        history_snapshot = list(tool_history)

    # Check for immediate tool failure
    err_detail = _step_failure(step_error, step_output)
    if err_detail:
        return StepOutcome(
            False,
            data={"output": step_output, "error": err_detail},
            errors=[err_detail],
            repairable=True,
        )

    # Evaluate machine-checkable acceptance predicates
    evaluated_acceptance: List[Dict[str, Any]] = []
    if acceptance_raw:
        try:
            predicates = [TaskAcceptancePredicate.model_validate(p) for p in acceptance_raw]
        except Exception as exc:
            return StepOutcome(
                False,
                data={"output": step_output},
                errors=[f"Invalid acceptance predicate: {exc}"],
                repairable=True,
            )
        dummy_state = TaskState(session_id=ctx.run.run_id, goal=ctx.run.title, acceptance=predicates)
        satisfied, unmet = dummy_state.evaluate_acceptance(ctx.workspace_dir, modified_snapshot, history_snapshot)
        evaluated_acceptance = [p.model_dump() for p in predicates]
        if not satisfied:
            return StepOutcome(
                False,
                data={"output": step_output, "acceptance": evaluated_acceptance},
                errors=[f"Acceptance predicates unmet: {'; '.join(unmet)}"],
                repairable=True,
            )

    return StepOutcome(
        True,
        data={"output": step_output, "status": "COMPLETED", "acceptance": evaluated_acceptance},
        errors=[],
    )
