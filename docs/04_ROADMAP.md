# GameForge Master Completion Roadmap (P0–P11)

**Owner:** Claude (principal architect). **Created:** 2026-10-31. **Status:** ACTIVE. This is the only active plan.
It supersedes `GAMEFORGE_MASTER_ROADMAP.md` (M8–M20) and the work-package table in Master Blueprint v2. Git history
keeps both.

Read first: [`02_AUDIT_2026-10-31.md`](02_AUDIT_2026-10-31.md) (where we are), [`01_ARCHITECTURE.md`](01_ARCHITECTURE.md)
(where we are going), [`handovers/HANDOVER_PROTOCOL.md`](handovers/HANDOVER_PROTOCOL.md) (how work is executed).

---

## 1. Starting point in one paragraph

The engine layer is strong. It has 126 read-back-catalogued ops, a 7.4k-line C++ plugin, a real
build/test/package toolchain and kit actors verified in PIE. The 5 recipe genres reach packaged games from a prompt.
**But the product loop is narrow.** A prompt can only produce those 5 fixed genres with placeholder art. Nothing
built in M8–M16 is reachable from a prompt. There is no design spec the user can review. Verification is per-demo
and partly depends on window focus and a pawn that teleports. The IDE is laid out as a code IDE. The plan below turns
the strong parts into the product loop *idea → spec → build → play → change*, in dependency order.

## 2. Phase map

```
P0 Foundation hardening ─┬─► P1 Game Design Spec ──► P2 Forge executor + checkpoints ──► P3 Scenario QA harness
                         │                                                                  │
                         │                     P4 Studio UX v2 ◄────────────────────────────┘ (needs P1–P3 data)
                         │                                │
                         │      P5 Gameplay Kit v2 ◄──────┤ (P3 runner + P2 runs)
                         │                │
                         │      P6 Composer: GDS → playable game; recipe migration
                         │                │
                         │      P7 Content & art direction ──► P8 Living projects (change requests, index, import)
                         │                                                          │
                         └─► P9 Model intelligence (parallel track from P1; gates defaults before P11)
                                                                                    ▼
                                         P10 Scale: performance, Shipping, multiplayer, cinematics, UE 5.8 lane
                                                                                    ▼
                                         P11 Release: flagship "Ember Vale", IDE distribution, 1.0 gates
```

| Phase | Name | Core outcome | Depends on | Estimate* |
|---|---|---|---|---|
| **P0** | Foundation hardening | Defects F-03…F-08, F-10, F-11, F-15, F-16 fixed; settings service; ops package; one-command verification | — | 4–6 days |
| **P1** | Game Design Spec | `gds/1` schema, prompt→GDS (deterministic + model), validators, 5 recipe presets, legacy pipeline accepts a GDS | P0 | 1.5–2 wks |
| **P2** | Forge executor | One persisted DAG executor, resume, input-hash skipping, per-step git checkpoints, events; legacy pipeline and agent plans run on it | P1 | 2 wks |
| **P3** | Scenario QA harness | Event bus v2, Enhanced-Input scenario runner + autopilot in `GameForgeRuntime`, scenario generator from GDS goals, packaged headless runs | P2 | 2–3 wks |
| **P4** | Studio UX v2 | New information architecture (Home/Games/Design/Build/Play/Evidence/Assets/Code/Settings + Assistant) on real data | P1–P3 | 2–3 wks |
| **P5** | Gameplay Kit v2 | Data-driven runtime: GameDefinition, rules engine, player/camera rigs, GAS health, enemies, spawners, interaction, HUD, feedback, menus, save; all with automation + scenario tests | P3 | 5–7 wks |
| **P6** | Composer | GDS → composition → playable packaged game; 5 legacy genres reproduced on the kit; 2 new genres; legacy recipes retired | P5 | 4–6 wks |
| **P7** | Content & art direction | Art direction → materials, props, vegetation, characters, animation, VFX/SFX through the content resolution order; content library; "no placeholder" rubric gate | P6 | 4–6 wks |
| **P8** | Living projects | Change requests via GDS patches, incremental rebuilds, user-edit protection, project index, import of existing UE projects | P6 (P7 for content regeneration) | 4–5 wks |
| **P9** | Model intelligence | Agentic eval suite, real hosted-tier validation, routing from scores, local fine-tune flywheel, gated neural spikes | P1 (track), P6 for codegen evals | 3–4 wks (parallel) |
| **P10** | Scale & advanced systems | Performance budgets + optimisation loop, Shipping packaging ≤ 400 MB, World Partition open worlds, multiplayer (listen server), in-game cinematics, UE 5.8 lane | P6–P8 | 5–7 wks |
| **P11** | Release | Flagship "Ember Vale" from one prompt, IDE distribution (Nuitka), first-run onboarding, soak tests, security review, 1.0 gates | all | 2–3 wks |

