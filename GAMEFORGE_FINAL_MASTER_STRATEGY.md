# GAMEFORGE FINAL MASTER STRATEGY
## The Authoritative Source of Truth for Vision, Requirements, Architecture, Engine Coverage, Benchmarks, Training, Governance, and Roadmap

**Version:** 3.1.0 — Progress ledger and sequential execution protocol update (19 October 2026)  
**Status:** AUTHORITATIVE SINGLE SOURCE OF TRUTH. Step 4 has been audited and verified at E4; Step 5 is UNRESOLVED / NOT ACCEPTED — EVIDENCE INTEGRITY AND TEST GATE OPEN; Step 6 is USER-AUTHORIZED PRE-GATE IMPLEMENTATION IN PROGRESS — NOT ACCEPTED. Steps 7–15 remain gated/planned or research-gated.  
**Primary objective:** Build a world-leading game-development specialist AI whose intended intelligence spans game engines and whose first deep real-engine execution target is Unreal Engine 5.7.4. Establish measurable capability, compare existing models, specialize only with rights-cleared data and execution feedback, and build the full Windows product only after the model-and-agent loop proves value.

> **Evidence discipline:** The benchmark and Game IR concepts originate in the supplied GameForge v0.1 draft. The combined roadmap and architecture below are synthesis and engineering recommendations. None of the proposed advantages should be treated as proven until measured. Engine versions, licensing, model licenses, APIs, and tool availability must be verified when each implementation decision is made; this blueprint does not claim fresh verification.


**Current project status (19 October 2026):** Step 4 evidence has been audited and reconciled at E4. Step 5 remains UNRESOLVED / NOT ACCEPTED due to reviewer findings regarding test discovery scope, candidate diffs, and scorecard consistency. Under explicit user direction, Step 6 rights-aware data factory work is in progress as a user-authorized pre-gate implementation branch without certifying Step 5 or waiving subsequent gates.

**Engine version policy:** Pin existing fixtures and baseline runs to the locally reported Unreal Engine 5.7.4 installation until the initial benchmark is frozen. Unreal Engine 5.8 was announced by Epic in June 2026; it is a later version, not the version installed in the supplied environment. Add a version-migration task rather than silently changing the baseline ([official Unreal Engine 5.8 announcement](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available)).

**Scope and honesty note:** “All engines” is the model's intended breadth, not a promise that every engine, version, plugin, and API is already supported. The blueprint defines the feature domains, initial engine catalogue, coverage levels and registry process required to grow that capability. Engine features change; the registry must be updated from version-specific sources and tests. The Step 1–3 test results in this document are reported results, not independently rerun here.

---

## 1. Executive decision

### Build the intelligence first—not the desktop app

The project should proceed in this order:

1. Define success and build a reproducible benchmark.
2. Establish strong-model baselines using the same tasks and harness.
3. Build the smallest execution harness that can grade real Unity and Unreal projects.
4. Test model approaches: strong general model with tools, specialized fine-tune, and Game IR plus contracts.
5. Build a rights-cleared data pipeline from tasks, editor trajectories, builds, test failures, repairs, and successful outcomes.
6. Train and evaluate a game-development specialist through supervised fine-tuning and then outcome-verifiable optimization where feasible.
7. Prove measurable improvements on private held-out tasks and multi-step project changes.
8. Expand into characters, animation, assets, performance, debugging, and complete mini-games.
9. Only then build the Windows product and polished engine integrations around the proven model.

### Product thesis

A game-development model should not merely produce plausible scripts. It should understand the requested gameplay, create or modify engine-native code and assets, execute the project, observe test results, diagnose failures, repair them, and preserve existing functionality.

### What “world number one” means

Do not use an unqualified marketing claim. Define it as a measurable target: top performance on a published, reproducible, independently runnable game-development benchmark, with agent harness, tool access, time budget, model version, cost, and task split disclosed. Report general-model comparisons under equal conditions. A benchmark is only credible if it resists contamination, includes private held-out tasks, and includes human-reviewed task quality.

---

## 2. Non-negotiable principles

1. **Execution beats eloquence.** Builds, runtime probes, asset validation, and regression tests outrank answer quality.
2. **Real engines in the loop.** Do not use mocked engine behavior as the final judge.
3. **Benchmark before major training spend.** Know what the current model can and cannot do before deciding which training approach is worth funding.
4. **Specialize without crippling reasoning.** Preserve general coding, mathematical, physical, and planning capabilities that matter for game development. Minimize wasted inference and training—not useful competence.
5. **Treat Game IR as an experiment.** Do not force all tasks through an abstraction that may be too limited.
6. **Keep native escape hatches.** Difficult engine-specific features must remain expressible in C#, C++, Blueprint/editor scripting, shaders, or other native formats.
7. **One spec, explicit backend differences.** Cross-engine parity is a testable target, not a claim that Unity and Unreal behave identically.
8. **Every edit is reviewable and reversible.** Work from version-controlled snapshots; produce diffs, logs, and a rollback path.
9. **Data provenance is part of the dataset.** Record source, license/permission basis, allowed uses, transformation history, and removal obligations.
10. **No benchmark leakage.** Hidden tests and reference solutions remain unavailable to the acting model.
11. **Separate functionality from feel.** First make the controller correct; then optimize tunable parameters against measurable feel targets.
12. **State uncertainty explicitly.** Research hypotheses, benchmark results, and production guarantees must never be conflated.

---

## 3. Target capabilities

### Level A — Engine fluency
- Understand project structure, engine versions, build logs, compiler diagnostics, editor APIs, native scripting patterns, and asset references.
- Repair broken builds and migrate deprecated APIs.
- Explain and safely change existing projects without destructive broad rewrites.

### Level B — Gameplay components
- Character/pawn movement, camera, jump, collision, health/damage, inventory, interactions, projectiles, abilities, enemy state machines, checkpoints, respawn, and HUD bindings.
- Multi-file implementation that preserves architecture and existing tests.

### Level C — Engine-native authoring
- Create and wire prefabs/scenes in Unity and actors/components/Blueprint assets in Unreal through supported editor APIs or commandlets.
- Create input mappings, UI assets, references, import settings, collision, materials, and other serialized assets.

### Level D — Character and animation pipeline
- Produce or ingest a mesh; validate topology, UVs, triangle/LOD budgets, skeleton, skin weights, retargeting, clips, and animation graph/state machine.
- Integrate locomotion, jump, landing, root motion where appropriate, and gameplay events.
- Verify generated or imported assets inside the target engine. Mesh generation, rigging, animation, and retargeting may initially be handled by separate tools/models.

### Level E — Project-scale engineering
- Implement features across an existing codebase; debug regressions; profile runtime; manage dependencies and engine-version differences; support save/load and networking scaffolds where specified.

### Level F — End-to-end game construction
- Turn a design brief into a playable mini-game with a coherent loop, level setup, controls, UI, feedback, assets, tests, performance checks, and a build artifact.

### Level G — Iterative, long-horizon work
- Maintain project/world state across many actions.
- Make a change, run the right checks, inspect failures, repair only affected parts, and prove that unrelated behavior did not regress.

---

## 4. GameForge-Bench

### 4.1 Design and reporting
Use eight tiers, as in the supplied draft:

| Tier | Focus | Primary grading |
|---|---|---|
| T1 | Engine knowledge and repair | Build + tests |
| T2 | Gameplay components | Runtime tests + behavior/feel probes |
| T3 | Scene and editor authoring | Saved-asset structure and runtime checks |
| T4 | Animation | Asset structure + sampled pose/transition probes |
| T5 | Asset pipeline | Asset validation + performance budgets |
| T6 | Project-scale features | Hidden tests + regression suite |
| T7 | End-to-end mini-game | Bot playtest + calibrated visual/human review |
| T8 | Debugging and performance | Hidden reproduction + performance budget |

The initial slice should focus on T2 and T3, since they test useful core abilities without requiring the entire asset-generation stack. Build a starter set of 30 *logical task specifications* with paired Unity/Unreal variants wherever semantically feasible. The benchmark runner should treat each engine variant as a separate execution.

### 4.2 Task package
Every task should be self-contained and version-controlled:

```text
tasks/<task-id>/
  task.yaml            # public task prompt, engine/version, time/tool limits, allowed paths
  starter-project/     # project snapshot or reproducible fixture
  visible-tests/       # optional tests that agents are allowed to inspect
  hidden/              # hidden tests, probes, asset checks; grader-only access
  reference/           # expert solution and rationale; grader-only access
  provenance.yaml      # origin, license/permission basis, transformation notes
```

Do not mount `hidden/` or `reference/` into the agent's workspace. Run every attempt against a clean snapshot.

### 4.3 Grading pipeline
Apply checks in order and retain a separate result for each layer:

1. **Policy/static checks:** allowed edit paths; no tampering with tests or graders; no disabling checks; no unauthorized network access; no secrets in logs.
2. **Build/import:** Unity batch build/test compilation or Unreal build/automation path appropriate to the task.
3. **Unit/integration tests:** visible and hidden test suite.
4. **Runtime behavior probes:** replay controlled inputs with fixed timestep and seeded randomness where possible; compare measured outcomes against tolerance bands.
5. **Saved-asset checks:** expected components/classes/references/state machines/UI bindings exist; no missing scripts/references. Use editor APIs/commandlets for Unreal assets rather than hand-writing opaque binary assets.
6. **Performance/resource checks:** frame time, allocation/memory, draw calls, triangle budgets, or other task-specific constraints on declared reference hardware.
7. **Visual/gameplay review:** only for tasks where visual or experiential quality cannot be adequately reduced to deterministic probes. Calibrate automated visual judges against human labels and publish agreement/error bars.
8. **Regression:** confirm the fix did not break existing behavior.

A compile pass is not a full pass. Report which layer failed.

### 4.4 Controller feel probes
Use measurable, tolerance-based probes for:
- Jump apex height and time to apex.
- Run speed cap.
- Acceleration and deceleration response.
- Stop distance.
- Slope and step-up behavior.
- Coyote time and jump buffering.
- Camera collision (camera never intersects blocking geometry in the defined setup).
- Input response latency.

Because physics behavior can differ between engines and machines, use tolerances and per-backend conformance tests rather than demanding bit-identical results.

### 4.5 Metrics
Publish:
- Pass@1 and, where justified, pass@k by tier and overall.
- Layered completion rates: build, tests, behavior probes, asset validation, performance, visual/human review.
- Regression rate.
- Cross-engine parity for paired tasks.
- Task completion time, tokens, tool calls, and inference/training cost.
- Human expert acceptance and severity-weighted defect rate.
- Reliability across repeated runs, not just best-of-many.
- Full harness card: model/version, prompt policy, tools, context strategy, retries, time/step budget, hardware, engine version, and dependencies.

### 4.6 Splits and contamination controls
- Public development split for iteration.
- Public rotating test split for visible comparison over time.
- Private held-out split for claimed performance.
- Freshly authored or substantially mutated tasks; never rely exclusively on tutorial-derived tasks.
- Hidden-test mutations where feasible, immutable grader, occasional human audit, and a policy that a benchmark score must state whether test files were agent-accessible.
- Freeze benchmark versions and report results separately across versions.

### 4.7 Starter task inventory: 30 logical specifications
Pair Unity/Unreal variants wherever the gameplay semantics and engine fixtures permit it. T2 and T3 are intentionally mixed.

**T2 — Gameplay components (15)**
1. Third-person character movement and camera orbit.
2. Platformer jump with variable jump height.
3. Coyote time and jump buffering.
4. Health and damage with invulnerability window.
5. Pickup collection with one-time activation.
6. Inventory with stack limits and add/remove operations.
7. Enemy finite-state machine: idle, chase, attack, recover.
8. Projectile with collision, damage, and lifetime cleanup.
9. Interactable door activated by a nearby player.
10. Cooldown-based ability with a resource cost.
11. Checkpoint activation and player respawn.
12. Death/respawn flow that resets only specified state.
13. Stamina drain and regeneration with movement constraints.
14. Moving platform with safe rider transport.
15. Damage/death events that drive a clean UI/gameplay update without duplicate event subscriptions.

**T3 — Scene/editor authoring (15)**
16. Create and wire a player prefab/actor with required components and references.
17. Create a HUD with health and stamina bindings.
18. Author a pickup object and place multiple configured instances.
19. Wire a door, trigger volume, and interaction target.
20. Assemble a small enemy encounter with spawn points and bounds.
21. Build a simple platformer test level with specified start/goal/obstacles.
22. Create checkpoint and respawn locations with valid references.
23. Configure input actions/mappings for move, look, jump, interact.
24. Create a projectile prefab/actor with collision and visual reference.
25. Create a damageable target with health and feedback hooks.
26. Set collision channels/layers for player, enemy, projectile, and world.
27. Configure a moving platform and its path/waypoints.
28. Create a basic pause/settings UI and wire resume/restart actions.
29. Set up a camera rig and verify wall-collision configuration.
30. Create an animation-ready character setup using supplied rig/clips and verify required graph references (full animation behavior is reserved for T4 expansion).

Every task needs an exact prompt, initial project, allowed edit paths, setup instructions, grading layer list, hidden test/probe plan, reference solution, task owner/reviewer, estimated difficulty, and provenance record. The list above is inventory only, not yet a validated benchmark.

---

## 5. Model strategy: specialize first, scale with evidence

### 5.1 Start from a capable base model
Do not train a frontier model from scratch as the first move. Select one or more candidates based on license, coding ability, long-context behavior, tool use, inference cost, local/cloud deployment requirements, and fine-tuning access. Verify current model terms at selection time. Avoid choosing by general benchmark score alone; run the baseline suite first.

### 5.2 Candidate model experiments
Compare, on identical tasks and budgets:
1. Strong general model + project context + tools.
2. Same base model with game-development supervised fine-tuning.
3. Fine-tuned model with retrieval over versioned engine docs/schemas.
4. Model that plans/outputs a constrained Game IR plus contracts.
5. IR model with native-code/editor escape hatches.
6. Modular specialist design: core reasoning model plus optional code, visual/scene, animation/asset, and QA experts/router.

Keep the architecture that wins in held-out completion, cost, latency, reliability, and maintainability—not the one with the most novel diagrams.

### 5.3 Proposed learning pipeline

**Stage 0 — Baseline:** no training; characterize error classes and capability gaps.

**Stage 1 — Domain-adaptive continued training (optional):** use rights-cleared engine/game-dev material only if the base model benefits from it. Evaluate against an untouched baseline to ensure no regressions in general coding or reasoning.

**Stage 2 — Supervised fine-tuning:** train on expert-authored tasks and examples of plans, project inspection, patch generation, tool calls, structured outputs, diagnosis, repairs, and concise completion reports. Include both successes and carefully labeled failed attempts with the correct repair trajectory.

**Stage 3 — Preference/quality alignment:** compare candidate solutions using expert preferences and deterministic test outcomes. Do not let stylistic preferences override measured behavior.

**Stage 4 — Outcome-verifiable optimization:** reward builds, hidden test passes, behavior probes, asset checks, regression safety, and performance budgets. Start with tasks whose rewards are reliable and cheap. Reward shaping must avoid hacks such as deleting features, weakening tests, hard-coding probe traces, or bypassing the engine.

**Stage 5 — Distillation:** distill high-quality specialist trajectories into a smaller model for low-latency/local use, only after the teacher has a demonstrated advantage.

Each stage needs ablations and rollback criteria. Training is not a substitute for better harnesses or task definitions.

### 5.4 What should be inside the model versus supplied at runtime

**Model weights:** general reasoning needed for game development; game architecture patterns; tool-use habits; C#/C++/shader/Blueprint/editor concepts; debugging strategies; gameplay-system synthesis; handling structured specs.

**Versioned retrieval:** current API names, engine-version changes, plugin docs, project symbols, coding conventions, asset schemas, build settings, and project-specific facts that become stale.

**Deterministic tools/compiler:** unit conversion, schema validation, code generation for stable patterns, project indexing, tests, asset creation through supported APIs, builds, profiling, and rollback.

**Specialist models/services:** mesh/image generation, auto-rigging, motion generation, audio generation, vision-based screenshot/video understanding. Treat these as tools until benchmark evidence justifies training a unified multimodal model.

### 5.5 Data factory and rights
Potential data families, only where terms permit the intended use:
- Official documentation and API references.
- Permissively licensed repositories and project samples.
- Internally authored benchmark projects and solutions.
- Synthetic Unity/Unreal projects generated specifically for training.
- Expert-authored gameplay specs, code, assets, and bug fixes.
- Tool-use trajectories from models operating in sandboxed engines.
- Compiler/build/test logs linked to corrective patches.
- Scenes, prefab/actor structures, animation graphs, shader/material configurations, and asset metadata.
- Profile traces and before/after performance changes.

For every record preserve source/provenance, license or permission, allowed training/redistribution uses, engine/version, task spec, tool trace, final diff, evaluation results, and any removal obligation. Do not assume documentation access, engine source access, marketplace assets, model outputs, or open repositories automatically grant training or redistribution rights. Obtain legal review before relying on any source family.

### 5.6 Training examples should capture process, not just answer
A high-value trajectory records:
1. User request and project snapshot.
2. Model's interpreted requirements and assumptions.
3. Repository/project inspection and relevant context.
4. Plan and expected files/assets to change.
5. Tool actions and edits.
6. Build/test/probe outputs.
7. Diagnosis and repair actions.
8. Final clean rerun, diff, regression result, and summary.

Do not blindly train on every trajectory. Failed, noisy, insecure, license-unclear, or grader-gaming trajectories need filtering or explicit negative labels.

---

## 6. Game IR and executable contracts

### 6.1 Hypothesis
A typed, engine-neutral gameplay representation may improve consistency and testability on T2–T4. It is unproven. Compare direct generation, IR+contracts, and IR+native escape hatches with the same model/harness/task budgets.

### 6.2 Minimal v0.1 layers
- **Entities:** named gameplay objects and typed components.
- **Behaviors:** hierarchical state machines and event transitions.
- **Rules:** event-driven or tick-based systems, expressed with bounded semantics.
- **Feel:** tunable parameters with ranges and measurable targets.
- **Contracts:** invariants, expected ranges, and executable probes.
- **Bundles:** character/asset/animation package references plus QA rules.
- **Bindings:** backend mappings and explicitly typed native escape hatches.

Expressions should be typed, include units, be deterministic, and avoid unbounded loops or I/O. Native actions must be explicit and auditable.

### 6.3 Units and backend semantics
The compiler owns conversions and coordinate mappings. The draft proposes a canonical left-handed, Y-up, meter-based representation, with explicit back-end conversion to Unity and Unreal conventions. This must be verified against the actual conventions and APIs in selected engine versions before implementation; never encode assumptions without tests.

### 6.4 Contracts as durable value
Even if the IR fails to improve generation, executable contracts and behavior probes remain useful for training rewards, runtime verification, and regression prevention. Keep contracts as a separate module so the IR can be narrowed or dropped without losing them.

### 6.5 Native escape hatches
Use native blocks for features where engine-specific capabilities, plugins, networking, custom physics, shaders, animation systems, or performance considerations cannot be cleanly expressed. The contract should declare inputs/outputs, engine/version, allowed side effects, and validation method.

### 6.6 Experiment gate
Keep IR only if it improves held-out completion, cross-engine parity, or overall cost/reliability on predefined criteria. Before the experiment, define the minimum practically meaningful improvement and uncertainty method; do not declare victory after observing results.

---

## 7. Character Bundle: flagship capability

Treat a character as a validated bundle rather than a single generated mesh or script.

### Inputs
- Design brief, style/reference images if licensed, target engine/version, target platform, camera and control style, polygon/LOD budgets, rig requirements, and gameplay feature list.

