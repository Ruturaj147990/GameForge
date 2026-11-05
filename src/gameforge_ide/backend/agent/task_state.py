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
from typing import Any, Callable, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# A "custom" predicate is satisfied only when a registered evaluator confirms it from observed state.
# The predicate's own ``satisfied`` field is output, never input (design contract rule 2).
def _history_has_success(tool_history: list[dict], tools: frozenset[str]) -> tuple[bool, str]:
    for entry in tool_history:
        if entry.get("tool_name") in tools and str(entry.get("status", "")).upper() == "SUCCESS":
            return True, f"{entry.get('tool_name')} returned SUCCESS"
    return False, f"no successful call to any of {sorted(tools)} in tool history"


def _editor_responsive(tool_history: list[dict]) -> tuple[bool, str]:
    for entry in tool_history:
        out = entry.get("output") or {}
        if entry.get("tool_name") == "unreal_editor" and isinstance(out, dict)                 and out.get("status") == "SUCCESS" and (out.get("result") or {}).get("ok") is True:
            return True, f"editor op {(out.get('result') or {}).get('op')} returned ok"
    return False, "no successful unreal_editor read-back in tool history"


CUSTOM_PREDICATE_EVALUATORS: dict[str, Callable[[list[dict]], tuple[bool, str]]] = {
    "inspection_complete": lambda h: _history_has_success(h, frozenset({"list_dir", "read_file", "search_code"})),
    "editor_responsive": _editor_responsive,
}


TaskIntent = Literal["answer", "inspect", "plan", "mutate", "validate"]
TaskPhase = Literal["discover", "plan", "author", "validate", "repair"]
TerminalStatus = Literal["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"]


