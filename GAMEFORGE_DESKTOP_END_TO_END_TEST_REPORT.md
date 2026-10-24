# GAMEFORGE IDE — END-TO-END WORKFLOW AUDIT REPORT

**Date:** 2026-10-24  
**Audit Target:** Native PySide6 Desktop Application (`MainWindow`)  
**Inference Engine:** Ollama (`http://127.0.0.1:11434`)  
**Active Production Model:** `gameforge-27b-sft:latest` (Ollama digest `03d36e692be8`)  
**Engine Toolchain:** Unreal Engine 5.7.4 (`E:\UE\UE_5.7`)  
**Gateway Security:** `ToolGateway` with Typed Parameter Schemas & Strict Workspace Boundary  

> **Historical snapshot:** These end-to-end claims predate the 17:22 current checkpoint and were not rerun in this pass. Current live Ollama is unavailable; current API endpoint tests are environment-blocked; Unreal package compilation passed but editor/bridge runtime remains unverified. See `GAMEFORGE_TEST_REPORT.md` and `GAMEFORGE_UNREAL_INTEGRATION_REPORT.md`.

---

## 1. End-to-End Workflow Architecture

```
[PySide6 MainWindow]
     │
     ├──> [ChatPanel] ──(Qt Signals)──> [AgentService (QThread)]
     │                                        │
     │                                        ├──> [OllamaProvider] ──> gameforge-27b-sft:latest
     │                                        │
     │                                        └──> [AgentRuntime]
     │                                                 │
     │                                                 └──> [ToolGateway]
     │                                                          │
     │                                                          ├──> [EditTools] (diff/apply/rollback)
     │                                                          ├──> [UnrealTools] (UE 5.7 detection/build)
     │                                                          └──> [FileTools] (read/search/tree)
     │
     ├──> [DiffPanel] ──(Sync Tool Calls)──> [ToolService] ──> [ToolGateway]
     │
     └──> [TerminalPanel] ──(Qt QProcess)──> powershell.exe (Bounded to E:\gameforge_step1)
```

There are zero localhost HTTP dependencies or WebSockets involved in normal UI operations. Everything runs in-process with typed Qt signals bridging background worker threads to GUI widgets.

---

## 2. Test Workflow 1: Live Model Inference & Token Streaming

### Procedure
1. Created new agent session via `AgentService.create_session("Default Session", "gameforge-27b-sft:latest", "ollama")`.
2. Initialized `MainWindow` and `ChatPanel`.
3. Verified Ollama availability: returned `True` (Ollama online on `127.0.0.1:11434`).
4. Entered prompt: `"In Unreal Engine 5.7 C++, what method enables an actor component to tick every frame?"`
5. Dispatched task via `ChatPanel._on_send()`.

### Observed Results
- **Initial Status:** Dispatched signal `status_changed("PLANNING")` then `status_changed("THINKING")`.
- **Streaming Tokens:** Received 18 tokens incrementally via `token_received(token: str)`.
- **Active Bubble:** Tokens accumulated live in `_MessageBubble`, auto-sizing without clipping.
- **Completion:** `task_done` signal emitted after 20.13 seconds.
- **Artifact Captured:** `reports/screenshot_live_streaming.png`.
- **Verdict:** `[VERIFIED]` — Live 27B model inference operates seamlessly through in-process Qt signals.

---

## 3. Test Workflow 2: Controlled File Editing, Diff Approval & Rollback

### Procedure
1. Created disposable test file on disk:
   `E:\gameforge_step1\scratch\disposable_health_component.cpp`
   Initial content:
   ```cpp
   // Initial version
   void UHealthComponent::BeginPlay() {
       Super::BeginPlay();
       CurrentHealth = 50.0f;
   }
   ```
   Initial SHA-256: `98db67d6928e08cf4fb44d715a6b0c2a5e9ad28da4e941cb1fc6be4cfcbfd690`