### Bundle contents
- Mesh references and import settings.
- Topology/triangle/UV/LOD metadata.
- Skeleton and bone mapping.
- Skin-weight constraints.
- Retarget configuration.
- Animation clips and metadata: idle, walk, run, start/stop, jump start/loop/land, attack, hit, death as required.
- Animation graph/state machine and blend parameters.
- Controller/gameplay components, input bindings, collision, camera configuration, and event wiring.
- QA checks and generated tests.

### Validation gate
1. File and import integrity.
2. Mesh/topology/UV/triangle/LOD checks appropriate to the target.
3. Skeleton and skin weights valid.
4. Retargeted motion imports and produces valid poses.
5. Animation graph transitions work on sampled inputs/timestamps.
6. Character controls pass movement/feel probes.
7. Collision and camera pass geometry tests.
8. Asset references resolve in a clean project.
9. Performance budgets pass on declared hardware.

Potential tools for mesh, rigging, motion, and animation can be composed initially. Do not claim fully automatic high-quality character generation until this whole chain works repeatedly on held-out characters. For foot sliding and subjective motion quality, define quantitative proxies plus human review; a single threshold cannot represent all motion quality.

---

## 8. End-to-end agent workflow (eventual product)

For each feature request, use the following loop:

1. **Understand:** resolve intended behavior, engine/version, project constraints, target platform, and acceptance criteria.
2. **Inspect:** index code, scenes, prefabs/actors, asset references, settings, plugins, tests, and recent failures.
3. **Specify:** create a concise feature spec and contracts. Use Game IR only where supported; identify required native blocks.
4. **Plan:** list changes, dependencies, risk, tests, rollback point, and expected asset/code outputs.
5. **Generate:** produce code, editor actions, scene assets, and asset/animation jobs.
6. **Apply safely:** perform allowed edits in a snapshot or isolated worktree; keep tool permissions narrow.
7. **Build/import:** compile and import in the real engine.
8. **Test:** run unit, integration, hidden/equivalent local probes, saved-asset validation, and performance checks appropriate to the task.
9. **Observe:** inspect logs, scene state, screenshots/video, profiler traces, and test failures.
10. **Repair:** propose a minimal corrective diff; do not hide or weaken tests.
11. **Regression:** rerun target tests and affected existing suites.
12. **Review:** show diff, evidence, known limitations, and any unresolved issue.
13. **Commit/package:** only after explicit policy and quality gates; preserve undo/rollback.
14. **Learn:** save eligible, rights-cleared trajectory artifacts for future training, with secrets and private content filtered.

The agent's status output should differentiate **generated**, **compiled**, **tested**, **visually reviewed**, and **accepted**. It must not collapse these into a misleading “done.”

---

## 9. Future system architecture

This is the destination architecture, not the first build.

```text
Windows client (future)
  ├─ Project/engine selector and task brief
  ├─ Diff, approvals, run history, rollback controls
  └─ Observability: logs, test reports, screenshots, profiler summaries
          │
          ▼
Orchestrator / policy boundary
  ├─ Project index and persistent project/world model
  ├─ Planner + task decomposition
  ├─ Model router (cloud flagship / local distilled model)
  ├─ Retrieval: versioned APIs, project symbols, schemas, prior verified patterns
  ├─ Tool permission and approval service
  └─ Trace/evaluation/data-provenance recorder
          │
          ├─ Game reasoning model
          ├─ Code/editor specialist (may be same model initially)
          ├─ Visual/scene understanding model
          ├─ Mesh/rig/motion/audio tools
          └─ QA critic / playtest agent
          │
          ▼
Engine bridge adapters
  ├─ Unity editor/batchmode, tests, asset APIs
  └─ Unreal editor/commandlets, build/tests, Python/editor APIs
          │
          ▼
Sandboxed project snapshot → build/import → probes → QA → repair
          │
          └─ Signed evaluation artifacts + reversible diff + eligible training data
```

### Architecture principles
- Reuse supported engine/editor APIs or existing bridges where reliable; do not rebuild integration surface unnecessarily.
- Keep an internal abstraction for tools so changing an MCP server or editor API does not require retraining the model for every transport detail.
- Version all project indexes, engine schemas, generated assets, tool versions, and test outputs.
- Store a project/world graph that links entities, components, scripts, references, animation states, events, input actions, and tests. Refresh it after edits; never assume stale indexes are correct.
- Model router decisions should be benchmark-driven: local versus cloud, text versus vision, simple patch versus high-risk task.
- Every autonomous action should have a declared permission scope and an auditable trace.

---

## 10. Safety, security, reliability, and licensing

- Run agent jobs in isolated project snapshots or disposable workers with resource limits.
- Disable network access by default; allowlist dependencies or downloads when needed and approved.
- Keep credentials outside prompts, logs, datasets, and generated project files.
- Protect the grader, hidden tests, reference solutions, and benchmark secrets.
- Validate generated code, plugins, scripts, and build steps before execution; treat project files and imported assets as potentially hostile.
- Restrict writes to allowed paths; detect modifications to tests, project settings, or grading logic.
- Preserve a clean git diff, rollback snapshot, and test evidence for every job.
- Record asset/model/tool provenance and license obligations; do not silently train on restricted code or generated content with uncertain terms.
- Verify current Unity/Epic terms for CI, seat/license activation, engine redistribution, source access, and generated asset use at implementation time.
- Have a human approval gate for destructive operations, dependency upgrades, external uploads, publishing, and actions with unclear legal/security consequences.

---

## 11. Roadmap and decision gates

The phases below are strategic gates. The numbered implementation Steps 1–15 later in this document track operational milestones. Where historical draft wording conflicts with the updated current-state ledger, the current-state ledger and latest verified handoff take precedence.

### Phase 0 — Charter and benchmark definition
**Deliverables:** mission, outcome metrics, task schema, initial inventory, provenance policy, evaluation protocol and decision log.
**Reported status:** foundational specifications and inventory exist; treat each task as only as complete as its fixture, grader and execution evidence.
**Gate:** prompts are clear, graders test the intended behavior, hidden data is protected and results are reproducible.

### Phase 1 — Unreal-first execution foundation
**Deliverables:** runner, clean snapshots, engine adapters, build/test capture, policy checks, behavior probes, asset checks, reporting and controller/health/pickup/composition pilots.
**Reported status:** Steps 1–3 handoffs report Unreal Engine 5.7.4 validation; Unity adapters and C# counterparts exist but real-engine Unity execution was reported unavailable.
**Gate:** real Unreal tests pass, known-defect candidates fail for the intended reason, old pilots remain stable and engine verification levels are honest.

### Phase 2 — Complete the next vertical slice and freeze a baseline benchmark
**Deliverables:** native Unreal health/stamina HUD, projectile collision/combat, engine-neutral intelligence scope, engine feature registry, cross-engine benchmark plan, engine-knowledge registry, seven engine-neutral tasks, and task/report metadata.
**Reported status:** Step 4 handoff summary supplied by the user reports completion on Unreal Engine 5.7.4, 12 HUD probes, 12 projectile probes, 94/94 unit/protected-oracle tests, 6/6 real-engine integration tests, and no regressions to prior pilots. Independent re-execution remains a separate audit action.
**Gate:** inspect `GAMEFORGE_STEP4_HANDOFF_REPORT.md` and actual artifacts; independently rerun applicable tests where feasible; distinguish widget-state tests from rendered-visual evidence; confirm projectile tests use genuine engine collision events.

### Phase 3 — Baseline model evaluation
**Deliverables:** fair baseline protocol and results from at least two suitable existing models, under equal task/context/tool/time budgets; failure taxonomy and per-domain scorecard.
**Gate:** results are reproducible, costs are recorded, human review calibrates subjective dimensions and private held-out tasks remain uncontaminated.

### Phase 4 — Rights-aware data factory
**Deliverables:** trajectory schema, source/license register, data validation, task/reference/defect curation, deduplication, leakage checks and labeled failure corpus.
**Gate:** every training-intended record has provenance, permission status, version metadata and quality labels.

### Phase 5 — Specialist SFT prototype
**Deliverables:** a small adapter/LoRA or other justified fine-tune using a licensed base and clean data; controlled before/after evaluation; broad capability regression set.
**Gate:** measurable held-out game-development gain without unacceptable regressions or licensing problems.

### Phase 6 — Tool-use and verifiable outcome optimization
**Deliverables:** tool-call and repair trajectories, safe outcome rewards, hidden grader robustness, and multi-step evaluation.
**Gate:** end-to-end task success improves under the same budget and security/failure rates remain acceptable.

### Phase 7 — Game IR/contract experiment
**Deliverables:** minimal IR for a small task set, compiler/backend and native escape hatch, controlled direct-generation comparison.
**Gate:** measured advantage or an explicit decision to narrow/drop IR. Keep contracts regardless if they prove useful.

### Phase 8 — Multimodal, character and asset expansion
**Deliverables:** visual QA, animation state graph, retargeting, Character Bundle, asset pipeline checks and bot playtests.
**Gate:** native-engine integration and objective QA pass on held-out assets/projects, not just curated demonstrations.

### Phase 9 — Broader engine support and Windows productization
**Deliverables:** real Unity/Godot runners when available, staged other-engine adapters, desktop shell, diff/review/rollback and permissioned tool UI.
**Gate:** each claimed engine capability has a declared coverage level; the app measurably improves a real workflow and security/legal review is completed.

### Phase 10 — Scale only where evidence justifies it
Consider large continued pretraining, from-scratch pretraining, MoE, unified multimodal training or learned engine simulation only when controlled experiments expose a capability ceiling that cheaper approaches cannot solve economically.

## 12. Novel R&D hypotheses to preserve

These are promising hypotheses, not validated results:

1. **Gameplay contracts:** every feature begins with explicit invariants and probes, turning vague requests into executable acceptance criteria.
2. **Structure versus feel:** use the model to design architecture, then a numerical optimizer to tune controller parameters against measurable targets.
3. **Adversarial bot playtesters:** a builder agent creates a feature while a critic agent tries to expose broken behavior, exploit paths, softlocks, and poor feedback; the builder repairs failures.
4. **Character Bundle:** one typed manifest coordinates geometry, rigging, motion, animation graph, gameplay, and QA.
5. **Project/world graph:** a continuously updated semantic graph spans code, assets, scene state, references, event flows, tests, and behavior.
6. **Learned engine-action simulator:** predict editor-action effects for cheap candidate exploration, but verify final outcomes in a real engine. This is research-grade and should not be an early dependency.
7. **Cross-engine semantic agreement:** paired backends and shared contracts provide data and evaluation signals, while backend-specific behavior remains explicit.
8. **Self-healing with reversible changes:** detect failures, isolate a minimal change, rerun validation, and roll back automatically when expected metrics worsen.

Do not make the learned simulator, fully unified multimodal model, or universal IR prerequisites for the first useful specialist.

---

## 13. Team and resource strategy

Initial roles, even if some are part-time or combined:
- Game-engine lead covering Unity and Unreal semantics.
- Evaluation/benchmark engineer.
- ML fine-tuning and data engineer.
- Automation/build infrastructure engineer.
- Technical artist or character-animation specialist for later Character Bundle work.
- Legal/licensing review as needed.

Start with existing models and rented/available compute for controlled fine-tuning experiments. Do not commit to a large training cluster until the benchmark shows a clear opportunity, data rights are understood, and the expected gain of training over prompting/tools is measured. Keep costs as an experiment-level ledger: inference, engine runners, GPU time, storage, human annotation, and failed runs. Avoid treating parameter count as a proxy for game-development competence.

---

## 14. Step 1 — Original foundation plan (reported complete)

### Historical objective
This section preserves the initial Step 1 plan for traceability. The supplied Step 1 handoff reports that the benchmark foundation and first Unreal controller pilot were implemented and validated. Do not rerun Step 1 blindly; inspect the current repository and historical artifacts before changing it.

The original objective was to create a trustworthy definition of success and a small set of real game-engine tasks before training a model or building the Windows app.

### Step 1 deliverables
1. **Project charter:** target users, model-first scope, out-of-scope items, and operational definition of “best at game development.”
2. **Benchmark v0.1 task inventory:** the 30 logical T2/T3 task specs in Section 4.7, marked as draft until implemented and reviewed.
3. **Task schema:** required metadata, project inputs, path limits, engine/version pinning, time/tool budget, grading layers, and provenance.
4. **Evaluation contract:** exact build/test/probe outputs, thresholds, tolerances, and report format for each task.
5. **Baseline protocol:** equal harness and budget across the base model(s) and future specialist; repeated runs on a subset to estimate variance.
6. **Implementation decision log:** unresolved items, owner, evidence needed, decision, and date.

### Original Step 1 work sequence (historical checklist)
1. Freeze initial scope to T2/T3 and the 30 logical specifications.
2. Pick one Unity and one Unreal version for the initial harness only after confirming the actual installed/licensed versions and CI viability.
3. Select 6 pilot tasks (3 T2, 3 T3) spanning both engines; implement their project fixtures and deterministic graders first.
4. Ask two experienced developers to solve/review those tasks independently; resolve ambiguous prompts and flaky checks.
5. Run strong baseline model(s) through the same harness and capture traces, failures, costs, and time.
6. Fix benchmark flaws before expanding all 30 tasks or training.

### Proposed first six pilot tasks
- T2: third-person movement + camera.
- T2: health/damage with invulnerability and death behavior.
- T2: pickup collection with one-time activation.
- T3: player prefab/actor composition and required references.
- T3: health HUD binding.
- T3: input action/mapping setup.

Use Unity/Unreal paired variants where equivalent fixtures are practical. The first pilot set should test whether the harness itself is reliable—not just whether the model succeeds.

### Step 1 acceptance gate (reported as passed; rerun after shared-infrastructure changes)
Proceed to Phase 1 expansion only when:
- Task prompts are unambiguous and solveable without hidden context.
- Allowed edit paths and hidden-test boundaries are enforced.
- A clean baseline project can be restored for every attempt.
- Build/test/artifact outputs are captured automatically.
- Graders distinguish compilation, runtime behavior, and asset structure.
- Repeated runs expose and quantify flaky probes rather than hiding them.
- Two expert reviewers agree the task checks the intended behavior.
- Provenance and licensing are recorded for each fixture and dataset item.

### Do not do yet
- Do not train a large model from scratch.
- Do not lock the product to a single model architecture or a full Game IR.
- Do not build the polished Windows desktop application.
- Do not claim world-leading performance from a public benchmark alone.
- Do not start with text-to-3D as a substitute for gameplay-system correctness.

---

## 15. Open decisions register

| Decision | Default position | Evidence required to change it |
|---|---|---|
| Train from scratch or specialize a base? | Specialize a capable base first | Evidence that base limits cannot be removed economically |
| Single model or specialist modules? | Benchmark both; start simple | Held-out quality/cost/latency results |
| Game IR mandatory? | No; experimental | Controlled win against direct native generation |
| Use LLM-as-judge? | Only calibrated visual/end-to-end review | Agreement with human labels and audited error rates |
| Train on public repositories? | Only with reviewed rights/terms | Written provenance and legal approval appropriate to use |
| Add learned engine simulator? | Research track only | Simulator fidelity and transfer validated against real engine |
| Build desktop product now? | No; after model value is proven | Reliable model loop and concrete user value validated |
| What means “number one”? | Tiered private/public benchmark with harness disclosure | Independent evaluation and robust held-out wins |

---

## Final operating rule

**Build the measure, then the harness, then the data, then the specialist model, then the advanced character/asset pipeline, and finally the Windows product.** At every stage, continue only when evidence shows the previous stage is reliable enough to support the next.

# PART XVI — AUTHORITATIVE CURRENT STATE AND PROJECT CONTROL

## 16.1 Current milestone ledger

Use this table as the single high-level project tracker. It must be updated only when evidence changes.

| Milestone | Purpose | Current status | What is supported by the supplied project reports | What must not be claimed |
|---|---|---|---|---|
| Step 1 — GameForge-Bench foundation | Create schemas, runner, adapters, task inventory and real-engine controller test | REPORTED_COMPLETE | Unreal controller pilot and initial harness are reported passing | Do not say all 30 task specs are fully implemented benchmark tasks |
| Step 2 — Health/damage | Validate temporal gameplay logic, health invariants and exactly-once death | REPORTED_COMPLETE | Unreal 5.7.4 health component and 16 probes reported passing; two defective candidates rejected | Do not claim Unity execution passed |
| Step 3 — Pickup/composition/isolation audit | Connect resources/pickups into a composed player and introduce isolation-provider abstraction | REPORTED_COMPLETE | 12 pickup probes, 9 composition probes, five defective candidates and 80 passing tests reported | Do not call process-level isolation a secure OS sandbox |
| Step 4 — HUD/projectile/cross-engine scope | Add UI, collision-driven combat, engine coverage metadata and universal intelligence scope documents | REPORTED_COMPLETE (Audited: E4_REPORTED_REAL_ENGINE) | Audited independently in STEP4_AUDIT_REPORT.md; 114 unique automated tests (49 unit, 45 protected oracles, 20 real integration tests); 12 HUD probes, 12 projectile probes; prior pilots verified without regression | Do not claim independent E5 reproduction, full visual screenshot verification, Unity runtime, or OS sandbox verification |
| Step 5 — Existing-model baseline | Compare at least two existing models with equal tasks, tools, contexts and budgets | STEP5 FAIL — INTEGRITY DEFECTS REMAIN (HISTORICAL RESULTS INVALIDATED PENDING RETEST) | Audited in STEP5_RECONCILIATION_AUDIT.md and STEP5_SCORECARD_AUDIT.md; historical runs preserved in reports/baseline_runs/; all 14 native C++ attempts produced 0 applied patches; historical 90.9% Pass@1 reflected pristine fixture solutions rather than candidate code; harness extraction and allowlist bugs repaired | Do not claim Step 5 accepted, verified, or passed |
| Step 6 — Rights-aware data factory | Build a legal, versioned trajectory dataset | PRE-GATE IMPLEMENTATION COMPLETE — TRAINING GATE CLOSED PENDING EXTERNAL LEGAL REVIEW | Trajectory schema v1.0 machine-validated; source register rights enforcement audited; deterministic ingestion, deduplication, group splitting, protected contamination scanner, and CLI implemented (tests passing 11/11); formal external legal review packet authored in STEP6_EXTERNAL_RIGHTS_REVIEW_PACKET.md | Zero real gameplay examples cleared for training; do not begin model training until external legal clearance is executed |
| Step 7 — Specialist training prototype | SFT/adapter experiment against baselines | PLANNED — DEPENDS ON STEPS 5–6 | Strategy described | Do not begin expensive training without baseline and data readiness |
| Step 8 — Tool-use and repair learning | Improve long-horizon implementation and self-repair | PLANNED — DEPENDS ON STEP 7 AND VERIFIED REWARDS | Requires trustworthy tool trajectories and verifiers | Do not treat an agent loop as trained competence by itself |
| Step 9 — Game IR experiment | Test intermediate representation against direct native generation | RESEARCH_GATE — DEPENDS ON STABLE TASKS/BASELINES | v0.1 draft and hypothesis exist | Do not assume IR is beneficial until matched A/B tests prove it |
| Step 10 — Multimodal quality | Reason over screenshots, scenes, animation, audio and profiler output | PLANNED_RESEARCH | Feature domains are defined | Do not claim asset or animation generation from conceptual plans |
| Step 11 — Character Bundle | Produce a connected playable character from mesh through animation and controller | PLANNED_RESEARCH | Bundle proposal exists | Do not call a standalone mesh a complete game-ready character |
| Step 12 — Multi-engine native execution | Add and verify more real engine backends | PLANNED — ENGINE/toolchain gated | Unity C# counterparts are authored; real Unity execution was reported unavailable | Do not claim Unity/Godot runtime parity before running them |
| Step 13 — Windows app | Ship the user-facing desktop product | DEFERRED — DEPENDS ON PROVEN MODEL/AGENT LOOP | Architecture direction exists | Do not let app work displace proof of model capability |
| Step 14 — Scale/architecture decision | Decide model scale, experts, RL and multimodal route | RESEARCH_GATE | Candidate approaches are documented | Do not assume frontier-from-scratch training is affordable or necessary |
| Step 15 — Production readiness | Security, reliability, licensing, release, observability | FUTURE — DEPENDS ON SECURITY/LEGAL REVIEW | Risk areas are identified | Do not run arbitrary hostile native code in the current host boundary |

