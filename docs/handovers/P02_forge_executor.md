# P2 — Forge Executor, Checkpoints and Jobs (handover)

**Branch:** `master` (no feature branches). **Depends on:** P1 accepted. **Decisions:** AD-11, AD-13, AD-14 (enforcement).
**Estimate:** 2 weeks. **Read first:** `../01_ARCHITECTURE.md` §3.4, §4, §7.2.

## Objective

Replace the two executors with **one durable executor**: the linear `GamePipeline.run` closure chain
(`pipeline/game_pipeline.py:101-297`) and the agent `TaskPlanExecutor` (`backend/agent/plan_executor.py`). The new
executor persists every run, resumes after crashes, skips unchanged work and checkpoints the project after every
successful step. **No behaviour change** for users except two: builds can now resume, and Build-view data exists.

## Package layout

```
src/gameforge_ide/core/events.py        # thread-safe pub/sub (Qt-free)
src/gameforge_ide/core/jobs.py          # JobManager + Windows job objects + spawn()
src/gameforge_ide/forge/__init__.py
src/gameforge_ide/forge/model.py        # StepKind, StepStatus, StepSpec, StepRecord, RunSpec, RunState
src/gameforge_ide/forge/executor.py     # ForgeExecutor
src/gameforge_ide/forge/checkpoints.py  # ProjectRepo (git)
src/gameforge_ide/forge/store.py        # RunStore: persistence + runs index
src/gameforge_ide/forge/handlers/__init__.py   # HANDLERS registry
src/gameforge_ide/forge/handlers/legacy_stages.py  # spec/scaffold/sources/build/assemble/tests/package/smoke
src/gameforge_ide/forge/handlers/tool_call.py      # agent tool-call steps (ToolGateway + predicates)
src/gameforge_ide/forge/legacy_adapter.py      # GamePipeline API on top of Forge
src/gameforge_ide/forge/plan_adapter.py        # TaskPlan → RunSpec
src/gameforge_ide/desktop/services/forge_service.py  # Qt bridge (signals) — consumed by P4 Build view
tests/unit/test_forge_model.py test_forge_executor.py test_forge_checkpoints.py test_jobs.py test_forge_legacy_adapter.py test_forge_plan_adapter.py
```

---

## WI-2.1 `forge/model.py`

