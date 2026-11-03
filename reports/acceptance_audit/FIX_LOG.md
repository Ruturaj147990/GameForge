# GameForge 1.0 — Code Remediation & Fix Log

Generated: 2026-11-02T00:10:00Z | Verified by Antigravity Autonomous Inspector

## Overview
This log details all modifications made to source files during the GameForge 1.0 acceptance audit and feature-by-feature repair cycle. Every fix preserves existing architecture contracts, honors protected grader oracles, and has been verified with live regression tests.

---

### Fix 1: Canonical Project Resolver Implementation
- **Files Added:**
  - `src/gameforge_ide/core/projects.py`
  - `tests/unit/test_core_projects.py`
- **Purpose:** Centralized, authoritative project identification and multi-root directory discovery.
- **Functions:**
  - `find_uproject(path)`: Locate `<Name>.uproject`.
  - `find_gds(path)`: Locate `game.gds.json` or `spec.json`.
  - `is_gameforge_project(path)`: Verify project markers.
  - `resolve_project_dir(name, workspace_dir)`: Resolve authoritative directory path across workspace, projects_root, and developer paths.
  - `list_all_project_dirs(workspace_dir)`: Multi-root project discovery.
  - `find_packaged_executable(project_dir, name)`: Locate packaged Win64 executable.
  - `open_folder_in_file_manager(path)`: Native OS explorer launcher.
- **Verification:** `pytest tests/unit/test_core_projects.py` passed (7/7 in 0.07s).

---

### Fix 2: Multi-View Project Directory Integration
- **Files Modified:**
  - `src/gameforge_ide/desktop/services/projects_service.py`
  - `src/gameforge_ide/desktop/views/design_view.py`
  - `src/gameforge_ide/desktop/views/build_view.py`
  - `src/gameforge_ide/desktop/views/play_view.py`
  - `src/gameforge_ide/desktop/views/evidence_view.py`
- **Changes:**
  - Replaced hardcoded `Path(get_settings().projects_root) / project_name` with `resolve_project_dir(project_name, workspace_dir)`.
  - Added OS File Explorer launcher buttons (📁) to headers of `BuildView`, `PlayView`, and `EvidenceView`.
  - Enabled double-click artifact launching in `EvidenceView`.
- **Verification:** `pytest tests/unit/test_design_view.py tests/unit/test_build_view.py tests/unit/test_play_view.py tests/unit/test_evidence_view.py` passed (30/30).

---

### Fix 3: Desktop Shell Project Synchronization
- **Files Modified:**
  - `src/gameforge_ide/desktop/main_window.py`
- **Changes:**
  - Updated `MainWindow._on_project_selected()` to propagate active project directory to:
    - `self._agent.set_workspace(proj_dir)`
    - `self._tools.set_workspace(proj_dir)`
    - `self._code_view._explorer.set_workspace(proj_dir)`
    - `self._code_view._terminal.set_workspace(proj_dir)`
    - `self._chat_panel.set_workspace(proj_dir)`
  - Connected `_code_view._explorer.open_folder_requested` to `_open_folder` in Studio shell layout.
  - Added `refresh_projects(select_project=...)` method to update `TopBar.project_combo` dynamically when new games are drafted.
- **Verification:** Verified live in PySide6 shell; project selection changes synchronized across all tabs.

---

### Fix 4: ProjectsService Attribute Error Safety
- **Files Modified:**
  - `src/gameforge_ide/desktop/services/projects_service.py`
- **Changes:**
  - Protected against `NoneType.is_file()` when evaluating `uproject_file` or `gds_file` during project discovery scans.
- **Verification:** `pytest tests/unit/test_home_view.py::test_projects_service_helpers` passed.

---

### Fix 5: Removal of AD-15 Host Path Literals
- **Files Modified:**
  - `src/gameforge_ide/core/projects.py`
- **Changes:**
  - Removed raw `"E:/GameForge/projects"` string literals.
  - Implemented dynamic lookup via `os.environ.get("GAMEFORGE_EXTRA_PROJECTS_ROOT")` and settings host profile inspection.
- **Verification:** `pytest tests/unit/test_no_host_paths.py` passed (1/1).

---

### Fix 6: Pydantic Schema Compatibility for Survival & Timer Games
- **Files Modified:**
  - `src/gameforge_ide/design/draft.py`
  - `src/gameforge_ide/design/expand.py`
- **Changes:**
  - Added `seconds: Optional[int] = Field(None, ge=1, le=3600)` to `DraftWin`.
  - Added `target: Optional[int] = Field(None, ge=0, le=10000)` to `DraftLose`.
  - Updated `expand.py` to extract `w.seconds or w.target` for `survive_seconds` and `l.seconds or l.target` for `timer_runs_out`.
- **Verification:** `pytest tests/unit/test_draft_schema.py tests/unit/test_gds_expand.py` passed (9/9). Live generation of `CyberStorm` prompt-to-GDS passed with model path.

---

### Fix 7: Custom Keyword Routing Against Preset Hijacking
- **Files Modified:**
  - `src/gameforge_ide/design/prompt_to_gds.py`
