# GameForge Master Roadmap (M8–M20+) — Executable Playbook

**Author:** Claude Code (Opus 5.5), 2026-10-30T17:10Z. **Audience:** Antigravity and any later agent session.
**Status of this document:** ACTIVE PLAN. It supersedes the milestone ordering in the user's "Master Engineering
Programme M8–20" prompt where they differ. The reasons are given in §2. The security rules in
`GameForge — Master Blueprint.md` (v2) still apply in full.

Read first: `AGENTS.md` → `context.md` (top "CURRENT STATE") → `reports/AUDIT_M1_M10_2026-10-30.md` → this file.
After every work package (WP), update `context.md`, the progress log in `AUTONOMOUS_RUN_STATE.md`, and the
matching row in `GAMEFORGE_COMPLETE_CAPABILITY_MATRIX.md`.

---

## 0. Ground rules (non-negotiable; violating any one invalidates a milestone)

1. **Real engine only.** Acceptance evidence must come from UE 5.7.4 (`E:\UE\UE_5.7`) through the real paths:
   `unreal/live_editor.py`, `unreal/toolchain.py` and `pipeline/game_pipeline.py`. Anything under
   `tests/doubles/` or marked `simulated: True` is never evidence.
2. **No fabricated provenance.** The M9 audit found an Epic sample FBX presented as "generated". Every artifact
   records its *real* source: procedural, neural, imported, human or native-editor.
3. **Neural ≠ procedural.** Do not label anything "AI-generated" unless the selected neural backend actually ran
   and produced it. Neural text-to-3D and text-to-motion are **BLOCKED** on this host (see §4) until proven otherwise.
4. **Every mutation is a named, typed op** in `src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops.py`,
   backed by native C++ in the `GameForgeEditor` module when Python reflection is insufficient. No arbitrary
   editor Python on the normal path. Each op: snapshot → mutate → read-back → evidence.
5. **Protected graders** in `graders/protected/` are never edited. Run both test suites after every WP:
   ```powershell
   $env:TEMP="E:\gameforge_step1\scratch\pytest_os_temp"; $env:TMP=$env:TEMP
   python -m pytest tests/unit/ -q ; python -m pytest graders/protected/ -q
   ```
   Baseline on 2026-10-30: 411 unit + 45 protected, all passing.
6. **Destructive integration tests** run on disposable projects under `E:\GameForge\validation\<wp>_<date>\`,
   never on `GFProbe` or a user project.
7. **Plugin rebuild path:** RunUAT BuildPlugin → `E:\GameForge\validation\GameForgePlugin_<tag>` → copy the
   binaries to the repo's (gitignored) `GameForge/Binaries` and to the probe project. Back up the old binaries first.
   Record the new DLL SHA-256 in `context.md`.
8. **Resource discipline:** 12 GB VRAM. Never run the Unreal Editor and a >6 GB model job at the same time. Use the
   existing GPU/resource scheduler. Ollama calls always pass `"think": False`.
9. **Statuses:** `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, `NOT VERIFIED`, `EXPERIMENTAL`. A milestone is PASS only
   when its acceptance block below is green with real evidence files committed under `reports/`.
10. **No installs, paid services or external data transfer** without explicit user approval. Record such needs as
    `BLOCKED (needs approval)`.

---

## 1. Verified baseline (2026-10-30, from the audit)

| Area | Status | Evidence |
|---|---|---|
| M1 DAG planner + IDE plan runner | PASS | `reports/milestone1_*_demo.json` |
| M2 Blueprint graph ops (9) | PASS | `reports/milestone2_blueprint_demo.json` |
| M3 UMG authoring | PASS | `reports/milestone3_umg_demo.json` |
| M4 Functional UMG + `GameForgeRuntime` state component | PASS | `reports/milestone4_umg_functional_demo.json` |
| M5/M6/M7 platformer / arena / card battler, packaged and real input | PASS | `reports/packaged_real_input_summary.json` |
| M8 procedural world v1 (landscape, spline road, HISM scatter, PCG grid 400, NavMesh, seeds) | PASS (v1 scope) | `reports/audit_m8_completion.json` |
| M9 procedural skinned humanoid (20 bones) → glTF → Interchange → quarantine → promote | PASS (prototype quality) | `reports/audit_m9_generated_character.json`, `audit_m9_m10_completion.json` |
| M10 6 procedural clips → AnimSequence, locomotion AnimInstance, PIE transitions | PASS (v1). Retarget: see WP-10.3 | `reports/audit_m10_generated_motion.json` |
| Neural text-to-3D / text-to-motion | BLOCKED | No CUDA; 12 GB AMD |

