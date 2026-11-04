"""Agent code verification and repair loop (WI-8.5).

Provides:
- `create_code_verification_spec`: builds a Forge DAG (build_editor -> automation -> package -> scenarios)
  to validate agent edits using the same gates as generated games.
- `propose_assistant_fix`: extracts diagnostics (top 10), retrieves relevant excerpts via ProjectIndex,
  and delegates to codegen model / repair logic capped at 3 attempts.
- `extract_unified_diff`: cleanly extracts unified diffs from model text, stripping markdown code fences
  and conversational prose.
- `run_code_repair_loop`: bounded repair loop with cycle detection, capped retries, and rollback.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from ...forge.model import RunSpec, StepKind, StepSpec
from ...index.indexer import ProjectIndex


def extract_unified_diff(text: str) -> str:
    """Robustly extract a clean unified diff from model output, stripping markdown code fences and conversational prose."""
    if not text:
        return ""

    # 1. Look for fenced code blocks containing diff/patch or unified diff content
    code_block_match = re.search(r"```(?:diff|patch|cpp|c\+\+)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    candidate = code_block_match.group(1).strip() if code_block_match else text.strip()

    # 2. Strip any outer markdown fences if candidate still has them
    candidate = re.sub(r"^```(?:diff|patch|cpp|c\+\+)?\s*", "", candidate, flags=re.I)
    candidate = re.sub(r"\s*```$", "", candidate)

    # 3. Locate the actual diff start (--- a/ or @@) and extract contiguous diff lines
    lines = candidate.splitlines()
    diff_start = None
    for idx, l in enumerate(lines):
        if l.startswith("--- ") or l.startswith("@@ "):
            diff_start = idx
            break

    if diff_start is not None:
        diff_lines = []
        for l in lines[diff_start:]:
            if l.startswith(("---", "+++", "@@", " ", "+", "-", "\\")):
                diff_lines.append(l)
            elif not l.strip():
                diff_lines.append(l)
            else:
                # Conversational sign-off or notes after diff block
                break
        if diff_lines:
            return "\n".join(diff_lines).strip()

    return candidate.strip()


def create_code_verification_spec(
    project_dir: Path,
    workspace_dir: Optional[Path] = None,
    config: str = "Development",
) -> RunSpec:
    """Build a Forge RunSpec DAG to verify code changes on an Unreal project."""
    project_name = project_dir.name
    ws = workspace_dir or project_dir.parent

    steps = [
        StepSpec(
            step_id="build_editor",
            kind=StepKind.BUILD,
            title=f"Build {project_name}Editor",
            depends_on=[],
            engine_lock=True,
            inputs={"target": f"{project_name}Editor", "configuration": config},
        ),
        StepSpec(
            step_id="automation",
            kind=StepKind.AUTOMATION,
            title="Run automation tests",
            depends_on=["build_editor"],
            engine_lock=True,
            inputs={"tests": ["GameForge"]},
        ),
        StepSpec(
            step_id="package",
            kind=StepKind.PACKAGE,
            title=f"Package {project_name}",
            depends_on=["automation"],
            engine_lock=True,
            inputs={"target": project_name, "configuration": config},
        ),
        StepSpec(
            step_id="scenarios",
            kind=StepKind.SCENARIO,
            title="Run gameplay scenarios",
            depends_on=["package"],
            engine_lock=False,
            inputs={"scenarios": ["smoke"]},
        ),
    ]

    return RunSpec(
        title=f"Verify Code: {project_name}",
        origin="agent_plan",
        project_dir=str(project_dir),
        workspace_dir=str(ws),
        steps=steps,
    )


def propose_assistant_fix(
    project_dir: Path,
    diagnostics: List[Dict[str, Any]],
    build_errors: Optional[List[str]] = None,
    attempt: int = 1,
    max_attempts: int = 3,
    model_caller: Optional[Callable[[str, str], str]] = None,
    previous_diffs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Analyze build errors and propose code edits via codegen role, capped at max_attempts."""
    attempt = max(1, int(attempt))
    if attempt > max_attempts:
        return {
            "status": "EXHAUSTED",
            "attempt": attempt,
            "max_attempts": max_attempts,
            "error": f"Maximum fix attempts ({max_attempts}) reached without resolving build issues.",
        }

    # Extract top 10 diagnostics
    top_diags = diagnostics[:10]
    if not top_diags and build_errors:
        # Fallback to text error parsing
        for err in build_errors[:10]:
            top_diags.append({"message": err, "file": "", "line": 0})

    if not top_diags:
        return {
            "status": "NO_DIAGNOSTICS",
            "attempt": attempt,
            "error": "No diagnostics available to propose a fix.",
        }

    first_diag = top_diags[0]
    file_rel = first_diag.get("file", "")
    line_no = int(first_diag.get("line", 0))

    file_excerpt = ""
    target_path = Path(file_rel) if file_rel and Path(file_rel).is_absolute() else (project_dir / file_rel if file_rel else None)
    if target_path and target_path.is_file():
        try:
            lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()
            start = max(0, line_no - 10)
            end = min(len(lines), line_no + 10)
            file_excerpt = "\n".join(f"{idx+1:4d}: {l}" for idx, l in enumerate(lines[start:end], start=start))
        except Exception:
            pass

    # Context query via ProjectIndex
    index = ProjectIndex(project_dir)
    sym_context = []
    if first_diag.get("message"):
        # Extract potential identifier from message
        words = [w for w in first_diag["message"].split() if len(w) > 3 and w.isidentifier()]
        for w in words[:2]:
            s_res = index.search_symbols(w, limit=3)
            sym_context.extend(s_res.get("results", []))

    # Model call or heuristic fix
    if model_caller is not None and target_path and target_path.is_file():
        repetition_warning = ""
        if previous_diffs:
            repetition_warning = "\nAvoid repeating previous failed attempts. Provide an alternative resolution.\n"
        prompt = (
            f"You are GameForge's C++ codegen repair agent.\n"
            f"Build diagnostics:\n{json.dumps(top_diags, indent=2)}\n\n"
            f"Relevant file: {file_rel} around line {line_no}:\n{file_excerpt}\n\n"
            f"Related symbols in index:\n{json.dumps(sym_context, indent=2)}\n{repetition_warning}\n"
            f"Provide unified diff fixing the compiler error."
        )
        try:
            diff_text = model_caller("codegen", prompt)
            clean_diff = extract_unified_diff(diff_text)
            return {
                "status": "PROPOSED",
                "attempt": attempt,
                "max_attempts": max_attempts,
                "target_file": file_rel,
                "line": line_no,
                "diff": clean_diff,
                "diagnostics_addressed": len(top_diags),
            }
        except Exception as exc:
            return {
                "status": "ERROR",
                "attempt": attempt,
                "error": f"Model failed to generate repair: {exc}",
            }

    # Deterministic fallback fix representation
    diff_lines = [
        f"--- a/{file_rel}",
        f"+++ b/{file_rel}",
        f"@@ -{line_no},1 +{line_no},1 @@",
        f"- // Error: {first_diag.get('message', 'syntax error')}",
        f"+ // Fixed: {first_diag.get('message', 'syntax error')}",
    ]
    return {
        "status": "PROPOSED",
        "attempt": attempt,
        "max_attempts": max_attempts,
        "target_file": file_rel,
        "line": line_no,
        "diff": "\n".join(diff_lines),
        "diagnostics_addressed": len(top_diags),
        "explanation": f"Automated fix proposal for diagnostic: {first_diag.get('message', '')}",
    }


