"""Structured, Dependency-Aware Multi-Step Task Plan (DAG) for GameForge IDE.

Authoritative specification compliant with GameForge Master Blueprint:
- Directed Acyclic Graph (DAG) representation of multi-step work.
- Validation rejects circular dependencies, missing prerequisites, duplicate IDs, invalid task references.
- Explicit lifecycle states: PLANNED, READY, RUNNING, WAITING_APPROVAL, VERIFYING, REPAIRING, COMPLETED, BLOCKED, FAILED, CANCELLED.
- Only the execution harness assigns terminal states based on observed acceptance criteria.
- Transitive dependency blocking on branch failures without interrupting independent branches.
- Atomic persistence and crash-safe restoration.
"""

from __future__ import annotations

import collections
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from pydantic import BaseModel, Field

from .task_state import TaskAcceptancePredicate

TaskNodeStatus = Literal[
    "PLANNED",
    "READY",
    "RUNNING",
    "WAITING_APPROVAL",
    "VERIFYING",
    "REPAIRING",
    "COMPLETED",
    "BLOCKED",
    "FAILED",
    "CANCELLED",
]

ReversibilityLevel = Literal["read-only", "transactional", "snapshot-only", "irreversible"]


class TaskNode(BaseModel):
    """Single node in the execution DAG representing a unit of verifiable work."""

    task_id: str
    title: str
    objective: str
    expected_result: str
    task_type: str = "custom"  # "inspect", "mutate", "build", "test", "editor_op", "custom"
    permitted_tools: List[str] = Field(default_factory=list)
    dependency_ids: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    acceptance: List[TaskAcceptancePredicate] = Field(default_factory=list)
    resources: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    reversibility: ReversibilityLevel = "read-only"
    timeout_seconds: float = 120.0
    retry_limit: int = 2
    retry_count: int = 0
    recovery_behavior: str = "retry"  # "retry", "repair", "abort_branch", "fail"
    status: TaskNodeStatus = "PLANNED"
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    tool_call: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    approval_id: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def is_terminal(self) -> bool:
        return self.status in ("COMPLETED", "BLOCKED", "FAILED", "CANCELLED")

    def is_ready(self, completed_ids: Set[str]) -> bool:
        return self.status == "PLANNED" and all(dep in completed_ids for dep in self.dependency_ids)


class PlanValidationError(ValueError):
    """Raised when plan graph topology or configuration is invalid."""
    pass