**Open doubts that the next session must re-verify before building on them** (marked `[REPORTED]` because the
later claims were written by an agent session without a detailed evidence breakdown):
- "IK retargeting verified": confirm that the retargeted AnimSequence's *bone transform tracks* differ correctly from
  the source and match the target skeleton's proportions (WP-10.3). A skeleton swap is not a retarget.
- "PCG 400 instances": confirm that a real `UPCGGraph`/`UPCGComponent` generated them, and not an HISM loop labelled PCG.
- Code inspection (Claude, 2026-10-30T17:20Z): `pcg_scatter` builds a real `UPCGGraph` + `PCGVolume`, but uses
  `PCGCreatePointsGridSettings` (grid), not the Surface Sampler its docstring claims. `anim_ik_retarget` uses
  real `IKRigController`/`IKRetargeterController` + `IKRetargetBatchOperation` (genuine retarget path), while the
  older `anim_retarget_sequence` is the SetSkeleton copy and must not be cited as retarget evidence.
  What remains is the track-level numeric proof.
- Uncommitted working-tree changes exist in `plan_executor.py`, `procedural_world/templates.py` and
  `gameforge_ops.py`. Review `git diff` before editing those files. Nothing has been committed since `9eeca5b`.

---

## 2. Architectural decisions (Claude's improvements to the proposed programme)

Each entry gives the alternatives, the choice and the reason. Full detail is in `GAMEFORGE_ARCHITECTURE_EVOLUTION.md`.

**AD-1 — One operation catalogue drives everything (adopt before M11).**
*Alternatives:* (a) keep adding ad-hoc `@op` functions per milestone; (b) a generic remote-Python executor;
(c) a declarative catalogue (`configs/unreal_ops_catalog.json` or a Python registry) holding the schema,
permissions, reversibility, read-back op, required plugins/modules and test IDs for every op.
*Choice:* (c). It generates `GAMEFORGE_UNREAL_OPERATION_COVERAGE.md`, the tool-gateway schemas and the planner's
tool list from one source, so no op can be advertised without a read-back and a test.
(b) violates the security model. (a) is what produced the M3/M4 silent-success bugs.

**AD-2 — A generic "graph authoring kernel" in C++ instead of per-domain graph code.**
Blueprint (M2), Material (M11), Niagara (M13, partly), MetaSound (M14), AnimGraph (M10) and PCG graphs are all
`UEdGraph`-like or have builder APIs. Build one C++ abstraction: `CreateNode(type, params)`, `Connect(pinA, pinB)`,
`SetPinDefault`, `ReadBack()` → canonical JSON, `Compile()` → diagnostics. Adapters per graph type:
- Material: `UMaterialEditingLibrary` (CreateMaterialExpression, ConnectMaterialExpressions,
  ConnectMaterialProperty, RecompileMaterial). This is fully scriptable, so it is the **first** adapter.
- MetaSound: `UMetaSoundBuilderSubsystem` / `UMetaSoundSourceBuilder` (AddNodeByClassName, ConnectNodes,
  BuildToAsset). Check the exact 5.7 headers under `Engine/Plugins/Runtime/Metasound/Source/MetasoundEngine/Public`.
- PCG: `UPCGGraph::AddNodeOfType` / `AddEdge`.
- Niagara: the editor graph is not a stable API. Use **emitter templates + module stack parameter overrides**
  (`UNiagaraSystem`, user parameters) as the supported path, and graph editing only as EXPERIMENTAL.
- AnimGraph: keep the native `UAnimInstance` subclass approach (already PASS). AnimBP graph editing stays EXPERIMENTAL.
The read-back JSON is identical across domains, so the planner's acceptance predicates are generic
(`graph_has_node`, `graph_edge`, `graph_compiles`).

