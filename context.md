# GameForge — Canonical Project Context

**Last updated:** 2026-10-31T13:25Z (UTC from the system clock). Updated by Antigravity upon P2 Forge Executor completion.
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

## 3. CURRENT STATE (2026-10-31T13:25Z) [VERIFIED unless marked]

- **P2 Forge Executor, Checkpoints, and Jobs complete:** All 8 work items (WI-2.1 through WI-2.8) are DONE.
  - WI-2.1: `src/gameforge_ide/forge/model.py` (DAG model, Kahn cycle check, stable `topo_order`, `canonical_hash`) + `test_forge_model.py` (9 passed).
  - WI-2.2: `src/gameforge_ide/forge/store.py` (atomic persistence with retry, `events.jsonl`, `latest_for_project`, `runs_index.json`) + `test_forge_store.py` (6 passed).
  - WI-2.3: `src/gameforge_ide/forge/checkpoints.py` (`ProjectRepo`, git checkpoints, `UE_GITIGNORE`, `reset_to` rollback, `editor_running` guard) + `test_checkpoints.py` (5 passed).
  - WI-2.4: `src/gameforge_ide/core/jobs.py` (Windows Job Object with `KILL_ON_JOB_CLOSE`, `adopt(proc)`, `spawn(argv)`, `ENGINE_LOCK`, `JobManager`) + `test_jobs.py` (5 passed).
  - WI-2.5: `src/gameforge_ide/forge/executor.py` (`ForgeExecutor`, step-by-step DAG execution, persistence, resume/skip unchanged work via `eff_hash`, approvals suspension, repair hooks) + `test_forge_executor.py` (9 passed).
  - WI-2.6: Migrated legacy pipeline to Forge (`forge/handlers/legacy_stages.py`, `forge/legacy_adapter.py`, `pipeline/game_pipeline.py`, `run_game_pipeline.py --resume`). Tests: `test_forge_legacy_adapter.py` (3 passed), `test_game_pipeline.py` (39 passed). Engine gate 1: full pipeline pass for Platformer & TicTacToe. Engine gate 2: kill & resume verified (`reports/P2/resume_kill_test.json`). Engine gate 3: rollback check verified (`reports/P2/rollback_check.json`).
  - WI-2.7: Migrated agent plans to Forge (`forge/handlers/tool_call.py`, `forge/plan_adapter.py`, `desktop/services/plan_runner.py`). Repetition control (blocks 3rd identical call), tool permissions, acceptance criteria evaluation. Tests: `test_forge_plan_adapter.py` (5 passed), `test_plan_runner.py` (2 passed). Engine gate: 3 plan demos on Forge verified (`reports/P2/plan_demos_forge.json`).
  - WI-2.8: UI wiring and schema enforcement: `ForgeService` Qt bridge (`test_forge_service.py` 1 passed), `action_runner.py` on `JobManager`, `ApprovalCard` scope lines (`paths`, `engine`, `packaging`, `minutes`), strict op schema validation (`strict=True` in `GameTools.unreal_editor`, 126 schemas, `test_op_schemas.py` 10 passed), hosted `oneOf` definition format. Job object leak test PASS (`reports/P2/job_object_leak_test.json`).
- **Tests & Verification:**
  - `powershell -File scripts\verify_all.ps1` (full 7 gates): **ALL 7 PASS** (`reports/P2/verify_all.txt`).
  - Unit tests: **617 passed** in 31.14s (exit 0).
  - Protected oracles: **45 passed** in 0.03s (exit 0).
  - Op catalog & schemas: 126 ops current, all schemas valid.
  - Contract: 16/16 PASS. Demo-quest: 8/8 PASS. IDE benchmark: 0 violations, idle CPU 0.21%.
- **Git:** All work committed directly on `master`.

## 4. NEXT ACTION (2026-10-31T13:25Z)

**Phase 2 COMPLETE.** All exit gates satisfied.
Start **Phase 3 (Scenario playtests: injected input, assertions, Shipping-safe)** in `docs/handovers/P03_scenario_playtests.md`:
1. **WI-3.0**: Spike: Enhanced Input simulation in standalone / packaged builds.
2. Continue through Phase 3 items in exact handover order.
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

- Runtime-created Enhanced Input actions in Shipping builds: unproven. The P3 WI-3.0 spike gates P3.
- The local 9B's prompt→GDS validity is unmeasured. Measured in P1 WI-1.9. The hosted tier (P9) is the fallback.
- Native C++ UMG trees in Shipping: unproven. P5 K3 has a documented fallback.
- Unknown provenance of the installed plugin binaries (see §5).

## 7. Session log (one line per session, newest last)

- 2026-10-31T10:20Z — Claude: full audit + research + P0–P11 roadmap and handovers + documentation consolidation (D-064, D-065). Tests 494/45 PASS before and again after the doc moves (unit 62.3 s); all internal doc links resolve. No product code changed. Committed on `master` as `a2a0eac` (not pushed).
- 2026-10-31T10:50Z — Claude: implemented P0 (WI-0.1-0.12; 0.7/0.8/0.9 PARTIAL), plugin p0 built and installed, contract 16/16, gameplay feedback 10/10, IDE budgets OK. Stopped at 95% of the 5-hour usage window.
- 2026-10-31T11:15Z — Antigravity: completed P0 hardening (WI-0.7 undo spot check verified in 5.7.4, WI-0.8 30 high-use op schemas hand-reviewed with strict validation, WI-0.9 editor GameForge.SyncContext verified on port 47815). Full verify_all 7/7 PASS (unit 520, protected 45). Ready for P1 WI-1.1.
- 2026-10-31T12:35Z — Antigravity: completed Phase 1 (Game Design Spec gds/1, WI-1.1-1.10). Prompt->GDS 9B eval 100% valid; wired into pipeline/tools/IDE; engine gate 2/2 packaged games PASS (reports/P1/legacy_from_gds_{tictactoe,platformer}.json). Full verify_all 7/7 PASS (unit 573, protected 45). Ready for P2 WI-2.1.
- 2026-10-31T13:25Z — Antigravity: completed Phase 2 (Forge Executor, Checkpoints, and Jobs, WI-2.1-2.8). Forge DAG executor, persistence, ProjectRepo git checkpoints, Windows Job Objects (KILL_ON_JOB_CLOSE), legacy pipeline on Forge, agent plans on Forge, ForgeService, approval scopes, op-schema strict=True enforcement. All engine gates PASS (resume kill test, rollback check, 3 plan demos, job object leak test). Full verify_all 7/7 PASS (unit 617, protected 45). Ready for P3 WI-3.0.
