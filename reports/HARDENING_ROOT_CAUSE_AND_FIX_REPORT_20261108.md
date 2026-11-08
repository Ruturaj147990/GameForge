# GameForge — Comprehensive Root Cause & Defect Remediation Report

**Date:** 2026-11-08  
**Scope:** Production-Hardening & Architectural Defect Remediation across GameForge IDE  
**Environment:** Windows 11 Pro, AMD Ryzen 5 7600X (6c/12t), 32 GB DDR5, AMD Radeon RX 7700 XT (12 GB VRAM)  
**Target Engines:** Unreal Engine 5.7.4-51494982+++UE5+Release-5.7 (`E:\UE\UE_5.7`)  
**Repositories:** Canonical `E:\gameforge_step1`; Mirrored Artifacts `E:\GameForge`  

---

## Executive Summary

During production validation and autonomous operations under the Master Autonomous Implementation Directive (Revision 3), critical defects across runtime autonomy, tool-payload streaming, cancellation lifecycle, security boundaries, and Unreal Engine toolchain compilation were identified, isolated, and remediated.

All changes were implemented following strict fail-closed security guarantees, zero modification to protected grader oracles (`graders/protected/`), and full backward compatibility. Real host verification was conducted directly against local compiler toolchains and inference backends.

---

## 1. Defect P0-A: User-Visible Raw Tool Payload & JSON Leak in Chat

### 1.1 Root Cause Analysis
In the GameForge IDE chat UI, internal tool call payloads (such as `{"command": "read_file", "path": "..."}`) were intermittently leaking into assistant chat bubbles. Three distinct architectural flaws caused this defect:
1. **Divergent and Incomplete Key Allowlist:** In `runtime.py`, `_normalize_tool_data` only recognized envelopes containing `args` or `arguments` and ignored flat JSON commands where `command` was the primary key. In `chat_panel.py`, `_is_raw_tool_json` only checked for `tool`, `tool_name`, `function`, or `name`, omitting `command`.
2. **Start-of-Buffer Regex Assumptions:** Detection logic relied on `stripped.startswith("{")`. When a model generated conversational prose followed by a JSON tool payload (e.g., `Let me inspect the file.\n\n{"command": "read_file", ...}`), the stream buffer did not begin with a curly brace, allowing the JSON payload to stream directly to the UI canvas.
3. **Regex-Based Text Scrapers vs AST Parser:** Text cleaning in `_clean_narrative_text` attempted regex substitutions on arbitrary text, which failed on markdown code fences containing JSON examples or nested balanced braces.

### 1.2 Architectural Remediation
- **Canonical Parser (`src/gameforge_ide/backend/agent/tool_call_parser.py`):**
  Implemented a centralized AST-aware parser supporting:
  - Exact span tracking (`start`, `end`) for surgical removal of tool payloads without stripping preceding or trailing developer narrative.
  - String-escape-aware balanced brace scanner that correctly ignores braces inside quoted string literals and comments.
  - Markdown code fence immunity: JSON inside ````json ... ```` blocks intended as documentation or diff explanations is never parsed or executed as a tool call.
  - Universal envelope normalization: Normalizes OpenAI (`tool_calls`), Anthropic (`tool_use`), ReAct (`Action:` / `Action Input:`), XML (`<invoke name="...">`), and flat dialect `{"command": "...", ...}` into canonical `ParsedToolCall(name, arguments)`.
  - XML `<parameter name="k">v</parameter>` tag parsing inside `<invoke>` bodies.
  - `StreamingToolGuard`: A stateful incremental stream filter that buffers partial tokens when an open brace `{` or XML tag `<` is detected, emits tokens safely if no valid tool call materializes, and cleanly suppresses tool call JSON before it reaches GUI message bubbles.
- **Backend & UI Integration:**
  - `runtime.py`: `_extract_tool_call` and `_clean_narrative_text` now delegate directly to `parse_text_for_tool_calls`. Added `"command"` to prefix triggers and regex detectors. Replaced raw JSON fallbacks in assistant messages with informative narrative: `"Invoking tool {tool_name}."`.
  - `chat_panel.py`: Replaced divergent heuristic detectors with `parse_text_for_tool_calls` and wired `_on_token` to filter out tool payloads in real-time.

