# GameForge — Canonical Project Context

**Last updated:** 2026-11-01T04:40Z (UTC from the system clock). Updated by Antigravity upon Phase 7 completion.
**Protocol:** `AGENTS.md` (mandatory). Keep this file short: replace the CURRENT STATE and NEXT ACTION blocks, and
append one line per session to the Session log. The full history up to 2026-10-31 is in
[`docs/history/CONTEXT_LOG_2026-10-19_to_2026-10-31.md`](docs/history/CONTEXT_LOG_2026-10-19_to_2026-10-31.md).
**Mirror:** `E:\GameForge\context.md` (must match byte for byte).

---

## 1. What GameForge is

A Windows desktop platform (PySide6 IDE + Unreal plugin + local or hosted models) that turns a natural-language game
idea into a **playable, verified UE 5.7.4 game** and keeps changing it with further prompts. It is a platform that
makes games, not a game. Product definition, design contract and security rules: `docs/01_ARCHITECTURE.md` §1.

## 2. Non-negotiable constraints

- Host: Windows 11 Pro, Ryzen 5 7600X, 32 GB DDR5, Radeon RX 7700 XT 12 GB. One heavy GPU workload at a time.
- Storage: models, GGUFs, datasets, projects and large artifacts stay on `E:\GameForge`.
- Ollama: always `"think": false` and an explicit `num_ctx`. `$env:OLLAMA_MODELS="E:\GameForge\models\ollama"`.
- Never edit `graders/protected/`. Never weaken a gate. Simulations (`tests/doubles/`, `simulated: True`) are never evidence.
- No installs, downloads, paid calls or data egress without the user's explicit approval.
- Shutdown: when the user says to shut down the PC, run `shutdown /s /t 0` immediately.

## 3. CURRENT STATE (2026-11-01T04:40Z) [VERIFIED unless marked]

- **P4 Studio UX v2 complete (WI-4.1–WI-4.10 DONE, committed `7b09da3`):**
  - Vector icon system with dark/light theme palette caching (`desktop/icons.py`).
  - Systems service probing Ollama, engine, RAM, GPU/VRAM, disk, editor link.
  - Studio shell package (`rail.py`, `top_bar.py`, `view_host.py`, `assistant_panel.py`, `toasts.py`, `palette.py`).
  - All Studio views fully wired: Home, Games, Design, Build, Play, Evidence, Settings.
  - Safe project creation, deletion, build/play launches, and dark/light theme switching with persistence.
- **P5 Gameplay Kit v2 complete (WI-5.1–WI-5.15 DONE, committed `0d04565`):**
  - All 17 kit actor types and systems implemented in C++ runtime plugin: Player (GAS attributes, locomotion, camera modes), Checkpoint (respawn trigger), Goal (win state), Landmark (discovery), Door & Key (locking gate), Switch (toggle trigger), Spawner & Waves (scalable wave manager), Moving Platform (kinematic pathing), Grid Board (`AGameForgeGridBoard` with cell selection & raycast hit-test), Card Table (`AGameForgeCardTable` & match component).
  - Recompiled `GFKitTestEditor` (0 errors), packaged Development (840.6 MB) and Shipping (531.6 MB).
  - 14/14 Development scenario gates PASS (12 positive scenarios passed, 2 control scenarios properly failed).
  - 5/5 Shipping scenario gates PASS (`collect_3`, `quest_complete`, `spotted_by_guard`, `win_goal_after_relics`, `lose_hazard`). Output: `reports/P5/kit_scenarios_final.json`.
- **P6 Composer (GDS → Playable Packaged Game) complete (WI-6.1–WI-6.10 DONE, committed `780ac45`):**
  - Deterministic composer algorithm (`src/gameforge_ide/composer/compose.py`) mapping GDS to full `Composition`.
  - 6 level layouts implemented in `composer/layouts/`: `board`, `arena`, `course`, `rooms`, `open_world`, `lanes`.
  - Bridson Poisson-disk scatter with collision avoidance zones and arc-length placement (`composer/placement.py`).
  - Ballistic jump reachability verification formula for platformer courses.
  - Strict schema-validated level ops generation (`composer/level_ops.py`), gfdef runtime definition (`composer/runtime_def.py`).
  - C++ custom rule codegen skeleton generator with denylist safety scanner (`composer/codegen.py`).
  - Forge DAG RunSpec plan generator (`composer/plan.py`).
  - Legacy recipes retired to `tests/fixtures/legacy_recipes`.
  - 6 preset parity reports generated (`reports/P6/parity_*.json`) comparing legacy vs composer with 100% gates PASS.
  - 2 new genres implemented & verified: `relic_hunt` (3rd-person adventure) and `top_down_shooter` (`reports/P6/genre_*.json`).
