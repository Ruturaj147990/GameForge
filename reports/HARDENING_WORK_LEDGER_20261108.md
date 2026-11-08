# GameForge — Hardening Work Ledger (2026-11-08)
**Date:** 2026-11-08T12:55:00+05:30  
**Baseline Commit:** `b7618403e730612e894f407ab51d3dd02fa56ae5`  
**Max Parallel Agents:** 5 (Agent 1 Lead Coordinator + 4 Specialists)

---

## 1. Five-Agent Team & Exclusive File Ownership

| Agent | Role | Exclusive Owned Files | Primary Deliverables |
|---|---|---|---|
| **Agent 1** | **Principal Coordinator & Unreal Release Integration** | `E:\GameForge\projects\CounterStrike\Source\CounterStrike\GFGameImpl.{h,cpp}`, `src/gameforge_ide/pipeline/autofix.py`, `src/gameforge_ide/backend/agent/code_verify.py`, `configs/engine_knowledge_registry.json`, `context.md`, `reports/*` | Fix UE 5.7.4 color constants (`FLinearColor::Gray`, `FColor::Orange`) and `GFGameImpl` overrides, build target, orchestrate 5 agents, maintain work ledger and final verification. |
| **Agent 2** | **Backend Runtime, Tool Protocol & Context Autonomy** | `src/gameforge_ide/backend/agent/runtime.py`, `src/gameforge_ide/backend/agent/tool_call_parser.py`, `src/gameforge_ide/backend/agent/context_manager.py`, runtime unit tests | Canonical tool call parser/normalizer, flat command dialect, context budget propagation, tool schema context accounting, typed tool history, trusted approval receipts. |
| **Agent 3** | **Providers, Async Lifecycle & Cancellation** | `src/gameforge_ide/desktop/services/agent_service.py`, `src/gameforge_ide/backend/providers/ollama_provider.py`, `src/gameforge_ide/core/process_manager.py`, `src/gameforge_ide/core/jobs.py` | Eliminating `QThread.terminate()`, cancellable provider transport with response closure, thread-safe cancellation tokens, safe workspace switching state machine, executor cleanup. |
| **Agent 4** | **Security, Approvals & Command Broker** | `src/gameforge_ide/backend/security/boundary.py`, `src/gameforge_ide/backend/tools/command_broker.py`, `src/gameforge_ide/backend/tools/terminal_tools.py`, `src/gameforge_ide/backend/tools/gateway.py`, `src/gameforge_ide/storage/approval_store.py`, `src/gameforge_ide/backend/tools/fs_tools.py`, `edit_tools.py` | Immutable command request normalization, approval ID syntax validation (`apr_[0-9a-f]{12}`), one-time approval consumption & execution receipts, Windows junction handling (Python 3.10-3.14 safe), `.gameforge/approvals` protection. |
| **Agent 5** | **Chat UI, Stream Presentation & Interaction Quality** | `src/gameforge_ide/desktop/panels/chat_panel.py`, `src/gameforge_ide/desktop/panels/activity_card.py`, desktop UI tokens / styles | Calmer borderless assistant chat presentation, right-aligned user bubbles, hover copy action, inline activity chips without raw JSON leak, smooth throttled streaming, truthful status indicators. |

---

## 2. Shared Interface Contracts

1. **Tool-Call Contract:**  
   `ParsedToolCall(name: str, arguments: dict[str, Any], call_id: Optional[str], start: int, end: int, source: str)`.  
   Centralized in `tool_call_parser.py`. Normalizes native provider calls and legacy flat format `{"command": "read_file", "path": "..."}`. Returns typed calls and cleaned narrative text. Registered tool names/aliases verified via `ToolGateway`.

2. **Cancellation Contract:**  
   `CancellationToken` provides thread-safe, idempotent cooperative cancellation. Provider requests register response/socket abort callbacks. Aborted provider requests close the socket immediately. Child processes register Job Object / process termination.

3. **Task State & Execution Receipt Contract:**  
   State transitions are strictly one-way: `CREATED -> RUNNING -> WAITING_APPROVAL -> RUNNING -> COMPLETED / FAILED / CANCELLED / BLOCKED`.  
   `resume_task_after_approval()` strictly requires a valid, verified execution receipt bound to the approved operation digest. Caller-supplied `tool_result` dictionaries are never trusted without receipt verification.