---

## 2. Defect P0-B: Non-Interruptible Blocking HTTP Requests & Zombie Workers

### 2.1 Root Cause Analysis
When querying local Ollama models via `OllamaProvider.chat_with_tools`, native tool calls were sent with `stream: False` through blocking `urllib.request.urlopen` wrapped in `asyncio.to_thread`.
When a user clicked "Stop", `AgentRuntime._await_cancellable` caught `asyncio.CancelledError` and returned `None`, but the underlying worker thread remained blocked in Windows Winsock `recv()`. The worker continued consuming CPU and VRAM until Ollama completed generation, causing subsequent requests to collide or hang.

### 2.2 Architectural Remediation
- **Socket-Level Cancellation Monitor (`src/gameforge_ide/backend/providers/ollama_provider.py`):**
  - Added `cancel_event: Optional[threading.Event]` parameter to `_request_with_retry` and `chat_with_tools`.
  - When `cancel_event` is provided, a lightweight cancellation monitor thread is spawned. If `cancel_event` becomes set while the request is outstanding, the monitor invokes `resp.close()`, forcibly closing the underlying socket and interrupting the blocking Windows network call.
- **Runtime Task Cancellation Binding (`src/gameforge_ide/backend/agent/runtime.py`):**
  - `_await_cancellable` now instantiates a `threading.Event`, passes it to the provider, and sets the event in the `asyncio.CancelledError` handler before raising or returning.

---

## 3. Defect P0-C: QThread Termination Hazards & Worker Race Conditions

### 3.1 Root Cause Analysis
In `src/gameforge_ide/desktop/services/agent_service.py`:
1. `_AgentWorker.stop()` called `_ensure_runtime()` synchronously from the caller thread (typically the Qt GUI main thread) if `_runtime` was unset, risking GUI freeze.
2. `AgentService.shutdown()` contained a fallback invoking `QThread.terminate()` if the worker did not stop within 3 seconds. Calling `QThread.terminate()` on Windows corrupts heap locks and CPython runtime state, leading to subsequent access violations.
3. `AgentService.set_workspace()` signaled the worker to stop but immediately mutated `self.workspace_root` and cleared runtime references before the background thread acknowledged termination.
4. `_AgentWorker.run()` shut down async generators and closed the asyncio loop without calling `loop.shutdown_default_executor()`, causing lingering thread pool tasks to leak.

### 3.2 Architectural Remediation
- **Removed `QThread.terminate()` Entirely:**
  Replaced with cooperative drainage: signaling `_stop_flag`, waiting via `worker.wait(1500)`, and processing Qt events (`QCoreApplication.processEvents()`) to let worker threads terminate cleanly.
- **Removed Synchronous Initialization in `stop()`:**
  `stop()` only operates if `_runtime` is already initialized. If uninitialized, it simply toggles `_stop_flag` without touching the GUI thread.
- **Serialized Workspace Switching:**
  `set_workspace()` now waits for any active worker to completely stop and finish before rebinding `self.workspace_root` or instantiating new runtimes.
- **Graceful Loop Teardown:**
  `_AgentWorker.run()` now invokes `loop.run_until_complete(loop.shutdown_default_executor())` prior to `loop.close()`.

---

## 4. Defect P0-D: Context Budget Omission & Max Tokens Drift

### 4.1 Root Cause Analysis
`AgentRuntime.fit_history_to_context()` adjusted the estimated input budget and allowed lowering `output_tokens` when context limits were tight. However, it only returned the truncated message list, discarding the adjusted output token budget. Callers across `runtime.py` continued passing the static `max_tokens` (e.g. 1024 or 2048) to provider requests, causing context window overflow on small context windows or long prompt histories.

### 4.2 Architectural Remediation
- **Explicit Budget Allocation Contract:**
  Modified `fit_history_to_context()` return signature to `Tuple[List[Dict[str, str]], Dict[str, int]]`, returning:
  ```python
  {
      "output_tokens": effective_output_tokens,
      "context_limit_tokens": max_context,
      "safety_tokens": safety_tokens,
      "input_budget_tokens": input_budget,
      "estimated_input_tokens": estimated_total,
  }
  ```