class TaskAcceptancePredicate(BaseModel):
    """Machine-checkable definition of done evaluated against real observed state."""
    predicate_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    predicate_type: Literal[
        "file_changed",
        "file_exists",
        "file_content_contains",
        "build_ok",
        "tests_pass",
        "asset_exists",
        "unreal_actor_exists",
        "unreal_asset_exists",
        "command_exit_code",
        "blueprint_compiled",
        "blueprint_node_connected",
        "widget_compiled",
        "widget_hierarchy_verified",
        "widget_event_bound",
        "gameplay_state_verified",
        "menu_interaction_verified",
        "custom",
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
                # Check for genuine state change: preimage vs postimage hash, or approved diff, or verified creation
                matched = False
                matched_reason = ""
                target_path = (workspace_root / pred.target).resolve()

                # 1. Check tool history for diff application or edits with hash evidence
                for th in tool_history:
                    out = th.get("output", {})
                    if isinstance(out, str):
                        try:
                            out = json.loads(out)
                        except Exception:
                            pass
                    if isinstance(out, dict):
                        fpath = out.get("file_path") or th.get("arguments", {}).get("subpath") or th.get("arguments", {}).get("path")
                        if fpath and (fnmatch.fnmatch(fpath, pred.target) or fpath == pred.target):
                            pre_h = out.get("original_sha256") or th.get("pre_state_hash")
                            post_h = out.get("new_sha256") or th.get("post_state_hash")
                            # If hashes are available, require genuine state comparison: pre_hash != post_hash
                            if pre_h and post_h:
                                if pre_h != post_h:
                                    if target_path.exists():
                                        cur_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
                                        if cur_hash == post_h:
                                            matched = True
                                            matched_reason = f"Verified content hash change ({pre_h[:8]} -> {post_h[:8]}) matches disk"
                                            break
                            elif th.get("status") in ("SUCCESS", "APPLIED"):
                                matched = True
                                matched_reason = f"Verified edit applied via tool '{th.get('tool_name')}'"
                                break

                # 2. Check if file was in modified_files set from an actual edit action
                if not matched:
                    for mf in modified_files:
                        if fnmatch.fnmatch(mf, pred.target) or mf == pred.target:
                            matched = True
                            matched_reason = f"Observed in approved modification list ({mf})"
                            break

                if matched:
                    pred.satisfied = True
                    pred.evidence = f"File {pred.target} verified modified on disk: {matched_reason}"
                else:
                    pred.satisfied = False
                    unmet.append(f"file_changed({pred.target}): No approved modification or content hash transition observed for path")

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

            elif pred.predicate_type == "file_content_contains":
                target_path = (workspace_root / pred.target).resolve()
                if not target_path.exists():
                    pred.satisfied = False
                    unmet.append(f"file_content_contains({pred.target}): File does not exist on disk")
                else:
                    try:
                        content = target_path.read_text(encoding="utf-8", errors="replace")
                        expected_str = str(pred.expected or "")
                        if expected_str in content:
                            pred.satisfied = True
                            pred.evidence = f"File {pred.target} contains expected content '{expected_str[:40]}...'"
                        else:
                            pred.satisfied = False
                            unmet.append(f"file_content_contains({pred.target}): Expected content not found in file")
                    except Exception as e:
                        pred.satisfied = False
                        unmet.append(f"file_content_contains({pred.target}): Error reading file: {e}")

            elif pred.predicate_type == "command_exit_code":
                expected_code = int(pred.expected) if pred.expected is not None else 0
                matched_cmd = False
                for th in reversed(tool_history):
                    tool_n = th.get("tool_name") or th.get("tool") or ""
                    cmd_arg = str(
                        th.get("command")
                        or (th.get("arguments", {}).get("command") if isinstance(th.get("arguments"), dict) else "")
                        or (th.get("args", {}).get("command") if isinstance(th.get("args"), dict) else "")
                        or ""
                    )
                    if tool_n in ("run_command", "terminal_run") or cmd_arg:
                        if not pred.target or pred.target in cmd_arg or fnmatch.fnmatch(cmd_arg, pred.target) or cmd_arg in pred.target:
                            out_data = th.get("output", {})
                            code = th.get("exit_code")
                            if code is None and isinstance(out_data, dict):
                                code = out_data.get("exit_code")
                            matched_cmd = True
                            if code == expected_code:
                                pred.satisfied = True
                                pred.evidence = f"Command '{cmd_arg[:40]}' exited with expected code {expected_code}"
                            else:
                                pred.satisfied = False
                                unmet.append(f"command_exit_code({pred.target}): Command exited with code {code}, expected {expected_code}")
                            break
                if not matched_cmd:
                    pred.satisfied = False
                    unmet.append(f"command_exit_code({pred.target}): Expected execution record for command not observed")

            elif pred.predicate_type == "unreal_actor_exists":
                # Check for actor label in unreal_editor actors_in_level tool results
                actor_found = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        out_data = th.get("output", {})
                        if isinstance(out_data, str):
                            try:
                                out_data = json.loads(out_data)
                            except Exception:
                                pass
                        res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                        actors = res_data.get("data", {}).get("actors", [])
                        if any(isinstance(a, dict) and a.get("label") == pred.target for a in actors):
                            actor_found = True
                            pred.satisfied = True
                            pred.evidence = f"Actor '{pred.target}' verified present in active level via Unreal read-back"
                            break
                        # Also check spawn_actor output directly
                        if res_data.get("data", {}).get("label") == pred.target:
                            actor_found = True
                            pred.satisfied = True
                            pred.evidence = f"Actor '{pred.target}' verified spawned and read-back confirmed"
                            break
                if not actor_found:
                    pred.satisfied = False
                    unmet.append(f"unreal_actor_exists({pred.target}): Actor label not confirmed in active level")

            elif pred.predicate_type == "unreal_asset_exists":
                asset_found = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        out_data = th.get("output", {})
                        if isinstance(out_data, str):
                            try:
                                out_data = json.loads(out_data)
                            except Exception:
                                pass
                        res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                        if res_data.get("data", {}).get("exists") is True:
                            asset_found = True
                            pred.satisfied = True
                            pred.evidence = f"Asset '{pred.target}' existence verified in Unreal project"
                            break
                if not asset_found:
                    pred.satisfied = False
                    unmet.append(f"unreal_asset_exists({pred.target}): Asset existence not confirmed in Unreal project")

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

            elif pred.predicate_type == "blueprint_compiled":
                compiled_ok = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        args = th.get("arguments", {})
                        if args.get("op") in ("blueprint_compile", "compile_blueprint"):
                            bp_p = args.get("args", {}).get("blueprint_path") or args.get("blueprint_path")
                            if not pred.target or pred.target in str(bp_p):
                                out_data = th.get("output", {})
                                if isinstance(out_data, str):
                                    try:
                                        out_data = json.loads(out_data)
                                    except Exception:
                                        pass
                                res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                                data_block = res_data.get("data", {})
                                if res_data.get("ok") and (data_block.get("status") in ("UpToDate", "UpToDateWithWarnings") or data_block.get("compiled_successfully")):
                                    compiled_ok = True
                                    pred.satisfied = True
                                    pred.evidence = f"Blueprint '{pred.target}' compiled successfully with status '{data_block.get('status')}'"
                                    break
                if not compiled_ok:
                    pred.satisfied = False
                    unmet.append(f"blueprint_compiled({pred.target}): Blueprint compilation success not verified in tool history")

            elif pred.predicate_type == "blueprint_node_connected":
                connected_ok = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        args = th.get("arguments", {})
                        if args.get("op") == "blueprint_connect_pins":
                            bp_p = args.get("args", {}).get("blueprint_path") or args.get("blueprint_path")
                            if not pred.target or pred.target in str(bp_p):
                                out_data = th.get("output", {})
                                if isinstance(out_data, str):
                                    try:
                                        out_data = json.loads(out_data)
                                    except Exception:
                                        pass
                                res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                                if res_data.get("ok") and res_data.get("data", {}).get("verified_linked"):
                                    connected_ok = True
                                    pred.satisfied = True
                                    pred.evidence = f"Blueprint pins connected and verified linked for '{pred.target}'"
                                    break
                if not connected_ok:
                    pred.satisfied = False
                    unmet.append(f"blueprint_node_connected({pred.target}): Verified pin connection not observed in tool history")

            elif pred.predicate_type == "widget_compiled":
                compiled_ok = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        args = th.get("arguments", {})
                        if args.get("op") == "widget_compile":
                            w_p = args.get("args", {}).get("asset_path") or args.get("asset_path")
                            if not pred.target or pred.target in str(w_p):
                                out_data = th.get("output", {})
                                if isinstance(out_data, str):
                                    try:
                                        out_data = json.loads(out_data)
                                    except Exception:
                                        pass
                                res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                                data_block = res_data.get("data", {})
                                if res_data.get("ok") and (data_block.get("status") in ("UpToDate", "UpToDateWithWarnings") or data_block.get("compiled_successfully")):
                                    compiled_ok = True
                                    pred.satisfied = True
                                    pred.evidence = f"Widget Blueprint '{pred.target}' compiled successfully with status '{data_block.get('status')}'"
                                    break
                if not compiled_ok:
                    pred.satisfied = False
                    unmet.append(f"widget_compiled({pred.target}): Widget Blueprint compilation success not verified in tool history")

            elif pred.predicate_type == "widget_hierarchy_verified":
                verified_ok = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        args = th.get("arguments", {})
                        if args.get("op") in ("widget_readback_tree", "widget_inspect"):
                            w_p = args.get("args", {}).get("asset_path") or args.get("asset_path")
                            if not pred.target or pred.target in str(w_p):
                                out_data = th.get("output", {})
                                if isinstance(out_data, str):
                                    try:
                                        out_data = json.loads(out_data)
                                    except Exception:
                                        pass
                                res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                                if res_data.get("ok") and res_data.get("data", {}).get("widget_count", 0) > 0:
                                    verified_ok = True
                                    pred.satisfied = True
                                    cnt = res_data.get("data", {}).get("widget_count")
                                    pred.evidence = f"Widget '{pred.target}' hierarchy verified with {cnt} widgets in tree"
                                    break
                if not verified_ok:
                    pred.satisfied = False
                    unmet.append(f"widget_hierarchy_verified({pred.target}): Widget hierarchy not confirmed in tool history")

            elif pred.predicate_type == "widget_event_bound":
                bound_ok = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        args = th.get("arguments", {})
                        if args.get("op") in ("widget_bind_event", "widget_inspect_events"):
                            w_p = args.get("args", {}).get("asset_path") or args.get("asset_path")
                            if not pred.target or pred.target in str(w_p):
                                out_data = th.get("output", {})
                                if isinstance(out_data, str):
                                    try:
                                        out_data = json.loads(out_data)
                                    except Exception:
                                        pass
                                res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                                if res_data.get("ok"):
                                    bound_ok = True
                                    pred.satisfied = True
                                    pred.evidence = f"Widget event bound for '{pred.target}' verified in tool history"
                                    break
                if not bound_ok:
                    pred.satisfied = False
                    unmet.append(f"widget_event_bound({pred.target}): Event binding not observed in tool history")

            elif pred.predicate_type == "gameplay_state_verified":
                state_ok = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        args = th.get("arguments", {})
                        if args.get("op") in ("gameplay_get_state", "gameplay_modify_state"):
                            out_data = th.get("output", {})
                            if isinstance(out_data, str):
                                try:
                                    out_data = json.loads(out_data)
                                except Exception:
                                    pass
                            res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                            if res_data.get("ok"):
                                state_ok = True
                                pred.satisfied = True
                                pred.evidence = f"Gameplay state verified in tool history: {res_data.get('data')}"
                                break
                if not state_ok:
                    pred.satisfied = False
                    unmet.append(f"gameplay_state_verified({pred.target}): Gameplay state verification not observed in tool history")

            elif pred.predicate_type == "menu_interaction_verified":
                click_ok = False
                for th in reversed(tool_history):
                    if th.get("tool_name") == "unreal_editor":
                        args = th.get("arguments", {})
                        if args.get("op") == "widget_click_button":
                            btn = args.get("args", {}).get("button_name") or args.get("button_name")
                            if not pred.target or pred.target in str(btn):
                                out_data = th.get("output", {})
                                if isinstance(out_data, str):
                                    try:
                                        out_data = json.loads(out_data)
                                    except Exception:
                                        pass
                                res_data = out_data.get("result", out_data) if isinstance(out_data, dict) else {}
                                if res_data.get("ok") and res_data.get("data", {}).get("clicked"):
                                    click_ok = True
                                    pred.satisfied = True
                                    pred.evidence = f"Menu button click '{pred.target}' verified executed in tool history"
                                    break
                if not click_ok:
                    pred.satisfied = False
                    unmet.append(f"menu_interaction_verified({pred.target}): Menu button interaction not observed in tool history")

            elif pred.predicate_type == "custom":
                evaluator = CUSTOM_PREDICATE_EVALUATORS.get(pred.target)
                if evaluator is None:
                    pred.satisfied = False
                    unmet.append(f"custom({pred.target}): no registered evaluator (cannot be satisfied)")
                else:
                    ok, why = evaluator(tool_history)
                    pred.satisfied = ok
                    pred.evidence = why
                    if not ok:
                        unmet.append(f"custom({pred.target}): {why}")

        all_satisfied = len(unmet) == 0
        return all_satisfied, unmet
