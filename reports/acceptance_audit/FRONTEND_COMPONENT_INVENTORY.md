# GameForge Desktop Frontend — Complete Component & Feature Inventory

**Document ID:** `GF-INVENTORY-2026-11`  
**Lead Coordinator:** Primary Antigravity Agent  
**Last Updated:** 2026-11-05T13:28:00Z  
**Total Frontend Source Files:** 53  
**Total Inventoried Components:** 52  

---

## Format Specification
`Component/Feature → Purpose → User Action → Filename → Line Numbers → Owner`

---

## 1. Application Shell & Navigation

| Component / Feature | Purpose | User Action | Filename | Line Numbers | Owner |
|---|---|---|---|---|---|
| **MainWindow Shell** | Application root window, central widget host, view coordinator | Switch views, toggle drawer, resize window | [`src/gameforge_ide/desktop/main_window.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/main_window.py#L97-L1829) | L97–L1829 | **Lead Agent** |
| **Activity Rail (`Rail`)** | Fixed-width vertical activity bar with primary navigation icons | Click icon or press shortcut (`Ctrl+1`..`Ctrl+8`) | [`src/gameforge_ide/desktop/shell/rail.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/rail.py#L31-L170) | L31–L170 | **Lead Agent** |
| **RailButton** | Custom button widget in activity rail with active indicator pill | Hover, click to switch view | [`src/gameforge_ide/desktop/shell/rail.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/rail.py#L172-L215) | L172–L215 | **Lead Agent** |
| **Studio TopBar (`TopBar`)** | Global header bar with breadcrumb, project combo, build chip, system status | Select project, click breadcrumb, click readiness | [`src/gameforge_ide/desktop/shell/top_bar.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/top_bar.py#L27-L365) | L27–L365 | **Lead Agent** |
| **Lazy ViewHost Router (`ViewHost`)** | QStackedWidget container dynamically instantiating views on demand | View transition driven by Rail or TopBar | [`src/gameforge_ide/desktop/shell/view_host.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/view_host.py#L11-L82) | L11–L82 | **Lead Agent** |
| **Command Palette (`CommandPalette`)** | Fuzzy-searchable action launcher dialog with acronym/token filtering | Press `Ctrl+K` or `Ctrl+P`, type search, select action | [`src/gameforge_ide/desktop/shell/palette.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/palette.py#L24-L159) | L24–L159 | **Lead Agent** |
| **Assistant Drawer Shell (`AssistantPanel`)** | Right-side sliding drawer host with splitter persistence | Click Assistant button or press `Ctrl+I` to open/close | [`src/gameforge_ide/desktop/shell/assistant_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/assistant_panel.py#L20-L167) | L20–L167 | **Lead Agent** |

---

## 2. Views & Primary Screens

| Component / Feature | Purpose | User Action | Filename | Line Numbers | Owner |
|---|---|---|---|---|---|
| **Studio Home Landing View (`HomeView`)** | Main landing dashboard with prompt input, starter presets, recent games, readiness | Type game prompt, click preset, open recent game | [`src/gameforge_ide/desktop/views/home_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/home_view.py#L42-L827) | L42–L827 | **Agent A** |
| **Studio Games Catalog View (`GamesView`)** | Project catalog browser with grid/list modes, filter, delete, new game | Browse games, search, create project, delete game | [`src/gameforge_ide/desktop/views/games_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/games_view.py#L77-L881) | L77–L881 | **Agent A** |
| **Studio Settings View (`SettingsView`)** | Application preferences: engine detection, storage directories, model routing, theme | Change paths, configure model routing, switch theme | [`src/gameforge_ide/desktop/views/settings_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/settings_view.py#L49-L493) | L49–L493 | **Agent A** |
| **First-Run Onboarding (`OnboardingWizard`)** | 3-step setup wizard for fresh installations (Engine, Storage, Models) | Complete step-by-step setup, click Finish | [`src/gameforge_ide/desktop/views/onboarding.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/onboarding.py#L44-L282) | L44–L282 | **Agent A** |
| **Studio Design View (`DesignView`)** | Visual GDS specification editor, revision timeline, proposal triggers | Edit GDS parameters, propose changes, review diff | [`src/gameforge_ide/desktop/views/design_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/design_view.py#L53-L1006) | L53–L1006 | **Agent B** |
| **Studio Developer View (`CodeView`)** | Developer perspective hosting code editor and dockable tools | Browse code, edit files, inspect diffs, run terminal | [`src/gameforge_ide/desktop/views/code_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/code_view.py#L51-L453) | L51–L453 | **Agent B** |
| **Studio Build & Pipeline View (`BuildView`)** | Pipeline run monitor with timeline step list, batched logs, problems table | View build status, inspect step logs, cancel or rollback run | [`src/gameforge_ide/desktop/views/build_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/build_view.py#L61-L886) | L61–L886 | **Agent C** |
| **Studio Play & QA View (`PlayView`)** | Scenario review and test suite results with packaged launcher | Review automated test passes, launch game executable | [`src/gameforge_ide/desktop/views/play_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/play_view.py#L45-L437) | L45–L437 | **Agent C** |
| **Studio Assets View (`AssetsView`)** | Full asset inventory browser with stage/category filters and metadata drawer | Search assets, filter by type, inspect asset details | [`src/gameforge_ide/desktop/views/assets_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/assets_view.py#L38-L385) | L38–L385 | **Agent C** |

---

## 3. Shared Widgets & Controls

| Component / Feature | Purpose | User Action | Filename | Line Numbers | Owner |
|---|---|---|---|---|---|
| **Problems Table (`ProblemsTable`)** | Diagnostic errors/warnings table with source jump links | Click row to jump to source file and line | [`src/gameforge_ide/desktop/widgets/problems_table.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/widgets/problems_table.py#L18-L90) | L18–L90 | **Agent C** |
| **Batched Log View (`LogView`)** | High-throughput streaming log viewer with auto-scroll lock | Scroll up to pause, click 'Resume Autoscroll' | [`src/gameforge_ide/desktop/widgets/log_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/widgets/log_view.py#L21-L192) | L21–L192 | **Agent C** |
| **Step Row Delegate (`StepRowDelegate`)** | Custom QStyledItemDelegate for DAG timeline items | Render status icon, title, checkpoint badge, duration | [`src/gameforge_ide/desktop/widgets/step_row.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/widgets/step_row.py#L17-L122) | L17–L122 | **Agent C** |
| **GDS Form Widget (`GdsForm`)** | Multi-section structured game design specification editor | Edit title, pitch, genre, player counts, rules, entities | [`src/gameforge_ide/desktop/widgets/gds_form.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/widgets/gds_form.py#L47-L656) | L47–L656 | **Agent B** |
| **Collapsible Section (`CollapsibleSection`)** | Expandable card section widget with header disclosure triangle | Click header to expand or collapse section | [`src/gameforge_ide/desktop/widgets/gds_form.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/widgets/gds_form.py#L47-L95) | L47–L95 | **Agent B** |
| **Rule Editor Dialog (`RuleEditorDialog`)** | Modal form for creating and editing structured game rules | Select trigger, conditions, target entity, effect | [`src/gameforge_ide/desktop/widgets/rule_editor.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/widgets/rule_editor.py#L23-L324) | L23–L324 | **Agent B** |
| **Code Editor (`CodeEditor`)** | Central code editing widget with line numbers and syntax highlighting | Type, edit code, jump to line | [`src/gameforge_ide/desktop/views/code_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/code_view.py#L154-L245) | L154–L245 | **Agent B** |
| **Line Number Area (`LineNumberArea`)** | Gutter widget displaying line numbers synchronized with scroll | Visual line orientation | [`src/gameforge_ide/desktop/views/code_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/code_view.py#L110-L152) | L110–L152 | **Agent B** |
| **Code Syntax Highlighter (`CodeHighlighter`)** | QSyntaxHighlighter supporting C++, Python, JSON, Unreal macros | Syntax-colored keyword rendering | [`src/gameforge_ide/desktop/views/code_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/code_view.py#L51-L108) | L51–L108 | **Agent B** |

---

## 4. Docks & Panels

| Component / Feature | Purpose | User Action | Filename | Line Numbers | Owner |
|---|---|---|---|---|---|
| **Explorer Panel (`ExplorerPanel`)** | Filesystem tree view of current project with filter | Click file to open in editor, search files | [`src/gameforge_ide/desktop/panels/explorer_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/explorer_panel.py#L29-L232) | L29–L232 | **Agent B** |
| **Diff Panel (`DiffPanel`)** | Side-by-side or unified diff reviewer with Apply/Reject actions | Review diff chunks, click Apply, Reject, or Rollback | [`src/gameforge_ide/desktop/panels/diff_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/diff_panel.py#L29-L251) | L29–L251 | **Agent B** |
| **Chat & AI Assistant Panel (`ChatPanel`)** | Conversational assistant interface with streaming responses | Type message, approve tool actions, switch session | [`src/gameforge_ide/desktop/panels/chat_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/chat_panel.py#L44-L1473) | L44–L1473 | **Agent B** |
| **Approval Card (`ApprovalCard`)** | Mutating action confirmation card in assistant chat | Click Approve, Reject, or inspect parameter diff | [`src/gameforge_ide/desktop/panels/approval_card.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/approval_card.py#L45-L279) | L45–L279 | **Agent B** |
| **Design Preview Panel (`DesignPanel`)** | Assistant drawer preview tab for active GDS | Read GDS summary from assistant drawer | [`src/gameforge_ide/desktop/panels/design_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/design_panel.py#L20-L93) | L20–L93 | **Agent B** |
| **Asset Inspector Panel (`AssetPanel`)** | Dockable asset property inspector | Inspect asset details from developer perspective | [`src/gameforge_ide/desktop/panels/asset_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/asset_panel.py#L20-L185) | L20–L185 | **Agent C** |
| **Unreal Engine Panel (`UnrealPanel`)** | Dockable Unreal Engine status and op dispatch tool | Trigger test commands, check editor bridge | [`src/gameforge_ide/desktop/panels/unreal_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/unreal_panel.py#L30-L330) | L30–L330 | **Agent C** |
| **Terminal Panel (`TerminalPanel`)** | Embedded PowerShell terminal emulator | Enter shell commands within workspace context | [`src/gameforge_ide/desktop/panels/terminal_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/terminal_panel.py#L27-L218) | L27–L218 | **Agent C** |
| **Plan Panel (`PlanPanel`)** | Dockable step-by-step task plan visualizer | Inspect execution tasks and plan progress | [`src/gameforge_ide/desktop/panels/plan_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/plan_panel.py#L20-L265) | L20–L265 | **Agent C** |
| **Mission Panel (`MissionPanel`)** | Dockable autonomous goal and mission tracker | Track autonomous engineering goals | [`src/gameforge_ide/desktop/panels/mission_panel.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/panels/mission_panel.py#L20-L284) | L20–L284 | **Agent C** |

---

## 5. Dialogs & Modals

| Component / Feature | Purpose | User Action | Filename | Line Numbers | Owner |
|---|---|---|---|---|---|
| **New Project Dialog (`NewProjectDialog`)** | Modal for creating new games with genre presets | Enter project name, select genre/template, click Create | [`src/gameforge_ide/desktop/dialogs/new_project_dialog.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/dialogs/new_project_dialog.py#L28-L290) | L28–L290 | **Agent A** |
| **Delete Game Dialog (`DeleteGameDialog`)** | Confirmation modal requiring exact project name typing | Type project name, click Delete Game | [`src/gameforge_ide/desktop/dialogs/delete_game_dialog.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/dialogs/delete_game_dialog.py#L28-L229) | L28–L229 | **Agent A** |
| **Ollama Setup Dialog (`OllamaSetupDialog`)** | Health checker and 1-click launcher for Ollama daemon | Click Launch Daemon, test connection, close | [`src/gameforge_ide/desktop/dialogs/ollama_setup.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/dialogs/ollama_setup.py#L37-L418) | L37–L418 | **Agent A** |
| **Hosted Settings Dialog (`HostedSettingsDialog`)** | Hosted AI provider credentials and daily budget controls | Enter API keys, configure daily spend caps, save | [`src/gameforge_ide/desktop/dialogs/hosted_settings.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/dialogs/hosted_settings.py#L39-L253) | L39–L253 | **Agent A** |
| **About Dialog (`AboutDialog`)** | Information modal with version 1.0.0 and engine details | View release info, copy system diagnostics | [`src/gameforge_ide/desktop/dialogs/about_dialog.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/dialogs/about_dialog.py#L23-L148) | L23–L148 | **Agent A** |

---

## 6. Feedback, Indicators & Notifications

| Component / Feature | Purpose | User Action | Filename | Line Numbers | Owner |
|---|---|---|---|---|---|
| **Toast Card (`ToastCard`)** | Non-modal notification bubble with auto-dismiss | Read status, click close icon | [`src/gameforge_ide/desktop/shell/toasts.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/toasts.py#L25-L141) | L25–L141 | **Lead Agent** |
| **Toast Overlay (`ToastOverlay`)** | Stacking container for floating toasts | Displays feedback non-intrusively | [`src/gameforge_ide/desktop/shell/toasts.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/toasts.py#L143-L224) | L143–L224 | **Lead Agent** |
| **Readiness Row Widget (`ReadinessRowWidget`)** | System probe status row with one-click fix action button | Click 'Set up' / 'Start' on offline components | [`src/gameforge_ide/desktop/views/home_view.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/views/home_view.py#L320-L390) | L320–L390 | **Agent A** |
| **Run Status Pill** | Active Forge DAG run indicator pill in TopBar | Click pill to switch to BuildView | [`src/gameforge_ide/desktop/shell/top_bar.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/shell/top_bar.py#L120-L160) | L120–L160 | **Lead Agent** |

---

## 7. Design System & Styling

| Component / Feature | Purpose | User Action | Filename | Line Numbers | Owner |
|---|---|---|---|---|---|
| **Design Tokens (`tokens.py`)** | Single source of truth for spacing, radius, typography, colors | Shared token definitions | [`src/gameforge_ide/desktop/styles/tokens.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/styles/tokens.py#L1-L50) | L1–L50 | **Lead Agent** |
| **Dark Theme QSS (`dark_theme.py`)** | High-contrast Midnight Purple stylesheet for Qt widgets | QSS stylesheet compilation & cascade | [`src/gameforge_ide/desktop/styles/dark_theme.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/styles/dark_theme.py#L1-L864) | L1–L864 | **Lead Agent** |
| **Vector Icon System (`icons.py`)** | SVG vector icon rendering with theme-aware palette recoloring | Dynamic SVG loading & caching | [`src/gameforge_ide/desktop/icons.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/icons.py#L1-L59) | L1–L59 | **Lead Agent** |
| **Theme Helpers (`theme.py`)** | Color constants bridge and palette synchronization | System theme resolution | [`src/gameforge_ide/desktop/theme.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/theme.py#L1-L61) | L1–L61 | **Lead Agent** |
