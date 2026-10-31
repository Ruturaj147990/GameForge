# GameForge Master Roadmap (M8–M20+) — Executable Playbook

**Author:** Claude Code (Opus 5.5), 2026-10-30T17:10Z. **Audience:** Antigravity and any later agent session.
**Status of this document:** ACTIVE PLAN. It supersedes the milestone ordering in the user's "Master Engineering
Programme M8–20" prompt where they differ. The reasons are given in §2. The security rules in
`GameForge — Master Blueprint.md` (v2) still apply in full.

Read first: `AGENTS.md` → `context.md` (top "CURRENT STATE") → `reports/AUDIT_M1_M10_2026-10-30.md` → this file.
After every work package (WP), update `context.md` and the
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

**Status at 2026-10-31T10:00Z (Claude, interactive session).** Tests: 491 unit + 45 protected pass. Nothing committed.
Done on 2026-10-31 (details in items 1–6 below):
- M16 cinematic 8/8.
- M10 v2 blend-space drive 10/10.
- M13 + M14 gameplay feedback 10/10 and MetaSound 5/5.
- M8 v2 village 15/15 with PCG exclusion, plus World Partition / Data Layers 9/9.
- M15 guard 6/6 and quest + save/load 8/8.
- Packaged kit self-test **PASS 6/6** (`reports/kit_packaged_selftest.json`): a Character walks physically (legs ~550–600 cm/s); quest, save → restore in a new process, and guard all verified in a cooked game. **Next step #1:** add leg-speed checks to the PIE demos, which use `pie_move_player_to` on a DefaultPawn that may snap.

The list "Done this window" just below is the 2026-10-30 window-#2 record.
Every engine demo runs on a disposable copy of `E:\GameForge\validation\live_ops_probe` (≈3–6 min each) and
writes `reports/<name>.json`. Run them from the repo root with `python scripts/<name>.py`.

**Done this window (evidence in `reports/`):**
- WP-A: PASS. Registry wired everywhere; re-verify 10/10 (`wpa_reverify_20261031.json`).
- M11: PASS. Material demo 14/14 (`m11_material_demo.json`), landscape layers 7/7 (`m11_landscape_demo.json`).
- M12: PASS. Prop 9/9 (`m12_asset_demo.json`), kit 5/5 (`m12_kit_demo.json`).
- M8 v2: surface PCG 4/4 (`m8v2_pcg_demo.json`); forest village acceptance 10/10 (`m8v2_village_demo.json`).
- M13: PARTIAL. 3/3 (`m13_vfx_demo.json`): template systems, PIE spawn, live particle counts.
- M14: PARTIAL. 7/7 (`m14_audio_demo.json`): procedural SFX, import, attenuation, PIE playback + GF_EVENT.
- M10 v2: BlendSpace1D asset 4/4 (`m10v2_blendspace_demo.json`).
- M16: PARTIAL (`m16_sequence_demo.json`). Sequence build, cut/key/audio read-back and scrubbing all PASS.
  MRQ wrote 72 PNG frames, but they are pure black (all zeros), so cut detection is NOT VERIFIED.
- M19: CSV-profiler ops + parser; village PIE capture in `m19_perf_village.json` (see the performance report).

**Next steps, in order (each one: change → run its demo → update this list, the matrix and context.md):**
1. ~~M16 render fix~~ **DONE 2026-10-31T04:45Z, 8/8 PASS.** Root cause: the demo's sun (yaw 160) lit the cube faces
   facing away from the cameras, and there is no sky atmosphere, so the visible faces were exactly 0. An Unlit-pass
   diagnostic (`sequence_render` now takes `render_pass` and `warmup_frames`) proved the cameras, cuts and MRQ were
   fine. Lesson: before blaming MRQ, render Unlit. Old notes follow.
   MRQ PNGs are RGBA 640x360 with RGB = 0 and alpha = 255 on every frame. Ruled out:
   `-RenderOffscreen` (run 3 used a visible window) and exposure (run 4: 20,000-lux sun + SkyLight, no manual
   exposure volume). Next suspects, in order:
   (a) the job's deferred pass needs `MoviePipelineDeferredPassBase` settings, or the default "FinalImage"
   render-pass layer is empty without a `MoviePipelineGameOverrideSetting`;
   (b) ~~`MoviePipelineNewProcessExecutor`~~ tried in run 5 (`sequence_render` now takes `executor`): still black;
   (c) render one frame via `HighResShot` from each CineCamera as a fallback cut check.
   Pass = `cuts_detected_at_24_and_48` and `shots_show_expected_colours` true in `reports/m16_sequence_demo.json`.
