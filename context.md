# GameForge — Canonical Project Context

**Last updated:** 2026-10-31T12:35Z (UTC from the system clock). Updated by Antigravity upon P1 Game Design Spec completion.
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

## 3. CURRENT STATE (2026-10-31T12:35Z) [VERIFIED unless marked]

- **P1 Game Design Spec (`gds/1`) complete:** All 10 work items (WI-1.1 through WI-1.10) are DONE.
  - WI-1.1: `events_catalog.py` (42 catalog events across 12 modules) + `test_events_catalog.py` (5 passed).
  - WI-1.2: Canonical GDS schema `src/gameforge_ide/design/gds.py` (JSON Schema 22 KB) + `test_gds_schema.py` (10 passed).
  - WI-1.3: `DesignDraft` model-facing schema `src/gameforge_ide/design/draft.py` (JSON Schema 3.2 KB <= 6 KB) + `test_draft_schema.py` (4 passed).
  - WI-1.4: Deterministic expander `src/gameforge_ide/design/expand.py` + `test_gds_expand.py` (5 passed).
  - WI-1.5: 7 legacy presets matching recipes losslessly `src/gameforge_ide/design/presets.py` + `test_gds_presets.py` (6 passed).
  - WI-1.6: `prompt_to_gds.py` with 1 repair attempt + `OllamaProvider.complete_json` + `test_prompt_to_gds.py` (9 passed).
  - WI-1.7: Markdown renderer `src/gameforge_ide/design/render.py` (`EVENT_PHRASES` with 42 entries) + `test_gds_render.py` (4 passed).
  - WI-1.8: Atomic store/revisions `src/gameforge_ide/design/store.py` + lossless legacy recipe adapter `src/gameforge_ide/design/legacy.py` + tests (6 passed).
  - WI-1.9: Prompt fixture set (40 prompts in `tests/fixtures/gds_prompts.jsonl`, 15 model drafts) + `test_gds_fixtures.py` (4 passed, 500 property drafts PASS) + live 9B evaluation `scripts/pipeline/eval_prompt_to_gds.py` (`reports/P1/prompt_to_gds_9b.json` PASS, 15/15 valid, 100% fail closed, 2.16s latency).
  - WI-1.10: Wired into `GameTools` (`plan_game`, `propose_create_game`, `create_game`), `GamePipeline` (`on_project_dir_ready`), `ApprovalCard`, `DesignPanel` (Markdown + JSON tabs on activity rail), `run_game_pipeline.py` (`--prompt`), and launcher startup improvements. Engine gate 2/2 PASS: two packaged games from GDS (`reports/P1/legacy_from_gds_tictactoe.json` and `reports/P1/legacy_from_gds_platformer.json`).
- **Tests & Verification:**
  - `powershell -File scripts\verify_all.ps1` (full 7 gates): **ALL 7 PASS** (`reports/P1/verify_all.txt`).
  - Unit tests: **573 passed** (exit 0).
  - Protected oracles: **45 passed** (exit 0).
  - Contract: 16/16 PASS. Demo-quest: 8/8 PASS. IDE benchmark: 0 violations, idle CPU 0.05%.
- **Documentation consolidated (D-065):** `docs/README.md` index, `docs/handovers/` P00–P11, `docs/00_STATUS.md` capability matrix updated.
- **Git:** All work committed directly on `master`.

## 4. NEXT ACTION (2026-10-31T12:35Z)

**Phase 1 COMPLETE.** All exit gates satisfied.
Start **Phase 2 (Forge Executor, Checkpoints and Jobs)** in `docs/handovers/P02_forge_executor.md`:
1. **WI-2.1**: Implement `src/gameforge_ide/forge/model.py` and `tests/unit/test_forge_model.py`.
2. **WI-2.2**: Implement `src/gameforge_ide/core/jobs.py` (Windows job objects, JobManager) and `tests/unit/test_jobs.py`.
3. Continue through Phase 2 items in exact handover order.
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