4. **Command Request Contract:**  
   `CommandExecutionRequest` is canonicalized once with default `shell="direct"`. The same normalized immutable object is passed to `tool_requires_approval()`, `classify_request()`, the approval store, audit logs, and `execute_request()`.

5. **UI Activity Event Contract:**  
   `tool_call_started`, `tool_call_finished`, `tool_result`, `status`, and `token` events carry `event_id`, `task_id`, `tool`, `display_label`, and status. UI never parses raw text for tool commands.

6. **Context Budget Contract:**  
   `fit_history_to_context()` includes effective `output_tokens` in its returned budget dict. Callers pass this exact value as `max_tokens` / `num_predict` to providers. Preflight budget includes tool schema tokens alongside system prompt and conversation messages.

---

## 3. Work Item Ledger & Acceptance Tracking

| Item ID | Category | Description | Owner | Status | Evidence / Commit |
|---|---|---|---|---|---|
| **WI-1.1** | Unreal C++ | Fix `FLinearColor::Grey` -> `FLinearColor::Gray` and `Orange` in `Color.h` | Agent 1 | IN PROGRESS | Verified local `Color.h:457,758` |
| **WI-1.2** | Unreal C++ | Fix `CounterStrike/Source/CounterStrike/GFGameImpl.{h,cpp}` method overrides | Agent 1 | IN PROGRESS | Align with `GFGameBase.h` virtuals |
| **WI-1.3** | Autofix/Invariants | Add `FLinearColor::Gray` and `FColor::Orange` to `autofix.py`, `code_verify.py`, `engine_knowledge_registry.json` | Agent 1 | PENDING | C++ invariant updates |
| **WI-2.1** | Tool Protocol | Implement canonical `tool_call_parser.py` supporting flat `command` and streaming guard | Agent 2 | PENDING | Unit test matrix |
| **WI-2.2** | Runtime Autonomy | Wire runtime to canonical parser, eliminate regex cleaning and separate UI detector | Agent 2 | PENDING | End-to-end extraction tests |
| **WI-2.3** | Context Budget | Fix `output_tokens` propagation and account for native tool schemas in context budget | Agent 2 | PENDING | Context limit tests (2K-32K) |
| **WI-2.4** | Tool History | Canonicalize tool history records (`tool_name` vs `tool`) with backwards compatibility | Agent 2 | PENDING | History migration tests |
| **WI-2.5** | Approval Receipt | Enforce trusted execution receipt in `resume_task_after_approval()` | Agent 2 | PENDING | Anti-forgery tests |
| **WI-3.1** | Cancellation | Implement thread-safe `CancellationToken` and socket abort in `OllamaProvider` | Agent 3 | PENDING | Cancel-during-inference tests |
| **WI-3.2** | QThread Lifecycle | Remove `QThread.terminate()` fallback; use cooperative cancellation & event-driven teardown | Agent 3 | PENDING | Teardown stress tests |
| **WI-3.3** | Workspace Switch | Serialize `set_workspace()` and prevent UI thread runtime initialization in `stop()` | Agent 3 | PENDING | Concurrency tests |
| **WI-3.4** | Executor & Cleanup | Clean up default asyncio loop executor, task references, and child processes on stop | Agent 3 | PENDING | Resource leak tests |
| **WI-4.1** | Command Normalization | Harmonize `shell="direct"` across `TerminalTools`, `ToolGateway`, `CommandExecutionRequest` | Agent 4 | PENDING | Semantic consistency tests |
| **WI-4.2** | Approval Security | Validate approval IDs (`_APPROVAL_ID_RE`), atomic compare-and-set transitions, one-time use | Agent 4 | PENDING | Approval attack tests |
| **WI-4.3** | Path & Reparse | Harden Windows junction/reparse-point checks, fail-closed on `OSError` | Agent 4 | PENDING | Windows path tests |
| **WI-4.4** | App State Boundary | Protect `.gameforge/approvals`, secrets, and metadata from model write tools | Agent 4 | PENDING | Boundary attack tests |
| **WI-5.1** | Chat Visuals | Calm borderless assistant messages, right-aligned user bubbles, hover copy action | Agent 5 | PENDING | Theme & style tests |
| **WI-5.2** | Activity Chips | Streamlined inline tool chips using existing `activity_card.py` items without raw JSON | Agent 5 | PENDING | Activity tests |
| **WI-5.3** | UI Streaming | Smooth throttled rendering, scroll anchoring, and truthful status indicators | Agent 5 | PENDING | Streaming performance tests |