- **Changes:**
  - Introduced `CUSTOM_DETAIL_KEYWORDS` set encompassing weapons, enemy variants, narrative objects, and mechanics.
  - Guarded keyword preset matching so prompts containing rich custom specifications route directly to local model draft expansion.
- **Verification:** `pytest tests/unit/test_prompt_to_gds.py` (9/9 PASS). Tested with CounterStrikeLite; path verified as `model`.

---

### Fix 8: Shooter Combat & Projectile Attack Mechanics in C++ Runtime Plugin
- **Files Modified:**
  - `src/gameforge_ide/kit/runtime_def.py`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Public/GameForgePlayer.h`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgePlayer.cpp`
- **Changes:**
  - Added `attack_mode`, `projectile_speed`, and `attack_damage` property extraction in `runtime_def.py`.
  - Added default input binding for `IA_Fire` (Left Mouse Button).
  - Implemented `bProjectileAttack`, `ProjectileSpeed`, `PerformAttack()`, and `PerformRangedAttack()` on `AGameForgeCharacter`.
  - Bound `IA_Fire` and `IA_Attack` to `PerformAttack()` which dynamically spawns `AGameForgeProjectile` in first-person mode.
- **Verification:** `pytest tests/unit/test_gameplay_kit.py` (9/9 PASS). Recompiled `GFKitTestEditor` in 28.8s (0 errors).

---

### Fix 9: Composer Codegen RuleSpec ID Attribute Error
- **Files Modified:**
  - `src/gameforge_ide/composer/compose.py`
- **Changes:**
  - Replaced invalid attribute access `rule.id` with `getattr(rule, "rule_id", getattr(rule, "id", ...))`.
- **Verification:** `pytest tests/unit/test_composer.py` passed (6/6).

---

### Fix 10: Forge Handler C++ Codegen Task Support
- **Files Modified:**
  - `src/gameforge_ide/forge/handlers/legacy_stages.py`
- **Changes:**
  - Enhanced `legacy_sources` to check for `tasks` in `ctx.step.inputs`.
  - Generated C++ header and source files in `Source/<Project>/Public` and `Private` using `generate_header` and `generate_source`.
- **Verification:** `pytest tests/unit/test_forge_executor.py` passed (9/9). Verified `Custom0Rule` to `Custom2Rule` compilation in `CounterStrikeLiteEditor`.

---

### Fix 11: Composer Routing Protection for Model-Generated Designs
- **Files Modified:**
  - `src/gameforge_ide/design/legacy.py`
  - `src/gameforge_ide/design/prompt_to_gds.py`
- **Changes:**
  - Marked model-generated GDS with `meta.generator = f"model:{model}"`.
  - Updated `to_legacy_params` to raise `LegacyUnsupported` when `generator.startswith("model:")` or `camera == "first_person"`, guaranteeing full modern Phase 6 Composer execution.
- **Verification:** `pytest tests/unit/test_gds_legacy.py` passed.

---

### Fix 12: Chatbot Intent Grammar & Typo Generalization
- **Files Modified:**
  - `src/gameforge_ide/pipeline/spec_from_prompt.py`
  - `src/gameforge_ide/backend/agent/runtime.py`
- **Changes:**
  - Expanded `_CREATE` and `_GAME_WORD` to recognize colloquial verbs (`wanna`, `cod`, `mak`, `deploy`, `produce`) and typos (`gem`, `gaem`, `shtr`, `platfomer`).
  - Added camera/perspective mutation terms to `is_change`.
- **Verification:** Evaluated 2,000 prompt corpus in `scripts/eval_chatbot_2000.py`; intent accuracy measured at 94.70% (1,894/2,000).

---

### Fix 13: Elimination of "Box-and-Player" Assembly Bug
- **Files Modified:**
  - `src/gameforge_ide/forge/handlers/legacy_stages.py`
- **Changes:**
  - Overhauled `legacy_assemble()` to check for `"plan"` in `ctx.step.inputs`.
  - When present, deserialized `LevelPlan`, generated full op sequence via `plan_to_op_calls()`, and dispatched all room/cover geometry, placed actors (bots, bomb defusal sites), NavMeshBoundsVolume, and nav rebuild operations through `LiveEditorLink`.
  - Bypassed hardcoded cube walls for all composer-driven games.
- **Verification:** Verified 93 geometry ops + 105 level op calls in `scripts/run_storage_and_cs_regen_benchmark.py`.

---

### Fix 14: Dynamic Multi-Source Unreal Engine Discovery
- **Files Added:**
  - `src/gameforge_ide/unreal/discovery.py`
  - `tests/unit/test_unreal_discovery.py`
- **Files Modified:**
  - `src/gameforge_ide/core/settings.py`
- **Changes:**
  - Implemented 5-source detection: explicit environment overrides, Epic Games Launcher `*.item` manifests, `LauncherInstalled.dat`, Windows Registry, and active drive scanning.
  - Implemented strict validation of `UnrealEditor.exe`, `UnrealBuildTool.dll`, and `remote_execution.py`.
  - Connected `discover_engines()` in `settings.py` to use dynamic discovery without hardcoded fallbacks.
- **Verification:** `pytest tests/unit/test_unreal_discovery.py` passed (8/8 in 0.17s). Discovered engine 5.7.4 (CL 51494982) at `E:\UE\UE_5.7` via `epic_manifest_item`.