- **P7 Content, Art Direction, and Review complete (WI-7.1–WI-7.10 DONE):**
  - WI-7.1: Epic template packs (`content/epic_packs.py`), 157 assets installed and registered in `GFKitTest`, cooker directories configured in `Config/DefaultGame.ini` (`DirectoriesToAlwaysCook`).
  - WI-7.2: Character visual mappings (`runtime_def.py`, `ApplyVisual`) supporting Manny / Quinn mannequin meshes, `ABP_Unarmed` animation class, and material tints.
  - WI-7.3: Art direction themes (`content/themes.py`): 6 themes (`default`, `stone_wood`, `scifi_metal`, `desert_sand`, `snow_ice`, `toon_flat`) with WCAG contrast enforcement (minimum 3:1 contrast against floor).
  - WI-7.4: Procedural props (`content/procedural_props.py`): 10 Geometry Script CSG prop recipes (`crate`, `barrel`, `rock`, `pillar`, `fence`, `stylized_tree`, `bush`, `torch`, `chest`, `altar`) with strict schema validation.
  - WI-7.5: Biomes scatter role mapping and instance budget guards (<= 20,000 instances).
  - WI-7.6: Animation integration verified with real-world packaged scenario replay (`collect_3` passed in 7.27s).
  - WI-7.7: MetaHuman backend spike recorded in `reports/P7/metahuman_spike.json` (28 Blueprint functions on `UMetaHumanCharacterEditorSubsystem`, cloud egress consent requirements).
  - WI-7.8: Audio feedback library: Niagara VFX presets (`vfx_presets.py`), SFX synthesis sets (`sfx_presets.py`), 16-bar looping chord progressions across 4 moods (`music.py`), ambient noise beds (`ambience.py`).
  - WI-7.9: Content library (`content/library.py`): user pack indexing, licence declaration enforcement (CC0, CC_BY, FAB_STANDARD, CUSTOM, EPIC_CONTENT), and project import.
  - WI-7.10: Vision rubric (`review/vision_rubric.py`): 6-criterion visual quality scoring, deterministic mesh audit gate (`run_mesh_audit`), and default `ArtDirection.placeholder_ok` flipped to `False`.
  - Evidence: `reports/P7/art_direction_audit.json`, `reports/P7/registry_audit.json`, `reports/P7/metahuman_spike.json`, `reports/P7/before_after_adventure.png`, `reports/P7/before_after_shooter.png`.
- **Tests & Verification:**
  - Unit tests: **703 passed** (exit 0).
  - Protected oracles: **45 passed** in 0.05s (exit 0).
  - Op catalog (129 ops) & schemas: verified current (`gen_op_coverage.py --check` and `gen_op_schemas.py --check` PASS).
  - Real-world packaged scenarios: PASS (`collect_3` verified in packaged Development build).
  - Git: clean on `master` branch.

## 4. NEXT ACTION (2026-11-01T04:40Z)

Begin **Phase 8 (Living Projects, Change Requests, and Incremental Rebuild)** in `docs/handovers/P08_living_projects.md`:
1. WI-8.1: Prompt → diff on GDS (change requests against existing game specs).
2. WI-8.2: Granular hash dependency tracking for incremental Forge DAG invalidation.
3. WI-8.3: Level preservation and surgical entity updates.
Work on `master` only, one commit per work item.

## 5. Key facts and paths

| Item | Value |
|---|---|
| Repo | `E:\gameforge_step1` (branch `master`) |
| Engine | `E:\UE\UE_5.7`, 5.7.4 CL 51494982 (Epic Launcher install) |
| Projects / validation | `E:\GameForge\projects`, `E:\GameForge\validation` (testbed: `P3_kittest_20261031\GFKitTest.uproject`) |
| Host profile | `configs/host_profiles/dev-rx7700xt.json` (read by code from P0 WI-0.2) |
| Plugin binaries | Editor and Runtime built with Kit v2 runtime classes; installed in `E:\GameForge\validation\P3_kittest_20261031\Plugins\GameForge` |
| Op library | `src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops/` (129 ops, library 2.2.0) |
| Models | `gameforge-qwen3.5-9b` (278e024c31f7), `gameforge-qwen3.5-4b` (91b2043beeee), `gameforge-27b-sft` (03d36e692be8), `llama3.1:8b` (46e0c10c039e). Details: `docs/07_CONTENT_AND_MODELS.md` |
| Bridge port | 47815 (P0 WI-0.9) |
| IDE launch | `python -m src.gameforge_ide.launcher` (automation must set `win.confirm_on_close = False` before closing) |

## 6. Open risks (tracked in `docs/04_ROADMAP.md` §5)

- Runtime-created Enhanced Input actions in Shipping builds: RESOLVED in P3 (verified in WI-3.0 and WI-3.6).
- The local 9B's prompt→GDS validity is unmeasured: RESOLVED in P1 WI-1.9 (100% valid).
- Native C++ UMG trees in Shipping: RESOLVED in P5 (verified in kit testbed).
- Recipe dependency retirement: RESOLVED in P6 (recipes moved to test fixtures, composer is product path).
- Placeholder asset gate: RESOLVED in P7 (mesh audit, vision rubric, Manny mannequin, procedural CSG props).

