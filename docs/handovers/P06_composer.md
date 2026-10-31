# P6 — Composer: GDS → playable packaged game (handover)

**Branch:** `phase/P6-composer`. **Depends on:** P5 accepted. **Decision:** AD-10. **Resolves:** F-01, F-12.
**Estimate:** 4–6 weeks. **Read first:** `../01_ARCHITECTURE.md` §3, §4.1; `P05_gameplay_kit.md` (the gfdef contract).

## Objective

Make the product loop real: **any GDS that uses PASS kit modules becomes a packaged game whose must-pass scenarios
pass**, built by Forge from a composition. Then reproduce the 5 legacy genres from presets on the kit, add two new
genres, and remove the per-recipe C++ templates from the product path.

## Package layout

```
src/gameforge_ide/composer/
  __init__.py
  model.py         # Composition, LevelPlan, OpCall, Placement, CodegenTask, CompositionError
  compose.py       # compose(gds) -> Composition
  layouts/__init__.py  board.py arena.py course.py rooms.py open_world.py lanes.py  # each: plan_level(level, gds, rng) -> LevelPlan
  placement.py     # Poisson-disk scatter, path placement, slot resolution
  level_ops.py     # LevelPlan -> [OpCall] (geometry, lighting, kit actors, props, nav, save) + manifest builder
  runtime_def.py   # GDS -> gfdef/1 JSON
  codegen.py       # custom_code -> C++ rule class (model) + safety scan + repair ladder hooks
  plan.py          # Composition -> forge RunSpec
  content.py       # minimal content step for P6 (VFX from templates, procedural SFX); P7 replaces it
tests/unit/test_composer_*.py   tests/fixtures/gds/*.gds.json (one per preset + 2 new genres)
```

---

## WI-6.1 `composer/model.py`

```python
class OpCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str                                  # must be in op_catalog.agent_ops(); args validated by op_schemas (strict)
    args: Dict[str, Any] = {}
    expect: Dict[str, Any] = {}              # e.g. {"ok": True, "data.count": 3}; checked after the call
    purpose: str = ""                        # human-readable line for the Build log

class PlacedActor(BaseModel):
    actor_id: str                            # "<entity_id>_<n>" (unique, stable across rebuilds for the same GDS)
    entity_id: Optional[str]                 # None for geometry/props owned by the layout
    runtime_class: str
    location: Tuple[float, float, float]     # centimetres, level space
    yaw: float = 0.0
    tags: List[str] = []                     # always includes GF_E_<entity_id> for entities and GF_Owned
    properties: Dict[str, Any] = {}          # UPROPERTY name -> value (already mapped via kit property_map)

class LevelPlan(BaseModel):
    level_id: str
    map_path: str                            # /Game/Maps/<LevelId>
    partitioned: bool
    player_start: Tuple[float, float, float]
    nav_bounds: Tuple[Tuple[float, float, float], Tuple[float, float, float]]   # center, extent (cm)
    geometry_ops: List[OpCall]               # floors, walls, landscape, platforms (layout-owned)
    actors: List[PlacedActor]
    lighting: Literal["day", "dusk", "night", "indoor"]
    nav_checks: List[Tuple[str, str]]        # (from actor_id | "player_start", to actor_id) that must be reachable

class CodegenTask(BaseModel):
    handler_name: str                        # "Custom0Rule"
    description: str
    rule_id: str

class Composition(BaseModel):
    gds_id: str; gds_revision: int; project_name: str
    modules: List[str]                       # kit module ids used
    plugins: List[str]                       # .uproject plugins to enable
    module_deps: List[str]                   # Build.cs deps for the game module
    levels: List[LevelPlan]
    gfdef: Dict[str, Any]                    # gfdef/1
    codegen: List[CodegenTask]
    scenarios: List[str]                     # scenario ids to generate after assembly (manifests needed)
    content_requests: List[Dict[str, Any]]   # P6: vfx/sfx preset ids; P7 extends
    warnings: List[str] = []

class CompositionError(Exception):
    def __init__(self, problems: List[str], suggestions: List[str]): ...
```

## WI-6.2 `compose.py` (the algorithm)