```python
"""Forge data model (AD-11). Everything is JSON-serialisable and persisted after each transition."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StepKind(str, Enum):
    DESIGN = "design"; SCAFFOLD = "scaffold"; CODEGEN = "codegen"; BUILD = "build"; ASSEMBLE = "assemble"
    CONTENT = "content"; AUTOMATION = "automation"; PACKAGE = "package"; SCENARIO = "scenario"
    REVIEW = "review"; REPORT = "report"; TOOL_CALL = "tool_call"


class StepStatus(str, Enum):
    PENDING = "PENDING"; RUNNING = "RUNNING"; WAITING_APPROVAL = "WAITING_APPROVAL"; DONE = "DONE"
    FAILED = "FAILED"; BLOCKED = "BLOCKED"; SKIPPED = "SKIPPED"; CANCELLED = "CANCELLED"


TERMINAL = {StepStatus.DONE, StepStatus.FAILED, StepStatus.BLOCKED, StepStatus.SKIPPED, StepStatus.CANCELLED}


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class StepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    kind: StepKind
    title: str = Field(max_length=120)
    depends_on: List[str] = Field(default_factory=list)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    engine_lock: bool = False
    approval: Literal["none", "run", "step"] = "none"
    max_attempts: int = Field(1, ge=1, le=5)
    timeout_s: float = Field(3600, gt=0, le=6 * 3600)
    checkpoint: bool = True            # commit the project after DONE (needs a project repo)

    @property
    def input_hash(self) -> str:
        return canonical_hash({"kind": self.kind.value, "inputs": self.inputs})


class ArtifactRef(BaseModel):
    path: str
    kind: Literal["log", "report", "screenshot", "package", "scenario_result", "other"] = "other"
    sha256: Optional[str] = None


class StepRecord(BaseModel):
    step_id: str
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    input_hash: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    ok: Optional[bool] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    artifacts: List[ArtifactRef] = Field(default_factory=list)
    checkpoint: Optional[str] = None   # git commit sha after DONE

    @property
    def duration_s(self) -> Optional[float]:
        return round(self.finished_at - self.started_at, 1) if self.started_at and self.finished_at else None


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(default_factory=lambda: "run_" + time.strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(3))
    title: str
    origin: Literal["prompt", "change_request", "agent_plan", "cli", "test"] = "cli"
    project_dir: Optional[str] = None           # None for workspace-only runs (agent plans)
    workspace_dir: str
    gds_revision: Optional[int] = None
    steps: List[StepSpec]
    created_at: float = Field(default_factory=time.time)

    @field_validator("steps")
    @classmethod
    def _dag(cls, steps: List[StepSpec]) -> List[StepSpec]:
        ids = [s.step_id for s in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate step_id")
        known = set(ids)
        for s in steps:
            missing = [d for d in s.depends_on if d not in known]
            if missing or s.step_id in s.depends_on:
                raise ValueError(f"step {s.step_id}: bad dependencies {missing or [s.step_id]}")
        # Kahn cycle check
        indeg = {s.step_id: len(s.depends_on) for s in steps}
        children: Dict[str, List[str]] = {i: [] for i in ids}
        for s in steps:
            for d in s.depends_on:
                children[d].append(s.step_id)
        queue = [i for i, n in indeg.items() if n == 0]
        seen = 0
        while queue:
            cur = queue.pop()
            seen += 1
            for c in children[cur]:
                indeg[c] -= 1
                if indeg[c] == 0:
                    queue.append(c)
        if seen != len(ids):
            raise ValueError("dependency cycle")
        return steps

    def topo_order(self) -> List[StepSpec]:
        """Stable topological order: declaration order among ready steps."""
        done: set[str] = set()
        order: List[StepSpec] = []
        pending = list(self.steps)
        while pending:
            for s in pending:
                if all(d in done for d in s.depends_on):
                    order.append(s); done.add(s.step_id); pending.remove(s)
                    break
        return order


class RunState(BaseModel):
    run: RunSpec
    records: Dict[str, StepRecord]
    status: Literal["PENDING", "RUNNING", "WAITING_APPROVAL", "DONE", "FAILED", "CANCELLED", "BLOCKED"] = "PENDING"
    approvals: Dict[str, str] = Field(default_factory=dict)   # "run" or step_id -> approval_id
    updated_at: float = Field(default_factory=time.time)

    @classmethod
    def new(cls, run: RunSpec) -> "RunState":
        return cls(run=run, records={s.step_id: StepRecord(step_id=s.step_id) for s in run.steps})
```

**Tests:** cycle, missing dependency and duplicate id rejected; `topo_order` is stable; `input_hash` changes when
any input changes and not when only the title changes.

---

## WI-2.2 `forge/store.py`

- `RunStore(project_dir: Optional[Path], workspace_dir: Path)`. The run dir is
  `<project>/Saved/GameForge/runs/<run_id>/` if `project_dir` is set, otherwise
  `<workspace>/.gameforge/runs/<run_id>/`.
- `save(state)`: write `state.json` atomically (tmp + `os.replace`); retry `os.replace` up to 5× on `PermissionError`
  (antivirus or indexer locks on Windows), sleeping 0.1 s between tries.
- `append_event(run_id, event: dict)`: append one JSON line to `events.jsonl` (`"t": time.time()` added).
- `load(run_id)`, `latest_for_project(project_dir)`, and the index `<workspace>/.gameforge/runs_index.json`
  (`[{run_id, title, project_dir, status, created_at, updated_at}]`, the newest 200 kept) for the Build and Games views.

---

## WI-2.3 `forge/checkpoints.py` (AD-13)

