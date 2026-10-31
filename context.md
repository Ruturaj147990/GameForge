# GameForge — Canonical Project Context

**Last updated:** 2026-10-31T10:20Z (UTC from the system clock; earlier entries in the history log mix local time
with a `Z` suffix). Updated by Claude (Opus 5.5) at the end of the audit and planning session.
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

## 3. CURRENT STATE (2026-10-31T10:20Z) [VERIFIED unless marked]

- **Audit complete:** `docs/02_AUDIT_2026-10-31.md` (findings F-01…F-21). The headline: the engine layer is strong
  (126 read-back-catalogued ops, a 7.4k-line C++ plugin, toolchain, 5 recipe genres reaching packaged games), but the
  M8–M16 capabilities are **not reachable from a prompt** (F-01). There is no reviewable game spec (F-02). The planner
  can complete without evidence (F-03). There are 23 hard-coded host paths (F-05), and the default model is the 27B
  with 4K context (F-06).
- **Plan adopted (D-064):** `docs/04_ROADMAP.md`, phases **P0–P11**, with executable handovers in `docs/handovers/`
  (protocol: `HANDOVER_PROTOCOL.md`). Architecture decisions AD-1…AD-20 are in `docs/01_ARCHITECTURE.md` §9.
- **Code in the handovers checked in this session:** the P1 GDS schema (`gds.py`, `events_catalog.py`, `draft.py`)
  and the P2 Forge model/executor/jobs code were extracted from the handover Markdown and executed in the scratchpad.
  The GDS round-trips and every cross-reference validator fires (GDS JSON schema 22 KB, DesignDraft 3 KB). The executor
  handles happy path, resume, dependency-aware input-hash skipping, failure blocking, exceptions, timeout, approval
  suspend/resume, repair retries, cycle rejection, mid-run cancel and the Windows job object correctly. The 16
  Studio icon SVGs render in QtSvg. The P3/P5 C++ is **not compiled yet**: it is specified with API checks for the
  implementer.
- **Documentation consolidated (D-065):** the knowledge base index is `docs/README.md`. Superseded plans were deleted
  after their content was merged. History moved to `docs/history/`. `README.md`, `ANTIGRAVITY_HANDOFF.md` and this file
  were rewritten, and the `AGENTS.md` pointers updated. **No product code was changed in this session**, except one
  config string (`src/gameforge_ide/config/hosted_providers.default.json` `data_policy` path).
- **Tests:** `python -m pytest tests/unit/ -q -p no:cacheprovider` → **494 passed**;
  `python -m pytest graders/protected/ -q -p no:cacheprovider` → **45 passed** (both exit 0, 2026-10-31, before the
  doc moves, and again after them: 494 / 45 passed).
- **Git:** this session's changes (docs plus the one config string) are committed on branch `docs/plan-2026-10-31`, based on
  `master` @ `c092b4c`. Not merged into `master`, not pushed.
- **Research highlights** (`docs/03_RESEARCH_2026-10-31.md`): UE 5.8 ships an experimental Unreal MCP with no auth on
  `127.0.0.1:8000` (it collides with our bridge port, so we move to 47815). MetaHuman 5.7 is scriptable
  (`UMetaHumanCharacterEditorSubsystem`, 28 BlueprintCallable functions present on disk). Enhanced Input injection APIs
  are present (`EnhancedInputSubsystemInterface.h:148,195`). The ROCm 7.2 HIP SDK for Windows lists gfx1101 (the
  neural verdict changes to BLOCKED pending approval). Spec2Game shows +18 points from a detailed spec, with rules and
  termination as the weak areas. Epic template Mannequins and LevelPrototyping content is on disk under
  `E:\UE\UE_5.7\Templates\TemplateResources\High\`.

## 4. NEXT ACTION

1. **The user decides whether to merge** branch `docs/plan-2026-10-31` into `master` (its single commit holds the plan and
   the doc clean-up). Nothing has been pushed. Branch `phase/P0-foundation` from whichever branch holds the docs.
2. **Start P0** (`docs/handovers/P00_foundation.md`) on branch `phase/P0-foundation`, beginning with **WI-0.1**
   (planner: completion only on evidence). P0 needs no approvals except the plugin rebuild in WI-0.9 (a local build;
   no install).
3. After each work item, follow `HANDOVER_PROTOCOL.md` §5 (progress table, this file, status matrix).

## 5. Key facts and paths

| Item | Value |
|---|---|
| Repo | `E:\gameforge_step1` (branch `master`) |
| Engine | `E:\UE\UE_5.7`, 5.7.4 CL 51494982 (Epic Launcher install) |
| Projects / validation | `E:\GameForge\projects`, `E:\GameForge\validation` (probe: `live_ops_probe\GFProbe.uproject`) |
| Host profile | `configs/host_profiles/dev-rx7700xt.json` (read by code from P0 WI-0.2) |
| Plugin binaries installed in the repo | Editor `db062c3e594bcae20926a6362e3482eb3668aa3bed4d817a440419d706d82dfa`, Runtime `5cf12c9a7f98d44dd782b88cac38ba74e6d8f57af659f645e77b3a58cf5d4cb4` [VERIFIED hashes; **provenance UNVERIFIED**, they differ from the `GameForgePlugin_neutral` package (Editor `7d005442…4c03`, Runtime `ecc83a30…4384`). P0 WI-0.9 establishes `GameForgePlugin_p0` as the single documented build] |
| Op library | `src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops.py` (126 ops, 173 KB; split into a package in P0 WI-0.6) |
| Models | `gameforge-qwen3.5-9b` (278e024c31f7), `gameforge-qwen3.5-4b` (91b2043beeee), `gameforge-27b-sft` (03d36e692be8), `llama3.1:8b` (46e0c10c039e). Details: `docs/07_CONTENT_AND_MODELS.md` |
| Bridge port | 8000 today → 47815 in P0 WI-0.9 |
| IDE launch | `python -m src.gameforge_ide.launcher` (automation must set `win.confirm_on_close = False` before closing) |

## 6. Open risks (tracked in `docs/04_ROADMAP.md` §5)

- Runtime-created Enhanced Input actions in Shipping builds: unproven. The P3 WI-3.0 spike gates P3.
- The local 9B's prompt→GDS validity is unmeasured. Measured in P1 WI-1.9. The hosted tier (P9) is the fallback.
- Native C++ UMG trees in Shipping: unproven. P5 K3 has a documented fallback.
- Unknown provenance of the installed plugin binaries (see §5).

## 7. Session log (one line per session, newest last)

- 2026-10-31T10:20Z — Claude: full audit + research + P0–P11 roadmap and handovers + documentation consolidation (D-064, D-065). Tests 494/45 PASS before and again after the doc moves (unit 62.3 s); all internal doc links resolve. No product code changed. Committed on branch `docs/plan-2026-10-31` (not merged, not pushed).
