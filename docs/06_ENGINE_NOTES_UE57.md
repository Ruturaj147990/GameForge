# Unreal Engine 5.7.4 — Engineering Notes for GameForge

**Owner:** Claude. **Consolidated:** 2026-10-31 from `GAMEFORGE_MASTER_ROADMAP.md` §5, `context.md` (2026-10-27…31) and
the engine-install audit. Every item was learned on this engine (5.7.4-51494982, `E:\UE\UE_5.7`). Add new lessons
here **as you learn them**: one line, with the evidence report.

---

## 1. Install facts (verified 2026-10-31)

- Launcher install `UE_5.7` → `E:\UE\UE_5.7` (manifest `C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat`).
  FabPlugin 5.7 and QuixelBridge 5.7 are installed. `Engine/Build/Build.version`: 5.7.4, CL 51494982.
- Plugins on disk used or planned by GameForge: PythonScriptPlugin, EditorScriptingUtilities, EnhancedInput (with
  `IEnhancedInputSubsystemInterface::InjectInputForAction` at line 148 and `StartContinuousInputInjectionForAction` at
  line 195), PCG (`Plugins/PCG`), PCGBiomeCore (experimental), GeometryScripting, Niagara, Metasound, MovieRenderPipeline,
  StateTree, GameplayStateTree, GameplayAbilities, SmartObjects, PoseSearch, Chooser, MotionWarping, CommonUI,
  GameFeatures, ModularGameplay, CQTest, CQTestEnhancedInput, FunctionalTestingEditor, MetaHumanCharacter
  (`Plugins/MetaHuman/MetaHumanCharacter`), Mover (experimental), Iris (experimental), AIAssistant (experimental).
- **Absent in 5.7.4:** `ModelContextProtocol` and `ToolsetRegistry` (they ship with 5.8).
- Epic template content usable in projects: `Templates/TemplateResources/High/Characters/Content/Mannequins`
  (Manny/Quinn, `SK_Mannequin`, `ABP_Unarmed`, `BS_Idle_Walk_Run`, locomotion/attack/death/pistol/rifle anims) and
  `Templates/TemplateResources/High/LevelPrototyping/Content` (prototype meshes, materials, interactables).

## 2. Plugin build, install and provenance

