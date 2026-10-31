# GameForge Complete Capability Matrix

Updated 2026-10-30T19:40Z (Claude Code; rows 9, 18, 21–24, 36 revised from engine demos). Engine target: UE 5.7.4 (`E:\UE\UE_5.7`, CL 51494982).
Statuses: `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, `NOT VERIFIED`, `EXPERIMENTAL`, `PLANNED`.
Provenance classes: PROC (procedural), NEURAL, IMPORTED, HUMAN, NATIVE (Unreal editor construction), CODEGEN.
Machine-readable row-level evidence: `reports/audit_20261030_capability_matrix.csv`.
Roadmap: `GAMEFORGE_MASTER_ROADMAP.md`.

| # | Capability | Status | Provenance | Real evidence / note |
|---|---|---|---|---|
| 1 | Multi-step DAG planner, approvals, recovery, IDE runner | PASS | — | `reports/milestone1_*_demo.json` |
| 2 | Blueprint graph authoring (9 ops) + compiler diagnostics | PASS | NATIVE | `reports/milestone2_blueprint_demo.json` |
| 3 | UMG widget authoring + UI-inclusive capture | PASS | NATIVE | `reports/milestone3_umg_demo.json` |
| 4 | Functional UMG, routed clicks, gameplay state component (runtime module) | PASS | NATIVE/CODEGEN | `reports/milestone4_umg_functional_demo.json` |
| 5 | Recipe games: tic-tac-toe, N-in-row, Connect Four | PASS | CODEGEN | context.md §G |
| 6 | Platformer / arena / card battler, packaged + real Win32 input | PASS | CODEGEN | `reports/packaged_real_input_summary.json` |
| 7 | Free-form game via model C++ + repair ladder | PARTIAL | CODEGEN (LLM) | Hard gates pass; visual quality weak on the 9B tier |
| 8 | Landscape heightfield (fBm), spline road, HISM scatter, landmark | PASS | PROC/NATIVE | `reports/milestone8_procedural_world_demo.json` |
| 9 | PCG graph authoring (grid → static mesh spawner) | PARTIAL | NATIVE | Authenticity PASS (`reports/wpa_reverify_20261031.json`: 400 instances in a PCG-tagged ISM); still grid sampling only (Surface Sampler = M8 v2) |
| 10 | NavMesh pathing, traversal, seed reproducibility | PASS | NATIVE | `reports/audit_m8_completion.json` |
| 11 | Biomes (all paint layers visible), kit villages, **PCG-native exclusion around structures** (Get Actor Data by tag → binary Difference), lighting presets, seed determinism, regeneration keeping user actors | PASS (village 15/15; **World Partition + Data Layer ownership 9/9**, `reports/m8v2_datalayers_demo.json`) / PLANNED (landscape inside a partitioned world, runtime streaming, packaged traversal, real tree/rock meshes instead of placeholder cones/spheres) | PROC/NATIVE | `reports/m8v2_village_demo.json`: layers Grass 192 / Rock 32 / Moss 32; exclusion control: 243 instances inside houses without vs 0 with; `reports/m8v2_village.png`. Dungeon generator offline-tested only; ownership is label-prefix based (AD-7 interim) |
| 12 | Procedural skinned humanoid (20 bones) → glTF → Interchange import | PASS (prototype quality) | PROC | `reports/audit_m9_generated_character.json` |
| 13 | In-engine skin deformation check, quarantine → promotion | PASS | NATIVE | `reports/audit_m9_m10_completion.json` |
| 14 | Neural text/image-to-3D character or mesh | BLOCKED | NEURAL | CUDA-only research code; 12 GB AMD |
| 15 | Automatic neural rigging | BLOCKED | NEURAL | Same |
| 16 | Procedural locomotion clips (6) → AnimSequence (engine poses match) | PASS | PROC | `reports/audit_m10_generated_motion.json` |
| 17 | Locomotion AnimInstance, PIE transitions Idle→…→Land | PASS (PIE) / NOT VERIFIED (packaged) | NATIVE | `audit_m9_m10_completion.json` |
| 18 | IK Rig + IK Retargeter + batch retarget (`anim_ik_retarget`) | PASS | NATIVE | World-space chain proof: swing error ≤ 0.44°, target keeps own arm length (`reports/wpa_reverify_20261031.json`) |
| 19 | BlendSpace1D (Idle/Walk/Run on Speed) driving the locomotion AnimInstance in PIE | PASS (PIE, 10/10: weights follow ground speed, phase-synced blend, transitions intact) / PLANNED (foot IK, montages, turn-in-place, packaged check) | NATIVE | `reports/m10v2_blend_drive_demo.json`, `reports/m10v2_blendspace_demo.json` |
| 20 | Neural text-to-motion | BLOCKED | NEURAL | CUDA |
| 21 | Material graph authoring + read-back (`material_build_graph`, `material_readback_graph`) | PASS | NATIVE | `reports/m11_material_demo.json` (12/12; read-back identical after restart) |
| 22 | PBR texture sets (procedural), texture import roles, MIs | PASS | PROC/NATIVE | `pbr_texture_generator.py`; `reports/m11_material_demo.json`. Material Functions: PLANNED. Landscape layers: see `reports/m11_landscape_demo.json` |
| 23 | Geometry Script procedural props, LOD, collision, UV, modular kit | PASS | NATIVE | `reports/m12_asset_demo.json` (crate 754/376/188 tris, spec→promote), `reports/m12_kit_demo.json` (5 kit pieces, 3×2 room) |
| 24 | Asset registry with provenance/search | PASS | — | `backend/assets/registry.py` (SQLite); quarantine, character, animation, PBR and M12 pipelines record into it; PROMOTE gated on ENGINE_VERIFY |
| 25 | Niagara VFX: template systems, PIE spawn, live particle-count read-back, **gameplay-event trigger** (`AGameForgeVFXPickup`, runtime kit) | PASS (PIE) / NOT VERIFIED (packaged, `stat Niagara` cost, M11 renderer material) | NATIVE | `reports/m13_vfx_demo.json`; `reports/m13_gameplay_vfx_demo.json` 5/5: the player pawn walks a NavMesh path into the pickup → `GF_EVENT pickup` → burst 190→0 particles, `reports/m13_gameplay_vfx.png`. Emitter-composed systems unsupported from 5.7 Python |
| 26 | Procedural SFX, WAV import, attenuation, PIE playback (AmbientSound + SpawnSoundAtLocation), **MetaSound graph authoring**, **gameplay-triggered spatialized SFX** (`AGameForgePickup`) | PASS (PIE) / PLANNED (Sound Class/Mix, Submix reverb, packaged playback, audible-output capture) | PROC/NATIVE | `reports/m14_audio_demo.json` 8/8; `reports/m14_metasound_demo.json` 5/5 (Sine × AD Envelope; graph-driven OnFinished stops it at 0.68 s); `reports/gameplay_feedback_demo.json` 10/10 |
| 27 | Speech / music generation | BLOCKED (install approval) / PLANNED | NEURAL/PROC | Registry |
| 28a | **Perception guard NPC** (`AGameForgeGuard` kit actor: AI Perception sight + NavMesh; Patrol → Chase → Search → Return → Patrol) | PASS (PIE, 6/6) | NATIVE/CODEGEN | `reports/m15_guard_demo.json`. Note: the chase in the run lasted 0.36 s (the pawn crossed out of the 70° cone), so it is not a long-pursuit test. The state logic is native C++, not a BT/StateTree asset |
| 28b | **Quest giver + objectives + save/load** (`AGameForgeQuestGiver`, `UGameForgeObjectiveSubsystem`, USaveGame slot; pickups advance objectives) | PASS (PIE, 8/8, persists across PIE sessions) | NATIVE/CODEGEN | `reports/m15_quest_demo.json`: dialogue → objective 0/2 → 1/2 → Completed → turn-in; a new session loads Completed 2/2 from `Saved/SaveGames/GF_Objectives.sav`. Dialogue is logged/read back, not shown in a UI yet |
| 28c | GAS, StateTree/BT assets, EQS, hearing, Smart Objects, inventory, dialogue UI/branching | PLANNED | — | Gameplay kit + M15 remainder (all plugins present) |
| 29 | Basic enemy AI (AIController MoveTo) | PASS | CODEGEN | Arena recipe |
| 30 | Sequencer authoring (cuts, keys, audio) + Movie Render Queue | PASS | NATIVE | `reports/m16_sequence_demo.json` 8/8 (2026-10-31): lit MRQ render, cuts detected at frames 24/48, each shot shows its cube; `reports/m16_lit_frame30.png`. The black frames came from the demo's sun facing away from the cameras, not from MRQ |
| 31 | Multiplayer replication tests | PLANNED | — | M18 |
| 32 | Automation tests + packaged self-test + vision review | PASS | — | All recipes |
| 33 | Profiling (csvprofile capture + parser), optimization loop | PARTIAL | — | `reports/m19_perf_village.json` (editor PIE); packaged capture, Insights and the optimisation loop: PLANNED |
| 34 | Build / cook / package Win64 | PASS | — | ~860 MB per package |
| 35 | Incremental modification of existing projects | PLANNED | — | M20 / AD-7 |
| 36 | Operation catalogue with read-back enforcement | PASS | — | `unreal/op_catalog.py` (all `@op`s catalogued; unit test enforces read-back) |
