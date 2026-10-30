# GameForge Multimodal Pipelines

Updated 2026-10-30T17:20Z (Claude Code).

## Common artifact lifecycle (all asset types)
`SPEC → GENERATE → POSTPROCESS → VALIDATE → QUARANTINE → IMPORT → ENGINE-VERIFY → REVIEW → PROMOTE`

Each stage writes to the asset registry (planned, WP-A, `backend/assets/registry.py`). Required fields: asset_id,
purpose, provenance class (PROC/NEURAL/IMPORTED/HUMAN/NATIVE/CODEGEN), backend + version + licence, input spec
sha256, generation config, output format, tool versions, artifact sha256, dependencies, validation results,
evidence files, approval/promotion history. Quarantine path: `/Game/Quarantine/<Type>/`. Promoted:
`/Game/<Type>/<Name>/`.

## Pipelines

| Pipeline | Generate | Postprocess / validate | Import / engine verify | Status |
|---|---|---|---|---|
| Character | `character_generator.py` → glTF (skin, IBMs, Y-up, metres) | `character_rig_validator.py` (hierarchy, weights, FK stress) | Interchange import → `character_inspect_skeletal_mesh` → `character_measure_deformation` → promote | PASS (prototype) |
| Motion | `motion_generator.py` → JSON tracks | `animation_validator.py` (unit quats, loops, jitter) | `anim_import_motion_clip` → `anim_sample_bone_pose` matches synthesis | PASS |
| World | `ProceduralWorldParams` → landscape/spline/scatter/PCG ops | NavMesh path, seed digest | `procedural_world_inspect`, `world_generation_digest` | PASS (v1) |
| Material/texture | numpy PBR maps (planned) | channel/sRGB/size checks | texture import → M_/MI_ graph → assign → screenshot | PLANNED M11 |
| Static mesh | Geometry Script (planned) | tri budget, UV overlap, LOD counts | collision/LOD read-back, preview thumbnail | PLANNED M12 |
| VFX | Niagara template + params | particle count, cost | spawn on GF_EVENT | PLANNED M13 |
| Audio | numpy synth WAV | peak/RMS/length, loop seam | SoundWave/MetaSound, attenuation, play on event | PLANNED M14 |
| Cinematic | Sequencer ops | shot list check | MRQ render → frame inspection | PLANNED M16 |

## Format ≠ asset
A glTF, PNG or WAV is not a production asset until it is imported, configured (compression, sRGB, LODs,
collision, attenuation), referenced by gameplay, and verified in-engine. Pipelines are PASS only at ENGINE-VERIFY or later.