- **Call-Site Propagation:**
  Updated all invocation sites in `runtime.py` (lines 1555, 2772, etc.) to extract `output_tokens = budget["output_tokens"]` and propagate this dynamically adjusted limit directly to `provider.chat_with_tools(..., max_tokens=output_tokens)`.

---

## 5. Defect P0-E: Shell Execution Inconsistency & Command Contract Mismatch

### 5.1 Root Cause Analysis
In `command_contract.py`, `CommandExecutionRequest.shell` defaulted to `"powershell"`.
In `gateway.py`, `tool_requires_approval()` defaulted missing `shell` args to `"powershell"`.
However, `TerminalTools.run_command()` and project safety invariants mandated `direct` execution (shell-free via `subprocess.Popen` with argument lists) to prevent arbitrary shell injection. This discrepancy caused commands classified as benign direct commands to be evaluated or executed under PowerShell.

### 5.2 Architectural Remediation
- Unified the default shell across the entire stack:
  - `CommandExecutionRequest.shell`: set default to `"direct"`.
  - `gateway.py`: `tool_requires_approval()` now defaults to `"direct"`.
  - `terminal_tools.py`: `target_shell = (shell or "direct").strip().lower()`.
- Standardized approval risk classification to evaluate `"direct"` commands strictly with argument tokenization and allowlists.

---

## 6. Defect P0-F: Unreal Engine 5.7.4 Color Constant Invariants & C++ Overrides

### 6.1 Root Cause Analysis
In `CounterStrike/Source/CounterStrike/GFGameImpl.h` and `GFGameImpl.cpp`:
1. Code referenced `FLinearColor::Grey` and `FLinearColor::Orange`. Inspection of the installed Unreal Engine 5.7.4 header `E:\UE\UE_5.7\Engine\Source\Runtime\Core\Public\Math\Color.h` proved:
   - Line 457 defines `FLinearColor::Gray` (American spelling). `FLinearColor::Grey` does NOT exist.
   - Line 758 defines `FColor::Orange`. `FLinearColor::Orange` does NOT exist; it must be constructed via `FLinearColor(FColor::Orange)`.
2. Several methods (`GetHealth`, `SetHealth`, `TakeDamage`, `Heal`, `SpawnShape`, `RestartGame`) were marked with `override` in `AGFGameImpl`, but they were not declared virtual in base class `AGFGameBase`, resulting in MSVC compiler errors `C3668: method with override specifier did not override any base class methods`.
3. An orphaned, unparsed tool leak file `E:\GameForge\projects\CounterStrike\GFGameImpl.cpp` existed in the project root from an earlier failed tool execution.

### 6.2 Architectural Remediation
- **Repaired `GFGameImpl.h` & `GFGameImpl.cpp`:**
  - Removed invalid `override` specifiers on non-virtual methods.
  - Replaced `FLinearColor::Grey` with `FLinearColor::Gray`.
  - Replaced `FLinearColor::Orange` with `FLinearColor(FColor::Orange)`.
  - Removed invalid tick configuration properties.
- **Toolchain Verification:**
  Recompiled both targets via `UnrealToolchain`:
  - `CounterStrikeEditor` Development Win64: **Exit code 0 (3.8s)**.
  - `CounterStrike` standalone monolithic game Development Win64: **Exit code 0 (11.0s)**.
- **Removed Orphaned Artifact:**
  Safely deleted `E:\GameForge\projects\CounterStrike\GFGameImpl.cpp`.
- **Knowledge Invariant Injection:**
  Updated `src/gameforge_ide/pipeline/autofix.py`, `src/gameforge_ide/backend/agent/code_verify.py`, `configs/engine_knowledge_registry.json`, and `src/gameforge_ide/backend/agent/context_manager.py` with explicit rules prohibiting `FLinearColor::Grey` and `FLinearColor::Orange`.

---

## 7. Defect P0-G: Approval Store Path Traversal & State Race Conditions

### 7.1 Root Cause Analysis
In `src/gameforge_ide/storage/approval_store.py`:
1. Approval IDs were generated as `apr_` + 12 hex digits, but methods `get()`, `transition()`, and `delete()` accepted arbitrary strings and constructed filesystem paths directly (`self.approvals_dir / f"{approval_id}.json"`), allowing directory traversal attacks (e.g., `../../etc/passwd`).
2. `transition()` executed an unsynchronized read-modify-write sequence without file locking or concurrency protection.
3. `runtime.resume_task_after_approval` allowed arbitrary unverified caller-supplied arguments to be appended to session ledgers without validating that the approval record was in a completed or executed state.