*Calendar estimates for one developer plus AI agents, assuming a hosted heavy model is available from P6. These are
planning aids, not commitments. Estimates for engine work have historically been met; estimates for content
quality have not.

### Named milestones

- **MVP-A ("spec-driven")**, end of P4: every legacy genre is built from a reviewable GDS through Forge, verified by
  packaged scenarios, and shown in the new Studio UI.
- **MVP-B ("composed games")**, end of P6: new genres come from kit composition, and no generated gameplay C++ is
  needed except custom rules.
- **Beta**, end of P8: real art direction, iteration on existing games, project import.
- **1.0**, end of P11: flagship game, packaged IDE, all release gates green.

---

## 3. Phase summaries

Every phase has a full handover in `docs/handovers/` with work items, files, code, tests, acceptance and failure
cases. The summaries below are the contract. When a handover and its summary disagree, the handover is wrong: report
it in `QUESTIONS.md`.

### P0 — Foundation hardening ([handover](handovers/P00_foundation.md))
- **Objectives:** remove the trust defects and the host coupling before building on top.
- **Scope:** planner predicates (F-03); `core/settings.py` + engine discovery + all 23 paths (F-05); default model
  9B + `configs/model_routing.json` (F-06); character pipeline provenance (F-07); bridge port 47815 (F-08);
  `op_schemas.py` scaffold for the 30 most-used ops (F-10); split `gameforge_ops.py` into a package (F-11);
  transaction audit of the 73 mutating ops (F-04); dependency declarations (F-15); plugin descriptor (F-16); shared engine-demo
  harness and `scripts/` layout; `scripts/verify_all.ps1`.
- **Exit gate:** unit + protected suites green. `rg 'E:\\\\' src/gameforge_ide --glob '*.py'` returns only
  `core/settings.py` defaults documentation. Live contract 16/16 on a fresh probe copy.
  `scripts/engine/demo_gameplay_feedback.py` 10/10 with the split op package. The IDE starts with the 9B selected.

### P1 — Game Design Spec ([handover](handovers/P01_game_design_spec.md))
- **Objectives:** a reviewable, typed contract for every game (AD-9).
- **Scope:** `design/gds.py` (full schema), `design/events_catalog.py`, `design/presets/` (5 presets reproducing the
  legacy recipe defaults), `design/prompt_to_gds.py` (preset matcher → model draft with Ollama `format` JSON schema →
  validate → one repair → clarifying questions), `design/render.py` (Markdown summary and natural-language rule
  sentences), `design/legacy.py` (GDS → legacy recipe params), and a minimal Design panel (read-only render + JSON
  editor with validation).
- **Exit gate:** 40-prompt fixture set; for ≥ 95 % of preset prompts the deterministic path yields a valid GDS
  (rest → questions); model path ≥ 80 % valid on first try with 9B and 100 % fail-closed on invalid; TicTacToe and
  Platformer packaged from a GDS through the legacy pipeline (engine run).

### P2 — Forge executor ([handover](handovers/P02_forge_executor.md))
- **Objectives:** one durable executor (AD-11) with checkpoints (AD-13).
- **Scope:** `forge/model.py`, `forge/executor.py`, `forge/checkpoints.py`, `forge/handlers/*` wrapping the existing
  stage functions, `forge/legacy_adapter.py` (GamePipeline API preserved), agent TaskPlan → Forge adapter, run index,
  `core/jobs.py` with Windows job objects, op-schema enforcement (AD-14), and Build-view data (events JSONL).
- **Exit gate:** a legacy game run is killed mid-build (process kill during `build_editor`) and resumes, skipping done
  steps. Rollback to the `scaffold` checkpoint restores the tree byte-for-byte. All legacy pipeline tests pass
  through the adapter. Plan demos A/B/C re-run on Forge.

### P3 — Scenario QA harness ([handover](handovers/P03_scenario_qa.md))
- **Objectives:** playability proven by replaying input against the packaged build, headless, without window focus
  (AD-12, AD-19).
- **Scope:** C++ `UGameForgeEventBus`, `UGameForgeScenarioSubsystem`, `UGameForgeAutopilotComponent`, minimal kit
  player (`AGameForgeCharacter`, `AGameForgePlayerController` with runtime-built Enhanced Input), `qa/scenario.py`,
  `qa/generate.py` (from GDS goals + level manifest), `qa/runner.py` (packaged and `-game`), a Forge `scenario` step,
  and a re-verification of the M8/M13/M15 PIE traversal claims with leg-speed checks.
- **Exit gate:** in the kit test project, the collect, quest and guard-detection scenarios pass in a **Development
  package launched headless with no focus**, and again in a **Shipping** package (result file only). Two controls must
  fail: a `SetActorLocation` teleport cheat (`TELEPORT_SUSPECTED`) and an impossible expectation. The re-verification
  report lists every old traversal claim as PASS or FAIL. (`game.won`/`game.lost` scenarios arrive with the P5 rules
  engine.)

