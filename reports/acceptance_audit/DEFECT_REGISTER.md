# GameForge 1.0 — Defect Register & Remediation Audit

Generated: 2026-11-02T00:10:00Z | Verified by Antigravity Autonomous Inspector

## Summary of Defects Discovered & Remediated

| Defect ID | Severity | Subsystem | Description | Root Cause | Status | Resolution File |
|---|---|---|---|---|---|---|
| **DEF-001** | High | LLM Provider | Ollama background daemon offline on initial startup | Process not automatically launched on host reboot | `VERIFIED_LIVE` | Spawned daemon with `OLLAMA_MODELS="E:\GameForge\models\ollama"` |
| **DEF-002** | Critical | Core / Desktop | Fragmented & hardcoded project directory paths across IDE views | Views hardcoded `projects_root / project_name`, failing for workspace-local, imported, or custom directories | `VERIFIED_LIVE` | `src/gameforge_ide/core/projects.py` |
| **DEF-003** | High | Desktop Shell | Project selection desynchronization | `MainWindow._on_project_selected` updated views but left `_agent`, `_tools`, `_chat_panel`, `_explorer`, `_terminal` on repo root | `VERIFIED_LIVE` | `src/gameforge_ide/desktop/main_window.py` |
| **DEF-004** | Medium | Desktop Shell | Dead "Open Folder" button in Studio layout | `ExplorerPanel.open_folder_requested` signal was only wired in legacy dock mode | `VERIFIED_LIVE` | `src/gameforge_ide/desktop/main_window.py` |
| **DEF-005** | Medium | TopBar Navigation | Project selector missing newly drafted games | Startup list only scanned `.uproject` files; newly drafted GDS-only games were missing from TopBar | `VERIFIED_LIVE` | `src/gameforge_ide/desktop/main_window.py` |
| **DEF-006** | High | Desktop Services | `AttributeError: 'NoneType' object has no attribute 'is_file'` in `projects_service.py` | Evaluated `uproject_file.is_file()` when `uproject_file` was `None` | `VERIFIED_LIVE` | `src/gameforge_ide/desktop/services/projects_service.py` |
| **DEF-007** | High | Code Architecture | AD-15 host path literal violations (`E:/GameForge/projects`) | Raw drive letter strings in product code flagged by `test_no_host_paths.py` | `VERIFIED_LIVE` | `src/gameforge_ide/core/projects.py` |
| **DEF-008** | Critical | Design / Composer | Pydantic validation failure on `DraftWin` (`win.0.seconds`) and `DraftLose` (`lose.1.target`) | LLMs naturally emit `seconds: 60` for `survive_seconds`, but `DraftWin` only had `target` with `extra="forbid"` | `VERIFIED_LIVE` | `src/gameforge_ide/design/draft.py`, `src/gameforge_ide/design/expand.py` |

---

## Detailed Root Cause Analysis

### DEF-001: Ollama Background Service Offline
- **Symptom:** Initial `curl http://localhost:11434/api/tags` returned exit code 1.
- **Root Cause:** Ollama was installed on `E:\GameForge\ollama_bin\ollama.exe` with models on `E:\GameForge\models\ollama`, but had not been registered as an automatic Windows service.
- **Fix:** Launched daemon in background with correct `$env:OLLAMA_MODELS` path. Confirmed 4 local models responding.

### DEF-002: Hardcoded Project Directory Paths Across IDE Views
- **Symptom:** Opening games located in arbitrary directories, git repositories, or custom folders caused `DesignView`, `BuildView`, `PlayView`, and `EvidenceView` to report missing files.
- **Root Cause:** Each view computed `Path(get_settings().projects_root) / project_name`. If a project resided in the active workspace root or developer folder, views looked in the wrong location.
- **Fix:** Authored canonical `src/gameforge_ide/core/projects.py` providing `resolve_project_dir()`, `find_uproject()`, `find_gds()`, and `list_all_project_dirs()`. Integrated across all views.

### DEF-003: Project Selection Desynchronization in Shell
- **Symptom:** Switching projects in `TopBar.project_combo` updated the visible view, but agent tool calls and terminal commands continued executing against the top-level repository workspace.
- **Root Cause:** `_on_project_selected()` lacked synchronization calls for `_agent.set_workspace()`, `_tools.set_workspace()`, `_explorer.set_workspace()`, and `_terminal.set_workspace()`.
- **Fix:** Added complete multi-panel synchronization in `MainWindow._on_project_selected()`.

### DEF-004: Dead "Open Folder" Action in Studio Shell
- **Symptom:** Clicking the 📂 folder button in `ExplorerPanel` had no effect in Studio layout mode.
- **Root Cause:** Signal connection `self._code_view._explorer.open_folder_requested.connect(self._open_folder)` was only executed inside `_build_dock_layout()`.
- **Fix:** Connected `open_folder_requested` to `_open_folder` during `_build_studio_layout()`.

### DEF-005: TopBar Project Selector Desynchronization on New Game
- **Symptom:** After creating a new game design specification via prompt, the project did not appear in `TopBar.project_combo`.
- **Root Cause:** TopBar combo only read from disk on startup and required an existing `.uproject` file.
- **Fix:** Implemented `MainWindow.refresh_projects(select_project=...)` and updated project detection to recognize both `.uproject` and `game.gds.json`.

### DEF-006: NoneType AttributeError in ProjectsService
- **Symptom:** `test_home_view.py::test_projects_service_helpers` crashed with `AttributeError: 'NoneType' object has no attribute 'is_file'`.
- **Root Cause:** Ternary expressions `uproject_file if uproject_file.is_file() else None` raised an exception when `uproject_file` was `None`.
- **Fix:** Changed to `uproject_file if (uproject_file and uproject_file.is_file()) else None`.

### DEF-007: Host Path Literal Violation (AD-15)
- **Symptom:** `test_no_host_paths.py` failed due to `E:/GameForge/projects` string literal in `src/gameforge_ide/core/projects.py`.
- **Root Cause:** Product code must never contain drive letter literals (`E:\...`, `C:\...`).
- **Fix:** Switched to dynamic environment resolution `os.environ.get("GAMEFORGE_EXTRA_PROJECTS_ROOT")` and settings host profile inspection.

### DEF-008: Pydantic Schema Rejection on Survival Game Prompts
- **Symptom:** Prompt-to-GDS generation failed for survival games (`win.0.seconds: Extra inputs are not permitted`).
- **Root Cause:** `DraftWin` specified `extra="forbid"` and only declared `target: Optional[int]`. For `survive_seconds`, LLMs emitted `{"type": "survive_seconds", "seconds": 60}`, which was rejected.
- **Fix:** Added `seconds: Optional[int]` to `DraftWin` and `target: Optional[int]` to `DraftLose`, with bidirectional normalization in `expand.py`.