**AD-3 — Shared gameplay framework module instead of more recipe templates (reorders M15/M17).**
The four recipes each carry their own Character/GameMode/HUD C++. Extract a `GameForgeRuntime` gameplay kit
(the module already exists): interaction component, health/damage via **GAS** (AttributeSet + GameplayEffects),
inventory component, objective/quest subsystem, save-game subsystem, dialogue data assets, and a camera rig
component. New genres become *compositions* of kit components plus content. The existing recipes migrate
gradually, and only after their tests are green on the kit. Use native systems: GAS, StateTree, EQS, AI Perception,
Smart Objects, Enhanced Input, CommonUI where suitable. Do not invent parallel frameworks.

**AD-4 — Artifact lifecycle as a single registry (`asset_registry`) shared by all pipelines.**
SPEC → GENERATE → POSTPROCESS → VALIDATE → QUARANTINE → IMPORT → ENGINE-VERIFY → REVIEW → PROMOTE. Each asset
is an SQLite row (stays lightweight in the IDE) in `<workspace>/.gameforge/assets.db`, with sha256 values,
provenance class, backend+version+license, dependencies, the evidence file list and a preview path. Build it on the
existing quarantine pipeline (`QuarantinePipeline` + `live_operations.py`). Semantic search uses the existing local
embedding/LLM stack only if it is cheap. Start with SQL LIKE + tags, and add embeddings only when measured useful.

**AD-5 — Procedural-first specialist policy for this host.**
On a 12 GB AMD GPU under Windows (ROCm on Windows is limited; most 3D/motion research code is CUDA-only), the
canonical backends are **deterministic procedural generators plus native Unreal tools**. Neural backends are
admitted one per capability, and only after a measured local run passes (see `GAMEFORGE_SPECIALIST_REGISTRY.md`).
The candidates to evaluate first are those runnable via DirectML/ONNX or llama.cpp-Vulkan. The existing Ollama
vision model (`gameforge-qwen3.5-4b` + mmproj) is the canonical vision-review backend.

**AD-6 — Reorder: materials before props, world v2 after materials, gameplay kit before genres.**
M11 materials are a prerequisite for M12 assets, M8 v2 biomes, M9 character skins and M13 VFX materials.
New order (§3).

**AD-7 — Incremental project model ("project graph").**
For M20's "modify an existing game" requirement, keep a `<project>/Saved/GameForge/project_graph.json` index of
GameForge-owned assets, actors, C++ classes and their generating WP/spec hashes. Regeneration touches only nodes
whose spec hash changed, and user-edited assets (`modified_by_user` detected via package save-time/hash mismatch)
are never overwritten without approval.

**AD-8 — QA harness unifies existing pieces.** `real_input.py` + `GF_EVENT` log markers + automation tests +
`-GFSelfTest` + vision review are already the right primitives. M19 should build a scenario DSL
(`scenarios/*.yaml`: inputs → expected GF_EVENTs → screenshot checks) and add Unreal Insights
(`-trace=cpu,gpu,frame,memory` + `UnrealInsights.exe` CSV export / `-csvprofile`) for profiling.

---

## 3. Revised dependency order and work packages

```
WP-A  Foundations: op catalogue (AD-1) + asset registry (AD-4) + verify open doubts
  └─ M11 Materials/Textures (graph kernel adapter #1)
       ├─ M12 3D asset pipeline (props, kits, LOD, collision)
       │    └─ M8 v2 World (biomes, PCG graphs, World Partition, buildings)
       ├─ M9 v2 Character (materials, LODs, proportions)  ──┐
       └─ M13 Niagara VFX                                    │
  M10 v2 Animation (blend spaces, IK, retarget proof) ◄─────┘
  M14 Audio (MetaSound adapter)
  Gameplay kit (AD-3) → M15 AI/NPC/GAS → M17 genres
  M16 Cinematics (needs M9/M10/M14)
  M18 Multiplayer (isolated project; needs kit)
  M19 QA/profiling (start early; scenario DSL used by all)
  M20 Integration + project graph (AD-7) → Flagship demo
```

Each WP below has **steps**, **files**, and **acceptance** items. Do them in order. Inside each WP, run the tests
after each step.