```
compose(gds, allow_partial=False) -> Composition
 1. modules = {e.module for e in gds.entities}. For each: kit.registry.module(m). If status is not PASS
    (or PARTIAL with allow_partial) → problem "module kit.x is <status>"; collect all problems first.
 2. Validate every entity's props with the module params_model (already done by GDS validation; re-check here:
    a mismatch is an internal error).
 3. rng = random.Random(level.seed) per level. Layout = LAYOUTS[level.layout].plan_level(level, gds, rng).
 4. Entities without a slot are placed by placement.scatter(...) inside the layout's free area. Each placed actor
    gets tags [f"GF_E_{entity_id}", "GF_Owned", f"GF_{kind}_{n}"] and properties mapped through property_map.
    Pickups/goals/hazards get spawn tags if a rule spawns them (GF_SP_<entity_id>).
 5. gfdef = runtime_def.build(gds, comp)  (WI-6.5).
 6. codegen = [CodegenTask for every CustomCode effect in gds.rules].
 7. plugins = union(required_plugins of modules) ∪ {"GameForge", "EnhancedInput", "GameplayAbilities", "Niagara"};
    module_deps = union(game_module_deps) ∪ {"EnhancedInput", "GameForgeRuntime"}.
 8. scenarios = [s.scenario_id for s in gds.acceptance.scenarios].
 9. If problems → raise CompositionError(problems, suggestions) where suggestions name supported alternatives
    (e.g. "kit.enemy_ranged is PARTIAL; use kit.enemy_melee or allow partial modules").
```
**Determinism requirement:** `compose(gds)` twice gives a byte-identical `Composition.model_dump_json()`
(test it). Stable actor ids are what make P8 incremental rebuilds possible.

## WI-6.3 Layouts and placement

Each layout returns a `LevelPlan` with `geometry_ops`, slots and free areas. All dimensions are in centimetres;
`size_m` is converted ×100.

| Layout | Geometry (ops) | Slots | Reuse |
|---|---|---|---|
| `board` | none (the board actor builds its cells); fixed top-down camera via the board's camera component | `board` at origin | P5 `AGameForgeGridBoard` |
| `arena` | floor (`spawn_actor` StaticMeshActor `/Engine/BasicShapes/Cube` scaled to size × 0.1 m thick), 4 walls 300 cm high, 4–8 cover blocks (seeded, ≥ 600 cm apart, never within 800 cm of the centre) | `player_start` centre; `spawn_ring`: 8 points on a circle at 40 % of the half-size | arena recipe `assemble_arena_level` sizes |
| `course` | N platforms (N = max(7, pickups + 3)) along +X with height steps of ±0–150 cm and gaps of 250–450 cm (jumpable with jump_velocity 650 / gravity 1.2: **validate reachability with the ballistic formula below**), a start pad, a goal pad, kill_z at −500 cm below the lowest platform | `player_start` on the start pad; `goal` on the end pad; `checkpoint` on the middle platform; `path` = platform tops | platformer recipe layout |
| `rooms` | `backend/tools/dungeon_layout.py` (exists) generates rooms + corridors on a 400 cm grid; walls via the M12 modular kit (`mesh_generate_prop` kit pieces, or cube walls if the kit pieces are not yet in the project), with doorways | `player_start` in the first room; `goal` in the farthest room (BFS distance); `room_<i>` centres | M12 kit demo, dungeon_layout tests |
| `open_world` | `backend/tools/biomes.py` (exists): landscape + paint layers + PCG scatter graphs with exclusion around POIs; lighting rig; World Partition if size > 400 m | `player_start` on flat ground near the edge; `landmark` and `goal` at the far side; POIs on a Poisson set with ≥ 30 m spacing | M8 v2 village demo ops sequence (`scripts/engine/demo_m8v2_village.py`) |
| `lanes` | none (the card table builds lanes); fixed camera | `board` | P5 card module |

**Platform reachability** (course layout). For a gap `g` (horizontal, cm) and a height difference `h` (cm, positive up):
`t_apex = v / (gravity_scale × 980)`, `max_h = v² / (2 × gravity_scale × 980)`. The jump is reachable if `h ≤ 0.8 ×
max_h` and `g ≤ 0.8 × move_speed × t_air(h)`, where `t_air(h)` is the time to come back down to height `h`
(`t_apex + sqrt(2 × (max_h − h) / (gravity_scale × 980))`). Unit-test it: the legacy defaults (v=650, g=1.2,
speed 600) give max_h ≈ 180 cm.

