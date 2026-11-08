# GameForge Upgrade Report — 2026-11-09

This pass targets the main complaint: when GameForge finishes without errors, the game it makes is barely playable
and does not match the prompt. The work traced the whole prompt → design → composition → Unreal runtime path and
fixed every defect found on it. It also ran static analysis across the whole Python tree.

**Not verified on an engine.** Nothing here was compiled against Unreal 5.7 or run in the editor. The C++ plugin
has to be rebuilt (RunUAT `BuildPlugin`), and the Python changes should be checked with `pytest tests/unit` and
`graders/protected` on the Windows host. The `tests/` folder was not in the archive.

---

## 1. Root causes of "pathetic, unplayable, not what I asked for"

| # | Root cause | Where | Fix |
|---|---|---|---|
| 1 | Any design in one of the 5 legacy genres (platformer, arena, board, card, world) was converted to a legacy recipe. The recipe keeps 3–5 numbers and drops named enemies, hazards, guards, theme, rules and counts. | `design/legacy.py` | Only untouched presets (`generator: preset:<id>`) use legacy recipes. Everything else goes through the Composer, which honours the full design. Presets are now tagged with that generator. |
| 2 | No model available → "Which preset is this closest to?" or a bare preset. Any prompt containing "arena", "board" and so on was taken over by the preset by substring match. | `design/prompt_to_gds.py` | New deterministic prompt analyser (below). The preset fast path is used only when the prompt states nothing the preset would lose. Keywords match on word boundaries. |
| 3 | Weak or local models dropped details (20 zombies became 5 generic enemies; volcano became a grey arena). Pitch was capped at 280 characters and was the only record of the prompt. | design path | `reconcile_draft` repairs model drafts against the prompt's facts. The full prompt is stored in `meta.source_prompt`, and the facts are given to the model in the system prompt. |
| 4 | **Player was invisible.** `AGameForgeCharacter` never loaded a mesh (gfdef `mesh` was ignored). | `GameForgePlayer.cpp` | Mesh/anim from gfdef → Mannequins → a tinted primitive body (cylinder, head, visor). |
| 5 | **Enemies were invisible** without template content, never died (corpses kept blocking and counting), and stood still until the player was in range. | `GameForgeKitActors.cpp`, `GameForgeAttributes.cpp` | Proxy body, hit flash and knock-back, death (collision off, ragdoll or tip-over, removed after `CorpseSeconds`), wandering around spawn, leash and hysteresis, steering when there is no navmesh. |
| 6 | **"Defeat all" could never be won.** `entity.<id>.remaining` counts live tagged actors, and dead enemies were never removed. | runtime | The death handler sets a lifespan, so the enemy drops out of the count immediately. |
| 7 | **Per-entity counters never moved.** No placed actor ever got `EntityId`, so every event had `Entity=None` (HUD "Gems: --", rule `source` filters dead). | `level_ops.py` + runtime | `level_ops` sets `EntityId` on every kit actor. The runtime also resolves it from the `GF_E_<id>` tag. |
| 8 | **Win/lose did nothing visible.** The rules subsystem emitted `game.won`/`game.lost` but nobody reacted. There was no end screen, the player kept playing, and the menu widget was a stub. | `GameForgeKitUI.cpp`, `GameForgePlayer.cpp` | VICTORY / GAME OVER screen with score, R to restart, P to pause; gameplay input is blocked after the end. |
| 9 | **Death soft-locked the game.** Respawn needed `Lives>0` *and* a checkpoint, but checkpoints never set the respawn point. Falling destroyed the pawn (`Super::FellOutOfWorld`). The death event fired only once per life (`bDiedEmitted` never reset). | runtime | Respawn at the last checkpoint, else the start, after 1.5 s unless the game was lost. A lives stat is added. Falls are routed through damage. The death flag is re-armed on respawn. |
| 10 | **Platformer needed no jumping.** 3 m platforms sat 2.6–4.2 m apart centre-to-centre (touching or overlapping), and every gap was bridged by a walkway ramp. | `composer/layouts/course.py` | Rewritten. Edge gaps come from the real jump arc and difficulty. The course zig-zags and climbs, has moving platforms and hazard platforms, and has bonus pickups over gaps. Bridges exist only on easy. |
| 11 | **Arena entities were piled on a diagonal line.** Each wall's avoidance disc had radius ≈ half the wall length, so it covered the whole arena and scatter placed 0 of N. | `composer/compose.py` | Walls are modelled as chains of small discs. Ground and board planes are no longer treated as obstacles. |
| 12 | **Everything was grey or white.** Layouts used `/Game/LevelPrototyping/...` materials that blank projects don't have. Kit actors were untinted basic shapes. Theme, biome and palette were never used. | layouts, kit actors | New `composer/theme.py` with 18 themes. `spawn_actor` gains `color` (cached BasicShapeMaterial tints) and `light_color`. Kit actors are colour-coded: gold pickups, red/orange hazards, blue checkpoints, yellow goal. |
| 13 | **Levels were empty.** | — | New `composer/decor.py` adds theme-specific set dressing built from basic shapes: trees, tombstones and torches with lights, lava rocks, crystals, neon blocks, palms, cacti, platform columns. It is kept out of gameplay space. |
| 14 | **Every game had the same level** (seed 2026). | `expand.py` | Stable seed per design from the title and prompt. |
| 15 | **Open-world actors were buried.** 20 m landscape relief and every actor spawned at z=100. | `open_world.py`, `level.py` op | Gentler terrain. New `snap_to_ground` for actors and PlayerStart (the trace ignores decoration). |
| 16 | **Wave spawners spawned the wrong enemy.** `enemy_entity_id` defaulted to "enemy", but entity ids are "enemys"/"zombies". Spawned enemies got default stats and no EntityId. Kills from any enemy counted toward any wave, and a failed spawn made a wave un-clearable. | expand + `AGameForgeSpawner` | Spawner is linked to a real enemy entity. Enemies are spawned deferred with the entity's GDS stats and colour. Waves count only their own members, escalate in size, and announce themselves on the HUD. |
| 17 | **Shooters shot into the floor.** Top-down aiming used the 60°-down camera forward vector. The top-down shooter default attack was melee. | `GameForgePlayer.cpp`, `expand.py` | Cursor aim in top-down, crosshair aim in third person, facing in side view. The shooter/FPS default is projectile. No enemy friendly fire, and the shooter can't hit itself. |
| 18 | **"Collect everything, then reach the exit"** won on reaching the exit, because wins are OR-ed. `collect_all` used the model's `target`, not the placed count. | `expand.py` | The goal is locked behind the pickup total (`required_stat`), with an on-screen "Not yet" message. The win count equals the placed count. |
| 19 | **Model and preset props invalidated the whole design** (kit param models are `extra="forbid"`; e.g. `player_speed`, `recipe`, `enemy_max_health`). | `expand.py` | `sanitize_props` maps aliases, drops unknown keys and clamps values to the module's ranges. |
| 20 | **Free-text custom rules became empty generated C++ classes** (compile risk, no behaviour). | `expand.py` | They become one on-screen briefing message instead. |
| 21 | **Movement felt terrible.** Engine-default air control 0.05 and ice-skating braking. | `GameForgePlayer.cpp` | Tuned air control, braking and acceleration. Sprint (Shift), double jump, arrow keys and gamepad support added. |
| 22 | **Event counters survived "Play again".** The bus lives on the GameInstance, so collect-N goals were met instantly after a restart. | `GameForgeEvents.cpp`, `GameForgeRules.cpp` | `ResetCounters()` runs at world begin play. |
| 23 | **Rule effects `message` and `end_game` were ignored.** For example, board games never registered an AI win as a loss. | `GameForgeRules.cpp` | Both are implemented (`ui.message` reaches the HUD). |
| 24 | **No feedback ever played.** gfdef held preset ids like `vfx.sparkle_burst` instead of asset paths. The feedback subsystem required the settings asset. HUD counters showed "Score: 10 / 100". | `kit/runtime_def.py`, `GameForgeKitUI.cpp` | Ids are resolved to asset paths with the same definition lookup as the rules. The HUD gets real targets (`of`), a countdown timer, a title card, an objective line and a controls hint. |