### WP-A — Foundations (do first; ~1 session)
1. Re-verify the open doubts in §1 (retarget tracks, PCG authenticity). Write `reports/wpa_reverify_<date>.json`.
2. Create `src/gameforge_ide/unreal/op_catalog.py`: a dataclass `OpSpec(name, domain, schema, mutates, reversible,
   readback_op, requires_plugins, min_engine="5.7.4", tests=[...], status)`. Populate it from the existing `@op`
   functions in `gameforge_ops.py` (grep `@op("`). Add a unit test that fails if any `@op` lacks a catalogue entry
   or any mutating op lacks `readback_op`.
3. Add `scripts/gen_op_coverage.py` → regenerates `GAMEFORGE_UNREAL_OPERATION_COVERAGE.md`.
4. Create `src/gameforge_ide/backend/assets/registry.py` (SQLite) + migrate the quarantine pipeline to record into it.
   Unit tests for the schema, provenance classes and hash checks.
5. **Acceptance:** both suites green; coverage doc regenerated; one existing promoted asset (the GFAdventurerHero
   skeletal mesh) has a registry row with its real provenance `procedural`.

### M11 — Materials, textures, shaders
1. C++ `UGameForgeMaterialLibrary` (or Python ops if `MaterialEditingLibrary` suffices; check this first, since it
   usually does): create Material, add expressions (TextureSample, Constant3Vector, ScalarParameter,
   VectorParameter, TextureCoordinate, Multiply, Lerp), connect to material properties, set usage flags, recompile,
   **read back** the expression graph + compile errors (`UMaterial::GetMaterialResource → GetCompileErrors`).
2. Texture import ops: sRGB on/off by channel role, compression (`TC_Normalmap`, `TC_Masks` for packed ORM),
   validation of resolution/power-of-two/channel content.
3. Material Instance Constant creation + parameter set + read-back. Material Functions: create + call.
4. Procedural PBR texture generator (Python, numpy; no new deps if numpy is present): noise-based albedo,
   height→normal, roughness, AO, packed ORM. Provenance `procedural`.
5. Landscape layered material (LandscapeLayerBlend) + paint layers via `ULandscapeInfo` (needed by M8 v2).
6. **Acceptance demo** `scripts/demo_m11_material.py` on a disposable project: generate a PBR set → import → build
   M_ + MI_ → assign to a mesh actor → screenshot with vision review + pixel statistics showing the texture is visible
   (not the default checker) → reload editor → read-back is identical. Evidence: `reports/m11_material_demo.json`.

### M12 — 3D asset production
1. Asset spec schema (`backend/models/asset_spec.py`): category, dimensions in cm, tri budget, LOD count,
   collision type, material slots.
2. Procedural mesh backend: Unreal **Geometry Script** (`GeometryScriptingCore` plugin; check that it is enabled in
   5.7.4): primitives, booleans, extrude, UV auto-unwrap (`AutoGenerateXAtlasMeshUVs` or `PatchBuilder`),
   simplify → `CreateNewStaticMeshAssetFromMesh`. This is better than Python mesh code because the ops run in-engine
   and produce native assets directly.
3. Modular kit generator (walls/floors/doors on a 400 cm grid) for M8 v2 villages/dungeons.
4. LODs (`StaticMeshEditorSubsystem.set_lods` / reduction settings), collision (simple + complex), Nanite flag where
   appropriate, read-back of tri counts per LOD.
5. Registry + preview thumbnail (`viewport_screenshot` of an isolated preview scene).
6. **Acceptance:** one prop (e.g. crate or lantern) passes spec → generation → LOD/collision → material (M11) →
   quarantine → promote, with read-back and screenshot. `reports/m12_asset_demo.json`.

### M8 v2 — World generation
1. Real PCG graph authoring (graph kernel adapter): Surface Sampler → Density Filter → Static Mesh Spawner, with a
   biome attribute filter. Verify `UPCGComponent::Generate` produced managed ISM components.
2. Biomes: forest/desert/island/mountain presets → heightfield params + landscape layer weights + PCG asset sets.
3. Modular buildings / village from M12 kits; dungeon = grid layout generator + kit.
4. Lighting presets (SkyAtmosphere, SkyLight, DirectionalLight, ExponentialHeightFog, VolumetricCloud).
5. World Partition for maps above a threshold size; Data Layers for generated vs user content (supports AD-7).
6. **Acceptance:** "create a forest village" → saved level; NavMesh path between 2 POIs; seed A=B; regeneration
   with a changed seed preserves a user-placed actor; packaged real-input traversal.