**placement.py:** `scatter(area_polygon, n, min_spacing_cm, rng, avoid=[circles])` uses Bridson Poisson-disk
sampling with up to 30 attempts per point. If fewer than `n` points fit, return the ones found and add a warning
"placed 3 of 5 pickups; level too small", and the composer raises if a win condition needs the missing count.
`along_path(points, n)` places evenly by arc length.

## WI-6.4 `level_ops.py`

Turn a `LevelPlan` into an op sequence. Every op is checked against `op_schemas` in **strict** mode, and the composer
unit test asserts that every generated call validates.
```
new_level {level_path: map_path, partitioned, if_exists: "replace"}      # add "replace" to new_level if missing (WI-6.8)
lighting preset ops (day/dusk/night/indoor): DirectionalLight, SkyLight, SkyAtmosphere, ExponentialHeightFog,
   VolumetricCloud (outdoor only), PostProcessVolume unbound with manual exposure (EV from preset table)
geometry_ops (from the layout)
for each PlacedActor: spawn_actor {label: actor_id, actor_class: runtime_class, location, rotation{yaw}}
                      actor_set_tags {label, tags}                                   # new op, WI-6.8
                      set_actor_property {label, property, value} for each property
NavMeshBoundsVolume via spawn_actor + scale from nav_bounds; nav_rebuild {}
for each nav_check: nav_find_path {from, to} with expect {"data.found": true}
datalayer ensure/add (open_world partitioned only): generated content → DL_GFGenerated
gamedef_write {asset_path: "/Game/GameForge/GD_Main", json: gfdef}   (once per project, in the first level's step)
save_all {}
```
Then build the **manifest** (`qa/manifest.py` from P3) from `actors_in_level` read-back. Extend `_actor_record` to
include tags (WI-6.8), so the manifest uses observed positions and tags, not planned ones.

Lighting presets **reuse `backend/tools/biomes.py`** (`LIGHTING` + `lighting_rig(preset)`), which already emits
`spawn_actor` rows. Extend that dict; do not create a second table in `level_ops.py`.

| GDS `lighting` | `biomes.LIGHTING` key | Exposure (`scene_set_manual_exposure.exposure_bias`) | Status |
|---|---|---|---|
| day | `day_clear` (sun 6.0, pitch −45, yaw 35; sky light, atmosphere, fog, clouds) | 10.0 | **verified** in the M8 v2 village (`reports/m8v2_village_demo.json`) |
| dusk | new `dusk`: sun 2.5, pitch −8, yaw 250, warm colour (1.0, 0.62, 0.38); sky light; atmosphere; fog | start at 9.0 | starting point; capture-verify |
| night | new `night`: directional "moon" 0.6, pitch −35, yaw 20, colour (0.55, 0.65, 1.0); sky light intensity 0.4; fog | start at 6.0 | starting point; capture-verify |
| indoor | new `indoor`: no sun or atmosphere; sky light 1.0; 2–4 point lights placed by the layout (rooms: one per room centre, intensity 5,000, attenuation 1,500 cm) | start at 9.0 | starting point; capture-verify |

**Capture verification (part of WI-6.9):** for each preset, assemble the arena layout and capture from the player
start (manual exposure on). Pass if the mean luminance of the frame is between 0.18 and 0.65 and at least 2 % of
pixels are above 0.9 (lit faces exist). That is the M16 lesson: the sun must light the faces the camera sees. Store
`reports/P6/lighting_<preset>.png` and the numbers. Tune only the starting-point values, and record the final values
in `biomes.LIGHTING` with a comment that names the report.

## WI-6.5 `runtime_def.py` (GDS → gfdef/1)

A pure function with golden-file tests (`tests/fixtures/gfdef/<preset>.json`). The mapping table:

| gfdef key | From GDS |
|---|---|
| `title`, `seed` | `meta.title`, `scene.levels[start].seed` |
| `player` | `overview.camera` → `"third_person"/...`; player entity props (`move_speed`, `jump_velocity`, `max_health`, `attack_*`); `lives` from props (default 0); `kill_z` from the course layout or −2000 |
| `input` | `input.actions`: each binding `"Key:mod1+mod2"` → `{"key","mods":[…]}`; `swizzle_negate` → `["swizzle","negate"]` |
| `stats` | built-ins used anywhere (scan conditions/effects/HUD), `player.health` from max_health, every `game.counter.*` referenced (initial 0), and `persist` flags for stats used by objectives |
| `entities` | every entity: `{"class": runtime_class, "spawn_tag": "GF_SP_<id>"}` |
| `rules` | each `RuleSpec` → `{"id", "when": {"e": when.event, "ent": when.source}, "if": conditions, "do": effects}`; `custom_code` → `{"kind": "custom_code", "class": "/Script/<Project>.<Handler>"}` |
| `win`/`lose` | `goals.win`/`goals.lose` verbatim |
| `feedback` | each row → `{"e", "vfx": content asset path for the preset id, "sfx": …, "shake", "msg"}`; preset → path from `content.py` |
| `hud` | `ui.hud` → `{"id","kind","stat","label"}`, plus `"of"` for counters bound to `entity.X.collected` (= entity count) |
| `menus` | `ui.main_menu/pause_menu/end_screen` |
| `custom_rules` | from codegen tasks |

