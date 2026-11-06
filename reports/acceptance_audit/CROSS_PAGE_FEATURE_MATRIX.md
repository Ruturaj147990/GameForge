# GameForge Desktop Frontend — Cross-Page Feature & Action Matrix

**Document ID:** `GF-MATRIX-2026-11`  
**Lead Coordinator:** Primary Antigravity Agent  
**Last Updated:** 2026-11-05T13:30:00Z  

---

## 1. Screen-by-Screen Capability & Action Profile

| Screen / View | Primary Information Displayed | Supported User Actions | UI Controls Providing Actions | Workflows Involved | Shared Components Used | Overlapping / Similar Screens |
|---|---|---|---|---|---|---|
| **TopBar** | Active project name, active path, current view breadcrumb, active build run state, readiness status | Change active project, jump to project folder, open settings, toggle assistant drawer, open command palette | `QComboBox` (`project_combo`), interactive path chip, `RailButton` triggers, `_run_chip` | Global to all workflows | `icon()`, `tokens.py`, `ProjectsService` | HomeView (project switching), GamesView (project selection) |
| **Activity Rail** | Navigation icons for primary views, assistant drawer toggle | Switch primary views (`Ctrl+1`..`Ctrl+8`), toggle assistant drawer | `RailButton` items, active indicator bar | Global navigation | `icon()`, `tokens.py` | TopBar breadcrumb, CommandPalette |
| **HomeView** | Hero prompt input, starter genre presets, recent games list (thumbnails, status, date), system readiness cards | Generate game from natural-language prompt, click preset to populate prompt, open recent game in DesignView, fix offline systems | `PromptTextEdit`, `PresetChip`, `RecentGameCard`, `QPushButton` ("Design It"), `ReadinessRowWidget` | Game inception, rapid prototyping, system health checks | `RecentGameCard`, `PresetChip`, `ReadinessRowWidget`, `tokens.py` | GamesView (recent games list), DesignView (spec generation), SettingsView (readiness / paths) |
| **GamesView** | Visual catalog of all local projects (grid/list mode), project path, engine version, last modified, build status | Browse projects, switch active project, search/filter games, create new game, open project folder, delete project | `QListView` / `QTableView`, search `QLineEdit`, view mode toggle button, "+ New Project" button, context menu ("Delete Game") | Project selection, project management, project lifecycle | `NewProjectDialog`, `DeleteGameDialog`, `ProjectsService`, `tokens.py` | HomeView (recent games cards), TopBar (`project_combo`) |
| **DesignView** | Game Design Spec (GDS) overview, genre, camera, player counts, rules list, levels, revision history timeline | Edit GDS parameters, add/edit gameplay rules, propose AI change from prompt, review sentence diffs, trigger build | `GdsForm`, `CollapsibleSection`, `RuleEditorDialog`, prompt `QLineEdit`, "Propose Change", "Build Game", "View Diff" | Game design authoring, iterative prompt modifications, DAG build dispatch | `GdsForm`, `RuleEditorDialog`, `tokens.py`, `ForgeService` | ChatPanel (propose change / open design), HomeView (prompt to design) |
| **CodeView** | Source code editor with line numbers, file tree, diff inspector, embedded terminal, Unreal bridge | Browse project files, edit code, jump to line, review/apply/rollback AI diffs, execute PowerShell commands | `CodeEditor`, `LineNumberArea`, `CodeHighlighter`, `ExplorerPanel`, `DiffPanel`, `TerminalPanel`, `UnrealPanel` | Direct developer modification, code review, terminal debugging | `ExplorerPanel`, `DiffPanel`, `TerminalPanel`, `UnrealPanel`, `tokens.py` | DesignView (source jump), ProblemsTable (file jump) |
| **BuildView** | Forge DAG run history, step timeline model, execution status badges, batched stdout/stderr logs, compilation problems | Select run, inspect step logs, filter problems, jump to error line, cancel active build, rollback to checkpoint | `QComboBox` (`run_combo`), `QListView` (`step_list`), `LogView`, `ProblemsTable`, `QPushButton` ("Cancel", "Rollback", "Show Problems") | Pipeline build verification, build error diagnostics, run rollback | `StepRowDelegate`, `LogView`, `ProblemsTable`, `tokens.py`, `ForgeService` | PlayView (run results), TopBar (`_run_chip`), CodeView (error jump) |
| **PlayView** | Automated scenario test matrix (smoke, jump, collectibles, goal, combat), pass/fail status, packaged binary path | Inspect scenario assertions, trigger scenario replay, launch packaged Windows game executable | `QTableView`, scenario inspector panel, `QPushButton` ("Launch Game", "Run Scenarios") | Gameplay verification, QA acceptance, game execution | `tokens.py`, `runner.py` | BuildView (pipeline outcome), GamesView (playable flag) |
| **AssetsView** | Project asset inventory, category/stage filters, asset metadata table, asset detail drawer | Filter assets by type, search asset keywords, view metadata (dimensions, material, source op) | Search `QLineEdit`, category `QComboBox`, `QTableView`, detail drawer | Content inspection, visual asset verification | `tokens.py`, `AssetRegistry` | CodeView (asset explorer dock) |
| **SettingsView** | Engine installations, project storage root, model routing tiers, appearance preferences (theme, font scale) | Detect/browse engine paths, change storage root, test model routing, switch dark/light theme | `QComboBox`, file pickers, model routing table, theme radio buttons | Configuration, platform tuning | `tokens.py`, `apply_theme` | OnboardingWizard (initial setup), OllamaSetupDialog (daemon setup) |
| **Assistant Drawer (ChatPanel)** | Streaming agent conversation, thinking tokens, tool execution cards, GDS design preview | Chat with AI agent, request game changes, approve/reject file diffs and tool executions | `ChatPanel`, `_MessageBubble`, `ApprovalCard`, `DesignPanel` | AI-assisted engineering, interactive change requests | `ApprovalCard`, `DiffPanel`, `tokens.py` | DesignView (propose change), CodeView (diff panel) |