### M9 v2 — Character
1. Fix proportions/topology: increase segment resolution, separate hand/foot geometry, smooth skin weights
   (geodesic falloff), verify inverse bind matrices against the engine reference pose.
2. Materials from M11 (skin/cloth regions by UV island). LODs + physics asset (`UPhysicsAsset` auto-generate).
3. Evaluate the neural/auto-rig options in the registry (§4). Integrate only if one runs locally.
4. **Acceptance:** spec → mesh → rig → import → physics asset → material → preview in PIE with M10 animations,
   no visible candy-wrapping at 90° elbow/knee (vision review + max vertex displacement metric).

### M10 v2 — Animation
1. WP-10.1 BlendSpace1D (Speed) built natively (`UBlendSpace` sample points via C++), driven by the locomotion
   AnimInstance; start/stop and turn-in-place clips from the procedural synthesizer.
2. WP-10.2 Foot IK: Control Rig or `TwoBoneIK` in the AnimInstance; measure foot-ground penetration on a slope.
3. WP-10.3 **Retarget proof:** IK Rig + IK Retargeter assets (`IKRigEditor` controllers in 5.7:
   `UIKRigController`, `UIKRetargeterController`; confirm in headers) from GF skeleton → UE5 Manny (engine content)
   and back. Batch export via `UIKRetargetBatchOperation` or the retargeter's export function. Evidence:
   per-bone world-space comparisons at N frames between the source pose and the retargeted pose (with tolerances).
4. Montages: attack montage + notify → gameplay event.
5. **Acceptance:** PIE and **packaged** character showing idle→walk→run→jump→fall→land, with GF_EVENT markers and
   anim-state log lines; the retarget evidence JSON passes.

### M13 — Niagara VFX
1. Ops: create a system from an engine template emitter (Fountain, Burst, Hanging Particulates…), set user
   parameters/rapid-iteration parameters, set the renderer material (M11), and set GPU/CPU sim target.
2. VFX spec presets: fire, smoke, sparks, rain, snow, magic burst, impact, trail.
3. Gameplay trigger: `UNiagaraFunctionLibrary::SpawnSystemAtLocation` on a GF_EVENT (e.g. pickup).
4. **Acceptance:** an effect spawned by a real gameplay event in PIE; read-back of the active particle count
   (`UNiagaraComponent` → `GetSystemInstanceController` / debug HUD) > 0; screenshot; `stat Niagara` cost recorded.

### M14 — Audio
1. Procedural SFX synthesizer (numpy → 16-bit WAV): click, whoosh, impact, pickup chime, ambient wind loop.
   Provenance `procedural`.
2. Import ops (`USoundWave`), SoundCue or MetaSound Source via the builder API, Sound Class/Mix, Attenuation
   (spatialization), Submix reverb.
3. Gameplay hookup: play at a location on a GF_EVENT.
4. Neural TTS/music: evaluate per the registry. Piper TTS (ONNX, CPU, MIT code; voice licenses vary per voice)
   is the leading candidate for speech. Music stays procedural/MetaSound until a licensed local model passes.
5. **Acceptance:** sound plays in PIE/packaged at an event, with an audio log marker (`au.Debug.Sounds` or a
   `UAudioComponent::OnAudioPlaybackPercent` probe) and attenuation verified by distance read-back.

### Gameplay kit (AD-3) → M15 AI/NPC
1. Enable the `GameplayAbilities`, `StateTree`, `GameplayStateTree`, `SmartObjects`, `EnhancedInput` plugins in
   generated projects (`.uproject` edit through the scaffolder).
2. Kit components in `GameForgeRuntime`: `UGFInteractionComponent`, `UGFInventoryComponent`, `UGFObjectiveSubsystem`,
   `UGFSaveSubsystem` (USaveGame), `UGFDialogueComponent` (data-asset driven), GAS `UGFAttributeSet` (Health,
   Stamina, Damage meta-attribute).
3. AI: Behavior Tree + Blackboard creation ops (`UBehaviorTree`, `UBlackboardData`; BT graph authoring through
   `UBehaviorTreeGraph` is editor-only and fragile, so prefer **StateTree** with C++ tasks), AI Perception sight/hearing.
