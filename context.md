# GameForge — Canonical Project Context

**Last updated:** 2026-10-31T16:00Z (UTC from the system clock). Updated by Antigravity upon P4 WI-4.5, WI-4.6, WI-4.7 completion.
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

## 3. CURRENT STATE (2026-10-31T16:00Z) [VERIFIED unless marked]

- **P3 Deterministic Scenario QA Harness complete:** All 7 work items (WI-3.0 through WI-3.6) are DONE.
  - WI-3.0: Spike: Enhanced Input simulation in standalone / packaged builds. Runtime input injection works in cooked Shipping with `DefaultPlayerInputClass` & `DefaultInputComponentClass` in `DefaultInput.ini`. Distance traveled: Dev 1112.34 cm, Ship 1111.86 cm (`reports/P3/spike_inject.json`).
  - WI-3.1: Event bus: `GameForgeEventNames.h` (parity with 42 catalogue events), `UGameForgeEventBus` game instance subsystem writing JSONL sessions in all configurations, `UGameForgeEventLibrary::EmitGameForgeEvent`, retrofitted kit actors (`AGameForgePickup`, `AGameForgeGuard`, `AGameForgeQuestGiver` with `EntityId`). Parity test `test_event_names_parity.py` PASS.
  - WI-3.2: Minimal kit player: `AGameForgeCharacter` (camera boom, camera modes, emits `PlayerSpawned`), `AGameForgePlayerController` (runtime IA/IMC, offscreen projection + hit-test in `SelectAtScreenPosition`), `AGameForgeGameModeBase`.
  - WI-3.3: Autopilot component: `UGameForgeAutopilotComponent` (physically honest movement via injected `IA_Move`, NavMesh walking, teleport detection `Step > MaxSpeed * DeltaTime * 1.5 + 50`, stuck detection).
  - WI-3.4: Scenario subsystem: `UGameForgeScenarioSubsystem` (tickable, headless replay via `-GFScenario=` and `-GFScenarioOut=`, steps state machine, expectation evaluation, screenshots on events, UTF-8 JSON result writer).
  - WI-3.5: Host side: `scenario.py` (schemas, `extra="forbid"`), `manifest.py` (level manifest), `generate.py` (GDS -> scenarios), `runner.py` (`run_packaged`, `run_editor_game`), `forge/handlers/scenario.py` Forge step handler. 6 unit tests PASS.
  - WI-3.6: Kit testbed project: `GFKitTest` scaffolded, level built via ops, packaged Dev & Shipping. 5 dev scenarios (collect_3, quest_complete, spotted_by_guard PASS; controls teleport_cheat & impossible FAIL), 3 ship scenarios PASS (`reports/P3/kit_testbed_scenarios.json`). Traversal claims M8, M13, M15 re-verified with autopilot (`reports/P3/reverify_traversal.json`).
- **P4 Studio UX v2 in progress (WI-4.1–WI-4.7 DONE):**
  - WI-4.1: Vector icon system in `src/gameforge_ide/desktop/icons.py` and `assets/icons/` with theme palette caching (4 passed).
  - WI-4.2: Systems service (`core/systems.py`, `desktop/services/systems_service.py`) probing Ollama, engine, editor link, RAM, disk, hosted models (3 passed).
  - WI-4.3: Studio shell package (`rail.py`, `top_bar.py`, `view_host.py`, `assistant_panel.py`, `toasts.py`, `palette.py`), `main_window._build_studio_shell()`, shortcuts Ctrl+1..8, Ctrl+J, Ctrl+K, legacy shell preserved under `GAMEFORGE_LEGACY_SHELL=1` (5 passed).
  - WI-4.4: Home view (`desktop/views/home_view.py`) with prompt input (Enter=newline, Ctrl+Enter=design), preset chips from `PRESETS`, "Design it →" running `prompt_to_gds` on JobManager, recent games grid joining GDS & runs index, readiness card fed by systems service (`desktop/services/projects_service.py`, `test_home_view.py` 7 passed). Zero hardcoded hex colours.
  - WI-4.5: Games view (`desktop/views/games_view.py`) with grid/list mode toggle, search/genre filtering, sort order, project card delegate, and safe project deletion with link checking (`test_games_view.py` 5 passed).
  - WI-4.6: Design view (`desktop/views/design_view.py`) with GDS pydantic form (`widgets/gds_form.py`), structured rules editor (`widgets/rule_editor.py`), debounced 300ms validation, history diff (`DiffDialog`), raw JSON dialog, and build game trigger (`test_design_view.py` 7 passed).
  - WI-4.7: Build view (`desktop/views/build_view.py`) with timeline `StepRowDelegate` (`widgets/step_row.py`), batched read-only `LogView` (`widgets/log_view.py`), `ProblemsTable` (`widgets/problems_table.py`), artifacts inspector, cancel confirmation, resume, and rollback with checkpoint preview and active editor session guard (`test_build_view.py` 6 passed).