```python
"""Per-project git checkpoints. GameForge owns the repo inside each generated project; commits are local only."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

UE_GITIGNORE = """# GameForge-managed project repo (checkpoints)
Binaries/
Intermediate/
Saved/
DerivedDataCache/
Packaged/
.vs/
*.sln
*.VC.db
*.opendb
"""
MAX_COMMIT_MB = 200


class CheckpointError(RuntimeError):
    pass


class ProjectRepo:
    def __init__(self, project_dir: Path, git: Optional[str] = None):
        self.dir = Path(project_dir)
        self.git = git or shutil.which("git")

    @property
    def available(self) -> bool:
        return self.git is not None

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        if not self.git:
            raise CheckpointError("git is not installed; checkpoints are disabled")
        res = subprocess.run([self.git, "-C", str(self.dir), *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=300)
        if check and res.returncode != 0:
            raise CheckpointError(f"git {' '.join(args)} failed: {res.stderr.strip()[:500]}")
        return res

    def ensure(self) -> None:
        if (self.dir / ".git").is_dir():
            return
        self._run("init", "-q")
        self._run("config", "user.name", "GameForge")
        self._run("config", "user.email", "gameforge@localhost")
        self._run("config", "core.autocrlf", "false")
        gi = self.dir / ".gitignore"
        if not gi.exists():
            gi.write_text(UE_GITIGNORE, encoding="utf-8", newline="\n")
        self._run("add", "-A")
        self._run("commit", "-q", "--allow-empty", "-m", "forge: initial")

    def head(self) -> str:
        return self._run("rev-parse", "HEAD").stdout.strip()

    def commit(self, message: str) -> str:
        """Commit everything not ignored; returns HEAD (unchanged if nothing changed)."""
        self._run("add", "-A")
        if not self._run("status", "--porcelain").stdout.strip():
            return self.head()
        staged = self._run("diff", "--cached", "--numstat").stdout   # binary files show "-\t-"
        size_mb = sum((self.dir / line.split("\t")[-1]).stat().st_size for line in staged.splitlines()
                      if (self.dir / line.split("\t")[-1]).is_file()) / 1e6
        if size_mb > MAX_COMMIT_MB:
            self._run("reset", "-q")
            raise CheckpointError(f"checkpoint would add {size_mb:.0f} MB (> {MAX_COMMIT_MB} MB); refusing")
        self._run("commit", "-q", "-m", message)
        return self.head()

    def reset_to(self, sha: str, editor_running: bool) -> None:
        """Hard reset + clean of non-ignored files. Refuses while an editor holds the project's files."""
        if editor_running:
            raise CheckpointError("stop the Unreal Editor for this project before rolling back")
        self._run("cat-file", "-e", f"{sha}^{{commit}}")
        self._run("reset", "-q", "--hard", sha)
        self._run("clean", "-q", "-fd")

    def changed_since(self, sha: str) -> List[str]:
        out = self._run("diff", "--name-only", sha, "--").stdout.splitlines()
        untracked = self._run("ls-files", "--others", "--exclude-standard").stdout.splitlines()
        return sorted(set(out) | set(untracked))
```

**Tests (`test_forge_checkpoints.py`, requires git, skip with a reason if absent):** ensure → initial commit; commit
after writing a file returns a new sha; a no-change commit returns the same sha; `reset_to(sha, editor_running=True)`
raises; `reset_to(sha, False)` restores byte-identical content (hash a file before and after); `changed_since` lists a
modified file; the 200 MB guard fires on a 201 MB file. Use a 1 MB file and monkeypatch `MAX_COMMIT_MB=0.5` to keep the
test fast.

---

## WI-2.4 `core/jobs.py` — child processes that cannot leak

```python
"""Background jobs and child-process ownership. Every child the IDE starts joins one Windows job object that is
created with KILL_ON_JOB_CLOSE, so all children die with the IDE even if it crashes (Blueprint §8.1)."""
from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
from ctypes import wintypes
from typing import Optional, Sequence

_JOB = None
_LOCK = threading.Lock()
ENGINE_LOCK = threading.RLock()   # serialises every engine-mutating job and Forge step (design rule 6)

if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                    "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _EXT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BASIC), ("IoInfo", _IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)


def _job():
    global _JOB
    if sys.platform != "win32":
        return None
    with _LOCK:
        if _JOB is None:
            h = _k32.CreateJobObjectW(None, None)
            if not h:
                raise ctypes.WinError(ctypes.get_last_error())
            info = _EXT()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not _k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            _JOB = h
        return _JOB


def adopt(proc: subprocess.Popen) -> bool:
    """Put an already-started child into the IDE job. Returns False (and logs) if Windows refuses."""
    job = _job()
    if job is None:
        return False
    return bool(_k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle))))


def spawn(argv: Sequence[str], **popen_kwargs) -> subprocess.Popen:
    """The only way product code starts child processes (editor, UBT, UAT, games, Ollama helpers)."""
    if popen_kwargs.get("shell"):
        raise ValueError("shell=True is forbidden")
    proc = subprocess.Popen(list(argv), **popen_kwargs)
    adopt(proc)
    return proc
```

