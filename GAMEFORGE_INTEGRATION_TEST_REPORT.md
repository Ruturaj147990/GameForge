# GameForge Integration Test Report

Updated 2026-10-30T19:45Z (Claude Code, autonomous window #2). This report only collects results that were
actually executed. Every engine run below used a disposable copy of `E:\GameForge\validation\live_ops_probe`
(path in each report's `project` field), UE 5.7.4, `-RenderOffscreen`, and ended with a graceful editor exit 0.

## Latest executed results
| Date | Command | Result | Evidence |
|---|---|---|---|
| 2026-10-30 | `python -m pytest tests/unit/` | 411 passed, exit 0 | `reports/AUDIT_M1_M10_2026-10-30.md` §4 |
| 2026-10-30 | `python -m pytest graders/protected/` | 45 passed, exit 0 | same |
| 2026-10-30 | `scripts/audit_rebuild_games.py` | 4 games × 8 stages OK | `reports/audit_20261030_pipeline_runs.json` |
| 2026-10-30 | `scripts/verify_real_input_packaged.py` | 3/3, 4/4, 7/7, 4/4; 0 leaked processes | `reports/packaged_real_input_summary.json` |
| 2026-10-30 | M8 completion checks | 6/6 PASS | `reports/audit_m8_completion.json` |
| 2026-10-30 | M9/M10 completion checks | 10/10 PASS | `reports/audit_m9_m10_completion.json` |
| 2026-10-30 | `python scripts/backfill_registry_hero.py` | GFAdventurerHero row at stage PROMOTE (idempotent) | `E:\GameForge\validation\live_ops_probe\.gameforge\assets.db` |
| 2026-10-30 | `python scripts/wpa_reverify.py` | 10/10 PASS (run 1 FAIL: own sampling bug, fixed) | `reports/wpa_reverify_20261031.json` |
| 2026-10-30 | `python scripts/demo_m11_material.py` | 14/14 PASS (runs 1–3 exposed 3 op bugs, fixed) | `reports/m11_material_demo.json` + `m11_mi.png` |
| 2026-10-30 | `python scripts/demo_m12_asset.py` | 9/9 PASS (run 2 PARTIAL: LOD floor on a 98-tri mesh) | `reports/m12_asset_demo.json` + `m12_crate.png` |
| 2026-10-30 | `python scripts/demo_m12_kit.py` | 5/5 PASS | `reports/m12_kit_demo.json` + `m12_kit_room.png` |
| 2026-10-30 | AutomationTool BuildPlugin (GameForge) | exit 0, 0 warnings (2 earlier compile errors fixed) | `scratch/plugin_build_m11.log`, `E:\GameForge\validation\GameForgePlugin_m11` |
| 2026-10-30 | `python scripts/demo_m11_landscape.py` | 7/7 PASS (run 1: deferred weight merge + over-exposure) | `reports/m11_landscape_demo.json` + `m11_landscape_ev10.png` |
| 2026-10-30 | `python scripts/demo_m8v2_pcg.py` | 4/4 PASS | `reports/m8v2_pcg_demo.json` + `m8v2_surface_pcg.png` |
| 2026-10-30 | `python -m pytest tests/unit/` / `graders/protected/` | 475 passed / 45 passed, exit 0 | — |
| 2026-10-30 | `python scripts/demo_m8v2_village.py` | 10/10 PASS (run 1: editor crash from a fixed landscape spawn name; C++ fixed) | `reports/m8v2_village_demo.json` + `m8v2_village.png` |
| 2026-10-30 | AutomationTool BuildPlugin (m13: VFX library + unique spawn names) | exit 0 | `scratch/plugin_build_m13.log`, `E:/GameForge/validation/GameForgePlugin_m13` |
| 2026-10-30 | `python scripts/demo_m13_vfx.py` | 3/3 PASS (run 1: emitter-composed system empty; switched to template systems) | `reports/m13_vfx_demo.json` + `m13_vfx_pie.png` |
| 2026-10-30 | `python scripts/demo_m14_audio.py` (real audio device) | 7/7 PASS (run 1: `spawn_sound_at_location` returned None; switched to AmbientSound components) | `reports/m14_audio_demo.json` |
| 2026-10-30 | `python scripts/demo_m10v2_blendspace.py` | 4/4 PASS | `reports/m10v2_blendspace_demo.json` |
| 2026-10-30 | `python scripts/demo_m16_sequence.py` (runs 2–5) | 6/8 PARTIAL: sequence/read-back/scrub PASS; MRQ frames all black in all three runs (offscreen, windowed, daylight sun, new-process executor) → cut checks FAIL | `reports/m16_sequence_demo.json` |
| 2026-10-30 | `python scripts/perf_village_pie.py` | 3/3 PASS after a host-side parser fix (1,190 frames, 8.34 ms mean) | `reports/m19_perf_village.json` |
| 2026-10-30 | `python -m pytest tests/unit/` / `graders/protected/` | 489 passed / 45 passed, exit 0 | — |

| 2026-10-31 | `python scripts/demo_m16_sequence.py` (runs 6–8) | 8/8 PASS: Unlit diagnostic proved MRQ/cuts fine; the root cause was the demo sun facing away from the cameras | `reports/m16_sequence_demo.json`, `reports/m16_lit_frame30.png` |
| 2026-10-31 | AutomationTool BuildPlugin (m10v2: BlendSpace drive + FinalizeBlendSpace) | exit 0, 0 warnings | `scratch/plugin_build_m10v2.log` |
| 2026-10-31 | `python scripts/demo_m10v2_blend_drive.py` | 10/10 PASS (run 1: empty weights, runtime segments not built; fixed natively) | `reports/m10v2_blend_drive_demo.json` |
| 2026-10-31 | `python -m pytest tests/unit/` / `graders/protected/` | 489 passed / 45 passed, exit 0 | — |
| 2026-10-31 | AutomationTool BuildPlugin (m13v2: AGameForgeVFXPickup, Runtime→Niagara) | exit 0 | `scratch/plugin_build_m13v2.log` |
| 2026-10-31 | `python scripts/demo_m13_gameplay_vfx.py` | 5/5 PASS on the first run (script later superseded by demo_gameplay_feedback.py when the class became AGameForgePickup) | `reports/m13_gameplay_vfx_demo.json`, `reports/m13_gameplay_vfx.png` |
| 2026-10-31 | `python scripts/diag_m14_spawn_sound.py` (diagnostic) | run 1: sound=None (EditorAssetLibrary refuses during PIE); run 2 after the fix: all 4 spawn variants return playing components | `reports/m14_spawn_diag.json` |
| 2026-10-31 | AutomationTool BuildPlugin (m14v2: AGameForgePickup with VFX+SFX) | exit 0 | `scratch/plugin_build_m14v2.log` |
| 2026-10-31 | `python scripts/demo_gameplay_feedback.py` | 10/10 PASS (run 1 9/10: the test polled too slowly for the 0.35 s chime; fixed in the test) | `reports/gameplay_feedback_demo.json` |
| 2026-10-31 | `python scripts/demo_m14_audio.py` | 8/8 PASS incl. spawn_sound_at_location; evidence-aliasing bug fixed | `reports/m14_audio_demo.json` |
| 2026-10-31 | `python scripts/demo_m14_metasound.py` | 5/5 PASS on the first run (stops by itself at 0.68 s) | `reports/m14_metasound_demo.json` |
| 2026-10-31 | `python scripts/demo_m8v2_village.py` (runs 3–5) | 15/15 PASS. Run 3: PCG volumes missing (my helper got bound to `@op("pcg_build_graph")`; fixed + unit test). Run 4: 14/14, but "0 inside" was not discriminating. Run 5 adds a dense control: 243 inside without exclusion → 0 with | `reports/m8v2_village_demo.json`, `reports/m8v2_village.png` |
| 2026-10-31 | `python -m pytest tests/unit/` / `graders/protected/` | 491 passed / 45 passed, exit 0 | — |
| 2026-10-31 | `python scripts/demo_m8v2_datalayers.py` (runs 1–5) | 9/9 PASS. Runs 1–4 exposed: WP partition flag unreadable from World; only loaded actors visible after restart; `get_actor_descs` return shape; SoftObjectPath `str()`; descriptors pending until save. All fixed in the ops | `reports/m8v2_datalayers_demo.json` |
| 2026-10-31 | AutomationTool BuildPlugin (m15: AGameForgeGuard, Runtime → GameplayTasks/NavigationSystem) | exit 0 (run 1: C4458 shadowing fixed) | `scratch/plugin_build_m15.log` |
| 2026-10-31 | `python scripts/demo_m15_guard.py` (runs 1–5) | 6/6 PASS. Run 1: editor crash (MoveTo recursion in OnMoveCompleted). Runs 2–4: patrol stuck on its spawn point (degenerate path → Invalid) and a too-weak resume check. All fixed | `reports/m15_guard_demo.json` |
| 2026-10-31 | AutomationTool BuildPlugin (m15b: objectives subsystem, quest giver, pickup ObjectiveId; Runtime → Json) | exit 0 (run 1: missing Json module link) | `scratch/plugin_build_m15b.log` |
| 2026-10-31 | `python scripts/demo_m15_quest.py` (runs 1–2) | 8/8 PASS. Run 1: gameplay and save/load already worked per GF_EVENTs, but the read op failed (`SubsystemBlueprintLibrary` missing in Python); added `GetForWorld` | `reports/m15_quest_demo.json` |
| 2026-10-31 | `python scripts/package_kit_selftest.py` (runs 1–2) | PARTIAL 5/6. Cooked build: quest/objectives/save→restore in a new process, guard perception: PASS. `walk_physically_plausible` FAIL: legs took ≤0.01 s, so the pawn was snapped, not walked. Run 1: self-test index crash + JSON string-match bug, fixed | `reports/kit_packaged_selftest.json` |
| 2026-10-31 | `python -m pytest tests/unit/` / `graders/protected/` | 491 passed / 45 passed, exit 0 | — |
| 2026-10-31 | `python -m pytest tests/unit/` / `graders/protected/` | 489 passed / 45 passed, exit 0 | — |

## Required for every future WP (template)
Command · exit code · log path · read-back JSON · screenshot path · packaged check (if game-affecting) ·
unit + protected counts.