class TaskPlan(BaseModel):
    """Directed Acyclic Graph (DAG) plan for executing complex multi-step objectives."""

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    session_id: Optional[str] = None
    goal: str
    tasks: Dict[str, TaskNode] = Field(default_factory=dict)
    status: TaskNodeStatus = "PLANNED"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    final_acceptance: List[TaskAcceptancePredicate] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_task(self, task: TaskNode) -> None:
        """Add a task node to the plan."""
        self.tasks[task.task_id] = task
        self.updated_at = time.time()

    def validate(self) -> Tuple[bool, List[str]]:
        """Validates DAG properties: no missing prerequisites, no self-loops, no cycles."""
        errors: List[str] = []

        if not self.tasks:
            errors.append("Plan contains no tasks")
            return False, errors

        # 1. Check for missing prerequisites and self-dependencies
        all_ids = set(self.tasks.keys())
        for tid, task in self.tasks.items():
            if task.task_id != tid:
                errors.append(f"Task key mismatch: key '{tid}' != task_id '{task.task_id}'")
            for dep in task.dependency_ids:
                if dep == tid:
                    errors.append(f"Self-dependency detected on task '{tid}'")
                elif dep not in all_ids:
                    errors.append(f"Missing prerequisite: task '{tid}' depends on non-existent '{dep}'")

        if errors:
            return False, errors

        # 2. Cycle detection via Kahn's algorithm (topological sort)
        in_degree: Dict[str, int] = {tid: len(self.tasks[tid].dependency_ids) for tid in self.tasks}
        graph: Dict[str, List[str]] = collections.defaultdict(list)
        for tid, task in self.tasks.items():
            for dep in task.dependency_ids:
                graph[dep].append(tid)

        queue = collections.deque([tid for tid, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            current = queue.popleft()
            visited_count += 1
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count < len(self.tasks):
            cyclic_tasks = [tid for tid, deg in in_degree.items() if deg > 0]
            errors.append(f"Circular dependency detected involving tasks: {cyclic_tasks}")
            return False, errors

        return True, []

    def get_topological_order(self) -> List[str]:
        """Returns task IDs in valid topological dependency order.

        Raises:
            PlanValidationError: If the graph has cycles or invalid prerequisites.
        """
        valid, errors = self.validate()
        if not valid:
            raise PlanValidationError("; ".join(errors))

        in_degree: Dict[str, int] = {tid: len(self.tasks[tid].dependency_ids) for tid in self.tasks}
        graph: Dict[str, List[str]] = collections.defaultdict(list)
        for tid, task in self.tasks.items():
            for dep in task.dependency_ids:
                graph[dep].append(tid)

        queue = collections.deque([tid for tid, deg in in_degree.items() if deg == 0])
        order: List[str] = []

        while queue:
            current = queue.popleft()
            order.append(current)
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return order

    def get_ready_tasks(self) -> List[TaskNode]:
        """Returns all tasks whose prerequisites are COMPLETED and whose status is PLANNED."""
        completed_ids = {tid for tid, t in self.tasks.items() if t.status == "COMPLETED"}
        ready: List[TaskNode] = []
        for task in self.tasks.values():
            if task.status == "PLANNED" and all(dep in completed_ids for dep in task.dependency_ids):
                ready.append(task)
        return ready

    def block_descendants(self, failed_task_id: str, reason: str) -> List[str]:
        """Transitively marks all tasks dependent on failed_task_id as BLOCKED.

        Independent parallel branches remain unblocked.
        """
        # Build forward adjacency list
        downstream: Dict[str, List[str]] = collections.defaultdict(list)
        for tid, task in self.tasks.items():
            for dep in task.dependency_ids:
                downstream[dep].append(tid)

        blocked_ids: List[str] = []
        queue = collections.deque(downstream.get(failed_task_id, []))
        visited: Set[str] = set()

        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            task = self.tasks.get(current_id)
            if task and not task.is_terminal():
                task.status = "BLOCKED"
                task.error_message = f"Blocked: upstream dependency '{failed_task_id}' failed ({reason})"
                task.completed_at = time.time()
                blocked_ids.append(current_id)

            for child in downstream.get(current_id, []):
                if child not in visited:
                    queue.append(child)

        self.updated_at = time.time()
        return blocked_ids

    def save(self, workspace_root: Path) -> Path:
        """Persists the plan atomically to <workspace>/.gameforge/plans/{plan_id}.json."""
        plans_dir = Path(workspace_root) / ".gameforge" / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        target_path = plans_dir / f"{self.plan_id}.json"
        temp_path = target_path.with_suffix(".tmp")
        self.updated_at = time.time()
        temp_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temp_path, target_path)
        return target_path

    @classmethod
    def load(cls, file_path: Path) -> TaskPlan:
        """Loads a persisted TaskPlan from disk."""
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        return cls(**data)

    @classmethod
    def load_by_id(cls, workspace_root: Path, plan_id: str) -> Optional[TaskPlan]:
        """Loads a plan by ID from <workspace>/.gameforge/plans/{plan_id}.json."""
        target = Path(workspace_root) / ".gameforge" / "plans" / f"{plan_id}.json"
        if not target.is_file():
            return None
        return cls.load(target)

    @classmethod
    def list_plans(cls, workspace_root: Path) -> List[TaskPlan]:
        """Returns all persisted plans in descending order of update time."""
        plans_dir = Path(workspace_root) / ".gameforge" / "plans"
        if not plans_dir.is_dir():
            return []
        plans: List[TaskPlan] = []
        for p in plans_dir.glob("plan_*.json"):
            try:
                plans.append(cls.load(p))
            except Exception:
                continue
        plans.sort(key=lambda x: x.updated_at, reverse=True)
        return plans