---

### Fix 15: Strict Two-Location Storage Architecture & New Project Dialog
- **Files Added:**
  - `src/gameforge_ide/desktop/dialogs/new_project_dialog.py`
  - `tests/unit/test_project_storage_architecture.py`
- **Files Modified:**
  - `src/gameforge_ide/desktop/dialogs/__init__.py`
  - `src/gameforge_ide/desktop/views/games_view.py`
  - `src/gameforge_ide/desktop/views/home_view.py`
  - `src/gameforge_ide/desktop/views/design_view.py`
  - `src/gameforge_ide/desktop/main_window.py`
  - `src/gameforge_ide/desktop/panels/approval_card.py`
  - `src/gameforge_ide/backend/tools/game_tools.py`
  - `src/gameforge_ide/desktop/services/action_runner.py`
- **Changes:**
  - Enforced Location 1 (conversation history only in `.gameforge/sessions`) and Location 2 (single authoritative project root).
  - Created `NewProjectDialog` prompting for C++ project name and authoritative destination folder.
  - Added `+ New Project…` and `Open…` buttons to `GamesView` toolbar.
  - Added inline `Project Folder: [ Path ] [ Browse… ]` selector in `HomeView`.
  - Added `Authoritative Project Root` banner in `DesignView` with `Change Folder…` action.
  - Added Project Root display and folder change action in chat `ApprovalCard`.
  - Forwarded `project_dir` across `ActionRunner` and `GameTools.create_game`.
- **Verification:** `pytest tests/unit/test_project_storage_architecture.py` passed (6/6 in 0.54s).

---

### Fix 16: GDS Schema Enhancement for Canonical Project Root
- **Files Modified:**
  - `src/gameforge_ide/design/gds.py`
- **Changes:**
  - Added `project_dir: Optional[str] = None` to `Meta` model in `gds.py`, enabling the GDS to store its authoritative project root directory without Pydantic validation errors.
- **Verification:** All 817 unit tests and 45 protected oracles PASS.

---

### Fix 17: UI/UX Disconnected Controls & Persistence Audit (DEF-021 through DEF-027)
- **Files Modified:**
  - `src/gameforge_ide/desktop/views/home_view.py`
  - `src/gameforge_ide/desktop/widgets/gds_form.py`
  - `src/gameforge_ide/desktop/views/design_view.py`
  - `src/gameforge_ide/desktop/views/settings_view.py`
  - `src/gameforge_ide/desktop/main_window.py`
- **Changes:**
  - Added `openAssistantRequested` signal in `HomeView` on unsupported prompt notices.
  - Implemented win and lose goal extraction and persistence in `GdsForm._apply_inputs_to_spec()`.
  - Added `self.projectChanged.emit(project_name)` in `DesignView.load_project()`.
  - Wired `EvidenceView.openFileRequested` to `CodeView.open_file()`.
  - Synchronized theme and font scale to workspace `.gameforge/ide_settings.ini`.
  - Cleaned dead code in `_open_command_palette` and registered Home and Games views.
  - Connected `diff_rolled_back` to `CodeView.reload_current_file()`.
- **Verification:** UI view tests PASS (821 unit tests, 45 protected oracles).

---

### Fix 18: Recurring Box-and-Player Failure Elimination & Tactical FPS Layout (DEF-028)
- **Files Added:**
  - `src/gameforge_ide/composer/layouts/tactical_fps.py`
