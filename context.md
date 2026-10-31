# GameForge — Canonical Project Context

**Last updated:** 2026-10-31T11:15Z (UTC from the system clock; earlier entries in the history log mix local time
with a `Z` suffix). Updated by Antigravity upon P0 foundation completion.
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

## 3. CURRENT STATE (2026-10-31T11:15Z) [VERIFIED unless marked]

- **P0 Foundation Hardening complete:** All 12 work items (WI-0.1 through WI-0.12) are DONE.
  - WI-0.7: Engine undo spot check verified in offscreen UE 5.7.4 editor (`reports/P0/undo_spotcheck.json` PASS). Property mutations run inside `ScopedEditorTransaction` and revert cleanly under `TRANSACTION UNDO`.
  - WI-0.8: Argument models for all 30 high-use ops hand-reviewed and registered in `REVIEWED` with `extra="forbid"` (`op_schemas.py`). Unit suite verifies schema coverage and reject/round-trip behavior (`test_op_schemas.py` 9 passed).
  - WI-0.9: Loopback bridge on port 47815 verified. Editor-originated `GameForge.SyncContext` console command successfully transmits context with bearer authentication to `--serve` backend (`reports/P0/bridge_47815.json` PASS).
  - Plugin build `GameForgePlugin_p0` installed in repo and `live_ops_probe` (Editor DLL `f3ac7f193f437efbe281d5ce849a6e8c3239c60386f245f26c6c52f308a7f75a`, Runtime DLL `ba9bd0d58683bce2589ea6250b950331ca79b04ef3ee8b38d6c64bfa593be73d`).
- **Tests & Verification:**
  - `powershell -File scripts\verify_all.ps1` (full 7 gates): **ALL 7 PASS** (`reports/P0/verify_all.txt`).
  - Unit tests: **520 passed** (exit 0).
  - Protected oracles: **45 passed** (exit 0).
  - Contract: 16/16 PASS. Demo-quest: 8/8 PASS. IDE benchmark: 0 violations, idle CPU 0.21%.
- **Documentation consolidated (D-065):** `docs/README.md` index, `docs/handovers/` P00–P11, `docs/00_STATUS.md` capability matrix updated.
- **Git:** All work committed directly on `master`.

## 4. NEXT ACTION (2026-10-31T11:15Z)

**Phase 0 COMPLETE.** All exit gates satisfied.
Start **Phase 1 (Game Design Spec `gds/1`)** in `docs/handovers/P01_game_design_spec.md`:
1. **WI-1.1**: Implement `src/gameforge_ide/design/events_catalog.py` and `tests/unit/test_events_catalog.py`.
2. **WI-1.2**: Implement GDS schema `src/gameforge_ide/design/gds.py` and `tests/unit/test_gds_schema.py`.
3. Continue through Phase 1 items in exact handover order.
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
