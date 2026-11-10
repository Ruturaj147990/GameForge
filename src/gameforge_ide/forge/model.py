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
    DESIGN = "design"
    SCAFFOLD = "scaffold"
    CODEGEN = "codegen"
    BUILD = "build"
    ASSEMBLE = "assemble"
    CONTENT = "content"
    AUTOMATION = "automation"
    PACKAGE = "package"
    SCENARIO = "scenario"
    REVIEW = "review"
    REPORT = "report"
    TOOL_CALL = "tool_call"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    DONE = "DONE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    INTERRUPTED = "INTERRUPTED"


TERMINAL = {
    StepStatus.DONE,
    StepStatus.FAILED,
    StepStatus.BLOCKED,
    StepStatus.SKIPPED,
    StepStatus.CANCELLED,
    StepStatus.INTERRUPTED,
}


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


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
    checkpoint: bool = True  # commit the project after DONE (needs a project repo)

    @property
    def id(self) -> str:
        return self.step_id

    @property
    def input_hash(self) -> str:
        return canonical_hash({"kind": self.kind.value, "inputs": self.inputs})


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    kind: Literal["log", "report", "screenshot", "package", "scenario_result", "other"] = "other"
    sha256: Optional[str] = None


class StepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    checkpoint: Optional[str] = None  # git commit sha after DONE

    @property
    def id(self) -> str:
        return self.step_id

    @property
    def duration_s(self) -> Optional[float]:
        if self.started_at is not None and self.finished_at is not None:
            return round(max(0.0, self.finished_at - self.started_at), 1)
        return None


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(default_factory=lambda: "run_" + time.strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(3))
    title: str
    origin: Literal["prompt", "change_request", "agent_plan", "cli", "test"] = "cli"
    project_dir: Optional[str] = None  # None for workspace-only runs (agent plans)
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
        indeg = {s.step_id: len(set(s.depends_on)) for s in steps}
        children: Dict[str, List[str]] = {i: [] for i in ids}
        for s in steps:
            for d in set(s.depends_on):
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
            found = False
            for s in pending:
                if all(d in done for d in s.depends_on):
                    order.append(s)
                    done.add(s.step_id)
                    pending.remove(s)
                    found = True
                    break
            if not found:
                remaining = [s.step_id for s in pending]
                raise ValueError(f"dependency cycle or unresolvable dependencies: {remaining}")
        return order


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run: RunSpec
    records: Dict[str, StepRecord]
    status: Literal[
        "PENDING",
        "RUNNING",
        "WAITING_APPROVAL",
        "DONE",
        "FAILED",
        "CANCELLED",
        "BLOCKED",
        "INTERRUPTED",
    ] = "PENDING"
    approvals: Dict[str, str] = Field(default_factory=dict)  # "run" or step_id -> approval_id
    updated_at: float = Field(default_factory=time.time)

    @classmethod
    def new(cls, run: RunSpec) -> "RunState":
        return cls(run=run, records={s.step_id: StepRecord(step_id=s.step_id) for s in run.steps})
