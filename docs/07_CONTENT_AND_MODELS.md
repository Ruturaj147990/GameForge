# Content Pipelines, Specialist Backends and Models

**Owner:** Claude. **Consolidated:** 2026-10-31 from `GAMEFORGE_SPECIALIST_REGISTRY.md`, `GAMEFORGE_MULTIMODAL_PIPELINES.md`,
`context.md` §D and the model reports in `reports/`. Rule: **one active canonical backend per capability, no silent
substitution, and a NEURAL claim needs a measured local run on this host.** Installing any backend needs the user's
approval.

---

## 1. Language models (canonical roster, D-044: exactly four local LLMs)

| Model | Ollama ID | GGUF SHA-256 | Speed | Context tested | Role default (from P0) |
|---|---|---|---|---|---|
| `gameforge-qwen3.5-9b:latest` | `278e024c31f7` | `e1a7d1a50527609e7ebe8aa78c31388103d29495e6b46b16dc0d24ee4fccc906` | 63.9 tok/s | 67.5K | chat, design, codegen |
| `gameforge-qwen3.5-4b:latest` | `91b2043beeee` | `2353155701a96721e78f20ce75af22db5b93cfdbdb90e4c0d73faf48c0658431` | 102.8 tok/s | 121.9K | fast, vision (with mmproj) |
| `gameforge-27b-sft:latest` | `03d36e692be8` | `d73eb68413c0226e1a4a24c81a987d611b7b7375af8594fbebfa7aec4b912f2b` | 5.4 tok/s | 4K | heavy_local (editor closed) |
| `llama3.1:8b` | `46e0c10c039e` | `667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29` | 77.3 tok/s | 8K | baseline |