2. ~~M10 v2 WP-10.1 drive~~ **DONE 2026-10-31T05:30Z, 10/10 PASS** (`scripts/demo_m10v2_blend_drive.py`,
   plugin build **m10v2**). Gotcha: Python-built blend spaces have empty runtime segments until
   `UBlendSpace::ResampleData()` runs, so `anim_create_blendspace_1d` now calls the native
   `FinalizeBlendSpace`. Original notes:
   add an optional `UBlendSpace* LocomotionBlendSpace` to `GameForgeLocomotionAnimInstance`
   (Runtime module). In `FGameForgeLocomotionProxy::Evaluate`, for Idle/Walk/Run, use
   `BlendSpace->GetSamplesFromBlendInput(FVector(GroundSpeed,0,0), …)` + `GetAnimationPose`. Rebuild the plugin
   (command below) and extend the M9/M10 audit PIE run to log blend weights at 0/150/300/450 speed.
3. ~~M13 gameplay trigger~~ **DONE 2026-10-31T06:00Z, 5/5 PASS** (`scripts/demo_m13_gameplay_vfx.py`, plugin
   **m13v2**). Implemented as a reusable kit actor, `AGameForgeVFXPickup` (GameForgeRuntime, now depends on Niagara),
   instead of a per-recipe Blueprint. The real PIE pawn walks into it, which logs `GF_EVENT pickup` and spawns a tagged
   effect. Remaining: packaged check, `stat Niagara` cost. Original note: spawn `NS_GFExplosion` from a GF_EVENT (pickup) in a recipe game via
   `UGameForgeVFXLibrary::SpawnSystem` from Blueprint; read particle counts after the event.
4. ~~M14~~ **DONE 2026-10-31T06:40Z** (plugin **m14v2**). Root cause: `EditorAssetLibrary.load_asset` returns None
   while PIE runs ("The Editor is currently in a play mode"), so the sound was None. **Any op that loads assets during
   PIE must use `_load_asset_pie_safe`.** New: `metasound_build_source`/`metasound_inspect` (5/5,
   `reports/m14_metasound_demo.json`), `pie_actor_state` (read live PIE actor properties), the kit actor
   `AGameForgePickup` (replaces AGameForgeVFXPickup: VFX + SFX + attenuation on collection), and
   `scripts/demo_gameplay_feedback.py` 10/10. The M14 demo also had an evidence bug (dict aliasing overwrote the
   spawn results), now fixed. Its 8/8 includes spawn_sound_at_location. Original note:
   find why `GameplayStatics.spawn_sound_at_location` returns None in 5.7 PIE (check
   `World->bAllowAudioPlayback` and the audio device for the PIE world in C++); add MetaSound builder ops.
5. M8 v2 leftovers. **Partly DONE 2026-10-31T07:30Z** (`demo_m8v2_village.py` 15/15):
   - Forest thresholds lowered: layers are now 192/32/32.
   - PCG exclusion around houses via `biomes.scatter_graphs(exclusion_tag=…)`: tagged TriggerBoxes → Get Actor
     Data (single point) → binary Difference. Proven by a dense control (243 inside without → 0 with).
   - `pcg_build_graph` takes `{"__enum__"}`/`{"__struct__"}` props.
   - Bug caught on the way: inserting a helper under an `@op` decorator re-bound the op. New unit test
     `test_every_op_decorator_wraps_the_function_of_the_same_name`.
   - **World Partition + Data Layers DONE 08:15Z** (`scripts/demo_m8v2_datalayers.py` 9/9). New ops:
     `new_level(partitioned=True)`, `datalayer_ensure`, `datalayer_add_actors`, `datalayer_list_actors`, and
     `world_clear_generated(data_layer_asset=…)` (AD-7 ownership replaces the label prefix). 5.7 lessons:
     (a) WP loads only always-loaded actors and loaded cells, so list and clear through
     `WorldPartitionBlueprintLibrary.get_actor_descs()`, then `load_actors(guids)`;
     (b) in Python, `get_actor_descs()` returns the array itself;
     (c) a `SoftObjectPath` needs `export_text()`, because `str()` gives its repr;
     (d) deleted actors keep their descriptor and external file until the level is saved.
   - **Remaining:** landscape inside a WP world, runtime streaming, packaged village traversal, real vegetation
     meshes, and migrating `demo_m8v2_village.py` to a WP level + Data Layer ownership.
   Original note: forest biome Rock/Moss thresholds (they barely appear), PCG exclusion around houses, World
   Partition for large maps, Data Layers (replace the label-prefix ownership rule of `world_clear_generated`),
   packaged real-input traversal of the village.
