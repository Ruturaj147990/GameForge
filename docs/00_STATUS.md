# GameForge Capability Status (live matrix)

**Owner:** Claude (Antigravity updates rows when a work item finishes; Claude reviews). **Last full review:**
2026-10-31 (audit). This replaces `GAMEFORGE_COMPLETE_CAPABILITY_MATRIX.md` and `GAMEFORGE_FINAL_PRODUCTION_READINESS.md`.
Engine: UE 5.7.4 (CL 51494982). Statuses: `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, `NOT VERIFIED`, `EXPERIMENTAL`,
`PLANNED`. Provenance classes: see `07_CONTENT_AND_MODELS.md` §3.

**Product verdict (2026-10-31):** Production-capable for 7 genres across 6 layouts via data-driven Kit v2 and deterministic Composer (grid board, platformer, arena combat, card battler, procedural world, third-person adventure, and top-down shooter). All 693 unit tests pass, 45 protected grader oracles pass. The path to 1.0 is `04_ROADMAP.md`.

## A. Product loop

| Capability | Status | Evidence / note | Phase |
|---|---|---|---|
| Prompt → packaged game, 5 recipe genres + 2 new genres | PASS | Composer replaces legacy recipes; 6 preset parity + adventure & top-down shooter verified (`reports/P6/`) | P6 |
| Free-form game via model C++ + repair ladder | PARTIAL | hard gates pass (whack-a-mole, 9B); visual quality weak | P6 replaces it with composition |
| Game Design Spec (typed, reviewable) | PASS | schema gds/1, deterministic expander, presets, prompt_to_gds eval 100% valid, store/revisions, pipeline wired; 2 packaged games from GDS (reports/P1/legacy_from_gds_{tictactoe,platformer}.json) | P1 |
| One durable executor, resume, checkpoints | PASS | Forge executor, atomic persistence, git checkpoints, resume kill test (reports/P2/resume_kill_test.json), rollback check (reports/P2/rollback_check.json), plan demos on Forge (reports/P2/plan_demos_forge.json), leak test (reports/P2/job_object_leak_test.json) | P2 |
| Scenario playtests (injected input, Shipping-safe) | PASS | Headless packaged Development & Shipping replay, injected Enhanced Input, C++ event bus, 5 dev scenarios (incl. 2 controls) & 3 ship scenarios (`reports/P3/kit_testbed_scenarios.json`) | P3 |
| Studio UI for the loop | PASS | P4 WI-4.1–WI-4.10 DONE (icons, systems service, studio shell, Home, Games, Design, Build, Play/QA, Settings views, packaging/launch, theme persistence) | P4 |
| Composition of kit modules from a spec | PASS | P6 complete: deterministic composer (`compose.py`), 6 layouts (`board`, `arena`, `course`, `rooms`, `open_world`, `lanes`), Bridson Poisson-disk scatter, ballistic reachability, level_ops strict schema validation, gfdef runtime definition, Forge DAG plan, parity across 6 legacy presets + 2 new genres (`reports/P6/parity_*.json`, `reports/P6/genre_*.json`) | P6 |
| Change requests / incremental rebuild | PASS | RFC 6902 JSON patch, shortcuts, impact analysis, 10 change requests verified (reports/P8/change_requests.json) | P8 |
| Incremental modification of user projects | PASS | project_graph actor reconciliation with user edit protection ('keep mine'), template import verified (reports/P8/import_demo.json), 100k index benchmark (reports/P8/index_benchmark.json) | P8 |

## B. Agent, planner, IDE

| Capability | Status | Evidence / note | Phase |
|---|---|---|---|
| DAG planner, approvals, recovery | PASS | F-03 fixed in P0 WI-0.1 (evaluator-backed custom predicates, NO_EVIDENCE); M1 demos re-run | P2 replaces |
| Native tool calling (4 local models) | PASS | `reports/native_tool_selftest.json` | — |
| Hosted tier | BLOCKED (needs approval) | requires explicit user approval for paid API key and data egress | P9 |
| IDE resource budgets | PASS | `reports/ide_resource_benchmark.json` | — |
| Settings / host independence | PASS | `core/settings.py`; `test_no_host_paths` (P0 WI-0.2/0.3) | — |
| Default model | PASS | evidence-based routing table generated from P9 evals (`config/model_routing.json`) | P9 |

## C. Engine layer

| Capability | Status | Evidence / note | Phase |
|---|---|---|---|
| Live editor link (token, loopback, crash classes) | PASS | contract 16/16 | — |
| Op catalogue with read-back enforcement (126 ops) | PASS | `unreal/op_catalog.py` + tests | — |
| Op argument schemas | PASS | all 126 drafted, 30 high-use hand-reviewed in `REVIEWED` (`op_schemas.py`) with strict validation (P0 WI-0.8) | P2 strict |
| Undo coverage for mutating ops | PASS | audited: 11 transactional, 46 checkpoint-only, 14 runtime; engine spot check PASS (P0 WI-0.7, `reports/P0/undo_spotcheck.json`) | P2 checkpoints |
| Build / test / package Win64 (Development) | PASS | ~860 MB per game | — |
| Shipping packages, size ≤ 400 MB | PLANNED | F-13 | P10 |
| Blueprint graph authoring (9 ops) | PASS | `reports/milestone2_blueprint_demo.json` | — |
| UMG authoring + functional UMG | PASS | `reports/milestone3_umg_demo.json`, `milestone4_umg_functional_demo.json` | — |

## D. Worlds, assets, presentation

| Capability | Status | Evidence / note | Phase |
|---|---|---|---|
| Landscape, spline road, HISM scatter, landmark | PASS | `reports/milestone8_procedural_world_demo.json` | — |
| PCG surface-sampled scatter + tag exclusion | PASS | `reports/m8v2_pcg_demo.json`, `m8v2_village_demo.json` | — |
| Biomes with paint layers, kit villages, seed determinism | PASS | `reports/m8v2_village_demo.json` (15/15) | — |
| World Partition + Data Layer ownership | PASS | `reports/m8v2_datalayers_demo.json` (9/9) | — |
| Landscape inside WP, streaming, packaged traversal | PLANNED | — | P10 |
| NavMesh pathing | PASS | `reports/audit_m8_completion.json` | — |
| PIE traversal claims (M8/M13/M15 via `pie_move_player_to`) | PASS | Re-verified with physically honest autopilot input on AGameForgeCharacter in GFKitTest (`reports/P3/reverify_traversal.json`) | P3 |
| Materials: graph authoring, MIs, functions, landscape layers | PASS | `reports/m11_material_demo.json`, `m11_landscape_demo.json` | — |
| Procedural PBR textures | PASS | `pbr_texture_generator.py` + M11 demo | — |
| Geometry Script props, LOD, collision, modular kit | PASS | `reports/m12_asset_demo.json`, `m12_kit_demo.json` | — |
| Asset registry with provenance | PASS | `backend/assets/registry.py` + tests | — |
| Epic template content (Manny/Quinn, prototyping) | PASS | P7 complete: installed in projects, directories to always cook configured, 157 assets registered with honest EPIC_CONTENT provenance (`reports/P7/registry_audit.json`) | P7 |
| Art direction / no-placeholder gate | PASS | P7 complete: deterministic mesh audit (0 placeholders), 6 themes, 10 procedural CSG props, visual rubric (`reports/P7/art_direction_audit.json`) | P7 |
| Procedural skinned humanoid → import → promote | PASS (prototype) | `reports/audit_m9_generated_character.json` | — |
| Procedural locomotion clips, AnimInstance, BlendSpace drive | PASS (PIE) | `reports/audit_m10_generated_motion.json`, `m10v2_blend_drive_demo.json` | — |
| IK Retargeter path | PASS | `reports/wpa_reverify_20261031.json` | — |
| Niagara template systems, PIE spawn, gameplay trigger | PASS (PIE) | `reports/m13_vfx_demo.json`, `gameplay_feedback_demo.json` | — |
| Procedural SFX, MetaSound graphs, spatial playback | PASS (PIE) | `reports/m14_audio_demo.json`, `m14_metasound_demo.json` | — |
| Sequencer + MRQ with cut detection | PASS | `reports/m16_sequence_demo.json` (8/8) | — |
| CSV profiling (editor PIE) | PARTIAL | `reports/m19_perf_village.json` | P10 |

## E. Gameplay kit (runtime)

| Capability | Status | Evidence / note | Phase |
|---|---|---|---|
| Pickup with VFX + SFX + objective progress | PASS (PIE) | `reports/gameplay_feedback_demo.json` | — |
| Perception guard (patrol/chase/search/return) | PASS (PIE), packaged | `reports/m15_guard_demo.json`, `kit_packaged_selftest.json` | — |
| Quest giver + objectives + save/load | PASS (PIE + packaged) | `reports/m15_quest_demo.json`, `kit_packaged_selftest.json` | — |
| Packaged kit self-test (Character walker) | PASS 6/6 | `reports/kit_packaged_selftest.json` | — |
| Event bus (C++ UGameForgeEventBus subsystem + JSONL session logs) | PASS | P3 WI-3.1 (GameForgeEventNames.h, parity test PASS) | P3 |
| Scenario QA Harness (headless Dev/Ship replay, autopilot, injected input) | PASS | P3 WI-3.0-3.6 (reports/P3/kit_testbed_scenarios.json, 8/8 gates PASS) | P3 |
| Rules engine, GAS health, enemies, spawner, HUD, menus | PASS | P5 complete (`reports/P5/kit_scenarios_final.json`, 19/19 gates PASS, 3/3 AutomationTests PASS) | P5 |
| Board / card logic as kit modules | PASS | P5 complete (AGameForgeGridBoard, AGameForgeCardTable, card match component, packaged Dev/Ship tested) | P5 |

## F. Models and specialists

| Capability | Status | Evidence / note | Phase |
|---|---|---|---|
| 4-model local roster | PASS | `07_CONTENT_AND_MODELS.md` §1 | — |
| Vision review | PASS | P7 complete: 6-criterion visual quality rubric + deterministic mesh audit gate (`reports/P7/art_direction_audit.json`) | P7 |
| Agentic eval suite | PASS | 5 task suites evaluated across all 4 local models on live Ollama host (`reports/P9/eval_*.json`) | P9 |
| Neural text/image-to-3D on this host | BLOCKED (needs approval) | spikes recorded in `reports/P9/spike_*.json` (ROCm 7.2 gfx1101, Hunyuan3D-2.1, Piper TTS) | P9 |
| Speech / music generation | PASS (procedural) | P7 complete: 16-bar looping chord progressions across 4 moods (`content/music.py`) + ambient sound beds (`content/ambience.py`) | P7 |
| Multiplayer | PLANNED | — | P10 |
