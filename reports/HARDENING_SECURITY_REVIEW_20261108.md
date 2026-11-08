# GameForge — Comprehensive Security & Threat Model Review

**Date:** 2026-11-08  
**Scope:** Security Posture, Threat Modeling, and Vulnerability Remediation for GameForge IDE  
**Classification:** Engineering Audit & Verification  
**Repositories:** Canonical `E:\gameforge_step1`; Mirrored Artifacts `E:\GameForge`  

---

## 1. Threat Model & Adversarial Surface

The GameForge IDE operates as an AI-powered game development studio integrating local/hosted large language models (LLMs), an embedded PySide6 GUI, autonomous agent loops, and execution hooks into Unreal Engine 5.7.4.

Because the IDE processes user prompts, code diffs, LLM-generated tool calls, and shell commands, the threat model must account for the following threat vectors:

```
[Untrusted External / Model Input]
                 │
                 ▼
 ┌───────────────────────────────┐
 │       Chat & Agent Loop       │ ◄── Threat A: Raw Payload Leak / Prompt Injection
 └───────────────┬───────────────┘
                 │ Tool Invocation
                 ▼
 ┌───────────────────────────────┐
 │      Security Boundary        │ ◄── Threat B: Path Traversal / Reparse Point Escape
 └───────────────┬───────────────┘
                 │ Path Validated
                 ▼
 ┌───────────────────────────────┐
 │   Command Broker & Approval   │ ◄── Threat C: Arbitrary Shell Injection / TOCTOU
 └───────────────┬───────────────┘
                 │ Approval Verified
                 ▼
 ┌───────────────────────────────┐
 │   Subprocess Direct Runner    │ ◄── Threat D: Zombie Workers / Network DOS
 └───────────────────────────────┘
```

### Threat Vectors Analyzed:
1. **Threat A (Prompt Injection & Tool Hijacking):** Untrusted input (e.g. from third-party C++ repositories, GDS files, or web snippets) attempts to trick the LLM into generating malicious commands or phantom edits.
2. **Threat B (Filesystem Jailbreak):** Model attempts to read or modify files outside the workspace root using relative traversals (`../../`), Windows drive letters, or NTFS reparse points / directory junctions.
3. **Threat C (Arbitrary Shell Injection & Unapproved Execution):** Dangerous commands executed via PowerShell or cmd instead of tokenized direct execution; tampering with pending approval records to bypass user consent.
4. **Threat D (Denial of Service / Zombie Worker Proliferation):** Blocking network requests in background threads that cannot be interrupted when the user cancels, consuming VRAM, CPU, and sockets indefinitely.

---

## 2. Hardened Security Controls & Defenses

### 2.1 Filesystem Jail & Boundary Enforcement (`boundary.py`)
- **Workspace Confinement:** All paths accessed by tools are resolved against `workspace_root.resolve()`. Any path outside this root raises `SecurityBoundaryError`.
- **NTFS Directory Junction & Reparse Point Detection:**
  In addition to standard POSIX symlinks (`Path.is_symlink()`), the boundary validator now explicitly inspects Windows NTFS reparse attributes using `FILE_ATTRIBUTE_REPARSE_POINT` (flag `0x400` via `os.lstat` and `os.path.isjunction`). Any directory junction pointing outside the workspace is blocked fail-closed.
- **Fail-Closed Traversal Walk:**
  The path component hierarchy is walked from root to leaf. Any `OSError` (such as permission denied or invalid handle) immediately triggers fail-closed error propagation rather than silent continuation.
- **Sensitive State Pattern Blacklist:**
  The `PROTECTED_PATTERNS` registry was expanded to prohibit read/write access to internal state stores:
  - `.gameforge/approvals/**`
  - `.gameforge/settings.json`
  - `.gameforge/ide_settings.ini`
  - `.gameforge/credentials`
  - `.git/**`, `.env`, private keys (`id_rsa`, `*.pem`), and `graders/protected/**`.

### 2.2 Shell-Free "Direct" Execution Standard (`command_contract.py`, `gateway.py`, `terminal_tools.py`)
- **Canonical "direct" Default:**
  Previously, `CommandExecutionRequest` and `tool_requires_approval()` defaulted to `"powershell"`, whereas `TerminalTools` ran as `"direct"`. This discrepancy has been eliminated. The entire stack defaults to `"direct"`.
- **Shell-Free Tokenization:**
  Commands executed under `"direct"` bypass shell interpreters (`cmd.exe` or `powershell.exe`) and pass argument vectors directly to `subprocess.Popen(args, shell=False)`. This neutralizes shell metacharacter injection (`&`, `|`, `;`, `$(...)`, `` `...` ``).