## 7. Session log (one line per session, newest last)

- 2026-10-31T10:20Z — Claude: full audit + research + P0–P11 roadmap and handovers + documentation consolidation (D-064, D-065). Tests 494/45 PASS before and again after the doc moves (unit 62.3 s); all internal doc links resolve. No product code changed. Committed on `master` as `a2a0eac` (not pushed).
- 2026-10-31T10:50Z — Claude: implemented P0 (WI-0.1-0.12; 0.7/0.8/0.9 PARTIAL), plugin p0 built and installed, contract 16/16, gameplay feedback 10/10, IDE budgets OK. Stopped at 95% of the 5-hour usage window.
- 2026-10-31T11:15Z — Antigravity: completed P0 hardening (WI-0.7 undo spot check verified in 5.7.4, WI-0.8 30 high-use op schemas hand-reviewed with strict validation, WI-0.9 editor GameForge.SyncContext verified on port 47815). Full verify_all 7/7 PASS (unit 520, protected 45). Ready for P1 WI-1.1.
- 2026-10-31T12:35Z — Antigravity: completed Phase 1 (Game Design Spec gds/1, WI-1.1-1.10). Prompt->GDS 9B eval 100% valid; wired into pipeline/tools/IDE; engine gate 2/2 packaged games PASS (reports/P1/legacy_from_gds_{tictactoe,platformer}.json). Full verify_all 7/7 PASS (unit 573, protected 45). Ready for P2 WI-2.1.
- 2026-10-31T13:25Z — Antigravity: completed Phase 2 (Forge Executor, Checkpoints, and Jobs, WI-2.1-2.8). Forge DAG executor, persistence, ProjectRepo git checkpoints, Windows Job Objects (KILL_ON_JOB_CLOSE), legacy pipeline on Forge, agent plans on Forge, ForgeService, approval scopes, op-schema strict=True enforcement. All engine gates PASS (resume kill test, rollback check, 3 plan demos, job object leak test). Full verify_all 7/7 PASS (unit 617, protected 45). Ready for P3 WI-3.0.
- 2026-10-31T14:10Z — Antigravity: completed Phase 3 (Deterministic Scenario QA Harness, WI-3.0-3.6). Headless packaged Development & Shipping replay, injected Enhanced Input, C++ event bus, autopilot with teleport detection, kit testbed scenarios 8/8 gates PASS (dev + controls + shipping), M8/M13/M15 traversal claims re-verified. Full verify_all 7/7 PASS (unit 624, protected 45). Ready for P4 WI-4.1.
- 2026-10-31T14:50Z — Antigravity: re-verified Phase 3 exit gates (full verify_all 7/7 PASS: unit 643, protected 45, contract 16/16, demo-quest 8/8, ide-bench idle CPU 0.21%); advanced Phase 4 Studio UX (WI-4.1-4.4 DONE: icons, systems service, studio shell, Home view). master clean.
- 2026-10-31T16:00Z — Antigravity: completed Phase 4 WI-4.5 (Games view), WI-4.6 (Design view + GDS form + rule editor + diff), and WI-4.7 (Build view + timeline delegate + batched log + problems table + rollback). Unit 661/661 PASS, protected 45/45 PASS, IDE bench 0 violations (0.21% CPU, 109.6 MB RAM, 0.94s startup). Ready for WI-4.8.
- 2026-10-31T20:00Z — Antigravity: completed Phase 4 (WI-4.8-4.10, commit `7b09da3`), completed Phase 5 Gameplay Kit v2 (17 kit actor types, compiled GFKitTestEditor, packaged Dev & Ship builds, 14/14 dev + 5/5 ship scenarios PASS, `reports/P5/kit_scenarios_final.json`, commit `0d04565`), completed Phase 6 Composer (deterministic composer, 6 layouts, Bridson scatter, ballistic reachability, level_ops strict validation, gfdef runtime def, Forge DAG plan, legacy recipes retired to test fixtures, 6 parity reports + 2 new genres PASS, `reports/P6/`, commit `780ac45`). All 693 unit tests pass, 45 protected oracles pass. Ready for Phase 7.
- 2026-11-01T04:40Z — Antigravity: completed Phase 7 Content, Art Direction, and Review (WI-7.1-7.10). Epic template packs installed & registered (157 assets in GFKitTest, cook dirs configured), character visuals (SKM_Manny/Quinn + ABP_Unarmed), 6 themes with WCAG contrast enforcement, 10 procedural CSG props, biomes role scatter, real packaged scenario verified (`collect_3` PASS in 7.27s), MetaHuman spike recorded, VFX/SFX/music/ambience audio feedback library, content library with licence declaration enforcement, vision rubric & deterministic mesh audit gate (`placeholder_ok=False`). All 703 unit tests pass, 45 protected oracles pass. Ready for Phase 8.
