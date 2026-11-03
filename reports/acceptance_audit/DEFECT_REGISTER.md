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
| **DEF-016** | Critical | Forge / Pipeline | Recurring "Box-and-Player" generation failure bypassing modern Composer | `legacy_assemble()` in `legacy_stages.py` ignored `ctx.step.inputs["plan"]` and called hardcoded legacy recipes | `VERIFIED_LIVE` | `src/gameforge_ide/forge/handlers/legacy_stages.py` |
| **DEF-017** | Critical | Unreal Engine | Hardcoded engine path and missing Epic manifest item scanning | `settings.py` fell back to `E:\UE\UE_5.7` and failed to discover Epic Games Launcher `*.item` manifests | `VERIFIED_LIVE` | `src/gameforge_ide/unreal/discovery.py`, `src/gameforge_ide/core/settings.py` |
| **DEF-018** | High | Project Storage | Project storage fragmentation and silent hardcoded placement | Projects were silently created in default folders rather than prompting user for authoritative root | `VERIFIED_LIVE` | `src/gameforge_ide/desktop/dialogs/new_project_dialog.py`, `backend/tools/game_tools.py` |
| **DEF-019** | Medium | Desktop Views | Missing "New Project" and "Open Project" directory controls in GamesView & HomeView | Users had no UI buttons to initiate clean project root directory selection | `VERIFIED_LIVE` | `src/gameforge_ide/desktop/views/games_view.py`, `home_view.py` |
| **DEF-020** | Medium | Design / GDS | Pydantic validation failure when GDS declared `Meta.project_dir` | `Meta` model had `extra="forbid"` and lacked `project_dir: Optional[str]` | `VERIFIED_LIVE` | `src/gameforge_ide/design/gds.py` |

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

### DEF-009: Preset Keywords Intercepting Rich Custom Game Prompts
- **Symptom:** Prompts with custom mechanics and narratives containing words like "arena" or "brawler" were prematurely hijacked by static presets instead of routing to local LLM expansion.
- **Root Cause:** `prompt_to_gds.py` evaluated keyword substring matching before checking if the prompt contained rich custom requirements.
- **Fix:** Added `CUSTOM_DETAIL_KEYWORDS` check in `prompt_to_gds.py` so prompts with custom mechanics route to local LLM draft expansion.

### DEF-010: Player Entity Weapon & Attack Parameters Omitted in Runtime Definition
- **Symptom:** First-person and shooter games generated from prompts lacked projectile shooting capabilities and input bindings for firing.
- **Root Cause:** `runtime_def.py` ignored player entity properties (`attack_mode`, `projectile_speed`, `attack_damage`, `weapons`) and omitted `IA_Fire` from Enhanced Input default mappings.
- **Fix:** Added extraction of player entity properties in `runtime_def.py` and mapped `IA_Fire` into default input bindings.

### DEF-011: Missing Projectile Attack Mechanics in C++ Runtime Plugin
- **Symptom:** `AGameForgeCharacter` only possessed melee attack logic, preventing FPS and ranged shooter mechanics from working in game.
- **Root Cause:** `AGameForgePlayerController` only bound `IA_Attack` to `PerformMeleeAttack()`.
- **Fix:** Implemented `bProjectileAttack`, `ProjectileSpeed`, `PerformAttack()`, and `PerformRangedAttack()` in `GameForgePlayer.h` and `GameForgePlayer.cpp`, spawning `AGameForgeProjectile` along camera aim direction and binding `IA_Fire`.

### DEF-012: AttributeError 'RuleSpec' object has no attribute 'id' in Composer
- **Symptom:** `compose(gds)` crashed with `AttributeError: 'RuleSpec' object has no attribute 'id'` when GDS rules had custom code effects.
- **Root Cause:** `composer/compose.py` read `rule.id` instead of `rule.rule_id`.
- **Fix:** Updated `compose.py` to use `getattr(rule, "rule_id", getattr(rule, "id", ...))` defensively.

### DEF-013: Missing Codegen Handler Support in Forge Executor
- **Symptom:** StepKind.CODEGEN failed when executing modern GDS compositions with custom C++ rule tasks.
- **Root Cause:** `legacy_sources` in `src/gameforge_ide/forge/handlers/legacy_stages.py` only supported legacy recipes and ignored `tasks` in `ctx.step.inputs`.
- **Fix:** Added support in `legacy_sources` for `ctx.step.inputs["tasks"]`, automatically generating C++ headers and source files via `generate_header` and `generate_source`.

### DEF-014: Legacy Recipe Hijacking of Model-Generated GDS
- **Symptom:** `create_game` tried to convert model-generated designs into legacy recipes rather than running the modern Phase 6 Composer path.
- **Root Cause:** `to_legacy_params` did not check if the GDS was generated by an LLM or had first-person camera mode.
- **Fix:** Added check in `to_legacy_params` raising `LegacyUnsupported` when `gds.meta.generator.startswith("model:")` or camera is first-person.

