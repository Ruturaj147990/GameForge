# GameForge Architecture (canonical)

**Owner:** Claude (principal architect). **Last revised:** 2026-10-31. **Status:** authoritative.
This replaces `GameForge — Master Blueprint.md` (v2), `GAMEFORGE_ARCHITECTURE_EVOLUTION.md` and
`GAMEFORGE_HOSTED_INFERENCE_ARCHITECTURE.md`. Their unique content is merged here, and git history keeps the
originals.

Implementers (Antigravity) must not change anything in this document. Proposed changes go to
`docs/handovers/QUESTIONS.md` for Claude to decide.

---

## 1. Product definition

**GameForge is a Windows desktop platform that turns a natural-language game idea into a playable, verified
Unreal Engine 5 game. The user can then keep changing that game with further prompts.** It is not a game and not a
code assistant with game features. The primary loop is:

```
Idea (prompt) ──► Game Design Spec (editable) ──► Build run (plan → generate → assemble → test → package)
      ▲                                                                                   │
      └──────── change request (prompt or spec edit) ◄── Play + Evidence (scenarios, screenshots, reports) ◄┘
```

Success means that a non-developer can type *"a third-person forest adventure where I collect 5 relics while
avoiding guards"*, review a one-page design, press **Build**, and receive a packaged game. Replayable scenarios prove
that winning and losing actually work, and the user can then say *"make the guards faster and add a second area"*.

### Quality bar (from the design contract, unchanged since Blueprint v1)

No AI system is foolproof. GameForge guarantees that **wrong output cannot silently become a wrong result**:

1. The model proposes; the harness decides. No model output runs until it passes schema validation and a policy check.
2. Completion is evidence, not text. COMPLETE requires acceptance predicates that pass against observed state.
3. Fail closed. A missing token, policy, snapshot or editor connection yields BLOCKED with the cause.
4. Everything is bounded: time, output, retries, tokens, tool calls, VRAM, disk, spend.
5. Snapshot before mutate. Use editor undo transactions and **project git checkpoints** (AD-13), and label anything irreversible.
6. One writer at a time. Editor mutations are serial.
7. Read back after write. A write's return value is never the proof.
8. Untrusted data stays data. That covers model output, file contents, logs and Unreal context.
9. Local by default. Egress needs an explicit per-workspace opt-in.
10. Every claim has a ledger entry. Status is generated from evidence, and a test run against a simulation is never evidence of an engine capability.

### Security rules (non-negotiable)

- **Agent command execution** stays allowlisted, shell-free (argv only), workspace-contained, time-bounded and
  approval-gated (`backend/tools/terminal_tools.py`). The embedded terminal is user-controlled and is not a sandbox.
- **Approvals** can only be granted from a trusted UI path (`ToolGateway.execute_tool(..., approval_granted=True)`
  is called only by UI code). Model text can never approve anything.
- **Editor link:** loopback only, a 256-bit session token in `<Project>/Saved/GameForge/session.token`, checked
  with `hmac.compare_digest`. Arguments travel as one JSON string literal and are never interpolated as code. No
  arbitrary editor Python on the normal path.
- **Bridge server (`--serve`):** loopback-only bind, rejects non-loopback hosts, no wildcard CORS.
  **Default port changes from 8000 to 47815** (AD-16) to avoid UE 5.8 Unreal MCP.
- **Unreal MCP (UE 5.8+, optional):** it has no auth, so it may only be used for *read-only* ops (AD-16).
- **Hosted models:** keys live only in Windows Credential Manager (`GameForge/<provider>`) or the environment, never
  in files or logs. A provider is used only if the workspace lists it in `.gameforge/egress.json`. Spend is
  checked against per-task and per-day caps *before* each call (`.gameforge/spend.jsonl`). Unpriced metered models
  are refused. **No silent fallback** between providers.
- **Content:** no automatic download of model weights or content packs. Every asset records its real provenance
  class (§7.4). Licence territory rules are enforced by `LicenseRegistry`.
- **Protected graders** (`graders/protected/`) are never edited.

---

## 2. System overview

