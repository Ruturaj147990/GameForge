# GameForge — Canonical Project Context & Memory

**Last Updated:** 2026-10-24T18:29:58+05:30
**Current Milestone:** Native GameForge IDE MVP implementation and local verification advanced. Authenticated UE 5.7.4 editor-to-backend context sync works; all 195 unit tests and 45 protected tests pass. Cleanup on 2026-10-24 removed 3,313,603,708 bytes of obsolete build outputs, disposable probes, test scratch and bytecode caches. All model weights/datasets were preserved. At the user request, Ollama app/daemon, bridge, test jobs and disposable Unreal probes are stopped.
**Primary Repository Root:** `E:\gameforge_step1`  
**Storage & Large-Artifact Root:** `E:\GameForge`  
**Active Production Model:** `gameforge-27b-sft:latest` (Ollama ID: `03d36e692be8`, GGUF SHA-256: `d73eb684...`)  
**Context Protocol:** Mandatory reading & updating on every session ([AGENTS.md](file:///e:/gameforge_step1/AGENTS.md))  

---

## A. Project Identity & Mission

GameForge is an autonomous, open-weights, multi-engine game development artificial intelligence.
- **Intended Capabilities:** Expert-level code generation, refactoring, and debugging across Unreal Engine 5.7 (GAS, Networking, Subsystems, TObjectPtr), Unity 6 (DOTS Entities 1.3, Baker Authoring, C# Gameplay), Godot 4.3 (GDScript, CharacterBody3D, Typed Signals), and universal Game Mathematics.
- **Multimodal Perception:** Direct screenshot-based visual debugging of compiler error logs, editor crashes, shader artifacts, and scene hierarchies.
- **Primary Deliverable:** Local, reproducible GGUF models running via Ollama/llama-server with hybrid GPU/CPU offload on consumer AMD hardware, backed by a deterministic evaluation benchmark and version-aware engine knowledge registry.

---

## B. Non-Negotiable Constraints

1. **Hardware & OS:** Windows 11 Pro, AMD Ryzen 5 7600X (6C/12T, 32GB DDR5), AMD Radeon RX 7700 XT (12GB GDDR6 VRAM). `[VERIFIED]`
2. **Storage Boundaries:** 100% of large models, datasets, caches, training checkpoints, and GGUFs must remain on the `E:` drive (`E:\GameForge`). No 10+ GB artifacts on the OS `C:` drive. `[VERIFIED]`
3. **Computer Safety Rule:** **NEVER shut down, restart, sleep, or hibernate the system. Never invoke `shutdown.exe`.** `[VERIFIED]`
4. **Local Execution Only:** Zero paid cloud APIs, zero external model downloading during tasks, zero simulated/fake training updates. `[VERIFIED]`
5. **Rollback & Provenance Safeguards:** Never overwrite working models or Modelfiles without preserving rollback configurations. Distinguish weight training from prompt/configuration improvements. `[VERIFIED]`
6. **Inference Directives:** When querying Ollama API programmatically, set `"think": False` for direct code generation to prevent hidden reasoning token exhaustion. `[VERIFIED]`

---

## C. Current System Architecture

```
E:\gameforge_step1\ (Canonical Git Repo)
├── configs/
│   ├── engine_knowledge_registry.json   <- v2.1.0: Version-aware API invariants (UE 5.7, Unity 6, Godot 4.3)
│   ├── Modelfile.gameforge-27b-sft-v2   <- Rollback Modelfile (v2.0)
│   └── Modelfile.gameforge-27b-sft-v2.1 <- Canonical production Modelfile (v2.1)
├── src/gameforge_bench/
│   ├── cli.py / gameforge_cli.py        <- CLI routing & interactive chat defaults (points to gameforge-27b-sft)
│   ├── grading.py                       <- 9-layer benchmark grading engine
│   └── knowledge_retrieval.py           <- In-memory engine knowledge retrieval
├── scripts/
│   ├── run_phase2_broader_eval.py       <- 16-task deterministic broader benchmark harness
│   └── run_phase2_targeted_and_holdout_test.py <- 7-task comparative retest and holdout validator
├── tests/unit/
│   └── test_evaluation_harness.py       <- Unit tests for evaluation arithmetic, syntax, and rubric normalization
└── reports/gameforge-27b-sft/           <- Detailed release reports, manifests, execution logs, and raw outputs

E:\GameForge\ (Large-Artifact Storage Root)
├── artifacts/gameforge-27b-sft/         <- Standalone Q4_K_M GGUF (16.8 GB)
├── models/ollama/                       <- Ollama storage ($env:OLLAMA_MODELS): blobs, manifests-v2
├── ollama_bin/ollama.exe                <- Canonical Ollama binary v0.40.6 (Vulkan backend)
├── training/gameforge-27b-sft/          <- SFT LoRA adapter safetensors (2.78M params)
└── datasets/gameforge-27b-sft/          <- Original 518-sample multi-engine SFT dataset
```

---

## D. Model Inventory & Deployment State

| Tag | Ollama ID | Format | Size | SHA-256 / Digest | Status | Evidence State |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`gameforge-27b-sft:latest`** | `03d36e692be8` | Q4_K_M GGUF | 16.8 GB | `d73eb68413c0226e1a4a24c81a987d611b7b7375af8594fbebfa7aec4b912f2b` | **PRODUCTION CANONICAL (v2.1)** | `VERIFIED` |
| `qwen3.8:27b-q4_K_M` | `25b843619e94` | Q4_K_M GGUF | 16.8 GB | Foundation base model | Preserved for baseline delta checks | `VERIFIED` |
| `gameforge-27b:latest` | `7bc56a87ebcc` | Q4_K_M GGUF | 16.8 GB | Pre-SFT candidate | Preserved for regression audits | `VERIFIED` |
| `gameforge-v2:latest` | `9f6fae7cd1ff` | Q4_K_M GGUF | 1.9 GB | Compact 3B specialist | Preserved | `VERIFIED` |
| `gameforge-v1:latest` | — | GGUF | — | Obsolete prompt-wrapper baseline | **RETIRED & REMOVED** | `VERIFIED` |

- **Vision Projector:** Attached blob `sha256:ac3714bfdddeca31351f2752bf1a63f266f4df87c0b68c895e44945ca704448e` (931 MB). Verified functional in Ollama. `[VERIFIED]`
- **Inference Runtime:** Last verified on 2026-10-24 with 37 GPU offloaded layers and 28 CPU/DDR5 layers (~4.7 tokens/sec). `[SUPERSEDED CURRENT STATE]` Ollama app and daemon were stopped at user request on 2026-10-24; model files remain intact.

---

## E. Latest Verified Metrics (Phase 2 Results)

1. **Broader 16-Task Multi-Engine Benchmark:** `[VERIFIED]` (2026-10-24)
   - Score: **153 / 160 points (95.62%)**
   - Perfect 10/10 Tasks: **13 / 16 (81.25%)**
   - UE 5.7 Tick Avoidance (`PH2-04`): **10 / 10** (Resolved prior 0/10 failure caused by conversational preamble).
   - Visual Debugging (`PH2-16`): **10 / 10** (OCR + include diagnosis in 429 tokens).
   - Source: [`reports/gameforge-27b-sft/phase2_evaluation_results.csv`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_evaluation_results.csv)
2. **Comparative Targeted Retest & Holdout Suite:** `[VERIFIED]` (2026-10-24)
   - Targeted Retest (3 tasks): **30 / 30 (100.0%)** (Candidate v2.1 reduced token usage on `PH2-02` from 512 [TRUNC] to 272 [COMPLETE]).
   - Unseen Holdout Suite (4 tasks): **40 / 40 (100.0%)** (Zero regressions across UE LineTrace, Unity Audio event, Godot Lerp, Math Euler-Quat).
   - Source: [`reports/gameforge-27b-sft/phase2_holdout_results.csv`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_holdout_results.csv)
3. **Full Project Unit Tests:** `[VERIFIED]` (2026-10-24)
   - Command: `pytest tests/unit/` $\to$ **141 passed in 18.44 seconds (100% pass rate)**.
4. **Historical Discrepancy Note:** `[SUPERSEDED]`
   - Prior report stated *"3 tasks improved"* on the short 8-task test. Audit of `before_after_results.csv` confirmed **4 tasks improved** (+9, +1, +10, +10), with `TASK-03` (+1) overlooked in the earlier summary.

---

## F. Completed Work & Key Engineering Decisions

- **DirectML Parameter-Efficient SFT:** Trained 940 optimizer steps across 470 verified multi-engine samples on RX 7700 XT. Converged cross-entropy loss: 8.5610 $\to$ 4.0715 (val: 3.5461). Learned adapters permanently merged into Q4_K_M weights. `[VERIFIED]`
- **Anti-Scaffolding Directives (v2.1):** Solved token budget exhaustion by instructing the model to focus on requested method bodies rather than emitting redundant dual `.h`/`.cpp` files with duplicate `#include` headers. `[VERIFIED]`
- **Multimodal Projector Restoration:** Re-attached vision projector blob into Modelfile, restoring OCR screenshot error diagnosis. `[VERIFIED]`
- **Retirement of V1:** Removed obsolete prompt-wrapper `gameforge-v1:latest` from registry. `[VERIFIED]`

---

## G. Current State & Active Objective

- **Current State:** `[VERIFIED]` Agent safety, prompt-loss, stop/send race, context-window budgeting, and Unreal metadata pipeline are implemented. The runtime reloads persisted session state, pins the full active prompt, estimates context use from UTF-8 bytes, omits older whole messages when needed, and reports omissions; oversized prompts fail explicitly without truncation. Compact system prompt estimate is 2,281 tokens against 2,944 estimated input tokens (heuristic only). Latest full suite: **195 unit tests passed in 17.82s**; protected suite **45 passed in 0.06s**. Two upstream Starlette/AnyIO deprecation warnings remain. API tests pass with local socket access. Tests use unique generated assets and clean generated sessions/context; the actual disposable editor probe JSON was removed after capturing its evidence. API tests cover unset/wrong/valid bridge bearer tokens. Latest UE 5.7.4 Win64 package with authentication and `GameForge.SyncContext` built successfully (56.57s, exit 0; 12 files, 59,401,787 bytes; DLL SHA-256 `176FCE31F17DE0269B1B77B5F0DC97FEBE8EC3AD3D8D02D0B351BFDFA4778C06`). A disposable UE 5.7.4 editor invoked the console command against the bearer-protected local backend; its log records SUCCESS and the persisted project/version metadata. The menu and console command share the same sync function; menu click was not automated, and selected actor/open-asset values were empty in this probe. Plugin source gathers selected actor paths, engine version, and open asset-editor paths; backend bounds, atomically persists, and labels metadata untrusted. Direct canonical Ollama generation returned `GAMEFORGE_OK` with `think:false`; provider stream returned `IDE_STREAM_OK`; native desktop UI displayed `NATIVE_UI_OK`. These do not verify AgentRuntime/desktop UI streaming. PyInstaller is absent and installation was not authorized. Hosted inference remains design-only. Remaining: UI-mediated agent stream, populated editor metadata/menu interaction, DPI/minimum-size and repeatable performance checks, bridge request timeout/token rotation and same-user process-secret exposure, and standalone packaging.

- **Native Desktop Architecture:** `[VERIFIED]`
  - `src/gameforge_ide/desktop/main_window.py` — `QMainWindow` with dockable panels, menu bar, tool bar, status bar.
  - `src/gameforge_ide/desktop/panels/chat_panel.py` — streaming chat with auto-sizing markdown bubbles, model selector, send/stop.
  - `src/gameforge_ide/desktop/panels/explorer_panel.py` — lazy `QTreeWidget` workspace tree with search.
  - `src/gameforge_ide/desktop/panels/diff_panel.py` — syntax-coloured diff review with approve/reject/rollback.
  - `src/gameforge_ide/desktop/panels/unreal_panel.py` — UE5 engine info, uproject list, staged build trigger.
  - `src/gameforge_ide/desktop/panels/terminal_panel.py` — embedded `QProcess` PowerShell terminal with toolbar toggle.
  - `src/gameforge_ide/desktop/services/agent_service.py` — `QThread` async bridge with `@Slot()` run, `_trigger_run` Signal, and safe generator cleanup.
  - `src/gameforge_ide/desktop/services/tool_service.py` — `QThreadPool` wrapper for `ToolGateway`.
  - `src/gameforge_ide/desktop/styles/dark_theme.py` — premium studio dark stylesheet (high-contrast indigo/teal palette).
  - `src/gameforge_ide/launcher.py` — **native desktop is the default**; `--serve` for minimal loopback Unreal plugin bridge.
  - `release/GameForge.bat` — portable desktop launch batch file.
- **Next Concrete Action:** Exercise `AgentRuntime.execute_task_stream()` through the native desktop UI with the canonical local model and verify completion/cancellation events. Then populate a disposable UE project with a selected actor/open asset and verify those actual values through the menu/console bridge path. Complete Windows DPI/minimum-size and repeatable resource/performance checks. Keep the bridge loopback-only; add bounded HTTP timeout and token lifecycle controls. Standalone packaging remains blocked because no packager is installed and installation was not authorized; continue only through an available approved packaging path.

---

## H. Test & Execution Reference

```powershell
# 1. Start Ollama Server with Canonical Storage (if stopped)
$env:OLLAMA_MODELS = "E:\GameForge\models\ollama"; & "E:\GameForge\ollama_bin\ollama.exe" serve

# 2. Launch native GameForge IDE desktop (PySide6; default mode)
python -m src.gameforge_ide.launcher

# 3. Run Full Automated Unit Test Suite (195 discovered; run with local socket access if sandbox networking blocks TestClient)
pytest tests/unit/

# 4. Run Protected Benchmark Test Oracles (45 tests)
pytest graders/protected/

# 5. Run Broader 16-Task Deterministic Evaluation
python scripts/run_phase2_broader_eval.py gameforge-27b-sft:latest

# 6. Run Targeted Retest and Holdout Validation
python scripts/run_phase2_targeted_and_holdout_test.py
```

---

## I. Known Problems & Lessons Learned

1. **Hidden Reasoning Token Exhaustion:** When querying Ollama API, omitting `"think": False` causes models with reasoning capability (Qwen3.8 architecture) to burn generation tokens inside `<think>` tags, leaving the response empty. Always specify `"think": False` for direct code generation.
2. **Dual Translation Unit Bloat:** When asked for Unreal C++ classes, models tend to output both full `.h` and `.cpp` with 10 includes each, burning >400 tokens on boilerplate. Prompts must steer models to focus on requested method implementations.
3. **Ollama Windows Process Binding:** Running `ollama list` without setting `$env:OLLAMA_MODELS` defaults to `C:\Users\limbk\.ollama`. Always set `$env:OLLAMA_MODELS = "E:\GameForge\models\ollama"`.

---

## J. Important Artifacts & Source of Truth

- **Canonical Context:** [`context.md`](file:///e:/gameforge_step1/context.md) (This file)
- **Desktop Acceptance Report:** [`GAMEFORGE_DESKTOP_ACCEPTANCE_REPORT.md`](file:///e:/gameforge_step1/GAMEFORGE_DESKTOP_ACCEPTANCE_REPORT.md) (Milestone K acceptance & workflow proof)
- **Release Gate Report:** [`GAMEFORGE_IDE_RELEASE_GATE_REPORT.md`](file:///e:/gameforge_step1/GAMEFORGE_IDE_RELEASE_GATE_REPORT.md) (Full 7-gate release audit)
- **Localhost Cleanup Manifest:** [`GAMEFORGE_LOCALHOST_CLEANUP_MANIFEST.md`](file:///e:/gameforge_step1/GAMEFORGE_LOCALHOST_CLEANUP_MANIFEST.md) (41.6 KB web UI purged)
- **Localhost Cleanup Results:** [`GAMEFORGE_LOCALHOST_CLEANUP_RESULTS.csv`](file:///e:/gameforge_step1/GAMEFORGE_LOCALHOST_CLEANUP_RESULTS.csv) (Audit classification of all web assets)
- **GameForge IDE Test Report:** [`GAMEFORGE_IDE_TEST_REPORT.md`](file:///e:/gameforge_step1/GAMEFORGE_IDE_TEST_REPORT.md) (213 passing tests)
- **GameForge IDE Final Report:** [`GAMEFORGE_IDE_FINAL_REPORT.md`](file:///e:/gameforge_step1/GAMEFORGE_IDE_FINAL_REPORT.md) (Product release report)
- **GameForge IDE Implementation Plan:** [`GAMEFORGE_IDE_IMPLEMENTATION_PLAN.md`](file:///e:/gameforge_step1/GAMEFORGE_IDE_IMPLEMENTATION_PLAN.md) (Milestones A–I sequence)
- **GameForge IDE Execution Log:** [`GAMEFORGE_IDE_EXECUTION_LOG.md`](file:///e:/gameforge_step1/GAMEFORGE_IDE_EXECUTION_LOG.md) (Step-by-step implementation log)
- **GameForge IDE Architecture:** [`GAMEFORGE_IDE_ARCHITECTURE.md`](file:///e:/gameforge_step1/GAMEFORGE_IDE_ARCHITECTURE.md) (System architecture specification)
- **GameForge Cleanup Manifest:** [`GAMEFORGE_CLEANUP_MANIFEST.md`](file:///e:/gameforge_step1/GAMEFORGE_CLEANUP_MANIFEST.md) (23.89 GB reclaimed)
- **GameForge Cleanup Results:** [`GAMEFORGE_CLEANUP_RESULTS.csv`](file:///e:/gameforge_step1/GAMEFORGE_CLEANUP_RESULTS.csv) (Machine-readable cleanup actions)
- **Master Blueprint Audit:** [`reports/master_blueprint_implementation_audit.md`](file:///e:/gameforge_step1/reports/master_blueprint_implementation_audit.md) (Complete 60-requirement audit vs Master Strategy)
- **Authoritative Master Strategy:** [`GAMEFORGE_FINAL_MASTER_STRATEGY.md`](file:///e:/gameforge_step1/GAMEFORGE_FINAL_MASTER_STRATEGY.md) (v3.1.0 SSOT and sequential execution controller)
- **Phase 2 Release Report:** [`reports/gameforge-27b-sft/phase2_final_report.md`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_final_report.md)
- **Phase 2 Release Manifest:** [`reports/gameforge-27b-sft/phase2_final_manifest.json`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_final_manifest.json)
- **Production Modelfile:** [`configs/Modelfile.gameforge-27b-sft-v2.1`](file:///e:/gameforge_step1/configs/Modelfile.gameforge-27b-sft-v2.1)
- **Engine Knowledge Registry:** [`configs/engine_knowledge_registry.json`](file:///e:/gameforge_step1/configs/engine_knowledge_registry.json)

---

## K. Resume Instructions for Antigravity Sessions

1. **Read `context.md`:** Review current state, production tags, and active constraints before taking any action.
2. **Check Daemon Status:** Run `netstat -ano | findstr :11434` or query `http://127.0.0.1:11434/api/tags` to ensure Ollama is responsive.
3. **Verify Git & Artifacts:** Confirm `git status` and verify referenced paths on `E:` drive.
4. **Execute Bounded Steps:** Resume directly from the documented active objective; do not repeat completed milestones.
5. **Preserve Rules:** Never invoke `shutdown.exe`, never write large artifacts to `C:`, never modify model weights without authorization.
6. **Update `context.md`:** Update this file at major milestones and before concluding every session.

---

## L. Recent Context Changes

- **2026-10-24T18:29:** [VERIFIED] User-requested cleanup removed 3,313,603,708 bytes (~3.09 GiB): superseded plugin build trees, disposable UE probe projects/logs, scratch test/eval outputs and Python bytecode/test caches. Preserved all canonical/current/baseline model artifacts, datasets, training records, source, reports, protected graders, latest plugin package (E:\GameForge\validation\gameforge_plugin_auth_console_20261024) and authenticated editor log. Stopped Ollama app/daemon, GameForge bridge, dangling pytest processes and disposable Unreal command-line editors; ports 8000 and 11434 were no longer listening after shutdown. Context mirrored to E:\GameForge\context.md.\n- **2026-10-24T18:15:** `[VERIFIED]` Latest full unit suite passed **195/195 in 17.82s**; protected suite **45/45 in 0.06s**. Auth API cases pass with local socket access. Built UE 5.7.4 Win64 plugin with bearer auth and `GameForge.SyncContext` (56.57s, exit 0; DLL SHA-256 `176FCE31F17DE0269B1B77B5F0DC97FEBE8EC3AD3D8D02D0B351BFDFA4778C06`). Ran the command in a disposable editor against the authenticated local backend; UE log recorded SUCCESS and project `HostProject`/engine `5.7.4` persisted. Probe file removed afterward. Menu click not automated; empty actor/assets because the disposable host has no content. Direct Ollama generation, real provider stream, and native UI reply remain verified. Auth residual: same-user environment visibility, no timeout/token rotation. Remaining: AgentRuntime/desktop UI stream, populated UE actor/asset context, manual menu check, DPI/performance, packaging unavailable/no install authorization. Exact final test command: `python -m pytest tests/unit/ -q --basetemp .pytest_codex_full_bridge_auth_20261024` (with `TEMP`/`TMP` redirected to the workspace and local socket permission) — 195 passed, 17.82s, 2 upstream deprecation warnings; protected command `python -m pytest graders/protected/ -q --basetemp .pytest_codex_protected_bridge_auth_final_20261024` — 45 passed, 0.06s. Changed implementation paths in this closeout: `src/gameforge_ide/backend/app.py`, `src/gameforge_ide/launcher.py`, `src/gameforge_ide/unreal/GameForge/Source/GameForgeEditor/Private/GameForgeBridgeClient.cpp`, `src/gameforge_ide/unreal/GameForge/Source/GameForgeEditor/Private/GameForgeEditorModule.cpp`, corresponding public headers, and `tests/unit/test_ide_api.py`; current reports, `DECISION_LOG.csv`, `GAMEFORGE_ROADMAP.csv`, and this context were reconciled. See latest Unreal, security, test, release, strategy, execution and defect reports.
- **2026-10-24T17:50:** All 194 unit tests passed in 16.55s and 45 protected tests passed in 0.03s. Initial API TestClient hangs were due to sandbox socket restrictions; API module passes 8/8 with local socket access, and the original TestClient fixture was retained. `OllamaProvider.stream_chat()` returned `IDE_STREAM_OK` from `gameforge-27b-sft:latest`; direct API smoke also passed. Tests now create unique generated asset names and clean their session/context/mesh artifacts. Packager inventory found no PyInstaller/Nuitka/cx_Freeze. Outstanding: menu-triggered Unreal sync, AgentRuntime/desktop streaming, bridge authentication, UI/performance checks, and packaging authorization/tool availability. Updated test, security, migration, performance, release, strategy, roadmap and execution reports.

- **2026-10-24T17:37:** Direct local Ollama smoke passed. `/api/tags` returned `gameforge-27b-sft:latest` digest `03d36e692be8736b1897f3028f9ba0223ee99822cc864826df825fac2a7a013b`; `/api/chat` with `think: false`, `num_predict: 16` returned exactly `GAMEFORGE_OK`, `done=true`, prompt/eval counts 625/5, total duration 17.3689968s including model load 13.9904232s. This is a single direct API check, not IDE streaming or a performance benchmark. Updated test/performance/final/release/strategy/migration reports. Next: invoke the Unreal menu action live and verify IDE-mediated model streaming.

- **2026-10-24T17:32:** Updated context pipeline closed out: latest UE 5.7.4 Win64 plugin package compiled in 36.04s (10 files; DLL SHA-256 `C08457FE672B12A390C729835476632DC86751317D9007F3986A0D50F7C58AFB`; BuildPlugin log SHA-256 `C1FE3879FB16F9E65BBC83D389821BC691398F49574BF184365D43139F0489C1`). Disposable UnrealEditor-Cmd mounted plugin and logged startup/quit; actual loopback Uvicorn GET health, POST context, GET context all returned 200 and persisted/read back fields. Plugin menu action itself was not invoked. Fixed CP1252-incompatible Unicode launcher banner. Broad command `python -m pytest tests/unit/ --ignore=tests/unit/test_ide_api.py -q --basetemp .pytest_codex_unreal_context_final_20261024` with `TEMP`/`TMP` workspace-local: **186 passed in 17.53s**; `python -m pytest graders/protected/ -q --basetemp .pytest_codex_protected_close_20261024`: **45 passed**; collection **194**. One isolated host-policy test passed separately; 7 API endpoints remain blocked by TestClient/AnyIO startup. Changed source: `src/gameforge_ide/launcher.py`, `src/gameforge_ide/backend/unreal_context.py`, `src/gameforge_ide/backend/app.py`, `src/gameforge_ide/backend/agent/context_manager.py`, `src/gameforge_ide/unreal/GameForge/Source/GameForgeEditor/Private/GameForgeBridgeClient.cpp`, `src/gameforge_ide/unreal/GameForge/Source/GameForgeEditor/Public/GameForgeBridgeClient.h`, `tests/unit/test_gameforge_ide.py`; current reports/roadmap/strategy/execution/defect ledger updated. Temporary pytest directories and the generated `.gameforge/unreal_context.json` probe were removed. Next: live menu-originated plugin request, API test environment compatibility, DPI/performance and packaging gates. Mirrored context and verified matching file hash.

- **2026-10-24T17:27:** Unreal editor metadata pipeline implemented: plugin reads actual selected actor paths, engine version, and open asset-editor paths (uses active_asset only when exactly one asset editor is open). Bridge request now carries open_assets. Backend validates bounded fields, atomically stores `.gameforge/unreal_context.json` inside workspace, and the agent system prompt includes it under an explicit untrusted-metadata label. Focused core/desktop tests: **45 passed in 3.66s**. Plugin compile pending after C++ change; runtime bridge/editor interaction remains unverified.

- **2026-10-24T17:22:** Unreal plugin package compile **PASS** for UE 5.7.4 Win64 using engine AutomationTool DLL directly (48.0s, exit 0). UHT processed generated host project; UBT compiled and linked `GameForgeEditorModule.cpp` and `GameForgeBridgeClient.cpp` with VS2022 14.44.35228/Windows SDK 10.0.22621.0. Output: `E:\GameForge\validation\gameforge_plugin_probe_20261024` (59,100,866 bytes); DLL SHA-256 `fc47fe6bece47efeafe212a47fda2ca3cb6f66707daac10d6945743c7730117b`. `RunUAT.bat` wrapper failed in restricted shell before starting; direct AutomationTool succeeded after approved sandbox escalation. Editor load and bridge handshake remain unverified. Changed code/docs/tests: `src/gameforge_ide/backend/agent/runtime.py`, `src/gameforge_ide/backend/agent/context_manager.py`, `src/gameforge_ide/desktop/panels/chat_panel.py`, `tests/unit/test_gameforge_ide.py`, `tests/unit/test_acceptance_criteria.py`, `GAMEFORGE_FINAL_MASTER_STRATEGY.md`, `GAMEFORGE_ROADMAP.csv`, `DECISION_LOG.csv`, `GAMEFORGE_DEFECTS_AND_REPAIRS.csv`, `GAMEFORGE_ARCHITECTURE.md`, `GAMEFORGE_UNREAL_INTEGRATION_REPORT.md`, `GAMEFORGE_PERFORMANCE_REPORT.md`, `GAMEFORGE_HOSTED_INFERENCE_ARCHITECTURE.md`, `GAMEFORGE_DEPLOYMENT_RUNBOOK.md`, `configs/ui_interaction_registry.json`, and migration/security/capability/test/execution reports. Plugin binary SHA-256: `fc47fe6bece47efeafe212a47fda2ca3cb6f66707daac10d6945743c7730117b`; built artifact remains at `E:\GameForge\validation\gameforge_plugin_probe_20261024`.

- **2026-10-24T17:16:** Fresh broad test reconciliation: **183 non-API unit tests passed in 16.71s** with workspace `TEMP`/`TMP`; the separate loopback host-policy case passed (**1 passed, 7 deselected**) and protected graders **45 passed**. Current unit collection is **191**. The other 7 API endpoint tests are blocked because Starlette TestClient/AnyIO hangs during Windows Proactor startup (`socket._fallback_socketpair` blocks); selector-policy attempt also stalled. `test_api_health` faulthandler captured the blocked stack. Full-suite pass is not claimed. AC-23 stale desktop-deferral assertion was reconciled with D-029; strategy and test now assert the current in-progress desktop gate.

- **2026-10-24T16:52:** **D-035 Persisted Studio Themes and Layout COMPLETE.** Added Ctrl+T and View menu dark/light switching; active palette applies to inline styles, diff formatting, terminal output, and newly-created chat content. Theme, geometry, and dock visibility persist per workspace; Reset Layout restores the default dock state and window size. Tested across window recreation. Fresh checks: **32 core/desktop + 1 selected bridge-host + 45 protected tests passed**. Added theme/layout controls to the capability registry. Real Windows DPI/minimum-size visual checks and full interaction/prompt matrices remain open; Ollama/live Unreal/full suite/packaging remain blocked or unverified. Recorded D-035 and updated Step 13 status and execution/migration reports. Mirrored context to `E:\GameForge\context.md`.
- **2026-10-24T16:54:** **High-severity prompt-loss defect repaired.** AgentRuntime previously appended the prompt through SessionManager but built provider history from a stale Session snapshot, omitting the current user turn. Runtime now reloads the persisted session before history construction. Added exact-text history and Ollama JSON payload cases for spaces, CRLF/LF, indentation, Unicode, and long context. Fresh checks: **36 core/desktop + 1 selected bridge-host + 45 protected tests passed**. Added defect GF-UX-002 and updated G5 evidence. Live HTTP stream roundtrip and broader context overflow/attachment tests remain next.
- **2026-10-24T16:58:** **Ollama response parser isolated and tested synchronously.** A mocked async stream attempt hung in `asyncio.run` under Python 3.14 and was interrupted. Extracted the newline-delimited JSON parser for direct tests covering malformed lines, streamed tokens, final metadata, and termination. Fresh checks: **38 core/desktop + 1 selected bridge-host + 45 protected tests passed**. Request payload construction/serialization is covered; async HTTP request roundtrip, context-window budgeting, session-switch attribution, and attachments remain open.
- **2026-10-24T16:59:** `pytest tests/unit/ --collect-only -q` completed with **187 unit test cases collected in 0.93s**. This is discovery evidence only. The historical 172-unit/45-protected execution predates current test additions; a full current unit execution remains unverified due the recorded environment hang/temp issues.
- **2026-10-24T17:09:** **Context-window budgeting and history feedback implemented (D-036).** System prompt is compacted to identity, constraints, current state, next action, and brief tool schemas. Runtime conservatively estimates tokens from UTF-8 bytes, reserves output/safety capacity, pins the full active prompt, selects recent whole history messages, and reports omissions; oversized prompts fail explicitly without truncation. UI surfaces omission count and budget. System prompt measured at 2,281 estimated tokens vs 2,944 input allowance for the default 4,096 context. Fresh focused checks: 42 core/desktop tests pass in 3.56s. Added actual architecture, Unreal, performance, hosted architecture, deployment, and UI registry artifacts; marked prior web-first architecture report superseded. Unreal Engine 5.7.4 editor/UBT/UAT and VS2022 Community paths present; plugin build not run. **Next:** Seven FastAPI TestClient endpoint tests need a functioning AnyIO/Windows test environment; then complete the prompt matrix, Windows DPI checks, plugin build/bridge handshake, and empirical startup/resource profiling.
- **2026-10-24T17:01:** **Stop/send and stale-session event race repaired.** `AgentService.stop()` no longer marks the worker idle prematurely, so new prompts cannot overwrite the shared worker session/prompt before the old task ends. Switching sessions requests stop and suppresses old task events until completion. Fresh checks: **39 core/desktop + 1 selected bridge-host + 45 protected tests passed**; unit inventory now **188 collected**. Added defect GF-LIFE-001. Full provider timeout/recovery and async HTTP tests remain unverified.
- **2026-10-24T15:42:** **Full Repository Cleanup & Simplification COMPLETE.** Audited all repository files, imports, entry points, and dependencies across `E:\gameforge_step1` and `E:\GameForge`.
  1. Purged 14 ephemeral evaluation run directories from `scratch/eval_runs/` (223 files, 6,622,708 bytes reclaimed).
  2. Purged 9 ephemeral test JSON output dumps from `reports/` (24,435 bytes reclaimed).
  3. Consolidated historical blueprint `GAMEFORGE_MASTER_BLUEPRINT_V1_ARCHIVE.md` (38,096 bytes) into `archive/` per Master Strategy Section 32.1 & Line 2770.
  4. Aligned missing dependencies in `requirements.txt` (`PySide6>=6.6.0`, `fastapi>=0.100.0`, `uvicorn>=0.20.0`, `httpx>=0.24.0`).
  5. Declared `ide` optional dependencies and `gameforge-ide` launcher script entry point in `pyproject.toml`.
  6. Reclaimed **6,930,432 bytes (+6.93 MB)** on drive `E:`, bringing total free space to **590,253,051,904 bytes (549.72 GB)** and total workspace space reclaimed to **23.90 GB**.
  7. Verified 100% passing test suite: **172 unit tests + 45 protected oracles = 217 passing tests (0 failures)**.
  8. Verified native desktop launcher (`launcher --help`), panel imports (all 6 modules cleanly imported), and Ollama model connectivity.
  9. Preserved all 98.9 GB of model weights, Ollama blobs, training checkpoints, datasets, legal packets, and protected benchmarks intact.
  Recorded Decision D-032. Produced `GAMEFORGE_CLEANUP_MANIFEST.md` (v2.0.0) and `GAMEFORGE_CLEANUP_RESULTS.csv` (40 itemized audit actions).
- **2026-10-24T16:31:** **Codex security hardening COMPLETE.** Replaced unsafe agent `shell=True` command execution with a shell-free argv allowlist, shell-syntax rejection, containment validation, and a bounded timeout. Approval-required agent actions now stop before execution; non-mutating diff proposals retain the existing review flow. Added byte-accurate stale-patch protection and atomic writes for apply/rollback. Targeted core + desktop tests: **27 passed**; protected graders: **45 passed**. Recorded D-033 and added `GAMEFORGE_CODEX_MIGRATION_REPORT.md` and `GAMEFORGE_SECURITY_REVIEW.md`. Current blockers: Ollama port 11434 unavailable; PyInstaller unavailable and installation not authorized; sandbox prevents a new complete full-suite test run.
  - Changed source: `src/gameforge_ide/backend/tools/terminal_tools.py`, `edit_tools.py`, `gateway.py`, and `agent/runtime.py`; added regressions in `tests/unit/test_gameforge_ide.py`; updated `AGENTS.md`, `DECISION_LOG.csv`, `GAMEFORGE_ROADMAP.csv`, and `GAMEFORGE_IDE_EXECUTION_LOG.md`. Session-created temporary test folders were removed before handoff.
- **2026-10-24T16:35:** **D-034 Shared Approval, Loopback Bridge, and Prompt Fidelity COMPLETE.** ToolGateway now blocks approval-marked actions from every caller unless a trusted user-interface path explicitly approves them. Human diff and staged-build controls use this path. Removed wildcard CORS and reject non-loopback bridge binds. Chat composer now forwards exact prompt text. Fresh checks: 29 core/desktop + 1 bridge-host + 45 protected passed. Added `GAMEFORGE_CAPABILITY_MATRIX.md`, `GAMEFORGE_DEFECTS_AND_REPAIRS.csv`, and `GAMEFORGE_TEST_REPORT.md`. Remaining: theme/palette and command palette, full prompt matrix, live Ollama, real Unreal plugin/editor, full suite, hosted service package, performance measurements, and distributable packaging.
  - Changed source: `src/gameforge_ide/backend/app.py`, `src/gameforge_ide/backend/tools/gateway.py`, `src/gameforge_ide/launcher.py`, `src/gameforge_ide/desktop/main_window.py`, `src/gameforge_ide/desktop/panels/chat_panel.py`, `diff_panel.py`, `unreal_panel.py`, `src/gameforge_ide/desktop/services/tool_service.py`; regression coverage in `tests/unit/test_gameforge_ide.py`, `test_desktop_acceptance.py`, and `test_ide_api.py`. Stable `objectName` values were added for all main-window menu actions and asserted in the window-assembly test.
- **2026-10-24T15:20:** **Milestone K+ Complete: Critical Desktop UI Repair, Full Functionality Audit & End-to-End Recovery.** Diagnosed and fixed 8 visual and runtime defects:
  1. Auto-sizing `_MessageBubble` (`QTextBrowser` with rich markdown and syntax highlighting) eliminating 30px content squashing and clipping.
  2. Dock sizing proportions enforced in `MainWindow` (`resizeDocks` for Explorer: 260px, Unreal: 340px, Terminal: 160px).
  3. Scoped studio dark theme palette (`#0c0e14`, `#121622`, `#181f30`, `#f3f4f8`) removing root `QWidget` background override.
  4. Repaired UE 5.7 detection, `install_path`, `RunUAT.bat` path (`E:\UE\UE_5.7`), and deduplicated projects with directory tags.
  5. Added top toolbar Terminal toggle button (`_act_tb_terminal`) for 1-click workspace maximization.
  6. Wrapped async generator in `agent_service.py` with `try...finally: await stream_gen.aclose()` and `loop.shutdown_asyncgens()`.
  7. Added parameter fallback in `propose_edit` for both `subpath` and `file_path`.
  8. Verified live streaming from `gameforge-27b-sft:latest` (18 tokens) and captured 7 visual evidence screenshots in `reports/`.
  Full regression suite: **172 unit tests + 45 protected oracles = 217 passing tests (0 failures)**. Recorded Decision D-031. Produced `GAMEFORGE_DESKTOP_UI_REPAIR_REPORT.md`, `GAMEFORGE_DESKTOP_VISUAL_VERIFICATION.md`, `GAMEFORGE_DESKTOP_END_TO_END_TEST_REPORT.md`, `GAMEFORGE_DESKTOP_DEFECTS.csv`, and updated `GAMEFORGE_IDE_TEST_REPORT.md`.
- **2026-10-24T14:48:** **Milestone K: Native Desktop Acceptance & Legacy Web Cleanup COMPLETE.** Verified end-to-end native PySide6 workflow (`tests/unit/test_desktop_acceptance.py` — 6 tests passed). Streamed 217 tokens live from `gameforge-27b-sft:latest` in `AgentService`. Exercised full diff propose $\to$ reject $\to$ approve $\to$ rollback lifecycle with bit-identical SHA-256 restoration. Purged obsolete browser frontend (`src/gameforge_ide/frontend/` — 41.6 KB reclaimed). Reconciled test suite: **168 unit tests + 45 protected oracles = 213 passing tests (zero regressions)**. Recorded Decision D-030. Produced `GAMEFORGE_DESKTOP_ACCEPTANCE_REPORT.md`, `GAMEFORGE_LOCALHOST_CLEANUP_MANIFEST.md`, `GAMEFORGE_LOCALHOST_CLEANUP_RESULTS.csv`, and `GAMEFORGE_IDE_RELEASE_GATE_REPORT.md`.
- **2026-10-24T14:17:** **Native Windows Desktop Conversion COMPLETE.** Replaced the browser-oriented frontend with a genuine PySide6 `QMainWindow` desktop application. Delivered: `desktop/main_window.py`, 4 dockable panels (Chat, Explorer, Diff, Unreal), embedded QProcess terminal, `QThread`-based `AgentService`, `QThreadPool`-based `ToolService`, premium dark stylesheet. Launcher now opens native window by default. All 162 unit tests pass (zero regressions). Launch: `python -m src.gameforge_ide.launcher`.
- **2026-10-24T13:35:** Completed GameForge IDE MVP implementation across all Milestones A through I. Delivered FastAPI backend (`src/gameforge_ide/backend/`), desktop web UI (`src/gameforge_ide/frontend/`), native Unreal Engine 5.7 plugin (`GameForge.uplugin`), typed tool gateway, diff review & rollback, procedural 3D asset generation, and launcher. Verified live local streaming from `gameforge-27b-sft:latest`. 207 automated tests passed (162 unit + 45 protected benchmark oracles; zero regressions).
- **2026-10-24T13:20:** User resolved Decision `D-029` establishing the GameForge IDE MVP with Unreal-first integration as active product priority. Updated `GAMEFORGE_ROADMAP.csv` (Step 13 -> IN_PROGRESS). Published canonical cleanup records: `GAMEFORGE_CLEANUP_MANIFEST.md` and `GAMEFORGE_CLEANUP_RESULTS.csv` (23.89 GB reclaimed). Began Milestone A architecture and implementation.
- **2026-10-24T13:05:** Executed total workspace cleanup across all GameForge folders (`E:\gameforge_blueprint_package`, `E:\gameforge_step1`, `E:\GameForge`). Reclaimed 23.89 GB of disk space (purged 20 volatile Unreal build cache folders from fixtures, cleaned `scratch/eval_runs`, removed redundant unzipped packages and legacy scripts). Verified 100% test pass rate across 141 unit tests and 45 protected benchmark oracles.
- **2026-10-24T12:35:** Completed comprehensive Master Blueprint Implementation Audit (`reports/master_blueprint_implementation_audit.md`). 60 requirements audited; 26.67% verified complete; established absence of Unreal-side plugin as top critical path blocker.
- **2026-10-24T12:15:** Fully integrated persistent Antigravity memory system (`AGENTS.md`, `.agents/rules/context-protocol.md`, `.agents/skills/00-ml-orchestrator.md`, and mirrored `E:\GameForge\context.md`).
- **2026-10-24T12:10:** Created canonical `context.md` covering architecture, non-negotiable constraints, verified Phase 2 metrics (153/160 broader, 40/40 holdout, 141 unit tests), and deployment state.
- **2026-10-24T11:50:** Promoted candidate configuration to production `gameforge-27b-sft:latest` (Ollama ID: `03d36e692be8`).
- **2026-10-24T00:35:** Verified SFT weight convergence and retired `gameforge-v1:latest`.


