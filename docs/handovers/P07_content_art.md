# P7 — Content and Art Direction (handover)

**Branch:** `phase/P7-content`. **Depends on:** P6 accepted. **Decisions:** AD-17, AD-5. **Resolves:** F-20.
**Estimate:** 4–6 weeks. **Read first:** `../07_CONTENT_AND_MODELS.md`, `../03_RESEARCH_2026-10-31.md` R3, R4, R11.

## Objective

Generated games stop looking like prototypes, and **every asset carries truthful provenance and a licence class**.
Content is resolved in a fixed order per need (AD-17):
**user library (LIBRARY / EPIC_CONTENT) → engine-shipped Epic content → GameForge procedural/native → neural (only if
enabled in P9)**.

## Facts verified on disk (2026-10-31)

Epic template content shipped with this engine (`E:\UE\UE_5.7\Templates\TemplateResources\High\`), usable in Unreal
projects under the Unreal Engine EULA → provenance class `EPIC_CONTENT`:
- `Characters/Content/Mannequins/`: `Meshes/SKM_Manny_Simple`, `SKM_Quinn_Simple`, `SK_Mannequin` (skeleton);
  `Anims/Unarmed/ABP_Unarmed`, `BS_Idle_Walk_Run`, `MM_Idle`, `Walk/`, `Jog/`, `Jump/`, `Attack/`; `Anims/Death/MM_Death_*`;
  `Anims/Pistol/*`, `Anims/Rifle/*`; `Rigs/`, `Materials/`, `Textures/`.
- `LevelPrototyping/Content/`: `Meshes/SM_ChamferCube, SM_Cube, SM_Cylinder, SM_Plane, SM_QuarterCylinder*, SM_Ramp`;
  `Materials/M_PrototypeGrid, MI_PrototypeGrid_*, M_FlatCol, MF_ProcGrid`; `Interactable/Door, JumpPad, Target`.
- Feature packs: `E:\UE\UE_5.7\FeaturePacks\TP_ThirdPerson.upack`, `TP_TopDown.upack`, `TP_FirstPerson.upack`, …
- Installed engine plugins: FabPlugin 5.7 and QuixelBridge 5.7 (the user can add Fab/Megascans content to a library).

Templates mount this content at `/Game/Characters/Mannequins/...` and `/Game/LevelPrototyping/...`, and internal
references use those paths. **Copy the folders into `<Project>/Content/Characters/Mannequins` and
`<Project>/Content/LevelPrototyping` unchanged**, exactly as the engine's template instantiation does. Never rename or
move them afterwards: that breaks references.

---

## WI-7.1 Epic content packs (`src/gameforge_ide/content/epic_packs.py`)

```python
EPIC_PACKS = {
    "mannequins": {"src": "Templates/TemplateResources/High/Characters/Content/Mannequins",
                   "dst": "Content/Characters/Mannequins", "mount": "/Game/Characters/Mannequins"},
    "level_prototyping": {"src": "Templates/TemplateResources/High/LevelPrototyping/Content",
                          "dst": "Content/LevelPrototyping", "mount": "/Game/LevelPrototyping"},
}
def install_pack(project_dir: Path, pack: str, engine_root: Path) -> dict: ...
```
- Copy with `shutil.copytree(dirs_exist_ok=True)`. Record each `.uasset` in the asset registry: stage `PROMOTE`,
  provenance `EPIC_CONTENT`, licence `"Unreal Engine EULA (engine template content)"`, backend `"engine-template"`,
  plus the SHA-256. The registry's PROMOTE gate requires ENGINE_VERIFY first, so add ENGINE_VERIFY events from the
  verification below.
- Verification (Forge `content` step): `asset_exists` on 5 sentinel assets per pack, and
  `character_inspect_skeletal_mesh` on `SKM_Manny_Simple` (expect the `SK_Mannequin` skeleton and bone count > 60).
- Add `+DirectoriesToAlwaysCook=(Path="/Game/Characters")` and `(Path="/Game/LevelPrototyping")` whenever the gfdef
  references them. **Cooking rule:** any asset referenced only by a string in gfdef JSON is invisible to the cooker. The
  composer collects every asset path in gfdef and writes `DirectoriesToAlwaysCook` for each top folder.
  `tests/unit/test_composer_cook_dirs.py` enforces this.

## WI-7.2 Character visuals for kit pawns

- gfdef `player` gains `"mesh"`, `"anim_class"` and `"material_tint"`. Enemies, guards and NPCs get the same fields
  per entity in `gfdef.entities[id].visual`. **Schema change: Claude approves the field names in this handover. They are
  final.**
- `AGameForgeCharacter`/`AGameForgeEnemy`/`AGameForgeGuard`/`AGameForgeQuestGiver`: `ApplyVisual(const FString& Mesh,
  const FString& AnimClass, FLinearColor Tint)` loads via `FSoftObjectPath(...).TryLoad()`, sets the skeletal mesh,
  the anim class (`GetMesh()->SetAnimInstanceClass(LoadClass<UAnimInstance>(nullptr, *AnimClass))`) and a dynamic
  material instance with a `Tint` parameter if the material has one (the mannequin materials do; verify the parameter
  name in `Materials/` with `material_instance_inspect` and record it here). Mesh offset: Z −90 and yaw −90 (the
  mannequin convention; the template character uses these values. Verify against TP_ThirdPerson's BP defaults through
  read-back).
- `character_source` mapping: `mannequin` → Manny for the player and Quinn for NPCs, with palette tints for factions;
  `procedural` → the M9 pipeline asset (prototype quality; flagged in the review); `metahuman` → WI-7.7 (EXPERIMENTAL);
  `library` → WI-7.9.
- Death: on `player.died`/`enemy.killed`, play an `MM_Death_*` montage if available, else ragdoll
  (`SetSimulatePhysics(true)` on the mesh after `SetCollisionProfileName("Ragdoll")`).
- Attack: the player melee plays a montage from `Anims/Attack/` if present.
- **Scenario impact:** none. The autopilot and events are unchanged. Re-run the K3 suite to prove it.

## WI-7.3 Art direction → materials

1. Master materials (built once per project by `material_build_graph`, M11 path) under `/Game/GameForge/Materials/`:
   - `M_GF_Surface`: BaseColor = Tint × lerp(TexA, TexB, Blend) or Tint alone; Roughness, Metallic scalar params;
     optional normal; **world-aligned (triplanar) UVs** switch (static switch `UseWorldAlign`) so the procedural
     geometry needs no UV work.
   - `M_GF_Emissive` (pickups, goals): Tint × EmissiveStrength.
   - `M_GF_Toon` (style toon): stepped lighting through a `Floor(dot(N,L) × steps)/steps` custom expression, **only**
     if `material_build_graph` supports the `Custom` node. Otherwise the toon style uses flat roughness 1 and saturated
     tints, and that is documented.
2. Themes (`content/themes.py`): `default`, `stone_wood`, `scifi_metal`, `desert_sand`, `snow_ice`, `toon_flat`. Each
   maps surface roles (`floor`, `wall`, `prop`, `accent`, `terrain_low/steep/high`) to (texture set id from
   `pbr_texture_generator` with params, tint index into `art.palette`, roughness, metallic).
3. Generate PBR sets procedurally (M11 generator, `PROC`), import them with role settings (M11 path), and create one MI
   per role. Layout geometry ops get `material` args pointing at the role MIs.
4. Palette sanity: compute WCAG contrast between `accent` and `floor` tints. If < 3:1, swap to the next palette colour
   and record a warning.

## WI-7.4 Props and architecture (procedural, `NATIVE`)

`content/procedural_props.py` holds role recipes for `mesh_generate_prop` (M12 Geometry Script): `crate`, `barrel`,
`rock` (displaced sphere, seeded), `pillar`, `fence`, `stylized_tree` (trunk cylinder + 3–5 noise-displaced spheres),
`bush`, `torch`, `chest`, `altar`. Each recipe declares its triangle budget, LOD count, collision and material role.
Props run through the full M12 lifecycle (spec → generate → LOD/collision → registry → ENGINE_VERIFY → PROMOTE). Rooms
layouts use the M12 modular kit (walls, doorways, floors) with theme materials instead of cubes.

## WI-7.5 Vegetation and open-world dressing

`biomes.py` scatter specs reference **roles** instead of `/Engine/BasicShapes` meshes. The resolver maps roles to
library meshes if present, else to WI-7.4 procedural meshes. PCG graphs stay as they are (M8 v2), with exclusion kept.
Density per biome. Performance guard: total ISM instances ≤ 20,000 (`tech` budget, refined in P10).

## WI-7.6 Animation

- Default (`mannequin`): `ABP_Unarmed` for all humanoids (handles idle/walk/jog/jump from CharacterMovement). Verify
  in the testbed: a scenario capture mid-leg shows a walking pose. As a numeric check, `anim_sample_world_pose` on the
  foot bones at two times gives a different foot height (> 5 cm), which proves the animation is playing, not frozen.
- Motion matching (GASP), EXPERIMENTAL: only if the user has added the Game Animation Sample to their content library
  (WI-7.9). Retarget is not needed for Manny. Leave this as a documented manual option until a P10 decision.
- Procedural clips (M10) stay for the `procedural` character source.

## WI-7.7 MetaHuman backend (spike, EXPERIMENTAL, needs consent)

- `UMetaHumanCharacterEditorSubsystem` (verified: 28 BlueprintCallable functions in 5.7.4, including `BuildMetaHuman`,
  `RequestAutoRigging`, `RequestTextureSources`, `SpawnMetaHumanActor`). **`RequestAutoRigging` and
  `RequestTextureSources` call Epic cloud services**: egress plus an Epic login. The UI shows a consent dialog naming
  Epic as the recipient, and the workspace egress list must include `epic-metahuman`.
- Spike: create a character from a preset body, auto-rig, build, spawn, and capture. Record time, success, the assets
  created, and whether the result cooks in Shipping. Report: `reports/P7/metahuman_spike.json`. Status stays
  EXPERIMENTAL until Claude reviews it.

## WI-7.8 VFX and audio feedback library

- VFX presets (`content/vfx_presets.py`): `vfx.sparkle_burst`, `vfx.hit_flash`, `vfx.poof`, `vfx.confetti`, `vfx.ring`,
  `vfx.fire`, `vfx.smoke`, `vfx.magic_trail`. Each = a Niagara template system duplicated (M13 path) plus user-parameter
  overrides (colour from the palette, spawn count, lifetime). Check the user-parameter names per template with
  `vfx_inspect_system` and record them in the preset table.
- SFX sets (`default`, `retro`, `soft`): `sfx_synth` (M14) parameter presets per event (`pickup_chime`, `impact`,
  `defeat`, `fanfare`, `chime_low`, `ui_click`, `footstep_soft`). Import with attenuation.
- Music (`audio.music_mood`): `content/music.py` generates 16-bar loops procedurally: a chord progression per mood
  (calm: I–vi–IV–V at 80 bpm; tense: i–VI–VII–i at 120 bpm; heroic: I–V–vi–IV at 110 bpm; playful: I–IV–V–IV at
  128 bpm), sine/triangle voices with an envelope, written as WAV (`PROC`) and played by a kit `AGameForgeMusicPlayer`
  (looping, ducking on game end).
- Ambience (`audio.ambience`): procedural noise beds (wind = filtered noise with slow LFO; forest = wind + random
  chirps; dungeon = low drone + drips).

## WI-7.9 Content library (user-supplied packs, `LIBRARY`)

- `content/library.py`: `register_source(path, licence: LicenceDecl)`. The user must pick a licence class in a dialog
  (`EPIC_CONTENT` for Epic samples such as GASP; `FAB_STANDARD`; `CC0`; `CC_BY` with attribution text;
  `CUSTOM` with pasted text) and tick "I have the right to use this content in my games". There are no defaults.
- Indexing: open the source (a UE project folder or a `Content` folder) in a disposable editor session through
  `list_assets` (class, path, bounds via `static_mesh_inspect` for meshes) and store rows in
  `<artifacts_root>/content_library.db`. Role tagging: name heuristics (`tree|pine|oak` → tree, …), then an optional
  vision classification of thumbnails (advisory), then manual edits in the Assets view.
- Import into a game: a new op `asset_migrate {packages[], dest_content_dir}` wrapping `AssetTools.migrate_packages`
  with prompts disabled. **Verify the exact 5.7 Python signature with `api_introspect` first and record it in
  `06_ENGINE_NOTES_UE57.md`.** If no prompt-less path exists, fall back to a file copy of the package files, keeping
  the mount-relative paths (the same approach as WI-7.1), and document which one was used.
- Every imported asset gets a registry row: `LIBRARY`, the licence class and text, and the source path.

## WI-7.10 Vision rubric and the "no placeholder" gate

- Rubric criteria, each scored 0–1 by the vision model with a fixed prompt and JSON output: `readability`,
  `not_placeholder`, `lighting`, `composition`, `hud_legible`, `style_consistency`. The overall score is the mean.
- Calibration: 30 captures from P6/P7 runs, labelled by the user in the Evidence view (thumbs up/down per criterion; a
  new small UI). Agreement = the fraction of matching binarised scores (threshold 0.5). Gate ≥ 0.8. If it is not met,
  the rubric stays advisory and the report says so.
- Mesh audit (deterministic, the real gate): via `actors_in_level` + `actor_get_materials`, count static-mesh
  components using `/Engine/BasicShapes/*` or `/Game/LevelPrototyping/Meshes/*` **without** a theme MI, plus any
  `WorldGridMaterial`/`DefaultMaterial` usage. With `art.placeholder_ok == false` (the new GDS default from P7), the
  count must be 0, otherwise the `review` step FAILs and lists the actors.
- GDS revision: `ArtDirection.placeholder_ok` default changes to `False`. Existing GDS files keep their explicit value.
  Record this in `docs/01_ARCHITECTURE.md` §3.1 and DECISION_LOG.

## Phase exit gate
1. The adventure and shooter genres (P6) rebuilt with art direction: the mesh audit has 0 placeholders, the rubric is
   reported (and gates if calibrated), and the scenarios are still green.
2. The asset registry has a row with a correct licence class for every asset in both games. Test
   `test_registry_licence_complete` runs against the project DBs (`reports/P7/registry_audit.json`).
3. Captures `reports/P7/before_after_<genre>.png` (P6 vs P7) are in the report.
4. The MetaHuman spike recorded (any outcome). The content library imports one user pack if the user supplies one;
   otherwise BLOCKED (needs user content), which is acceptable.

## Failure cases and prevention
- **Broken references after copying packs:** never change the mount path. The sentinel `asset_exists` checks catch it.
- **Licence ambiguity:** without an explicit user selection, a library pack cannot be used (fail closed).
- **Cooking misses JSON-referenced assets:** the always-cook rule plus a Shipping scenario with a capture showing the mesh.
- **Performance regressions from dense vegetation:** the instance cap. P10 profiles it.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 7.1 | TODO | | | |
| 7.2 | TODO | | | |
| 7.3 | TODO | | | |
| 7.4 | TODO | | | |
| 7.5 | TODO | | | |
| 7.6 | TODO | | | |
| 7.7 | TODO | | | |
| 7.8 | TODO | | | |
| 7.9 | TODO | | | |
| 7.10 | TODO | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
