# GameForge — Master Blueprint and Execution Workflow

**Version:** 1.0  
**Status:** Proposed operating plan; not yet validated by experiments  
**Primary objective:** Build a game-development specialist model that demonstrably outperforms strong general-purpose models on real, engine-verified game-development tasks, then use it as the intelligence core of future Windows tooling for Unity and Unreal.

> **Evidence discipline:** The benchmark and Game IR concepts originate in the supplied GameForge v0.1 draft. The combined roadmap and architecture below are synthesis and engineering recommendations. None of the proposed advantages should be treated as proven until measured. Engine versions, licensing, model licenses, APIs, and tool availability must be verified when each implementation decision is made; this blueprint does not claim fresh verification.

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

### Phase 0 — Definition and benchmark design
**Deliverables:** project charter, metrics, task schema, first 30 task specifications, provenance policy, evaluation protocol, baseline model shortlist.  
**Gate:** tasks are clear enough for two experienced developers to independently solve and agree on grading; no hidden grader dependency is exposed to the agent.

### Phase 1 — Minimal dual-engine benchmark harness
**Deliverables:** clean project snapshots, Unity/Unreal runners for the subset selected, build/test capture, static policy checks, artifact storage, reproducible reports.  
**Gate:** repeated runs on a reference set are stable enough to distinguish model failure from harness flakiness. Flaky tests are quarantined and investigated.

### Phase 2 — Baseline evaluation
**Deliverables:** results from strong general models under the same harness and budget; human-expert task completion baseline; failure taxonomy.  
**Gate:** identify a short list of high-frequency, high-value failure modes and validate that tasks test real capability rather than harness quirks.

### Phase 3 — Game IR/contract experiment
**Deliverables:** minimal IR for pawn, pickup, health/damage, enemy FSM, HUD binding, and interactable; deterministic validator/compiler prototype; native escape hatches.  
**Gate:** compare direct generation vs IR+contracts vs IR+native escape hatch. Keep/narrow/drop based on predefined benchmark results.

### Phase 4 — Data factory and specialist SFT
**Deliverables:** provenance-aware dataset, trajectory schema, curated successful and repair examples, train/evaluate scripts, regression suite.  
**Gate:** specialist beats its base model on held-out game-development tasks without unacceptable regressions in relevant coding/planning abilities.

### Phase 5 — Verifiable optimization
**Deliverables:** task reward pipeline, deterministic rewards, anti-cheat checks, budget-aware training loop.  
**Gate:** improvements persist across private tasks and repeated runs; no rise in test tampering, hard-coded trace behavior, or regression rate.

### Phase 6 — Character/animation and asset expansion
**Deliverables:** Character Bundle schema; import/rig/animation QA; supplied-asset tasks first, then generated-asset tasks.  
**Gate:** full pipeline succeeds on a held-out character set, not only curated demonstrations.

### Phase 7 — Project-scale and end-to-end tasks
**Deliverables:** T6–T8, persistent project graph, bot playtests, visual judge calibration, profiling/debug workflows.  
**Gate:** reliable multi-step feature completion and measurable human acceptance.

### Phase 8 — Productization
**Deliverables:** Windows client, model service/local runtime, Unity/Unreal bridge adapters, approvals, diff viewer, undo/rollback, logs, packaging and update process.  
**Gate:** model quality and reliability justify product integration; engine/legal/security review is complete.

### Phase 9 — Scale only where evidence justifies it
Consider larger proprietary pretraining, a trained multimodal model, learned engine simulator, or specialist MoE only when experiments identify a capability ceiling that smaller specialization/tooling cannot solve economically.

---

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

## 14. Step 1 — Start now

### Objective
Create a trustworthy definition of success and a small set of real game-engine tasks before training a model or building the Windows app.

### Step 1 deliverables
1. **Project charter:** target users, model-first scope, out-of-scope items, and operational definition of “best at game development.”
2. **Benchmark v0.1 task inventory:** the 30 logical T2/T3 task specs in Section 4.7, marked as draft until implemented and reviewed.
3. **Task schema:** required metadata, project inputs, path limits, engine/version pinning, time/tool budget, grading layers, and provenance.
4. **Evaluation contract:** exact build/test/probe outputs, thresholds, tolerances, and report format for each task.
5. **Baseline protocol:** equal harness and budget across the base model(s) and future specialist; repeated runs on a subset to estimate variance.
6. **Implementation decision log:** unresolved items, owner, evidence needed, decision, and date.

### Step 1 work sequence
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

### Step 1 acceptance gate
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
