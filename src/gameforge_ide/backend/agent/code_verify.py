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


def _extract_symbol(message: str) -> Optional[str]:
    """Extract symbol name from compiler or runtime diagnostic message."""
    if not message:
        return None
    # 1. Quoted C++ or Python symbols: 'UHealthComponent', "MaxAmmo", `GF::FCombatStats`
    quoted = re.search(r"['\"`]([a-zA-Z_][\w:]*)['\"`]", message)
    if quoted:
        return quoted.group(1)
    # 2. Clang/GCC/MSVC unquoted patterns
    patterns = [
        r"\bundeclared identifier\s+([a-zA-Z_][\w:]*)",
        r"\bidentifier\s+([a-zA-Z_][\w:]*)\s+is undefined",
        r"\bno member named\s+([a-zA-Z_][\w:]*)\s+in",
        r"\bundefined reference to\s+([a-zA-Z_][\w:]*)",
        r"\bcannot find symbol\s*:\s*(?:(?:class|variable|method|symbol)\s+)?([a-zA-Z_][\w:]*)",
        r"\bname\s+([a-zA-Z_][\w:]*)\s+is not defined",
    ]
    for pat in patterns:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def parse_diagnostics(raw_diagnostics: Any) -> List[Dict[str, Any]]:
    """Robustly parse compiler outputs, pytest tracebacks, and raw logs into structured diagnostics."""
    if not raw_diagnostics:
        return []

    if isinstance(raw_diagnostics, list):
        parsed = []
        for item in raw_diagnostics:
            if isinstance(item, dict):
                norm = dict(item)
                norm.setdefault("file", item.get("file", ""))
                norm.setdefault("line", int(item.get("line", 0) or 0))
                norm.setdefault("column", int(item.get("column", 0) or 0))
                norm.setdefault("message", item.get("message", ""))
                norm.setdefault("severity", item.get("severity", "error"))
                # Extract symbol if not present
                if not norm.get("symbol") and norm.get("message"):
                    norm["symbol"] = _extract_symbol(norm["message"])
                parsed.append(norm)
            elif isinstance(item, str):
                parsed.extend(parse_diagnostics(item))
        return parsed

    if not isinstance(raw_diagnostics, str):
        return []

    results: List[Dict[str, Any]] = []
    lines = raw_diagnostics.splitlines()

    # Pattern 1: GCC / Clang format: [drive:]path/file.cpp:12:5: error: message
    gcc_clang_pattern = re.compile(
        r"^(?P<file>(?:[a-zA-Z]:[\\/])?[^:\r\n]+\.[a-zA-Z0-9]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?P<severity>error|warning|fatal error|note):\s*(?P<message>.*)$",
        re.IGNORECASE,
    )
    # Pattern 2: MSVC format: [drive:]path\file.cpp(12,5): error C1234: message or (12): error
    msvc_pattern = re.compile(
        r"^(?P<file>(?:[a-zA-Z]:[\\/])?[^\(\r\n]+\.[a-zA-Z0-9]+)\((?P<line>\d+)(?:,\s*(?P<col>\d+))?\)\s*:\s*(?P<severity>error|warning|fatal error|note)\s*(?:[A-Z0-9]+)?\s*:\s*(?P<message>.*)$",
        re.IGNORECASE,
    )
    # Pattern 3: Pytest failure/error format: FAILED/ERROR test_file.py::[Class::]test_func - AssertionError: message
    pytest_fail_pattern = re.compile(
        r"^(?:FAILED|ERROR)\s+(?P<file>(?:[a-zA-Z]:[\\/])?[^:\s\r\n]+\.py)::(?:(?P<cls>\w+)::)?(?P<func>\w+)(?:\s*-\s*(?P<message>.*))?$",
        re.IGNORECASE,
    )
    # Pattern 4: Python traceback line: File "path/file.py", line 12, in func
    py_trace_pattern = re.compile(
        r'^\s*File\s+"(?P<file>[^"]+)",\s*line\s*(?P<line>\d+)(?:,\s*in\s*(?P<func>\w+))?',
        re.IGNORECASE,
    )

    for idx, line in enumerate(lines):
        line_str = line.strip()
        if not line_str:
            continue

        m_gcc = gcc_clang_pattern.match(line_str)
        if m_gcc:
            msg = m_gcc.group("message").strip()
            sym = _extract_symbol(msg)
            results.append({
                "file": m_gcc.group("file").replace("\\", "/"),
                "line": int(m_gcc.group("line")),
                "column": int(m_gcc.group("col") or 0),
                "severity": m_gcc.group("severity").lower(),
                "message": msg,
                "symbol": sym,
            })
            continue

        m_msvc = msvc_pattern.match(line_str)
        if m_msvc:
            msg = m_msvc.group("message").strip()
            sym = _extract_symbol(msg)
            results.append({
                "file": m_msvc.group("file").replace("\\", "/"),
                "line": int(m_msvc.group("line")),
                "column": int(m_msvc.group("col") or 0),
                "severity": m_msvc.group("severity").lower(),
                "message": msg,
                "symbol": sym,
            })
            continue

        m_pytest = pytest_fail_pattern.match(line_str)
        if m_pytest:
            func_name = m_pytest.group("func")
            cls_name = m_pytest.group("cls")
            full_symbol = f"{cls_name}::{func_name}" if cls_name else func_name
            msg = (m_pytest.group("message") or f"Test failure in {full_symbol}").strip()
            results.append({
                "file": m_pytest.group("file").replace("\\", "/"),
                "line": 1,
                "column": 0,
                "severity": "error",
                "message": msg,
                "symbol": func_name,
            })
            continue

        m_pytrace = py_trace_pattern.match(line_str)
        if m_pytrace:
            # Check next line for error message
            next_msg = lines[idx + 1].strip() if idx + 1 < len(lines) else "Exception raised"
            results.append({
                "file": m_pytrace.group("file").replace("\\", "/"),
                "line": int(m_pytrace.group("line")),
                "column": 0,
                "severity": "error",
                "message": next_msg,
                "symbol": m_pytrace.group("func"),
            })
            continue

    if not results and lines:
        # Fallback: treat non-empty error-sounding lines as general diagnostics
        for line in lines:
            line_str = line.strip()
            if any(k in line_str.lower() for k in ("error", "failed", "exception", "assert")):
                results.append({
                    "file": "",
                    "line": 0,
                    "column": 0,
                    "severity": "error",
                    "message": line_str,
                    "symbol": _extract_symbol(line_str),
                })
                if len(results) >= 10:
                    break

    return results


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
    diagnostics: Any,
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

    # Extract parsed diagnostics
    all_diags = parse_diagnostics(diagnostics)
    if not all_diags and build_errors:
        all_diags = parse_diagnostics(build_errors)

    top_diags = all_diags[:10]

    if not top_diags:
        return {
            "status": "NO_DIAGNOSTICS",
            "attempt": attempt,
            "error": "No diagnostics available to propose a fix.",
        }

    first_diag = top_diags[0]
    file_rel = first_diag.get("file", "")
    line_no = int(first_diag.get("line", 0) or 0)

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

    # Context query via ProjectIndex and symbol extraction
    sym_context = []
    searched_symbols: Set[str] = set()
    for diag in top_diags:
        msg = diag.get("message", "")
        sym = diag.get("symbol")
        candidates = [sym] if sym else []
        candidates.extend(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", msg))
        for cand in candidates:
            if cand and cand not in searched_symbols and cand.isidentifier():
                searched_symbols.add(cand)
                if len(searched_symbols) >= 5:
                    break

    try:
        from ...index.indexer import ProjectIndex
        index = ProjectIndex(project_dir)
        for s in searched_symbols:
            s_res = index.search_symbols(s, limit=3)
            sym_context.extend(s_res.get("results", []))
    except Exception:
        pass

    # Fallback search in project_dir if index returned no symbol matches
    if not sym_context and searched_symbols and project_dir.is_dir():
        for s in list(searched_symbols)[:3]:
            for p in list(project_dir.glob(f"**/*{s}*"))[:2]:
                if p.is_file() and p.suffix in (".h", ".hpp", ".cpp", ".py", ".cs"):
                    try:
                        rel = str(p.relative_to(project_dir)).replace("\\", "/")
                        sym_context.append({"symbol": s, "file": rel, "type": "file_match"})
                    except Exception:
                        pass

    # Model call or heuristic fix
    if model_caller is not None and target_path and target_path.is_file():
        repetition_warning = ""
        if previous_diffs:
            repetition_warning = (
                f"\nAvoid repeating previous failed attempts ({len(previous_diffs)} prior diffs recorded). "
                "Provide an alternative resolution.\n"
            )
        engine_hints = []
        diag_text = json.dumps(top_diags)
        if any(k in diag_text for k in ("C2450", "C2046", "C4060")) or "switch" in diag_text.lower():
            engine_hints.append("- In Unreal C++, FKey is a struct (not an integer/enum). Never use switch (Key); replace with if (Key == EKeys::X) ... else if (Key == EKeys::Y)...")
        if "ToFloat" in diag_text or "C2039" in diag_text:
            engine_hints.append("- FVector has no .ToFloat() member. To rotate towards a direction, use Direction.Rotation() or Direction.Rotation().Quaternion(). For length, use .Size().")
        if "C2065" in diag_text:
            engine_hints.append("- Undeclared identifier: ensure all member variables and helpers are declared in the class definition in the header file.")
        hints_block = ("\n\nEngine Invariants & Fix Hints:\n" + "\n".join(engine_hints)) if engine_hints else ""

        prompt = (
            f"You are GameForge's C++ codegen repair agent.\n"
            f"Build diagnostics:\n{json.dumps(top_diags, indent=2)}\n\n"
            f"Relevant file: {file_rel} around line {line_no}:\n{file_excerpt}\n\n"
            f"Related symbols in index:\n{json.dumps(sym_context, indent=2)}\n{repetition_warning}{hints_block}\n"
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
                "symbols_queried": list(searched_symbols),
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
        "symbols_queried": list(searched_symbols),
        "explanation": f"Automated fix proposal for diagnostic: {first_diag.get('message', '')}",
    }


def _normalize_diff_for_cycle_check(diff: str) -> str:
    """Normalize diff lines, ignoring blank lines, line endings, and whitespace variations."""
    lines = []
    for line in (diff or "").splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if line_clean.startswith(("--- ", "+++ ")) and "\t" in line_clean:
            line_clean = line_clean.split("\t")[0].strip()
        lines.append(line_clean)
    return "\n".join(lines)


def run_code_repair_loop(
    project_dir: Path,
    diagnostics_fn: Callable[[], Any],
    apply_fix_fn: Callable[[Dict[str, Any]], bool],
    build_verify_fn: Callable[[], bool],
    model_caller: Optional[Callable[[str, str], str]] = None,
    max_attempts: int = 5,
    rollback_fn: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Autonomous bounded code repair loop with cycle detection and retry limits.

    Guarantees:
    - Bounded retries: capped at max_attempts (clamped between 1 and 5).
    - Prevents infinite loops: tracks proposed diffs and halts on cycle detection.
    - Early exit on success.
    - Optional rollback on failure.
    - Detailed audit history of all attempts.
    """
    hard_cap = min(max(1, int(max_attempts)), 5)
    seen_diffs: Set[str] = set()
    history: List[Dict[str, Any]] = []
    prev_diag_count: Optional[int] = None
    no_progress_count: int = 0

    def _execute_rollback() -> bool:
        if rollback_fn is not None:
            try:
                res = rollback_fn()
                return True if res is None or res else False
            except Exception:
                return False
        return False

    for attempt in range(1, hard_cap + 1):
        raw_diags = diagnostics_fn()
        diags = parse_diagnostics(raw_diags)
        if not diags:
            return {
                "status": "SUCCESS",
                "attempt": attempt - 1 if attempt > 1 else 1,
                "history": history,
                "rolled_back": False,
                "message": "No diagnostics reported; code is clean.",
            }

        curr_diag_count = len(diags)
        if prev_diag_count is not None and curr_diag_count >= prev_diag_count:
            no_progress_count += 1
        else:
            no_progress_count = 0
        prev_diag_count = curr_diag_count

        if no_progress_count >= 2:
            did_rollback = _execute_rollback()
            return {
                "status": "BLOCKED",
                "attempt": attempt,
                "error": "Repair halted: 2 consecutive attempts without measurable progress.",
                "history": history,
                "rolled_back": did_rollback,
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
            "diagnostics_addressed": fix.get("diagnostics_addressed", len(diags)),
        })

        if fix.get("status") != "PROPOSED":
            did_rollback = _execute_rollback()
            return {
                "status": fix.get("status", "FAILED"),
                "attempt": attempt,
                "error": fix.get("error", "Fix proposal failed."),
                "history": history,
                "rolled_back": did_rollback,
            }

        diff = fix.get("diff", "")
        norm_diff = _normalize_diff_for_cycle_check(diff)
        if norm_diff in seen_diffs or diff in seen_diffs:
            did_rollback = _execute_rollback()
            return {
                "status": "BLOCKED",
                "attempt": attempt,
                "error": "Cyclic repair detected: model proposed an identical diff already attempted.",
                "history": history,
                "rolled_back": did_rollback,
            }
        seen_diffs.add(diff)
        if norm_diff:
            seen_diffs.add(norm_diff)

        applied = apply_fix_fn(fix)
        if not applied:
            did_rollback = _execute_rollback()
            return {
                "status": "FAILED",
                "attempt": attempt,
                "error": f"Failed to apply proposed fix on attempt {attempt}.",
                "history": history,
                "rolled_back": did_rollback,
            }

        if build_verify_fn():
            return {
                "status": "SUCCESS",
                "attempt": attempt,
                "history": history,
                "rolled_back": False,
                "message": f"Code repair succeeded on attempt {attempt}.",
            }

    did_rollback = _execute_rollback()
    return {
        "status": "EXHAUSTED",
        "attempt": hard_cap,
        "max_attempts": hard_cap,
        "error": f"Maximum fix attempts ({hard_cap}) reached without resolving build issues.",
        "history": history,
        "rolled_back": did_rollback,
    }