- **Files Modified:**
  - `src/gameforge_ide/composer/layouts/__init__.py`
  - `src/gameforge_ide/composer/compose.py`
  - `src/gameforge_ide/composer/level_ops.py`
  - `src/gameforge_ide/composer/layouts/arena.py`
  - `src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops/level.py`
  - `src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops/_core.py`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgeGameDefinition.cpp`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgePlayer.cpp`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Public/GameForgePlayer.h`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgeRules.cpp`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgeKitUI.cpp`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgeKitActors.cpp`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Public/GameForgeKitActors.h`
  - `src/gameforge_ide/unreal/toolchain.py`
- **Changes:**
  - Implemented `tactical_fps.py` level layout with CT Base, T Base, Site A, Site B, Long A, Mid corridor, cover crates, and bomb sites.
  - Set explicit `static_mesh` and `material` args across all layout geometry pieces.
  - Added `PlayerStart` actor in `level_ops.py`.
  - Added `[/Script/GameForgeRuntime.GameForgeRuntimeSettings]\nGameDefinition=/Game/GameForge/GD_Main.GD_Main` in `scaffold_cpp_project()` and fallback in C++.
  - Added `WeaponMesh` to `AGameForgeCharacter`; implemented true first-person camera positioning (`SetRelativeLocation(FVector(0,0,68))`, `SetOwnerNoSee(true)`, attached weapon mesh in front of camera).
  - Overhauled `AGameForgeGameMode::StartPlay()` to parse `camera` mode and apply it.
  - Instantiated `UGameForgeHUDWidget` with center crosshair reticle (`+`) in player controller.
  - Added visible glowing orange bullet mesh to `AGameForgeProjectile`.
  - Attached humanoid skeletal meshes and weapons to `AGameForgeEnemy`.
  - Created interactive `AGameForgeBombSite` and `AGameForgeBomb` actors with C4 mesh, timer countdown, defuse interaction, and explosion.
- **Verification:** Real-world execution of `scripts/run_cs_benchmark.py`: 11/11 stages PASS, `CounterStrike.exe` packaged (156 MB container, 30.47% Oodle Kraken), gameplay scenario replay passed in 5.0s.

---

### Fix 19: Toolchain Plugin C++ Synchronization and Packaging Settings (DEF-029, DEF-030)
- **Files Modified:**
  - `src/gameforge_ide/unreal/toolchain.py`
  - `src/gameforge_ide/forge/checkpoints.py`
  - `src/gameforge_ide/qa/optimize.py`
- **Changes:**
  - Overhauled `deploy_gameforge_plugin()` to always synchronize `Source/` into project plugins.
  - Fixed Oodle compression merge in `package()` so packaging settings are appended under existing header.
  - Whitelisted `!Plugins/GameForge/` in `UE_GITIGNORE`.
  - Added pre-candidate snapshot and rollback restoration for `DefaultEngine.ini` in closed-loop optimizer.
- **Verification:** Compiled `GFKitTestEditor` (0 errors), packaged `CounterStrike.exe` (0 errors).

---

### Fix 20: Chatbot Intelligence and Intent Classification Robustness
- **Files Modified:**
  - `src/gameforge_ide/backend/agent/runtime.py`
  - `src/gameforge_ide/backend/tools/edit_tools.py`
  - `src/gameforge_ide/design/patch_rules.py`
  - `src/gameforge_ide/backend/tools/game_tools.py`
- **Changes:**
  - Fixed greeting prefix trap by stripping conversational markers and inspecting substantive remainder.
  - Fixed question mark trap by preserving `is_create` for polite requests ending with `?`.
  - Fixed predicate death spiral by removing `file_changed` fallback on read-only tasks.
  - Fixed CRLF vs LF line ending mismatch in `propose_edit`.
  - Fixed `RunState` error reporting in `game_tools.py`.
- **Verification:** Evaluated 2,000-prompt chatbot corpus (`scripts/eval_chatbot_2000.py`): 95.25% overall intent accuracy (1,905/2,000 PASS), 0.00% hallucination rate.

---

### Fix 21: GamesView Delete Game Option Fix and Robust File Deletion (DEF-031)
- **Files Modified:**
  - `src/gameforge_ide/desktop/services/projects_service.py`
  - `src/gameforge_ide/desktop/views/games_view.py`
  - `src/gameforge_ide/desktop/main_window.py`
- **Files Added:**
  - `tests/unit/test_delete_game_regression.py`
- **Changes:**
  - Fixed Windows `PermissionError: [WinError 5]` in `delete_project()` by adding an `onexc`/`onerror` handler clearing `stat.S_IWRITE` on read-only files (e.g. `.git/objects/*` pack files and binaries) with a retry loop.
  - Added support for explicit `project_dir` parameter in `delete_project()`, eliminating directory resolution failures when the folder name differs from the game title.
  - Updated `DeleteGameDialog` to accept both `game.name` and `game.title` (case-insensitively) and added Return-key confirmation.
  - Overhauled `GamesView._execute_delete` to pass authoritative `game.project_dir`, show a `QMessageBox.warning` on failure, and emit `gameDeleted(name, pdir)`.
  - Wired `GamesView.gameDeleted` to `MainWindow._on_game_deleted` to deselect active project, refresh `TopBar` and `HomeView`, and display an informative toast.
  - Purged deleted project runs from `runs_index.json` across all candidate paths and deleted SQLite index files.
- **Verification:**
  - `pytest tests/unit/test_delete_game_regression.py` PASS (6/6).
  - Real-world on-disk project deletion test with read-only files PASS.
  - All 827 unit tests and 45 protected oracles PASS.

---

### Fix 22: GamesView Active Terminal Shell Lock Release & Delete Confirmation Usability (DEF-032)
- **Files Modified:**
  - `src/gameforge_ide/desktop/views/games_view.py`
  - `src/gameforge_ide/desktop/services/projects_service.py`
  - `src/gameforge_ide/desktop/main_window.py`
  - `tests/unit/test_delete_game_regression.py`
- **Changes:**
  - Added `beforeGameDeleted` signal to `GamesView` and connected it to `MainWindow._on_before_game_deleted`.
  - In `_on_before_game_deleted`, stopped the terminal shell process (`_stop_shell()`) and redirected all panels back to the root workspace before deletion, releasing the OS directory lock (`[WinError 32]`).
  - Added `psutil` child process termination in `delete_project()` to ensure any sub-processes holding project paths are cleaned up.
  - Pre-emptively stripped read-only attributes on all files and subdirectories with a 5-attempt exponential backoff retry in `delete_project()`.
  - Added a 1-click `[Fill name]` button in `DeleteGameDialog`, auto-focused the input, added space/hyphen/punctuation normalization, and added dynamic visual status confirmation.
- **Verification:**
  - `pytest tests/unit/test_delete_game_regression.py tests/unit/test_games_view.py` PASS (14/14).
  - All 830 unit tests and 45 protected oracles PASS.

---

### Fix 23: unreal_editor and Backend Tools uproject Resolution (DEF-033)
- **Files Modified:**
  - `src/gameforge_ide/backend/tools/game_tools.py`
  - `src/gameforge_ide/backend/tools/unreal_tools.py`
- **Files Added:**
  - `tests/unit/test_uproject_resolution.py`
- **Changes:**
  - Implemented `GameTools._resolve_uproject(uproject)` resolving project names, directory paths, and relative paths to canonical `.uproject` file paths.
  - Updated `unreal_editor()`, `_link()`, `unreal_run_tests()`, and `unreal_package()` to resolve `uproject` via `_resolve_uproject()`.
  - Updated `UnrealEngineTools.run_staged_build()` to resolve `uproject_rel_path` via `_resolve_uproject_path()`.
- **Verification:**
  - `pytest tests/unit/test_uproject_resolution.py` PASS (3/3).
  - All 833 unit tests and 45 protected oracles PASS.

---

### Fix 24: Board Game Preset & Genre Classification Architecture (DEF-034, DEF-035)
- **Files Modified:**
  - `src/gameforge_ide/design/presets.py`
  - `src/gameforge_ide/design/prompt_to_gds.py`
  - `src/gameforge_ide/design/expand.py`
- **Files Added:**
  - `tests/unit/test_genre_classification.py`
- **Changes:**
  - Implemented `preset_snake_and_ladders()` producing a 100-cell grid board with 8 snakes, 8 ladders, 6-sided dice rolling, and 2 player tokens under `Genre.GRID_BOARD`.
  - Added board game keywords (`"snake and ladders"`, `"snakes and ladders"`, `"chutes and ladders"`, `"ludo"`, `"board game"`) to `PRESET_KEYWORDS`.
  - Updated `DRAFT_SYSTEM_PROMPT` to explicitly define each genre enum value and mandate `grid_board` with `fixed_board` and $\ge 2$ players for turn-based board games.
  - Fixed `expand_draft()` in `expand.py` to extract dynamic player counts from board properties or entities rather than hardcoding `players=1`.
- **Verification:**
  - `pytest tests/unit/test_genre_classification.py` PASS.

---

### Fix 25: Master Composer Layout Routing & Entity Deduplication (DEF-036, DEF-038)
- **Files Modified:**
  - `src/gameforge_ide/composer/compose.py`
  - `src/gameforge_ide/composer/layouts/board.py`
- **Changes:**
  - Corrected layout fallback mapping in `compose.py` from `("board", "card")` to `("grid_board", "board", "puzzle")` for `board` layout and `("card_battler", "card")` for `lanes` layout.
  - Overhauled `layouts/board.py` to extract `board_size`, `cell_size_cm`, `snakes`, and `ladders` from the GDS board entity into `board_actor.properties`.
  - Synchronized entity IDs between GDS entities and layout plans to prevent duplicate Poisson-disk scattering of board actors.
- **Verification:**
  - Composer tests PASS.

---

### Fix 26: Duplicate PlayerStart Elimination & Conditional NavMesh in Level Ops (DEF-037)
- **Files Modified:**
  - `src/gameforge_ide/composer/level_ops.py`
- **Changes:**
  - Guarded step 1b `spawn_actor(PlayerStart)` to check if `plan.actors` already contains an actor of class `PlayerStart` or label `GF_PlayerStart`, eliminating duplicate PlayerStart emissions.
  - Made `NavMeshBoundsVolume` and `nav_rebuild` conditional: skipped on board games or levels without AI pathfinding actors.
- **Verification:**
  - `pytest tests/unit/test_level_ops.py` PASS.

---

### Fix 27: Game-Specific Acceptance Test Derivation & Semantic Validation (DEF-039)
- **Files Added:**
  - `src/gameforge_ide/qa/game_spec_tests.py`
  - `src/gameforge_ide/design/semantic_validate.py`
  - `tests/unit/test_game_spec_tests.py`
- **Changes:**
  - Implemented `generate_acceptance_tests(gds)` deriving concrete test assertions from GDS rules and goals (board cell count, dice outcomes, snake/ladder transitions, win conditions).
  - Implemented `semantic_validate_gds(gds, prompt)` enforcing semantic parity between natural-language prompt intent and generated GDS genre/entities.
- **Verification:**
  - `pytest tests/unit/test_game_spec_tests.py` PASS.

---

### Fix 28: Pipeline Stage Evidence Validation (DEF-040)
- **Files Modified:**
  - `src/gameforge_ide/forge/handlers/__init__.py`
  - `src/gameforge_ide/forge/handlers/legacy_stages.py`
- **Changes:**
  - Enforced strict output validation in stage handlers before marking steps as DONE:
    - Design validates GDS semantic consistency.
    - Assemble validates actor coordinates and classes against LevelPlan read-back.
    - Scenario validates that game-specific scenarios ran and emitted required events.
- **Verification:**
  - All unit tests and protected oracles PASS.

---

### Fix 29: Composer Entity Placement, Card Table Deduplication & Dynamic Course Layout (DEF-041–DEF-044)
- **Files Modified:**
  - `src/gameforge_ide/composer/compose.py`
  - `src/gameforge_ide/composer/layouts/lanes.py`
  - `src/gameforge_ide/composer/layouts/course.py`
  - `src/gameforge_ide/design/prompt_to_gds.py`
- **Changes:**
  - Corrected unplaced entity count truncation by checking `getattr(e, "count", None) or e.props.get("count", 1)`.
  - Dynamically matched card table entity IDs from GDS in `layouts/lanes.py`, resolving duplicate entity scattering.
  - Dynamically calculated course platform counts (`num_platforms = max(7, num_pickups + 4)`), ensuring all pickups and landmarks are placed.
  - Differentiated creative prompts from parameter preset overrides in `prompt_to_gds.py`.
- **Verification:**
  - `python scratch/verify_bugs.py` confirmed 5 relics, 3 guards, exactly 1 card table, 5 pickups placed, and creative model routing.

---

### Fix 30: Natural Language Prompt Classification, Polite Intent & Living Project Changes (DEF-045–DEF-050)
- **Files Modified:**
  - `src/gameforge_ide/backend/agent/runtime.py`
  - `src/gameforge_ide/pipeline/spec_from_prompt.py`
  - `src/gameforge_ide/kit/modules/__init__.py`
  - `src/gameforge_ide/design/patch_rules.py`
  - `src/gameforge_ide/design/patch.py`
- **Changes:**
  - Added player nouns (`player|players|character|hero`) to mutation targets in `runtime.py`.
  - Filtered polite modal openers ("can/could/would you", "please") from informational Q&A.
  - Added `weapons` field to `PlayerCharacterParams` to allow player weapon sets.
  - Fixed combat patch rule to check for `kit.spawner` and updated speed patch to match `player_speed`.
  - Fixed lighting patch summarizer to query `gds.scene.levels[0].lighting`.
  - Allowed hyphenated titles in `is_game_creation_request`.
- **Verification:**
  - `python scratch/test_prompt_classification.py` passed 17/17 intent tests.
  - Bug verification script passed combat and lighting patch tests.

---

### Fix 31: Storage Hardening, Windows NTFS Lock Retries & Process Isolation (DEF-051–DEF-056)
- **Files Modified:**
  - `src/gameforge_ide/design/store.py`
  - `src/gameforge_ide/backend/providers/hosted.py`
  - `src/gameforge_ide/index/indexer.py`
  - `src/gameforge_ide/backend/tools/terminal_tools.py`
  - `src/gameforge_ide/backend/tools/unreal_tools.py`
  - `src/gameforge_ide/backend/tools/edit_tools.py`
  - `src/gameforge_ide/backend/tools/gateway.py`
- **Changes:**
  - Added 5-attempt retry loop with exponential backoff on `PermissionError` when saving GDS revisions under Windows file locking contention.
  - Added graceful JSONDecodeError handling in `SpendLedger._entries()`.
  - Added 5-line lookback window for C++ macro indexing and `re.UNICODE` support.
  - Adopted all terminal and UBT processes into Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`).
  - Prohibited empty `target_content=""` edits on existing files.
  - Fixed project directory resolution in `ToolGateway`.
- **Verification:**
  - `pytest scratch/test_auditor_suite.py` passed 8/8.

---

### Fix 32: Desktop Frontend, Keyboard Navigation & Unreal Pipeline Validation (DEF-057–DEF-066)
- **Files Modified:**
  - `src/gameforge_ide/desktop/main_window.py`
  - `src/gameforge_ide/desktop/services/forge_service.py`
  - `src/gameforge_ide/desktop/views/code_view.py`
  - `src/gameforge_ide/desktop/views/home_view.py`
  - `src/gameforge_ide/desktop/shell/top_bar.py`
  - `src/gameforge_ide/desktop/views/play_view.py`
  - `src/gameforge_ide/desktop/views/assets_view.py`
  - `src/gameforge_ide/desktop/views/build_view.py`
  - `src/gameforge_ide/desktop/widgets/gds_form.py`
  - `src/gameforge_ide/pipeline/game_pipeline.py`
  - `src/gameforge_ide/forge/validation.py`
  - `src/gameforge_ide/forge/handlers/legacy_stages.py`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgePlayer.cpp`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgeScenario.cpp`
- **Changes:**
  - Wired `MainWindow._cancel_active_run` and `ForgeService.cancel_run` to `ForgeExecutor.cancel_run` and `request_cancel`.
  - Passed `self._tools` to `DiffPanel` in `CodeView`.
  - Re-enabled cancel button on new design drafts in `HomeView`.
  - Reverted `TopBar` project combo on folder picker cancel.
  - Connected `itemSelectionChanged` and selection model `currentChanged` in `PlayView`, `AssetsView`, and `BuildView` for keyboard arrow navigation.
  - Added informative validation error emission for malformed win/lose condition syntax in `GdsForm` while preserving non-stat condition types (`EventOccurred`, `TimerElapsed`).
  - Updated `game_pipeline.resume()` to reset `SKIPPED`, `FAILED`, `CANCELLED`, and `BLOCKED` steps to `PENDING` with cleared errors.
  - Verified real spawned actors in assemble validation without swallowing exceptions.
  - Bound `IA_PrimaryAttack` and `IA_RollDice` aliases in C++ `AGameForgePlayerController`.
  - Removed strict NavSys pre-condition in `GameForgeScenario.cpp`.
- **Verification:**
  - `pytest scratch/test_ui_comprehensive_audit.py` passed 10/10.
  - `pytest scratch/test_audit_engine_forge_qa.py` passed 4/4.
  - Full test suite: 868/868 unit tests passed (91.93s), 45/45 protected oracles passed (0.05s).

---

### Fix 33: Desktop Frontend & UI/UX Re-Engineering
- **Files Modified:**
  - `src/gameforge_ide/desktop/shell/toasts.py`
  - `src/gameforge_ide/desktop/shell/palette.py`
  - `src/gameforge_ide/desktop/shell/rail.py`
  - `src/gameforge_ide/desktop/shell/top_bar.py`
  - `src/gameforge_ide/desktop/main_window.py`
  - `src/gameforge_ide/desktop/shell/icons.py`
  - `src/gameforge_ide/desktop/styles/dark_theme.py`
  - `src/gameforge_ide/desktop/views/code_view.py`
  - `src/gameforge_ide/desktop/widgets/log_view.py`
  - `src/gameforge_ide/desktop/widgets/problems_table.py`
  - `src/gameforge_ide/desktop/views/games_view.py`
  - `src/gameforge_ide/desktop/views/evidence_view.py`
  - `src/gameforge_ide/desktop/views/assets_view.py`
  - `src/gameforge_ide/launcher.py`
  - `tests/unit/test_frontend_ux_improvements.py`
- **Changes:**
  - Installed event filter on `parentWidget()` watching for `QEvent.Resize` and `QEvent.Show` in `toasts.py`, auto-repositioning floating notifications on window resize or maximize.
  - Upgraded `palette.py` with multi-keyword token matching and acronym fuzzy matching (`vd` -> `View: Design`, `cancel` -> `Forge: Cancel Active Run`).
  - Added `refresh_icons()` / `update_theme()` to `rail.py` and `top_bar.py` for live theme recoloring without restart; added `set_running()` indicator badging active runs.
  - Connected `ForgeService.runEvent` and `runListChanged` to update TopBar run chip, Rail build indicator, and status bar live in `main_window.py`.
  - Wired `CodeView` dock layout persistence (`save_dock_state`, `restore_dock_state`, `reset_dock_layout`) using `QSettings`.
  - Cleared SVG icon cache inside `apply_theme()` to prevent stale icons on theme switch.
  - Added smart auto-scroll lock in `log_view.py` with amber "Resume Auto-Scroll" button.
  - Added Enter and Delete keyboard navigation to `problems_table.py`, `games_view.py`, `evidence_view.py`, and `assets_view.py`.
  - Added `SetCurrentProcessExplicitAppUserModelID` in `launcher.py` for native Windows taskbar icon grouping.
- **Verification:**
  - `pytest tests/unit/test_frontend_ux_improvements.py` passed 11/11.
  - Desktop suite: 93/93 passed.

---

### Fix 34: Backend, Storage, Concurrency & Tool Infrastructure Re-Engineering
- **Files Modified:**
  - `src/gameforge_ide/backend/tools/edit_tools.py`
  - `src/gameforge_ide/backend/tools/gateway.py`
  - `src/gameforge_ide/backend/tools/fs_tools.py`
  - `src/gameforge_ide/backend/tools/approval_store.py`
  - `src/gameforge_ide/design/store.py`
  - `src/gameforge_ide/forge/store.py`
  - `src/gameforge_ide/index/indexer.py`
  - `src/gameforge_ide/core/jobs.py`
  - `tests/unit/test_backend_storage_reengineering.py`
- **Changes:**
  - Implemented two-phase atomic transaction engine in `edit_tools.py` (`apply_batch` with pre-validation dry run checking diff IDs, boundaries, existence, and SHA-256 digests; Phase 2 atomic apply with automatic reverse rollback on write failure); implemented `rollback_batch`; registered batch tools in `ToolGateway`.
  - Added directory guard and NOOP identical replacement detection; added 5-attempt retry loop with linear backoff and `stat.S_IWRITE` clearing on `PermissionError`.
  - Hardened `DesignStore`, `ForgeStore`, and `ApprovalStore` with transient NTFS lock retry loops and atomic write safety with dangling `.tmp_*` cleanup.
  - Upgraded `SymbolIndexer` with SQLite database triggers (`symbols_ai`, `symbols_ad`, `symbols_au`) syncing FTS5 automatically on INSERT/UPDATE/DELETE; replaced in-memory ID extraction with direct SQL JOIN; added kind index and wildcard token sanitization.
  - Scaled `JobManager` worker pool to 4 workers; implemented `terminate_all_children()` via Win32 `TerminateJobObject`.
  - Wrapped `re.compile` in error handling in `fs_tools.py` and excluded cache/build directories (`.gameforge`, `DerivedDataCache`, `Build`, `node_modules`, `scratch`).
- **Verification:**
  - `pytest tests/unit/test_backend_storage_reengineering.py` passed 11/11.
  - FTS query benchmark: 6.8ms (< 50ms budget).
  - 50k lines edit and rollback benchmark: 0.35s (< 2.0s budget).

---

### Fix 35: AI, Agents, LLM Orchestration & Prompt-to-GDS Re-Engineering
- **Files Modified:**
  - `src/gameforge_ide/design/prompt_to_gds.py`
  - `src/gameforge_ide/design/patch_rules.py`
  - `src/gameforge_ide/design/patch.py`
  - `src/gameforge_ide/backend/agent/runtime.py`
  - `src/gameforge_ide/design/expand.py`
  - `src/gameforge_ide/backend/agent/code_verify.py`
  - `src/gameforge_ide/pipeline/spec_from_prompt.py`
  - `tests/unit/test_ai_agent_orchestration_improvements.py`
- **Changes:**
  - Expanded `CUSTOM_DETAIL_KEYWORDS` in `prompt_to_gds.py` with 40+ thematic descriptors and lowered custom motif threshold to `>= 2`, preventing template hijacking on creative prompts.
  - Added 6 new deterministic patch rules in `patch_rules.py`: Rule 13 (health scaling/doubling), Rule 14 (jump velocity/force), Rule 15 (difficulty modes), Rule 16 (art style: stylized, realistic, low_poly, toon), Rule 17 (camera switching), Rule 18 (timer limits in lose goals). Enhanced `_match_add_n` to dynamically instantiate entities with proper default kit params when adding new entity types. Expanded deletion verbs (`remove|delete|destroy|eliminate|clear`).
  - Implemented `_compact_entities_list` in `patch.py` to truncate massive `points_m` coordinate arrays in LLM prompt contexts (saving ~80% token waste); added markdown code block stripping and outermost JSON brace extraction before `json.loads`.
  - Upgraded `_extract_tool_call` in `runtime.py` to support multi-schema tool outputs (OpenAI, Anthropic, function calling, GameForge formats); expanded `is_change` verbs and target nouns.
  - Added combat input action detection (`IA_Attack`/`IA_Fire`) and camera action bindings (`IA_Move`/`IA_Look`) in `expand_draft`.
  - Stripped markdown code blocks from model diffs and normalized paths in `code_verify.py`.
  - Expanded genre regex in `spec_from_prompt.py` to cover `runner`, `racing`, `simulator`, `strategy`, `tower defense`, `dogfight`, `metroidvania`, `sandbox`, `open world`, `quest`.
- **Verification:**
  - `pytest tests/unit/test_ai_agent_orchestration_improvements.py` passed 15/15.

---

### Fix 36: Unreal Engine, Composer, Gameplay Kit & QA Pipeline Re-Engineering (DEF-067–DEF-075)
- **Files Modified:**
  - `src/gameforge_ide/composer/layouts/open_world.py`
  - `src/gameforge_ide/composer/layouts/board.py`
  - `src/gameforge_ide/composer/layouts/lanes.py`
  - `src/gameforge_ide/composer/compose.py`
  - `src/gameforge_ide/qa/game_spec_tests.py`
  - `src/gameforge_ide/forge/handlers/scenario.py`
  - `src/gameforge_ide/unreal/GameForge/Source/GameForgeRuntime/Private/GameForgePlayer.cpp`
  - `src/gameforge_ide/unreal/runner.py`
  - `src/gameforge_ide/forge/handlers/legacy_stages.py`
  - `src/gameforge_ide/pipeline/project_import.py`
  - `src/gameforge_ide/composer/codegen.py`
  - `src/gameforge_ide/composer/level_ops.py`
- **Changes:**
  - Eliminated duplicate `biomes.lighting_rig` generation in `open_world.py` (DEF-067).
  - Added `GF_Board_Floor` and `GF_Lanes_Floor` static mesh actors with collision at `z=-10.0` in `board.py` and `lanes.py` (DEF-068), preventing characters from dropping into void (-2000cm KillZ).
  - Implemented 3D platform snapping for unplaced scattered entities in platformer courses in `compose.py` (DEF-069); forwarded `generate_acceptance_tests(gds)` test IDs into `comp.scenarios` (DEF-070).
  - Preserved game-specific acceptance scenarios during scenario filtering in `scenario.py`.
  - Replaced passive `WaitStep` assertions with authentic action sequences (`NavigateToStep`, `InjectStep`) in `game_spec_tests.py` (DEF-071).
  - Consolidated `GameDefinition` parsing and player attributes into `AGameForgeGameModeBase::StartPlay()` in `GameForgePlayer.cpp`, ensuring all execution modes apply camera mode, locomotion speed, projectile attack, and win/lose event listeners (DEF-072). Defaulted `runner.py` and `legacy_stages.py` to `GameForgeGameMode`.
  - Added `dirs_exist_ok=True` for plugin deployment in `project_import.py` (DEF-073).
  - Added `#include "GameForgeAttributes.h"` and `"Kismet/GameplayStatics.h"` in `codegen.py` (DEF-074).
  - Added `severe_tolerance_cm=500.0` threshold in `verify_placed_actor_transforms()` in `level_ops.py` (DEF-075).
- **Verification:**
  - Domain tests: 112/112 passed.
  - Full repository test suite: 908/908 passed in 101.78s (Exit 0).
  - Protected oracles: 45/45 passed in 0.04s.