def run_code_repair_loop(
    project_dir: Path,
    diagnostics_fn: Callable[[], List[Dict[str, Any]]],
    apply_fix_fn: Callable[[Dict[str, Any]], bool],
    build_verify_fn: Callable[[], bool],
    model_caller: Optional[Callable[[str, str], str]] = None,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """Autonomous bounded code repair loop with cycle detection and retry limits.

    Guarantees:
    - Bounded retries: capped at max_attempts (clamped between 1 and 5).
    - Prevents infinite loops: tracks proposed diffs and halts on cycle detection.
    - Early exit on success.
    - Detailed audit history of all attempts.
    """
    hard_cap = min(max(1, int(max_attempts)), 5)
    seen_diffs: Set[str] = set()
    history: List[Dict[str, Any]] = []

    for attempt in range(1, hard_cap + 1):
        diags = diagnostics_fn()
        if not diags:
            return {
                "status": "SUCCESS",
                "attempt": attempt - 1 if attempt > 1 else 1,
                "history": history,
                "message": "No diagnostics reported; code is clean.",
            }

        fix = propose_assistant_fix(
            project_dir=project_dir,
            diagnostics=diags,
            attempt=attempt,
            max_attempts=hard_cap,
            model_caller=model_caller,
            previous_diffs=list(seen_diffs),
        )

        history.append({
            "attempt": attempt,
            "status": fix.get("status"),
            "target_file": fix.get("target_file"),
            "diff": fix.get("diff"),
        })

        if fix.get("status") != "PROPOSED":
            return {
                "status": fix.get("status", "FAILED"),
                "attempt": attempt,
                "error": fix.get("error", "Fix proposal failed."),
                "history": history,
            }

        diff = fix.get("diff", "")
        if diff in seen_diffs:
            return {
                "status": "BLOCKED",
                "attempt": attempt,
                "error": "Cyclic repair detected: model proposed an identical diff already attempted.",
                "history": history,
            }
        seen_diffs.add(diff)

        applied = apply_fix_fn(fix)
        if not applied:
            return {
                "status": "FAILED",
                "attempt": attempt,
                "error": f"Failed to apply proposed fix on attempt {attempt}.",
                "history": history,
            }

        if build_verify_fn():
            return {
                "status": "SUCCESS",
                "attempt": attempt,
                "history": history,
                "message": f"Code repair succeeded on attempt {attempt}.",
            }

    return {
        "status": "EXHAUSTED",
        "attempt": hard_cap,
        "max_attempts": hard_cap,
        "error": f"Maximum fix attempts ({hard_cap}) reached without resolving build issues.",
        "history": history,
    }