## 16.2 Existing test counts are evidence with a provenance label

The supplied Step 1–3 reports state that 80 tests passed, including 14 real Unreal integration tests and 66 unit/hidden-oracle tests. The supplied Step 4 completion summary separately reports 94/94 unit/protected-oracle tests and 6/6 real-engine integration tests. These are suite-specific reported counts and must not be added into one unique-test total without inspecting test IDs and overlap. When Antigravity continues work, it should:

1. Re-run the previous reference tasks before modifying shared infrastructure.
2. Preserve the JSON reports and logs.
3. Check the actual engine version and fixture hashes.
4. Rerun earlier pilots after meaningful shared-runner changes.
5. Report any discrepancy between current results and historical handoff reports.
6. Avoid retroactively changing frozen acceptance criteria to make a regression disappear.

The source repository and artifacts are authoritative for current code state. Historical reports explain expected behavior but do not replace inspection.

## 16.3 What is the current “system”?

At this point, the real system is a **benchmark and engine-execution foundation**, not an AI game developer yet. It can be used to test engineered reference components and controlled defects. The model-facing path still needs fair baseline evaluation, model/tool integration, and training.

The distinction matters:

- A working benchmark can evaluate an AI, but it does not itself create intelligence.
- A reference component shows that the engine and grader can express a task; it does not prove a model can generate that component.
- A test that rejects a defective candidate makes the benchmark stronger; it does not prove that all candidate failures will be detected.
- Unity source files authored without the Unity Editor are not real-Unity runtime validation.
- A feature scope document is an aspiration and coverage plan, not evidence of model knowledge.

## 16.4 Source-of-truth and evidence hierarchy

GameForge separates **normative authority** (what the project is supposed to do) from **empirical evidence** (what the current implementation actually does). Neither axis can silently replace the other.

### Normative authority — instructions and design

1. **`GAMEFORGE_FINAL_MASTER_STRATEGY.md`** — the single authoritative source for mission, requirements, architecture, priorities, staged roadmap, and governance.
2. **Approved Architecture Decision Records (ADRs)** — may amend a specific master-strategy clause only when they identify the clause, rationale, evidence, impacts, and effective version. The master strategy must then be updated.
3. **Versioned task specifications and frozen acceptance criteria** — executable task-level interpretations of the master requirements. If they conflict with the master strategy, flag the conflict and stop the affected work rather than silently choosing one.
4. **Machine-readable roadmap and engine coverage matrix** — derived tracking registers; neither may override the master strategy.

### Empirical evidence — implementation truth

1. Current source code and engine-native assets show what is actually implemented.
2. Machine-readable reports, engine logs, build/test outputs, snapshots, and hashes show what was executed and observed.
3. Reproducible clean-snapshot reruns provide stronger evidence than unrepeatable or hand-authored claims.
4. Handoff reports summarize evidence but do not substitute for artifacts when a claim is disputed.
5. Unverified AI-generated text, assumptions, and retrospective summaries are not evidence.

### Conflict protocol

When a requirement disagrees with code or a test result, do not change the requirement just to make the implementation pass. Record a discrepancy, identify which side is wrong, repair the implementation or propose an ADR-backed requirement change, rerun the affected tests, and update the strategy only after the decision is approved. Every milestone status must retain its evidence level.
---

# PART XVII — THE FULL INTELLIGENCE CONTRACT

## 17.1 “All-knowing” translated into an engineering target

The intended model should be broadly capable of answering game-development questions for any engine, but literal omniscience is not an achievable engineering specification. Engines, SDKs, third-party plugins, proprietary APIs and versions are too numerous and change too rapidly. Translate the ambition into these testable commitments:

1. It can explain general game-development principles across genres and engines.
2. It can identify the target engine, version, language and project architecture from context.
3. It can answer about documented engines outside the primary execution backend.
4. It can retrieve current, version-matched information instead of pretending its training data is current forever.
5. It can distinguish a verified fact, likely pattern, project inference, and uncertain/unavailable feature.
6. It can generate native code using the idioms of the requested engine.
7. It can translate intent between engines without insisting their APIs and semantics are identical.
8. It can work with custom engines if the project, SDK headers and documentation are available.
9. It can state when a capability cannot be validated in the current environment.
10. It can improve over time as the engine registry and evaluation dataset expand.

This is the defensible interpretation of “all engines”: broad coverage with calibrated confidence, not a claim to have memorized every API.

## 17.2 Three types of knowledge

**Conceptual knowledge** answers “What is a finite-state machine?” or “Why should damage authority live on the server in a multiplayer game?” This is mostly engine-independent.

**Implementation knowledge** answers “How is this state machine expressed in this engine/version?” It requires native idioms, API semantics and version context.

**Execution knowledge** answers “Does this implementation actually work in this project?” It requires project inspection and some form of execution or verification. A model should not infer execution success from code appearance.

The product should visibly distinguish these three types, especially when users ask for implementation in an engine that is not installed.

## 17.3 Universal request interpretation contract

For each request the system should resolve, where possible:

- User objective and intended player-facing behavior.
- Engine and exact version.
- Target platform and hardware constraints.
- Project architecture and existing implementation style.
- Single-player versus multiplayer requirements.
- Performance/memory budgets.
- Asset style, quality and licensing constraints.
- Whether the user wants explanation, draft, applied edit or autonomous work.
- Allowed tools, paths and approval level.
- How success can be tested.

If a key element is missing, the agent should infer a safe default only when the result is reversible and the ambiguity is noncritical. Otherwise, it should ask one focused question or record the assumption explicitly.

## 17.4 Output quality contract

Substantial implementation responses should include:

- A concise plan.
- Native implementation or exact edit.
- Dependency and version assumptions.
- Tests or acceptance criteria.
- Commands actually executed.
- Results actually observed.
- Known limitations.
- Rollback/diff summary.
- Provenance and licensing notes where assets or training sources matter.

No invented API names, fake test logs, unearned “pass” labels or unqualified “production-ready” claims.

## 17.5 The model should retain general capabilities

Do not remove general coding/logic/math or broad language understanding as “unnecessary topics.” Game tasks use those capabilities continually: kinematics, geometry, transforms, numerical stability, algorithms, resource lifecycles, distributed systems, optimization, UI design, debugging and project management all benefit from general reasoning.

Specialization means a greater probability of correct game-development answers and actions, better native-engine understanding, fewer hallucinated APIs, and higher task success—not intentionally forgetting knowledge that supports those outcomes.

---

# PART XVIII — ENGINE COVERAGE REGISTRY: OPERATING MODEL

## 18.1 Why a registry is required and how Registry v2.1 works

A prose list of engines gets stale. The durable artifact is a structured registry with one row per **engine ID × feature domain**, refined over time by version, feature subdomain, support maturity, and evidence. The registry is a planning and evidence-tracking system; a row never proves that a capability works merely because it exists.

The source package contains 4,524 records: 39 canonical `engine_id` values × 116 feature domains, with 20 feature categories. The original CSV contains 12 columns, while this blueprint's earlier specification listed 19 different/overlapping fields. That schema drift is a real defect, not a cosmetic detail.

**Registry v2.1 uses a 26-column compatibility schema:** preserve every existing field and add every field required by the original 19-field specification that was missing. Five fields overlapped between the actual legacy CSV and the specified schema, so adding all missing fields to the 12 legacy fields produces 26 columns rather than 19. This deliberately avoids discarding provenance or status information while the registry migrates.

### Legacy-compatible fields retained (12)

- `engine_id`
- `engine_family`
- `feature_category`
- `feature_domain`
- `intended_capability`
- `priority`
- `current_status`
- `verification_level`
- `evidence_note`
- `required_next_evidence`
- `owner`
- `last_verified_at`

### Governance and evidence fields added (14)

- `version_range`
- `feature_subdomain`
- `support_level`
- `knowledge_evidence`
- `code_generation_evidence`
- `project_integration_evidence`
- `runtime_verification_evidence`
- `official_reference`
- `source_access_date`
- `license_review_status`
- `required_plugin_or_sdk`
- `known_semantic_differences`
- `benchmark_task_ids`
- `open_gaps`

The canonical CSV keeps the original 12 columns unchanged in name and retains them for existing tooling. Empty values are allowed when no evidence exists; never invent official references, dates, benchmark IDs, licenses, or test outcomes to make the table look complete.

### Field semantics and constraints

- `priority` is strictly `P0`, `P1`, `P2`, or `P3`; it must never contain milestone or status tags.
- `current_status` records lifecycle state using Section 30.4's canonical vocabulary.
- `verification_level` records evidence strength using the E0–E5 ladder in Section 30.4.
- `support_level` is a capability maturity label, not an alternative verification result; use a controlled vocabulary such as `CATALOGUED_ONLY`, `SPECIFIED_ONLY`, `AUTHORED_UNVERIFIED`, `UNIT_TESTED_ONLY`, `NARROW_REAL_ENGINE_PILOT_REPORTED`, `INDEPENDENTLY_REPRODUCED_END_TO_END`, or `RETIRED`.
- `knowledge_evidence`, `code_generation_evidence`, `project_integration_evidence`, and `runtime_verification_evidence` are separate: conceptual question answering does not prove code generation, project integration, or runtime behavior.
- `official_reference` must point to a verified engine/version-appropriate source. If no exact source has been checked, leave it blank and record the gap.
- `license_review_status` must distinguish `NOT_REVIEWED`, `REVIEW_REQUIRED`, `CLEARED_FOR_STATED_USE`, `RESTRICTED`, and `PROHIBITED_FOR_STATED_USE`; do not infer clearance from a source being publicly accessible.
- `benchmark_task_ids` refers to tasks related to the feature, not proof that every engine has a native task variant.
- `last_verified_at` is only filled for the specific evidence event that actually occurred; historical handoff dates and independently reproduced test dates must not be conflated.

### Migration rule

The original 12-column matrix is preserved in the archive as `ENGINE_FEATURE_COVERAGE_MATRIX_V1.csv`. Registry v2.1 is the active working file. Any converted values must be conservative, auditable, and noted in `evidence_note`; rows with no evidence remain catalogued/planned. The matrix migration normalizes the legacy status words and removes invalid values from `priority`. This does not promote any engine or feature beyond the evidence supplied.
## 18.2 Coverage levels must be granular

For an engine, do not assign one blanket level. For example, the system might have:

- Unreal health/damage: real-engine validated.
- Unreal UMG: authored, asset checks passed, visual review not verified.
- Unreal motion matching: knowledge support only.
- Unity health/damage: authored static counterpart, real engine unverified.
- Godot health/damage concept: engine-neutral spec exists, no native implementation.

That is a much more truthful and useful description than “supports Unreal, Unity and Godot.”

## 18.3 Engine/version provenance

Every API-heavy answer and project action should use the best available engine/version signal. Sources of signal, in order:

1. Project metadata.
2. Engine executable detected by the adapter.
3. Build logs and generated project files.
4. Package/plugin manifests.
5. User-provided version.
6. Inference from code structure, labeled as inferred.

If the project metadata conflicts with the detected engine, stop before risky migration or explain the conflict. Do not silently retarget the project.

## 18.4 Plugins and external packages are first-class records

A game engine is often a platform for plugins. The registry must track:

- Plugin/package name and exact version.
- Whether it is enabled in the project.
- Whether the plugin is required by the task.
- Whether its APIs are public and documented.
- License and redistribution conditions.
- Whether the adapter can install/configure it.
- Whether the plugin is available in the test environment.
- Whether the task can run without it.

Do not assume a plugin can be downloaded or installed during an evaluation. Prefer pre-provisioned, pinned environments.

## 18.5 Cross-engine semantic mapping is not one-to-one

Map concepts using semantic records, not name similarity. Examples:

- Unreal Actor/Component, Unity GameObject/Component, and Godot Node/Scene have overlapping but different lifecycle and ownership semantics.
- Unreal CharacterMovementComponent and Unity CharacterController/Rigidbody or Godot CharacterBody are not interchangeable implementations.
- Delegates, C# events, Godot signals, Blueprint dispatchers and Luau events differ in lifecycle and execution semantics.
- Engine coordinate systems, units, transform conventions and physics stepping differ.
- Prefabs, Blueprints, packed scenes, Roblox Instances and ECS archetypes represent composition differently.
- Visual scripting graphs have different serialization, execution order and tool automation needs.

The model should explain these distinctions and generate native solutions rather than forcing superficial equivalence.

# PART XIX — ENGINE-SPECIFIC CAPABILITY DOSSIERS

The following dossiers expand the coverage matrix into a practical checklist. Each bullet is a future model competency or integration concern, not a claim that GameForge currently implements it. Exact API names and package availability must be verified against the chosen engine version before code is written or training data is labeled.

## 19.1 Unreal Engine — competency dossier

### Project/editor operations
- Detect `.uproject`, engine association, target platform, enabled plugins and source/binary installation constraints.
- Inspect project modules, `Target.cs`, `Build.cs`, config files, maps, assets and generated files.
- Create project/source files using valid module conventions and avoid hand-writing binary asset formats.
- Launch Editor or commandlet in supported mode; preserve log files and return codes.
- Distinguish editor-only APIs from runtime modules and packaged-game restrictions.
- Create and inspect native assets through Editor APIs, commandlets or validated editor automation.
- Track engine upgrades and asset serialization/version migration.
- Detect missing plugins and conflicting plugin/engine versions.

### C++/Blueprint construction
- Design UObject/Actor/Component boundaries and ownership.
- Use reflection and exposure specifiers safely.
- Generate header/implementation pairs with correct include conventions.
- Respect UObject garbage collection and pointer ownership semantics.
- Create Blueprint-friendly APIs without forcing all logic into graphs.
- Create/modify Blueprint graphs only through supported tooling and validate node/pin wiring.
- Use data assets/tables for balance and configuration when appropriate.
- Keep gameplay contracts independent of benchmark instrumentation.

### Movement, collision and gameplay
- Set up Enhanced Input, mapping contexts and action binding.
- Configure character movement, capsule, speed, acceleration, jump, rotation and movement modes.
- Build camera booms, camera offsets, lag and collision rules.
- Use collision channels, object types, overlap/hit responses and traces correctly.
- Construct damage, health, stamina, ability, cooldown, inventory, pickup, interaction and projectile systems.
- Establish event ordering, idempotency, timer semantics and reentrancy policies.
- Build AI controllers, perception, behavior trees/StateTree/EQS where suitable.
- Support GAS architecture as a specialist task family instead of requiring it for every project.

### Animation, world and visuals
- Build Animation Blueprints, state machines, blend spaces, montages and notifies.
- Retarget skeletons and test IK/Control Rig/pose behavior.
- Configure PCG, Landscape, World Partition, Data Layers and instancing as version/platform allows.
- Create material instances/functions and reason about shader permutations.
- Configure lighting/post-process/rendering settings based on target platform.
- Set up Niagara systems and bind them to gameplay events.
- Configure physics assets, ragdoll, destructible or vehicle behavior when required.
- Create UMG widgets and establish event-driven data flows.

### Networking, performance and QA
- Configure replication, ownership, RPCs and authority.
- Keep client-facing feedback responsive without trusting clients for authoritative gameplay.
- Build server/client test topologies where available.
- Run Automation tests and headless logic probes.
- Use rendering-capable runs for screenshot and visual checks.
- Capture Insights/stat/profiler traces and measure frame-time budgets.
- Package/cook and validate missing assets, shader errors and target-specific limitations.

## 19.2 Unity — competency dossier

### Project and scripting
- Detect `ProjectVersion.txt`, packages, assembly definitions, scripting defines, build settings and render pipeline.
- Respect `MonoBehaviour` lifecycle, serialization, execution order and play/edit mode boundaries.
- Choose between GameObject/Component and ECS/DOTS only after considering the existing architecture.
- Use ScriptableObjects for suitable data definitions and preserve serialization compatibility.
- Work with prefab variants, nested prefabs, scene references and asset GUIDs.
- Use package manifests and pinned package versions; don't assume optional packages exist.
- Generate editor scripts and custom inspectors where they save repeatable work.

### Gameplay/input/physics
- Use the project's input model—legacy input or Input System—without mixing them accidentally.
- Select CharacterController, Rigidbody or a custom controller for a reason.
- Respect FixedUpdate/Update semantics and physics time stepping.
- Use collision layers, triggers, collision matrix and physics queries correctly.
- Build player controls, camera behavior, interaction, health, combat, inventory, AI and save/load.
- Manage Coroutines, async loading, cancellation and object lifetime.
- Design event subscriptions so `OnEnable`/`OnDisable` and rebinding do not duplicate listeners.

### Assets, animation and rendering
- Configure model import, rig type, avatar, materials, textures, mesh compression, normals and tangents.
- Use Animator Controllers, Blend Trees, animation events, root motion and retargeting workflows appropriate to packages/version.
- Understand UI Toolkit versus uGUI and existing-project conventions.
- Configure Built-in/URP/HDRP differences and detect pipeline incompatibility.
- Use Shader Graph/custom shaders, post-processing, lighting, probes and effects as the project supports.
- Use Addressables only where present and properly configured.
- Validate prefabs, scenes, animation references, missing scripts and asset import settings.

### Testing/build/performance
- Distinguish Edit Mode from Play Mode tests.
- Drive batchmode safely and capture editor/player logs.
- Run build validation on the configured player platform.
- Inspect Profiler, Memory Profiler, Frame Debugger and build output when available.
- Track GC allocations, draw calls, CPU/GPU time and memory.
- Handle license activation and CI rights according to current applicable terms.
- Mark authored-but-not-executed code distinctly until an actual Editor run occurs.

## 19.3 Godot — competency dossier

- Parse `project.godot`, autoloads, input actions, main scene and export configuration.
- Understand Nodes, Scenes, resources, ownership, scene inheritance and packed-scene instantiation.
- Choose GDScript or C# based on project and runtime configuration.
- Use signals, groups, callable references, node paths and scene lifecycle safely.
- Build CharacterBody2D/3D movement, physics bodies, collision layers/masks, raycasts and navigation.
- Use AnimationPlayer, AnimationTree and state transitions.
- Use Control-node UI layout, anchors, containers, input focus and responsive design.
- Build 2D sprite/tilemap and 3D mesh/material pipelines.
- Work with shaders, particles, audio buses and spatial audio.
- Handle multiplayer authority/RPC semantics and peer lifecycle.
- Validate resources/import UIDs, exported projects, missing resources and version differences.
- Use headless mode and a real test harness where supported; never assume a mock of the SceneTree proves runtime behavior.

## 19.4 GameMaker — competency dossier

- Understand GML and the version-specific event model.
- Create objects, instances, rooms, layers, sprites and animation sequences.
- Handle Create/Step/Draw/Destroy and collision events consistently.
- Use alarms/timers and avoid update-order assumptions.
- Build 2D movement, collision resolution, camera, tile maps, input and controllers.
- Model inventories, health, state machines, dialogs and room transitions.
- Handle data structures and cleanup to avoid leaks.
- Use surfaces, shaders and blend modes where necessary.
- Build GUI layers and coordinate transformations.
- Validate extensions, target platform and export configuration.
- Use debugger/profiler and frame-timing probes.

## 19.5 Construct — competency dossier

