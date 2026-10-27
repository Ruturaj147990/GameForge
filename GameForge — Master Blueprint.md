# GameForge — Master Blueprint v2

Oct 27, 2026 · supersedes v1 (archived at `archive/GameForge — Master Blueprint v1 (2026-10-27).md`)

**Mission.** Give GameForge one natural-language prompt, for example *"create a tic-tac-toe game in Unreal Engine"*, and get back a playable, verified Unreal project. GameForge plans the work, picks the right models and tools, writes the code and assets, operates the editor, tests the result in the real engine, reviews it and repairs it. It stops only when the acceptance criteria pass, or when it can name exactly why they cannot.

v1's ten design rules still apply unchanged (§1). v2 adds six things:

- An honest baseline of what actually runs today (§2).
- The full capability catalogue, mapped to the UE 5.7.4 mechanism that can deliver each item (§5).
- A generation strategy that small local models can actually complete (§3).
- The four-model decision, settled (§6).
- Resource, scale and IDE requirements (§8–§10).
- A phased plan with live exit gates and an effort estimate (§11–§12).

---

## 1. Design contract (unchanged from v1)

No AI system is foolproof. What GameForge guarantees is that **wrong output cannot silently become a wrong result**: every action is validated before it runs, bounded while it runs, verified after it runs, and is either reversible or explicitly marked irreversible.

1. The model proposes; the harness decides. No model output runs until it passes schema validation and a policy check.
2. Completion is evidence, not text. COMPLETE requires acceptance predicates that pass against observed state.
3. Fail closed. A missing token, policy, snapshot or editor connection yields BLOCKED with the cause.
4. Everything is bounded: time, output, retries, tokens, tool calls, VRAM, disk, spend.
5. Snapshot before mutate. Undo transactions where the editor supports them, and labelled irreversibility where it does not.
6. One writer at a time. Editor mutations are serial.
7. Read back after write. A write's return value is never the proof.
8. Untrusted data stays data.
9. Local by default.
10. Every claim has a ledger entry. **Status is generated from evidence. A test that runs against a simulation is never evidence of an engine capability** (new in v2; see §2).

---

## 2. Honest baseline (audited 2026-10-27 against source, not reports)

