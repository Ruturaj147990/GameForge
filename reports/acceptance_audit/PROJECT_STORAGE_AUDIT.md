# GameForge 1.0 — Project Storage Architecture & Two-Location Protocol Audit

**Date:** 2026-11-02T08:05:00Z  
**Auditor:** Antigravity Autonomous Inspector & Systems Engineer  
**Status:** FULLY COMPLIANT (100% VERIFIED)

---

## 1. Executive Summary & Problem Diagnosis

Prior to this audit and architectural remediation, GameForge exhibited project storage fragmentation across multiple locations on the host PC:
1. **Unintended Default Placement:** New games created via prompts or cards were placed silently into hardcoded default directories (`E:\GameForge\projects\<ProjectName>`) without prompting the user to specify or confirm an authoritative project root.
2. **Scattered Project Assets:** Source code, `.uproject` files, intermediate compilation artifacts, build outputs, and GameForge design specifications were scattered across disparate paths without a unified root container.
3. **Ghost Project Duplicates:** Re-opening or rebuilding projects sometimes produced multiple nested copies or orphaned project records in workspace databases.
4. **Hardcoded Engine Root:** Subsystems fell back to fixed paths (`E:\UE\UE_5.7`), failing if Unreal Engine was installed on another drive letter or standard Epic Games Launcher location.

This audit establishes, implements, and verifies the **Strict Two-Location Storage Architecture** across all GameForge subsystems.

---

## 2. The Strict Two-Location Storage Architecture

Under GameForge 1.0, there are exactly two managed persistent storage destinations:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GAMEFORGE 1.0 STORAGE DESTINATIONS                    │
├──────────────────────────────────────┬──────────────────────────────────────┤
│  LOCATION 1: App Conversation History │  LOCATION 2: User Project Root       │
├──────────────────────────────────────┼──────────────────────────────────────┤
│  • Stored in workspace/app data      │  • Selected by user on project start │
│  • Path: <workspace>/.gameforge/     │  • Contains 100% of project assets   │
│  • Chat logs, approval records       │  • .uproject, Config, Content, Source│
│  • Minimal project path references   │  • Plugins, GameForge/, Packaged/    │
│  • ZERO source code or game assets   │  • Single authoritative project root │
└──────────────────────────────────────┴──────────────────────────────────────┘
```

### Location 1: Application-Owned Conversation History
- **Path:** `<workspace>/.gameforge/sessions` (and `.gameforge/approvals`).
- **Contents:**
  - `sess_*.json`: Conversation turn histories and user prompt logs.
  - `apr_*.json`: Approval action records (approval status, timestamp, tool arguments).
  - Minimal project path references (e.g., `{"project": "CounterStrikeLite", "project_dir": "E:/UserProjects/CounterStrikeLite"}`).
- **Strict Invariants:**
  - Location 1 must **never** contain game source files (`.cpp`, `.h`, `.Target.cs`), Unreal project definitions (`.uproject`), generated meshes, materials, audio assets, or packaged game binaries.
  - Deleting or migrating Location 1 never corrupts the underlying Unreal Engine project.

### Location 2: User-Selected Project Directory (Authoritative Root)
- **Path:** Explicitly selected by user on creation, or resolved directly from an existing `.uproject`.
- **Structure:**
  ```text
  UserSelectedProjectRoot/
  ├── ProjectName.uproject          # Unreal Engine project descriptor
  ├── Config/                       # DefaultEngine.ini, DefaultGame.ini, DefaultInput.ini
  ├── Content/                      # Levels, Blueprints, Materials, Audio, Meshes
  ├── Source/                       # C++ module source and header files
  │   └── ProjectName/
  │       ├── Public/
  │       └── Private/
  ├── Plugins/                      # Deployed runtime plugins (Plugins/GameForge)
  ├── GameForge/                    # Design specifications & compositions
  │   ├── design/
  │   │   └── game.gds.json         # Authoritative GameDesignSpec (schema gds/1.1)
  │   ├── composition/              # RunSpec DAG plans and compositions
  │   ├── reports/                  # Pipeline build, test, and verification reports
  │   └── evidence/                 # Visual viewport captures and telemetry
  ├── Packaged/                     # Packaged redistributable game executables
  │   └── Windows/
  │       └── ProjectName.exe
  ├── Saved/                        # Unreal Engine logs, session tokens, autosaves
  ├── Intermediate/                 # UBT compilation intermediate objects & PCH
  └── Binaries/                     # Compiled C++ game DLLs & editor binaries
  ```
- **Strict Invariants:**
  - Exactly one copy of the project exists on disk.
  - Every IDE subsystem (`HomeView`, `GamesView`, `DesignView`, `BuildView`, `PlayView`, `EvidenceView`, `GameTools`, `ActionRunner`, `ForgeExecutor`) receives and operates on this identical authoritative root.
  - The project can be copied, moved, or backed up as a single self-contained directory tree.

---

## 3. Directory Selection Workflow Implementation

To guarantee the user always controls Location 2:
1. **Interactive Dialog (`NewProjectDialog`):**
   - Implemented in `src/gameforge_ide/desktop/dialogs/new_project_dialog.py`.
   - Prompts for C++ Project Name and Destination Folder with real-time path resolution.
   - Educates the user on the Two-Location Architecture with an explicit architectural notice.
   - Validates parent directory writability, sanitizes project identifiers, and warns if existing files are present.
2. **Games View Controls:**
   - Added `+ New Project…` button (triggers `NewProjectDialog`) and `Open…` button (opens folder selector for existing projects).
   - Emits `newProjectRequested(name, pdir)` and `openProjectRequested(pdir)` directly to `MainWindow`.
3. **Home View Prompt Integration:**
   - Added an inline `Project Folder: [ Path ] [ Browse… ]` selector row beneath prompt inputs.
   - When the user clicks "Design it →", the resulting GDS embeds `gds.meta.project_dir = str(target_pdir)`.
4. **Design View Project Banner:**
   - Displays `Authoritative Project Root: <resolved_path>` prominently with a `Change Folder…` action.
   - All GDS saves and Forge run approvals operate strictly on this confirmed directory.

---

## 4. Verification & Audit Outcomes

| Requirement | Implementation Target | Verification Method | Outcome |
|---|---|---|---|
| Exactly two managed locations | `core/projects.py`, `services/projects_service.py` | `test_two_location_storage_isolation` | **PASS (100%)** |
| User-selected directory prompt | `NewProjectDialog`, `HomeView`, `GamesView` | UI unit tests + benchmark script | **PASS (100%)** |
| Zero scattered/duplicate folders | `scripts/run_storage_and_cs_regen_benchmark.py` | Filesystem scan across workspaces | **PASS (100%)** |
| Self-contained project hierarchy | `CS_Regeneration`, `Platformer_Diversity` | Checked .uproject, Config, Source, Plugins, GDS | **PASS (100%)** |
| Automatic Engine Detection | `unreal/discovery.py`, `core/settings.py` | `test_unreal_discovery.py` (8 tests) | **PASS (100%)** |