```powershell
& E:\UE\UE_5.7\Engine\Binaries\DotNET\AutomationTool\AutomationTool.exe BuildPlugin `
  "-Plugin=E:\gameforge_step1\src\gameforge_ide\unreal\GameForge\GameForge.uplugin" `
  "-Package=E:\GameForge\validation\GameForgePlugin_<tag>" -TargetPlatforms=Win64
```
1. Back up the current binaries (`E:\GameForge\validation\plugin_binaries_backup_pre_<date>_<tag>`).
2. Copy `<package>\Binaries\Win64\*` to `src\gameforge_ide\unreal\GameForge\Binaries\Win64\` (gitignored) and to the
   probe project's `Plugins\GameForge\Binaries\Win64\`.
3. Set `plugin_build` in the host profile (P0 WI-0.2; previously `PLUGIN_BUILD` in `scripts/engine/demo_m11_landscape.py`).
4. Record both DLL SHA-256 values in `context.md`.

**Current state (2026-10-31, [VERIFIED] hashes, provenance [UNVERIFIED]):**
- Repo-installed binaries (modified 2026-10-31 11:45): Editor `db062c3e594bcae20926a6362e3482eb3668aa3bed4d817a440419d706d82dfa`,
  Runtime `5cf12c9a7f98d44dd782b88cac38ba74e6d8f57af659f645e77b3a58cf5d4cb4`.
- Latest package `E:\GameForge\validation\GameForgePlugin_neutral`: Editor `7d0054424a6ab3c691a1fc5e2557a6ae1cad3d13d31ff6bac1016ab76e7b4c03`,
  Runtime `ecc83a30f6ba8716df7d45f8f518e9b1756f3968cf3fda48f335e1a5dd384276`.
- These **differ**, and neither matches a hash recorded in `context.md`. The repo binaries were probably built inside
  the kit test project and copied back. **P0 WI-0.9** rebuilds `GameForgePlugin_p0` and installs it everywhere, and from
  then on only packaged builds are installed.

Rules: a C++ change is not done until the plugin builds with 0 warnings in GameForge modules. Live Coding is never
used for GameForge evidence.

## 3. Python (editor) API lessons — 5.7.4

| Topic | Lesson | Evidence |
|---|---|---|
| PCG | `PCGComponent` has no `get_graph()`. Use `get_editor_property("graph_instance").get_editor_property("graph")` | `wpa_reverify_20261031.json` |
| Materials | `MaterialInstanceConstantFactoryNew` has no `initial_parent`. Use `MaterialEditingLibrary.set_material_instance_parent` | `m11_material_demo.json` |
| Materials | MI parameter setters' return values are unreliable. Confirm by read-back | M11 |
| Enums | Enum values need `.name` for stable read-back strings | M11 |
| Naming | Suffixes "IDs"/"UVs" are mangled: `get_num_triangle_i_ds`, `auto_generate_x_atlas_mesh_u_vs` | M12 |
| Animation | `AnimPoseExtensions.get_anim_pose_at_time` at exactly `play_length` returns an empty pose. Sample slightly before the end | WP-A re-verify |
| Retarget | `IKRetargetBatchOperation.duplicate_and_retarget` writes to `/Game/` root. Move the results afterwards | WP-A |
| Blend spaces | Python-built blend spaces have empty runtime segments until `UBlendSpace::ResampleData()` runs; `FinalizeBlendSpace` (native) does it | `m10v2_blend_drive_demo.json` |
| Landscape | Weightmaps read back as 0 until the edit-layer merge runs on a later tick. Poll | `m11_landscape_demo.json` |
| Landscape | LandscapeLayerBlend inputs are named `Layer <Name>` | M11 |
| Niagara | `NiagaraSystemFactoryNew` takes no emitters from Python. Duplicate template systems instead | `m13_vfx_demo.json` |
| GameplayStatics | No `begin_deferred_actor_spawn_from_class` in Python. `pie_view_from` moves the pawn instead (NOT VERIFIED) | M10 v2 |
| Subsystems | `SubsystemBlueprintLibrary` is missing in 5.7 Python. Give subsystems a static `GetForWorld` UFUNCTION | `m15_quest_demo.json` |
| PIE assets | `EditorAssetLibrary.load_asset` returns None during PIE ("Editor is in play mode"). **Any op that loads assets during PIE must use `_load_asset_pie_safe` (`unreal.load_asset`)** | `m14_spawn_diag.json` |
| World Partition | WP loads only always-loaded actors and loaded cells. List and clear through `WorldPartitionBlueprintLibrary.get_actor_descs()` then `load_actors(guids)` | `m8v2_datalayers_demo.json` |
| World Partition | In Python, `get_actor_descs()` returns the array itself | same |
| World Partition | A `SoftObjectPath` needs `export_text()`; `str()` gives its repr | same |
| World Partition | Deleted actors keep their descriptor and external file until the level is saved | same |
| Sequencer | Scrubbing to the exclusive end frame evaluates as frame 0 | `m16_sequence_demo.json` |
| MRQ | `{sequence_name}` resolved to "" (files became `.0000.png`). Use a fixed prefix | M16 |
| Geometry Script | Meshes under ~200 tris cannot reach a 25 % LOD. Booleans need closed meshes | `m12_asset_demo.json` |
| Blueprint graphs | `UEdGraphNode::Pins` and `UEdGraph::Nodes` are protected from Python. Graph work goes through native C++ (`GameForgeBlueprintGraphLibrary`) | M2 |
| Ops | Inserting a helper between `@op("x")` and `def x` re-binds the op. A unit test now enforces adjacency | `m8v2_village_demo.json` |
| To verify (P7) | Exact `AssetTools.migrate_packages` signature and prompt-less options | P7 WI-7.9 |

## 4. C++ lessons

- Spawned objects need unique names (`MakeUniqueObjectName`). A fixed name is fatal once an actor with that name was
  destroyed in the level (editor crash on regeneration, M8 v2).
- `FLandscapeImportLayerInfo Info(FName(...))` is a vexing parse. Use brace initialisation.
- **AI movement:** never issue `MoveTo` from `OnMoveCompleted`. A request that fails immediately completes
  synchronously, which recurses into a stack overflow (M15 editor crash). Schedule it on the next tick.
- A guard spawned on its patrol point gets `RequestSuccessful` and then an `Invalid` completion, never `AlreadyAtGoal`.
  Decide arrival in 2D first.
- Missing includes that compile only through unity builds (e.g. `Engine/World.h` in the locomotion anim instance)
  break other build configurations. Include what you use.
- New module dependencies need both Build.cs and (for plugins) `GameForge.uplugin` `Plugins` entries (Niagara, and
  later EnhancedInput, GameplayAbilities).
- C4458 (declaration hides class member) is treated as an error in plugin builds. Rename locals.

## 5. Rendering, capture and PIE

- **`-nullrhi` + `spawn_actor` crashes 5.7.4** (`EXCEPTION_INT_DIVIDE_BY_ZERO`). Unattended sessions use
  `-RenderOffscreen`.
- Black captures: before blaming MRQ or the capture path, render **Unlit**. In M16 the cause was a sun lighting the
  faces that point away from the cameras, with no sky atmosphere for ambient light.
- Captures against a dark sky need manual exposure (`scene_set_manual_exposure`, bias 10 for the `day_clear` rig).
- `LiveEditorLink.launch()` passes `-NoSound` unless `no_sound=False`. Audio tests need the real device.
- `pie_move_player_to` uses `SimpleMoveToLocation` on a DefaultPawn, which **can teleport** (packaged run 2: 11–17 m
  legs in ≤ 0.01 s). Movement evidence must come from the P3 autopilot (injected input + leg-speed checks).
- Real Win32 input needs an idle desktop: Windows refuses foreground focus while the user works elsewhere. The P3
  scenario runner removes this dependency.

## 6. Packaging and cooked builds

- `Packaged\Windows\<Name>.exe` is a launcher. Test the binary in `<Name>\Binaries\Win64\`.
- **Shipping compiles out `UE_LOG` and disables the console.** Evidence must come from files the game writes (event
  bus JSONL, scenario result files), not from logs. The legacy `-GFSelfTest` log markers only work in Development.
- Assets referenced only by strings (JSON, soft paths in config) are not cooked unless their folders are in
  `+DirectoriesToAlwaysCook`.
- The default Development package of a small game is ~860 MB. Shipping + trimming is planned in P10.

## 7. Live-link protocol facts

- Remote execution: `DefaultEngine.ini` bind `127.0.0.1`, TTL 0. Discovery accepts only the node whose `project_root`
  matches. Token in `Saved/GameForge/session.token`.
- The editor caches the `gameforge_ops` module in `sys.modules` for its lifetime. Deploy, then launch a **new** editor.
- One call in flight at a time. A dropped socket is classified as `EDITOR_CRASHED` or `EDITOR_LINK_LOST`.