6. **M15 first increment DONE 2026-10-31T09:00Z**: `AGameForgeGuard` + `AGameForgeGuardAIController` (GameForgeRuntime;
   AI Perception sight, NavMesh; Patrol/Chase/Search/Return), `scripts/demo_m15_guard.py` 6/6 in PIE.
   Lessons:
   - never issue a MoveTo from `OnMoveCompleted`: a request that fails at once completes synchronously, so it
     recursed until the stack overflowed (editor crash in run 1);
   - a guard standing on its patrol point gets "RequestSuccessful" then an `Invalid` completion, and no
     AlreadyAtGoal, so decide arrival in 2D first.
   **M15 part 2 DONE 09:35Z**: `UGameForgeObjectiveSubsystem` (GameInstance subsystem, USaveGame slot: auto-saves on
   every change, loads on session start), `AGameForgeQuestGiver`, and `AGameForgePickup.ObjectiveId`.
   `scripts/demo_m15_quest.py` 8/8, including the restore in a second PIE session. Lesson: `SubsystemBlueprintLibrary`
   is not in 5.7 Python, so subsystems need a static `GetForWorld` UFUNCTION. **M15 acceptance met in PIE.**
   Next, in order: (a) M15 extras: hearing sense, a longer pursuit test, dialogue UI (UMG), GAS attributes; (b) M9 v2 character quality; (c) M10 v2 foot IK/montages;
   (d) packaged checks for pickup/guard/locomotion; (e) M17 genres, M18, M20, flagship "Ember Vale".
   Original note: Then M9 v2 (character quality), M10 v2 foot IK/montages, gameplay kit (AD-3) → M15 AI, M17 genres, M18, M20.

Plugin binaries: the current build is **m15b** (`E:\GameForge\validation\GameForgePlugin_m15b`, 2026-10-31; Editor DLL sha256 16ec5b0bccca9d58…, Runtime 83b73af4ff6dca0e…; it contains m10v2 + AGameForgePickup + AGameForgeGuard + objectives/quest giver; previous binaries in `E:\GameForge\validation\plugin_binaries_backup_pre_20261031_m15b`), installed in the
repo plugin folder and in `live_ops_probe`. Rebuild command (PowerShell):
`& E:\UE\UE_5.7\Engine\Binaries\DotNET\AutomationTool\AutomationTool.exe BuildPlugin "-Plugin=E:\gameforge_step1\src\gameforge_ide\unreal\GameForge\GameForge.uplugin" "-Package=E:\GameForge\validation\GameForgePlugin_<tag>" -TargetPlatforms=Win64`
then copy `Binaries\Win64\*` into `src\gameforge_ide\unreal\GameForge\Binaries\Win64\` and the probe, and point
`PLUGIN_BUILD` in `scripts/demo_m11_landscape.py` at the new folder.

Engine-API lessons for 5.7.4 Python (keep):
- `PCGComponent` has no `get_graph()`; use `get_editor_property("graph_instance").get_editor_property("graph")`.
- `MaterialInstanceConstantFactoryNew` has no `initial_parent`; use `MaterialEditingLibrary.set_material_instance_parent`.
- MI parameter setters' return values are unreliable; confirm by read-back.
- Enums need `.name`.
- "IDs"/"UVs" suffixes are mangled (`get_num_triangle_i_ds`, `auto_generate_x_atlas_mesh_u_vs`).
- `AnimPoseExtensions.get_anim_pose_at_time` at exactly `play_length` returns an empty pose.
- `IKRetargetBatchOperation.duplicate_and_retarget` writes to `/Game/` root.
- Landscape weightmaps read back as 0 until the edit-layer merge runs on a later tick; poll.
- LandscapeLayerBlend inputs are named `Layer <Name>`.
- Captures against a black sky need manual exposure (`scene_set_manual_exposure`).
- C++: `FLandscapeImportLayerInfo Info(FName(...))` is a vexing parse; spawn names must be unique
  (`MakeUniqueObjectName`), or regeneration crashes the editor.
- `NiagaraSystemFactoryNew` takes no emitters from Python.
- `GameplayStatics` lacks `begin_deferred_actor_spawn_from_class` (`pie_view_from` now moves the pawn; NOT VERIFIED).
- `LiveEditorLink.launch()` passes `-NoSound` unless `no_sound=False`.
- Sequencer scrubbing to the exclusive end frame evaluates as frame 0.
- MRQ `{sequence_name}` resolved to "" (files became `.0000.png`); use a fixed prefix.
- Coarse meshes (< ~200 tris) cannot reach a 25% LOD; Geometry Script booleans need closed meshes.
