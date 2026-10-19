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


def extract_code_blocks(text: str, allowed_paths: Optional[List[str]] = None) -> Dict[str, str]:
    """Extracts code blocks from model response mapped to target file paths."""
    patches: Dict[str, str] = {}
    
    # Pattern 1: Explicit file path annotation like "### File: Source/GameForgePilot/..." or "**File:** `path`"
    file_header_pattern = re.compile(
        r"(?:###|//|#|\*\*)\s*(?:File|Path|Target):\s*`?([a-zA-Z0-9_\-\./\\]+)`?\s*(?:\*\*)?\s*\n```(?:[a-zA-Z0-9_+\-]+)?\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    for match in file_header_pattern.finditer(text):
        path_str = match.group(1).strip().replace("\\", "/")
        content = match.group(2)
        patches[path_str] = content

    # Pattern 2: Generic code blocks if no explicit file annotations matched
    if not patches:
        generic_pattern = re.compile(r"```(?:cpp|c\+\+|csharp|cs|yaml|json)?\n(.*?)```", re.DOTALL | re.IGNORECASE)
        matches = generic_pattern.findall(text)
        if matches and allowed_paths:
            # Map primary code block to first allowed edit path if it looks like a path
            for ap in allowed_paths:
                clean_ap = ap.strip().replace("\\", "/")
                if "/" in clean_ap or clean_ap.endswith((".cpp", ".h", ".cs", ".yaml", ".json")):
                    patches[clean_ap] = matches[0]
                    break

    return patches


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

        payload = {
            "model": model_name,
            "prompt": request.prompt,
            "system": request.system_prompt or "",
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
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
    if model_response.success and model_response.code_patches:
        for rel_path, code in model_response.code_patches.items():
            # Check policy: is rel_path within allowed_edit_paths or source tree?
            norm_rel = rel_path.replace("\\", "/").lstrip("/")
            allowed = False
            for ap in task_spec.allowed_edit_paths:
                norm_ap = ap.replace("\\", "/").rstrip("/")
                if norm_rel.startswith(norm_ap) or norm_rel.endswith(norm_ap.split("/")[-1]):
                    allowed = True
                    break
                elif "source" in norm_ap.lower() and ("source/" in norm_rel.lower() or norm_rel.lower().endswith((".cpp", ".h", ".cs"))):
                    allowed = True
                    break
                elif "content" in norm_ap.lower() and ("content/" in norm_rel.lower() or norm_rel.lower().endswith((".uasset", ".json"))):
                    allowed = True
                    break
            
            target_path = attempt_candidate_dir / norm_rel
            old_content = ""
            if target_path.is_file():
                old_content = target_path.read_text(encoding="utf-8", errors="replace")

            if allowed:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(code, encoding="utf-8")
                patch_success = True
                
                # Compute unified diff
                diff_lines = list(difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    code.splitlines(keepends=True),
                    fromfile=f"a/{norm_rel}",
                    tofile=f"b/{norm_rel}",
                ))
                diffs[norm_rel] = "".join(diff_lines)

    # Save diffs
    diff_file = output_dir / "candidate_diffs.patch"
    diff_file.write_text("\n\n".join(f"# {p}\n{d}" for p, d in diffs.items()), encoding="utf-8")

    # 5. Run grading pipeline on the candidate workspace
    run_result = runner.run_task(
        task_id=task_spec.id,
        engine_name="unreal" if "engine_neutral" not in task_spec.category else "auto",
        candidate_dir=attempt_candidate_dir,
        candidate_id=candidate_config.get("candidate_id", "cand"),
        candidate_type="model_candidate",
    )

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
            "patches_extracted_count": len(model_response.code_patches),
            "patches_applied_count": len(diffs),
        },
        "grading": {
            "overall_status": run_result.get("status", "UNVERIFIED"),
            "report_file": run_result.get("report_file"),
            "layers": run_result.get("report", {}).get("layers", {}),
            "probes_passed": sum(1 for p in run_result.get("report", {}).get("probes", {}).values() if p.get("passed")),
            "probes_total": len(run_result.get("report", {}).get("probes", {})),
        },
        "evidence": {
            "raw_output_path": str(raw_output_path),
            "diff_path": str(diff_file),
            "eval_workspace": str(attempt_candidate_dir),
        },
    }

    record_file = output_dir / "attempt_record.json"
    record_file.write_text(json.dumps(attempt_record, indent=2), encoding="utf-8")

    return attempt_record