4. **Acceptance:** an NPC guard with patrol → perceive player → chase → lose → return, plus a quest giver whose
   dialogue updates an objective that persists through save/load. Tested in PIE with GF_EVENT markers.

### M16 — Cinematics
1. Ops: `ULevelSequence` create, bind actors (possessables/spawnables), CineCameraActor + camera cut track,
   transform keys, animation track (M10 clip), audio track (M14), event track.
2. Movie Render Queue job (`UMoviePipelineQueueSubsystem`) → PNG sequence → frame inspection (vision + pixel diff
   between shots to prove the cuts).
3. **Acceptance:** a 3-shot sequence rendered to frames; cut frames are detected; audio is present in the sequence
   read-back.

### M17 — Genres via the kit
Priority: third-person action-adventure (it is the flagship), then roguelike dungeon (reuses M8 v2 dungeon), then
FPS. Each genre needs a playable vertical slice, automation tests, packaged real input and GF_EVENT assertions.

### M18 — Multiplayer (isolated project)
Listen server + 2 clients via `-server`/`-game` with `-ExecCmds` and `-log`. Replicated health/score via the kit,
server-authoritative damage. Use `Net PktLag`/`PktLoss` console vars for lag tests. Evidence is the logs of all three
processes agreeing on the final state. No public infrastructure.

### M19 — QA / profiling (start in parallel with M11)
Scenario DSL; `-csvprofile` + Insights trace; a budget file per game; optimization loop: measure → change one
thing → re-measure → keep only if improved without vision-review regression.

### M20 — Integration + flagship
Project graph (AD-7), a multi-workstream plan generator over the catalogue, incremental regeneration.
Flagship: **"Ember Vale"**, a compact third-person action-adventure: forest village (M8 v2) with a dungeon, procedural
hero (M9 v2) with locomotion (M10 v2), PBR props (M11/M12), guard AI + quest giver (M15), fire/impact VFX (M13),
spatial SFX (M14), intro cinematic (M16), HUD/menus (M3/M4), QA scenarios (M19), packaged build.

---

## 4. Specialist backends: current decisions (details in `GAMEFORGE_SPECIALIST_REGISTRY.md`)

| Capability | Canonical now | Neural candidate to evaluate (one only) | Status |
|---|---|---|---|
| Reasoning | 4-model roster (unchanged) | n/a | PASS |
| Vision review | gameforge-qwen3.5-4b + mmproj (Ollama) | n/a | PASS (advisory) |
| Mesh (props) | UE Geometry Script (procedural) | TripoSR/Hunyuan3D need CUDA | BLOCKED neural |
| Character | ProceduralSkinnedCharacterGenerator | none viable locally | BLOCKED neural |
| Rigging | procedural rig (own skeleton) | UniRig/RigNet need CUDA | BLOCKED neural |
| Motion | ProceduralKinematicMotionSynthesizer | MDM/MoMask need CUDA | BLOCKED neural |
| Textures/PBR | procedural numpy generator (M11) | SD-family via DirectML/ONNX: not installed | NOT VERIFIED |
| Speech | none yet | Piper (ONNX, CPU) needs install approval | BLOCKED (approval) |
| Music/SFX | procedural synth + MetaSound | none | PLANNED |

---

## 5. Next action (always keep current)

Done 2026-10-30T17:45Z: WP-A steps 2–3 (`unreal/op_catalog.py`, `scripts/gen_op_coverage.py`) and step 4 core
(`backend/assets/registry.py`). 419 unit + 45 protected pass.

1. ~~WP-A step 4b~~ DONE 18:15Z (quarantine → registry; TRELLIS.2 mislabel fixed). Remaining: wire the registry
   into `pipeline/character_pipeline.py` and `pipeline/animation_pipeline.py` (both build `AssetProvenanceRecord`
   directly) and backfill the GFAdventurerHero row (provenance `procedural`, evidence
   `reports/audit_m9_m10_completion.json`).
2. **WP-A step 1**: re-verify retarget-track authenticity (per-bone world-space comparison) and PCG on a disposable
   project; write `reports/wpa_reverify_<date>.json`.
3. M11, starting with the procedural PBR texture generator (`backend/tools/pbr_texture_generator.py`, if not
   already present), then the material graph ops.
