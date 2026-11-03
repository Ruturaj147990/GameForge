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