| Area | Reported | Actually in the code | Evidence state |
|---|---|---|---|
| Agent runtime: task state, predicates, nudges, repetition limit, approvals, recovery | Implemented | Implemented in `backend/agent/` (runtime 837 lines). Tool calls are parsed from model text, not the native `tools` protocol | `[VERIFIED]` unit-level; native tool calling `[NOT IMPLEMENTED]` |
| Agent tool surface | — | 14 tools: fs read/search, propose/apply/rollback edit, run allowlisted command, git, UE info/find/build, procedural blockout mesh | `[VERIFIED]` |
| Unreal transport, supervisor, operations library, snapshots | "Phase 2 verified, 6 genuine read-backs" | **Simulated.** `PythonRemoteTransport` never opened a socket and returned `ok: True`. `UnrealOperationsLibrary` stores actors and assets in Python dicts. The handshake hard-codes `"5.7.4"` and `token_verified: True` | `[SUPERSEDED]` as engine evidence. Now labelled `simulated: True` |
| **Real editor link** (new, this session) | — | `unreal/live_editor.py` uses the engine's own `remote_execution.py`, with a project-identity check and a session token. `GameForge/Content/Python/gameforge_ops.py` contains 18 real in-editor operations | `[VERIFIED]` live on UE 5.7.4 for discovery, handshake and `new_level`. See `reports/GAMEFORGE_REALITY_AUDIT_2026-10-27.md` for the full run |
| Physics drop probe | "Chaos-compliant" | A Python Euler integrator. Unreal is never run | `[SUPERSEDED]` as engine evidence |
| Level layout generator | Implemented | Bounding-box validation is real. Instantiation targets the simulated library | Partially `[VERIFIED]` |
| Asset pipeline (spec, geometry/UV checks, quarantine, provenance, licence register, GPU lock) | Implemented | Real Python checks on OBJ/mesh data. Unreal import goes through the simulated library. No generative 3D model is installed | Checks `[VERIFIED]`; import and generation `[NOT IMPLEMENTED]` |
| C++ editor plugin | Built on 5.7.4 | Real. Pushes editor context to the IDE bridge (telemetry only) | `[VERIFIED]` (2026-10-24 build logs) |
| Desktop IDE | Implemented | Real PySide6 app: chat, explorer, diff, Unreal and terminal panels, themes, slash commands | `[VERIFIED]` |
| Models | Four LLMs | Ollama serves exactly four tags, three with vision projectors. The Ollama capabilities list `tools` for the Qwen3.5 tags | `[VERIFIED]` 2026-10-27 `/api/tags` |
| **Prompt → playable game** | Goal | `pipeline/game_pipeline.py` + `recipes/grid_board_game` + chat approval card. Typing *"create a tic tac toe game in unreal engine"* in the IDE → one Approve click → scaffold, compile, level built in the live editor, 8 automation tests, cook/package, packaged self-test with screenshot → ▶ Play | `[VERIFIED]` 2026-10-27 in the real IDE window, 102 s, all gates pass (`E:\GameForge\projects\ide_e2e\TicTacToe`) |
| Native tool calling | — | Ollama `tools` in the agent loop; text extraction only as fallback. Self-test passes on all four local models | `[VERIFIED]` live |
| Hosted heavy-model tier | — | `providers/hosted.py`: Anthropic + OpenAI-compatible providers, Credential Manager keys, workspace egress opt-in, spend ledger with caps, router `route_hosted` | `[VERIFIED]` against a local HTTP/SSE mock; no real provider enabled |
| Shipped-IDE efficiency | — | `scripts/ide_resource_benchmark.py`: start 0.8–1.7 s, ~90 MB private, <0.4% idle CPU, 0 child processes; explorer handles 30k-file folders with a 37 ms worst UI stall | `[VERIFIED]` all §8.1 budgets met |
| **Free-form games (no recipe)** | — | `pipeline/freeform.py` on a verified C++ host framework (`recipes/freeform_host`): model design → model C++ → safety scan → compile with repair ladder (deterministic autofix, then model with error-code hints) → level → package → packaged self-test with runtime repair → advisory vision review with one improvement round that must keep every gate green | `[VERIFIED]` whack-a-mole written by local 9B passes all hard gates; reviewer still flags visual quality (bootstrap-tier limit) |
| Recipe families | — | `grid_board_game`: tic-tac-toe, Gomoku, N-in-a-row, **Connect Four (gravity)**, 10 automation tests | `[VERIFIED]` Connect Four packaged + self-test PASS |
| IDE production features | — | Approval cards (approve/reject/cancel/play/folder), Mission Control (resources, approvals inbox, games, hosted spend, metadata clean-up), Hosted Models dialog (Credential Manager keys, opt-in, caps, test call), `/game`, cancel kills whole process trees, idle editors auto-close, storage hygiene, busy-only close prompt | `[VERIFIED]` by tests; dialogs not yet exercised by a human |

**Consequence.** Phase 2 of v1 is re-opened. Simulated components stay only as test doubles. Any capability that depends on them is listed as unproven until it is re-run through `LiveEditorLink`.

---

## 3. Model tiers and the generation strategy

GameForge is **model-agnostic**. The product target is **cloud-hosted heavy models** (frontier-class coding and vision models with long context and reliable native tool calling). The four local models are a **bootstrap and test tier**: they keep development offline and cheap, and they stress-test the harness, because a pipeline that works with a 4B–9B model is robust with a stronger one.

| Tier | Models | Purpose | Status |
|---|---|---|---|
| **T-Local (bootstrap / test)** | The four local Ollama LLMs (§6) | Offline development, regression runs, privacy-only projects, harness stress tests | Active |
| **T-Hosted (product target)** | Any provider profile in `configs/hosted_providers.json`: OpenAI-compatible endpoints, Anthropic Messages API, or a GameForge-hosted gateway | Planning, authoring and repair of whole games; long-context project reasoning; vision review | Arranged in code (provider profiles, credential store, egress gate, spend ledger); disabled until a profile is enabled for a project |

**Rules that do not change between tiers.** The harness decides (rule 1), completion needs evidence (rule 2), and everything is bounded (rule 4). A stronger model buys fewer repair iterations and larger steps. It never buys permission.

**Temporary small-model scaffolding (T-Local only; relaxed per tier).** These techniques make 4B–9B models usable today. They are gated by model capability, not built into the architecture:

1. **Spec first (Game IR).** The prompt becomes a typed Game Spec. *This stays in every tier*, because it is the acceptance contract the harness verifies against.
2. **Recipes.** Pre-verified, parameterised C++ module sets (board game, arena, platformer…). Under T-Local, the model selects and fills recipe slots. Under T-Hosted, recipes become optional accelerators and test fixtures, and the model may author any architecture.
3. **C++-first gameplay.** C++ is preferred because it is diffable and compiler-repairable. Under T-Hosted, Blueprint graph authoring (catalogue row B2) becomes a first-class output once the plugin graph operations exist.
4. **Small per-subtask contexts.** Under T-Local, each subtask sees only its slice. Under T-Hosted, the context profile widens (§9), and the same retrieval code pins more material.
5. **Deterministic builders and verification loops.** These stay in every tier.

The router chooses the tier per task from capability records (`supports_tools`, `max_context`, `supports_images`, measured scores, `data_egress_class`). A hosted tier is used only when the project has explicitly enabled that provider (§6).

**Worked example: "create a tic-tac-toe game"**

| Step | What GameForge does | Gate |
|---|---|---|
| 1 Spec | Game Spec: 3×3 board, two players (hot-seat; AI optional), win/draw detection, restart, HUD showing turn and result | Schema valid; user may edit the acceptance list |
| 2 Recipe | `grid_board_game` recipe: `ATTTBoard` (cells as clickable actors), `ATTTGameMode`, `UTTTGameState` (rules), `UTTTHud` (UMG), top-down camera pawn | Recipe version pinned |
| 3 Scaffold | Create the C++ project from the engine Blank template into the workspace; enable required plugins | `.uproject` valid; `Build.bat` Development Editor exit 0 |
| 4 Code | The model fills the recipe slots (rules, AI move choice, UI text); compiler diagnostics drive bounded repair | UBT exit 0; zero new warnings in GameForge modules |
| 5 Assemble | Live editor operations: new level, spawn board/camera/lights, materials X/O/board, Blueprint subclasses, set GameMode override, save | Read-back of every actor and asset |
| 6 Test | Automation spec `GameForge.TicTacToe.*`: row/column/diagonal wins, draw, invalid move, restart. Run headless with `UnrealEditor-Cmd -ExecCmds="Automation RunTests GameForge"` | All tests pass; JUnit/JSON report parsed |
| 7 Play check | PIE with scripted clicks plus a screenshot; the vision model confirms the board, marks and HUD | Screenshot exists; advisory review stored |
| 8 Package | `RunUAT BuildCookRun -platform=Win64 -cook -stage -pak -archive`; launch the packaged exe with `-ExecCmds` smoke test | Exit 0; the packaged game boots and quits cleanly |
| 9 Report | Change summary, screenshots, test table, provenance, known limits | Ledger complete |

---

## 4. Unreal execution layer (v2)

Four mechanisms, chosen per capability:

| Mechanism | Used for | Status on 5.7.4 |
|---|---|---|
| **Live editor operations** (Python remote execution → `gameforge_ops.py`) | Assets, actors, levels, materials, Blueprint creation and compile, import, Sequencer, PCG, Control Rig and MetaSound wherever Python exposes them | Link `[VERIFIED]` 2026-10-27 |
| **GameForge C++ editor plugin** (operations registered as `UFUNCTION`s callable from Python) | Blueprint graph nodes and pins, UMG widget trees, Niagara emitters, anything Python cannot reach | Plugin builds; command surface `[NOT IMPLEMENTED]` |
| **Headless commandlets and UAT** (`UnrealEditor-Cmd`, `Build.bat`, `RunUAT`) | C++ compilation, automation tests, cooking, packaging, shadow-copy Tier 4 Python | Build `[VERIFIED]` 2026-10-24; tests and packaging `[NOT IMPLEMENTED]` |
| **Epic Unreal MCP** | Optional transport once Epic's plugin is confirmed on the pinned engine | Not present in this 5.7.4 install; v1 notes say the documentation is for 5.8 |

UI automation (clicking the editor) is a last resort, and its result must still be read back.