- Reason about event sheets, trigger/condition/action ordering, sub-events and event groups.
- Understand object types, families, behaviors, instances, layouts and layers.
- Model variables, functions, state transitions and event-driven logic.
- Control sprite animations, collision, platform movement, pathfinding and camera behavior.
- Design responsive layouts, UI navigation, touch input and control mapping.
- Build save/load, browser/local persistence and networking where supported.
- Understand third-party behaviors/plugins and their version constraints.
- Validate event sheets structurally and through repeatable preview/runtime tests.
- Distinguish editor preview success from target build correctness.

## 19.6 Defold — competency dossier

- Understand Lua modules, game objects, components, collections and factories.
- Bind input actions and control update/fixed-update behavior.
- Use message passing, URLs, hashes and component addresses correctly.
- Build collision objects, triggers, physics interactions and 2D movement.
- Create GUI scenes/scripts, sprite animations, tilemaps and camera behavior.
- Manage collection proxies and loaded/unloaded collection lifecycle.
- Load resources safely and account for bundle/memory limits.
- Inspect project configuration, native extensions and platform settings.
- Validate build profiles and exported bundles.

## 19.7 Cocos Creator / Cocos2d-x — competency dossier

- Keep Creator's editor/component/TypeScript flow separate from Cocos2d-x's native framework flow.
- Understand node hierarchies, scenes, prefabs, asset managers and serialization.
- Build animation, sprites, tilemaps, 2D/3D physics and UI as supported by product/version.
- Handle event dispatch, touch input and lifecycle correctly.
- Work with materials/shaders, lighting and post-processing according to renderer and platform.
- Manage asset bundles and asynchronous resource loading.
- Build native platform extensions and bindings when permitted.
- Check Android/iOS/web differences and platform-specific limitations.

## 19.8 Bevy — competency dossier

- Understand ECS entities, components, resources, systems, schedules and system ordering.
- Respect Rust ownership, borrowing, trait bounds, lifetimes and compile-time diagnostics.
- Handle events/messages, change detection, query filters and resource lifecycles.
- Use asset server, handles, scenes, reflection and serialization as supported by the selected version.
- Build input, camera, rendering, UI, audio, animation and state systems using the configured plugin ecosystem.
- Record exact plugin versions and avoid assuming an unofficial plugin is part of Bevy core.
- Test fixed-step simulation, deterministic state transitions and resource cleanup.
- Manage Cargo features, compile times and target platform compatibility.

## 19.9 Stride — competency dossier

- Work with C# entity/component and scene models.
- Understand asset database and editor-generated artifacts.
- Compose prefabs, materials, animation graphs, lights, cameras and collision.
- Build physics, input, UI and game loop code.
- Handle entity references and serialization across scene changes.
- Verify native project/build tools and version compatibility before generating code.

## 19.10 O3DE — competency dossier

- Understand Gems, modular build dependencies, entity/component patterns and reflection.
- Inspect Asset Processor outputs and asset dependencies.
- Use C++ and Script Canvas as appropriate to project architecture.
- Create/edit supported assets through editor tooling, not by hand-writing binary resources.
- Understand Atom renderer, materials, animation and physics integrations where installed.
- Handle CMake/build configuration, SDK/toolchain complexity and module registration.
- Evaluate multiplayer/service modules only when present in the project.
- Record that O3DE setup and build costs may make it a later integration priority.

## 19.11 CRYENGINE — competency dossier

- Understand native C++ modules and entity/component conventions.
- Work with visual scripting/Schematyc features where supported by the selected version.
- Build character and AI behavior using engine-native facilities.
- Understand physics, collision, animation, rendering and material/particle systems.
- Work with the level editor and asset conversion pipeline.
- Handle networking features and authoritative behavior where used.
- Record source/build distribution constraints and exact toolchain/version.

## 19.12 Roblox Studio — competency dossier

- Understand Luau, services, Instances, model hierarchies, script context and lifecycle.
- Distinguish client, server and shared execution contexts.
- Use RemoteEvents/RemoteFunctions with server-side validation and trust boundaries.
- Build character movement, animation, collisions, tools, pickups and UI using Roblox-native models.
- Handle DataStore limits, persistence, retries and schema migration.
- Work with terrain, meshes, asset permissions and platform moderation constraints.
- Use Studio test modes and multi-client tests.
- Prevent insecure client-authoritative currency, damage, purchases and progression.
- Treat publishing, marketplace use and user-generated content as platform-policy-sensitive operations.

## 19.13 UEFN / Verse — competency dossier

- Separate UEFN project APIs and restrictions from unrestricted general Unreal projects.
- Understand Verse syntax, types, concurrency/state semantics and supported runtime behavior.
- Work with devices, level/asset setup and Fortnite-specific gameplay hooks.
- Respect UEFN content/tool limitations, publishing requirements and platform policy.
- Validate through the actual supported toolchain and available playtest flow.
- Do not assume arbitrary Unreal plugins/C++ modules can be used in UEFN.

## 19.14 RPG Maker — competency dossier

- Maintain distinct profiles for different RPG Maker generations and scripting languages.
- Understand database-driven actors, classes, equipment, items, skills, enemies and encounter data.
- Understand event pages, switches, variables, common events, map triggers and battle flow.
- Build dialogue, cutscenes, quest state, progression, saving and UI through native mechanisms.
- Audit plugins for compatibility and conflicting overrides.
- Validate migration and save compatibility; do not apply plugin code written for another version as if equivalent.

## 19.15 Ren'Py — competency dossier

- Understand script syntax, labels, menus, conditions, variables and branching story paths.
- Use screen language, UI actions, transitions and input handling.
- Integrate Python logic carefully with rollback/save semantics.
- Manage persistent state, route flags and endings.
- Support translation, accessibility, captions, images, music and voice assets.
- Test representative story paths for unreachable branches, state conflicts and broken references.
- Build and package for supported targets, with version-specific constraints.

## 19.16 MonoGame / FNA — competency dossier

- Understand the framework lifecycle, update/draw loop, graphics device and content pipeline.
- Implement input, audio, sprites and rendering without assuming an editor or prefab system.
- Design or integrate the project's own entity/component framework.
- Work with SpriteBatch, custom shaders and 3D rendering where appropriate.
- Manage disposal of graphics/audio resources and device reset behavior.
- Test simulation logic separately from rendering while clearly labeling those tests.
- Validate platform-specific packaging and native dependencies.

## 19.17 Phaser — competency dossier

- Understand JavaScript/TypeScript project layout, scenes, loaders and lifecycle.
- Work with Arcade/Matter physics integrations and their distinct semantics.
- Build sprites, animations, tilemaps, cameras, input and UI.
- Understand async asset loading, browser audio constraints and canvas/WebGL differences.
- Implement browser persistence, network interactions and event handling.
- Validate npm dependency locks, bundler configuration, security policy and target browsers.
- Use browser automation for runtime and screenshot tests.

## 19.18 PixiJS — competency dossier

- Treat PixiJS as a rendering foundation; inspect the project's separate game loop, input, physics and state libraries.
- Understand containers, transforms, sprites, textures, renderers, filters and asset loading.
- Manage texture/resource lifetimes and GPU memory.
- Handle animation and UI through the chosen project's architecture.
- Build test automation using browser tooling and runtime instrumentation.
- Avoid inventing built-in gameplay systems that the project has not installed.

## 19.19 Three.js — competency dossier

- Understand scene, camera, renderer, mesh, material, light and transform graph.
- Load glTF/GLB and manage texture/material dependencies.
- Use animation mixers, raycasting and custom input/gameplay loops.
- Identify when a physics engine or gameplay framework is external.
- Handle WebGL/WebGPU support differences as configured.
- Optimize draw calls, instancing, geometry and texture memory.
- Test browser runtime and target-device constraints.

## 19.20 Babylon.js — competency dossier

- Understand scenes, engines, meshes, materials, cameras and lights.
- Work with glTF assets, animation groups, skeletal systems and import settings.
- Use picking/raycasting and configured physics plugins.
- Build GUI and input workflows.
- Handle scene serialization, asset management, rendering and browser deployment.
- Distinguish Babylon-specific features from capabilities supplied by external plugins.

## 19.21 PlayCanvas — competency dossier

- Understand editor/entity/component hierarchy and script lifecycle.
- Work with assets, templates, animation, materials, lighting and physics.
- Handle editor-to-runtime asset references and publishing workflows.
- Manage browser runtime, input, UI, networking and performance.
- Keep cloud/editor account permissions and project-sharing rules explicit.

## 19.22 LÖVE / Love2D — competency dossier

- Understand `love.load`, update, draw, input and callback conventions.
- Build scenes/state machines, sprites, animation, collision and custom rendering.
- Integrate external physics or ECS frameworks only when configured.
- Handle asset loading, audio, save/load, localization and packaging.
- Build tests around deterministic game logic without pretending an editor asset system exists.

## 19.23 Panda3D — competency dossier

- Understand Python/C++ APIs, ShowBase lifecycle, scene graph and NodePath transforms.
- Work with models, animation, collision traversers, input and task scheduling.
- Handle shaders, lighting, audio and physics integrations.
- Package assets and Python/native dependencies for targets.
- Use debug tools and deterministic simulation tests where possible.

## 19.24 libGDX — competency dossier

- Understand Java/Kotlin lifecycle, screens, render loops and asset managers.
- Work with scene/UI systems such as configured Scene2D interfaces.
- Build input, physics, animation, audio and game-state architectures.
- Manage threading, asset loading and native libraries.
- Test and package desktop/mobile/web targets as supported by the selected stack.

## 19.25 Custom/in-house engines — competency dossier

- Detect language, compiler, build system, engine entry point, scene serialization and asset format.
- Index project-local headers, interfaces, source, examples and documentation.
- Build a local symbol/API graph instead of hallucinating generic APIs.
- Infer lifecycle and component patterns from code but label inference.
- Ask for missing SDK/license/build requirements when essential.
- Produce an adapter profile before granting write/execute access.
- Start at knowledge/static levels; promote to runtime verification only after a repeatable build and test command exists.


## 19.26 UNIGINE — competency dossier

- Inspect project configuration, engine build and available C++/C# APIs.
- Understand world/node/object hierarchy, transforms and native component-like systems.
- Work with high-fidelity rendering, materials, terrain, large environments and simulation features where licensed/available.
- Configure physics, collision, animation, input, UI and audio through the actual supported APIs.
- Validate editor/runtime behavior, asset references and performance on the declared platform.
- Record engine version, SDK availability and license dependency before claiming execution support.

## 19.27 Torque3D — competency dossier

- Understand TorqueScript/C++ conventions and engine object hierarchy.
- Build scenes, entities, input, collision, physics and gameplay logic with the version's native patterns.
- Work with materials, terrain, networking and UI systems as available in the selected branch.
- Inspect build system, third-party dependencies and legacy API patterns.
- Validate through a reproducible build and runtime test rather than assuming old examples still compile.

## 19.28 GDevelop — competency dossier

- Understand events, conditions, actions, extensions, scene variables and object variables.
- Build object behaviors, collisions, timers, input and event ordering.
- Create scenes, layers, UI and 2D asset configuration through supported project formats/tools.
- Track extension versions and dependencies.
- Generate structured event-sheet tests and validate actual preview/export behavior where possible.
- Do not turn visual/event logic into arbitrary code if native event sheets are the correct interface.

## 19.29 Solar2D — competency dossier

- Understand Lua project layout, scene lifecycle, display objects, listeners and timers.
- Build touch input, sprite animation, 2D collision/physics and transition logic.
- Manage scene transitions and display-object lifetimes.
- Handle asset scaling, device resolution and mobile lifecycle.
- Validate plugin configuration, native build settings and app packaging.

## 19.30 Buildbox — competency dossier

- Inspect supported project/export representation before attempting programmatic edits.
- Understand the product's visual node/logic model and supported object behaviors.
- Treat editor-only visual operations separately from code export or runtime scripting.
- Validate the build/export using the actual tool and licensed feature set.
- Do not invent a stable file API where the product exposes none; use documented user-authorized editor automation or keep assistance at the planning level.

## 19.31 Armory3D — competency dossier

- Distinguish Blender's scene/material/animation authoring from Armory runtime/project settings.
- Understand the selected Haxe/runtime integration and node-based logic where present.
- Validate asset conversion, physics, scripting, input, materials and export target configuration.
- Keep Blender plugin version, engine version and runtime toolchain pinned.
- Use real export/build checks before calling runtime integration verified.

## 19.32 Wicked Engine — competency dossier

- Inspect repository version, build system, C++ interfaces and sample projects.
- Understand scene hierarchy, components, rendering, materials, animation, physics and editor state as implemented in that version.
- Build a project/API index rather than hallucinating Unreal or Unity APIs.
- Add only the runtime test adapters the actual engine exposes.
- Treat current API coverage as project/repository-specific and verify every generated symbol against source/docs.

## 19.33 Amazon Lumberyard legacy projects — competency dossier

- Treat this as a legacy maintenance/migration target rather than a default new-project engine.
- Identify the precise branch/version and compatibility requirements.
- Understand legacy entity/component and editor patterns as they appear in that project.
- Assist with migration analysis, build failures, asset conversion and documentation preservation.
- Do not reuse Lumberyard assumptions automatically for O3DE or current engines.

## 19.34 OpenFL / HaxeFlixel — competency dossier (`openfl_haxeflixel`)

- Distinguish the OpenFL cross-platform framework from the HaxeFlixel game framework layered on it; do not treat them as identical product APIs.
- Detect Haxe project/build configuration, library/dependency manifests, target platforms, compiler versions, and framework versions.
- Understand Haxe types, class/module conventions, callbacks, state/scene lifecycle, cameras, input, collision, sprites, animation, tilemaps, audio, UI, and resource disposal where used by the chosen framework.
- Validate project builds and exported targets using the actual Haxe/OpenFL/HaxeFlixel toolchain; do not infer runtime support from code syntax alone.
- Track licenses for third-party Haxe libraries and asset pipelines independently.

## 19.35 Flax Engine — competency dossier (`flax_engine`)

- Detect the Flax project format, engine version, C# scripts, native module/build configuration, scene/assets, and plugin dependencies.
- Understand actor/component composition, scene hierarchy, prefabs, script lifecycle, physics/collision, animation, materials, UI, audio, navigation, and editor tooling as supported by the pinned version.
- Use version-matched official references and real engine build/test facilities when available; never assume API compatibility with Unity or Unreal because the language or component terminology looks similar.
- Check asset references, resource handles, packaging targets, and engine/editor versus runtime boundaries.
- Record actual version and licensing/toolchain constraints before promoting any domain beyond `E0`–`E2`.

## 19.36 Source-engine and Source-SDK modding — competency dossier (`source_modding`)

- Require the exact target game, SDK branch, game build, mod type, and permitted distribution model before generating implementation instructions.
- Distinguish Source SDK variants, game-specific APIs, entity I/O, Hammer map workflows, VScript or other scripting facilities where supported, native extension/build mechanisms, and server/plugin boundaries.
- Do not assume that APIs or build workflows from one Source-based game transfer unchanged to another.
- Validate mod code, maps, assets, and deployment only against the stated SDK/game version and its allowed toolchain.
- Apply game-specific license, anti-cheat, server policy, and redistribution constraints; do not facilitate bypass of protections or unauthorized manipulation of live services.

**Canonical engine-ID reconciliation:** The coverage matrix has 39 unique engine IDs but the narrative dossiers group three related pairs (`cocos_creator`/`cocos2dx`, `rpg_maker_mz_mv`/`rpg_maker_xp_vxace`, and `monogame`/`fna`). The original 33 dossiers therefore covered 36 IDs; the three new dossiers above bring the narrative coverage to 36 dossier sections covering all 39 canonical IDs. Grouping is for readability only; registry rows and verification remain separate per engine ID.

# PART XX — COMPLETE FUTURE SYSTEM ARCHITECTURE

## 20.1 Main architectural components

### A. Game-development model layer

Responsibilities:
- Interpret user intent and project context.
- Reason about game mechanics, code, engine semantics and technical tradeoffs.
- Generate plans, typed descriptions, native code, configuration and tool actions.
- Diagnose failures and propose repairs.
- Explain what it did and how it verified results.

It should not be responsible for authenticating users, deciding which filesystem paths are accessible, or authoritatively grading its own output. Those are system responsibilities.

### B. Engine/version knowledge service

Responsibilities:
- Store engine/version records and feature coverage.
- Retrieve appropriate official/documented API references.
- Record package/plugin dependencies and compatibility constraints.
- Distinguish source-backed facts from model inferences.
- Track deprecated/version-specific APIs.
- Provide snippets/examples whose source rights and license status are recorded.

### C. Project understanding/indexer

Responsibilities:
- Detect project type, engine and version.
- Index source files, symbols, references, assets and project metadata.
- Construct dependency and ownership graphs.
- Find relevant code and asset context for a task.
- Detect stale summaries when hashes change.
- Report missing dependencies and unresolved references.
- Respect user/project confidentiality policies.

### D. Planner and task manager

Responsibilities:
- Convert a request into an explicit outcome specification.
- Identify dependencies and ordering.
- Break multi-file work into verifiable subgoals.
- Estimate risk and define budgets.
- Maintain checkpoints and task state.
- Stop safely when blocked, over budget or no longer making progress.

### E. Action/tool broker

Responsibilities:
- Expose typed, auditable tools.
- Validate arguments and permissions.
- Apply path restrictions and timeouts.
- Route to read-only, editing, engine, asset, build, testing and reporting tools.
- Preserve exact tool inputs/outputs.
- Never allow the model to replace protected grading code or trusted reports.

### F. Engine adapters

Responsibilities:
- Detect installed engine and version.
- Expose supported project inspection and edit capabilities.
- Create or modify native assets via supported APIs.
- Run build/import/test operations.
- Capture logs, runtime telemetry and screenshots.
- Report adapter capabilities and limitations.

Each adapter must declare its own supported feature set. A shared interface should not hide meaningful engine differences.

### G. Execution and isolation service

Responsibilities:
- Prepare a clean, recorded workspace.
- Freeze candidate state before hidden grading.
- Enforce time and process budgets.
- Remove or sanitize sensitive environment variables.
- Execute approved engine actions.
- Record the actual isolation level.
- Clean up after execution.

### H. Trusted evaluator

Responsibilities:
- Run hidden probes and tests.
- Validate saved assets and references.
- Check performance and regressions.
- Calibrate visual review.
- Compute statuses from actual evidence.
- Validate reports against schemas.

It must remain outside candidate control.

### I. Multimodal observation layer

Responsibilities:
- Interpret screenshots, rendered clips, editor UI, scene hierarchies, animation curves, profiler views and logs.
- Compare actual results with design intent.
- Extract structured observations.
- Preserve timestamps and source references.
- Calibrate confidence and distinguish perception from exact telemetry.

### J. Dataset and learning service

Responsibilities:
- Store permissioned trajectories and result records.
- Run data validation and deduplication.
- Protect evaluation splits.
- Track licensing/provenance and privacy.
- Prepare SFT, preference and outcome-training datasets.
- Produce dataset manifests and reproducibility hashes.

### K. User application

Responsibilities:
- Project selection and permission configuration.
- Chat, plan, execute, observe and review modes.
- Show diff, logs, tests and verification levels.
- Provide rollback and stop controls.
- Display model/provider choice, costs and local/cloud status.

The application is downstream of the core services; it should not own the benchmark or trusted grader logic.

## 20.2 Service and data flow

1. The user submits intent and chooses permission level.
2. Project detection supplies engine/version metadata.
3. The indexer finds related code/assets/docs.
4. Retrieval provides version-matched references.
5. The model formulates a task contract and proposed plan.
6. The policy broker validates actions and allowed paths.
7. A checkpoint is created.
8. The agent generates code/native assets and integrates references.
9. The engine adapter builds or imports the project.
10. The trusted evaluator runs tests and probes.
11. Logs and outputs are interpreted by the model/observer.
12. The model repairs or requests a human decision.
13. A final regression pass checks prior working behavior.
14. The user receives the diff, artifacts, evidence and limitations.
15. A rights/privacy-filtered trajectory may enter the training pipeline.