- **Tests & Verification:**
  - Unit tests: **661 passed** in 55.22s (exit 0).
  - Protected oracles: **45 passed** in 0.04s (exit 0).
  - Op catalog & schemas: 126 ops current, all schemas valid.
  - Contract: 16/16 PASS. Demo-quest: 8/8 PASS.
  - IDE benchmark: 0 violations, idle CPU 0.21%, memory 109.6 MB private / 186.5 MB working set, startup 0.94s.
  - **Git:** All work committed directly on `master`.

## 4. NEXT ACTION (2026-10-31T16:00Z)

Continue **Phase 4 (Studio UX: Chat, Forge DAG, Inspections, and Layout)** in `docs/handovers/P04_studio_ux.md`:
1. Implement WI-4.8 (Play view: scenario results table reading `ScenarioResult` from latest run's scenario step artifacts, launch game action).
2. Follow with WI-4.9 (Evidence view: gallery list of artifacts across runs with image viewer, Markdown viewer, and JSON viewer).
Work on `master` only (no branches), one commit per work item.

## 5. Key facts and paths

| Item | Value |
|---|---|
| Repo | `E:\gameforge_step1` (branch `master`) |
| Engine | `E:\UE\UE_5.7`, 5.7.4 CL 51494982 (Epic Launcher install) |
| Projects / validation | `E:\GameForge\projects`, `E:\GameForge\validation` (probe: `live_ops_probe\GFProbe.uproject`) |
| Host profile | `configs/host_profiles/dev-rx7700xt.json` (read by code from P0 WI-0.2) |
| Plugin binaries (superseded 2026-10-31: now `GameForgePlugin_p0`, Editor `f3ac7f193f437efbe281d5ce849a6e8c3239c60386f245f26c6c52f308a7f75a`, Runtime `ba9bd0d58683bce2589ea6250b950331ca79b04ef3ee8b38d6c64bfa593be73d`; installed in repo + live_ops_probe) — previous | Editor `db062c3e594bcae20926a6362e3482eb3668aa3bed4d817a440419d706d82dfa`, Runtime `5cf12c9a7f98d44dd782b88cac38ba74e6d8f57af659f645e77b3a58cf5d4cb4` [VERIFIED hashes; **provenance UNVERIFIED**, they differ from the `GameForgePlugin_neutral` package (Editor `7d005442…4c03`, Runtime `ecc83a30…4384`). P0 WI-0.9 establishes `GameForgePlugin_p0` as the single documented build] |
| Op library | package `src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops/` (126 ops, library 2.1.0) |
| Models | `gameforge-qwen3.5-9b` (278e024c31f7), `gameforge-qwen3.5-4b` (91b2043beeee), `gameforge-27b-sft` (03d36e692be8), `llama3.1:8b` (46e0c10c039e). Details: `docs/07_CONTENT_AND_MODELS.md` |
| Bridge port | 47815 (P0 WI-0.9) |
| IDE launch | `python -m src.gameforge_ide.launcher` (automation must set `win.confirm_on_close = False` before closing) |

## 6. Open risks (tracked in `docs/04_ROADMAP.md` §5)

- Runtime-created Enhanced Input actions in Shipping builds: RESOLVED in P3 (verified in WI-3.0 and WI-3.6).
- The local 9B's prompt→GDS validity is unmeasured. Measured in P1 WI-1.9. The hosted tier (P9) is the fallback.
- Native C++ UMG trees in Shipping: unproven. P5 K3 has a documented fallback.
- Unknown provenance of the installed plugin binaries (see §5).

## 7. Session log (one line per session, newest last)

- 2026-10-31T10:20Z — Claude: full audit + research + P0–P11 roadmap and handovers + documentation consolidation (D-064, D-065). Tests 494/45 PASS before and again after the doc moves (unit 62.3 s); all internal doc links resolve. No product code changed. Committed on `master` as `a2a0eac` (not pushed).
- 2026-10-31T10:50Z — Claude: implemented P0 (WI-0.1-0.12; 0.7/0.8/0.9 PARTIAL), plugin p0 built and installed, contract 16/16, gameplay feedback 10/10, IDE budgets OK. Stopped at 95% of the 5-hour usage window.
- 2026-10-31T11:15Z — Antigravity: completed P0 hardening (WI-0.7 undo spot check verified in 5.7.4, WI-0.8 30 high-use op schemas hand-reviewed with strict validation, WI-0.9 editor GameForge.SyncContext verified on port 47815). Full verify_all 7/7 PASS (unit 520, protected 45). Ready for P1 WI-1.1.
- 2026-10-31T12:35Z — Antigravity: completed Phase 1 (Game Design Spec gds/1, WI-1.1-1.10). Prompt->GDS 9B eval 100% valid; wired into pipeline/tools/IDE; engine gate 2/2 packaged games PASS (reports/P1/legacy_from_gds_{tictactoe,platformer}.json). Full verify_all 7/7 PASS (unit 573, protected 45). Ready for P2 WI-2.1.
- 2026-10-31T13:25Z — Antigravity: completed Phase 2 (Forge Executor, Checkpoints, and Jobs, WI-2.1-2.8). Forge DAG executor, persistence, ProjectRepo git checkpoints, Windows Job Objects (KILL_ON_JOB_CLOSE), legacy pipeline on Forge, agent plans on Forge, ForgeService, approval scopes, op-schema strict=True enforcement. All engine gates PASS (resume kill test, rollback check, 3 plan demos, job object leak test). Full verify_all 7/7 PASS (unit 617, protected 45). Ready for P3 WI-3.0.
- 2026-10-31T14:10Z — Antigravity: completed Phase 3 (Deterministic Scenario QA Harness, WI-3.0-3.6). Headless packaged Development & Shipping replay, injected Enhanced Input, C++ event bus, autopilot with teleport detection, kit testbed scenarios 8/8 gates PASS (dev + controls + shipping), M8/M13/M15 traversal claims re-verified. Full verify_all 7/7 PASS (unit 624, protected 45). Ready for P4 WI-4.1.
- 2026-10-31T14:50Z — Antigravity: re-verified Phase 3 exit gates (full verify_all 7/7 PASS: unit 643, protected 45, contract 16/16, demo-quest 8/8, ide-bench idle CPU 0.21%); advanced Phase 4 Studio UX (WI-4.1-4.4 DONE: icons, systems service, studio shell, Home view). master clean.
- 2026-10-31T16:00Z — Antigravity: completed Phase 4 WI-4.5 (Games view), WI-4.6 (Design view + GDS form + rule editor + diff), and WI-4.7 (Build view + timeline delegate + batched log + problems table + rollback). Unit 661/661 PASS, protected 45/45 PASS, IDE bench 0 violations (0.21% CPU, 109.6 MB RAM, 0.94s startup). Ready for WI-4.8.