### P4 — Studio UX v2 ([handover](handovers/P04_studio_ux.md), spec [05_UX_SPEC.md](05_UX_SPEC.md))
- **Objectives:** the IDE becomes the game studio (AD-18).
- **Scope:** shell (top bar, rail, central `QStackedWidget` views, Assistant side panel), Home (prompt + presets + recent
  games + readiness checklist), Design (GDS form editor + raw JSON + validation + revision diff), Build (Forge timeline,
  live log tail, problems list, cancel/resume/rollback), Play (launch, scenario table, captures), Evidence (gallery),
  Settings (paths, engine, models, egress), onboarding, keyboard and DPI tests. Code mode keeps the existing
  explorer/diff/terminal docks.
- **Exit gate:** a scripted usability walk (prompt → review → build → play → evidence) needs no developer action. Idle
  CPU < 1 %, cold start < 2.5 s, no UI stall > 50 ms (instrumented), screenshots at 100/125/150 % DPI with no clipping.

### P5 — Gameplay Kit v2 ([handover](handovers/P05_gameplay_kit.md))
- **Objectives:** a tested, data-driven runtime that can express the GDS without generated gameplay code (AD-10).
- **Scope (C++ in `GameForgeRuntime`):** `UGameForgeGameDefinition` + `UGameForgeRuntimeSettings`,
  `UGameForgeRulesSubsystem` (ECA engine), `AGameForgeGameMode/GameState` (stats, win/lose), camera rig presets,
  `UGameForgeAttributeSet` (GAS health/stamina/damage), `AGameForgeEnemy` (melee/ranged), `AGameForgeSpawner`,
  `AGameForgeHazard`, `AGameForgeCheckpoint`, `AGameForgeGoal`, `UGameForgeInteractionComponent` +
  `IGameForgeInteractable`, `AGameForgeDoor`, `UGameForgeHUDWidget` (name-bound), `UGameForgeFeedbackSubsystem`,
  `UGameForgeMenuWidget`, `UGameForgeSaveSubsystem` (generalising objectives), board and card logic modules ported
  from the legacy recipes. Python `kit/registry.py` + `kit/modules/*.py` (param models). Kit automation tests and
  scenario suite.
- **Exit gate:** every module with status PASS has (a) automation tests green, (b) at least one scenario in the
  kit test level passing in a packaged build, (c) a registry row with evidence paths.

### P6 — Composer ([handover](handovers/P06_composer.md))
- **Objectives:** GDS → playable packaged game through composition; retire per-recipe templates.
- **Scope:** `composer/compose.py`, layouts (board, arena, course, rooms, open_world, lanes) reusing
  `dungeon_layout.py`, `biomes.py` and recipe layout logic; `composer/level_ops.py` (op list with read-back and
  manifest); `composer/runtime_def.py` (`gfdef/1`); `composer/codegen.py` (custom_code → C++ rule handler with repair
  ladder); Forge plan builder; legacy-parity suite; two new genres (third-person exploration/adventure, top-down
  shooter).
- **Exit gate:** the 5 legacy genres reproduced from presets on the kit with equal or better tests; 2 new genres from
  prompts; all `must_pass` scenarios green in packaged builds; recipe templates moved to `tests/fixtures/legacy_recipes/`.

### P7 — Content & art direction ([handover](handovers/P07_content_art.md))
- **Objectives:** games stop looking like prototypes (research R11 failure mode) without fabricating provenance.
- **Scope:** art-direction resolver (palette → material instances; lighting presets; material theme library);
  content resolution order (AD-17) with a **Content Library** (index of user-installed packs: Starter Content,
  GASP, Fab/Megascans) and licence classes; props via Geometry Script kits; vegetation via PCG with real meshes from
  the library or procedural meshes; characters (Manny/Quinn from engine content → procedural v2 → MetaHuman backend
  behind consent); animation (GASP motion matching when installed → procedural clips); VFX/SFX feedback presets
  bound to events; vision rubric calibrated against human labels; "no placeholder" gate.
- **Exit gate:** the adventure genre builds with zero placeholder primitives (rubric + mesh audit). Every asset has a
  registry row with a correct licence class. Rubric agreement with human labels ≥ 0.8 on a 30-image set.

### P8 — Living projects ([handover](handovers/P08_living_projects.md))
- **Objectives:** keep improving a game after the first build (AD-7).
- **Scope:** `design/patch.py` (JSON Patch on GDS, model-proposed, schema-validated), impact analysis through
  input hashes, `project_graph.json` ownership + generation hashes, user-edit detection and conflict UI, project
  index (SQLite FTS5: C++ symbols, assets, config), agent code edits on existing projects with compile + scenario
  gates, import of non-GameForge UE projects (read-only index + reverse-drafted GDS).