- **Approval Risk Classification:**
  Commands are analyzed by the command broker before execution. Any command mutating files, launching network sockets, or invoking external binaries requires explicit user approval via the GUI modal.

### 2.3 Approval Store Cryptographic Non-Repudiation (`approval_store.py`)
- **Strict Approval ID Pattern:**
  Approval IDs are strictly constrained to `^apr_[0-9a-f]{12}$`. Any attempt to supply path traversal strings (e.g. `apr_../../evil`) triggers a `ValueError`.
- **Cryptographic Operation Digest:**
  Each approval record calculates a SHA-256 digest over `(tool, args, session_id)`:
  ```python
  digest_payload = f"{tool}:{json.dumps(args, sort_keys=True)}:{session_id}"
  operation_digest = hashlib.sha256(digest_payload.encode()).hexdigest()
  ```
  Transitions verify that the record matches the requested operation, preventing substitute payloads.
- **Thread-Safe Atomic State Transitions:**
  State transitions (`PENDING` -> `APPROVED` -> `DONE` or `REJECTED`) are protected by a reentrant `threading.Lock`, preventing race conditions or double-spend of approvals.
- **Execution Receipts:**
  Approved actions produce an immutable execution receipt with timestamp, execution result status, and operation hash. `runtime.resume_task_after_approval` verifies this receipt before updating the session ledger.

### 2.4 Real-Time Socket Cancellation (`ollama_provider.py`)
- **Socket-Level Disconnection:**
  Blocking HTTP requests via `urllib.request.urlopen` now support a `cancel_event: threading.Event`.
- **Cancellation Monitor Thread:**
  When a user cancels a running generation, the monitor immediately closes the active HTTP response socket (`resp.close()`), causing the underlying Windows Winsock call to abort instantly without waiting for Ollama to finish generation. This prevents thread starvation and zombie generation runs.

### 2.5 AST Tool-Call Extraction & Streaming Leak Suppression (`tool_call_parser.py`)
- **Markdown Fence Immunity:**
  JSON examples inside ````json ... ```` code blocks in assistant explanations are protected from execution.
- **Balanced Brace Scanning:**
  Avoids naive regex matching by tracking brace depth while respecting string literal escape sequences (`\"`, `\\`).
- **Streaming Guard Filter:**
  The `StreamingToolGuard` intercepts streamed token deltas, buffers opening syntax until tool-call boundaries are verified, and prevents raw tool JSON from leaking to the developer's chat bubble.

---

## 3. Adversarial Test Coverage

The security hardening is backed by a suite of automated unit and integration tests:

| Test Identifier | Test Module | Security Guarantee Verified | Status |
|---|---|---|---|
| `test_approval_id_path_traversal_blocked` | `test_security_approval_hardening_20261108.py` | Traversal strings in approval IDs raise `ValueError` | PASS |
| `test_approval_digest_and_lock` | `test_security_approval_hardening_20261108.py` | SHA-256 operation digest calculation & thread-safe transition | PASS |
| `test_shell_default_consistency` | `test_security_approval_hardening_20261108.py` | Canonical `"direct"` shell across contract, gateway, and tools | PASS |
| `test_boundary_junction_and_protected_patterns` | `test_security_approval_hardening_20261108.py` | Reparse points and `.gameforge/approvals` protected fail-closed | PASS |
| `test_code_fence_json_not_executed` | `test_tool_call_parser.py` | Documentation code fences never trigger tool execution | PASS |
| `test_unknown_command_not_executed` | `test_tool_call_parser.py` | Unknown commands reject execution without error leakage | PASS |
| `test_escaped_quotes_and_braces_in_arguments` | `test_tool_call_parser.py` | Complex string escapes do not break parser containment | PASS |
| `test_agent_worker_cancellation_instant_cleanup` | `test_lifecycle_cancellation_hardening_20261108.py` | Socket monitor aborts blocking HTTP read upon cancellation | PASS |

---

## 4. Residual Risks & Ongoing Recommendations

1. **Host Embedded Terminal vs OS Sandbox:**
   As documented in `AGENTS.md`, the embedded IDE terminal is user-facing and interactive; it is not an OS security hypervisor. Agent-issued commands must continue to route exclusively through `CommandBroker` with direct execution allowlists.
2. **Local Model Sanitization:**
   Prompt injection mitigation at the parser level suppresses command execution and UI leaks. However, high-temperature open-weight models may still produce unexpected reasoning paths. The bounded iteration limit (`max_iterations = 12`) and repetitive tool call detectors must remain strictly enforced.
3. **Protected Grader Integrity:**
   All 5 protected test files (`graders/protected/`) remain 100% byte-for-byte identical to their original baseline hashes (`631776...`, `3ff897...`, `41c198...`, `69694c...`, `70f8ef...`). They must never be relaxed or modified by autonomous agents.