## 20.3 Core interfaces to standardize

- `ProjectDescriptor`: engine, version, paths, plugins, platform and source-control state.
- `TaskSpec`: user-facing task, acceptance criteria, budgets, paths and engine scope.
- `ActionRequest`: typed operation, arguments, permission class and expected output.
- `ActionResult`: success/failure, return code, logs, changed paths and evidence.
- `CandidateSnapshot`: immutable content inventory and hash.
- `EngineRun`: engine version, command, duration, exit code and artifact references.
- `ProbeResult`: ID, target, measured value, tolerance, verdict and trace.
- `AssetValidationResult`: asset ID, checks, errors and verification level.
- `IsolationReport`: provider, security level and experimentally verified boundary.
- `EvaluationReport`: benchmark, task, engine, model, grading layers and final status.
- `TrainingTrajectory`: prompts, actions, observations, result labels and rights status.

Use JSON schemas or another formal validation approach for these interfaces where persistence or cross-process use is required.

## 20.4 Model router versus specialist experts

Initially route by **task mode** and **evidence needs**, not by an elaborate expert network. For example:

- Quick conceptual Q&A may use a low-latency general/specialist model with retrieval.
- Multi-file implementation uses the strongest coding/reasoning model available under the budget.
- Screenshot analysis may use a vision-capable model.
- Large codebase indexing should use tools and embeddings rather than sending the whole repository into every prompt.
- Asset generation may call specialist 3D/animation tools.
- Final status comes from trusted tests, not a model router.

After baseline data exists, compare a single model, model-plus-RAG, adapters, and specialist routing. The router is only valuable if it improves quality, cost or latency on held-out tests.

## 20.5 Memory tiers

- **Conversation memory:** Current user request, approvals, preferences and active task state.
- **Project memory:** Architecture summaries, symbols, assets, build settings and dependencies.
- **Session memory:** Actions, observations, errors, repair attempts and checkpoints.
- **Engine knowledge memory:** Versioned API/documentation records and compatibility notes.
- **Long-term learning store:** Accepted/failed trajectories and expert labels, with rights/provenance.

Each memory record needs source, version/hash and freshness. Stale summaries can cause wrong edits; memory must be invalidated or recomputed after relevant changes.

---

# PART XXI — MULTIMODAL, SPATIAL, AND TEMPORAL INTELLIGENCE

## 21.1 Why text-only competence is insufficient

Game projects include artifacts that cannot be represented adequately by source code alone:

- Visual scripting graphs.
- Scene/actor hierarchies.
- Native binary or database-like assets.
- Meshes, textures and materials.
- Rig hierarchies and animation curves.
- Screenshots and playtest video.
- Audio and timing events.
- Profiler timelines and frame captures.
- Physics traces and state over time.

The system needs a structured representation around these artifacts, not just a giant text prompt containing file excerpts.

## 21.2 Vision tasks

Initial vision benchmark tasks should include:

1. Compare a target screenshot with a design brief.
2. Identify missing UI elements or incorrect layout.
3. Detect obvious camera clipping/occlusion in selected views.
4. Identify visual differences between two controlled builds.
5. Locate missing textures/materials or broken references.
6. Compare scene screenshots across revisions.
7. Read editor/error UI when it is visible and appropriate.
8. Evaluate whether the player/target/pickup is present and positioned correctly.

Exact numeric claims should be derived from telemetry or asset data whenever possible. A screenshot model should not be the sole source for exact health values, polygon counts, runtime states or performance figures.

## 21.3 Video and playtest understanding

A playtest record should align:

- Input trace.
- Frame number/timestamp.
- Player position/velocity/state.
- Collision events.
- Health/inventory/event state.
- Screenshot/video frame.
- Runtime log and probe output.

The model can summarize “player gets stuck at this ledge after the second jump,” but the system should tie that conclusion to observed frames and state. Playtesting should be repeatable using scripted routes before relying on exploratory agent play.

## 21.4 Animation understanding

Use both structural and temporal metrics:

- Skeleton topology.
- Clip duration and sample rate.
- Root translation and rotation.
- Pose continuity.
- Foot contacts and sliding.
- Ground penetration.
- Joint range and deformation artifacts.
- Transition validity.
- Motion alignment to locomotion.
- Animation event timing.
- CPU evaluation cost.

Use a combination of sampled numerical poses, scene execution and calibrated visual review. Do not infer a correct animation graph solely from its graph node labels.

## 21.5 Geometry and materials understanding

Use machine-measurable signals where possible:

- Vertex and triangle count.
- Bounding box, scale and pivot.
- Normals/tangents and degenerate triangles.
- UV occupancy/overlap as appropriate.
- Texture dimensions and memory.
- Material slot count.
- LOD ratios.
- Collision mesh complexity.
- Skin weights and skeleton references.
- Engine import warnings.

VLM review can complement these metrics for silhouette, visual consistency, style and obvious artifact detection, but should not replace topology and import validation.

## 21.6 Audio understanding

Later coverage may include:

- Event-to-audio binding correctness.
- Clip length/format/sample rate.
- Loop/cut/pop detection.
- Audio routing and attenuation.
- Dialogue/subtitle timing.
- Interactive music state changes.
- Memory and streaming constraints.

Use native playback tests and relevant signal analysis; subjective judgments need calibrated listeners or explicit user preference data.

## 21.7 Multimodal strategy experiments

Compare:

1. Strong language/code model alone.
2. Same model with retrieved structured scene/asset metadata.
3. Model plus image/video observations.
4. Model plus specialist visual/animation tools.
5. Unified multimodal model where available and license/cost permits.

Measure task success, latency, cost, visual judgment agreement and error types. Do not assume a unified model is always better than specialized tools.

---

# PART XXII — MODEL TRAINING DESIGN IN DETAIL

## 22.1 Begin with a training hypothesis, not with a GPU request

Every proposed training run must answer:

- Which concrete benchmark failure are we fixing?
- Why is it a model-capability issue rather than a retrieval, prompt, harness or environment issue?
- What examples will teach the missing behavior?
- What is the baseline on held-out tasks?
- What result would make us stop?
- What compute, memory and data rights are required?
- Which general capabilities might regress?

## 22.2 Learning methods and their proper roles

### Continued pretraining

Potentially useful for absorbing a large body of game-development domain text/code and specialized representations. Requires a significant, rights-cleared corpus and appropriate compute; not the first local experiment.

### Supervised fine-tuning

Useful for learning task formats, coding conventions, plans, tool-call patterns, structured output and repair explanations from high-quality examples. Start with a small prototype where training support and license allow.

### Parameter-efficient tuning

Adapter/LoRA-style tuning may be a lower-cost experiment for compatible model architectures. The feasibility must be tested against the chosen model and the actual AMD/Linux/Windows stack; 12 GB VRAM is a constraint, especially for long context.

### Preference optimization

Useful where experienced reviewers can rank competing architecture/code/repair decisions. It needs clear rubrics and a representative set; uncalibrated preferences can teach style rather than correctness.

### Outcome/verifiable reward optimization

Potentially valuable when engine runs provide trustworthy outcomes such as compile success, probe pass, asset validity and regression status. It depends on secure graders, adequate parallelism and reward anti-gaming. Begin small and controlled.

### Rejection sampling / best-of-N

May improve data quality by selecting candidates that pass verifiable checks. It is not a substitute for training, and selected examples must not all come from the same narrow benchmark pattern.

### Distillation

Potentially useful to transfer long, high-quality trajectories or specialist capability into a smaller local model. Need source-model rights, privacy review, and held-out measurements.

### Training from scratch

A separate, very expensive future decision. It is not the default plan. Only investigate after base-model specialization shows a defined limitation that cannot be solved by data, retrieval, adapters or architecture.

## 22.3 Curriculum design

Training examples should progress from simpler, verifiable tasks toward longer integrations:

1. Engine-neutral concept explanation.
2. API selection and version reasoning.
3. Single-function code completion and repair.
4. Component implementation with invariants.
5. Multi-component integration.
6. Native asset/configuration creation.
7. Build/import error repair.
8. Runtime probes and temporal logic.
9. Multi-file project modifications.
10. Scene/actor/prefab composition.
11. UI/event/animation graph wiring.
12. Performance regression diagnosis.
13. Cross-engine translation.
14. Asset/rig/animation QA.
15. End-to-end mini-game creation and repair.

Do not simply mix all data without measuring sequence/order effects. Run ablations where feasible.

## 22.4 Positive and negative examples

Store examples that teach:

- Correct solution and why it passed.
- Plausible wrong solution and exact observed failure.
- Root cause diagnosis.
- Minimal repair that fixes it.
- Regression caused by a repair.
- Tool call that failed and safe recovery.
- Incorrect API answer corrected using versioned documentation.
- Cross-engine translation that preserved semantics.
- Failure due to unavailable engine versus model failure.

Label rejected candidates carefully. A failed build from an unavailable toolchain is not a bad-code training example unless the model caused the dependency failure.

## 22.5 General-capability retention set

Every specialized-model release should also be evaluated on a small regression suite for:

- General code generation.
- Math/physics reasoning relevant outside games.
- Algorithm design.
- Clear explanations.
- Planning and instruction following.
- Structured output.
- Security and permission handling.

Game-specialization gains do not justify avoidable catastrophic forgetting.

## 22.6 Data split discipline

Maintain separate, permissioned datasets:

- `train`: allowed for training.
- `dev`: may guide iteration/hyperparameters.
- `public_eval`: published/rotating comparison set.
- `private_eval`: held out and protected.
- `stress_eval`: adversarial/version-drift/partial-context set.
- `human_review`: samples chosen for expert judgments.

Do not allow hidden graders, reference solutions or private eval task descriptions to leak into training records. Generate task mutations and detect near duplicates. Record which model/version generated synthetic examples, and do not treat model-generated truth as ground truth without independent verification.

## 22.7 Dataset release readiness

Before a record enters training, validate:

- License/provenance accepted.
- Privacy screening complete.
- No secrets or credentials.
- Task/report schema valid.
- Output quality and reference labels reviewed.
- Test/evaluation contamination checked.
- Model-generated text labeled appropriately.
- Engine/version metadata present.
- Artifacts are reproducibly addressable by hashes.
- Data owner/permission path recorded.

---

# PART XXIII — DETAILED GAMEFORGE-BENCH EXPANSION PLAN

## 23.1 Initial task families beyond the four reported pilots

The following should become structured task families as capacity allows. Each task needs a specific acceptance contract; the list is a backlog taxonomy, not proof these fixtures exist.

### Core gameplay
- Third-person controller.
- First-person controller.
- Top-down controller.
- 2D platformer controller.
- Camera orbit and wall collision.
- Input remapping and device fallback.
- Health/damage/invulnerability.
- Stamina drain/regeneration/restore.
- Pickup collection.
- Inventory add/remove/stacking.
- Equipment slots and stat application.
- Projectile movement/collision.
- Melee hit windows and repeated-hit prevention.
- Enemy state machine.
- Player target/lock-on logic.
- Ability cooldown/cost/state transitions.
- Interaction interface.
- Door, switch, key and quest gate.
- Checkpoint and respawn.
- Save/load and schema migration.
- Damage-over-time and status effects.
- Death and respawn event order.
- Object pool lifecycle.
- Spawn waves and encounter control.

### Player character and composition
- Player actor/prefab completeness.
- Correct component uniqueness.
- Valid references and lifecycle order.
- Controller + health + stamina + interaction integration.
- Character animation state machine.
- Animation notifies bound to combat.
- Foot IK/grounding.
- Root motion versus code-driven movement.
- Character ragdoll and recovery.
- Character asset retargeting.
- Non-human creature skeleton/animation handling.

### UI and interaction
- Health/stamina HUD.
- Inventory UI.
- Cooldown/ability UI.
- Pause/options menu.
- Input focus and controller navigation.
- Localized text expansion.
- Event subscription deduplication.
- UI binding cleanup on player change.
- Save/load menu.
- Dialogue/quest interface.
- Accessibility scaling and rebindable controls.

### World/level/editor authoring
- Compose player actor from components.
- Create a basic test map.
- Place spawn points and pickups.
- Wire level sequence or trigger volume.
- Build a navigation-ready scene.
- Create PCG/terrain rules where engine supports it.
- Configure collision profiles.
- Repair missing asset references.
- Validate level hierarchy and unused assets.
- Create data-driven actor variants.

### Animation/rigging/assets
- Import static mesh and configure LOD/collision.
- Import skeletal mesh and verify skeleton.
- Retarget known animation set.
- Build locomotion blend/state graph.
- Add jump/start/loop/land transitions.
- Verify root-motion settings.
- Sample pose correctness at timestamps.
- Detect foot sliding and ground penetration.
- Validate UV/texture/material budgets.
- Create material instance and parameter binding.
- Create a basic Niagara/VFX Graph effect and bind to event.
- Create audio event and validate trigger timing.

### AI/navigation
- Enemy patrol/idle/chase/attack/return state machine.
- Navigation path following.
- Perception/aggro range and line of sight.
- Flee/cover behavior.
- Target selection with deterministic tie-breaking.
- Spawn director with bounded intensity.
- NPC interaction and dialogue state.
- Bot playtest route following and failure reporting.

### Project-scale engineering
- Add a feature to existing codebase without breaking old behavior.
- Migrate version-deprecated API.
- Refactor duplicated component code.
- Split module while retaining behavior.
- Fix missing references and package/build failure.
- Change input action mapping safely.
- Update asset import settings across selected directory.
- Add logging and diagnostics without excessive overhead.
- Add tests to existing project conventions.
- Resolve merge/conflict or stale asset references.

### Performance/debugging
- Seeded 30–50% frame-time regression.
- Memory growth after repeated spawn/despawn.
- Duplicate event subscriptions causing performance bug.
- Excessive allocations/GC.
- Draw-call or material-count regression.
- Shader compile/permutation explosion.
- Navigation updates too often.
- Large asset load hitch.
- Network over-replication.
- Physics tunneling or unstable time step.

### Cross-engine and conceptual tasks
- Compare Actor/Component, GameObject/Component and Node/Scene semantics.
- Convert health/damage contract between engines.
- Port controller requirements with unit/axis conversion.
- Identify equivalent concepts and non-equivalent engine features.
- Repair wrong engine-version API usage.
- Explain where native implementation must diverge.
- Assess an unknown engine repository from source/documentation.

## 23.2 Task definition checklist

Every newly added task should answer:

1. Why is this task representative of game development?
2. What capability is being evaluated?
3. What context is candidate-visible?
4. What exact files/assets may be changed?
5. What are the required behaviors and invariants?
6. Which checks are deterministic?
7. Which checks are subjective and need calibration?
8. What is the native engine/version requirement?
9. What is the reference solution?
10. What controlled defect(s) demonstrate grader sensitivity?
11. How is the candidate prevented from modifying the grader?
12. What is the expected budget?
13. How are failures classified?
14. What source/asset rights apply?
15. How will test contamination be controlled?

## 23.3 Benchmark integrity checks

- Do not expose hidden-test code to evaluated models.
- Do not allow candidate execution to write trusted result files.
- Hash project and acceptance artifacts before/after runs.
- Do not let the agent disable tests or rewrite acceptance criteria.
- Detect direct tampering with test path, engine configuration and report paths.
- Mutate hidden tests when possible and review a random sample manually.
- Keep reference solutions protected and separate.
- Report flaky probes openly and quarantine unresolved ones.
- Avoid exact floating-point matching for physics.
- Do not let scoring depend solely on an LLM judge.
- Version every change to a task, fixture and acceptance threshold.


# PART XXIV — FEATURE COMPLETENESS, API KNOWLEDGE, AND VERSION MANAGEMENT

## 24.1 Do not train solely on memorized API names

Game-engine APIs are versioned. A system that memorizes a function signature without understanding lifecycle, ownership, threading, capability requirements and semantic constraints will still generate broken projects.

Training and inference should combine:

- API/API-symbol knowledge.
- Intended use and constraints.
- Minimal and representative examples.
- Deprecated/removed alternatives.
- Version range and plugin dependency.
- Failure modes and debugging patterns.
- Actual compile/import/test evidence.
- Similar concept mapping across engines.

## 24.2 Engine API record

For each important API or feature, record:

- Canonical engine, version range and feature family.
- Symbol/API name and language.
- Short semantic summary.
- Expected lifecycle/thread context.
- Arguments/return type where confirmed.
- Ownership and lifetime rules.
- Required module/package/plugin.
- Relevant platform restrictions.
- Deprecation or migration notes.
- Minimal rights-cleared example.
- Known failure patterns.
- Applicable benchmark tasks.
- Source reference and verification date.

## 24.3 Retrieval strategy

- Prefer exact version-matched documentation.
- Retrieve primary documentation before third-party blog content when available and permitted.
- Include project-local definitions to override generic assumptions.
- Rerank by engine, version, API family and task type.
- Keep retrieved source IDs in internal trace records.
- Avoid dumping entire manuals into every prompt.
- Detect contradiction between retrieved references and current code; explain it.
- Keep a freshness policy for fast-changing APIs and plugins.
- Validate generated API usage by compilation or other appropriate tests whenever possible.

## 24.4 No-fabrication API protocol

If the model cannot confirm an API:

1. Search the current registry/retrieval source when allowed.
2. Inspect the installed engine's headers, reflection, package sources or official docs if permitted.
3. Search the local project's existing usage.
4. Offer a version-conditional implementation or clearly labeled pseudocode if still uncertain.
5. Never invent a source reference, path or compile result.

## 24.5 Version migration capability

The model should support tasks such as:

- Find deprecated APIs.
- Replace them with appropriate newer equivalents.
- Update package/build references.
- Migrate serialized assets where supported.
- Preserve runtime behavior.
- Run old and new tests or provide a migration validation plan.
- Report breaking changes and manual actions.

Migration must be benchmarked separately from new feature creation because old APIs, content formats and plugin dependencies introduce special constraints.

---

# PART XXV — FUTURE WINDOWS APPLICATION: DETAILED FEATURE INVENTORY

## 25.1 Project onboarding

- Choose an existing game project or create a new one.
- Detect engine, version, modules/packages, plugins, language and platform.
- Show supported/unsupported features before running actions.
- Validate workspace permissions and source-control status.
- Show unresolved project errors before agent changes.
- Allow the user to choose local model or an authorized remote provider.
- Allow the user to declare confidentiality and telemetry rules.
- Record project identity locally with configurable persistence.

## 25.2 Task workspace

- Natural-language request input.
- Engine/version selection and inferred engine display.
- Ask / Explain / Plan / Generate / Apply / Test / Repair / Review modes.
- Requirements and assumptions panel.
- Planned files/assets and dependencies.
- Budget limits and stop conditions.
- User approval controls.
- Execution progress with actions and observations.
- Failure summary and retry/repair policy.

## 25.3 Source and native asset review

- Code diff viewer.
- File tree and symbol navigation.
- Asset/scene hierarchy browser where technically feasible.
- Reference and dependency graph.
- Blueprint/visual graph diff summary where supported.
- Prefab/scene/object property diff summary.
- Material, animation and UI asset change summary.
- Generated file provenance.
- Side-by-side before/after screenshots.
- Restore checkpoint or discard agent changes.

## 25.4 Engine controls

- Engine detection and version check.
- Start/stop Editor/engine process.
- Build/import/test action buttons.
- Configurable test profile.
- Headless vs rendered test mode.
- View logs, compile errors and runtime exceptions.
- Show unavailable plugin or license blocker.
- Record exact engine arguments and run duration.
- Do not require UI to run CI/CLI tests.

## 25.5 Test and evidence view

