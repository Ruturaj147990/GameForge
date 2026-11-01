# GameForge 1.0 — Architecture Audit & Subsystem Verification
Generated: 2026-11-01T23:57:39.648550 | Verified by Antigravity Autonomous Inspector

## 1. Desktop Application Architecture and UI
- **Framework:** PySide6 6.12.0 (Qt 6) desktop shell.
- **Layout Architecture:** Dual-mode shell supporting Studio Layout (`StudioShell`, dock-free modern multi-view) and classic Dock Layout (`StudioWindow`).
- **The 7 Canonical Views:**
  1. **Home (`HomeView`):** Dashboard, quick project launcher, system readiness telemetry, recent builds.
  2. **Games (`GamesView`):** Interactive project catalog, package status indicators, quick open/play actions.
  3. **Design (`DesignView`):** GDS viewer/editor, prompt-to-game interactive design, revision history, diff inspector.
  4. **Build (`BuildView`):** Forge executor pipeline monitor, live step log streaming, pause/resume, checkpoint rollback.
  5. **Play (`PlayView`):** Integrated game launcher, automated playthrough runner, QA metrics, FPS/performance HUD.
  6. **Evidence (`EvidenceView`):** Audit artifact gallery, test reports, screenshot inspect, protected oracle logs.
  7. **Settings (`SettingsView`):** Ollama model selector, engine paths, directories, theme toggle (Studio Dark/Light), font scaling.

## 2. Directory Lifecycle & Project Identity Architecture
- **Canonical Resolver:** `src/gameforge_ide/core/projects.py` provides authoritative project identity and multi-root discovery.
- **Supported Project Roots:**
  - Configured `settings.projects_root`
  - Active IDE workspace directory
  - Dedicated large-storage path `E:\GameForge\projects`
- **Project Marker Rules:** Directory containing `<ProjectName>.uproject` OR `design/spec.json` OR `gameforge.json`.
- **Cross-View Synchronization:** `MainWindow._on_project_selected` synchronizes `_agent`, `_tools`, `_chat_panel`, `_explorer`, `_terminal`, and views.

## 3. Agent Runtime, Planning and Task Orchestration
- **Model Provider:** Local Ollama HTTP daemon on `127.0.0.1:11434` with model `gameforge-qwen3.5-9b:latest` (or `27b-sft`).
- **Constraint:** Programmatic calls enforce `"think": False` and bounded context `num_ctx: 4096`.
- **Streaming & Threading:** `ChatWorker` (QThread) handles streaming responses asynchronously without blocking Qt GUI thread.

## 4. Unreal Engine Bridge and Operation Catalogue
- **Toolchain:** `unreal/toolchain.py` interfaces with Unreal Build Tool (UBT) and Cook/Package pipelines.
- **Editor Bridge:** `unreal/live_editor.py` connects via loopback REST API (`127.0.0.1`) to the Unreal Engine Remote Execution plugin.
- **Operation Catalog:** Exactly 129 verified engine operations across actor spawning, level geometry, lighting, materials, and physics.

## 5. Procedural Composer & Generation Pipelines
- **Generator Engines:** 3 distinct topological algorithms in `pipeline/level_generator.py`:
  1. `arena`: Circular / radial walled combat arena with central focal points and perimeter cover.
  2. `course`: Sequential 3D obstacle and platforming route with elevation variations and checkpoints.
  3. `lanes`: Multi-path linear circuit with checkpoints and obstacle gates suited for racing/time trials.
- **Proof of Interpretation:** GDS parameters dynamically control room dimensions, obstacles, enemy count, and hazard density based on the player's text prompt.

## 6. Tool Gateway & Containment
- **Approval Protocol:** Modifying critical files or running destructive engine operations triggers PySide6 `ApprovalDialog`.
- **Diff Inspection:** Proposed GDS or code modifications generate unified diffs presented to the user prior to execution.
- **Containment:** Operations strictly contained to the active project workspace.

## 7. Protected Oracle Verification
- **Integrity:** `graders/protected/` is strictly read-only and passed 45/45 tests.
- **Coverage:** Pickup collection (t2_005), Projectile collision (t2_008), Player composition (t3_016), Health/Stamina HUD (t3_017).