### DEF-015: Chatbot Intent Misclassification on Informal Gaming Phrasings
- **Symptom:** 2,000-prompt benchmark exhibited 82.45% baseline accuracy due to informal typos ("mak a jumpin gem", "cod a top dwn shtr") and camera adjustments failing to trigger GDS generation/patching.
- **Root Cause:** Strict regex boundaries in `spec_from_prompt.py` and `runtime.py`.
- **Fix:** Expanded regex dictionaries and verb lists, boosting benchmark accuracy to 94.70% (1,894/2,000).

### DEF-016: Recurring "Box-and-Player" Generation Failure
- **Symptom:** Generating games from natural language prompts produced an empty walled cube with a single player inside, ignoring requested rooms, cover blocks, weapons, bots, and objectives.
- **Root Cause:** In `src/gameforge_ide/forge/handlers/legacy_stages.py`, `legacy_assemble()` completely bypassed `ctx.step.inputs["plan"]` (the Composer LevelPlan) and dispatched instead to legacy hardcoded recipes (`stages.assemble_arena_level()`), which spawned only `Arena_Floor`, 4 perimeter wall cubes, and a PlayerStart.
- **Fix:** Overhauled `legacy_stages.py::legacy_assemble()` to detect `if "plan" in ctx.step.inputs:`, deserialize `LevelPlan`, call `plan_to_op_calls()`, and dispatch the full sequence of modular geometry pieces (floors, dividing walls, doors), placed actors (combat bots, bomb defusal sites, weapon crates), NavMeshBoundsVolume, and nav rebuild operations through `LiveEditorLink`.

### DEF-017: Hardcoded Engine Path Dependency & Missing Epic Item Manifests
- **Symptom:** GameForge failed on machines where Unreal Engine was installed on custom drive letters or registered in Epic Games Launcher `*.item` files.
- **Root Cause:** `core/settings.py` relied on legacy `LauncherInstalled.dat` and fell back to `E:\UE\UE_5.7`. Modern Epic Games Launcher stores per-app manifests under `%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item`.
- **Fix:** Implemented `src/gameforge_ide/unreal/discovery.py` supporting 5 discovery sources: explicit env overrides, Epic Games Launcher `*.item` manifests, `LauncherInstalled.dat`, Windows Registry hives (HKLM/HKCU), and filesystem drive scanning. Integrated into `core/settings.py`.

### DEF-018: Project Storage Fragmentation & Silent Default Placement
- **Symptom:** Projects were silently created in default directories (`E:\GameForge\projects\<ProjectName>`) without allowing the user to choose or confirm the canonical project root.
- **Root Cause:** Subsystems lacked a unified contract for user-selected project roots, creating scattered files and multiple copies.
- **Fix:** Enforced the Strict Two-Location Storage Architecture: Location 1 (app conversation history only) and Location 2 (user-selected project root containing all project files). Created `NewProjectDialog` prompting for project name and directory with real-time validation.

### DEF-019: Missing Directory Selection UI Controls in Games & Home Views
- **Symptom:** The desktop IDE lacked buttons to initiate project directory selection or open existing projects from custom folders.
- **Root Cause:** `GamesView` only had view mode and refresh controls; `HomeView` lacked a directory location field in the prompt section.
- **Fix:** Added `+ New Project…` and `Open…` buttons in `GamesView` header toolbar; added inline `Project Folder: [ Path ] [ Browse… ]` selector in `HomeView`; added `Authoritative Project Root` banner in `DesignView`.

### DEF-020: Pydantic Schema Violation for `Meta.project_dir`
- **Symptom:** `GameDesignSpec` validation failed when setting `meta.project_dir` because `Meta` had `extra="forbid"`.
- **Root Cause:** `Meta` lacked a dedicated optional field for tracking the project directory.
- **Fix:** Added `project_dir: Optional[str] = None` to `Meta` in `src/gameforge_ide/design/gds.py`, enabling the GDS to durably declare its canonical project root.

### DEF-021: HomeView Unsupported Prompt Notice openAssistantRequested Signal Missing
- **Symptom:** When a user enters non-game prompts in HomeView, the notice says "Try the Assistant" but clicking or triggering it never opened the Assistant panel.
- **Root Cause:** `HomeView` lacked an `openAssistantRequested` signal emission and wiring to `MainWindow`.
- **Fix:** Added `openAssistantRequested` signal in `HomeView` and wired it in `MainWindow` to toggle the assistant dock open.