- Layer-by-layer pass/fail/blocked state.
- Per-probe target vs measured value.
- Timeline for temporal gameplay events.
- Screenshot and video review.
- Saved-asset structural verification.
- Performance budgets and profiler result links.
- Regression list.
- Unverified checks displayed distinctly.
- Download/export of report bundle.
- Model/provider/hardware/cost metadata when available.

## 25.6 Safety and settings

- Project-level allowed paths.
- Permission level.
- Network access setting for candidate execution.
- Local/cloud model selection.
- Secret-redaction and data sharing settings.
- Engine tool permissions.
- Timeout/resource budgets.
- Checkpoint/rollback policy.
- Third-party asset/license warnings.
- Log retention and deletion controls.
- Debug telemetry opt-in/opt-out.

## 25.7 App architecture requirements

- Desktop front end must not be responsible for hidden grading decisions.
- Engine adapters remain isolated services/modules.
- The core API must be callable by CLI and CI as well as the UI.
- Long-running engine jobs need cancellation and lifecycle handling.
- UI must distinguish “generated,” “applied,” “built,” “tested,” and “verified.”
- Reports must remain readable outside the application.
- Local projects should not be uploaded by default.
- Remote model requests must follow explicit user/organization data policy.

---

# PART XXVI — R&D IDEAS THAT COULD CREATE A REAL ADVANTAGE

These are research hypotheses or long-term product bets. None should be called proven inventions until experiments support them.

## 26.1 Gameplay Contracts

For each requested feature, create executable invariants and behavior probes before implementation.

Example: a character controller contract defines speed, jump apex, coyote time, camera collision, input latency and required state transitions. The engine's measured behavior determines acceptance.

Potential advantage: turns open-ended game requests into measurable engineering tasks and creates reliable reward signals.

Primary risk: contracts may miss subjective quality or overfit to narrow probe cases.

## 26.2 Game IR and contract compiler

The model outputs a typed engine-neutral semantic plan for common gameplay systems. A deterministic backend lowers supported nodes into native engine code/configuration and binds contracts. Native escape hatches handle features not captured by IR.

Potential advantage: unit-safe cross-engine reasoning and paired data.

Primary risk: IR could constrain expressivity and add compiler bugs. Run the controlled A/B experiment.

## 26.3 Learned editor-action simulator

Train a model to predict the likely state change resulting from an editor/tool action, based on observed before/after states.

Possible uses:

- Cheap planning rollouts.
- Predicting whether an operation will break references.
- Pre-screening action sequences.
- Suggesting a tool call that avoids expensive real-engine restarts.

Risk: learned predictions may be wrong on rare engine states. Real-engine verification remains mandatory for final claims.

## 26.4 Self-healing project graph

Maintain a semantic graph of types, component dependencies, assets, scene references, event flows and acceptance contracts. When a change occurs, identify affected dependencies and run only safe targeted tests first, followed by required regression tests.

Potential advantage: less wasted context, fewer unrelated edits and more reliable multi-file work.

Risk: graph extraction is incomplete for reflection, dynamic references, visual graphs and runtime-generated objects. Keep uncertainty metadata and fallback full validation.

## 26.5 Split architecture from “feel” tuning

The model decides the architecture and behavior. A numerical search process tunes parameters within declared bounds against probe targets.

Example: tune acceleration, braking, camera lag and jump variables to match a design contract after the movement implementation is correct.

Potential advantage: numerical optimization can explore ranges more systematically than repeated free-form code edits.

Risk: objective proxies may optimize the wrong thing; human playtest feedback still matters.

## 26.6 Adversarial bot playtester

A separate test agent plays the build and tries to find bugs or poor interactions. It should produce reproducible input traces and precise state evidence, not vague comments.

Potential workflow:

1. Build candidate.
2. Execute scripted baseline paths.
3. Let test agents explore permitted scenarios.
4. Cluster failures by root cause.
5. Reproduce failures with deterministic traces.
6. Have builder agent repair.
7. Rerun all prior traces and tests.

Potential advantage: discovers interaction-level failures beyond narrow unit tests.

Risk: exploration is incomplete and stochastic; use as a supplement, not replacement for explicit acceptance probes.

## 26.7 Character Bundle compiler

Represent mesh, skeleton, skin weights, retarget target, clips, state graph, controller, camera, inputs and component references as one typed deliverable. The system validates each stage and rejects broken intermediate assets.

Potential advantage: converts disconnected content tools into a more coherent game-ready workflow.

Risk: 3D generation and rigging quality vary by shape, skeleton, style and target engine; scope it progressively.

## 26.8 Universal asset QA gate

A pre-import asset auditor checks geometry, UVs, material count, collision, LOD, skeleton, skin weights, animation continuity, file format and license provenance before engine import.

Potential advantage: prevents broken or excessively expensive assets from entering the project.

Risk: some quality properties require engine-specific interpretation or human review.

## 26.9 Cross-engine behavioral translation

A shared gameplay contract is paired with native per-engine implementations. The benchmark measures semantic parity of observable behavior rather than textual similarity between code.

Potential advantage: teaches transferable concepts and exposes engine-specific mistakes.

Risk: certain engine behaviors cannot be made identical; tolerance and explicit backend differences must remain.

## 26.10 Project-scale reversible edits

Every action records an inverse or checkpoint, predicted dependency impact, and post-action evidence. A failure can revert the minimum affected slice rather than restoring the entire project blindly.

Potential advantage: enables safer long-horizon autonomy.

Risk: not every native asset/editor action has a simple inverse. Use snapshots/source control as the durable recovery foundation.

## 26.11 Version-drift challenge suite

Construct tasks in which docs, project files and engine versions disagree or APIs have been moved/deprecated. Score whether the model detects the mismatch, chooses the appropriate source, and avoids inventing compatibility.

Potential advantage: measures one of the highest-risk real-world assistant failure modes.

## 26.12 Minimal-repair reward

Reward a solution that fixes the target behavior while minimizing unrelated changes and preserving prior behavior. Use diff size as a secondary measure only—not as a substitute for correctness.

Potential advantage: encourages precise engineering instead of rewrite-heavy behavior.

Risk: over-penalizing large legitimate changes. Compare against expert-reviewed change necessity.

## 26.13 Failure-to-curriculum engine

Every benchmark failure is classified and mapped to future training tasks. For example, duplicate event subscriptions produce examples in lifecycle reasoning, failure diagnosis, idempotency contracts and test generation.

Potential advantage: turns evaluation into targeted learning rather than undirected data collection.

Risk: incorrect root-cause labels can train the wrong behavior; use expert review sampling and label confidence.

---

# PART XXVII — HIGH-LEVEL PRODUCT FEATURE CATALOGUE

This list translates the technical taxonomy into user-visible outcomes. “Future” means intended scope, not current implementation.

## 27.1 Ask and explain

- Explain engine concepts and API behavior.
- Compare how multiple engines model the same gameplay feature.
- Explain existing code/assets and data flow.
- Produce beginner-friendly, intermediate and expert-level explanations.
- Provide version-aware implementation suggestions.
- Cite internal project/source references when available.
- Explain why a proposed approach is risky or inefficient.
- Distinguish native functionality from plugin functionality.

## 27.2 Code and gameplay creation

- Create and refactor player/NPC components.
- Create health, stamina, damage, inventory and item systems.
- Create weapons, projectiles, melee hit detection, abilities and status effects.
- Create quests, dialogue, interaction and progression systems.
- Create save/load and checkpoint systems.
- Create behavior trees, state machines and utility AI.
- Create movement, camera, vehicle and traversal systems.
- Create multiplayer-ready boundaries and replication logic where supported.
- Create data-driven configuration and reusable templates.

## 27.3 World and level creation

- Create test scenes/levels and spawn points.
- Place and configure actors/components.
- Build terrain and layout prototypes.
- Apply collision/nav settings.
- Create PCG rules and bounded procedural layouts.
- Create environment lighting and material setups.
- Validate references and scene integrity.
- Make changes based on design briefs and screenshots.

## 27.4 Character and animation creation

- Generate character requirements from natural language.
- Generate or integrate meshes through appropriate providers.
- Validate rig/skeleton and skin weights.
- Retarget animation sets.
- Create locomotion/action animation graphs.
- Integrate controller movement and animation state.
- Configure IK and foot contact where supported.
- Measure motion continuity and performance.
- Create a complete character bundle with tests.

## 27.5 Visual assets and effects

- Create/modify materials, shaders, textures and decals.
- Build particle/VFX systems and trigger timing.
- Configure audio events, attenuation, dialogue and UI sounds.
- Create environment props and procedural geometry.
- Audit asset size, import settings, LODs, collision and platform constraints.
- Preserve asset rights and provenance records.

## 27.6 UI and accessibility

- Create HUD and resource bars.
- Create menus, inventories, maps, settings and dialogue UI.
- Support responsive layouts and input focus.
- Bind UI to game state with safe lifecycle handling.
- Add localization-ready structures.
- Provide captions, remapping, scaling and accessibility checks where required.

## 27.7 Debug and optimize

- Diagnose compile/import errors.
- Diagnose runtime exceptions and invalid references.
- Reproduce gameplay bugs using input traces.
- Diagnose collision/physics anomalies.
- Identify performance regressions.
- Optimize CPU/GPU, memory, draw calls, network bandwidth and loading.
- Run regression tests after repairs.
- Generate a handoff report with evidence.

## 27.8 Team and pipeline integration

- Generate tests and code review summaries.
- Create changes in branches/worktrees.
- Report dependency and plugin changes.
- Produce CI-friendly result bundles.
- Track acceptance criteria and release gates.
- Generate structured documentation and migration notes.
- Support project-specific style guides and approved knowledge packs.

---

# PART XXVIII — DETAILED MILESTONE GATES AND DELIVERY ARTIFACTS

## 28.1 Step 4 gate — complete and audit before model baseline

**Status:** REPORTED COMPLETE based on the user-supplied Step 4 completion summary. This is E4-style reported evidence, not an independent rerun by the present blueprint update.

Reported deliverables and results:

- `t3-017-health-stamina-hud`: native `UHealthStaminaHUDWidget`, dynamic event subscriptions, clamping, idempotent listener registration and cleanup; 12 probes H1–H12 reported passing on Unreal Engine 5.7.4.
- `t2-008-projectile-collision`: native `AProjectileActor`, collision-driven impact, owner exclusion, exactly-once damage, lifespan cleanup and health invulnerability integration; 12 probes Proj1–Proj12 reported passing on Unreal Engine 5.7.4.
- `docs/GAME_ENGINE_INTELLIGENCE_SCOPE.md`, `docs/ENGINE_COVERAGE_MATRIX.md`, `docs/GAMEFORGE_MODEL_REQUIREMENTS.md`, `docs/CROSS_ENGINE_BENCHMARK_PLAN.md` and `configs/engine_knowledge_registry.json`.
- Seven structured engine-neutral tasks under `benchmark_tasks/engine_neutral/`.
- Backward-compatible engine-scope and verification metadata in task/report schemas and normalization/reporting code.
- Reported tests: 94/94 unit and protected-oracle tests; 6/6 real-engine integration tests; 30 task specifications validated with zero errors; prior pilots reported intact. The same supplied summary also says “80 total passing automated tests”; since 94 + 6 does not equal 80, reconcile collected test IDs/overlap from actual pytest output before asserting an aggregate count.
- Reported controlled-defect rejection for duplicate HUD subscriptions, display clamping, no projectile damage, and projectile self-damage.

Required artifacts (as defined in the previous Antigravity prompt):

- `t3-017-health-stamina-hud` task and acceptance criteria.
- `t2-008-projectile-collision` task and acceptance criteria.
- Native Unreal UMG implementation and lifecycle tests.
- Native Unreal projectile actor and real collision-driven probes.
- Controlled defective candidates.
- Engine-agnostic intelligence-scope document.
- Engine coverage matrix.
- Model requirements document.
- Cross-engine benchmark plan.
- Report/schema updates with honest verification levels.
- `GAMEFORGE_STEP4_HANDOFF_REPORT.md`.

Next audit action: inspect `GAMEFORGE_STEP4_HANDOFF_REPORT.md`, `STEP4_AUDIT_REPORT.md`, source files, JSON results, test IDs and logs in the actual repository. Re-run the suites where feasible before using the benchmark for model comparisons. Check whether any UI visual claims have actual rendered screenshots or only widget-state checks. Confirm projectile probes use true engine collision events rather than direct calls only. Confirm all prior pilots still pass. Do not downgrade the supplied report's status merely because this document was updated from a summary, but preserve the distinction between reported completion and independent reproduction.

## 28.2 Step 5 gate — baseline readiness

- Benchmark version frozen.
- Each baseline task reviewed for ambiguity.
- Hidden-test leakage risks reviewed.
- At least two model candidates with confirmed allowed use.
- Equal task context/tool/time budgets.
- Same engine versions and fixtures.
- Exact costs and time recorded when available.
- Failure reports retained.
- Repeated subset to estimate variance.
- No private test leakage.

## 28.3 Step 6 gate — dataset readiness

- License/provenance policy approved.
- Train/dev/evaluation split boundaries defined.
- Trajectory schema validated.
- No secret/confidential data in examples.
- Reference results reproducible.
- Failure taxonomy applied and reviewed.
- Deduplication/contamination checks automated.
- Human review coverage documented.

## 28.4 Step 7 gate — SFT proof of value

- Base model, license and exact revision recorded.
- Training configuration reproducible.
- Held-out evaluation frozen before training.
- GameForge benchmark scored before and after.
- General coding/reasoning regression set scored before and after.
- Memory, latency, cost and inference deployment measured.
- Ablations identify which data class contributed.
- If no clear gain, stop or change target rather than scaling.

## 28.5 Step 8 gate — agentic competence

- Model has bounded, typed tools.
- Work starts from a clean project snapshot.
- Agent observes build and runtime evidence.
- It can diagnose multiple failure types.
- It performs targeted repairs.
- It reruns relevant regressions.
- It does not modify hidden grader or acceptance criteria.
- Its final claims match observed results.
- It can stop safely and report when blocked.

## 28.6 Step 9 gate — Game IR choice

- Implement only the minimal IR and deterministic backend needed for the experiment.
- Compare direct output and IR output on matched tasks.
- Report each grading layer separately.
- Count compiler-specific failures.
- Compare costs and repair iterations.
- Retain a native escape hatch.
- Record decision to expand, shrink or abandon IR.

## 28.7 Step 10 gate — visual/multimodal value

- Define visual labels/rubric before evaluation.
- Collect human-rated calibration sample.
- Measure agreement and error types.
- Tie video observations to timestamps/state when feasible.
- Keep visual review separate from deterministic metrics.
- Demonstrate improvement on held-out tasks.

## 28.8 Step 11 gate — character bundle

- Use rights-cleared input asset or source workflow.
- Mesh imports into Unreal.
- Rig/skeleton resolves.
- Animation set retargets.
- Animation graph transitions correctly.
- Controller and animation remain synchronized.
- Collision and movement work.
- Visual/motion QA passes documented checks.
- Asset provenance is complete.
- A controlled broken asset/rig is rejected.

## 28.9 Step 12 gate — multi-engine support

Per engine:

- Real engine/version discovery.
- Clean fixture and native reference solution.
- Build/import pipeline.
- At least one meaningful runtime probe family.
- Saved-asset validation.
- Controlled-defect rejection.
- Reproducibility and regression tests.
- Accurate report and support level.
- License and SDK/toolchain compliance.

Static code generation alone does not satisfy real-engine support.

## 28.10 Step 13 gate — Windows product readiness

- Users can select a project and see detected engine/version.
- Permissions are understandable and effective.
- Plan/diff approval is usable.
- Run/test/report loop works end to end.
- Cancellation and rollback work.
- Logs and reports are persisted safely.
- Model/provider config and costs are visible.
- Sensitive data handling is explicit.
- A small user study shows measurable workflow benefit.

---

## 28.11 Step 14 gate — scale and model-architecture decision

Step 14 is a controlled research decision, not an automatic commitment to a larger model or mixture-of-experts system. Pass only when:

- A specific capability ceiling is demonstrated on held-out GameForge-Bench tasks after fair baseline evaluation.
- Strong retrieval, project indexing, better tool design, task decomposition, or a small adapter have been tested as lower-cost alternatives where relevant.
- Candidate models/architectures are compared with equal tool permissions, budgets, prompt context, retry rules, and splits.
- The report includes quality, regression, latency, VRAM/RAM, throughput, failure taxonomy, and total cost under a disclosed workload.
- Any additional training compute has an approved budget and an expected-value hypothesis before it is rented.
- No architecture is adopted because of parameter count, marketing claims, or a single aggregate benchmark.

If a larger model, MoE, expert router, or learned editor simulator does not yield repeatable benefit at an acceptable cost, retain the simpler design and record the result.

## 28.12 Step 15 gate — production readiness and secure execution

Pass only when:

- Threat modeling covers untrusted code, tool abuse, prompt injection from project files/docs/assets, secret exposure, network egress, destructive edits, build workers, and hidden-grader exfiltration.
- An OS-level container/VM/sandbox boundary is actually deployed and its limits experimentally tested before executing arbitrary untrusted native code at scale.
- The benchmark reports isolation classification and does not label process-level restrictions as a hardened sandbox.
- Model weights, training data, documentation, model outputs, assets, plugins, and engine usage have documented provenance and legal review for the intended use.
- A release candidate passes full unit/integration/regression suites and a soak/repeatability run.
- Rollback, audit logs, permission review, privacy controls, version pinning, reproducible releases, and incident handling are documented.
- Known gaps are explicitly accepted by a named owner; no critical known failure is hidden by a status label.

# PART XXIX — DOCUMENTATION AND IMPLEMENTATION STYLE RULES FOR ANTIGRAVITY

## 29.1 Antigravity must not treat this blueprint as permission to implement everything at once

The master blueprint contains a multi-year scope. An implementation prompt should always name the current milestone and acceptance gate. Antigravity should audit existing files, implement only the scoped vertical slice, run tests, and document blocked work.

## 29.2 Every handoff must include

- Status and exact scope.
- Source changes and unchanged critical files.
- Engine/tool versions detected.
- Commands actually run.
- Unit versus real-engine test results.
- Probe values and target tolerances.
- Controlled-defect outcomes.
- Reports and logs path.
- Security/isolation classification.
- Unverified/blocked items.
- Regression outcomes.
- Next single recommended task.

## 29.3 No ambiguous acceptance statements

Avoid “works as expected,” “production-grade,” “full integration,” “all tests pass,” or “ready” without defining the test path and evidence. Prefer a statement such as:

> “Built on Unreal Engine 5.7.4; 12 registered probes passed using the named fixture; two buildable defective candidates were rejected by probes P2 and P4; screenshot-based visual review was not performed.”

## 29.4 Preserve source documents

Do not silently rewrite the original GameForge-Bench v0.1 design or source task drafts when they are meant to be historical specifications. Make versioned updates and record decisions. Keep the master blueprint a living plan, not the only history record.


# PART XXX — HOW TO USE THIS BLUEPRINT IN THE REAL PROJECT

## 30.1 This is the master specification and sequential execution controller

This file is the durable source of instructions and the ordered plan. It is not an instruction to implement the entire multi-year product in one uncontrolled code change. Antigravity must execute the roadmap **one milestone at a time, in order**, using the gates and resume protocol below. The user should not have to repeatedly choose which milestone comes next.

For every milestone:

1. Read this canonical master strategy first, then inspect the actual repository, current milestone ledger, latest handoff report, Git state and required toolchains.
2. Determine the lowest-numbered milestone that is not accepted by evidence. Do not use old prompts or archived documents as competing instructions.
3. Write an internal scoped work plan directly from the relevant milestone's required artifacts and acceptance gate; then implement the work rather than stopping after planning.
4. Execute applicable tests to completion, inspect logs/results, repair failures and rerun regression checks.
5. Do not mark a milestone complete on documentation alone. The gate must be supported by code/assets and actual test evidence appropriate to the claim.
6. On passing the gate, update this master strategy's current-state ledger, `GAMEFORGE_ROADMAP.csv`, relevant engine registry rows, and handoff report. Preserve historical reports and acceptance criteria.
7. Record architecture/priority/acceptance changes through a numbered ADR. Routine progress/status changes do not require an ADR but must cite evidence.
8. Automatically continue to the next sequential milestone in the same agent session when feasible and when no approval-only action is required. Never ask the user which step to do next.
9. If context/time/resource limits prevent completing the next milestone, write an exact resumable state: current step, completed substeps, failing/blocking tests, files changed, commands run, next command/action and unmet gate. Resume from it on the next invocation without repeating successful work unnecessarily.
10. Do not skip a failed or blocked dependency gate. You may complete safe, independent documentation or diagnostics, but downstream dependent steps cannot be marked complete.
11. Routine repository reads, ordinary code edits, local test execution, report writing, and reversible workspace operations are authorized within scope. Obtain explicit approval before paid API/cloud/GPU spending, purchasing, publishing/releasing, pushing to a remote, destructive data deletion, installing software or enabling Windows/firmware security features, changing privileged permissions, using credentials, or accepting legal terms.
12. Be honest about this operating model: execution occurs while the agent session is active; this document does not create a background daemon or run tasks after the session ends. On every later invocation, resume from the recorded milestone state.

### 30.1.1 Mandatory milestone loop

`READ SSOT → AUDIT LIVE STATE → SELECT FIRST UNACCEPTED STEP → IMPLEMENT → TEST → REPAIR → REGRESSION TEST → VERIFY GATE → UPDATE STATE → CONTINUE TO NEXT STEP OR RECORD BLOCKER`.

The loop must not stop at “here is a plan”, “waiting for completion”, or an unverified success summary. When a tool starts an asynchronous engine build/test, poll it until completion or timeout, preserve its output, and classify the actual result.

### 30.1.2 Approval and blocker behavior

Never bypass a dependency merely because a later task is easier. If a required API credential, paid compute, engine installation, user-only permission, legal decision, or OS feature is needed, complete all safe work that does not depend on it, record precisely what approval/capability is missing, and stop the dependent branch. Do not silently substitute fake/mock evidence for a blocked real-engine or training experiment.

### 30.1.3 Ordered execution register — all operational steps

This table is the automatic sequence. Section 28 contains the detailed acceptance gate for each milestone; this table determines order, prerequisites and what the agent must execute. Statuses are updated only with evidence.

| Step | State at v3.1.0 | Execute in this order | Required gate before advancing |
|---|---|---|---|
| 1 — Benchmark foundation | REPORTED_COMPLETE | Validate schemas/inventory; execute controller pilot; preserve runner, reports and defect controls. | Real Unreal pilot + grading/CLI tests; known-defect rejection; reproducible report. Re-run when shared runner changes. |
| 2 — Health/damage | REPORTED_COMPLETE | Verify health invariants, invulnerability timing, event ordering and exactly-once death. | Native Unreal build; all required probes; defective candidates rejected; regression suite green. |
| 3 — Pickup/composition/isolation audit | REPORTED_COMPLETE | Verify health/stamina pickups, one-time collection, composed player and process-level isolation disclosure. | Pickup/composition probes; five defect categories; previous pilots unchanged; isolation not mislabeled as OS sandbox. |
| 4 — HUD/projectile/cross-engine scope | AUDITED_E4_VERIFIED | Step 4 handoff audited; test totals reconciled to 114 unique automated tests (49 unit, 45 protected oracles, 20 integration); native Unreal 5.7.4 HUD and projectile probes verified; 0 spec errors; prior pilots green. | E4 reported real-engine evidence audited and verified; widget-state and damage callback scope documented. |
| 5 — Existing-model baselines | UNRESOLVED / NOT ACCEPTED | Historical baseline evaluation run preserved in GAMEFORGE_STEP5_BASELINE_REPORT.md; open review findings regarding candidate diffs, test discovery, and scorecard consistency remain under investigation. | Review findings resolved with verified evidence before formal milestone acceptance. |
| 6 — Rights-aware data factory | USER_AUTHORIZED_PRE_GATE_IN_PROGRESS | Trajectory schema v1.0 validated; dataset source register rights audited; deduplication, group splitting, and protected contamination scanner implemented; synthetic end-to-end testing complete. | Implementation branch authorized by user pre-gate; formal milestone acceptance remains gated on legal source review and dataset completion. |
| 7 — Specialist SFT/adaptor proof | FRAMEWORK_REPAIR_IN_PROGRESS; TRAINING_BLOCKED_PENDING_STEP5_STEP6 | SFT/LoRA configuration, training readiness validator, dataset builder, asset specialist boundary, dry-run, and unit tests implemented; training execution strictly gated pending Step 5 baseline retest and Step 6 rights clearance. | Reproducible held-out improvement on game tasks without unacceptable general-reasoning regressions, license issues or serving problems. No scale-up if gain is not clear. |
| 8 — Tool-use and repair learning | PLANNED; depends on 7 and trusted tools | Record valid agent trajectories; train/evaluate planning, tool selection, diagnostics, targeted repair and regression-aware iteration; start with verifiable outcomes. | Under equal budgets, complete-task success and repair efficiency improve; tool safety and regression rates remain acceptable; reports reflect observed results. |
| 9 — Game IR experiment | RESEARCH_GATE; depends on stable benchmark | Implement minimal IR/contracts for a few primitives; compare direct native generation, IR+compiler, and IR with native escape hatches. | Matched task A/B results show a meaningful advantage after accounting for compiler failures/costs, or decision records shrinking/dropping the IR. |
| 10 — Multimodal evaluation | PLANNED_RESEARCH | Build screenshot, short-video, scene-tree, asset, animation and profiler-trace tasks; calibrate any model/judge against human labels; measure text-only vs multimodal baselines. | Held-out improvements are measured; visual/temporal scores are calibrated; non-visual deterministic metrics remain separate. |
| 11 — Character Bundle prototype | PLANNED_RESEARCH | Integrate licensed/source-cleared mesh, skeleton, skin weights, retargeting, motion clips, animation graph, controller and QA into one Unreal bundle. | Native import and runtime checks pass for rig/pose/animation/controller/collision/performance; a known-broken asset is rejected; provenance complete. |
| 12 — Expand native engine execution | PLANNED; toolchain-gated | First install/enable only with permission; add one engine at a time using native fixture, build/import, probes, saved-asset inspection, defect tests and versioned docs. Start with Unity/Godot based on user demand and feasibility. | Each engine/feature claims only its measured support level; real runtime verification is completed per engine/version; cross-engine parity is measured, not assumed. |
| 13 — Windows application | DEFERRED; depends on proven agent loop | Design app shell, project detection, task planning, diff/review, engine/tool permissions, run/test reports, cancellation, rollback, secret/cost visibility, settings and update path. | End-to-end user workflow is reliable, reversible, secure enough for stated threat model, and measurably useful in user evaluation. |
| 14 — Scale/model architecture decision | RESEARCH_GATE | Compare base sizes, fine-tunes, adapters, routing/MoE, multimodal backbones and local/cloud split under matched quality/cost/latency/VRAM tests. Evaluate learned simulators only if useful. | A specific capability ceiling is measured; cheaper alternatives are tested; costs and hardware constraints are disclosed; scale-up has an approved budget and expected-value hypothesis. |
| 15 — Production/security/legal readiness | FUTURE; depends on preceding product path | Threat model; OS-level sandbox deployment; provenance/legal review; secrets/network controls; CI; release/version pinning; telemetry/privacy; rollback; incident/runbook; user support. | Tested security boundaries, legal clearance for intended use, complete regression/soak/reproducibility suite, operational acceptance and documented residual risks. |

**Mandatory continuation rule:** once a step's gate is satisfied, immediately start the next row in sequence without asking the user to select the next task, until the session ends, a genuine blocker is reached, or an approval-only action is required. Do not leap over a gate. Do not conduct paid training or API evaluation without authorization. The current active row at this revision is Step 6 (Rights-Aware Data Factory).

## 30.2 Priorities

- **P0 — Current prerequisite:** Required for the next measurable milestone or a correctness/security issue.
- **P1 — Core:** High-value game-development capability needed for useful baseline coverage.
- **P2 — Important expansion:** Valuable for breadth, asset pipelines or mature workflows after core gates pass.
- **P3 — Specialist/future:** Advanced, less universally needed, costly, or dependent on additional infrastructure.

Priority is a sequencing tool, not a quality ranking of the feature.

## 30.3 Feature registry maintenance procedure

When adding or updating a feature:

1. Identify the exact engine/version range.
2. Select a feature family and subdomain.
3. Add official or otherwise appropriate reference records after verification.
4. Mark the current support level conservatively.
5. Link task IDs and verification artifacts.
6. Record plugin/toolchain dependencies.
7. Add a representative task if the capability is strategic.
8. Create a reference solution and controlled defect where native execution matters.
9. Run applicable tests and record environment information.
10. Promote status only after evidence satisfies the next level.
11. Record semantic differences where another engine implements the concept differently.
12. Revisit records when an engine version changes or a plugin/API is deprecated.

## 30.4 Required status language

Use these terms consistently:

- `PLANNED`: Future intent only.
- `SPECIFIED`: Requirements and acceptance criteria exist.
- `AUTHORED`: Code/assets/documents have been created.
- `STATICALLY_VALIDATED`: Static/schema/source validation ran successfully.
- `UNIT_TESTED`: Isolated tests passed, potentially with mocks.
- `REAL_ENGINE_VERIFIED`: The relevant behavior was actually executed against the declared real engine/version.
- `END_TO_END_VERIFIED`: A connected multi-system workflow passed the specified end-to-end tests.
- `BLOCKED`: Required engine, toolchain, license, permission or infrastructure is unavailable.
- `UNVERIFIED`: No adequate evidence supports a pass claim.
- `RETIRED`: The capability/task has been deliberately removed with a logged decision.

Do not use “supports” without adding the level and scope. For example: “Unity health component authored and statically checked; real Unity runtime unverified” is acceptable. “Unity support complete” is not.

### Evidence ladder (`verification_level`)

- `E0_CATALOGUED`: Capability is named in the taxonomy; no task spec or implementation evidence.
- `E1_SPECIFIED`: Task requirements/acceptance criteria exist, but native implementation/runtime evidence is absent.
- `E2_STATIC_OR_AUTHORED`: Code/assets are authored or statically/schema checked; no actual engine run has verified behavior.
- `E3_UNIT_TESTED`: Isolated unit tests passed; engine behavior may still be unverified.
- `E4_REPORTED_REAL_ENGINE`: A handoff report and artifacts state that real-engine checks passed for a narrow scope; not independently reproduced in the current audit.
- `E5_INDEPENDENTLY_REPRODUCED_REAL_ENGINE`: An independent clean-snapshot run re-executed the declared engine/version, probes, regression and required asset checks with auditable outputs.

Lifecycle state and evidence level are separate axes. `REAL_ENGINE_VERIFIED` must be scoped to the exact task, version and run; E4 must not be silently relabeled E5.

## 30.5 Exact current next actions

**Current next milestone: Step 6 — Rights-aware data factory.** Steps 1–4 are audited and verified at E4; Step 5 existing-model baseline evaluation has been executed under frozen manifest `gameforge-bench-v0.2.0-baseline` with two local candidates and accepted by measured evidence (Pass@1 90.9%, 100% variance agreement on repeated runs, $0.00 cost, zero private test leakage). Step 6 dataset readiness is now active.

Execute Step 6 in this order:
1. Define and validate the formal trajectory schema (`schemas/trajectory_schema.json`).
2. Establish the dataset source and license register (`configs/dataset_source_register.json`) with approved provenance policies.
3. Define strict train/dev/eval_private split boundaries with private evaluation isolation.
4. Implement automated deduplication and contamination detection against private benchmark tasks (`src/gameforge_bench/data_factory.py`).
5. Curate initial clean-room task trajectories and controlled defect examples.
6. Verify human review coverage and zero confidential/proprietary data leakage.


1. Reconfirm the current repository, pinned Unreal Engine 5.7.4 environment, task inventory, and all four reference pilots. Run `validate-specs` and the applicable regression suites.
2. Freeze a baseline benchmark release manifest: task IDs, task and acceptance versions, starting fixture hashes, engine/tool versions, hidden split membership (kept private), permitted context, permitted tools, retry policy, wall-clock/token/tool budgets, and report schema.
3. Select at least two existing model configurations that can legally and practically be evaluated. Create a model register containing provider/model/revision, license/terms, modality, context window, tool support, pricing if relevant, deployment, date and permission basis.
4. Prefer already available or no-cost/local candidates when adequate. Do not use saved credentials, call paid APIs, rent GPU/cloud resources, or accept terms without the required authorization. If this blocks comparison, complete the protocol and environment preparation, record the blocker, and do not fabricate results or pass the baseline gate.
5. Define an adapter contract for invoking model candidates under identical prompts, project context, allowed tools, retry rules, timeouts and task budgets. Keep candidate identity hidden from graders where practical.
6. Run candidates over a carefully selected initial subset of genuine engine tasks and engine-neutral tasks. Include at minimum controller, health/damage, pickup/composition, HUD, projectile and several engine-neutral tasks after checking their live status. Use clean snapshots and the same engine/version.
7. Preserve raw outputs, tool traces, diffs, build/runtime logs, hidden-grader results, time, tokens, cost and error classifications. Repeat a subset to estimate variance.
8. Score each grading layer separately. Distinguish compile success from behavior, assets, performance, regressions, cross-engine reasoning and human-reviewed quality. Do not collapse all outcomes into one score without also publishing per-domain results.
9. Analyze failures and identify the most valuable missing-data categories. Do not tune prompts after seeing only one model's results without applying the same protocol to all candidates.
10. Produce `GAMEFORGE_STEP5_BASELINE_REPORT.md`, update the model register and derived roadmap, and mark Step 5 passed only when every gate in Section 28.2 is satisfied.
11. When Step 5 passes, automatically proceed to Step 6 (rights-aware data factory) if the session can continue safely; otherwise persist exact resume state and make Step 6 the unambiguous next milestone.

After Step 5, the mandated sequence is: Step 6 rights-aware data factory; Step 7 SFT/adapter proof of value; Step 8 tool-use and outcome-verifiable repair learning; Step 9 controlled Game IR experiment; Step 10 multimodal evaluation; Step 11 Character Bundle prototype; Step 12 per-engine native execution expansion; Step 13 Windows application; Step 14 scale/model-architecture decision; Step 15 production/security/legal readiness. The detailed deliverables and gates in Sections 28.3–28.12 govern these steps. No step may bypass its prerequisites.

## 30.6 Questions that require evidence rather than assumptions

- Does a game-specialized fine-tune beat a general coding model with the same tools?
- Does Game IR materially improve correctness or just add compile failures?
- Does retrieval improve versioned API accuracy enough to justify its latency/context cost?
- Is a single model enough, or do specialist adapters/models improve total quality/cost?
- Can the local AMD GPU reliably run a suitable inference backend, and at what context length/throughput?
- What proportion of tasks can be executed headlessly in Unreal, and which need rendered validation?
- How much training data is needed before the first measurable gain?
- Which engine after Unreal deserves full runtime support first?
- Does character generation fail most often at geometry, rigging, animation, engine integration, or quality criteria?
- What isolation environment is practical for executing untrusted native code while keeping Unreal toolchains available?

These are research questions that should become small experiments and logged decisions, not assumed answers.

---

# PART XXXI — GLOSSARY

- **Agent:** A model-driven system that plans actions, uses tools, observes results and iterates toward a goal.
- **Adapter:** Engine-specific implementation of a shared set of inspection/build/test operations.
- **Asset:** A native resource such as mesh, material, texture, animation, audio, scene/prefab, widget or data object.
- **Baseline:** Performance of a model/configuration before specialization, used for comparison.
- **Behavior probe:** A controlled input sequence that measures actual game behavior against a target/tolerance.
- **Candidate:** The implementation being evaluated; may be produced by a model or supplied by a developer.
- **Character Bundle:** Proposed typed grouping of mesh, rig, animation graph, controller and QA artifacts for a coherent playable character.
- **Cross-engine parity:** Similarity in observable gameplay contract across native implementations, within explicit tolerances; not textual code similarity.
- **Data provenance:** Traceable record of origin, rights, transformations and allowed use for an artifact or training record.
- **ECS:** Entity Component System; a design pattern with different concrete forms and APIs in different engines.
- **Game IR:** Proposed engine-neutral typed description of common gameplay semantics, optionally lowered into native engine implementations.
- **Grader/oracle:** Trusted code and tests that determine whether an implementation satisfies acceptance criteria.
- **Hidden test:** A protected acceptance test not exposed to the candidate during evaluation.
- **Idempotency:** Repeating an operation under the same logical conditions does not duplicate an effect that should happen once.
- **Pass@1:** Fraction of tasks passing on the first attempt under a declared protocol.
- **Pass@k:** Fraction of tasks for which at least one of up to k attempts passes, reported with retry/cost rules.
- **Project graph:** Structured map of source symbols, components, assets, references, events and dependencies.
- **RAG/retrieval:** Supplying selected external/project knowledge at inference time rather than relying only on model weights.
- **SFT:** Supervised fine-tuning on curated examples of desired inputs/outputs or tool trajectories.
- **UMG:** Unreal Motion Graphics, Unreal's widget/UI framework.
- **Verification level:** Explicit classification of what was actually checked (from catalogued to real-engine/production evidence).
- **World model / learned simulator:** A learned predictor of state transitions or environment actions; in this project, a research hypothesis that must be verified against the real engine.

---

# PART XXXII — SOURCE AUDIT, RECONCILIATION, EXTERNAL CONSTRAINTS, AND CURRENT OPERATING DECISIONS

## 32.1 Source-ingestion manifest

The original source package contained the V2 master blueprint, the V1 archive, the roadmap CSV, the engine-feature matrix, and a README inside the ZIP. The source audit reported these counts; the package's local artifacts and ZIP entries were checked for presence and dimensions during reconciliation. The user subsequently supplied a Step 4 completion summary, which updates project progress but is not a substitute for independently inspecting the live repository and full handoff artifacts:

| Source artifact | Reported size | Reported content count | Use in this revision |
|---|---:|---:|---|
| `GAMEFORGE_MASTER_BLUEPRINT.md` V2 | 136,588 bytes | 2,465 lines | Main source body preserved, amended and promoted into this version |
| `GAMEFORGE_MASTER_BLUEPRINT_V1_ARCHIVE.md` | 38,096 bytes | 566 lines | Historical comparison/archive |
| `GAMEFORGE_ROADMAP.csv` | 3,639 bytes | 16 lines: header + 15 milestone rows | Operational roadmap retained and status-caveated |
| `ENGINE_FEATURE_COVERAGE_MATRIX.csv` V1 | 1,651,073 bytes | 4,525 lines: header + 4,524 records | Migrated to Registry v2.1 while preserving V1 in archive |
| `README.txt` from package ZIP | 921 bytes | 9 lines | Package/status caveat incorporated |

The matrix comprises 39 canonical `engine_id` values × 116 `feature_domain` values, organized into 20 `feature_category` groups. This is a catalogue scope, not a claim that 4,524 features are implemented. The package does not contain the actual repository source tree, all Step 1–3 JSON reports, a Step 4 handoff report, or a Git commit proving the supplied implementation reports; those remain external implementation evidence and must be inspected from the repository when executing the next milestone.

## 32.2 Contradiction register and binding resolutions