**Live link protocol (implemented).** The supervisor writes `DefaultEngine.ini` remote-execution settings (bind `127.0.0.1`, TTL 0), installs `gameforge_ops.py`, writes a 256-bit token to `<Project>/Saved/GameForge/session.token`, launches the editor (`-RenderOffscreen` for unattended work), and accepts only the discovery node whose `project_root` matches the target. Every call carries the token, which the editor checks with `hmac.compare_digest`. Arguments travel as one JSON string literal, never interpolated as code. There is one call in flight, a per-call timeout, and a dropped socket is classified as `EDITOR_CRASHED` or `EDITOR_LINK_LOST`.

**Known hazard (measured).** Under `-nullrhi`, `spawn_actor` crashed UE 5.7.4 with `EXCEPTION_INT_DIVIDE_BY_ZERO` in `UnrealEditor-Engine.dll`. Unattended sessions use `-RenderOffscreen`. `-nullrhi` is restricted to commandlets that do not touch level viewports.

**Version adapters.** Every operation declares `min_engine`, the feature probe it needs (the handshake already returns 13 probes such as `MaterialEditingLibrary`, `PCGGraph`, `ControlRigBlueprint` and `MetaSoundBuilderSubsystem`), and a contract test. An operation is *supported* on an engine only when its contract test has passed live on that exact engine build (changelist recorded).

---

## 5. Capability catalogue

The status vocabulary is **live** (contract test passed on 5.7.4), **impl** (code exists, live test pending), **planned**, and **research** (mechanism unconfirmed). Today almost every row is `planned`. That is the honest starting point.

| # | Domain | Prompt-level capabilities | UE 5.7.4 mechanism | External model? | Status |
|---|---|---|---|---|---|
| A1 | Project and scaffolding | New C++ or Blueprint project from template, plugins, config, maps and modes | File templates + `.uproject` editing + UBT | No | **live** |
| A2 | Levels and actors | New/load/save level, spawn/delete/transform actors, properties | Live ops (`new_level`, `spawn_actor`, …) | No | **live** (16/16 contract) |
| B1 | C++ gameplay | Classes, components, subsystems, interfaces, delegates, Build.cs, unit and automation tests, compile-repair | Workspace edits + UBT + diagnostics parser | LLM | **live** for recipe code (UBT + diagnostics parser); model-authored C++ repair loop planned |
| B2 | Blueprints | Create, reparent, defaults, components, compile (Python); nodes, pins and links (plugin) | `BlueprintFactory`, `BlueprintEditorLibrary`; C++ `FBlueprintEditorUtils`/K2 schema for graphs | LLM | **live** create/compile; graph nodes planned |
| C1 | Static mesh creation | Procedural primitives and kitbash, blockouts, UVs, LODs, collision, pivot/scale | Geometry Script, `StaticMeshEditorSubsystem`, existing OBJ generator | Optional 3D generator | planned |
| C2 | Text/image → 3D | Generated props with PBR | Generator service → glTF → quarantine import | TRELLIS.2-class model; AMD/Windows support unconfirmed | research |
| D1 | Materials | Material graphs, functions, instances, PBR parameters | `MaterialEditingLibrary` (create expression, connect) | Optional texture model | **live** (create_material) |
| D2 | Textures | Procedural textures; generated PBR maps | Python image synthesis → import; optional diffusion model | Optional | planned |
| E1 | Terrain and environment | Landscape, PCG graphs, foliage, biomes, lighting rigs, World Partition, Data Layers | `LandscapeEditorSubsystem` (limited), PCG (plugins present in 5.7.4 incl. PCGBiome), plugin for gaps | No | research |
| F1 | Characters | Skeletal mesh import, skeleton, retarget, Control Rig, AnimBP | Interchange, IK Retargeter Python, `ControlRigBlueprint` + `RigHierarchyController` | Optional | research |
| F2 | Animation | Sequences, blend spaces, state machines, Control Rig keys | Python asset APIs + plugin for AnimGraph | Optional motion model | research |
| G1 | Audio | Import, SoundCues, MetaSound graphs, attenuation, mixes, triggers | `MetaSoundBuilderSubsystem`, asset factories | Optional (licence-gated, e.g. Stable Audio Open community licence) | research |
| H1 | VFX | Niagara systems from templates, parameter edits, spawn tests | Niagara Python (limited) + plugin | No | research |
| I1 | Gameplay AI | Behavior Trees, Blackboards, StateTree, NavMesh, perception, GAS | C++ first; asset creation via factories; plugin for graphs | LLM | planned |
| J1 | UI | UMG widgets, HUD, menus, bindings, input focus, scaling | C++ `UUserWidget` + plugin `WidgetTree` builder | LLM | planned |
| K1 | Level design and procedural layout | Rooms, corridors, spawns, objectives, nav checks | Existing layout validator + live ops + NavMesh query | No | impl (validator) |
| L1 | Cinematics | Level Sequences, cameras, cuts, tracks, MRQ render | `LevelSequenceEditorSubsystem`, `MoviePipelineQueueSubsystem` | No | research |
| M1 | Physics | Collision presets, physics materials, constraints, measured drop/settle tests | Live ops + PIE probe reading real transforms | No | planned (simulation retired) |
| N1 | Multiplayer | Replication, RPCs, authority, listen/dedicated server tests | C++ + multi-client PIE (`-game -server` processes) | LLM | planned |
| O1 | Testing and debugging | Automation tests, functional tests, log parsing, screenshot compare, crash triage | `UnrealEditor-Cmd -ExecCmds="Automation RunTests …"`, report parsing | Vision LLM (advisory) | **live** (automation runner + report parser + packaged self-test) |
| P1 | Performance | `stat unit/gpu`, Insights traces, memreport, budgets | `-trace=cpu,gpu,frame`, `UnrealInsights` CLI export, CSV profiler | No | planned |
| Q1 | Shipping | Cook, package, launch smoke test, size report | `RunUAT BuildCookRun` | No | **live** (BuildCookRun + packaged smoke test) |
| R1 | Coverage audit | Enumerate `unreal.*` classes and factories per engine; diff against the catalogue | Handshake reflection dump | No | planned |

