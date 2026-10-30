# GameForge Architecture Evolution

Updated 2026-10-30T17:20Z (Claude Code). Decisions AD-1…AD-8 are summarized in `GAMEFORGE_MASTER_ROADMAP.md` §2.
This file records the alternatives, rationale, limitations and sources. These are architecture *proposals adopted
for planning*. Each becomes a DECISION_LOG entry only when it is implemented and verified (do not invent decision IDs).

## Current architecture (verified)
Native PySide6 IDE (`src/gameforge_ide/desktop`) → agent/planner (`backend/agent`: task_plan, plan_executor,
plan_generator) → ToolGateway (typed, approval-gated) → `unreal/live_editor.py` loopback link → in-editor Python
dispatcher `gameforge_ops.py` (76 `@op` functions) → native C++ `GameForgeEditor` libraries (Blueprint, Widget,
Landscape, Character, Animation) + `GameForgeRuntime` module (gameplay state component). Build/test/package via
`unreal/toolchain.py` (UBT/UAT). Prompt → game via `pipeline/game_pipeline.py` with recipes and a free-form path.

## AD-1 Operation catalogue
- **Problem:** 76 ops with no declared read-back or test linkage; M3/M4 shipped ops that reported success while
  doing nothing.
- **Alternatives:** ad-hoc ops; generic Python exec (rejected: violates Blueprint security); catalogue.
- **Choice:** a catalogue with an enforced "mutating ⇒ readback_op" rule as a unit test.
- **Limitation:** read-back proves state, not visual correctness. Pair it with screenshots/vision review where visuals matter.

## AD-2 Graph authoring kernel
- **Sources (verified present in UE 5.7.4):** `Engine/Source/Editor/MaterialEditor/Public/MaterialEditingLibrary.h`,
  `Engine/Plugins/Runtime/Metasound/Source/MetasoundEngine/Public/MetasoundBuilderSubsystem.h`, `Engine/Plugins/PCG`
  (`UPCGGraph::AddNodeOfType/AddEdge`, already used by `pcg_scatter`), `IKRetargeterController.h`,
  `IKRetargetBatchOperation.h`.
- **Choice:** a uniform JSON node/edge read-back contract with per-domain adapters. Material is first because it has
  the most stable API. Niagara graph editing stays EXPERIMENTAL and uses a template + parameter strategy instead.
- **Limitation:** Niagara and AnimBP editor graphs are not public stable APIs, so coverage there stays partial.

## AD-3 Gameplay kit over templates
- **Problem:** 4 recipes duplicate Character/GameMode/HUD code; every new genre multiplies maintenance.
- **Choice:** components in `GameForgeRuntime` built on native GAS / StateTree / EnhancedInput / SmartObjects (all
  plugins present under `Engine/Plugins/Runtime`). Genres are compositions.
- **Risk:** GAS adds compile time and complexity; small recipes may keep the simple path.

## AD-4 Asset registry (SQLite, per workspace)
Lightweight (no service process), queryable and auditable. Search is tags + LIKE; embeddings only if measured useful
(they keep the shipped IDE's idle RAM budget intact).

## AD-5 Procedural-first specialists
The host has an AMD 12 GB GPU on Windows. Most open 3D, rig and motion models need CUDA. Procedural and native
backends give deterministic, licensed and verifiable output today. Neural backends get evaluated one at a time with
approval (see registry).

## AD-6 Reordered milestones
Materials → assets → world v2. Kit → AI → genres. QA runs continuously. Rationale: dependency fan-out (materials
feed 5 later milestones).

## AD-7 Project graph for incremental change
Spec-hash-keyed ownership of generated assets enables "modify the existing game" (M20) without regenerating or
overwriting user edits. It uses Data Layers to separate generated content from user content in levels.

## AD-8 Scenario-based QA
Reuse `real_input.py` + GF_EVENT markers; add a YAML scenario DSL and Insights/csvprofile capture.

## Newly discovered requirements (evolving list)
1. `pcg_scatter` docstring claims Surface Sampler but uses a grid; fix the docstring or implement surface sampling (M8 v2).
2. The packaged-game locomotion AnimInstance has not been exercised; it needs packaged verification.
3. Enhanced Input should replace legacy input bindings in generated projects (UE5 default).
4. Generated projects need a plugin-enable step in the scaffolder (GAS, StateTree, PCG, GeometryScript, Niagara, MetaSound).
5. Packaged size is ~860 MB per game. Investigate cook filtering (`+DirectoriesToNeverCook`, pak exclusions) in M19.
7. (Fixed 2026-10-30) `QuarantinePipeline` recorded `TRELLIS.2` as the generator of procedurally generated meshes.
   Any pipeline that accepts a `model_name` must verify that this backend actually ran.
6. Working tree has uncommitted Antigravity changes and no commits since `9eeca5b`. Commit hygiene is needed (branch per milestone).
