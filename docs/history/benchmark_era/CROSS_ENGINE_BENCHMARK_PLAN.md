# GameForge Cross-Engine Benchmark Plan
## Architecture, Task Taxonomy, Evaluation Methodology, and Extensibility

**Document Version:** 1.0.0  
**Status:** Approved Architectural Baseline  
**Scope:** Multi-Engine AI Evaluation Framework (Unreal Engine, Unity, Godot, Engine-Neutral)

---

## 1. Executive Summary and Motivation

GameForge is designed to evaluate and train state-of-the-art AI systems for professional game development. While Unreal Engine is our primary real-engine execution environment, the intended intelligence scope spans general game engineering and multiple target runtimes.

Evaluating a game-development AI solely through single-engine compilation introduces severe blind spots:
1. **Compilation Bias:** Code that compiles frequently exhibits silent runtime defects (event double-firing, race conditions, memory leaks, misconfigured collision channels).
2. **Engine Overfitting:** An AI trained only on one engine's syntax often fails at fundamental systems design, architectural decoupling, and cross-engine portability.
3. **Synthetic Validation Fallacy:** Pretending an unavailable engine (e.g., Unity or Godot) has verified runtime behavior without genuine engine execution invalidates scientific benchmarks.

This document formalizes the evaluation taxonomy, ground-truth methodologies, held-out integrity rules, and multi-engine progression path.

---

## 2. Five-Class Task Taxonomy

To rigorously test game-development intelligence, all GameForge tasks are classified into five distinct operational classes:

```
+-----------------------------------------------------------------------------+
|                      GameForge Benchmark Task Taxonomy                       |
+-----------------------------------------------------------------------------+
| Class A: Engine-Independent Game-Development Reasoning                     |
|          (Invariants, state machines, math, kinematics, decoupled design)   |
+-----------------------------------------------------------------------------+
| Class B: Engine-Specific Technical Knowledge                                |
|          (API mastery, lifecycle, memory models, object hierarchies)        |
+-----------------------------------------------------------------------------+
| Class C: Engine-Specific Implementation and Repair                          |
|          (Native code authoring, defect repair, asset structuring)          |
+-----------------------------------------------------------------------------+
| Class D: Cross-Engine Translation                                           |
|          (Translating requirements/code between UE, Unity, Godot)           |
+-----------------------------------------------------------------------------+
| Class E: Real-Engine Execution and Behavioral Verification                  |
|          (Automated headless/PIE execution, collision probes, asset tests)  |
+-----------------------------------------------------------------------------+
```

### Class A — Engine-Independent Game-Development Reasoning
- **Focus:** Foundational game architecture, mathematics, invariants, event semantics, and design contracts.
- **Evaluation Mechanism:** Deterministic rubric matching, formal schema validation, invariant verification, and expert grading.
- **Engine Execution Required:** No.
- **Examples:**
  - Defining temporal invariants of invulnerability frames (i-frames).
  - Specifying event-driven decoupling between gameplay components and presentation HUDs.
  - Formulating kinematics formulas and collision response tolerances.

### Class B — Engine-Specific Technical Knowledge
- **Focus:** Idiomatic engine APIs, configuration schemas, memory ownership conventions, and version-specific constraints.
- **Evaluation Mechanism:** Static code analysis, AST inspection, API surface matching against official registries.
- **Engine Execution Required:** No.
- **Examples:**
  - Unreal: `TWeakObjectPtr` lifecycle, Enhanced Input mapping contexts, UMG slate tree invalidation.
  - Unity: `MonoBehaviour` execution order, ScriptableObject data architecture, SerializedProperty drawer mechanics.
  - Godot: Node scene tree ownership, GDScript `@export` signals, custom GDExtension bindings.

### Class C — Engine-Specific Implementation and Repair
- **Focus:** Authoring compilable code, fixing controlled semantic bugs, implementing missing functions, or restructuring project files.
- **Evaluation Mechanism:** Native toolchain compilation (UBT, MSBuild/dotnet, SCons), static analyzers, linter checks.
- **Engine Execution Required:** Optional (build toolchain required; full engine runtime optional).
- **Examples:**
  - Implementing a delegate-based stamina consumption component in Unreal C++.
  - Repairing a memory leak in a Unity event listener on `OnDestroy`.
  - Authoring a Godot C# character controller with signal emission.