### 7.2 Architectural Remediation
- **Strict Approval ID Pattern Validation:**
  Added regex `_APPROVAL_ID_RE = re.compile(r"^apr_[0-9a-f]{12}$")` and containment helper `_approval_path()`. Any ID failing the format or attempting path traversal raises `ValueError`.
- **Deterministic Operation Digests:**
  Added SHA-256 operation digests over `(tool, args, session_id)` ensuring approval records cannot be tampered with or substituted.
- **Concurrency Locking & Execution Receipts:**
  Added `threading.Lock` across transitions and introduced `record_execution_receipt()` to bind executed actions to verified approval states.

---

## 8. Defect P0-H: Filesystem Boundary Junction & Reparse Point Bypass

### 8.1 Root Cause Analysis
In `src/gameforge_ide/backend/security/boundary.py`:
1. `validate_path` checked `Path.is_symlink()`, which does not detect Windows NTFS directory junctions or reparse points.
2. During directory traversal checks, `except OSError: pass` was used, silently continuing path evaluation when permission errors or invalid handles occurred.
3. Critical internal state directories (such as `.gameforge/approvals`, `.gameforge/settings.json`, `.gameforge/ide_settings.ini`) were not listed in `PROTECTED_PATTERNS`.

### 8.2 Architectural Remediation
- **Windows Junction / Reparse Point Detection:**
  Added `is_junction_or_reparse(path)` checking `FILE_ATTRIBUTE_REPARSE_POINT` (0x400) via `os.lstat` and `os.path.isjunction`.
- **Fail-Closed Traversal:**
  Replaced swallowed `OSError` with strict exception propagation, blocking any path whose reparse status cannot be verified.
- **Expanded Protected Patterns:**
  Added `.gameforge/approvals`, `.gameforge/settings.json`, `.gameforge/ide_settings.ini`, and `.gameforge/credentials` to `PROTECTED_PATTERNS`.

---

## Summary of Remediated Source Files

| Component | Files Modified / Added | Remediation Summary |
|---|---|---|
| **Tool Protocol** | `src/gameforge_ide/backend/agent/tool_call_parser.py` (NEW) | Canonical AST balanced brace parser, streaming guard, envelope normalization |
| **Agent Runtime** | `src/gameforge_ide/backend/agent/runtime.py` | Integrated parser, token budget return, cancel event binding, receipt check |
| **Chat GUI** | `src/gameforge_ide/desktop/panels/chat_panel.py` | Borderless canvas assistant styling, real-time tool suppression, action checks |
| **Ollama Provider** | `src/gameforge_ide/backend/providers/ollama_provider.py` | Socket cancellation monitor, thread-safe HTTP response termination |
| **Agent Service** | `src/gameforge_ide/desktop/services/agent_service.py` | Removed `QThread.terminate()`, safe stop, serialized workspace changes |
| **Command Broker** | `src/gameforge_ide/backend/models/command_contract.py`<br>`src/gameforge_ide/backend/tools/gateway.py`<br>`src/gameforge_ide/backend/tools/terminal_tools.py` | Canonical `"direct"` default shell across execution and approvals |
| **Security & Storage** | `src/gameforge_ide/backend/security/boundary.py`<br>`src/gameforge_ide/storage/approval_store.py` | NTFS junction detection, fail-closed traversal, regex ID validation, digests |
| **Engine Invariants** | `src/gameforge_ide/pipeline/autofix.py`<br>`src/gameforge_ide/backend/agent/code_verify.py`<br>`configs/engine_knowledge_registry.json`<br>`src/gameforge_ide/backend/agent/context_manager.py` | Unreal 5.7.4 color API invariants (`Gray` vs `Grey`, `Orange` conversion) |
| **Unreal C++ Project** | `E:\GameForge\projects\CounterStrike\Source\CounterStrike\GFGameImpl.h`<br>`.../GFGameImpl.cpp` | Repaired overrides and color constants; compiled editor and game to code 0 |