## 2. New modules

- `design/prompt_analysis.py`: a deterministic `PromptBrief` built from the prompt. It covers genre scoring,
  camera, 13 themes (biome, lighting, palette, music, ambience) and about 60 enemy nouns (ranged and boss
  detection). It also covers about 50 collectibles (merging "treasure chests"), hazards, goals, guards, NPCs,
  waves, survive/timer/score/lives/health numbers, difficulty, size, weapon type, double jump and sprint, and
  notes on unsupported features. It provides `brief_to_draft` (a full offline design), `reconcile_draft` (repairs
  model output) and `brief_for_model` (facts added to the system prompt).
- `composer/theme.py`: themes, role colours, the painting pass and decoration piece definitions.
- `composer/decor.py`: decoration placement for each layout type.
- `GameForgeRuntime/Public/GameForgeVisuals.h`: runtime tint and shape helpers.
- `kit/runtime_def.py` adds `describe_objective` and `describe_controls`. gfdef carries `objective`, `controls`,
  `pitch` and entity `label`s.

## 3. Other bugs fixed (from whole-tree static analysis)

The whole tree was checked with `compileall`, ruff and mypy.

- `scripts/models/materialize_gameforge_27b_sft.py`: `from __future__` was not the first statement (SyntaxError).
- `backend/tools/game_tools.py`: `logger` was undefined, so the error path itself crashed.
- `desktop/panels/terminal_panel.py`: `Optional` was undefined.
- `unreal/mutation_queue.py`: `asyncio.TimeoutExpired` doesn't exist, so every timeout raised AttributeError.
  It is now `asyncio.TimeoutError`.