## WI-6.6 `codegen.py` (custom rules only)

1. Skeleton per task (the model fills **only** the two function bodies; the anti-scaffolding lesson from the model work):
   ```cpp
   // <Project>/Source/<Project>/Public/<Handler>.h  (generated, not model-written)
   #pragma once
   #include "GameForgeRules.h"
   #include "<Handler>.generated.h"
   UCLASS()
   class <PROJECT>_API U<Handler> : public UGameForgeCustomRule
   {
   	GENERATED_BODY()
   public:
   	virtual void OnEvent(const FGameForgeEvent& Event) override;
   	virtual void Tick(float DeltaSeconds) override;
   };
   ```
   The `.cpp` skeleton has `// BEGIN MODEL CODE` / `// END MODEL CODE` markers inside each function.
2. The prompt contains: the rule description; the allowed API surface, a short reference generated from
   `GameForgeRules.h` and `GameForgeEvents.h` (`GameState()->GetStat/SetStat/AddStat`, `Emit`, event names);
   constraints (no includes, no new classes, no file or network I/O, no `GEngine->Exec`, no `ConsoleCommand`); and
   examples. Output schema: `{"on_event_body": str, "tick_body": str}` via `complete_json`, with role `codegen`.
3. `pipeline/authoring.safety_scan` (exists) runs on the bodies, plus a denylist regex
   (`#include|FPlatformProcess|FFileHelper|IFileManager|Exec\(|ConsoleCommand|asm|reinterpret_cast`).
