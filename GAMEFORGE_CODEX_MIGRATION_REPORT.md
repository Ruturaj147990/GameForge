# GameForge Codex Migration Report

**Updated:** 2026-10-24T18:15:45+05:30  
**Status:** `[VERIFIED]` source migration baseline; 195 unit and 45 protected tests, direct local generation/provider stream, and authenticated UE 5.7.4 editor-originated sync passed. AgentRuntime/desktop stream and packaging remain unverified/blocked.

## Canonical topology

| Concern | Canonical location | Verified state |
|---|---|---|
| Source and tests | `E:\gameforge_step1` | Git root on `master`; pre-existing worktree changes preserved. |
| Large model artifacts | `E:\GameForge` | Protected; not traversed or modified in this pass. |
| Desktop entry point | `src/gameforge_ide/launcher.py` | Native PySide6 is default; `--serve` retains only the Unreal bridge. |
| Agent and tools | `src/gameforge_ide/backend/agent`, `backend/tools` | In-process desktop use through `AgentService` and `ToolService`. |
| Unreal integration | `src/gameforge_ide/unreal/GameForge` | Plugin source retained; UE 5.7 root present at `E:\UE\UE_5.7`. |
| Protected benchmarks | `graders/protected/` | Untouched; 45/45 passed in this pass. |

## Codex hardening completed

- Replaced agent command dispatch based on `shell=True` and a blacklist with argv parsing, shell-syntax rejection, executable allowlist, workspace validation, and a 300-second maximum timeout.
- Marked agent command execution as approval-required and made the runtime stop before any approval-required action other than non-mutating diff proposal.
- Enforced approval policy centrally inside `ToolGateway`, so API and other callers cannot bypass the policy. Human diff controls and the staged-build button call the explicit approved path.
- Added stale-file guards and atomic byte writes for edit approval and rollback. A reviewed patch cannot overwrite later user edits; rollback restores the original bytes only when its own change is still current.
- Removed wildcard CORS and limited `--serve` to `localhost` or loopback IP addresses.
- Preserved the raw composer payload; whitespace-only detection no longer trims the prompt before sending.
- Fixed a runtime prompt-loss defect: after appending a user prompt, reload the persisted session before constructing provider history. Prompt serialization regressions cover boundary spaces, CRLF/LF, indentation, Unicode, and a long payload; Ollama payload explicitly retains `think: false`.
- Replaced the context builder's fixed first-50-lines slice with section-aware selection of canonical identity, non-negotiable constraints, and the active objective/resume state. An explicit character limit now marks truncation instead of silently omitting the current objective.
- Fixed stop/send shared-worker race: cancellation leaves the service busy until worker completion/error, and a session switch ignores late events from the prior task.
- Added a Ctrl+K searchable command palette for implemented session, chat, provider-status, panel-toggle, and About commands; main-window menu actions have stable object names for the interaction registry.
- Added persisted Studio Dark/Light selection (Ctrl+T and View menu), workspace-local settings at `.gameforge/ide_settings.ini`, saved window geometry/dock state, and a Reset Layout action. Existing inline widget styles are palette-converted on theme changes.
- Added context-window preflight using conservative UTF-8 token estimates. The active user prompt remains complete; older history is omitted by recency, and impossible budgets produce an explicit error rather than truncation. The UI reports omitted history and estimated budget. Tool schemas and canonical context were compacted while retaining current state and next action.
- Reconciled the old Step 13 desktop deferral and AC-23 assertion with the later D-029 decision, preserving the current in-progress status and open release gates.
- Built the updated Unreal editor plugin for Win64 against Unreal 5.7.4; it now extracts engine version, selected actor paths, and open asset-editor paths. The latest auth-enabled package loaded in a disposable editor; `GameForge.SyncContext` performed an authenticated editor-originated POST and persisted UE 5.7.4 project context. Actor and open-asset values were empty in the disposable host, and the menu click was not automated. See the Unreal report for package/log hashes.

## Current constraints

