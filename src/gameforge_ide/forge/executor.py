"""ForgeExecutor (AD-11): runs a RunSpec step by step with persistence, resume, approvals, retries and checkpoints."""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core import events as core_events
from ..core.jobs import ENGINE_LOCK
from .checkpoints import CheckpointError, ProjectRepo
from .model import TERMINAL, ArtifactRef, RunSpec, RunState, StepRecord, StepSpec, StepStatus, canonical_hash
from .store import RunStore


@dataclass
class StepContext:
    run: RunSpec
    step: StepSpec
    record: StepRecord
    shared: Dict[str, Any]  # outputs of earlier steps: shared[step_id] = record.data
    project_dir: Optional[Path]
    workspace_dir: Path
    cancel: threading.Event
    log: Callable[[str], None]  # appends a "log" event (bounded to 2 KB per line)

    @property
    def artifacts_dir(self) -> Path:
        base = Path(self.project_dir).resolve() if (self.project_dir and str(self.project_dir).strip()) else Path(self.workspace_dir).resolve()
        d = base / "Saved" / "GameForge" / "evidence"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d


@dataclass
class StepOutcome:
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    repairable: bool = False  # handler says a retry after repair may succeed
    blocked: bool = False  # environment problem (engine missing, approval revoked): no retry


Handler = Callable[[StepContext], StepOutcome]
RepairHook = Callable[[StepContext, StepOutcome], bool]  # returns True if it changed something worth retrying