### DEF-022: GdsForm goals.win and goals.lose Data Loss on Edit
- **Symptom:** Edits made to win and lose goals in `GdsForm` were lost when saving or building.
- **Root Cause:** `_apply_inputs_to_spec()` in `gds_form.py` failed to extract and update `_edit_win` and `_edit_lose` text into `spec.goals.win` and `spec.goals.lose`.
- **Fix:** Implemented parser and updater for win/lose goals in `gds_form.py`.

### DEF-023: DesignView load_project Missing projectChanged Event
- **Symptom:** Opening a project in Design View did not synchronize the project selector in other views.
- **Root Cause:** `load_project()` in `design_view.py` failed to emit `self.projectChanged.emit(project_name)`.
- **Fix:** Added `self.projectChanged.emit(project_name)` in `load_project()`.

### DEF-024: EvidenceView openFileRequested Disconnected from CodeView
- **Symptom:** Clicking a file link in EvidenceView did nothing.
- **Root Cause:** `openFileRequested` signal was not connected to `CodeView.open_file()`.
- **Fix:** Connected `openFileRequested` on EvidenceView to `CodeView` in `MainWindow`.

### DEF-025: SettingsView Theme & Font Scale Incomplete Persistence
- **Symptom:** Theme and font changes did not persist to workspace `.gameforge/ide_settings.ini`.
- **Root Cause:** `SettingsView` only saved to `QSettings` without synchronizing `.gameforge/ide_settings.ini`.
- **Fix:** Synchronized settings to both `QSettings` and `<workspace>/.gameforge/ide_settings.ini`.

### DEF-026: MainWindow Command Palette Dead Code & Missing Studio Views
- **Symptom:** Command palette had 48 lines of unreachable dead code and lacked shortcuts for "View: Home" and "View: Games Catalog".
- **Root Cause:** Stale fallback block left behind after ViewHost refactor.
- **Fix:** Cleaned dead code and registered Home and Games views in `_open_command_palette`.

### DEF-027: DiffPanel diff_rolled_back Signal Disconnected
- **Symptom:** Rolling back a diff in DiffPanel left the editor with stale unsynchronized buffers.
- **Root Cause:** `diff_rolled_back` signal was not connected to reload file buffers.
- **Fix:** Connected `diff_rolled_back` to `CodeView.reload_current_file()` in `MainWindow`.

### DEF-028: Recurring Box-and-Player Failure: Missing StaticMesh & Material References in Layout Ops, Missing PlayerStart Actor, Null GameDefinition, CameraMode Ignored
- **Symptom:** Prompts consistently generated a generic platform with a mannequin enclosed by bare boxes.
- **Root Cause:** 1) Layouts spawned `StaticMeshActor` without `static_mesh` or `material` args; Unreal defaulted to bare untextured cubes; 2) `level_ops.py` omitted `PlayerStart`, spawning default pawn at `(0, 0, 100)`; 3) `scaffold_cpp_project()` never wrote `GameDefinition` setting into `DefaultGame.ini`, leaving `UGameForgeRuntimeSettings::GameDefinition` null at runtime; 4) C++ `AGameForgeGameMode::StartPlay()` read speeds and health but completely ignored `camera`, never setting `Char->CameraMode` or calling `Char->ApplyCameraMode()`; 5) Projectiles, bot meshes, and HUD were not instantiated or attached in C++.
- **Fix:** 1) Created `tactical_fps` layout and updated `arena` layout with explicit prototype meshes and materials; 2) Added `PlayerStart` actor in `level_ops.py`; 3) Added `[/Script/GameForgeRuntime.GameForgeRuntimeSettings]\nGameDefinition=/Game/GameForge/GD_Main.GD_Main` in `scaffold_cpp_project()` and fallback in C++; 4) Overhauled `AGameForgeGameMode::StartPlay()` to parse `camera`, configure `CameraMode`, hide pawn mesh in first person, attach weapon mesh in viewport, add center crosshair reticle, spawn glowing bullet projectiles, and spawn humanoid enemy bot meshes; 5) Created `AGameForgeBombSite` and `AGameForgeBomb` interactive actors.

### DEF-029: Project Source Compilation Failing to Sync Plugin C++ Source Changes
- **Symptom:** Changes to GameForge plugin C++ runtime were not propagated to project plugins during compilation.
- **Root Cause:** `deploy_gameforge_plugin()` only copied Python ops, skipping `Source/`.
- **Fix:** Overhauled `deploy_gameforge_plugin()` to always synchronize `Source/` into project plugins.

### DEF-030: Oodle Packaging INI Merge Conflict in Toolchain
- **Symptom:** Oodle compression settings were skipped if `[/Script/UnrealEd.ProjectPackagingSettings]` already existed in `DefaultGame.ini`.
- **Root Cause:** Rigid string check failed to append packaging keys under existing header.
- **Fix:** Appended Oodle settings directly under the existing section header.