| ID | Conflict/gap found | Binding resolution |
|---|---|---|
| `C-1` — Engine counts | The V2 appendix said 31 entries; 33 narrative dossiers existed; the CSV has 39 canonical IDs. | The registry's 39 canonical IDs are authoritative. The narrative now has 36 dossier sections because three sections each discuss a related pair; three additional dossiers cover `openfl_haxeflixel`, `flax_engine`, and `source_modding`. All rows and evidence remain separate per canonical ID. |
| `C-2` — Registry schema | Section 18.1 listed 19 fields while the V1 CSV had 12 different/overlapping fields. | Registry v2.1 uses a 26-column union (12 legacy columns + 14 missing governance fields), keeping old data/field names and exposing all requested evidence columns. The V1 matrix is archived. |
| `C-3` — Status vocabulary | Matrix used ad hoc lifecycle strings and `E0_E1`/`E1_OR_SPECIFIED`; the blueprint prescribed canonical states. | Lifecycle `current_status` and evidence `verification_level` are distinct axes. Allowed lifecycle terms are Section 30.4; evidence uses E0–E5. A handoff-reported run is E4; independent reproduction is E5. |
| `C-4` — Priority corruption | The V1 matrix used `REPORTED_PILOT` and `STEP4_PENDING` in `priority`, which must be P0–P3. | Registry v2.1 converts those to actual priorities, records the legacy marker in evidence notes, and uses canonical status/evidence to represent rollout state. Unreal-first prerequisites may be P0; other-engine expansion remains lower priority. No status marker is permitted in the `priority` field. |
| `C-5` — Engine strategy | V1 expected paired Unity/Unreal execution early; V2 pivots to Unreal-first while keeping cross-engine goals. | The intelligence scope remains broad. Specs and engine-neutral concepts can be evaluated early, but real-engine execution through Step 11 is Unreal-first on the pinned local 5.7.4 setup. Full native Unity/Godot execution is gated at Step 12 after toolchains are available. No parity claim without per-engine execution. |
| `C-6` — Phase and step numbering | Older phase tables and the 15-step operational roadmap used different numbering/gates. | `STEP_1`–`STEP_15` are the operational source of truth. Phase numbers are narrative groupings only; every milestone has its own acceptance gate. Steps 14 and 15 now have explicit gates in Sections 28.11–28.12. |
| `C-7` — Pilot mapping | The original six pilot list drifted from how work was actually staged; Step 4 was pending when v3.0.0 was written. | Step 1: controller/movement/camera and input exercised within it; Step 2: health/damage; Step 3: pickup/stamina/player composition; Step 4: HUD/projectile and cross-engine benchmark foundations are reported complete in the supplied handoff summary. Independent audit remains part of Step 5 preparation. A standalone input-mapping task remains in the wider inventory. |

## 32.3 Current milestone state at this document revision

The authoritative milestone ledger remains Section 16.1 and the compact register is `GAMEFORGE_ROADMAP.csv`:

- **Steps 1–3:** reported complete in supplied handoff reports, with narrow Unreal Engine 5.7.4 scope. Reported test results have not been independently rerun as part of this master-document update.
- **Step 4:** AUDITED AND RECONCILED (E4_REPORTED_REAL_ENGINE). Audited in STEP4_AUDIT_REPORT.md with 114 unique automated tests (49 unit, 45 protected oracles, 20 real integration tests); 12 HUD probes, 12 projectile probes; prior pilots verified without regression on real Unreal Engine 5.7.4.
- **Step 5:** UNRESOLVED / NOT ACCEPTED — EVIDENCE INTEGRITY AND TEST GATE OPEN. Historical baseline evaluation run preserved in GAMEFORGE_STEP5_BASELINE_REPORT.md; review findings concerning candidate diffs, test discovery, and scorecard consistency remain under investigation. No baseline score is fabricated.
- **Step 6:** USER-AUTHORIZED PRE-GATE IMPLEMENTATION IN PROGRESS — NOT ACCEPTED. Authorized by user direction; trajectory schema v1.0, rights-enforcing source register, deduplication, group splitting, and protected contamination scanner implemented. Training remains blocked until formal legal source review.
- **Steps 7–15:** planned or research-gated. No supplied evidence establishes a completed proprietary training dataset, specialist fine-tuning run, RLVR run, validated Game IR compiler, integrated character generation pipeline, full multi-engine native execution, or finished Windows product.

## 32.4 Phase and milestone mapping

The 15 operational steps are authoritative. At this revision, Steps 1–4 are reported complete and Step 5 is the active next step. For readability, the strategic phases group them as follows; phase labels do not create additional tasks or bypass any step gate:

| Strategic group | Operational steps | Purpose |
|---|---|---|
| Foundation and first verified vertical slice | Steps 1–4 | Benchmark, movement, health, pickups/composition, then HUD/projectile audit |
| Model measurement and data rights | Steps 5–6 | Baselines, failure taxonomy, trajectory schema, provenance and split controls |
| First specialization loop | Steps 7–8 | Small SFT/adaptor experiment, then tool-use/repair optimization if justified |
| Representation experiment | Step 9 | Direct native generation vs. Game IR + contracts vs. IR with native escape hatches |
| Multimodal and character systems | Steps 10–11 | Visual/temporal reasoning, asset QA and complete Character Bundle |
| Broader native-engine execution | Step 12 | Promote Unity/Godot and later engines only per task/domain evidence |
| User-facing product | Step 13 | Windows application after the core model-agent loop is useful and safe |
| Architecture/compute scale decision | Step 14 | Compare larger model, routing, adapters, experts and simulators against measured constraints |
| Production readiness | Step 15 | Hardened sandbox, legal review, telemetry/privacy, release engineering and operations |

## 32.5 Engine versions: pin the local baseline, do not claim latest-version status

The supplied local environment reports Unreal Engine 5.7.4. Epic's official [Unreal Engine 5.8 release announcement](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available) is dated June 23, 2026, so 5.7.4 is the **local reproducibility pin**, not the latest public Unreal Engine release. Keep all current baseline fixtures pinned while measuring models, and add an explicit migration task for 5.8 after the relevant baseline is frozen. Never silently upgrade an engine in a benchmark run.

The host profile is reported as Windows 11 Pro Build 10.0.26100, AMD Ryzen 5 7600X, 32 GB RAM, and AMD Radeon RX 7700 XT with 12 GB VRAM. These are report-derived environment claims and should be rediscovered by `doctor` at execution time. Local inference is an experiment whose actual backend, memory, context length and throughput must be measured. Do not assert that a particular model fits or that ROCm/HIP fine-tuning works until the exact GPU/OS/software combination is tested. The desktop machine can host normal development and current Unreal pilot execution; it is not a plausible assumption for frontier-scale model pretraining or high-parallelism RL.

## 32.6 Model and compute policy: no predetermined model size or bill

A previous generated strategy proposed fixed 32B/7B checkpoints, 15B CPT tokens, 250,000 SFT trajectories, 64×H100 training, a specific multi-week schedule, and a roughly USD 68,545 release-cycle estimate. Those values were not validated by GameForge runs and are **not commitments, budgets, or planning baselines**. They are removed from the binding plan.

Binding sequence:

1. Complete the benchmark vertical slice and freeze the evaluation protocol.
2. Compare at least two strong existing model configurations under equal conditions, recording model/revision, terms, context strategy, tools, cost, latency, retries, per-tier pass rate, regression rate, and failure classes.
3. Decide whether the observed deficits are better addressed by prompts/tools/project indexing/retrieval, data quality, SFT/LoRA, outcome-based optimization, a router, or model scale.
4. Run the smallest experiment capable of falsifying the hypothesis. Prefer small adapters or a modest, licensed base-model experiment before large CPT or RL expenditure.
5. Scale compute only after an independently reviewable held-out improvement and an approved cost plan. Measure each provider's actual GPU/CPU pricing, throughput and queue behavior immediately before budgeting.

No parameter count, token budget, expected uplift, or cloud spend is a guaranteed target until supported by measured throughput and a documented experiment design.

## 32.7 Game IR remains optional and empirically gated

Game IR (the original proposal and any successor such as UGIR/GF-GDSL) is a hypothesis, not a mandatory output format. Always preserve executable gameplay contracts and behavior probes because they remain useful even if the IR is narrowed or abandoned.

The minimum controlled experiment must compare the same model/harness/budget on matched tasks:

- A: Direct native engine code/asset generation.
- B: IR plus executable contracts and a deterministic lowering backend.
- C: IR plus contracts with explicit native escape hatches.

Report task pass rates by grading layer, compiler failures, behavioral failures, cost, latency, cross-engine consistency and authoring friction. Only expand the IR where the evidence shows material benefit without unacceptable ceiling effects. Do not claim that 95% of Blueprints or any fixed portion of gameplay can be represented until experimentally demonstrated.

## 32.8 Legal, licensing, and training-data guardrails

This section is an engineering control, not legal advice. Licensing obligations depend on the exact terms, jurisdiction, licensee, activity, source material, output use, and effective date. Obtain legal review before treating any dataset or tool interaction as cleared.

### Unreal Engine

Epic's current [Unreal Engine EULA](https://www.unrealengine.com/eula/unreal) defines Licensed Technology broadly, including Unreal Engine code and Epic-provided content, and includes restrictions on use of Licensed Technology as input to generative-AI training (and on some prompt-based inputs when the model trains on them). Until legal review states otherwise, do not ingest proprietary engine source, engine-provided samples/starter content, MetaHuman-related restricted content, or Fab/Marketplace content into model training or training prompts. Keep GameForge-authored gameplay source and the engine's use as a build/test environment conceptually separate, but still review whether logs, symbols, prompts, generated artifacts or runtime outputs contain restricted Licensed Technology before turning them into training data.

### Unity

Unity's [Terms of Service](https://unity.com/legal/terms-of-service) updated June 30, 2026 restrict using Unity Offerings or derived data for AI/ML training, validation or development without prior authorization and regulate automated access/agentic interactions. Unity's separate [Documentation Terms of Use](https://unity.com/legal/docs-terms) contains a limited express permission to access, index, retrieve, summarize and train on public documentation **solely** to help users learn about, evaluate, and make best use of Unity; it explicitly does not grant permission to use the documentation or a model/system trained on it to develop, train or improve a product/service that competes with or replicates Unity offerings. Unity Asset Store materials are separately governed by the [Asset Store Terms](https://unity.com/legal/as-terms).

Because GameForge is intended to be a cross-engine game-development product, do **not** assume that the narrow documentation permission automatically covers our commercial model. Have counsel review the precise planned use and obtain written permission where needed. Never scrape Asset Store/Fab content for training just because it is publicly discoverable.

### Dataset rules

- Keep a `provenance.yaml` per source/project and a per-record provenance trace for all training examples.
- Record source URL/revision, license and version, collection date, author/rights holder where known, permitted uses, derivative permissions, transformation, engine version, third-party assets, teacher model/provider and output-use terms.
- Separate training, validation, public-dev, public-rotating, and private held-out evaluation assets. Keep hidden graders and private eval content out of training.
- Remove secrets, credentials, private user data and unapproved proprietary assets.
- Treat public availability and permissive code license as necessary but not always sufficient; review bundled assets, contributions, model output terms, and third-party dependencies.
- Clean-room synthetic data is preferred, but synthetic does not automatically mean free of source/model/license constraints.
- Do not use proprietary engine internals, Marketplace/Fab asset data, or documentation outside its allowed purpose unless written authorization explicitly permits the intended use.

## 32.9 Benchmark baseline protocol must precede major training

Step 5 must produce a baseline bundle that can be reproduced. It must include:

- A versioned task split, private held-out split and leakage/contamination controls.
- At least two selected models/configurations with revision/terms recorded; disclose if a provider is not comparable or cannot support the same tools.
- Identical starting projects, acceptance criteria, tool availability, prompt information, wall-clock/token/tool budgets, retry policy, and engine versions wherever possible.
- Pass@1 and, where meaningful, pass@k; per-tier and per-layer outcomes; compile pass rate; functional pass rate; saved-asset pass rate; regression; flakiness; agent tool calls; token use; wall time; monetary cost; and failure taxonomy.
- Human expert baselines on a stratified subset where practical. Model-as-judge may be used for visual quality only after calibration against humans and with agreement/error reported.
- Full raw report artifacts, model/tool traces as permitted, candidate hashes, and an analysis that distinguishes model capability from harness or tool advantages.

No “world number one” claim may be made from a self-authored benchmark score alone. Publish the protocol, disclose the harness, maintain an unexposed test set, and seek independent replication on important claims.

## 32.10 Registry v2.1 conversion and priority cleanup

The V1 matrix used `REPORTED_PILOT` (351 rows) and `STEP4_PENDING` (78 rows) in `priority`, even though both are lifecycle/milestone markers rather than P0–P3 priorities. Registry v2.1 converts these to actual priority values and carries evidence state through `current_status`, `verification_level`, `evidence_note` and `required_next_evidence`. The conversion is conservative:

- Rows previously marked as reported pilots receive `P0` on Unreal's current foundational pilot path and `P1` on non-primary engine rows; this is a sequencing assignment, not proof of support.
- Rows previously marked Step 4 pending receive `P0` for the Unreal-first Step 4 gate and `P1` for other engine variants as future core domains.
- `REPORTED_REAL_ENGINE_VERIFIED_FOR_NARROW_PILOT` maps to `current_status=REAL_ENGINE_VERIFIED` with `verification_level=E4_REPORTED_REAL_ENGINE`; it is not E5.
- `AUTHORED_REAL_ENGINE_UNVERIFIED` maps to `current_status=AUTHORED`, `verification_level=E2_STATIC_OR_AUTHORED`.
- `STEP4_SPECIFIED_PENDING_EVIDENCE` maps to `current_status=SPECIFIED`, `verification_level=E1_SPECIFIED`.
- `NOT_IMPLEMENTED_OR_UNVERIFIED` maps to `current_status=PLANNED`, `verification_level=E0_CATALOGUED`.
- `PLANNED_REGISTRY_ONLY` maps to `current_status=PLANNED`, `verification_level=E0_CATALOGUED`.

Empty `last_verified_at` remains empty because this update did not independently execute the engine tests. Existing evidence notes preserve that the Step 1–3 scope comes from the supplied handoff reports.

## 32.11 Source and document governance

- This file, `GAMEFORGE_FINAL_MASTER_STRATEGY.md`, is the only active narrative specification. `GAMEFORGE_MASTER_BLUEPRINT.md` is a compatibility pointer only.
- Archived V1/V2 documents are retained for history, not for active agent retrieval. Configure project instructions/RAG ignore rules to exclude the archive by default.
- `GAMEFORGE_ROADMAP.csv` and `ENGINE_FEATURE_COVERAGE_MATRIX.csv` are derived machine-readable registers and must not quietly redefine this strategy.
- Every change that modifies architecture, a priority, a gate, engine version policy, model/data rights policy, or Game IR decision requires a numbered ADR entry with evidence and a clause reference.
- Update the master version using semantic versioning: MAJOR for core thesis/strategy/breaking representation changes; MINOR for new milestones/capability families or material gates; PATCH for clarification/schema fixes that do not alter intent.
- On every handoff, Antigravity must first inspect this file and current code, identify the specific section(s) implemented, and report conflicts before coding. A prompt cannot silently override the strategy.

## 32.12 Official external references checked for this revision

These links anchor the narrow external claims above. They do not replace a legal review of GameForge's exact intended use:

- Epic Games, [Unreal Engine EULA](https://www.unrealengine.com/eula/unreal) — Licensed Technology definition and generative-AI input restriction; accessed 19 October 2026.
- Unity, [Terms of Service](https://unity.com/legal/terms-of-service) — Section 17.2 restrictions on AI/ML use of Unity Offerings/derived data and authorized agentic access; accessed 19 October 2026.
- Unity, [Documentation Terms of Use](https://unity.com/legal/docs-terms) — limited documentation permission and its competitive-product limitation; accessed 19 October 2026.
- Unity, [Asset Store Terms](https://unity.com/legal/as-terms) — separate terms for training/use of Asset Store content; accessed 19 October 2026.
- Epic Games, [Unreal Engine 5.8 is now available](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available) — public release announcement dated 23 June 2026; accessed 19 October 2026.

Recheck these primary sources whenever the collection method, model purpose, terms, or engine/tooling changes. This document is not a legal opinion and does not imply that any restricted corpus has been cleared.

---

# APPENDIX F — COMPANION ARTIFACTS AND ACTIVE SOURCE OF TRUTH

The active package consists of:

1. `GAMEFORGE_FINAL_MASTER_STRATEGY.md` — this complete, authoritative specification and roadmap. All implementation prompts and project governance derive from this file.
2. `ENGINE_FEATURE_COVERAGE_MATRIX.csv` — Registry v2.1 with **4,524 engine × feature-domain records across 39 canonical engine IDs and 116 feature domains**, now using 26 columns: the 12 legacy fields plus the 14 governance/evidence fields required to reconcile Section 18.1.
3. `GAMEFORGE_ROADMAP.csv` — compact machine-readable roadmap with 15 operational milestones, statuses, deliverables and acceptance gates. It is a derived register and may not override this strategy.
4. `README.txt` — package manifest and status caveat.
5. `archive/GAMEFORGE_MASTER_BLUEPRINT_V2_ARCHIVE.md` and `archive/GAMEFORGE_MASTER_BLUEPRINT_V1_ARCHIVE.md` — immutable historical versions for auditability only; they are not active instruction sources.
6. `archive/ENGINE_FEATURE_COVERAGE_MATRIX_V1.csv` — the original 12-column matrix before registry schema/status normalization.
7. `SOURCE_AUDIT_MANIFEST.md` — ingestion counts, reconciliation register, and source limitations.

The matrix is a registry, not proof that every listed capability is implemented or that the taxonomy captures every API. Most records remain catalogued/planned. Only feature/task rows with linked evidence may be promoted. The original V2 package had 12 matrix columns and incorrectly used `REPORTED_PILOT` and `STEP4_PENDING` in the `priority` field; Registry v2.1 normalizes those markers and retains the provenance notes. Counts are 39 `engine_id` values × 116 `feature_domain` values = 4,524 records, grouped into 20 `feature_category` groups.

`GAMEFORGE_MASTER_BLUEPRINT.md` is retained at the previous path as a short compatibility pointer to `GAMEFORGE_FINAL_MASTER_STRATEGY.md`. Do not edit the pointer as a second specification. If an old tool only opens the previous filename, it must follow the pointer to the canonical file.

---

# FINAL PROJECT CHARTER

**Mission:** Build a leading game-development specialist model that can reason across game engines and improve through real evidence, while using Unreal Engine as the first deep execution target.

**Near-term proof:** Demonstrate that the benchmark can grade connected native game systems reliably, including known defects, and then measure strong existing models against those tasks.

**Model strategy:** Start with capable existing models, choose by benchmark and license, add version-aware retrieval and project context, construct a high-quality provenance-controlled trajectory dataset, run small specialization experiments, and scale only after held-out gains are demonstrated.

**Long-term capabilities:** Engine-neutral reasoning; native engine code/assets; character bundles; geometry/rigging/animation; world and level construction; UI/audio/VFX; AI and combat systems; multiplayer; profiling/repair; complete playable mini-games; multi-engine portability; secure agentic execution; and a Windows application with approvals, diffs, rollback and evidence.

**Quality rule:** Every important claim is tied to a verification level and evidence artifact. Every new capability has acceptance criteria. Every autonomous change is reviewable and reversible. Every training artifact has provenance. Every scale-up decision follows a measured result.

**Current step:** Step 5 — inspect and, where feasible, independently rerun Step 4 evidence; freeze the benchmark protocol and begin equal-budget evaluation of at least two existing models. Steps 1–4 are reported complete; Step 4 results are reported, not independently reproduced by this update.

**Final operating principle:** GameForge should not merely sound like an expert in game development. It should be able to demonstrate that its work behaves correctly in the requested engine, explain what it verified, and continually improve from trusted, legally usable evidence.
