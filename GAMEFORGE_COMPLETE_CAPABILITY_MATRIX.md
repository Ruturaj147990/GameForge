# GameForge Complete Capability Matrix

Updated 2026-10-30T17:20Z (Claude Code). Engine target: UE 5.7.4 (`E:\UE\UE_5.7`, CL 51494982).
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
| 9 | PCG graph authoring (grid → static mesh spawner) | PARTIAL | NATIVE | `pcg_scatter`: real `UPCGGraph`; only grid sampling; the docstring wrongly says Surface Sampler |
| 10 | NavMesh pathing, traversal, seed reproducibility | PASS | NATIVE | `reports/audit_m8_completion.json` |
| 11 | Biomes, buildings, World Partition, Data Layers, lighting presets | PLANNED | — | Roadmap M8 v2 |
| 12 | Procedural skinned humanoid (20 bones) → glTF → Interchange import | PASS (prototype quality) | PROC | `reports/audit_m9_generated_character.json` |
| 13 | In-engine skin deformation check, quarantine → promotion | PASS | NATIVE | `reports/audit_m9_m10_completion.json` |
| 14 | Neural text/image-to-3D character or mesh | BLOCKED | NEURAL | CUDA-only research code; 12 GB AMD |
| 15 | Automatic neural rigging | BLOCKED | NEURAL | Same |
| 16 | Procedural locomotion clips (6) → AnimSequence (engine poses match) | PASS | PROC | `reports/audit_m10_generated_motion.json` |
| 17 | Locomotion AnimInstance, PIE transitions Idle→…→Land | PASS (PIE) / NOT VERIFIED (packaged) | NATIVE | `audit_m9_m10_completion.json` |
| 18 | IK Rig + IK Retargeter + batch retarget (`anim_ik_retarget`) | PARTIAL | NATIVE | Real IKRig/IKRetargeter controllers used; per-bone track-level proof still owed (WP-A) |
| 19 | BlendSpaces, foot IK, montages, turn-in-place | PLANNED | — | M10 v2 |
| 20 | Neural text-to-motion | BLOCKED | NEURAL | CUDA |
| 21 | Material creation (basic `create_material`) | PARTIAL | NATIVE | Constant-colour materials only |
| 22 | Material graphs, MIs, Material Functions, PBR texture sets, landscape layers | PLANNED | — | M11 (`MaterialEditingLibrary.h` present in 5.7.4) |
| 23 | Geometry Script procedural props, LOD, collision, UV | PLANNED | — | M12 (`GeometryScripting` plugin present) |
| 24 | Asset registry with provenance/search | PARTIAL | — | Quarantine + provenance JSON exist; no unified registry (WP-A) |
| 25 | Niagara VFX authoring | PLANNED | — | M13 |
| 26 | Audio import, MetaSound, attenuation, gameplay hookup | PLANNED | — | M14 (`MetasoundBuilderSubsystem.h` present) |
| 27 | Speech / music generation | BLOCKED (install approval) / PLANNED | NEURAL/PROC | Registry |
| 28 | GAS, StateTree, BT/EQS, Perception, Smart Objects, quests, inventory, save | PLANNED | — | Gameplay kit + M15 (all plugins present) |
| 29 | Basic enemy AI (AIController MoveTo) | PASS | CODEGEN | Arena recipe |
| 30 | Sequencer + Movie Render Queue | PLANNED | — | M16 |
| 31 | Multiplayer replication tests | PLANNED | — | M18 |
| 32 | Automation tests + packaged self-test + vision review | PASS | — | All recipes |
| 33 | Profiling (Insights/csvprofile), optimization loop | PLANNED | — | M19 |
| 34 | Build / cook / package Win64 | PASS | — | ~860 MB per package |
| 35 | Incremental modification of existing projects | PLANNED | — | M20 / AD-7 |
| 36 | Operation catalogue with read-back enforcement | PLANNED | — | WP-A (76 ops exist, uncatalogued) |