---

## 2. Redundancy & Duplication Analysis

### A. Project & Workspace Directory Selection
- **Status:** **CONSOLIDATED (Single Authoritative Source)**.
- **Analysis:** Previously, directory pickers existed independently in TopBar, HomeView, DesignView, BuildView, PlayView, ExplorerPanel, and ChatPanel.
- **Canonical Implementation:** `TopBar.project_combo` coordinated via `ProjectsService.activeProjectChanged` and `MainWindow.set_active_project()`.
- **Finding:** Confirmed that all views adhere to this single selector; no independent folder selectors remain.

### B. Game Creation Flows
- **Locations:**
  1. `HomeView` hero prompt input ("Design It" button) -> AI spec generation -> `DesignView`.
  2. `GamesView` "+ New Project..." button -> `NewProjectDialog` -> creates project on disk.
  3. `ChatPanel` prompt input -> proposes `create_game` tool call -> `ApprovalCard` -> executes Composer & Forge.
- **Assessment:** These three flows represent distinct user journeys:
  - Flow 1 (HomeView) is the visual "Prompt to Game Design" journey for designers.
  - Flow 2 (GamesView) is the manual "Empty / Preset Scaffold" journey for developers.
  - Flow 3 (ChatPanel) is the conversational autonomous agent journey.
- **Optimization:** Ensure consistent preset names, unified naming validation (`NewProjectDialog` vs `HomeView` sanitization), and seamless handoff without redundant inputs.

### C. System Readiness & Ollama Health Displays
- **Locations:**
  1. `TopBar` systems readiness status pill (`● Ready` / `● Offline`).
  2. `HomeView` readiness cards row (Ollama, Engine, Hardware).
  3. `SettingsView` engine discovery & model status.
- **Assessment:**
  - `TopBar` is an ambient global summary.
  - `HomeView` is an actionable onboarding prompt with "Set up" / "Start" buttons.
  - `SettingsView` is a detailed configuration interface.
- **Optimization:** Both TopBar click and HomeView fix actions open the canonical `OllamaSetupDialog` or `SettingsView`. Ensure exact state synchronization between `SystemsService` and all three views.

### D. File Jump & Error Inspection
- **Locations:**
  1. `ProblemsTable` in `BuildView` emits `openLocationRequested(path, line)`.
  2. `ExplorerPanel` in `CodeView` emits `file_selected(path)`.
  3. `ChatPanel` file links emit navigation requests.
- **Canonical Implementation:** `MainWindow` handles all file jump signals and routes them to `CodeView.open_file(path, line)`.

---

## 3. Cross-Page Usability & Interaction Heuristics Audit

| Usability Heuristic | Audit Finding | Improvement Required |
|---|---|---|
| **1. Visibility of System Status** | Build execution progress is clearly visible in TopBar chip and BuildView timeline, but long model generation in HomeView lacks an inline progress spinner. | Add clear indeterminate progress indicator to HomeView "Design It" button while LLM is generating. |
| **2. Match Between System & Real World** | Technical terminology is generally sound. However, rule editor uses raw variable expressions (e.g. `entity.relics.collected >= 5`). | Provide natural-language sentence builders alongside formula inputs in `RuleEditorDialog`. |
| **3. User Control & Freedom** | Cancellation of Forge builds is available in BuildView, but cancelling in-flight prompt generation in HomeView previously disabled the button permanently. | Ensure HomeView cancel action resets state cleanly and re-enables inputs immediately. |
| **4. Consistency & Standards** | TopBar, Rail, and all Views use design tokens. However, some button hover padding and table selection colors have subtle variations between views. | Standardize QSS table item selection and card hover transitions across all views. |
| **5. Error Prevention** | `DeleteGameDialog` requires exact typing of project name. `NewProjectDialog` validates identifier rules in real time. | Add real-time slug/identifier validation to HomeView prompt title extraction. |
| **6. Recognition Rather Than Recall** | Active project is always visible in TopBar. Recent games have visual cards with genre badges. | Ensure thumbnail previews load consistently for all recent games. |
| **7. Flexibility & Efficiency of Use** | Command Palette (`Ctrl+K`), quick shortcuts (`Ctrl+1`..`Ctrl+8`), and search filters provide high efficiency for power users. | Add keyboard arrow navigation to recent games grid and timeline steps. |
| **8. Aesthetic & Minimalist Design** | Uncluttered Midnight Purple dark theme. Evidence tab was removed to reduce noise. | Ensure empty states in PlayView, AssetsView, and GamesView provide helpful illustration and action guidance. |
| **9. Help Users Recognize & Recover** | Inline validation messages in GDS form indicate exact schema errors. BuildView Problems tab aggregates compiler issues. | Ensure error messages include direct actionable suggestions. |
| **10. Help & Documentation** | AboutDialog provides environment specs. Tooltips exist on icon-only actions. | Verify all icon buttons in Rail, TopBar, and View toolbars have descriptive tooltips and accessible names. |
