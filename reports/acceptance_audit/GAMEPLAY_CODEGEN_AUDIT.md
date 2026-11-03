# GameForge — Gameplay Architecture & Codegen Audit

**Audit Date:** 2026-11-03T14:15:00Z  
**Investigator:** Antigravity Autonomous Inspector & Remediation Agent  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary

This audit investigates the gameplay code generation and module compilation architecture of GameForge. Specifically, we investigate why project builds show `SnakeAndLadders.cpp` and existing GameForge plugin modules compiling, and determine whether game-specific mechanics are generated into C++, Blueprints, or DataAssets.

---

## 2. Architecture: Hybrid C++ Plugin + Project Codegen + DataAsset Runtime

GameForge's gameplay execution architecture operates across three synchronized layers:

```
┌──────────────────────────────────────────────────────────┐
│                   Layer 1: Project Target                │
│    Source/<Project>/<Project>.cpp (Module Entry Point)   │
│    Source/<Project>/Public/Custom*Rule.h (Custom Rules)  │
│    Source/<Project>/Private/Custom*Rule.cpp              │
│    Compiled by UBT into <Project>Editor.dll / .exe       │
└─────────────────────────────┬────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────┐
│              Layer 2: GameForge Runtime Plugin           │
│    Plugins/GameForge/Source/GameForgeRuntime/            │
│    - AGameForgeGridBoard (grid raycasts, tiles, turns)   │
│    - AGameForgeCardTable (deck, lanes, hand, turns)      │
│    - AGameForgeCharacter / Player (locomotion, abilities)│
│    - AGameForgeGoal / Checkpoint / Landmark / Switch     │
│    - UGameForgeCustomRule (base class for codegen rules) │
└─────────────────────────────┬────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────┐
│             Layer 3: DataAsset Runtime (GD_Main)         │
│    /Game/GameForge/GD_Main (UGameForgeGameDefinition)    │
│    - Rules, Goals, Win/Loss conditions                   │
│    - Entity configurations and property overrides        │
│    - Evaluated at tick and event by GameState            │
└──────────────────────────────────────────────────────────┘
```

### 2.1 Why the Scaffold Contains `SnakeAndLadders.cpp`
When a new game is scaffolded by `scaffold_cpp_project()` in `src/gameforge_ide/unreal/toolchain.py`:
1. It writes `<Project>.Target.cs`, `<Project>Editor.Target.cs`, `<Project>.Build.cs`.
2. It writes `<Project>.h` and `<Project>.cpp` declaring `IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, <Project>, "<Project>");`.
3. It references the `GameForge` plugin in `<Project>.uproject`, which links `GameForgeRuntime` and `GameForgeEditor` modules.

### 2.2 How Game-Specific Mechanics Are Generated
1. **Kit Actors with GDS Overrides:**
   - Turn-based board games instantiate `AGameForgeGridBoard` or `AGameForgeCardTable`.
   - The properties declared in GDS (`board_size: 100`, `snakes: 8`, `ladders: 8`, `dice_sides: 6`) are applied to the actor via `set_actor_property` and serialized into `GD_Main`.
2. **Custom Rule C++ Codegen:**
   - When a GDS declares custom logic (`Effect.CustomCode`), `src/gameforge_ide/composer/codegen.py` generates typed C++ header and implementation files inheriting from `UGameForgeCustomRule`.
   - The files are placed in `Source/<Project>/Public/Custom<N>Rule.h` and `Source/<Project>/Private/Custom<N>Rule.cpp`.
   - `build_editor` runs UBT to compile these custom C++ rule classes into the game's binary.
3. **Event Bus & Game State Runtime:**
   - At runtime, `AGameForgeGameState` reads `GD_Main`, registers listeners on the `FGameForgeEvent` bus, and checks win/loss conditions on event dispatch.

---

## 3. Findings & Remediations

1. **Missing Property Propagation (Resolved):**
   - In earlier versions, `board.py` instantiated `GameForgeGridBoard` with empty `properties={}`. The actor compiled, but board size defaulted to $3 \times 3$ rather than $10 \times 10$.
   - **Fix:** Properties from GDS (`board_size`, `cell_size_cm`, `snakes`, `ladders`) are now extracted and applied.
2. **UBT Target Rules Synchronization (Resolved):**
   - Verified that `scaffold_cpp_project()` always writes valid target rules matching the exact PascalCase project name.
3. **Module & Plugin Registration (Resolved):**
   - The GameForge plugin is deployed to `Plugins/GameForge` in each project and verified through pre-flight compilation before packaging.