- `[VERIFIED]` The Ollama registry returned the canonical `gameforge-27b-sft:latest` (digest `03d36e692be8736b1897f3028f9ba0223ee99822cc864826df825fac2a7a013b`). A direct `/api/chat` smoke with `think: false` returned `GAMEFORGE_OK` in 17.37s total (13.99s load). IDE-mediated streaming/provider UI remains unverified.
- PyInstaller is absent from Python 3.14.6. A standalone executable is therefore `[BLOCKED]` pending authorization to install an approved packager.
- This sandbox intermittently denies the default C: pytest temporary location and hangs minimal `asyncio.run` probes. Workspace-local temporary paths allow non-async test fixtures; those limitations are environment evidence, not product-pass evidence.
- Existing and future `QTextCharFormat` colors in diff/terminal output and new chat bubbles now use or convert to the active palette. Real Windows DPI and minimum-size visual checks remain unverified.

## Acceptance-gate snapshot

| Gates | Status | Evidence / exact limitation |
|---|---|---|
| G1–G2 | PASS | Canonical roots and native PySide6 entry point verified. |
| G3–G5 | PARTIAL | Dark/Light toggle, inline/rich-text recoloring, preference restoration, dock reset/restore, prompt fidelity, whole-prompt context budget, and older-history omission are covered by focused tests. Mocked async HTTP streaming hangs under this Python 3.14 environment; attachments, RTL/path matrix, tokenizer accuracy, Windows DPI/minimum-size visuals and a complete interaction registry remain unverified. |
| G6 | PARTIAL | Canonical local model registry and one direct bounded generation were verified; IDE-mediated streaming, cancellation, and repeated latency behavior remain unverified. |
| G7–G8 | PARTIAL | Typed gateway and bounded runtime exist; no fresh live structured-tool roundtrip was possible. |
| G9 | PASS | Human diff review plus atomic, stale-safe apply/rollback covered by 32 core/desktop tests. |
| G10–G11 | PARTIAL | JSON sessions and lazy explorer exist; theme preference and hidden dock state restore on window recreation, geometry/dock state are persisted, while session restart recovery and large-project retrieval are not fully verified. |
| G12–G14 | PARTIAL | UE 5.7.4 Win64 package build, disposable editor load, and authenticated `GameForge.SyncContext` context transfer passed. Menu click and populated actor/asset payload, staged IDE build UI, and Unreal import remain unverified. |
| G15 | PARTIAL | Command, approval, prompt, loopback and bearer-token auth controls are covered; same-user secret exposure, timeout/token lifecycle, egress and OS isolation remain incomplete. |
| G16 | PARTIAL | Stop/send race and late session-switch events are covered; provider timeout, worker crash, and full cancellation-recovery matrix remain incomplete. |
| G17 | NOT VERIFIED | No fresh startup, TTFT, memory, CPU, or VRAM measurements. |
| G18 | PASS | Prior cleanup is recorded and protected/model data remains intact. |
| G19 | PASS | Full unit suite: 195 passed in 17.82s; protected suite: 45 passed in 0.06s. API tests pass with local socket access. Two upstream deprecation warnings remain. |
| G20 | BLOCKED | PyInstaller is not installed; installation needs authorization. |
| G21 | PARTIAL | OpenAI-compatible adapter has a deterministic test double only. |
| G22 | DESIGN ONLY | Hosted inference topology, security boundaries, test contract, and deployment unknowns are documented in `GAMEFORGE_HOSTED_INFERENCE_ARCHITECTURE.md`; no service package or endpoint exists. |
| G23 | BLOCKED_PENDING_INFRA_AUTHORIZATION | No public hosting was provisioned. |
| G24 | PASS | Context mirrored, execution log and decisions updated. |
| G25–G26 | PARTIAL | Provenance records are preserved and recovery is documented; full licence/supply-chain and package-recovery audits were not run. |

Setting process `TEMP` and `TMP` to workspace-local storage resolved C: fixture failures. The initial API hang was caused by restricted local socket access: with socket permission enabled, the original `TestClient` API module passed **8 tests**, and the full **195-test** unit suite passed in 17.82s. A selector-loop workaround attempt was discarded and the original test fixture retained. A temporary real loopback Uvicorn server also accepted health/context requests and persisted/read back metadata.