### DEF-031: GamesView Delete Game Option Fails to Delete Project
- **Symptom:** Clicking "Delete Game..." in the GamesView card context menu and confirming deletion closed the dialog but left the project folder completely intact on disk, with no visible error message.
- **Root Cause:**
  1. `delete_project(project_name)` in `projects_service.py` relied on `shutil.rmtree(pdir)`. On Windows, Git repositories create read-only files (e.g. `.git/objects/*` pack files and binaries). Standard `shutil.rmtree` raises `PermissionError: [WinError 5] Access is denied` on the first read-only file, aborting deletion.
  2. `GamesView._execute_delete` only passed `game.name` (a string) without passing `game.project_dir`. For projects where folder name differed from display title (e.g. `CS_Regeneration` vs `CounterStrikeLite`), `resolve_project_dir("CounterStrikeLite")` returned `None`, failing silently.
  3. `DeleteGameDialog` required typing exact `game.name`. If a user typed the display title seen on the card (`game.title`) or used different case, the delete button remained disabled.
  4. In `GamesView._execute_delete`, if the background job failed or returned `False`, only a background `logger.error` was logged; the UI never displayed an error message or notified the user.
  5. `MainWindow` was not connected to project deletion signals, leaving stale active project references and unrefreshed recent lists.
- **Fix:**
  1. Updated `delete_project` to accept `project_dir` directly and implemented a Windows read-only file handler (`stat.S_IWRITE` via `onexc`/`onerror`) with a retry loop.
  2. Updated `delete_project` to purge deleted project entries from `runs_index.json` across candidate locations and remove SQLite index files (`<workspace>/.gameforge/index/<key>.db`).
  3. Updated `DeleteGameDialog` to accept both `game.name` and `game.title` (case-insensitively) and added Return key submission.
  4. Updated `GamesView` to pass `game.project_dir`, notify the user with `QMessageBox.warning` on failure, and emit `gameDeleted(name, pdir)`.
  5. Wired `GamesView.gameDeleted` to `MainWindow._on_game_deleted` to deselect deleted projects, refresh `TopBar` and `HomeView`, and display an informative toast.
  6. Added 6 comprehensive regression tests in `tests/unit/test_delete_game_regression.py`.

### DEF-032: GamesView Delete Game Blocked by Active Terminal Shell Lock & Rigid Confirmation UI
- **Symptom:** Selecting "Delete Game..." from the GamesView card context menu failed to delete the game when the project was currently active, or failed silently if the user could not satisfy the exact typed name barrier.
- **Root Cause:**
  1. **Active Terminal CWD Lock:** When a project was selected in GameForge Studio, `MainWindow._on_project_selected()` synchronized the workspace to `terminal_panel`, launching an interactive `powershell.exe` process whose Current Working Directory (`CWD`) was set to `game.project_dir`. On Windows, the operating system locks any folder that serves as the CWD of an active process (`[WinError 32] The process cannot access the file because it is being used by another process`). Because `MainWindow` only cleaned up *after* `_execute_delete` succeeded (`gameDeleted` signal), the directory remained locked during `shutil.rmtree()`, causing deletion to fail.
  2. **Confirmation Barrier:** `DeleteGameDialog` kept the "Delete permanently" button disabled until the user typed the exact name into an empty input box. When project cards ellipsize the title or when title differs from directory name (e.g. `CS_Regeneration` vs `CounterStrikeLite`), typing what appeared on the card failed to enable the button. Users had no 1-click option to auto-fill the confirmation.
- **Fix:**
  1. Added `beforeGameDeleted = Signal(str, Path)` to `GamesView` and emitted it immediately upon confirmation, prior to submitting the delete job.
  2. Implemented `MainWindow._on_before_game_deleted()` to stop the active terminal shell (`_stop_shell()`) and redirect all panel workspaces (`explorer`, `chat_panel`, `agent`, `tools`, `unreal_panel`, `design_panel`, `asset_panel`) back to `self._workspace`, completely releasing all directory and file locks before deletion begins.
  3. Enhanced `delete_project()` in `projects_service.py` to use `psutil` to detect and terminate any lingering child processes with CWD or open files inside `project_dir`, pre-emptively remove read-only attributes on all files/subdirectories, and retry `shutil.rmtree()` up to 5 times with exponential backoff.
  4. Enhanced `DeleteGameDialog` with a 1-click `[Fill name]` button, auto-focus on input, space/punctuation/hyphen-normalized matching (`counter strike`, `counter-strike`, `cs regeneration`), and dynamic visual validation text.
  5. Added 3 new unit tests in `tests/unit/test_delete_game_regression.py`.



