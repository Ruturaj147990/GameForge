"""Model Evaluation Adapter and Candidate Invocation Pipeline for GameForge.

Implements R-13 through R-21, R-33, R-35, R-39, and AC-5 through AC-8.
Provides typed interfaces for candidate invocation, controlled task attempts,
grading integration, raw output/evidence preservation, and layered scorecards.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .grading import RunStatus
from .runner import BenchmarkRunner
from .task_loader import TaskSpec, load_task


@dataclass
class ModelRequest:
    """Prompt and execution boundaries supplied to candidate."""
    task_id: str
    prompt: str
    system_prompt: Optional[str] = None
    context_files: Dict[str, str] = field(default_factory=dict)
    permitted_tools: List[str] = field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout_seconds: int = 120
    run_id: str = field(default_factory=lambda: f"req_{int(time.time())}")


@dataclass
class ModelResponse:
    """Standardized candidate output and invocation telemetry."""
    candidate_id: str
    raw_output: str
    code_patches: Dict[str, str] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_duration_seconds: float = 0.0
    cost_usd: float = 0.0
    error: Optional[str] = None
    success: bool = True
    raw_telemetry: Dict[str, Any] = field(default_factory=dict)


def apply_unified_diff(original_text: str, diff_text: str) -> Tuple[bool, str, Optional[str]]:
    """Applies a unified diff to original text cleanly.
    
    Returns (success, result_text, error_message).
    """
    orig_lines = original_text.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)
    
    hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    
    out_lines: List[str] = []
    orig_idx = 0
    i = 0
    n = len(diff_lines)
    
    # Skip diff file headers (--- / +++)
    while i < n and (diff_lines[i].startswith("---") or diff_lines[i].startswith("+++")):
        i += 1
        
    while i < n:
        line = diff_lines[i]
        match = hunk_header_re.match(line)
        if not match:
            # If not a hunk header, skip comments or unexpected lines
            i += 1
            continue
            
        orig_start = int(match.group(1)) - 1  # 1-indexed to 0-indexed
        orig_count = int(match.group(2)) if match.group(2) is not None else 1
        i += 1
        
        # Advance original lines up to hunk start
        while orig_idx < orig_start and orig_idx < len(orig_lines):
            out_lines.append(orig_lines[orig_idx])
            orig_idx += 1
            
        while i < n and not diff_lines[i].startswith("@@"):
            hline = diff_lines[i]
            prefix = hline[0] if len(hline) > 0 else ""
            content = hline[1:] if len(hline) > 0 else ""
            
            if prefix == " ":
                # Context line: must match original
                if orig_idx < len(orig_lines):
                    if orig_lines[orig_idx].rstrip("\r\n") != content.rstrip("\r\n"):
                        return False, original_text, f"Diff context mismatch: expected {content.strip()!r}, got {orig_lines[orig_idx].strip()!r}"
                    out_lines.append(orig_lines[orig_idx])
                    orig_idx += 1
                else:
                    return False, original_text, "Diff context line exceeds original file length"
            elif prefix == "-":
                # Deletion line: advance original index
                if orig_idx < len(orig_lines):
                    if orig_lines[orig_idx].rstrip("\r\n") != content.rstrip("\r\n"):
                        return False, original_text, f"Diff deletion mismatch: expected {content.strip()!r}, got {orig_lines[orig_idx].strip()!r}"
                    orig_idx += 1
                else:
                    return False, original_text, "Diff deletion line exceeds original file length"
            elif prefix == "+":
                # Addition line: append to output
                out_lines.append(content)
            elif prefix == "\\":
                # '\ No newline at end of file'
                pass
            i += 1
            
    # Append any remaining original lines
    while orig_idx < len(orig_lines):
        out_lines.append(orig_lines[orig_idx])
        orig_idx += 1
        
    return True, "".join(out_lines), None


def extract_code_blocks(text: str, allowed_paths: Optional[List[str]] = None) -> Dict[str, str]:
    """Extracts code blocks and unified diffs from model response mapped to target file paths."""
    patches: Dict[str, str] = {}
    
    # Pattern 1: Explicit file path annotation
    # Matches:
    # "### File: Source/GameForgePilot/..."
    # "**File:** `path`"
    # "// File: path"
    # "### `path`"
    # "File: `path`"
    file_header_pattern = re.compile(
        r"(?:###|//|#|\*)+\s*(?:File|Path|Target)?[:\*]*\s*`?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)`?[:\*]*"
        r"(?:[^\n`]*\n){1,4}\s*```(?:[a-zA-Z0-9_+\-]+)?\r?\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    for match in file_header_pattern.finditer(text):
        path_str = match.group(1).strip().replace("\\", "/").lstrip("/")
        content = match.group(2)
        patches[path_str] = content

    # Pattern 1b: Header immediately adjacent: "### File: path\n```cpp\n..."
    if not patches:
        tight_pattern = re.compile(
            r"(?:###|//|#|\*)+\s*(?:File|Path|Target)?[:\*]*\s*`?([a-zA-Z0-9_\-\./\\]+)`?[:\*]*\s*\r?\n```(?:[a-zA-Z0-9_+\-]+)?\r?\n(.*?)```",
            re.DOTALL | re.IGNORECASE,
        )
        for match in tight_pattern.finditer(text):
            path_str = match.group(1).strip().replace("\\", "/").lstrip("/")
            content = match.group(2)
            patches[path_str] = content

    # Pattern 1c: Diff block with diff headers "--- a/path\n+++ b/path"
    if not patches:
        diff_pattern = re.compile(
            r"```(?:diff|patch)?\r?\n---\s+[ab]?/?([^\n\r]+)\r?\n\+\+\+\s+[ab]?/?([^\n\r]+)\r?\n(.*?)```",
            re.DOTALL | re.IGNORECASE,
        )
        for match in diff_pattern.finditer(text):
            path_str = match.group(2).strip().replace("\\", "/").lstrip("/")
            content = match.group(0)[len("```diff\n"):-len("```")] if match.group(0).startswith("```") else match.group(3)
            patches[path_str] = content

    # Pattern 2: Generic code blocks if no explicit file annotations matched
    if not patches:
        generic_pattern = re.compile(r"```(?:cpp|c\+\+|csharp|cs|yaml|json)?\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
        matches = generic_pattern.findall(text)
        if matches and allowed_paths:
            # Map primary code block to first allowed edit path that has a file extension
            for ap in allowed_paths:
                clean_ap = ap.strip().replace("\\", "/").lstrip("/")
                if clean_ap.endswith((".cpp", ".h", ".cs", ".yaml", ".json")):
                    patches[clean_ap] = matches[0]
                    break

    return patches


def validate_patch_target(
    rel_path: str,
    allowed_paths: List[str],
    forbidden_edits: List[str],
    base_dir: Path,
) -> Tuple[bool, Optional[str], Optional[Path]]:
    """Validates that candidate patch target conforms strictly to path allowlists and security policies."""
    norm_rel = rel_path.replace("\\", "/").strip().lstrip("/")
    
    # 1. Path traversal security check
    if ".." in Path(norm_rel).parts or norm_rel.startswith("../"):
        return False, f"SECURITY REJECTION: Path traversal attempt detected ({rel_path})", None

    # 2. Protected test / benchmark oracle check
    lower_norm = norm_rel.lower()
    protected_fragments = [
        "graders/protected", "graders/reference_solutions", "acceptance_criteria",
        "hidden_tests", ".git", "eval_manifest.json", "model_register.json",
        "benchmark_tasks", "probes/protectedgrader"
    ]
    if any(p in lower_norm for p in protected_fragments):
        return False, f"SECURITY REJECTION: Modification of protected benchmark file forbidden ({rel_path})", None

    # 3. Explicit task forbidden edits check
    for fb in forbidden_edits:
        fb_clean = fb.lower().strip()
        if fb_clean and (fb_clean in lower_norm or any(part == fb_clean for part in lower_norm.split("/"))):
            return False, f"POLICY REJECTION: Path violates forbidden edits ({fb}): {rel_path}", None

    # 4. Resolve path against base directory
    direct_target = (base_dir / norm_rel).resolve()
    try:
        direct_target.relative_to(base_dir.resolve())
    except ValueError:
        return False, f"SECURITY REJECTION: Resolved path escapes workspace ({direct_target})", None

    # If direct file does not exist, search for existing project file with matching basename
    resolved_target = direct_target
    if not direct_target.is_file():
        filename = Path(norm_rel).name
        candidates = list(base_dir.glob(f"**/{filename}"))
        # Prefer Source/ or Content/ subtrees
        src_cands = [c for c in candidates if "source" in str(c).lower() and not any(p in c.parts for p in ["Binaries", "Intermediate", "Saved", ".vs"])]
        if src_cands:
            resolved_target = src_cands[0]
        elif candidates:
            valid_cands = [c for c in candidates if not any(p in c.parts for p in ["Binaries", "Intermediate", "Saved", ".vs"])]
            if valid_cands:
                resolved_target = valid_cands[0]

    # 5. Check task allowed_edit_paths
    rel_to_base = resolved_target.relative_to(base_dir).as_posix()
    is_allowed = False
    for ap in allowed_paths:
        norm_ap = ap.replace("\\", "/").rstrip("/")
        if norm_rel.startswith(norm_ap) or rel_to_base.startswith(norm_ap) or norm_rel.endswith(norm_ap) or rel_to_base.endswith(norm_ap):
            is_allowed = True
            break
        # Semantic keyword allowlists (only if norm_ap is a general category, not a specific source file)
        is_concrete_file = any(norm_ap.endswith(ext) for ext in [".cpp", ".h", ".cs", ".uasset", ".json", ".yaml"])
        if not is_concrete_file:
            if "source" in norm_ap.lower() and ("source/" in rel_to_base.lower() or rel_to_base.lower().endswith((".cpp", ".h", ".cs"))):
                is_allowed = True
                break
            if "content" in norm_ap.lower() and ("content/" in rel_to_base.lower() or rel_to_base.lower().endswith((".uasset", ".json"))):
                is_allowed = True
                break

    if not is_allowed:
        return False, f"POLICY REJECTION: Target path not within task allowed edit paths: {rel_path}", None

    return True, None, resolved_target


def invoke_candidate(
    candidate_config: Dict[str, Any],
    request: ModelRequest,
) -> ModelResponse:
    """Invokes one authorized candidate via the declared runtime interface."""
    cand_id = candidate_config.get("candidate_id", "unknown_candidate")
    runtime_type = candidate_config.get("runtime_type", "local_inference")
    provider = candidate_config.get("provider", "ollama")
    model_name = candidate_config.get("model_name", "llama3.1:8b")
    
    start_time = time.time()

    if runtime_type == "test_double":
        # Deterministic test double strictly for unit testing runner/adapter logic
        return ModelResponse(
            candidate_id=cand_id,
            raw_output="/* TEST DOUBLE RESPONSE */",
            code_patches={},
            prompt_tokens=50,
            completion_tokens=10,
            total_duration_seconds=0.01,
            success=True,
        )

    if provider == "ollama":
        host = candidate_config.get("deployment", {}).get("host", "127.0.0.1:11434")
        url = f"http://{host}/api/generate"

        effective_ctx = getattr(request, "max_context", None) or 4096
        payload = {
            "model": model_name,
            "prompt": request.prompt,
            "system": request.system_prompt or "",
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "num_ctx": effective_ctx,
            },
            "think": False,
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=request.timeout_seconds) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
            
            raw_output = resp_data.get("response", "")
            prompt_tokens = resp_data.get("prompt_eval_count", 0)
            completion_tokens = resp_data.get("eval_count", 0)
            duration_ns = resp_data.get("total_duration", 0)
            duration_s = duration_ns / 1e9 if duration_ns else (time.time() - start_time)

            patches = extract_code_blocks(raw_output)

            return ModelResponse(
                candidate_id=cand_id,
                raw_output=raw_output,
                code_patches=patches,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_duration_seconds=duration_s,
                cost_usd=0.0,
                success=True,
                raw_telemetry={
                    "load_duration_ns": resp_data.get("load_duration", 0),
                    "prompt_eval_duration_ns": resp_data.get("prompt_eval_duration", 0),
                    "eval_duration_ns": resp_data.get("eval_duration", 0),
                    "done_reason": resp_data.get("done_reason", "stop"),
                },
            )
        except urllib.error.URLError as e:
            return ModelResponse(
                candidate_id=cand_id,
                raw_output="",
                total_duration_seconds=time.time() - start_time,
                error=f"Ollama connection failure: {str(e)}",
                success=False,
            )
        except Exception as e:
            return ModelResponse(
                candidate_id=cand_id,
                raw_output="",
                total_duration_seconds=time.time() - start_time,
                error=f"Invocation exception: {str(e)}",
                success=False,
            )

    return ModelResponse(
        candidate_id=cand_id,
        raw_output="",
        total_duration_seconds=time.time() - start_time,
        error=f"Unsupported candidate provider or runtime: {provider} / {runtime_type}",
        success=False,
    )


def run_attempt(
    manifest: Dict[str, Any],
    candidate_config: Dict[str, Any],
    task_spec: TaskSpec,
    workspace_root: Path,
    runner: Optional[BenchmarkRunner] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Executes a single controlled evaluation attempt on a clean fixture snapshot."""
    start_time = time.time()
    attempt_id = f"attempt_{task_spec.id}_{candidate_config.get('candidate_id', 'cand')}_{int(start_time)}_{uuid.uuid4().hex[:6]}"
    
    runner = runner or BenchmarkRunner(workspace_root=workspace_root)
    output_dir = output_dir or (workspace_root / "reports" / "attempts" / attempt_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build Candidate-Visible Context (STRICT: no hidden tests or private graders)
    visible_prompt = (
        f"You are evaluated on the following GameForge benchmark task.\n\n"
        f"TASK ID: {task_spec.id}\n"
        f"TITLE: {task_spec.title}\n"
        f"TIER: {task_spec.tier}\n"
        f"CATEGORY: {task_spec.category}\n\n"
        f"OBJECTIVE AND REQUIREMENTS:\n"
        f"{task_spec.prompt}\n\n"
        f"ALLOWED EDIT PATHS:\n" + "\n".join(f"- {p}" for p in task_spec.allowed_edit_paths) + "\n\n"
        f"FORBIDDEN EDITS (Do not modify):\n" + "\n".join(f"- {p}" for p in task_spec.forbidden_edits) + "\n\n"
        f"Please provide your complete, syntactically correct native implementation within the allowed paths.\n"
        f"Format your code using Markdown blocks with explicit file headers, e.g.:\n"
        f"### File: <RelativePath>\n```cpp\n...code...\n```\n"
    )

    system_prompt = (
        "You are an expert game-engine C++ and systems software engineer. "
        "Adhere strictly to engine invariants, life cycles, idempotent delegates, "
        "safe math clamping, and public component interfaces."
    )

    request = ModelRequest(
        task_id=task_spec.id,
        prompt=visible_prompt,
        system_prompt=system_prompt,
        max_tokens=manifest.get("candidate_protocol", {}).get("budgets", {}).get("max_tokens_per_request", 4096),
        timeout_seconds=manifest.get("candidate_protocol", {}).get("budgets", {}).get("timeout_seconds", 180),
        run_id=attempt_id,
    )

    # 2. Invoke Candidate
    model_response = invoke_candidate(candidate_config, request)

    # Save raw model output immediately
    raw_output_path = output_dir / "candidate_raw_output.txt"
    raw_output_path.write_text(model_response.raw_output, encoding="utf-8")

    diffs: Dict[str, str] = {}
    patch_success = False
    
    # 3. Create clean workspace for attempt
    attempt_candidate_dir = output_dir / "candidate_files"
    attempt_candidate_dir.mkdir(parents=True, exist_ok=True)

    # Find base fixture to copy baseline files
    fixture_dir = workspace_root / "fixtures" / "unreal" / task_spec.id.replace("-", "_")
    if not fixture_dir.is_dir():
        parts = task_spec.id.split("-")
        if len(parts) >= 3:
            alt_f = workspace_root / "fixtures" / "unreal" / f"{parts[0]}_{parts[1]}_{parts[2]}"
            if alt_f.is_dir():
                fixture_dir = alt_f
            else:
                # Try finding any fixture directory starting with parts[0]_parts[1]
                matches = list((workspace_root / "fixtures" / "unreal").glob(f"{parts[0]}_{parts[1]}*"))
                if matches and matches[0].is_dir():
                    fixture_dir = matches[0]

    if fixture_dir.is_dir():
        for item in fixture_dir.glob("**/*"):
            if item.is_file() and not any(p in item.parts for p in ["Binaries", "Intermediate", "Saved", ".vs"]):
                rel = item.relative_to(fixture_dir)
                dest = attempt_candidate_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

    # 4. Apply extracted candidate patches
    patches_to_apply = dict(model_response.code_patches)
    if not patches_to_apply and model_response.raw_output:
        patches_to_apply = extract_code_blocks(model_response.raw_output, task_spec.allowed_edit_paths)

    rejection_reasons: Dict[str, str] = {}
    patch_application_errors: Dict[str, str] = {}
    effective_files_modified = 0

    if model_response.success and patches_to_apply:
        for rel_path, patch_content in patches_to_apply.items():
            is_valid, err_msg, resolved_target = validate_patch_target(
                rel_path=rel_path,
                allowed_paths=task_spec.allowed_edit_paths,
                forbidden_edits=task_spec.forbidden_edits,
                base_dir=attempt_candidate_dir,
            )
            if not is_valid or resolved_target is None:
                rejection_reasons[rel_path] = err_msg or "Path validation failed"
                continue

            old_content = ""
            if resolved_target.is_file():
                old_content = resolved_target.read_text(encoding="utf-8", errors="replace")

            # Check if patch is unified diff
            new_content = patch_content
            if patch_content.startswith("---") or "\n@@ -" in patch_content or patch_content.startswith("@@ -"):
                diff_ok, applied_text, diff_err = apply_unified_diff(old_content, patch_content)
                if not diff_ok:
                    patch_application_errors[rel_path] = diff_err or "Unified diff hunk application failed"
                    continue
                new_content = applied_text

            # Compute unified diff against baseline
            diff_lines = list(difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            ))
            diff_text = "".join(diff_lines)

            # Check if change is genuinely different
            if old_content != new_content and diff_text.strip():
                resolved_target.parent.mkdir(parents=True, exist_ok=True)
                resolved_target.write_text(new_content, encoding="utf-8")
                diffs[rel_path] = diff_text
                effective_files_modified += 1
            else:
                # Candidate output was identical to baseline file
                rejection_reasons[rel_path] = "Candidate content was bitwise identical to starter fixture (no effective change)"

    # Save diffs
    diff_file = output_dir / "candidate_diffs.patch"
    diff_file.write_text("\n\n".join(f"# {p}\n{d}" for p, d in diffs.items()), encoding="utf-8")

    # Save patch application audit log
    patch_audit = {
        "patches_extracted_count": len(patches_to_apply),
        "patches_applied_count": len(diffs),
        "effective_files_modified": effective_files_modified,
        "is_genuinely_different": (effective_files_modified > 0),
        "rejection_reasons": rejection_reasons,
        "patch_application_errors": patch_application_errors,
    }
    (output_dir / "patch_application_audit.json").write_text(json.dumps(patch_audit, indent=2), encoding="utf-8")

    # 5. Run grading pipeline on the candidate workspace
    run_result = runner.run_task(
        task_id=task_spec.id,
        engine_name="unreal" if "engine_neutral" not in task_spec.category else "auto",
        candidate_dir=attempt_candidate_dir,
        candidate_id=candidate_config.get("candidate_id", "cand"),
        candidate_type="model_candidate",
    )

    # STRICT GROUNDING ENFORCEMENT:
    # If this is a native code task (T2/T3) requiring implementation:
    # A task with zero applied patches or zero effective changes must NEVER be awarded a passing score!
    raw_grading_status = run_result.get("status", "UNVERIFIED")
    final_status = raw_grading_status
    failure_cause = None

    if getattr(task_spec, "native_execution_required", True) and "engine_neutral" not in task_spec.category:
        if len(diffs) == 0:
            final_status = "FAIL_NO_PATCHES_APPLIED"
            failure_cause = "Zero candidate patches were applied to project workspace"
        elif effective_files_modified == 0:
            final_status = "FAIL_NO_GENUINE_CHANGES"
            failure_cause = "Candidate changes were identical to starter fixture (zero delta)"
        elif patch_application_errors:
            if final_status == "PASS":
                final_status = "PARTIAL_PATCH_APPLICATION_FAILURE"
                failure_cause = f"Some patches failed application: {list(patch_application_errors.keys())}"

    attempt_record = {
        "attempt_id": attempt_id,
        "task_id": task_spec.id,
        "tier": task_spec.tier,
        "category": task_spec.category,
        "candidate_id": candidate_config.get("candidate_id", "cand"),
        "benchmark_release_id": manifest.get("benchmark_release_id", "gameforge-bench-v0.2.0"),
        "timestamp": time.time(),
        "duration_seconds": time.time() - start_time,
        "invocation": {
            "success": model_response.success,
            "error": model_response.error,
            "prompt_tokens": model_response.prompt_tokens,
            "completion_tokens": model_response.completion_tokens,
            "latency_seconds": model_response.total_duration_seconds,
            "cost_usd": model_response.cost_usd,
            "patches_extracted_count": len(patches_to_apply),
            "patches_applied_count": len(diffs),
            "effective_files_modified": effective_files_modified,
            "is_genuinely_different": (effective_files_modified > 0),
            "rejections": rejection_reasons,
            "patch_errors": patch_application_errors,
        },
        "grading": {
            "overall_status": final_status,
            "raw_harness_status": raw_grading_status,
            "failure_cause": failure_cause,
            "report_file": run_result.get("report_file"),
            "layers": run_result.get("report", {}).get("layers", {}),
            "probes_passed": sum(1 for p in run_result.get("report", {}).get("probes", {}).values() if p.get("passed")),
            "probes_total": len(run_result.get("report", {}).get("probes", {})),
        },
        "evidence": {
            "raw_output_path": str(raw_output_path),
            "diff_path": str(diff_file),
            "patch_audit_path": str(output_dir / "patch_application_audit.json"),
            "eval_workspace": str(attempt_candidate_dir),
        },
    }

    record_file = output_dir / "attempt_record.json"
    record_file.write_text(json.dumps(attempt_record, indent=2), encoding="utf-8")

    return attempt_record