2. **Step A — Propose Edit:**
   Called `propose_edit` via `ToolService`:
   - `subpath`: `scratch/disposable_health_component.cpp`
   - `target_content`: `CurrentHealth = 50.0f;`
   - `replacement_content`: `CurrentHealth = MaxHealth; // Fully healed on spawn`
   - **Result:** Status `PENDING_APPROVAL`, generated diff ID `ae319a91-bfd3-4524-af54-f1205f1bdeda`.
   - **File Verification:** Checked disk before approval; file was **completely unmodified** (`CurrentHealth = 50.0f;`).

3. **Step B — Diff Review Panel Display:**
   - Displayed diff in `DiffPanel`.
   - Syntax-highlighted unified diff rendered in `DiffView`: additions in green, deletions in red.
   - Captured evidence: `reports/screenshot_diff_review.png`.

4. **Step C — Approve Edit:**
   - Clicked `[Approve & Apply]`, invoking `apply_edit(diff_id="ae319a91-bfd3-4524-af54-f1205f1bdeda")`.
   - **Result:** Status `SUCCESS`.
   - **File Verification:** Read disk content; verified file contains `"CurrentHealth = MaxHealth; // Fully healed on spawn"`.
   - New SHA-256: `f1ac579ecceab6a15debfdb4a4e107be678f24458d7c040d6c52a0a256a5b29f`.

5. **Step D — Rollback Edit:**
   - Clicked `[↩ Rollback Applied]`, invoking `rollback_edit(diff_id="ae319a91-bfd3-4524-af54-f1205f1bdeda")`.
   - **Result:** Status `SUCCESS`.
   - **File Verification:** Read disk content; original pre-edit content restored (`CurrentHealth = 50.0f;`).
   - Restored SHA-256: `98db67d6928e08cf4fb44d715a6b0c2a5e9ad28da4e941cb1fc6be4cfcbfd690` (**Exact match to pre-edit hash**).

6. **Step E — Reject Edit:**
   - Proposed second edit to set `CurrentHealth = 0.0f;`.
   - Clicked `[❌ Reject]`, invoking `reject_edit(diff_id=...)`.
   - **Result:** Status `REJECTED`.
   - **File Verification:** Read disk content; file remained untouched (`CurrentHealth = 50.0f;`).

- **Verdict:** `[VERIFIED]` — Full gatekeeping lifecycle (propose → inspect → apply → rollback → reject) is 100% operational against real files.

---

## 4. Test Workflow 3: Unreal Engine 5.7 Detection & UAT Verification

### Procedure
1. Initialized `UnrealPanel` with workspace `E:\gameforge_step1`.
2. Executed `unreal_engine_info` and `unreal_find_projects` tools.

### Observed Results
- **Installed:** `True`
- **Version:** `5.7.4`
- **Install Path:** `E:\UE\UE_5.7`
- **UAT Available:** `True` (`E:\UE\UE_5.7\Engine\Build\BatchFiles\RunUAT.bat`)
- **Projects Found:** 5 canonical test fixtures (cleanly filtered and deduplicated):
  - `GameForgePilot [fixtures/unreal/t2_001_controller]`
  - `GameForgePilot [fixtures/unreal/t2_004_health]`
  - `GameForgePilot [fixtures/unreal/t2_004_health_damage]`
  - `GameForgePilot [fixtures/unreal/t2_005_pickup]`
  - `GameForgePilot [fixtures/unreal/t2_005_pickup_collection]`
- **Build Button:** Enabled with staged build safeguards.
- **Verdict:** `[VERIFIED]` — Engine and toolchain detected with accurate paths and verified UAT script.

---

## 5. Test Workflow 4: Embedded Terminal (PowerShell) Execution

### Procedure
1. Verified `TerminalPanel` initializes `QProcess` with `powershell.exe -NoLogo -NonInteractive`.
2. Verified working directory is `E:\gameforge_step1`.
3. Executed command `Get-Location` and checked standard output.
4. Toggled terminal visibility using the new top toolbar action button `_act_tb_terminal`.

### Observed Results
- Terminal started cleanly without UI lockup.
- Working directory accurately reported `E:\gameforge_step1`.
- Standard output and standard error stream into `_output` in Cascadia Code monospace.
- "Clear" button resets output; "↺" button restarts process cleanly.
- Terminal collapses and expands instantly without disturbing adjacent panels.
- **Verdict:** `[VERIFIED]` — Fully functional embedded shell.