- **Exit gate:** 10 scripted change requests on a generated game, each rebuilding only the affected steps with
  scenarios green. A user-modified asset is detected and not overwritten. A third-party sample project is
  imported and indexed in < 10 min.

### P9 — Model intelligence ([handover](handovers/P09_model_intelligence.md))
- **Objectives:** pick and improve models by measured performance on GameForge's real tasks (AD-20).
- **Scope:** `evals/` suite (prompt→GDS fidelity, GDS patch correctness, custom-rule codegen with compile + scenario,
  C++ repair from recorded diagnostics, rubric agreement); hosted-tier live validation (user supplies key + opt-in);
  routing table from scores; trajectory capture for local LoRA refresh (training-lineage rules); gated neural spikes
  (ROCm Windows: Hunyuan3D-2.1 shape-only; Piper TTS).
- **Exit gate:** eval report for all 4 local models (+ hosted if enabled), `model_routing.json` generated from it,
  and every spike result recorded as PASS, FAIL or BLOCKED with numbers.

### P10 — Scale & advanced systems ([handover](handovers/P10_scale_advanced.md))
- **Scope:** performance budgets per GDS `tech` (csvprofile on Test builds, Insights export), optimisation loop;
  Shipping packaging profile (trimmed plugins, compression, ≤ 400 MB); World Partition open worlds with a
  landscape inside WP + streaming + packaged traversal; multiplayer listen server (replicated kit stats/attributes,
  2-client scenario); in-game cinematics (intro sequence from GDS); UE 5.8 compatibility lane.
- **Exit gate:** each sub-area has a packaged, scenario-verified demo with its budget met.

### P11 — Release ([handover](handovers/P11_release.md))
- **Scope:** flagship "Ember Vale" from one prompt, built end-to-end by the product (golden test); IDE packaging with
  Nuitka (install approval), portable zip plus optional installer; first-run wizard; crash-safe state restore; soak
  test (10 consecutive game builds, zero leaked processes, metadata within cap); security review; documentation pass;
  1.0 tag.
- **Exit gate:** the release checklist in the P11 handover is fully green with evidence.

---

## 4. Cross-cutting rules for every phase

1. **Branch per phase:** `phase/P<n>-<slug>`, one commit per work item (`P<n> WI-<n>.<k>: <summary>`). Merge to
   `master` only after Claude's review verdict is `ACCEPT` in the handover's review log.
2. **Run the gates** after every work item: `powershell -File scripts\verify_all.ps1 -Quick` (unit + protected + op
   catalogue + docs links). Engine gates run at the end of each work item that touches engine code.
3. **Evidence** goes in `reports/<phase>/<name>.json` with `checks` and `steps`. A check must be able to fail, so add a
   control where a pass could happen by chance.
4. **Update** `context.md` (state, next action), `docs/00_STATUS.md` (capability rows) and the handover's progress
   table after each work item. Mirror `context.md` to `E:\GameForge\context.md`.
5. **No scope creep.** Ideas go to `QUESTIONS.md`. Implementers never change an architecture decision.

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation | Phase |
|---|---|---|---|---|
| Local 9B too weak for GDS drafting / codegen | High | Medium | Presets + deterministic matcher; fail-closed questions; hosted tier; P9 evals decide | P1, P9 |
| GAS integration cost (compile time, complexity) | Medium | Medium | Kit owns one AttributeSet + C++-defined effects; no GAS assets authored by ops | P5 |
| Runtime Enhanced Input objects (NewObject) behave differently from assets | Medium | High | P3 spike WI-3.1 proves injection with runtime-created actions in a packaged build before anything depends on it | P3 |
| Shipping builds strip logs and console | Certain | High if ignored | Evidence via result files (AD-19); scenario subsystem compiled in all configs | P3 |
| Git checkpoints in projects with large binary assets | Medium | Low | `.gitignore` for derived data; size check per commit (warn > 200 MB); LFS deferred | P2 |
| Editor holds files during rollback | High | Medium | Rollback requires the editor to be stopped (enforced) | P2 |
| 12 GB VRAM contention (editor + LLM) | High | Medium | Existing GPU scheduler; unload before PIE/capture/package; host profile | all |
| Content licence misclassification | Medium | High | Licence class recorded at import; library packs need a user-confirmed licence entry; audit test | P7 |
| UI rewrite regressions | Medium | Medium | Views built beside the existing panels; old panels removed only after parity tests | P4 |
| Model output drift across Ollama versions | Medium | Medium | Native tool self-test at startup; Ollama version in evidence; schema validation | P1, P9 |
| Scope explosion ("every game from any prompt") | Certain | High | Composer supports declared genres and modules; anything else returns "unsupported: needs module X" with a plan | P6 |