4. The Forge `codegen` step writes the files. The `build_editor` step's repair hook calls `codegen.repair(task,
   diagnostics)` (≤ 2 model repairs, after the deterministic `pipeline/autofix.py` pass). Repairs may only change the
   marked bodies. Anything outside the markers is restored from the skeleton.
5. A custom rule is accepted only when its scenarios pass. The codegen task records a `rule_test` scenario if the GDS
   has none that touches the rule (an amber "untested custom rule" warning in Design and Build).

## WI-6.7 `plan.py` (Composition → RunSpec)

| Step id | Kind | Depends on | Lock | Notes |
|---|---|---|---|---|
| `design` | design | — | no | save the GDS revision + composition.json (inputs: gds hash) |
| `scaffold` | scaffold | design | no | toolchain scaffold with plugins/module_deps; Enhanced Input ini; DefaultGame.ini settings; `GlobalDefaultGameMode=/Script/GameForgeRuntime.GameForgeGameMode`; project git (AD-13) |
| `codegen` | codegen | scaffold | no | only if tasks exist |
| `build_editor` | build | scaffold, codegen? | yes | `max_attempts=3` with the codegen repair hook |
| `content` | content | build_editor | yes | P6: VFX from templates (`vfx_create_system`), SFX import (`audio_import` of `sfx_synth` output) for the preset ids used |
| `assemble_<level_id>` | assemble | content | yes | one per level; level_ops; manifest |
| `scenario_gen` | design | all assemble steps | no | `qa.generate` with the manifests → `GameForge/scenarios/*.json`; gaps fail the step if any gap is a `must_pass` |
| `automation` | automation | assemble steps | yes | `GameForge.Kit` + project tests |
| `package` | package | automation | yes | Development |
| `scenarios` | scenario | package, scenario_gen | yes | all must_pass |
| `review` | review | scenarios | no | vision rubric (advisory in P6) |
| `report` | report | review | no | Markdown + JSON report into evidence |

Input hashes: `assemble_<level>` inputs = the LevelPlan JSON + the gfdef hash. `content` inputs = the content
requests. This gives P8 incremental behaviour for free.

## WI-6.8 New and extended ops (editor side)

- `actor_set_tags {label, tags[]}` (catalogue: level/project, readback `actors_in_level`). `_actor_record` adds
  `"tags": [str(t) for t in actor.tags]`.
- `new_level` gains `if_exists: "replace"` (delete and recreate), alongside the existing `load`.
- `gamedef_write` / `gamedef_inspect` (from P5, if not already added).
- Schemas for all of them (strict).

## WI-6.9 Legacy parity and retirement

1. For each preset (`tic_tac_toe`, `connect_four`, `platformer`, `arena_combat`, `card_battler`, `procedural_world`):
   GDS → composer → Forge → package → scenarios. Evidence: `reports/P6/parity_<preset>.json`, which compares with the
   legacy run (tests passing, scenario outcomes, package size, build minutes).
2. Gate: every preset has ≥ 1 win scenario and ≥ 1 lose scenario (or draw/board-loss for grid) passing on the
   composer path.
3. Switch the product: `GameTools.create_game` and the Design view's Build use the composer. `legacy.to_legacy_params`
   is used by nothing in `src/`.
4. `git mv src/gameforge_ide/recipes tests/fixtures/legacy_recipes` and remove `pipeline/game_pipeline.py`'s recipe
   imports. Keep `GamePipeline` as a thin wrapper over composer + Forge for scripts (or delete it once
   `scripts/pipeline/run_game_pipeline.py` calls composer + Forge directly). Delete `TaskPlanExecutor` if nothing
   imports it (P2 deprecation). The tests for the legacy recipes move with them and run against the fixtures, or are
   deleted with a note if they only checked template text.
5. Old demo scripts that parse legacy `GF_EVENT` log lines: update them to the bus JSONL, or mark them historical in
   `scripts/engine/README.md`.

## WI-6.10 Two new genres

- **Third-person exploration/adventure:** the prompt "a third-person forest adventure where I collect 5 relics while
  avoiding 3 guards and return them to the old hermit" → GDS (model path or a new preset `relic_hunt`) →
  open_world + pickups + guards + quest giver + goal. Win: `objective.completed` then `goal.reached`. Lose:
  `guard.spotted_player`.
- **Top-down shooter:** "top-down arena shooter, survive 3 waves of ranged robots" → arena + spawner + ranged
  enemies + player fire (`IA_Attack` mapped to a projectile in top-down mode: P5 `player.attack_mode =
  "projectile"`; if P5 did not ship it, add it as WI-6.10a with a kit change and a plugin rebuild).
- Evidence: `reports/P6/genre_adventure.json`, `genre_shooter.json`, each with passing scenarios and captures.

## Phase exit gate
1. Composer unit tests (determinism, schema-valid ops, gfdef goldens, reachability, scatter) green.
2. Parity: all 6 presets PASS on the composer path in Development packages, and at least 2 also in Shipping.
3. Two new genres PASS from prompts, end-to-end in the Studio UI (manual walk with screenshots).
4. Recipes removed from the product path; full unit suite green; `scripts\verify_all.ps1` green.
5. `docs/00_STATUS.md`: "Integrated prompt-to-game" becomes PASS for the supported genres, with module list and evidence.

## Failure cases and prevention
- **NavMesh missing on spawned geometry:** collision on the geometry, NavMeshBoundsVolume covering all of it, and
  `nav_rebuild` *after* all geometry. The `nav_find_path` checks catch it before packaging.
- **Actors placed inside geometry:** scatter avoids cover/walls (circles from the layout). Then do a downward trace snap
  (`landscape_height_at` for open world). Tolerance check in the manifest: z within 50 cm of the ground.
- **gfdef referencing assets that do not exist** (feedback VFX/SFX): the `content` step must produce every path in
  `gfdef.feedback`. The `assemble` step verifies them with `asset_exists` before `gamedef_write`.
- **Composer non-determinism** (dict ordering, set iteration): sort everything that comes from a set, and seed every
  RNG from the level seed.
- **Codegen writing outside the markers:** the writer rebuilds the file from the skeleton plus the bodies, so model text
  never controls file structure.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 6.1 | TODO | | | |
| 6.2 | TODO | | | |
| 6.3 | TODO | | | |
| 6.4 | TODO | | | |
| 6.5 | TODO | | | |
| 6.6 | TODO | | | |
| 6.7 | TODO | | | |
| 6.8 | TODO | | | |
| 6.9 | TODO | | | |
| 6.10 | TODO | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
