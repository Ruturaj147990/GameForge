# GAMEFORGE — AUDIT REMEDIATION & FIX LOG (2026-11-08)

This document tracks all defects discovered during the full system audit, their root causes, user-visible impacts, exact remediation, and verification evidence.

---

### DEF-AUDIT-01: Agent Preflight Failure on Models with 4K Context Windows
- **Severity:** P1 (Core Workflow Blocker)
- **Affected File:** `src/gameforge_ide/backend/agent/runtime.py`
- **Root Cause:** In `AgentRuntime`, `output_tokens` was rigidly calculated as `min(4096, max(1024, capabilities.max_context // 4))`. For a 4,096-context model, this reserved 1,024 tokens for output and 128 for safety, leaving an input budget of `4096 - 1024 - 128 = 2944` tokens. Because the complete system prompt (incorporating tool schemas, capability manifests, and project grounding) measures ~3,014 tokens, `fit_history_to_context` raised an unhandled `ValueError`, crashing before any model or tool invocation.
- **User-Visible Impact:** Tasks run against smaller models (e.g. 4K context) immediately failed with `Prompt/context preflight failed: GameForge system context is estimated at 3016 tokens, above the 2944-token input budget for this model.`
- **Remediation:**
  1. Updated `output_tokens` calculation for `<= 4096` context windows to budget `min(512, max(256, max_ctx // 8))`.
  2. Enhanced `AgentRuntime.fit_history_to_context` with dynamic adaptation: when `system_tokens > input_budget`, if total context has at least 256 tokens of output headroom above `system_tokens + safety_tokens`, it dynamically borrows from the oversized output reservation to allow the prompt to fit without failing.
- **Verification:** `tests/unit/test_domain_subagent1_bug_elimination.py` (23/23 PASS) and `tests/unit/test_system_audit_hardening_20261108.py::test_context_budget_dynamic_adaptation_on_small_windows` (PASS).

---

### DEF-AUDIT-02: QThread Teardown Crash on Immediate Task Cancellation (`0xC0000409`)
- **Severity:** P1 (Application Crash / Fatal Exit)
- **Affected File:** `src/gameforge_ide/desktop/services/agent_service.py`
- **Root Cause:** When `AgentService.stop()` or `shutdown()` was called immediately after `send()`, `_worker._runtime` was still `None` (lazy initialization), skipping `runtime.cancel_task()`. Furthermore, `_stream()` was blocked inside `run_until_complete()` before yielding its first event, so the internal `_stop_flag` check was never reached. When `shutdown()` called `self._thread.wait(3000)`, it timed out, leaving `_thread` running when Python garbage-collected the `agent` object. Destroying an active `QThread` triggered C++ `qFatal("QThread: Destroyed while thread is still running")`, terminating the host process with code `0xC0000409`.
- **User-Visible Impact:** Cancelling a task or quickly restarting/closing the application could crash the IDE silently or with a Windows fatal application error.
- **Remediation:**
  1. Added `_loop` and `_task` tracking to `_AgentWorker`. In `_AgentWorker.stop()`, if the event loop is active, invokes `loop.call_soon_threadsafe(task.cancel)` to cancel the running coroutine immediately.
  2. Added early cancellation check in `_stream()` before starting `execute_task_stream()`.
  3. Ensured `_worker.stop()` invokes `_ensure_runtime()` to guarantee `runtime.cancel_task()` is delivered.
  4. In `AgentService.shutdown()`, if `wait(3000)` times out, safely terminates the thread with `self._thread.terminate()` and `wait(1000)` before disposal.
- **Verification:** `tests/unit/test_backend_frontend_integration_e2e.py` (20/20 PASS) and `tests/unit/test_system_audit_hardening_20261108.py::test_agent_service_shutdown_never_destroys_running_qthread` (PASS).

---

### DEF-AUDIT-03: Invalid Bridge Server Documentation URL in Launcher Output
- **Severity:** P3 (Functional / Display Defect)
- **Affected File:** `src/gameforge_ide/launcher.py`
- **Root Cause:** In `launcher.py::main()`, the `--serve` mode startup banner printed `http://{args.host}:{args.port}/docs`. Because `--port` defaults to `None`, the banner printed `http://127.0.0.1:None/docs` instead of resolving the effective port (`args.port or get_settings().bridge_port`).
- **User-Visible Impact:** Users launching the bridge server saw an invalid, unclickable documentation URL.
- **Remediation:** Calculated `effective_port = args.port or get_settings().bridge_port` and passed it to both the console banner and `_launch_server`.
- **Verification:** `tests/unit/test_system_audit_hardening_20261108.py::test_launcher_server_effective_port_resolution` (PASS).

---

### DEF-AUDIT-04: Integration Usability Walk Failing on Play View Guard
- **Severity:** P2 (Integration Test & Scaffolding Mismatch)
- **Affected File:** `tests/integration/test_studio_walk.py`
- **Root Cause:** `test_studio_usability_walk` created a test binary at `Binaries/Win64/MyGame.exe` and an empty GDS `{}`. Under DEF-308 rules, raw development binaries in `Binaries/Win64` are not considered packaged games. Consequently, `MainWindow._current_project_has_package()` evaluated to False, keeping the Play view disabled and causing the view switch to fail.
- **User-Visible Impact:** Integration walk failed to verify Play view controls.
- **Remediation:** Updated test scaffolding to write mock packaged output to `Packaged/Windows/MyGame.exe` and serialized a valid `preset_platformer()` GDS spec.
- **Verification:** `pytest tests/integration/test_studio_walk.py` (PASS in 1.02s).
