# P10 — Scale and Advanced Systems (handover)

**Branch:** `master` (no feature branches). **Depends on:** P6–P8 accepted. **Decisions:** AD-16, AD-19. **Resolves:** F-13.
**Estimate:** 5–7 weeks. The sub-areas are independent and may run in any order. Do them one work item at a time.

---

## WI-10.1 Performance budgets and the optimisation loop

- **Capture:** package in the **Test** configuration (`toolchain.package(..., configuration="Test")`, which keeps the
  CSV profiler and drops most debug cost). A new scenario step, `{"profile": {"seconds": 20, "csv": true}}`, runs
  `csvprofile start/stop` through the in-game console. If the console is unavailable in Test builds, add a kit
  function `UGameForgeProfiler::StartCsv/StopCsv` that calls `FCsvProfiler::Get()->BeginCapture()/EndCapture()`, and
  verify that the API exists in 5.7.4 headers first. Parse with `backend/tools/csv_profile.py` (exists, tested).
- **Budgets** from GDS `tech`: `target_fps`, `max_frame_ms`. Report the p50/p95 frame time, game thread, render thread,
  GPU, draw calls (if present in the CSV) and memory.
- **Loop** (`qa/optimize.py`): a deterministic list of candidate changes, each reversible through the GDS or project
  settings: reduce the PCG density (−25 %), cap the shadow distance, enable Nanite on static meshes > 5k tris (where
  supported), lower the screen percentage to 85 %, HLOD for WP levels, and disable volumetric clouds. For each: apply →
  rebuild the affected steps → profile → keep it only if p95 improves ≥ 5 % **and** the vision rubric does not drop by
  > 0.05 **and** the scenarios still pass. Stop when within budget or the list is exhausted. Evidence:
  `reports/P10/perf_<game>.json` with the before and after of every attempt.

## WI-10.2 Shipping profile and package size

- `toolchain.package(..., configuration="Shipping", profile="release")` writes these settings before cooking:
  ```ini
  [/Script/UnrealEd.ProjectPackagingSettings]
  BuildConfiguration=PPBC_Shipping
  bCompressed=True
  PakFileCompressionFormats=Oodle
  bShareMaterialShaderCode=True
  bSharedMaterialNativeLibraries=True
  IncludePrerequisites=False          ; True when the user picks "standalone installer" in the export dialog
  +DirectoriesToNeverCook=(Path="/Game/GameForge/Debug")
  ```
  **Verify every key name against the 5.7.4 `ProjectPackagingSettings.h`** before writing them, and record the verified
  list in `06_ENGINE_NOTES_UE57.md`.
- Plugin trimming: the scaffolder writes `"Plugins"` entries with `"Enabled": false` for heavy default-enabled plugins
  the game does not need. Build the list from the 5.7.4 Blank template's enabled plugins minus the kit's
  requirements, and validate it by packaging the testbed. Remove one plugin per iteration if a cook fails, and record
  which.
- Size report: total, plus the largest files in the pak (`UnrealPak -List`). Gate: a small kit game ≤ 400 MB (the
  GDS `tech.max_package_mb` default drops to 400 in this phase).
- Shipping scenarios: the P3 result-file path (no logs) has been proven since P3. Re-run the full suite on Shipping.

## WI-10.3 Large open worlds

- A landscape inside a World Partition level (an open item since M8 v2): extend `GameForgeLandscapeLibrary` to create
  the landscape in a partitioned world (streaming proxies), and verify after save and reload that cells load.
- HLOD build: the commandlet `UnrealEditor-Cmd <uproject> -run=WorldPartitionBuilderCommandlet -Builder=WorldPartitionHLODsBuilder
  -AllowCommandletRendering`, wrapped as a toolchain function with log parsing. Check the exact arguments in 5.7.4
  first.
- A packaged traversal scenario over 500 m with streaming: the autopilot travels POI to POI. Record hitches (frame time >
  50 ms) during cell streaming.
- The composer enables WP automatically for `open_world` levels whose `size_m` > 400.

## WI-10.4 Multiplayer (listen server, 2 local clients)

- GDS `tech.multiplayer = "listen_server"` (already in the schema).
- Kit replication: the GameState stats array (`TArray<FGameForgeStat>`, `DOREPLIFETIME`), ASC `Mixed` mode for
  players and `Minimal` for AI, server-authoritative pickups/goals/hazards (overlaps processed on the server only:
  `HasAuthority()` guards), and the rules subsystem running on the server only, with clients receiving end-game state
  through a replicated `bEnded` + outcome. Events are emitted on the server, and a multicast RPC mirrors them to
  clients for HUD and feedback (the client-side bus only does presentation).
- Test harness: start the server `<Game>.exe <map>?listen -GFScenario=server.json -GFScenarioOut=server_result.json`,
  then a client `<Game>.exe 127.0.0.1 -GFScenario=client.json …` (two processes; the job object owns both).
  Scenarios: the client collects 3 pickups, and the server and client results must agree on
  `entity.pickups.collected == 3` and `game.won`. Net emulation (Development only):
  `-ExecCmds="Net PktLag=100,Net PktLoss=2"` on the client.
- Evidence `reports/P10/multiplayer.json` with both result files.

## WI-10.5 In-game cinematics

- A GDS addition (approve the shape here): `presentation.intro: {"enabled": bool, "seconds": 6-20, "focus":
  ["landmark", "goal"]}`. Bump to `gds/1.1` with backward-compatible defaults.
- The composer builds a Level Sequence with the M16 `sequence_build` op: a camera spline flythrough over the focus
  entities with an audio track (music mood). Kit `AGameForgeIntroPlayer` plays it on `game.started` before enabling
  input (skippable with any key). Scenarios get `{"skip_intro": true}` support in the scenario subsystem.
- Captures prove the shots (M16 cut-detection method).

## WI-10.6 UE 5.8 compatibility lane

- Install UE 5.8 side by side **with the user's approval** (on E:).
- `core/settings.py` gains `engine_channel: "pinned" | "next"`. Default pinned (5.7.4).
- Rebuild the plugin for 5.8. Run the live contract test, the kit automation tests and the full kit scenario suite.
  Record the API breaks.
- Unreal MCP (5.8): implement `unreal/mcp_bridge.py` as a **read-only** client that lists Toolset Registry tools and
  calls read-only ones. Add `meta=(AICallable)` to GameForge's read-only C++ `UFUNCTION`s under `#if
  ENGINE_MINOR_VERSION >= 8`. The port 47815 vs 8000 coexistence is verified.
- Evidence `reports/P10/ue58_lane.json`. Moving the pinned engine to 5.8 is a separate decision for Claude and the user.

## Phase exit gate
Every work item has a packaged, scenario-verified demo with its budget or acceptance met, and evidence in
`reports/P10/`. The status matrix is updated.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 10.1 | TODO | | | |
| 10.2 | TODO | | | |
| 10.3 | TODO | | | |
| 10.4 | TODO | | | |
| 10.5 | TODO | | | |
| 10.6 | TODO (needs approval) | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
