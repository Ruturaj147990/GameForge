"""Task State, Acceptance Predicates, and Ledger for GameForge IDE Agent Runtime.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026).
Enforces:
- Deterministic acceptance predicates over observed state.
- Write-ahead ledger of actions and evidence.
- Pinned goal immutability.
- Terminal status set exclusively by the application harness.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


TaskIntent = Literal["answer", "inspect", "plan", "mutate", "validate"]
TaskPhase = Literal["discover", "plan", "author", "validate", "repair"]
TerminalStatus = Literal["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"]


class TaskAcceptancePredicate(BaseModel):
    """Machine-checkable definition of done evaluated against real observed state."""
    predicate_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    predicate_type: Literal[
        "file_changed", "file_exists", "build_ok", "tests_pass", "asset_exists", "custom"
    ]
    target: str  # e.g., "Source/MyGame/MyGame.uproject", "Health*.cpp", "/Game/Props/SM_Crate"
    expected: Optional[Any] = None
    satisfied: bool = False
    evidence: Optional[str] = None
    evaluated_at: Optional[float] = None


class TaskBudget(BaseModel):
    """Hard execution and token limits enforced outside the model."""
    max_iterations: int = 12
    max_tokens: int = 32768
    timeout_seconds: float = 180.0
    max_repetition_count: int = 3
    started_at: float = Field(default_factory=time.time)

    def is_timed_out(self) -> bool:
        return (time.time() - self.started_at) > self.timeout_seconds


class PendingApproval(BaseModel):
    """State of an operation awaiting developer review."""
    approval_id: str
    diff_id: str
    file_path: str
    base_hash: str
    created_at: float = Field(default_factory=time.time)
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))


class LedgerEntry(BaseModel):
    """Append-only write-ahead log entry for an intended or executed action."""
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    phase: str
    action_type: str  # "intent", "tool_call", "tool_result", "diff_apply", "verification"
    payload: Dict[str, Any] = Field(default_factory=dict)
    pre_state_hash: Optional[str] = None
    post_state_hash: Optional[str] = None
    exit_code: Optional[int] = None
    diagnostics: Optional[str] = None


class TaskState(BaseModel):
    """Authoritative task object tracking life cycle, predicates, and ledger."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    goal: str  # User's request, byte-exact, never summarized
    intent: TaskIntent = "mutate"
    phase: TaskPhase = "discover"
    acceptance: List[TaskAcceptancePredicate] = Field(default_factory=list)
    budget: TaskBudget = Field(default_factory=TaskBudget)
    snapshot_id: Optional[str] = None
    pending_approval: Optional[PendingApproval] = None
    ledger: List[LedgerEntry] = Field(default_factory=list)
    terminal_status: Optional[TerminalStatus] = None
    terminal_reason: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def record_intent(self, description: str, tool_name: str, args: Dict[str, Any]) -> LedgerEntry:
        entry = LedgerEntry(
            phase=self.phase,
            action_type="intent",
            payload={"description": description, "tool": tool_name, "args": args},
        )
        self.ledger.append(entry)
        self.updated_at = time.time()
        return entry

    def record_result(
        self,
        tool_name: str,
        result: Dict[str, Any],
        pre_hash: Optional[str] = None,
        post_hash: Optional[str] = None,
        exit_code: Optional[int] = 0,
        diagnostics: Optional[str] = None,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            phase=self.phase,
            action_type="tool_result",
            payload={"tool": tool_name, "result": result},
            pre_state_hash=pre_hash,
            post_state_hash=post_hash,
            exit_code=exit_code,
            diagnostics=diagnostics,
        )
        self.ledger.append(entry)
        self.updated_at = time.time()
        return entry

    def evaluate_acceptance(
        self,
        workspace_root: Path,
        modified_files: set[str],
        tool_history: list[dict],
    ) -> tuple[bool, List[str]]:
        """Evaluates all acceptance predicates against real filesystem and execution evidence."""
        unmet: List[str] = []
        now = time.time()

        for pred in self.acceptance:
            pred.evaluated_at = now
            if pred.predicate_type == "file_exists":
                target_path = (workspace_root / pred.target).resolve()
                if target_path.exists():
                    pred.satisfied = True
                    pred.evidence = f"File exists at {pred.target} ({target_path.stat().st_size} bytes)"
                else:
                    pred.satisfied = False
                    unmet.append(f"file_exists({pred.target}): File does not exist on disk")

            elif pred.predicate_type == "file_changed":
                # Check if target matches any modified file or exists on disk
                matched = False
                for mf in modified_files:
                    if fnmatch.fnmatch(mf, pred.target) or mf == pred.target:
                        matched = True
                        break
                if not matched:
                    # Also check if target file exists and was created
                    tp = (workspace_root / pred.target).resolve()
                    if tp.exists():
                        matched = True

                if matched:
                    pred.satisfied = True
                    pred.evidence = f"File {pred.target} verified modified/created on disk"
                else:
                    pred.satisfied = False
                    unmet.append(f"file_changed({pred.target}): No approved modification observed for path")

            elif pred.predicate_type == "build_ok":
                # Look for successful build execution in tool history
                build_succeeded = any(
                    th.get("tool_name") in ("unreal_stage_build", "run_command", "terminal_run")
                    and th.get("status") == "SUCCESS"
                    and (th.get("exit_code") == 0 or "SUCCESS" in str(th.get("output", "")))
                    for th in tool_history
                )
                if build_succeeded:
                    pred.satisfied = True
                    pred.evidence = "Build executed with exit code 0"
                else:
                    pred.satisfied = False
                    unmet.append("build_ok(): Permitted build has not completed successfully")

            elif pred.predicate_type == "tests_pass":
                tests_succeeded = any(
                    "pytest" in str(th.get("arguments", {}))
                    and th.get("status") == "SUCCESS"
                    for th in tool_history
                )
                if tests_succeeded:
                    pred.satisfied = True
                    pred.evidence = f"Tests matching {pred.target} passed"
                else:
                    pred.satisfied = False
                    unmet.append(f"tests_pass({pred.target}): Required tests have not passed")

            elif pred.predicate_type == "asset_exists":
                # Asset existence check in quarantine or content
                asset_succeeded = any(
                    th.get("tool_name") == "unreal_asset_exists"
                    and th.get("arguments", {}).get("asset_path") == pred.target
                    and th.get("output", {}).get("exists") is True
                    for th in tool_history
                )
                if asset_succeeded:
                    pred.satisfied = True
                    pred.evidence = f"Asset {pred.target} verified via Unreal read-back"
                else:
                    pred.satisfied = False
                    unmet.append(f"asset_exists({pred.target}): Asset read-back unconfirmed")

            elif pred.predicate_type == "custom":
                if not pred.satisfied:
                    unmet.append(f"custom({pred.target}): Condition not yet satisfied")

        all_satisfied = len(unmet) == 0
        return all_satisfied, unmet