**Rule.** The IDE shows a capability as available only when its row is `live`. Rows never move to `live` from a unit test against a simulation.

---

## 6. Models and specialist services: decision

**Decision D-044 (taken autonomously per the user's instruction "do not ask me any questions"; reversible).** The local LLM roster stays at exactly four: `gameforge-qwen3.5-9b`, `gameforge-qwen3.5-4b`, `gameforge-27b-sft` and `llama3.1:8b`. Non-LLM generators (3D, image, audio, motion) are **specialist services**, inventoried separately in `configs/specialist_services.json` (planned). Each one is disabled until it is installed with explicit user approval and its licence row is recorded. **No generator weights are downloaded by GameForge automatically.** Until a service is enabled, every content domain falls back to procedural generation, so the system is complete without them.

**Routing by measured capability**

| Role | Default | Why |
|---|---|---|
| Planner / Game Spec author | `gameforge-qwen3.5-9b` | Tools + vision + 64K tested context; 63.9 tok/s |
| Fast discovery, classification, summarisation | `gameforge-qwen3.5-4b` | 102.8 tok/s; 121K tested context; fits beside a running editor |
| C++ authoring and repair | `gameforge-qwen3.5-9b`; escalate to `gameforge-27b-sft` only for short, hard fixes (4K context, 5.4 tok/s) | Measured benchmark ranking |
| Vision review (screenshots) | `gameforge-qwen3.5-4b` or `-9b` with mmproj | Vision projectors attached |
| Baseline / second opinion | `llama3.1:8b` | Untouched reference |

**Native tool calling (required).** Move from text-extracted JSON to Ollama's `tools` field, with a startup one-tool self-test per model, `"think": false` on every programmatic call, and explicit `num_ctx` on every request.

**Hosted heavy-model arrangements (implemented as data + gates; enabled per project).**

- **Provider profiles** (`configs/hosted_providers.json`): kind (`openai_compatible`, `anthropic`, `gameforge_gateway`), base URL, model list with declared context, tools and vision capabilities, prices per million tokens, data-policy statement, and `enabled: false` by default.
- **Credentials** are held in Windows Credential Manager through `keyring` when it is installed, otherwise in an environment variable. They never appear in config files, logs or the ledger.
- **Egress gate.** A project opts in by listing provider IDs in `<workspace>/.gameforge/egress.json`. The router refuses a hosted model for any project that has not opted in, and the UI always shows the active provider and model.
- **Spend ledger.** Every hosted call records tokens and estimated cost in `<workspace>/.gameforge/spend.jsonl`. Per-task and per-day caps are checked *before* each call, and reaching a cap stops escalation with a typed result.
- **No silent fallback.** If the hosted provider fails, the task reports the failure; it never quietly switches to a local model or another provider.
- **Promotion gate.** A hosted model joins routing only after its native tool-call self-test passes and it has run the agent-level benchmark.

**Host profile: dev-machine VRAM policy (temporary, machine-specific; `configs/host_profiles/dev-rx7700xt.json`).** The editor with offscreen rendering and the LLM cannot both be large at once on this 12 GB card. The scheduler enforces:

- 9B (~10 GB at 64K context): editor stopped, or between editor steps with `keep_alive: 0` unload before PIE, shader compile or screenshots.
- 4B: may stay resident beside the editor at ≤16K context.
- 27B: editor closed only.
- Generator services: exclusive lock, LLMs unloaded.

---

## 7. Agent runtime additions (on top of v1 §Agent runtime)

- **Task graph.** A prompt becomes a DAG of subtasks (spec → scaffold → code → assemble → test → package), each with its own predicates, budget, phase tools and context. The DAG is persisted, so it survives restart, and is shown live in the IDE.
- **Predicate library for games.** `uproject_valid`, `build_ok(target)`, `automation_pass(filter)`, `asset_exists(path, class)`, `actor_count(level, class, n)`, `pie_boots(map, seconds)`, `screenshot_exists`, `package_ok(platform)`, `packaged_smoke_ok`.
- **Diagnostics parsers.** MSVC/UBT errors, UHT errors, automation JSON reports and editor log categories become compact structured observations (file, line, code, message) for repair.
- **Repair ladder.** Fix in the same model (≤3 attempts) → bigger model with a reduced context → revert the subtask and try an alternative recipe slot → BLOCKED with diagnostics.
- **Approval scopes.** One approval covers a task's declared scope (paths, operations, build commands). T4 actions still need approval per action. Auto-approve presets for the disposable sandbox projects GameForge itself creates.

---

## 8. Resource efficiency

This section covers two separate things:

### 8.1 Shipped IDE efficiency budgets (product requirement, every user's machine)

The IDE is a coordinator. It must stay light even when the games, editors and models it drives are heavy. Each budget is measured by `scripts/ide_resource_benchmark.py` and enforced as a release gate.

| Budget | Target | How it is achieved |
|---|---|---|
| Idle RAM (private bytes, main window open, no task) | ≤ 300 MB | Lazy panel creation; virtualised item views (`QAbstractItemModel`) instead of a widget per row; bounded LRU caches; no file contents held for unopened files |
| RAM during a large task | ≤ 600 MB plus bounded caches | Streaming log and diagnostic parsing; tool outputs spill to disk past 64 KB; chat transcript paged from disk |
| Idle CPU | < 1% of one core averaged over 60 s | No polling timers faster than 1 Hz when idle; event-driven file watching; timers paused while the window is hidden |
| Cold start to interactive window | < 2.5 s | Deferred imports for heavy modules (providers, Unreal layer, indexer) |
| UI-thread stalls | None > 50 ms | All I/O, model calls, builds and editor calls run off the UI thread and can be cancelled |
| Install footprint (without models) | ≤ 250 MB | Ship only the Qt modules in use; never bundle weights, engines or browsers |
| Per-workspace metadata (`.gameforge/`) | Default cap 512 MB, user-configurable | Log rotation (5 × 10 MB); ledger compaction; diff and snapshot retention by age and count; cleanup preview before deletion |
| Child processes | Zero leaks | Every child (editor, UBT, UAT, services) belongs to a Windows job object, so closing the IDE ends them |
| Background work | Never starves the user's machine | Builds and indexing run at below-normal priority; indexing yields while the user is typing |

### 8.2 Host profile: developer machine (temporary, machine-specific)

These settings are for the current dev box (Ryzen 5 7600X, 32 GB, RX 7700 XT 12 GB). They live in `configs/host_profiles/dev-rx7700xt.json`, not in product code. The product auto-detects hardware and ships a conservative default profile.

| Resource | Dev-box policy |
|---|---|
| GPU VRAM | One heavy GPU workload at a time (editor rendering, local LLM, generator); unload LLMs with `keep_alive: 0` before PIE, shader compile or capture (§6) |
| System RAM | Warn at 85% commit; pause queued heavy jobs at 92% |
| CPU | UBT `MaxParallelActions` = 8 while interactive |
| Disk | Projects, DDC, packages and artifacts stay on `E:`; refuse heavy work below 20 GB free |
| Safety | Never shut down, restart, sleep or hibernate the machine; never call `shutdown.exe` |

## 9. Scale: large projects and large repositories

GameForge retrieves rather than stuffs, so the same design serves a 4K local model and a 1M-token hosted model. The index lives on disk (SQLite), not in IDE memory, so it respects §8.1.

- **Project index** (SQLite with FTS5, under `.gameforge/index/`): files, C++ symbols (classes, functions, `UPROPERTY`, `UFUNCTION`), Build.cs dependency graph, asset registry export (path, class, dependencies), config keys, and log events. It updates incrementally from a file watcher, a content hash and the editor's asset-registry events.
- **Hierarchical summaries** per module, folder and asset group, refreshed lazily and used to plan before opening files.
- **Bounded tools.** Every read tool pages its output (`offset`, `limit`) and reports totals. No tool returns unbounded data.
- **Context profiles** by model: the 4K, 16K, 64K and 128K profiles change how much retrieved material is pinned, not the algorithm. Larger future models plug in without redesign.
- **Targets.** Index 100k files / 50k assets in <10 minutes cold and <2 s incremental. Symbol lookup <50 ms.

---

## 10. IDE product requirements

The existing panels stay. These are the additions, ordered by user value:

1. **Mission view.** Prompt → live task graph, with predicates turning green, current step, elapsed time and budget.
2. **Evidence gallery.** Screenshots, test reports, build logs and packaged-game artifacts per task, plus before/after comparison.
3. **Approvals inbox.** Every pending approval across tasks, with scope, diff and consequence line.
4. **Unreal control center.** Editor state (offline / starting / idle / busy / PIE / crashed), launch/stop, live actor and asset browsers from read-back, PIE play button, screenshot.
5. **Resource monitor.** VRAM per process, RAM, CPU, disk free, GPU scheduler queue, loaded model.
6. **Model and service manager.** The four LLMs with digest, context profile and tok/s; specialist services with licence and status; one-click self-test.
7. **Capability matrix.** §5 rendered live from contract-test results.
8. **Command palette** (Ctrl+Shift+P) over every action, slash command and recent task.
9. **Problems panel.** Parsed compiler, UHT, automation and log diagnostics, each clickable to source.
10. **Project index search.** Symbols, assets, configs.

Quality bars: no UI-thread blocking >50 ms; every long action cancellable; state restored after a crash; keyboard-complete; 100/125/150% DPI screenshots in the test suite.

---

## 11. Work packages and exit gates

Every gate is passed **on the real engine**. Unit tests are necessary but never sufficient.

| WP | Scope | Exit gate (live) | Effort (solo, AI-assisted, full-time) |
|---|---|---|---|
| 1 Real engine link and audit | `LiveEditorLink`, ops, contract tests, crash classification, graceful quit, blocking capture | **DONE** — 16/16 live, crash/link-loss typed, graceful exit 0 | done |
| 2 Build/test/package toolchain | `unreal/toolchain.py`: scaffold, UBT + diagnostics, automation runner, BuildCookRun, packaged smoke | **DONE** — template project built, tested, packaged by tools alone | done |
| 3 Native tool calling + task graph | Native tools (**done**); repair ladder: autofix → model with hints → runtime/self-test repair (**done**); resumable pipelines via `--resume` and evidence (**done**); general multi-task DAG planner for arbitrary coding requests (open) | Scripted 10-step task completes on 9B with predicates; restart mid-task resumes | 1–2 weeks remaining |
| 4 Game Spec + first recipes | Grid family incl. Connect Four (**done**); free-form path on the host framework (**done**); arena/platformer recipe families (open) | **M2 met**; free-form whack-a-mole passes all hard gates | 1–3 weeks per further recipe family |
| 5 IDE mission/evidence/resources | Approval cards, Mission Control, Hosted Models dialog, cancel, `/game` (**done**); capability-matrix view, mission timeline view (open) | Usability script by a non-developer completes without help | ~1–2 weeks remaining |
| 6 C++ editor plugin ops | Blueprint graph nodes/pins, UMG widget tree, Niagara template ops | Generated graph compiles and passes PIE test | 5–8 weeks |
| 7 Content pipelines | Procedural mesh/texture/material/audio builders; generator-service adapters with licence gates | A prop and a sound go prompt → quarantine → promoted with provenance | 4–6 weeks (+2–4 per generator after hardware spike) |
| 8 Index and scale | §9 index, summaries, paged tools | Targets in §9 on a 100k-file synthetic project | 2–3 weeks |
| 9 Advanced domains | Landscape/PCG, characters/retarget/AnimBP, Sequencer/MRQ, MetaSound, AI/GAS, multiplayer | Each domain: one prompt-driven live end-to-end test | 14–24 weeks |
| 10 Performance and shipping | Insights/CSV profiling, budgets, regression checks | Profile captured and one optimisation verified by numbers | 3–4 weeks |
| 11 Coverage expansion | Reflection-driven catalogue diff; add or document gaps | No `unknown` rows; every gap has a reason | Ongoing |

---

## 12. Effort estimate

| Milestone | What you get | Calendar estimate (one developer + AI assistance, full-time) |
|---|---|---|
| M1: real engine control | WP1–2 | **Reached 2026-10-27** |
| M2: first prompt → playable game | WP3 (native tools) + WP4 (grid recipe) | **Reached 2026-10-27** for the grid-board family |
| M3: professional IDE + broad 2D/3D game recipes | IDE features largely done; 3–5 more recipe families; free-form quality needs the hosted tier enabled | ~1–2 months (or sooner with a hosted heavy model for free-form) |
| M4: full catalogue (characters, cinematics, VFX, audio, multiplayer, PCG worlds) | WP6, WP9–10, hosted-tier free-form authoring | ~8–14 months solo; much less with a hosted heavy model doing authoring |
| Team of 3–4 engineers | Same scope, parallel WPs | M2 ≈ 2 months; M4 ≈ 7–10 months |

These figures assume no surprises from generator hardware support on AMD. That is the largest single uncertainty, so it is isolated behind the specialist-service registry and procedural fallbacks. "Every possible game from any prompt" has no end date. The catalogue grows by recipes and operations, each one gated by a live test.

---

## 13. Not verified (carried forward and new)

- Epic's MCP plugin is absent from this 5.7.4 install. Third-party 5.7 MCP servers exist, but none is adopted.
- Blueprint graph and UMG tree editing need the C++ plugin path. The exact 5.7.4 `BlueprintGraphEditor` Python surface still needs a reflection dump.
- `-RenderOffscreen` stability for long sessions, and screenshot capture under it.
- AMD RX 7700 XT on Windows: AMD's PyTorch-on-Windows preview covers RDNA3, but TRELLIS.2-class generators use custom CUDA kernels. Run a hardware spike before committing.
- Audio model licences change. Stable Audio Open's community licence terms must be re-read at enablement time.
- Packaging on this machine (Windows SDK and toolchain are present for editor builds; a cook/package run has not been attempted).

## 14. Sources

- Epic: [Scripting the Unreal Editor Using Python](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python), [BlueprintGraphEditor Python API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/BlueprintGraphEditor), [BlueprintEditorLibrary](https://api.unrealengine.com/INT/PythonAPI/class/BlueprintEditorLibrary.html), [Unreal MCP (5.8 docs)](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-mcp-in-unreal-editor)
- Engine source in this install: `PythonScriptPlugin/Content/Python/remote_execution.py` and `Private/PythonScriptRemoteExecution.cpp` (pong fields `project_root`, `engine_root`), `PythonScriptPluginSettings.h` (config keys)
- AMD: [PyTorch on Windows preview for Radeon 7000/9000](https://www.amd.com/en/blogs/2025/the-road-to-rocm-on-radeon-for-windows-and-linux.html)
- Stability AI: [Stable Audio Open 1.0 model card](https://huggingface.co/stabilityai/stable-audio-open-1.0)
- Community (indicative only): [StraySpark Unreal MCP Server](https://www.strayspark.studio/docs/unreal-mcp-server), [BlueprintTools n-ary node bug report](https://forums.unrealengine.com/t/blueprinttools-read-graph-dsl-omits-3rd-inputs-on-n-ary-operator-nodes-booleanand-add-multiply-subtract/2744854)
- Ollama: [context length](https://docs.ollama.com/context-length), [tool calling](https://docs.ollama.com/capabilities/tool-calling)