- Vision projectors: 9B `sha256:f836f08f…` (921 MB), 27B `sha256:ac3714bf…` (931 MB), 4B `sha256:e56a899b…` (675 MB).
- Storage: `$env:OLLAMA_MODELS = "E:\GameForge\models\ollama"`; binary `E:\GameForge\ollama_bin\ollama.exe` (Vulkan).
- **Always** `"think": false` and an explicit `num_ctx` on programmatic calls.
- Training lineage: `reports/gameforge-27b-sft/`, `reports/GAMEFORGE_QWEN35_*`, `reports/GAMEFORGE_TRAINING_*`, datasets
  under `E:\GameForge\datasets\`. Never overwrite a tag or Modelfile without a rollback copy.
- Measured on GameForge Agentic Eval Suite (P9, `reports/P9/eval_*.json`):
  - gameforge-qwen3.5-4b:latest: 38.9% pass rate, 94.4% valid JSON, 101.1 tok/s, p90 latency 3.83s (routed to `fast`, design, codegen, `vision`).
  - gameforge-qwen3.5-9b:latest: 33.3% pass rate, 83.3% valid JSON, 63.4 tok/s, p90 latency 62.67s (routed to chat).
  - llama3.1:8b: 33.3% pass rate, 100.0% valid JSON, 76.4 tok/s, p90 latency 2.81s (baseline).
  - gameforge-27b-sft:latest: 25.0% pass rate, 75.0% valid JSON, 6.0 tok/s, p90 latency 120.01s (routed to heavy_local).
- Routing table generated from empirical evidence: src/gameforge_ide/config/model_routing.json (WI-9.3).
- Hosted tier (product target, opt-in per workspace): `backend/providers/hosted.py` (Anthropic Messages +
  OpenAI-compatible, SSE, tool calls, Credential Manager keys, spend ledger, caps, no silent fallback). Status: tested
  only against a local mock. P9 WI-2 validates it live with the user's key.
- **GameForge-hosted inference gateway: design only, not scheduled.** The design (inference-only service, TLS,
  tenant auth, bounded queues, provider-neutral tool-call mapping, usage ledger; client tools stay local) is preserved
  in `docs/history/HOSTED_GATEWAY_DESIGN_2026-10-24.md`.

## 2. Content backends per capability

| Capability | Canonical now | Next (phase) | Neural candidate | Status |
|---|---|---|---|---|
| Vision review | 4B + mmproj (advisory) | calibrated rubric (P7) | hosted vision (P9) | PASS (advisory) |
| Character mesh + rig | `ProceduralSkinnedCharacterGenerator` (prototype) | Epic Manny/Quinn (P7, `EPIC_CONTENT`); MetaHuman scripting (P7 spike, cloud consent) | none viable locally | PASS (prototype) |
| Animation | procedural kinematic clips (M10) + IK retarget | template mannequin anims via `ABP_Unarmed` (P7); GASP motion matching if the user adds it | MDM/MoMask (CUDA + SMPL licence) | PASS v1 |
| Props / architecture | Geometry Script (M12), modular kit | role recipes + themes (P7) | Hunyuan3D-2.1 shape-only via ROCm Windows (P9 spike) | PASS |
| Terrain / world | landscape library + PCG surface sampling + biomes (M8 v2) | real vegetation meshes via roles (P7); WP landscape (P10) | — | PASS v2 |
| Textures / PBR | numpy procedural generator (M11) | themes (P7) | SD-family via ONNX/DirectML (needs approval + licence) | PASS |
| Materials | `material_build_graph` / MIs (M11) | master materials + themes (P7) | — | PASS |
| VFX | Niagara template systems + parameters (M13) | preset library bound to events (P7) | — | PASS (PIE) |
| SFX | numpy synth + MetaSound builder (M14) | per-set presets (P7) | — | PASS (PIE) |
| Music | none | procedural mood loops (P7) | licensed model only after review | PLANNED |
| Speech | none | — | Piper TTS (CPU, MIT engine; per-voice licence) (P9 spike) | BLOCKED (approval) |

**Hardware status update (2026-10-31):** AMD's HIP SDK 7.2 for Windows lists the RX 7700 XT (gfx1101) as supported, and
Hunyuan3D-2.1 shape generation is reported to work natively on Windows ROCm 7.2. "Neural blocked on AMD" is therefore
**superseded**. The correct state is *BLOCKED pending install approval and a measured 12 GB spike* (P9 WI-9.5).

## 3. Asset lifecycle (all pipelines)

`SPEC → GENERATE → POSTPROCESS → VALIDATE → QUARANTINE → IMPORT → ENGINE_VERIFY → REVIEW → PROMOTE`

Each stage is an event in the per-workspace SQLite registry (`backend/assets/registry.py`). PROMOTE requires a passed
ENGINE_VERIFY. Required fields: asset id, purpose, **provenance class**, backend + version + licence, input spec
SHA-256, generation config, output format, tool versions, artifact SHA-256, dependencies, validation results, evidence
files, and approval/promotion history. Quarantine: `/Game/Quarantine/<Type>/`. Promoted: `/Game/<Type>/<Name>/`.
**A file format is not an asset**: a glTF, PNG or WAV counts only after import, configuration and engine verification.

### Provenance and licence classes

| Class | Meaning | Licence record |
|---|---|---|
| `PROC` | GameForge procedural generator ran | "GameForge-Generated (project-owned)" |
| `NATIVE` | built in-editor by ops (Geometry Script, PCG, material graphs) | same |
| `CODEGEN` | model-written code | same, plus the model id |
| `EPIC_CONTENT` | engine or Epic sample content (Manny, LevelPrototyping, GASP, Starter Content) | "Unreal Engine EULA" |
| `LIBRARY` | user-imported pack (Fab, Megascans, CC0, …) | the user-selected licence + text, confirmed in the UI |
| `NEURAL` | a neural backend actually ran | the model card licence + territory rules (`LicenseRegistry`) |
| `HUMAN` | user-authored | user |

A pipeline that accepts a backend name must verify that the backend ran. Lesson: on 2026-10-30, procedural meshes
were labelled `TRELLIS.2`.

## 4. Pipelines (status)

| Pipeline | Generate | Validate | Engine verify | Status |
|---|---|---|---|---|
| Character | `character_generator.py` → glTF | `character_rig_validator.py` | Interchange import → inspect → deformation → promote | PASS (prototype) |
| Motion | `motion_generator.py` | `animation_validator.py` | `anim_import_motion_clip` → `anim_sample_bone_pose` | PASS |
| World | biomes + landscape + PCG ops | NavMesh path, seed digest | `procedural_world_inspect`, `world_generation_digest` | PASS |
| Material/texture | `pbr_texture_generator.py` | channel/sRGB/size checks | import → M_/MI_ → screenshot | PASS |
| Static mesh | Geometry Script (`mesh_generate_prop`) | tri budget, LOD counts | LOD/collision read-back, thumbnail | PASS |
| VFX | Niagara templates | particle counts | spawn on event (PIE) | PASS (PIE) |
| Audio | `sfx_synth.py`, MetaSound builder | duration/loop checks | play on event (PIE) | PASS (PIE) |
| Cinematic | Sequencer ops | shot list | MRQ render + cut detection | PASS |
| Epic content packs | copy template folders | sentinel `asset_exists` | skeletal mesh inspect | PLANNED (P7) |
| Content library | user packs | user licence confirmation | `asset_migrate` + inspect | PLANNED (P7) |
