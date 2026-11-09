# GameForge 1.0 — User Guide

GameForge is an agentic game development platform for Windows that turns natural-language game ideas into verified, playable Unreal Engine 5.7 games, and iterates on them through living project diffs.

---

## 1. System Requirements & Installation

### Requirements
- **OS:** Windows 11 64-bit
- **Engine:** Unreal Engine 5.7.4 (installed via Epic Games Launcher)
- **CPU:** 6-core processor (Ryzen 5 7600X or Intel i5-13600K recommended)
- **Memory:** 32 GB RAM recommended (16 GB minimum)
- **GPU:** 12 GB VRAM (AMD Radeon RX 7700 XT or NVIDIA RTX 4070)
- **Storage:** NVMe SSD with >= 50 GB free space

### Installation Steps
1. Download `GameForge-1.0.0-win64.zip` from your release distribution.
2. Extract the archive to your preferred directory (e.g., `E:\GameForge\app`).
3. Run `Install-GameForge.ps1` in PowerShell to create Desktop and Start Menu shortcuts (no administrator privileges required).
4. Launch GameForge via the desktop shortcut or `GameForge.bat`.

---

## 2. First Run & Onboarding

Upon initial startup, GameForge performs automated environment validation:
1. **Engine Detection:** Automatically detects Unreal Engine 5.7.4 installations via Epic Launcher manifests and registry keys.
2. **Local Model Roster:** Validates local Ollama instance connectivity and confirms the presence of the 4 canonical models:
   - `gameforge-qwen3.5-9b` (primary conversational & design specialist)
   - `gameforge-qwen3.5-4b` (fast code generation & tool caller)
   - `gameforge-27b-sft` (heavy architecture & compiler repair)
   - `llama3.1:8b` (generalist fallback)
3. **Workspace Configuration:** Prompts for default project workspace directory (defaults to `Documents\GameForge\Projects`).

---

## 3. Creating Your First Game

### Natural-Language Prompting
From the **Home View** or **Assistant Panel**, enter a natural-language description of your game idea:
> *"Create a third-person action adventure in an ancient forest ruin at dusk: talk to the scout, recover 5 artifacts while avoiding patrol guards and fire hazards, unlock the gate with a switch, and escape."*

### Generation Pipeline
GameForge executes a structured, deterministic pipeline:
1. **Game Design Spec (GDS):** Generates schema-validated specification (`gds/1.1`) defining overview, scene, entities, rules, audio, and performance budgets.
2. **Deterministic Composition:** Maps GDS entities to levels using layout algorithms (`open_world`, `rooms`, `arena`, `course`, `board`, `lanes`), Poisson-disk distribution, and reachability math.
3. **Asset & Art Direction:** Selects cohesive material themes (`stone_wood`, `scifi_metal`, `desert_sand`), populates CSG procedural props, and binds Epic mannequin rigs (`SKM_Manny`, `ABP_Unarmed`).
4. **Cinematics:** Automatically constructs intro camera spline flythroughs with cut detection and mood music binding.
5. **Project Scaffolding:** Emits C++ source, configuration INIs, asset definitions, and generates the Unreal project.

---

## 4. Iterating on Living Projects

GameForge allows continuous natural-language modification without discarding custom edits:
- **Design Diffing:** Changes are computed as RFC 6902 JSON Patches (`add`, `remove`, `replace`) displayed in the Design View sentence diff preview.
- **Granular Impact Analysis:** Invalidation analysis rebuilds only changed pipeline steps, preserving compiled C++ binaries and unchanged level geometry.
- **Actor Reconciliation & Protection:** Modifying levels in Unreal Editor tags custom work as user-owned. Rebuilding GameForge detects conflicts and offers:
  - **Keep Mine:** Preserves user edits in the level.
  - **Use Design:** Re-aligns level with updated specification.

---

## 5. Playtesting, Scenarios & Performance Tuning

### Headless Scenario QA
Every game includes deterministic scenarios executed via injected inputs:
- Automated objective and combat verification without manual playthrough.
- Headless scenario runner supports both Development and Shipping builds.

### Shipping Package Optimization
- **Oodle Compression:** Automatically enables high-ratio Oodle compression in `DefaultGame.ini`.
- **Plugin Trimming:** Disables unused heavy default plugins (`AlembicImporter`, `GeometryCache`, `SpeedTreeImporter`, `DatasmithContent`).
- **Package Gate:** Enforces package size <= 400 MB for single-level games and <= 600 MB for multi-level adventures.

### Closed-Loop Performance Optimizer
GameForge incorporates an automated optimizer that runs CSV profiler benchmarks:
- Applies reversible adjustments: reduces PCG density, caps shadow distance, enables Nanite, tunes screen percentage.
- Retains optimizations only if p95 frame time improves >= 5% while visual quality rubric remains stable.

---

## 6. Troubleshooting & FAQ

### Unreal Engine Not Found
- Verify UE 5.7.4 is installed via Epic Games Launcher.
- If using a custom install path, open **Settings View → Engine Configuration** and manually set the path to `Engine/Binaries/Win64/UnrealEditor.exe`.

### Ollama Offline
- Verify Ollama is running (`ollama serve`).
- Verify model models directory is configured: `$env:OLLAMA_MODELS="E:\GameForge\models\ollama"`.

### Build Interruption & Recovery
- If the IDE or PC shuts down mid-build, re-launch GameForge and navigate to **Build View**.
- The interface automatically presents a **Resume** action to recover from the latest checkpoint without re-running completed steps.

### Disk Space Hygiene
- Temporary build outputs and scenario logs are maintained under `.gameforge/` inside each project workspace.
- Run project hygiene cleanup in Settings to prune intermediate cook caches.

---

## 7. Privacy, Security & Telemetry

- **100% Local-First:** All model inferences run on local GPU/VRAM via Ollama. No source code, project assets, or prompts leave your computer.
- **Zero Telemetry:** No user tracking, analytics beacons, or background data collection.
- **Shell-Free Execution:** Agent commands operate under strict executable allowlists (`git`, `cmake`, `python`, `pytest`) without shell interpreters (`cmd.exe`, `powershell.exe`).
- **Approval Gates:** File edits, deletions, and build triggers require interactive user approval.