### Class D — Cross-Engine Translation
- **Focus:** Porting systems between game engines while maintaining behavioral parity and adopting native idioms.
- **Evaluation Mechanism:** Dual-target validation, comparative behavioral probes, architectural translation grading.
- **Engine Execution Required:** Recommended where both engines are installed; otherwise evaluated via Class C on source and Class B on target.
- **Examples:**
  - Porting an Unreal C++ `UHealthComponent` to a Unity C# `HealthComponent`.
  - Porting a Godot character controller to an Unreal Third-Person Character.
  - Translating coordinate system differences (e.g., Unreal Z-up Left-Handed vs Unity Y-up Left-Handed vs Godot Y-up Right-Handed).

### Class E — Real-Engine Execution
- **Focus:** End-to-end runtime behavior, physical collision, temporal dynamics, UI layout rendering, and asset lifecycle.
- **Evaluation Mechanism:** Headless / PIE automated test harnesses, simulated agent probes, frame-by-frame measurement outputs (`probe_measurements.json`).
- **Engine Execution Required:** **Strictly Mandatory.**
- **Rules:** If the target engine binary is not installed or executable on the host, the task status MUST be `BLOCKED` or `HARNESS_INVALID`. Synthetic successes are strictly forbidden.

---

## 3. Evaluation Methodology Across Engines

| Engine | Toolchain / Runner | Current Step 4 Status | Verification Level | Next Step |
|---|---|---|---|---|
| **Unreal Engine 5.7** | UnrealEditor-Cmd (`-ExecutePythonScript`, PIE automation) | **REAL_ENGINE_VERIFIED** | Class E (Real Runtime Execution) | Expand combat, AI, and replication benchmarks |
| **Unity 2022/6** | Unity Editor batchmode (`-runTests`, `-executeMethod`) | **AUTHORED** (Code available, runner uninstalled) | Class C (Authored / Statically Validated) | Install Unity Editor in isolated test runner |
| **Godot 4.x** | Godot binary headless (`--headless`, `--script`) | **SPECIFIED** (Taxonomy defined, tasks planned) | Class B (Specified) | Author C#/GDScript templates & headless harness |
| **Engine-Neutral** | Python / pytest, JSON schema, AST analyzers | **REAL_ENGINE_VERIFIED** | Class A (Deterministic Verification) | Add multi-file architectural reasoning tasks |

---

## 4. Contamination Risks and Held-Out Benchmarks

To guarantee that future evaluated models have not memorized solutions:
1. **Public vs. Protected Separation:**
   - Public task definitions (`pilot_tasks/`) contain problem briefs, interfaces, and public test criteria.
   - Protected test suites (`graders/protected/`) contain secret probe seeds, randomized timing variations, and hidden assertions that are injected strictly during isolated evaluation runs.
2. **Controlled Defect Injections:**
   - Evaluation pipelines include negative test cases (controlled defects). A grader that accepts defective code is invalidated.
3. **Dynamic Parameter Perturbation:**
   - Invariants (e.g., initial health, projectile velocity, invulnerability windows) are tested across randomized valid domains to reject hardcoded responses.

---

## 5. Roadmap: From Unreal-First to Universal Engine Intelligence

- **Step 1–3:** Established foundation, character controller, health/damage temporal invariants, pickup collection, and player composition in Unreal Engine 5.7.
- **Step 4 (Current):** Established universal intelligence scope, engine-scope schema, UMG HUD widget, projectile collision physics, and engine-neutral reasoning tasks.
- **Step 5 (Next):** Complete character combat integration (weapon firing, projectile spawning from socket, HUD response in closed loop).
- **Step 6 (Multi-Engine Integration):** Deploy headless Unity and Godot execution harnesses in isolated test agents to advance Class E coverage across all three major engines.