- `desktop/views/build_view.py`: roll back called `reset_to(sha)` without the required `editor_running`, so every
  roll back failed. It now detects a running editor (psutil).
- `desktop/panels/explorer_panel.py`: `refresh()` was called but never existed, so the explorer never updated
  after agent edits. Implemented, keeping expansion state.
- `backend/tools/biomes.py`: `lighting_rig` forced every light to z=100 m, so the indoor fill light was useless.
- `composer/compose.py`: the composition `gds_id` was always "gds_0".
- `composer/level_ops.py`: a case-insensitive filter dropped the UE property `Value`. Unmapped snake_case props
  were sent as properties, producing hundreds of "skipped" warnings.
- `gameforge_ops/level.py`: colour dicts were not converted to `LinearColor`.
- Pickups: `Value`, `bRespawns` and `RespawnSeconds` existed in the property map but not on the class. Added,
  along with respawn, spin and bob, and hiding the actor when collected.
- Mixed `src.gameforge_ide.*` absolute and relative imports gave two module identities: duplicate singletons and,
  in `gds.py`, kit validation silently skipped under pytest. 124 imports were converted to relative. Missing
  `__init__.py` files were added in `backend/{agent,providers,tools,security}` and `models`.
- `plan_panel.py`: string evidence entries crashed rendering. `hosted_settings.py`: an unknown provider kind
  raised `None()`. `pbr_texture_generator.py`: a PNG without IHDR raised TypeError.
- Landmark trigger radius ignored `DiscoverRadius`. Hazard visuals now match the damage area. The moving
  platform property map pointed at non-existent `EndOffsetX/Y/Z`; it now sets `EndOffset`.
- The Ollama design call timeout went from 120 s to 300 s. Cold large models used to time out and fall back.
- `GamePipeline.run(GDS)` for a non-preset design now gives an actionable error.
- QA: a goal locked behind pickups gets collect-then-goal scenarios. Win scenarios for real jump courses are
  advisory (`must_pass=False`) and their failures don't fail the build; smoke and lose scenarios still gate it.
- The model output parser is lenient (markdown fences, prose around the JSON) and normalises common small-model
  schema slips before validation, so the one repair attempt isn't wasted.

## 3b. Round 2 — hardening and frontend (2026-11-09)

Verified in this sandbox: every Python file compiles and lints clean. 1,000+ generated prompts ran through
design, composition and editor op generation with 0 failures, and 250 runs fed garbage model output (wrong types,
markdown fences, unknown kinds, huge numbers) also gave 0 failures. The desktop IDE was launched offscreen and every
studio view was opened with and without a project, with 0 Python exceptions and 0 Qt warnings. Screenshots were
reviewed.

**Pipeline / backend**
- Fast-mode game creation in the agent never used the design model (`prompt_to_gds` was called without
  `complete_json`). It now uses the configured model.
- New `resolve_design_model()` probes Ollama (`/api/tags`, 2 s, cached) before using it. An offline or missing
  model goes straight to the deterministic design instead of waiting on two failing calls per game. The agent, the
  Home view and `/game` share it, so no throw-away `GameTools` instances are created.
- A new game no longer overwrites the project that happens to be open. It builds into the active project only when
  that project is empty or is the same game.