class ForgeExecutor:
    _active_executors: Dict[str, "ForgeExecutor"] = {}

    def __init__(
        self,
        handlers: Dict[str, Handler],
        repair_hooks: Optional[Dict[str, RepairHook]] = None,
        bus: Optional[core_events.EventBus] = None,
    ):
        self.handlers = handlers
        self.repair_hooks = repair_hooks or {}
        self.bus = bus or core_events.default_bus()
        self._run_cancel = threading.Event()  # user cancelled the whole run
        self._step_cancel: Optional[threading.Event] = None  # current step (also set on timeout)

    @classmethod
    def cancel_run(cls, run_id: str) -> bool:
        ex = cls._active_executors.get(run_id)
        if ex is not None:
            ex.request_cancel()
            return True
        return False

    def request_cancel(self, run_id: Optional[str] = None) -> None:
        """Called from the UI thread. Stops the current step and prevents further steps."""
        if isinstance(self, str) and run_id is None:
            ForgeExecutor.cancel_run(self)
            return
        if run_id:
            ForgeExecutor.cancel_run(run_id)
            return
        self._run_cancel.set()
        ev = self._step_cancel
        if ev is not None:
            ev.set()
        try:
            from ..core.jobs import terminate_all_children
            terminate_all_children()
        except Exception:
            pass

    # -- public -------------------------------------------------------------------------------
    def resume(self, state: RunState, store: RunStore, editor_running: Callable[[], bool] = lambda: False) -> RunState:
        """Resume a failed, cancelled or interrupted run, unblocking failed/cancelled/blocked steps."""
        for rec in state.records.values():
            if rec.status in (StepStatus.FAILED, StepStatus.CANCELLED, StepStatus.BLOCKED):
                rec.status = StepStatus.PENDING
                rec.errors = []
        return self.run(state, store, editor_running)

    def run(self, state: RunState, store: RunStore, editor_running: Callable[[], bool] = lambda: False) -> RunState:
        """Execute until DONE, FAILED, CANCELLED, BLOCKED or WAITING_APPROVAL. Safe to call again to resume."""
        ForgeExecutor._active_executors[state.run.run_id] = self
        try:
            return self._run_internal(state, store, editor_running)
        finally:
            ForgeExecutor._active_executors.pop(state.run.run_id, None)

    def _run_internal(self, state: RunState, store: RunStore, editor_running: Callable[[], bool] = lambda: False) -> RunState:
        """Execute until DONE, FAILED, CANCELLED, BLOCKED or WAITING_APPROVAL. Safe to call again to resume."""
        run = state.run
        repo = ProjectRepo(Path(run.project_dir)) if run.project_dir else None
        self._recover_interrupted(state)
        state.status = "RUNNING"
        self._persist(state, store, {"kind": "run_started"})
        if self._needs_run_approval(state):
            return self._suspend(state, store, "run")

        try:
            steps_order = run.topo_order()
        except (ValueError, Exception) as exc:
            state.status = "FAILED"
            for rec in state.records.values():
                if rec.status in (StepStatus.PENDING, StepStatus.RUNNING):
                    rec.status = StepStatus.BLOCKED
                    rec.errors = [f"DAG topology error: {exc}"]
            self._persist(state, store, {"kind": "run_finished", "status": "FAILED", "error": str(exc)})
            return state

        eff: Dict[str, str] = {}  # effective hash = own inputs + dependencies' effective hashes
        for step in steps_order:
            eff[step.step_id] = canonical_hash(
                {"self": step.input_hash, "deps": [eff[d] for d in sorted(step.depends_on)]}
            )
            rec = state.records[step.step_id]
            if self._run_cancel.is_set():
                return self._finish(state, store, "CANCELLED")
            if rec.status == StepStatus.DONE and rec.ok is True and rec.input_hash == eff[step.step_id]:
                continue  # resume / incremental: unchanged work is skipped

            # If step was previously marked BLOCKED, check if its dependencies are now all DONE:
            if rec.status == StepStatus.BLOCKED and all(
                state.records[d].status == StepStatus.DONE for d in step.depends_on
            ):
                rec.status = StepStatus.PENDING
                rec.errors = []

            if rec.status in TERMINAL and rec.status != StepStatus.DONE:
                continue  # FAILED/BLOCKED/SKIPPED stay until the run is re-planned
            if any(state.records[d].status != StepStatus.DONE for d in step.depends_on):
                rec.status = StepStatus.BLOCKED
                rec.errors = [
                    f"dependency not done: {[d for d in step.depends_on if state.records[d].status != StepStatus.DONE]}"
                ]
                self._persist(state, store, {"kind": "step_blocked", "step_id": step.step_id})
                continue
            if step.approval == "step" and step.step_id not in state.approvals:
                return self._suspend(state, store, step.step_id)
            try:
                self._run_step(state, store, step, rec, repo, editor_running, eff[step.step_id])
            except Exception as exc:
                rec.finished_at = time.time()
                rec.ok = False
                rec.status = StepStatus.CANCELLED if self._run_cancel.is_set() else StepStatus.FAILED
                rec.errors = [f"Step execution crashed: {type(exc).__name__}: {exc}", traceback.format_exc(limit=4)]
                self._persist(
                    state,
                    store,
                    {
                        "kind": "step_finished",
                        "step_id": step.step_id,
                        "ok": False,
                        "status": rec.status.value,
                        "errors": rec.errors[:10],
                    },
                )
            # A FAILED step needs no special handling: its dependants become BLOCKED by the dependency check above.
        final = (
            "DONE"
            if all(r.status in (StepStatus.DONE, StepStatus.SKIPPED) for r in state.records.values())
            else ("CANCELLED" if self._run_cancel.is_set() else "FAILED")
        )
        return self._finish(state, store, final)

    # -- internals ----------------------------------------------------------------------------
    def _run_step(self, state: RunState, store: RunStore, step: StepSpec, rec: StepRecord, repo: Optional[ProjectRepo], editor_running: Callable[[], bool], eff_hash: str) -> None:
        handler = self.handlers.get(step.step_id) or self.handlers.get(step.kind.value)
        if handler is None:
            rec.status, rec.errors = StepStatus.BLOCKED, [f"no handler for step {step.step_id} (kind {step.kind.value})"]
            self._persist(state, store, {"kind": "step_blocked", "step_id": step.step_id})
            return
        shared = {sid: r.data for sid, r in state.records.items() if r.status == StepStatus.DONE}
        while True:
            rec.attempts += 1
            rec.status, rec.started_at, rec.finished_at = StepStatus.RUNNING, time.time(), None
            rec.input_hash, rec.errors = eff_hash, []
            self._persist(state, store, {"kind": "step_started", "step_id": step.step_id, "attempt": rec.attempts})
            self._step_cancel = threading.Event()
            if self._run_cancel.is_set():
                self._step_cancel.set()
            ctx = StepContext(
                state.run,
                step,
                rec,
                shared,
                Path(state.run.project_dir) if state.run.project_dir else None,
                Path(state.run.workspace_dir),
                self._step_cancel,
                lambda line, sid=step.step_id: store.append_event(
                    state.run.run_id, {"kind": "log", "step_id": sid, "line": (str(line) if line is not None else "")[:2048]}
                ),
            )
            try:
                try:
                    if step.engine_lock:
                        with ENGINE_LOCK:
                            out = self._with_timeout(handler, ctx, step.timeout_s)
                    else:
                        out = self._with_timeout(handler, ctx, step.timeout_s)
                except Exception as exc:  # a handler crash is a typed step failure, never a crashed run
                    out = StepOutcome(False, errors=[f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=4)])

                if not out.ok and self._run_cancel.is_set():
                    out = StepOutcome(False, errors=["Cancelled by user"])

                rec.finished_at, rec.ok, rec.data = time.time(), out.ok, out.data
                rec.errors = out.errors
                valid_artifacts = []
                for a in (out.artifacts or []):
                    try:
                        if isinstance(a, dict):
                            a_copy = dict(a)
                            kind = a_copy.get("kind", "other")
                            if kind not in ("log", "report", "screenshot", "package", "scenario_result", "other"):
                                a_copy["kind"] = "other"
                            valid_artifacts.append(ArtifactRef.model_validate(a_copy))
                        elif isinstance(a, ArtifactRef):
                            valid_artifacts.append(a)
                    except Exception:
                        pass
                rec.artifacts = valid_artifacts
                if out.ok and not self._run_cancel.is_set():
                    from .validation import validate_stage_output
                    gds_obj = None
                    if "gds" in ctx.step.inputs:
                        try:
                            from ..design.gds import GameDesignSpec
                            g_raw = ctx.step.inputs["gds"]
                            gds_obj = GameDesignSpec.model_validate(g_raw) if isinstance(g_raw, dict) else g_raw
                        except Exception:
                            pass
                    if gds_obj is None:
                        for sh in ctx.shared.values():
                            if isinstance(sh, dict) and "gds" in sh:
                                try:
                                    from ..design.gds import GameDesignSpec
                                    g_raw = sh["gds"]
                                    gds_obj = GameDesignSpec.model_validate(g_raw) if isinstance(g_raw, dict) else g_raw
                                    if gds_obj is not None:
                                        break
                                except Exception:
                                    pass
                    # Strictly validate outputs when project context or stage outputs are present
                    if ctx.project_dir is not None or gds_obj is not None or any(
                        k in out.data for k in ("params", "recipe", "files", "exe", "report_path", "mesh_audit", "spawned_actors", "read_back_actors")
                    ):
                        val_data = dict(out.data)
                        if "params" in ctx.step.inputs and "params" not in val_data:
                            val_data["params"] = ctx.step.inputs["params"]
                        if "recipe" in ctx.step.inputs and "recipe" not in val_data:
                            val_data["recipe"] = ctx.step.inputs["recipe"]
                        stage_ok, validation_issues = validate_stage_output(
                            step.kind.value,
                            val_data,
                            gds=gds_obj,
                            project_dir=ctx.project_dir,
                            artifacts=out.artifacts,
                        )
                        if not stage_ok:
                            out.ok = False
                            out.errors.extend([f"Validation: {issue}" for issue in validation_issues])

                if out.ok:
                    if repo is not None and step.checkpoint and repo.available:
                        try:
                            repo.ensure()
                            rec.checkpoint = repo.commit(f"forge: {step.step_id} ({state.run.run_id})")
                        except (CheckpointError, Exception) as exc:
                            rec.data = {**rec.data, "checkpoint_warning": str(exc)}
                    rec.status = StepStatus.DONE
                    self._persist(
                        state,
                        store,
                        {"kind": "step_finished", "step_id": step.step_id, "ok": True, "duration_s": rec.duration_s},
                    )
                    return
                if self._run_cancel.is_set():
                    rec.status = StepStatus.CANCELLED
                elif out.blocked:
                    rec.status = StepStatus.BLOCKED
                elif (
                    rec.attempts < step.max_attempts
                    and out.repairable
                    and self.repair_hooks.get(step.kind.value, lambda c, o: False)(ctx, out)
                ):
                    self._persist(
                        state,
                        store,
                        {
                            "kind": "step_repairing",
                            "step_id": step.step_id,
                            "attempt": rec.attempts,
                            "errors": out.errors[:5],
                        },
                    )
                    continue
                else:
                    rec.status = StepStatus.FAILED
                self._persist(
                    state,
                    store,
                    {
                        "kind": "step_finished",
                        "step_id": step.step_id,
                        "ok": False,
                        "status": rec.status.value,
                        "errors": out.errors[:10],
                    },
                )
                return
            except Exception as exc:
                rec.finished_at = time.time()
                rec.ok = False
                rec.status = StepStatus.CANCELLED if self._run_cancel.is_set() else StepStatus.FAILED
                rec.errors = [f"Step execution crashed: {type(exc).__name__}: {exc}", traceback.format_exc(limit=4)]
                self._persist(
                    state,
                    store,
                    {
                        "kind": "step_finished",
                        "step_id": step.step_id,
                        "ok": False,
                        "status": rec.status.value,
                        "errors": rec.errors[:10],
                    },
                )
                return

    def _with_timeout(self, handler: Handler, ctx: StepContext, timeout_s: float) -> StepOutcome:
        """Handlers must poll ctx.cancel; on timeout or cancel we signal cancel and wait up to 2 s."""
        box: Dict[str, Any] = {}

        def target() -> None:
            try:
                box["out"] = handler(ctx)
            except Exception as exc:  # exceptions in this thread would otherwise be lost
                box["exc"] = f"{type(exc).__name__}: {exc}"
                box["tb"] = traceback.format_exc(limit=4)

        t = threading.Thread(target=target, daemon=True, name=f"forge-{ctx.step.step_id}")
        t.start()

        start_time = time.time()
        deadline = start_time + timeout_s
        timed_out = False

        while t.is_alive():
            t.join(timeout=0.05)
            if self._run_cancel.is_set():
                ctx.cancel.set()
                break
            if time.time() >= deadline:
                timed_out = True
                ctx.cancel.set()
                break

        if timed_out:
            ctx.cancel.set()
            t.join(timeout=1.0)
            return StepOutcome(False, errors=[f"TIMEOUT after {timeout_s:.1f}s"])

        if self._run_cancel.is_set():
            ctx.cancel.set()
            t.join(timeout=1.0)
            if "out" in box and box["out"].ok:
                return box["out"]
            return StepOutcome(False, errors=["Cancelled by user"])

        if "exc" in box:
            return StepOutcome(False, errors=[box["exc"], box["tb"]])
        return box.get("out") or StepOutcome(False, errors=["handler returned nothing"])

    def _recover_interrupted(self, state: RunState) -> None:
        for rec in state.records.values():
            if rec.status in (StepStatus.RUNNING, StepStatus.WAITING_APPROVAL):
                rec.status = StepStatus.PENDING  # crashed mid-step: re-run it (handlers are idempotent)

    def _needs_run_approval(self, state: RunState) -> bool:
        return any(s.approval == "run" for s in state.run.steps) and "run" not in state.approvals

    def _suspend(self, state: RunState, store: RunStore, key: str) -> RunState:
        state.status = "WAITING_APPROVAL"
        if key != "run":
            state.records[key].status = StepStatus.WAITING_APPROVAL
        self._persist(state, store, {"kind": "approval_needed", "key": key})
        return state

    def _finish(self, state: RunState, store: RunStore, status: str) -> RunState:
        state.status = status
        now = time.time()
        for rec in state.records.values():
            if rec.status == StepStatus.RUNNING:
                rec.status = StepStatus.CANCELLED if status == "CANCELLED" else StepStatus.FAILED
                if not rec.finished_at:
                    rec.finished_at = now
                if not rec.errors:
                    rec.errors = ["Cancelled by user"] if status == "CANCELLED" else ["Run failed while step was running"]
                self._persist(
                    state,
                    store,
                    {
                        "kind": "step_finished",
                        "step_id": rec.step_id,
                        "ok": False,
                        "status": rec.status.value,
                        "errors": rec.errors[:10],
                    },
                )
        self._persist(state, store, {"kind": "run_finished", "status": status})
        return state

    def _persist(self, state: RunState, store: RunStore, event: Dict[str, Any]) -> None:
        state.updated_at = time.time()
        store.save(state)
        ev = {"run_id": state.run.run_id, **event}
        store.append_event(state.run.run_id, ev)
        self.bus.publish("forge", ev)