```
┌──────────────────────────────── Desktop App (PySide6) ────────────────────────────────┐
│ Home │ Games │ Design │ Build │ Play │ Evidence │ Assets │ Code │ Settings   + Assistant panel │
│                     view models (Qt)  ◄── signals ── services adapters                 │
└───────────────────────────────────────┬───────────────────────────────────────────────┘
                                        │ (Qt-free Python API; every call runs off the UI thread)
┌───────────────────────────────────────▼───────────────────────────────────────────────┐
│ Application core  (src/gameforge_ide/core)                                            │
│   Settings & HostProfile · JobManager (threads, cancel, Windows job objects) · EventBus│
│   ProjectStore (games list, runs index) · Evidence store                              │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Design (design/)      Forge (forge/)          Composer (composer/)    QA (qa/)          │
│  GDS schema, prompt→   RunSpec/Step DAG,       GDS → kit modules,      scenario schema,│
│  GDS, GDS patches,     executor, resume,       layouts, level ops,     generation from │
│  validators, presets   git checkpoints,        gfdef runtime JSON,     goals, runner,  │
│                        repair ladder hooks     custom-code tasks       vision rubric   │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Agent (backend/agent)  — chat agent + tool loop; plans become Forge runs (P2)         │
│ Tools (backend/tools)  — ToolGateway (typed, approval-gated), content generators     │
│ Models (backend/providers) — router by role; Ollama (local), hosted (opt-in)          │
│ Assets (backend/assets) — SQLite registry, provenance, licence classes               │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Engine layer (unreal/)                                                                 │
│   LiveEditorLink ─► gameforge_ops (in-editor Python package) ─► GameForgeEditor (C++) │
│   UnrealToolchain (UBT, automation tests, BuildCookRun)                                │
│   GameForgeRuntime (C++ kit shipped inside every generated game)                      │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Component responsibilities (one owner per concern)

| Component | Owns | Never does |
|---|---|---|
| `desktop/` | Presentation, user intent, approvals UI | File I/O on the UI thread; business rules; direct engine calls |
| `core/settings.py` | Every path, engine root, projects root, model defaults and host profile | Hard-coded paths anywhere else |
| `core/jobs.py` | Background execution, cancellation, child-process ownership | UI widgets |
| `design/` | GDS schema, validation, prompt→GDS, GDS patches, presets | Engine calls |
| `forge/` | Build runs: step DAG, persistence, resume, checkpoints, events | Knowing *what* a step does (handlers do) |
| `composer/` | Turning a GDS into a concrete composition: kit modules, layout, level-op list, runtime definition, custom-code tasks | Running the engine (it emits plans) |
| `qa/` | Scenario schema, generation from goals, runners (packaged/PIE), result parsing, vision rubric | Deciding pass on text; editing the game |
| `backend/agent/` | Conversational agent loop, tool calls, edits on existing code | Building games outside Forge |
| `backend/tools/` | Tool gateway, content generators (procedural textures, SFX, meshes, characters, motion) | Approving actions |
| `backend/providers/` | Model access, routing by role, egress/spend gates | Choosing a model silently on failure |
| `backend/assets/` | Asset registry and provenance | — |
| `unreal/` | Engine link, op catalogue and schemas, toolchain, real input | Game-specific logic |
| `GameForgeEditor` (C++) | Editor-only ops that Python cannot reach | Anything shipped in a game |
| `GameForgeRuntime` (C++) | The gameplay kit, event bus, rules engine, scenario runner | Editor dependencies |

### 2.2 Directory structure — target state (after P0–P6)

```
E:\gameforge_step1\
├── AGENTS.md  README.md  context.md  ANTIGRAVITY_HANDOFF.md  DECISION_LOG.csv  pyproject.toml  requirements.txt
├── docs/
│   ├── README.md                     ← index of the knowledge base
│   ├── 00_STATUS.md                  ← capability matrix (live status + evidence)
│   ├── 01_ARCHITECTURE.md            ← this file
│   ├── 02_AUDIT_2026-10-31.md
│   ├── 03_RESEARCH_2026-10-31.md
│   ├── 04_ROADMAP.md                 ← phases P0–P11
│   ├── 05_UX_SPEC.md
│   ├── 06_ENGINE_NOTES_UE57.md       ← verified 5.7.4 API lessons, op rules, plugin build
│   ├── 07_CONTENT_AND_MODELS.md      ← models, specialists, pipelines, licences
│   ├── 08_TESTING_AND_EVIDENCE.md    ← test strategy, commands, evidence rules, baselines
│   ├── handovers/  HANDOVER_PROTOCOL.md  P00_*.md … P11_*.md  QUESTIONS.md
│   ├── history/                      ← old context log, defect logs, superseded reports
│   └── generated/                    ← op coverage table (P0 moves it here)
├── GAMEFORGE_FINAL_MASTER_STRATEGY.md STEP4_AUDIT_REPORT.md GAMEFORGE_ROADMAP.csv TASK_INVENTORY.csv
│   ENGINE_FEATURE_COVERAGE_MATRIX.csv EVALUATION_CONTRACT.md   ← benchmark product line (frozen; read by
│                                       gameforge_bench and tests relative to the root, beside protected graders/)
├── configs/  schemas/  fixtures/  graders/  pilot_tasks/  benchmark_tasks/
├── scripts/
│   ├── engine/      _harness.py  demo_*.py  (engine demos; one shared harness)
│   ├── pipeline/    run_game_pipeline.py  run_freeform_game.py  ide_prompt_to_game_e2e.py
│   ├── ide/         ide_resource_benchmark.py  native_tool_selftest.py
│   ├── models/      train_*, generate_*_dataset.py, benchmark_long_context.py … (training lineage)
│   └── verify_all.ps1                ← the one command that runs every gate (P0)
├── src/
│   ├── gameforge_bench/              ← benchmark/training product line (unchanged)
│   └── gameforge_ide/
│       ├── core/        settings.py  jobs.py  events.py  paths.py  projects.py
│       ├── design/      gds.py  events_catalog.py  prompt_to_gds.py  presets/  patch.py  render.py
│       ├── forge/       model.py  executor.py  checkpoints.py  handlers/  legacy_adapter.py
│       ├── composer/    compose.py  layouts/  level_ops.py  runtime_def.py  codegen.py
│       ├── kit/         registry.py  modules/*.py (Python side of each C++ kit module)
│       ├── qa/          scenario.py  generate.py  runner.py  rubric.py
│       ├── backend/     agent/ tools/ providers/ assets/ models/ security/ …
│       ├── desktop/     main_window.py  views/  panels/  services/  styles/  dialogs/
│       ├── pipeline/    (legacy linear pipeline; becomes a thin Forge adapter in P2, removed in P6)
│       ├── recipes/     (legacy; become GDS presets + regression fixtures in P6)
│       └── unreal/
│           ├── live_editor.py  toolchain.py  op_catalog.py  op_schemas.py  real_input.py …
│           └── GameForge/                       ← the UE plugin
│               ├── GameForge.uplugin
│               ├── Content/Python/gameforge_ops/  __init__.py (dispatch) core.py level.py … (P0 split)
│               └── Source/ GameForgeEditor/  GameForgeRuntime/
└── tests/  unit/  integration/  doubles/
```

---

## 3. Core data contracts

These contracts are canonical. Phase handovers contain the full code. Anything here that a handover contradicts is
a handover bug: report it in `QUESTIONS.md`.

### 3.1 Game Design Spec — `gds/1` (P1)

A pydantic v2 model in `src/gameforge_ide/design/gds.py`, serialised to `<project>/GameForge/design/game.gds.json`
(this path is versioned in the project's git). Its sections follow the seven-part structure that measurably improves
generation (research R10), plus GameForge sections:

| Section | Purpose | Key types |
|---|---|---|
| `meta` | Identity, revision, origin | `schema_version="gds/1"`, `gds_id`, `revision`, `project_name` (PascalCase), `title`, `source_prompt`, `generator` |
| `overview` | Game overview | `genre: Genre`, `pitch`, `camera: CameraKind`, `players`, `session_minutes` |
| `scene` | Scene & interface | `levels: [LevelSpec(level_id, layout: LayoutKind, size_m, biome, lighting, seed, layout_params)]`, `start_level` |
| `entities` | Objects & states | `[EntitySpec(entity_id, kind: EntityKind, module: kit module id, level_id, count, placement, props)]` |
| `input` | Player interaction | `[InputActionSpec(action_id "IA_*", value_type, bindings: UE key names)]` |
| `rules` | Core rules & mechanics | `[RuleSpec(rule_id, when: EventRef, conditions: [Condition], effects: [Effect])]`, which are event-condition-action rules executed by the runtime rules engine |
| `progression` | Game flow & progression | `phases`, `difficulty`, `difficulty_params` |
| `goals` | Goal & termination | `win: [Condition]` (any one wins), `lose: [Condition]`, `score`, `sandbox` |
| `feedback` | Feedback | `[FeedbackSpec(on: EventRef, vfx, sfx, camera_shake, ui_message)]` |
| `ui` | HUD/menus | `hud: [HudElement(kind, binds: stat)]`, `main_menu`, `pause_menu`, `end_screen` |
| `art` | Art direction | `style`, `palette`, `material_theme`, `character_source`, `placeholder_ok` |
| `audio` | Audio direction | `music_mood`, `ambience`, `sfx_set` |
| `tech` | Budgets | `target_fps`, `max_frame_ms`, `max_package_mb`, `multiplayer` |
| `acceptance` | Contract | `scenarios: [ScenarioRef]`, `vision_rubric_min`, `extra_checks` |

`Condition` is a discriminated union (`count_at_least`, `stat`, `timer`, `event`, `all`, `any`; nesting depth ≤ 3).
`Effect` is a discriminated union (`add_stat`, `set_stat`, `emit`, `spawn`, `message`, `end_game`, `custom_code`).
**There is no free-text logic and no `eval`.** Anything a condition or effect cannot express is a `custom_code`
effect. That becomes a codegen task with its own compile gate and scenario gate.

### 3.2 Event contract — `GF_EVENT` v2 (P3)

Every gameplay-relevant event goes through `UGameForgeEventBus` (GameInstance subsystem in `GameForgeRuntime`).
The bus does three things:
(a) broadcasts to in-game listeners (rules engine, scenario runner, feedback);
(b) appends to a per-session JSONL file `Saved/GameForge/events/<session>.jsonl`, written with `FFileHelper`, so it **works in Shipping builds**;
(c) logs one line `GF_EVENT {"e":"pickup.collected","t":12.345,"src":"Pickup_3","d":{"value":1}}` when logging is compiled in.

Event names match `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`. The built-in catalogue lives in
`design/events_catalog.py` (Python) and `GameForgeEventNames.h` (C++). The two are kept identical by a unit test that
parses the header. The legacy free-form lines (`GF_EVENT pickup …`) stay parseable until P6 removes the last legacy
recipe.

### 3.3 Runtime game definition — `gfdef/1` (P5)

The composer compiles the runtime-relevant part of the GDS into a compact JSON document: input actions and
bindings, stats, rules, win/lose conditions, feedback and HUD bindings. It is stored in a
`UGameForgeGameDefinition` asset (`UPrimaryDataAsset`, field `FString DefinitionJson`, plus `SchemaVersion`) at
`/Game/GameForge/GD_Main`. The project's `DefaultGame.ini` points at it through
`UGameForgeRuntimeSettings : UDeveloperSettings`. **Soft references in settings are not cooked automatically**, so the
scaffolder also writes `+DirectoriesToAlwaysCook=(Path="/Game/GameForge")` under
`[/Script/UnrealEd.ProjectPackagingSettings]`.

Rationale: generated games contain **no generated gameplay C++** unless a `custom_code` effect demands it. Behaviour
comes from the tested kit plus validated data, which removes the largest failure class (rules and termination,
research R10).

### 3.4 Build run — `RunSpec` / `StepSpec` (P2)

```python
class StepKind(str, Enum):
    DESIGN = "design"; SCAFFOLD = "scaffold"; CODEGEN = "codegen"; BUILD = "build"; ASSEMBLE = "assemble"
    CONTENT = "content"; AUTOMATION = "automation"; PACKAGE = "package"; SCENARIO = "scenario"
    REVIEW = "review"; REPORT = "report"; TOOL_CALL = "tool_call"

class StepSpec(BaseModel):
    step_id: str                      # ^[a-z][a-z0-9_]{1,40}$
    kind: StepKind
    title: str
    depends_on: list[str] = []
    inputs: dict[str, Any] = {}       # JSON-serialisable; hashed into input_hash
    engine_lock: bool = False         # True ⇒ serialised with every other engine-mutating step
    approval: Literal["none", "run", "step"] = "none"
    max_attempts: int = 1             # >1 only for kinds with a repair hook (codegen, build)
    timeout_s: float = 3600
```

A run is persisted to `<project>/Saved/GameForge/runs/<run_id>/state.json` (atomic replace) together with
`events.jsonl`. A step whose record is `DONE` with an unchanged `input_hash` is skipped on resume. That is what makes
both crash recovery and incremental change requests (P8) work.

### 3.5 Scenario — `scenario/1` (P3)

```json
{"schema": "scenario/1", "scenario_id": "win_collect_all", "map": "/Game/Maps/Level1", "timeout_s": 120,
 "steps": [
   {"navigate_to": {"tag": "GF_Pickup_1", "accept_radius_cm": 120}},
   {"inject": {"action": "IA_Jump", "value": true, "hold_s": 0.2}},
   {"wait_event": {"e": "pickup.collected", "count": 5, "timeout_s": 90}},
   {"select_actor": {"tag": "GF_Cell_1_1"}},
   {"wait_s": 1.0}],
 "expect": [{"event": "game.won"}, {"no_event": "game.lost"}],
 "capture": [{"on_event": "game.won", "screenshot": "won.png"}]}
```

`UGameForgeScenarioSubsystem` executes it inside the game, launched with `-GFScenario=<abs json> -GFScenarioOut=<abs json>`.
All movement goes through injected Enhanced Input, driven by `UGameForgeAutopilotComponent`, which follows a NavMesh
path and measures leg speeds. A leg completed faster than `MaxWalkSpeed × 1.15` fails as `TELEPORT_SUSPECTED`. The
result file is the evidence. It never depends on the log, so it works in Shipping.

### 3.6 Kit module descriptor (P5)

```python
@dataclass(frozen=True)
class KitModule:
    module_id: str                 # "kit.pickup"
    version: str
    runtime_class: str             # "/Script/GameForgeRuntime.GameForgePickup"
    entity_kinds: frozenset[str]   # EntityKind values it can implement
    params_model: type[BaseModel]  # validates EntitySpec.props; maps to UPROPERTY names
    required_plugins: tuple[str, ...] = ()
    game_module_deps: tuple[str, ...] = ()   # Build.cs deps the generated game module needs
    emits: tuple[str, ...] = ()              # GF_EVENT names
    automation_tests: tuple[str, ...] = ()   # "GameForge.Kit.Pickup"
    status: str = "PLANNED"                  # PASS | PARTIAL | EXPERIMENTAL | PLANNED
    evidence: tuple[str, ...] = ()
```

The composer may only select modules with status `PASS`, or `PARTIAL` if the GDS says `allow_partial`. The IDE
shows the same status. Nothing is advertised without evidence.

### 3.7 Op contract (unchanged envelope, schemas added in P0/P2)

Every in-editor op returns `{"ok", "op", "data", "warnings", "errors", "affected_paths", "reversibility"}`. From P0
every agent-visible op also has a pydantic argument model in `unreal/op_schemas.py`. `GameTools.unreal_editor` and
the composer validate arguments **before** dispatch, and the native tool schema sent to the model is generated from
the same models. P2 makes a missing schema a unit-test failure.

---

## 4. Main data flows

### 4.1 Prompt → game (target, after P6)

```
User prompt
  └─ design.prompt_to_gds  (deterministic preset match → model draft with JSON schema → pydantic validate
                            → ≤1 repair round → fail closed with questions)  ─► GDS r1 (shown in Design view)
User reviews / edits → "Build"  (one approval covers the run's declared scope: project dir, engine ops, packaging)
  └─ composer.compose(GDS) ─► Composition {modules, layout per level, level_ops, gfdef JSON, codegen tasks, scenarios}
  └─ forge.plan(Composition) ─► RunSpec:
       scaffold → [codegen? → build_editor] → content (textures/meshes/audio, parallel-safe)
       → assemble (per level: ops with read-back; manifest) → automation (kit + game tests)
       → package(Development) → scenario (each must_pass scenario, packaged) → review (vision rubric)
       → package(Shipping, if release) → report
  └─ Forge executes: per step git checkpoint; failures → repair hook → retry ≤ max_attempts → FAILED with diagnostics
Play view: ▶ Play, scenario table, screenshots, report
```

### 4.2 Change request (P8)

```
Prompt "make guards faster" ─► design.patch: model proposes a JSON Patch against the GDS (schema-validated)
  ─► Design view shows the diff ─► approve ─► GDS r(n+1)
  ─► composer recomposes ─► forge plans with the same step ids ─► unchanged input_hash ⇒ steps skipped
  ─► only affected steps rerun ─► full scenario regression ─► report shows the delta
User-edited assets (hash ≠ recorded generation hash) are never overwritten without a conflict prompt.
```

### 4.3 Chat assistant

The assistant is a side panel available everywhere. It answers questions, edits code in Code mode through the diff
and approval flow, and **routes game-building intents to the Design/Build flow** instead of running pipelines itself.
Agent plans (multi-step tool-call tasks) become Forge runs of `tool_call` steps (P2), so there is one executor, one
persistence format and one timeline UI.

---

## 5. Engine layer

### 5.1 Live link protocol (implemented; keep)

The supervisor writes the remote-execution settings to `DefaultEngine.ini` (bind `127.0.0.1`, TTL 0), installs the
op package, writes the session token, launches the editor (`-RenderOffscreen` for unattended work; **never
`-nullrhi` with level viewports**, because `spawn_actor` crashes 5.7.4) and accepts only the discovery node whose
`project_root` matches. One call is in flight at a time. Every call has a timeout. A dropped socket is classified as
`EDITOR_CRASHED` or `EDITOR_LINK_LOST`.

### 5.2 Op authoring rules (enforced by tests)

1. `@op("name")` sits directly above `def name(` or `def name_op(` (test `test_every_op_decorator_wraps_the_function_of_the_same_name`).
2. Every op has a catalogue row in `op_catalog.py`. A mutating op names a read-only `readback_op`.
3. Every agent-visible op has an argument model in `op_schemas.py` (P0 scaffold, P2 enforced).
4. Mutations of persistent assets or levels use `unreal.ScopedEditorTransaction(desc)`. Where the editor has no undo
   (file imports, MRQ renders, asset deletes), the op returns `reversibility="irreversible"` and relies on project git
   checkpoints (P0 WI-0.6 audits all 73 mutating ops).
5. Ops that load assets during PIE use `_load_asset_pie_safe` (`EditorAssetLibrary` refuses in play mode).
6. Spawned objects get unique names (`MakeUniqueObjectName` in C++). Fixed names crash regeneration.
7. Acceptance reads state back from the live object or subsystem (`pie_actor_state`, `gameplay_objectives`), never
   from the op that caused the change.

### 5.3 Plugin modules

| Module | Type | Contents | Ships in games |
|---|---|---|---|
| `GameForgeEditor` | Editor, PostEngineInit | Blueprint graph, Widget, Landscape, Character, Animation and VFX libraries; bridge client | No |
| `GameForgeRuntime` | Runtime | Gameplay kit, event bus, rules engine, scenario runner, objectives/save, guard AI, pickups, locomotion anim instance | Yes |

Plugin dependencies grow with the kit (P5: `EnhancedInput`, `GameplayAbilities`, `Niagara` exists today). The
scaffolder enables the same plugins in every generated `.uproject`. A unit test compares the `Plugins` list in
`GameForge.uplugin` with `toolchain.REQUIRED_PLUGINS`.

### 5.4 Engine versions (AD-16)

The roadmap is pinned to **5.7.4 (CL 51494982)**. A 5.8 compatibility lane opens in P10. It rebuilds the plugin,
runs the live contract and the scenario suite, and adds `meta=(AICallable)` to read-only `UFUNCTION`s so they can
also appear as Unreal MCP tools. Mutations always stay on the authenticated link.

---

## 6. Models

| Role | Default (local tier) | Hosted tier (opt-in) | Notes |
|---|---|---|---|
| `design` (prompt → GDS, GDS patches) | `gameforge-qwen3.5-9b` | strongest available (e.g. Claude Opus 5.5 `claude-opus-5-5`) | JSON-schema output, `think:false` |
| `codegen` (custom rules, repairs) | `gameforge-qwen3.5-9b` | strongest available | Compile + scenario gates decide |
| `fast` (classification, summaries) | `gameforge-qwen3.5-4b` | small hosted model | Can stay resident beside the editor at ≤16K context |
| `vision` (rubric, screenshot review) | `gameforge-qwen3.5-4b` + mmproj | hosted vision model | Advisory until P7 calibrates it |
| `chat` (assistant panel) | `gameforge-qwen3.5-9b` | user choice | **Not** the 27B (audit F-06) |
| `heavy_local` | `gameforge-27b-sft` | — | Short hard fixes only, editor closed |

Routing lives in `src/gameforge_ide/config/model_routing.json` (package data; P0 creates it, P9 regenerates it from
eval scores, and user overrides go in the settings file). The router refuses a
hosted model unless the workspace opted in, and never falls back silently. Every programmatic Ollama call sends
`"think": false` and an explicit `num_ctx`.

Dev-host VRAM policy (12 GB, `configs/host_profiles/dev-rx7700xt.json`): one heavy GPU workload at a time; unload
LLMs (`keep_alive: 0`) before PIE, shader compilation or capture; the 27B only with the editor closed.

---

## 7. Storage layout

### 7.1 Workspace (`<workspace>/.gameforge/`, gitignored)

`sessions/`, `diffs/`, `approvals/`, `plans/` (legacy, read until P2 migrates them), `exports/`, `ide_settings.ini`,
`egress.json`, `spend.jsonl`, `runs_index.json` (P2), `index/` (P8 FTS index).

### 7.2 Generated project (`<projects_root>/<Name>/`)

```
<Name>.uproject  Source/  Config/  Content/            ← Unreal
GameForge/                                             ← GameForge-owned, committed to the project's git
  design/game.gds.json   design/history/r0001.gds.json …
  composition.json       project_graph.json (P8)      scenarios/*.json
Saved/GameForge/                                       ← evidence, gitignored
  runs/<run_id>/state.json events.jsonl logs/          evidence/ (screenshots, scenario results, reports)
  session.token
.git/                                                  ← GameForge checkpoints (AD-13)
```

### 7.3 Large artifacts

`E:\GameForge` (`models\ollama`, `artifacts`, `datasets`, `training`, `validation`, `projects`). This is a host-profile
value, not a product constant.

### 7.4 Provenance classes

`PROC` (GameForge procedural), `NATIVE` (built in-editor by ops), `CODEGEN` (model-written code),
`EPIC_CONTENT` (engine or Epic sample content under the Unreal EULA, e.g. Manny, GASP, Starter Content),
`LIBRARY` (user-imported licensed packs, e.g. Fab), `NEURAL` (a neural backend actually ran), `HUMAN`
(user-authored). A pipeline that accepts a backend name must verify that the backend ran (lesson from the TRELLIS.2
mislabel, 2026-10-30).

---

## 8. Resource budgets (shipped IDE, enforced by `scripts/ide/ide_resource_benchmark.py`)

| Budget | Target |
|---|---|
| Idle private RAM | ≤ 300 MB (measured ~90 MB) |
| RAM during a large task | ≤ 600 MB plus bounded caches |
| Idle CPU | < 1 % of one core over 60 s (measured 0.2–0.6 %) |
| Cold start | < 2.5 s (measured 0.8–1.7 s) |
| UI-thread stalls | none > 50 ms |
| Install footprint without models | ≤ 250 MB |
| Per-workspace metadata | default cap 512 MB; rotation; cleanup preview |
| Child processes | zero leaks: every child is in a Windows job object |

Scale targets (P8): project index for 100k files / 50k assets in < 10 min cold and < 2 s incremental; symbol lookup < 50 ms.

---

## 9. Architecture decision register

`ADOPTED` decisions are binding. `PROPOSED` ones become binding when the named phase starts. Numbering continues from
the 2026-10-30 register.

| ID | Decision | Status | Phase |
|---|---|---|---|
| AD-1 | One op catalogue drives the coverage docs, tool schemas and agent op list | ADOPTED, implemented | — |
| AD-2 | Graph authoring through per-domain adapters with a uniform JSON read-back (Material, MetaSound, PCG; Niagara via templates) | ADOPTED, implemented for Material, MetaSound and PCG | — |
| AD-3 | Gameplay kit in `GameForgeRuntime` instead of per-recipe templates | ADOPTED, **not applied** → P5/P6 | P5 |
| AD-4 | Per-workspace SQLite asset registry with lifecycle and provenance | ADOPTED, implemented | — |
| AD-5 | Procedural-first specialist policy; neural backends are admitted one at a time after a measured local run | ADOPTED (re-evaluated by R13/R14) | P9 |
| AD-6 | Materials → assets → world; kit → AI → genres | ADOPTED, done | — |
| AD-7 | Project graph with spec-hash ownership for incremental change | ADOPTED → P8 (Data Layer ownership exists) | P8 |
| AD-8 | Scenario-based QA | ADOPTED → realised by AD-12 | P3 |
| **AD-9** | **The Game Design Spec (`gds/1`) is the single contract between the user, the models, the composer and QA** | ADOPTED 2026-10-31 | P1 |
| **AD-10** | **Composition over code: games are kit modules + data (`gfdef/1`). Recipes become GDS presets and regression fixtures, then retire** | ADOPTED | P5–P6 |
| **AD-11** | **One executor (Forge) for game builds and agent plans, with persisted runs, input-hash skipping and resume** | ADOPTED | P2 |
| **AD-12** | **Deterministic in-game scenario runner (Enhanced Input injection + event bus + result file) as the primary playability gate; Win32 input becomes a secondary smoke check** | ADOPTED | P3 |
| **AD-13** | **Every generated project is a git repo; Forge commits after each successful step; rollback = reset to a step checkpoint (editor closed)** | ADOPTED | P2 |
| **AD-14** | **Typed op argument schemas (pydantic) validated host-side before dispatch; tool schemas generated from them** | ADOPTED | P0/P2 |
| **AD-15** | **`core/settings.py` + host profiles own every path and default; zero hard-coded host paths in product code** | ADOPTED | P0 |
| **AD-16** | **Pin UE 5.7.4; 5.8 lane in P10; Unreal MCP read-only; bridge port 47815** | ADOPTED | P0/P10 |
| **AD-17** | **Content resolution order per asset need: user library (LIBRARY/EPIC_CONTENT) → procedural/native → neural (if enabled). Licence class recorded per asset** | ADOPTED | P7 |
| **AD-18** | **Studio information architecture: Home, Games, Design, Build, Play, Evidence, Assets, Code, Settings + Assistant side panel** | ADOPTED | P4 |
| **AD-19** | **QA on Development/Test packages; release packages are Shipping with trimmed plugins and compressed paks; evidence never depends on logs** | ADOPTED | P3/P10 |
| **AD-20** | **Model defaults are chosen by GameForge's own agentic eval suite (design, patch, codegen, repair, rubric), not by code-Q&A benchmarks** | ADOPTED | P9 |