- The chat shows a design summary (title, genre, camera, theme, objective, contents, player abilities) before the
  build starts, so the user can check the prompt was understood.
- Composition errors come back as a structured failure (`failed_stage: compose`, problems and suggestions) instead of
  an exception that aborted the agent turn. Composer warnings are forwarded as events.
- Approvals carry `project_dir`/`project_name`. The approval card used to guess "MyGame", write that guess back into
  the approval args, and **the game was built into a folder called MyGame**.
- The strategy model's answer is parsed leniently (fences, prose). A non-strategy answer is reused as a draft only
  when it actually looks like one. A model that labels an action game "scratch" no longer sends it down the
  puzzle-only scratch prompt.
- Real-time presets (platformer, arena, procedural world) now use the composer too, so they get the reworked course,
  themes, visible characters and working combat. Board and card presets keep their legacy recipes. Setting
  `GAMEFORGE_LEGACY_ACTION_RECIPES=1` restores the old routing. Preset player/spawner props are merged instead of
  replacing the expanded defaults, so lives and air control survive.
- Design rules render as sentences ("When pickup is collected, add 10 to the score") instead of raw pydantic reprs.
  Stat names are readable, and the design markdown shows setting and objective.

**Frontend**
- A stray, pre-created Code view sat at (0,0) on top of the top bar (the "Expl..." text over the logo). It is now
  hidden until the view host shows it.
- The app had a dark stylesheet on Fusion's *light* palette, so scroll viewports, table corners and group-box
  backgrounds rendered white. Settings and Design showed white bands with invisible section titles. A matching
  palette is now applied for both themes.
- `/game` ran the whole design (minutes with a local model) on the GUI thread and froze the IDE. It now runs in a
  background thread with a queued signal back to the UI.
- Home "Design it" checked `job.done` (a method, always truthy), so the double-submit guard never worked. It also
  always called Ollama. Both fixed.
- The workspace itself was listed as an empty "Unknown" game (any `.gameforge` folder counted as a project). Now only
  a .uproject, a design or project-scoped Forge runs make a folder a game.
- Chat: header title no longer truncated, welcome text no longer clipped, and the welcome screen hides once a
  conversation starts (slash commands and restored sessions left it above the messages). The example prompts now
  show rich game prompts; the button shows a shortened label and the tooltip has the full prompt.
- Dashboard subtitle wraps instead of being cut off.

## 4. Offline results (no model, deterministic)

| Prompt | Result |
|---|---|
| fight 20 zombies in a haunted graveyard at night with a shotgun, survive 3 minutes | `arena_combat`, third-person shooter, haunted theme (night, tombstones, torches), 20 green zombies + waves, objective "Survive 3 min" |
| 3D platformer on a volcano, collect 12 gems, reach the portal, double jump, lava | Volcano course with real jumps, 12 cyan gems, lava platforms, 3 lives, checkpoints, portal locked until all gems are collected |
| top-down shooter in space with alien drones that shoot, 5 waves | Cursor-aimed shooter, space theme, ranged drones/aliens, 5 escalating waves |
| stealth game called Shadow Vault … guards in a bank … steal 3 diamonds then escape | "Shadow Vault", rooms layout, guards (lose if spotted), exit locked until 3 diamonds are taken |
| counter strike style bomb defusal | First person, tactical layout, ranged terrorists |
| make tic tac toe / connect four / platformer | Unchanged preset path (legacy recipes) |

## 5. Known limits (honest)

- Chess, Sudoku, Tetris and racing have no dedicated runtime rules. Chess and Sudoku still run on the
  N-in-a-row grid board. Racing is built as an on-foot time trial, and the build reports this as an approximation.
- Decoration and kit visuals are basic shapes, not art assets.
- QA autopilot walks the navmesh, so it cannot verify a jump course. Those win scenarios are advisory.
- `plugin_manifest.json` source hashes were refreshed. The Binaries entries are stale until the plugin is rebuilt.
  Regenerate the manifest after building.

## 6. Next steps on the Windows host

1. Rebuild the plugin for Editor, Game Development and Shipping, fix any compile errors in the changed C++ files
   (listed in `context.md`), then regenerate the plugin manifest.
2. `python -m pytest tests/unit -q` and `graders/protected -q`. Update tests that assert on the old behaviour
   (preset hijacking, legacy routing, walkway courses, `entity.enemys` ids).
3. Build three prompts end to end (zombie survival, volcano platformer, space shooter) and play them.