Steps:
1. Replace every `subprocess.Popen(` in product code with `jobs.spawn(`. Find them with
   `rg "subprocess\.Popen\(" src/gameforge_ide`. They are in toolchain, live_editor, game_tools.play_game,
   terminal_tools and others. **Exception:** `game_tools.play_game` launches a game *for the user to keep playing*,
   so it must **not** die with the IDE. It keeps plain `subprocess.Popen` and is never adopted. The IDE process
   itself is not in the job; only adopted children (and their own descendants) are. Do **not** use
   `CREATE_BREAKAWAY_FROM_JOB`: it fails when the IDE runs inside a foreign job without BREAKAWAY_OK. Add a comment at
   that call site explaining why it is not adopted.
2. A unit test (Windows only) spawns `python -c "import time; time.sleep(60)"` through `spawn()` inside a *helper
   process*, kills the helper, and asserts with `psutil` that the sleeper is gone within 5 s.
3. `JobManager` (same file): `submit(fn, *, name, cancel_event) -> JobHandle` running on a `ThreadPoolExecutor(max_workers=2)`.
   `JobHandle` has `cancel()`, `done()` and `result(timeout)`. Engine jobs are serialised by `ENGINE_LOCK = threading.Lock()`
   (also used by Forge's `engine_lock` steps). The existing `desktop/services/action_runner.py` QThread logic moves
   onto JobManager in WI-2.8.

---

## WI-2.5 `forge/executor.py`

```python
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
    shared: Dict[str, Any]                  # outputs of earlier steps: shared[step_id] = record.data
    project_dir: Optional[Path]
    workspace_dir: Path
    cancel: threading.Event
    log: Callable[[str], None]              # appends a "log" event (bounded to 2 KB per line)


@dataclass
class StepOutcome:
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    repairable: bool = False                # handler says a retry after repair may succeed
    blocked: bool = False                   # environment problem (engine missing, approval revoked): no retry


Handler = Callable[[StepContext], StepOutcome]
RepairHook = Callable[[StepContext, StepOutcome], bool]   # returns True if it changed something worth retrying


class ForgeExecutor:
    def __init__(self, handlers: Dict[str, Handler], repair_hooks: Optional[Dict[str, RepairHook]] = None,
                 bus: Optional[core_events.EventBus] = None):
        self.handlers = handlers
        self.repair_hooks = repair_hooks or {}
        self.bus = bus or core_events.default_bus()
        self._run_cancel = threading.Event()                 # user cancelled the whole run
        self._step_cancel: Optional[threading.Event] = None  # current step (also set on timeout)

    def request_cancel(self) -> None:
        """Called from the UI thread. Stops the current step and prevents further steps."""
        self._run_cancel.set()
        ev = self._step_cancel
        if ev is not None:
            ev.set()

    # -- public -------------------------------------------------------------------------------
    def run(self, state: RunState, store: RunStore, editor_running: Callable[[], bool] = lambda: False) -> RunState:
        """Execute until DONE, FAILED, CANCELLED, BLOCKED or WAITING_APPROVAL. Safe to call again to resume."""
        run = state.run
        repo = ProjectRepo(Path(run.project_dir)) if run.project_dir else None
        self._recover_interrupted(state)
        state.status = "RUNNING"
        self._persist(state, store, {"kind": "run_started"})
        if self._needs_run_approval(state):
            return self._suspend(state, store, "run")
        eff: Dict[str, str] = {}   # effective hash = own inputs + dependencies' effective hashes
        for step in run.topo_order():
            eff[step.step_id] = canonical_hash({"self": step.input_hash,
                                                "deps": [eff[d] for d in sorted(step.depends_on)]})
            rec = state.records[step.step_id]
            if self._run_cancel.is_set():
                return self._finish(state, store, "CANCELLED")
            if rec.status == StepStatus.DONE and rec.input_hash == eff[step.step_id]:
                continue                                   # resume / incremental: unchanged work is skipped
            if rec.status in TERMINAL and rec.status != StepStatus.DONE:
                continue                                   # FAILED/BLOCKED/SKIPPED stay until the run is re-planned
            if any(state.records[d].status != StepStatus.DONE for d in step.depends_on):
                rec.status = StepStatus.BLOCKED
                rec.errors = [f"dependency not done: {[d for d in step.depends_on if state.records[d].status != StepStatus.DONE]}"]
                self._persist(state, store, {"kind": "step_blocked", "step_id": step.step_id})
                continue
            if step.approval == "step" and step.step_id not in state.approvals:
                return self._suspend(state, store, step.step_id)
            self._run_step(state, store, step, rec, repo, editor_running, eff[step.step_id])
            # A FAILED step needs no special handling: its dependants become BLOCKED by the dependency check above.
        final = "DONE" if all(r.status == StepStatus.DONE for r in state.records.values()) else (
            "CANCELLED" if self._run_cancel.is_set() else "FAILED")
        return self._finish(state, store, final)

    # -- internals ----------------------------------------------------------------------------
    def _run_step(self, state, store, step, rec, repo, editor_running, eff_hash: str) -> None:
        handler = self.handlers.get(step.kind.value)
        if handler is None:
            rec.status, rec.errors = StepStatus.BLOCKED, [f"no handler for step kind {step.kind.value}"]
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
            ctx = StepContext(state.run, step, rec, shared, Path(state.run.project_dir) if state.run.project_dir else None,
                              Path(state.run.workspace_dir), self._step_cancel,
                              lambda line, sid=step.step_id: store.append_event(
                                  state.run.run_id, {"kind": "log", "step_id": sid, "line": line[:2048]}))
            try:
                if step.engine_lock:
                    with ENGINE_LOCK:
                        out = self._with_timeout(handler, ctx, step.timeout_s)
                else:
                    out = self._with_timeout(handler, ctx, step.timeout_s)
            except Exception as exc:  # a handler crash is a typed step failure, never a crashed run
                out = StepOutcome(False, errors=[f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=4)])
            rec.finished_at, rec.ok, rec.data = time.time(), out.ok, out.data
            rec.errors = out.errors
            rec.artifacts = [ArtifactRef.model_validate(a) for a in out.artifacts]
            if out.ok:
                if repo is not None and step.checkpoint and repo.available:
                    try:
                        repo.ensure()
                        rec.checkpoint = repo.commit(f"forge: {step.step_id} ({state.run.run_id})")
                    except CheckpointError as exc:
                        rec.data = {**rec.data, "checkpoint_warning": str(exc)}
                rec.status = StepStatus.DONE
                self._persist(state, store, {"kind": "step_finished", "step_id": step.step_id, "ok": True,
                                             "duration_s": rec.duration_s})
                return
            if self._run_cancel.is_set():
                rec.status = StepStatus.CANCELLED
            elif out.blocked:
                rec.status = StepStatus.BLOCKED
            elif rec.attempts < step.max_attempts and out.repairable and \
                    self.repair_hooks.get(step.kind.value, lambda c, o: False)(ctx, out):
                self._persist(state, store, {"kind": "step_repairing", "step_id": step.step_id,
                                             "attempt": rec.attempts, "errors": out.errors[:5]})
                continue
            else:
                rec.status = StepStatus.FAILED
            self._persist(state, store, {"kind": "step_finished", "step_id": step.step_id, "ok": False,
                                         "status": rec.status.value, "errors": out.errors[:10]})
            return

    def _with_timeout(self, handler, ctx, timeout_s) -> StepOutcome:
        """Handlers must poll ctx.cancel; on timeout we set cancel and wait up to 60 s for the handler to return."""
        box: Dict[str, Any] = {}

        def target() -> None:
            try:
                box["out"] = handler(ctx)
            except Exception as exc:  # exceptions in this thread would otherwise be lost
                box["exc"] = f"{type(exc).__name__}: {exc}"
                box["tb"] = traceback.format_exc(limit=4)

        t = threading.Thread(target=target, daemon=True, name=f"forge-{ctx.step.step_id}")
        t.start()
        t.join(timeout_s)
        if t.is_alive():
            ctx.cancel.set()          # stops this step only; the run then records the step as FAILED (TIMEOUT)
            t.join(60)
            return StepOutcome(False, errors=[f"TIMEOUT after {timeout_s:.1f}s"])
        if "exc" in box:
            return StepOutcome(False, errors=[box["exc"], box["tb"]])
        return box.get("out") or StepOutcome(False, errors=["handler returned nothing"])

    def _recover_interrupted(self, state: RunState) -> None:
        for rec in state.records.values():
            if rec.status in (StepStatus.RUNNING, StepStatus.WAITING_APPROVAL):
                rec.status = StepStatus.PENDING          # crashed mid-step: re-run it (handlers are idempotent)

    def _needs_run_approval(self, state: RunState) -> bool:
        return any(s.approval == "run" for s in state.run.steps) and "run" not in state.approvals

    def _suspend(self, state, store, key: str) -> RunState:
        state.status = "WAITING_APPROVAL"
        if key != "run":
            state.records[key].status = StepStatus.WAITING_APPROVAL
        self._persist(state, store, {"kind": "approval_needed", "key": key})
        return state

    def _finish(self, state, store, status: str) -> RunState:
        state.status = status
        self._persist(state, store, {"kind": "run_finished", "status": status})
        return state

    def _persist(self, state: RunState, store: RunStore, event: Dict[str, Any]) -> None:
        state.updated_at = time.time()
        store.save(state)
        ev = {"run_id": state.run.run_id, **event}
        store.append_event(state.run.run_id, ev)
        self.bus.publish("forge", ev)
```

**Handler contract (write it in `forge/handlers/__init__.py`'s docstring):**
1. **Idempotent:** a handler may be re-run after a crash, so it must not fail just because its output already exists.
2. **Cancellable:** poll `ctx.cancel` at least every 2 s in loops, and pass it to the toolchain (`toolchain.cancel_event`).
3. **Fail closed:** return `StepOutcome(False, ...)`. Never raise for expected failures.
4. **Evidence:** artifacts are paths inside the project's `Saved/GameForge/evidence/` or the run dir.
5. Use `blocked=True` for environment problems (engine missing, VRAM scheduler refusal, approval revoked).

**Tests (`test_forge_executor.py`):** use fake handlers.
- A happy path of 3 steps writes `DONE` with persistence after each transition (count the `store.save` calls).
- A failure blocks dependants and leaves independent branches running.
- Resume: run, mutate a record to RUNNING, run again → that step re-runs and DONE steps are skipped (count handler calls).
- Input-hash change: alter one step's inputs → that step **and every step downstream of it** re-run (effective hash
  includes dependencies), and steps upstream are skipped.
- Approval `run` suspends before any step. Approving (`state.approvals["run"]="apr_x"`) and re-running proceeds.
- `max_attempts=3` with a repair hook that returns True twice and a handler that succeeds on the third try → DONE, attempts 3.
- Timeout: a handler sleeps past `timeout_s=0.5` → FAILED "TIMEOUT".
- A handler exception → FAILED with the exception text and no crash.
- Cancel mid-run → the remaining steps stay PENDING and the run is CANCELLED.

---

## WI-2.6 Legacy pipeline on Forge (`forge/handlers/legacy_stages.py`, `forge/legacy_adapter.py`)

1. Move each closure from `GamePipeline.run` (`s_spec`, `s_scaffold`, `s_sources`, `s_build`, `s_assemble`,
   `s_tests`, `s_package`, `s_smoke`) into handler functions in `legacy_stages.py`. Signature:
   `def legacy_scaffold(ctx: StepContext) -> StepOutcome`. They read `ctx.step.inputs["params"]` (the recipe params as
   a dict plus `"recipe_id"`) and rebuild the params object with the recipe's dataclass
   (`PARAMS_BY_RECIPE = {"grid_board_game": GridBoardParams, ...}`). They store what later steps need in `data`:
   `build_editor` → `{"exit_code", "log", "errors", "warnings", "diagnostics"}`; `package` →
   `{"exe": ...}`, which `packaged_smoke` reads from `ctx.shared["package"]["exe"]`. Recipe dispatch (the if/elif
   chain) moves into a small table, `RECIPE_IMPL[recipe_id] = (generate, assemble_fn, module_deps, default_gm_fmt,
   selftest_pass)`, so each handler does a lookup instead of an `isinstance` chain.
2. `legacy_adapter.plan_legacy(params, skip_package=False) -> RunSpec`: steps `spec → scaffold → sources →
   build_editor → assemble_level → automation_tests → package → packaged_smoke`, in a linear chain, with
   `engine_lock=True` on build/assemble/tests/package/smoke and `approval="none"`. The UI approval happened before the
   run, and the approval id goes into `state.approvals["run"]`.
3. `GamePipeline.run(params, skip_package, stop_after)` becomes: build the RunSpec → `RunState.new` →
   `ForgeExecutor(HANDLERS).run(...)` → translate it into the existing `PipelineResult` / `StageRecord` objects and
   write the same `pipeline_report.json`/`.md` (`render_markdown` unchanged). `on_event` callbacks keep firing
   `stage_started` / `stage_finished` / `pipeline_finished` with the same payloads, through a bus subscriber, so
   `action_runner` and the approval card keep working unchanged. `stop_after` → mark later steps `SKIPPED` before
   running.
4. **Project checkpoints:** the scaffold step's handler calls `ProjectRepo(project_dir).ensure()` after writing
   files. Every later DONE step commits.
5. **Resume entry point:** `GamePipeline.resume(project_dir)` → `RunStore.latest_for_project` → executor.run. Add
   `--resume <project_dir>` to `scripts/pipeline/run_game_pipeline.py`. The existing script already had `--resume`
   semantics through evidence; keep the flag name and change only the implementation.
6. **Tests:** `tests/unit/test_game_pipeline.py` must pass **unchanged**. If one needs a change, explain why in the
   commit. New `test_forge_legacy_adapter.py`: with fake stage handlers (monkeypatch `HANDLERS`), the adapter
   produces the 8-step chain, translates results to `PipelineResult`, and resume skips done steps.

**Engine gate (mandatory):**
```powershell
python scripts\pipeline\run_game_pipeline.py --prompt "create a tic tac toe game"     # PASS, git log shows 8 forge commits
# Kill test: start the platformer run, then kill python.exe when the log shows build_editor RUNNING
python scripts\pipeline\run_game_pipeline.py --prompt "make a platformer with 6 coins"
python scripts\pipeline\run_game_pipeline.py --resume E:\GameForge\projects\Platformer   # spec/scaffold/sources skipped, completes PASS
```
Evidence: `reports/P2/resume_kill_test.json` with the events of both runs, the skipped-step list and the final status.
**Rollback check:** `ProjectRepo(...).reset_to(<scaffold checkpoint>, editor_running=False)`, then verify that
`Source/` matches the checkpoint (`git status --porcelain` empty) and that the game sources from `sources` are gone.
Record this in `reports/P2/rollback_check.json`. Then re-run to completion.

---

## WI-2.7 Agent plans on Forge (`forge/handlers/tool_call.py`, `forge/plan_adapter.py`)

- `plan_to_run(plan: TaskPlan, workspace: Path) -> RunSpec`: one `TOOL_CALL` step per `TaskNode`, with
  `depends_on = dependency_ids`, `inputs = {"tool": name, "arguments": args, "acceptance": [p.model_dump() for p in
  task.acceptance], "permitted_tools": ..., "repetition_limit": 3}`, `approval = "step" if task.requires_approval else
  "none"` and `engine_lock = tool == "unreal_editor" and op is not read-only`.
- The `tool_call` handler calls `ToolGateway.execute_tool(name, args, approval_granted=<step approved>)` and then
  evaluates predicates with `TaskState.evaluate_acceptance` (P0 semantics: no tool + no predicates = NO_EVIDENCE). It
  also enforces `permitted_tools`. The repetition limit is per-run state stored in `ctx.shared["_repetition"]`.
- `desktop/services/plan_runner.py` uses the adapter + executor. `TaskPlanExecutor` stays in place (tests and demos)
  but is marked deprecated in its docstring. P4 removes its UI use, and P6 deletes it once nothing imports it.
- Re-run `scripts/engine/demo_real_unreal_plan.py`, `demo_real_repo_plan.py` and `demo_real_failure_plan.py` through the
  adapter (add a `--forge` flag). Expect the same verdicts. Evidence: `reports/P2/plan_demos_forge.json`.

---

## WI-2.8 Approval scopes, events to the UI, op-schema enforcement

1. **Run approval record:** `ApprovalStore.create(tool="forge_run", args={"run_id", "project_dir", "scope": {...}})`.
   The scope lists `paths` (project dir), `engine` ("editor ops in this project"), `packaging` (true/false) and
   `estimated_minutes`. Approving it sets `state.approvals["run"]` and resumes the run on a JobManager job. The
   existing approval card shows the scope lines.
2. `desktop/services/forge_service.py`: a `QObject` with signals `runEvent(dict)` and `runListChanged()`. It
   subscribes to `core.events.default_bus()` and re-emits through a `Qt.QueuedConnection`, so handlers never touch Qt.
   `action_runner.py` moves onto `JobManager` + Forge. Keep its public signals so the approval card keeps working.
3. **Op schemas mandatory (AD-14):** complete `op_schemas.py` for all agent-visible ops (126 − DIAGNOSTIC − LEGACY).
   `validate_args` returns an error for an unknown schema when `strict=True`. `GameTools.unreal_editor` and (P6) the
   composer use `strict=True`; demos keep calling the link directly. Test: every `op_catalog.agent_ops()` op has a schema.
   The native tool definition for `unreal_editor` gets a JSON schema with `oneOf` per op **only for hosted models**.
   For local models, the description lists the ops and the gateway validates (a 120-way `oneOf` overwhelms 4B/9B
   models; P9 measures this).

## Phase exit gate
1. Unit suite green, including the new Forge tests and the unchanged `test_game_pipeline.py`.
2. `reports/P2/resume_kill_test.json`, `rollback_check.json` and `plan_demos_forge.json` are present and PASS.
3. A job-object leak test passes: kill the IDE process during a build and find no `UnrealEditor`/`UnrealBuildTool`/
   `dotnet` children afterwards. Evidence: `reports/P2/job_object_leak_test.json`.
4. `scripts\verify_all.ps1` full run green. Context, status and progress updated.

## Failure cases and prevention
- **Windows file locks:** the editor or antivirus locks `.uasset`s, so the git commit or the atomic replace fails.
  Retry with backoff in `RunStore`. A commit failure is a *warning* on the step (`checkpoint_warning`), not a step
  failure, and is surfaced in the Build view.
- **Non-idempotent handlers:** scaffold must tolerate an existing project dir (it already overwrites sources with
  `overwrite_source=True`). Package must clear the previous `Packaged/` output first.
- **Timeout leaves a zombie engine:** on timeout the executor sets cancel. The toolchain's cancel kills the process
  tree, and the job object is the final backstop.
- **Two runs on one project:** `RunStore` takes a lock file `<run_dir>/../.lock` (`msvcrt.locking` or O_EXCL create).
  A second run returns BLOCKED "another run is active on this project (run_x)".

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 2.1 | DONE | 2026-10-31T12:42Z | 2026-10-31T12:44Z | test_forge_model (9 passed); DAG validation, Kahn cycle check, stable topo_order, canonical_hash |
| 2.2 | DONE | 2026-10-31T12:45Z | 2026-10-31T12:46Z | test_forge_store (6 passed); atomic persistence with lock retry, event logging, latest_for_project, runs index |
| 2.3 | DONE | 2026-10-31T12:46Z | 2026-10-31T12:47Z | test_forge_checkpoints (5 passed); ensure, commit, rollback/reset_to, editor guard, MAX_COMMIT_MB guard |
| 2.4 | TODO | | | |
| 2.5 | TODO | | | |
| 2.6 | TODO | | | |
| 2.7 | TODO | | | |
| 2.8 | TODO | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
