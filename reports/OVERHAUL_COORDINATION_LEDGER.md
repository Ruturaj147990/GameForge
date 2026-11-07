# GameForge IDE — Master Engineering Overhaul Coordination Ledger

**Version:** 1.0.0-OVERHAUL  
**Principal Architect / Orchestrator:** Agent 1  
**Timestamp:** 2026-11-07T12:35:00Z  
**Status:** ACTIVE — PHASE 0 COMPLETE -> LAUNCHING PHASE 1  

---

## 1. Five-Agent Responsibility & Exclusive File Ownership Register

Strict file ownership rules are established below. Agents 2 and 3 operate in parallel during Phase 1 and **must not** modify each other's owned files. Cross-boundary interfaces are fixed in Phase 0 contracts.

| Agent | Role | Exclusive File Ownership Boundaries | Shared Contracts Read/Consumed |
|---|---|---|---|
| **Agent 1** | Main Orchestrator / Principal Architect | Project-wide oversight, release criteria, phase gating, `context.md`, `reports/OVERHAUL_COORDINATION_LEDGER.md` | Authoritative contract definitions in `src/gameforge_ide/backend/models/` |
| **Agent 2** | Backend Specialist | `src/gameforge_ide/backend/` (`agent/`, `tools/`, `security/`, `session_manager.py`, `context_manager.py`, `plan_generator.py`, `services/agent_service.py`), `src/gameforge_ide/core/process_manager.py`, `tests/unit/backend/` | `PermissionsMode`, `CommandExecutionRequest`, `CommandExecutionResult`, `ContextUsageReport`, `PlanArtifact` |
| **Agent 3** | Frontend Specialist | `src/gameforge_ide/desktop/` (`views/`, `panels/`, `widgets/`, `tokens.py`, `main_window.py` UI layouts), `tests/unit/desktop/` | `PermissionsMode` enum, `ContextUsageReport` schema, `TaskMode` enum, `activity_card.py` event signals |
| **Agent 4** | Backend–Frontend Integration Specialist | End-to-end event loops, `MainWindow` signal wiring, state synchronization, integration test suites (`tests/gameforge_1_0/`, new E2E tests) | Bridge between Backend Broker/Services and Frontend Panels/Cards |
| **Agent 5** | GameForge–Unreal Integration Specialist | `src/gameforge_ide/unreal/` (`toolchain.py`, `live_editor.py`, `GameForge/` plugin source), `src/gameforge_ide/composer/`, `src/gameforge_ide/forge/` | Toolchain build targets, UAT BuildCookRun, scenario generation & replay |

---

## 2. Shared Interface Contracts (Established by Agent 1 in Phase 0)

### 2.1 Permissions Mode Contract (`src/gameforge_ide/backend/models/modes.py`)
```python
class PermissionsMode(str, Enum):
    REQUEST_ALL = "request_all"      # Every command requires explicit user approval before execution
    AUTO = "auto"                    # Routine safe workspace development operations run automatically; sensitive/uncertain require approval
    UNRESTRICTED = "unrestricted"    # Maximum application autonomy without routine approval prompts; platform OS boundaries still apply
```
- **UI Label:** `Permissions Mode` with items `Request All`, `Auto`, `Unrestricted`.
- **Approach Setting:** Remains completely independent (`Planning` vs `Fast`).
- **Persistence:** Saved in user settings (`default_permissions_mode`) and active session (`session.permissions_mode`).

### 2.2 Central Command Broker Contract (`src/gameforge_ide/backend/models/command_contract.py`)
- Request: `CommandExecutionRequest` (command, shell, working_directory, permissions_mode, reason, agent_id, execution_id, timeout_seconds)
- Result: `CommandExecutionResult` (execution_id, command, shell, status, exit_code, stdout, stderr, duration_s, risk_category, requires_approval, approved_by_user)
- State Machine: `CREATED -> VALIDATING -> AWAITING_APPROVAL / APPROVED -> RUNNING -> VERIFYING -> SUCCEEDED / FAILED / BLOCKED / CANCELLED`
- Windows Shell Support: PowerShell (`pwsh`, `powershell.exe`), Command Prompt (`cmd.exe`), Git Bash, direct. Handles PowerShell aliases (e.g. `cat` -> `Get-Content`).

### 2.3 Context Usage Contract (`src/gameforge_ide/backend/models/context_usage.py`)
- Report: `ContextUsageReport` (model_id, nominal_capacity, effective_budget, used_tokens, remaining_tokens, utilization_pct, is_estimated, estimation_method, breakdown)
- Breakdown: `ContextBreakdown` (system_prompt, conversation, memory, retrieved_docs, tool_definitions, other_overhead, reserved_output)

---

## 3. Authoritative Issue & Defect Ledger

| Issue ID | Severity | Subsystem | Owner | Confirmed Root Cause | Implementation Status | Test / Verification |
|---|---|---|---|---|---|---|
| **DEF-301** | Critical | Permissions / Shell Execution | Agent 2 | `TerminalTools._parse_command` rejected non-allowlisted executables (`cat`) and all shell syntax regardless of user permissions | OPEN | Test matrix across Request All, Auto, Unrestricted with `cat`, `dir`, `git`, `pytest` |
| **DEF-302** | High | LLM Planning | Agent 2 | `_build_plan_artifact` in `runtime.py` returned hardcoded static Sudoku steps instead of dispatching prompt to configured LLM | OPEN | Verify genuine Ollama model call, plan ID provenance, and dynamic step generation |
| **DEF-303** | High | Context Telemetry | Agent 2 & Agent 3 | No backend context breakdown or frontend context-usage indicator existed | OPEN | Backend `ContextManager.get_context_usage()`, Frontend `ContextUsageIndicator` widget with tooltip breakdown |
| **DEF-304** | High | Multi-File Repairs & Native Tools | Agent 2 | Local models emit markdown code blocks instead of structured tool calls; 4+ file repairs lack atomic manifest | OPEN | Multi-file manifest, dependency ordering, bounded recovery, and compilation gate |
| **DEF-305** | Medium | Windows Process & Lock Management | Agent 2 | File cleanup on Windows build directories collided with transient `.pdb`/`.exe` locks | OPEN | `ProcessLifecycleManager` with Job Objects and lock-aware exponential backoff retry service |
| **DEF-306** | High | UI Inventory & Permissions Mode | Agent 3 | TopBar/ChatPanel used legacy `AutonomyProfile` (Manual, Auto-Edit, Agentic) instead of `PermissionsMode` | OPEN | Component tests for `PermissionsMode` dropdown, signal synchronization, and card feedback |
| **DEF-307** | High | Backend–Frontend Integration | Agent 4 | Wiring contract mismatches between approval cards, context updates, and streaming events | OPEN | E2E test suite covering full conversational & build workflows |
| **DEF-308** | Critical | Unreal UAT Exit Code 25 | Agent 5 | In `run_20261107_103542_96db5b`, UAT failed with code 25 (`Error_MissingExecutable`) because standalone game target was unbuilt | OPEN | Pre-package validation ensuring game target compiled before `BuildCookRun` packaging |
| **DEF-309** | Medium | Authoritative Plugin Sync | Agent 5 | Plugin deployment could drift between template copies and project destinations | OPEN | Authoritative plugin manifest verification and drift check before packaging |
| **DEF-310** | Medium | Desktop IDE Distribution | Agent 1 | No standalone distribution packaging script / PyInstaller configuration verified | OPEN | Packaging configuration and verification following project completion |
