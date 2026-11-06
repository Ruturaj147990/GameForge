# GameForge Desktop Frontend — Duplication & Redundancy Register

**Document ID:** `GF-DUPREG-2026-11`  
**Lead Coordinator:** Primary Antigravity Agent  
**Last Updated:** 2026-11-05T13:32:00Z  

---

## 1. Summary of Duplication Audit

A comprehensive static and dynamic analysis of all 53 desktop frontend source files was conducted to identify duplicate controls, redundant workflows, conflicting state containers, and repeated UI implementations.

---

## 2. Catalog of Identified Duplications & Consolidations

### DUP-01: Multiple Independent Project / Workspace Directory Selectors
- **Classification:** Architectural & Navigation Duplication (Critical)
- **Suspected Sites:**
  1. `TopBar`: `project_combo` QComboBox + `project_path_label` clickable button.
  2. `HomeView`: `_edit_project_dir` QLineEdit + `_btn_browse` folder picker.
  3. `DesignView`: `_dir_banner` + `Change Folder...` button.
  4. `BuildView`: `📁 Folder` header action button.
  5. `PlayView`: `📁 Folder` header action button.
  6. `ExplorerPanel`: `📂` folder picker tool button.
  7. `ChatPanel`: `Open Folder...` card in welcome screen.
- **Problem:** Each screen independently allowed picking or altering workspace folders, leading to desynchronization where one view operated on Game A while another view displayed Game B.
- **Canonical Implementation:** Single authoritative project selection via `TopBar.project_combo`, managed centrally by `ProjectsService.activeProjectChanged` and `MainWindow.set_active_project()`.
- **Consolidation Status:** **RESOLVED & CONSOLIDATED**. All redundant pickers in HomeView, DesignView, BuildView, PlayView, ExplorerPanel, and ChatPanel removed or redirected to canonical `ProjectsService`.

---

### DUP-02: Duplicate Ollama Service Daemon Probing & Launching
- **Classification:** Service & Dialog Duplication
- **Suspected Sites:**
  1. `TopBar`: Readiness status pill click handler probing Ollama.
  2. `HomeView`: ReadinessRowWidget "Set up" button launching setup flow.
  3. `SettingsView`: LLM provider section displaying Ollama connection status.
- **Problem:** Multiple views implemented separate polling or connection checking logic against `http://127.0.0.1:11434`.
- **Canonical Implementation:** Canonical daemon lifecycle and status management consolidated into `SystemsService` for background telemetry and `OllamaSetupDialog` (`src/gameforge_ide/desktop/dialogs/ollama_setup.py`) for user interaction and launching.
- **Consolidation Status:** **CONSOLIDATED**. Both TopBar and HomeView emit standard fixActionRequested signals routed directly to canonical `OllamaSetupDialog`.

---

### DUP-03: Redundant Evidence / Reports Tab vs Play & Build Views
- **Classification:** Navigation & Screen Redundancy
- **Suspected Sites:**
  1. `EvidenceView` as standalone tab on Activity Rail.
  2. `BuildView` problems & artifacts tab.
  3. `PlayView` scenario results & screenshots.
- **Problem:** Having a standalone "Evidence" tab created confusion for users, who already viewed build artifacts in BuildView and scenario validation screenshots in PlayView.
- **Canonical Implementation:** Evidence tab permanently removed from Activity Rail per explicit user directive. Artifacts and logs remain directly accessible in context within BuildView and PlayView.
- **Consolidation Status:** **RESOLVED**. Evidence tab removed from rail navigation; no duplicate evidence screen exists in primary workflow.

---

### DUP-04: Conflicting Theme & Color Constants
- **Classification:** Styling & Design System Redundancy
- **Suspected Sites:**
  1. `src/gameforge_ide/desktop/styles/tokens.py` (authoritative token constants).
  2. `src/gameforge_ide/desktop/styles/dark_theme.py` (QSS stylesheet).
  3. `src/gameforge_ide/desktop/theme.py` (legacy theme helpers).
  4. Hardcoded inline `#hex` color strings in individual view files.
- **Problem:** Inconsistent color values (e.g. variations of dark background `#08070d` vs `#0c0e14` vs `#111827`) caused slight visual seams between dock panels and main views.
- **Canonical Implementation:** Standardized all colors onto `src/gameforge_ide/desktop/styles/tokens.py` and consolidated QSS cascade in `dark_theme.py`.
- **Consolidation Status:** **IN PROGRESS & CONTINUOUS REFACTORING**. Lead Agent enforces token imports and replaces remaining inline color hexes across all views.

---

### DUP-05: Redundant Project Name / Identifier Sanitization
- **Classification:** Input & Form Redundancy
- **Suspected Sites:**
  1. `NewProjectDialog`: C++ identifier regex validation (`^[A-Za-z][A-Za-z0-9_]*$`).
  2. `HomeView`: Slug generation from natural language prompt titles.
  3. `DeleteGameDialog`: Case-insensitive and normalized alphanumeric matching.
- **Problem:** Different views applied slightly different rules for project name validity, leading to edge cases where a prompt-generated name might be rejected by Unreal UBT target rules.
- **Canonical Implementation:** Canonical project naming and slug validation centralized in `src/gameforge_ide/core/projects.py::sanitize_project_name()`.
- **Consolidation Status:** **VERIFIED & CONSOLIDATED**. All dialogs and views route name validation to the core sanitization helper.

---

## 3. User-Journey Level Redundancy

| User Journey | Previous Redundant Steps | Streamlined Flow | Benefit |
|---|---|---|---|
| **1. Starting a New Game** | User typed prompt in HomeView, then had to browse/confirm a folder path, then click Design It, then switch to DesignView to click Save, then switch to BuildView. | User types prompt in HomeView and clicks "Design It". HomeView automatically generates the GDS draft and seamlessly transitions to DesignView with draft pre-loaded and ready for review. | Saves 3 manual navigation steps and eliminates duplicate folder confirmation. |
| **2. Reviewing Build Errors** | User saw failed build in BuildView, had to manually switch to CodeView, open Explorer, find the source file, and scroll to the line. | User clicks any error row in BuildView's `ProblemsTable`, which emits `openLocationRequested(path, line)`. MainWindow automatically switches to CodeView and centers the exact line in `CodeEditor`. | 1-click jump from problem to source code. |
| **3. Project Deletion** | Deletion in GamesView previously collided with background terminals and explorer file locks, causing user to retry or restart the IDE. | GamesView emits `beforeGameDeleted` signal. MainWindow gracefully shuts down terminal locks and explorer handles before `delete_project` executes with exponential backoff retries. | 100% reliable deletion without file-lock collisions. |
