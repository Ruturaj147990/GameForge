# GameForge — Engine Coverage & Capability Matrix

This matrix establishes the status of game engine knowledge, implementation, and verification across GameForge-Bench.

### Verification Level Taxonomy
- **`REAL_ENGINE_VERIFIED`**: Executed inside an installed, live engine editor/runtime; verified via headless or automation test harness.
- **`STATICALLY_VALIDATED`**: Source code compiles or passes linter/type checker/unit tests, but has not run in the target engine.
- **`AUTHORED`**: Native source code or configuration files exist in the repository; execution remains unperformed.
- **`SPECIFIED`**: Formally specified in task schemas and acceptance criteria; implementation pending.
- **`PLANNED`**: Identified in roadmap; specification pending.
- **`BLOCKED`**: Prerequisites (editor install, license, hardware feature) currently missing in host environment.

---

| Engine | Knowledge Domain | Target Capability | Implementation Status | Evaluation Method | Verification Level | Supported Versions | Authoritative References | Data Provenance | Dependencies & Blockers |
| :--- | :--- | :--- | :---: | :--- | :---: | :---: | :--- | :--- | :--- |
| **Universal** | Core Gameplay | Resource Invariants & Events | `REAL_ENGINE_VERIFIED` | Unit & Behavioral Probes | `REAL_ENGINE_VERIFIED` | N/A | IEEE / Game Programming Gems | GameForge Open Spec | None |
| **Universal** | Kinematics | Jump Arc & Buffer Timing | `REAL_ENGINE_VERIFIED` | Physics Simulation Probes | `REAL_ENGINE_VERIFIED` | N/A | Classical Mechanics | GameForge Open Spec | None |
| **Universal** | Interaction | One-Time Pickup Activation | `REAL_ENGINE_VERIFIED` | State Transition Probes | `REAL_ENGINE_VERIFIED` | N/A | Game Programming Patterns | GameForge Open Spec | None |
| **Universal** | UI Architecture | Event-Driven Resource HUD | `REAL_ENGINE_VERIFIED` | Widget Binding Probes | `REAL_ENGINE_VERIFIED` | N/A | MVVM / Observer Pattern | GameForge Open Spec | None |
| **Universal** | Combat | Projectile Impact & Owner Exclusion | `REAL_ENGINE_VERIFIED` | Collision Trace Probes | `REAL_ENGINE_VERIFIED` | N/A | Discrete Physics Collision | GameForge Open Spec | None |
| **Unreal Engine** | Character Kinematics | Third-person controller (`t2-001`) | `REAL_ENGINE_VERIFIED` | Headless UE5 Python Probe | `REAL_ENGINE_VERIFIED` | 5.7.4 | Epic Developer Docs (Character Movement) | Epic EULA compliant | None (`E:\UE\UE_5.7`) |
| **Unreal Engine** | Resource Systems | Health & damage component (`t2-004`) | `REAL_ENGINE_VERIFIED` | Headless UE5 C++ / Probes | `REAL_ENGINE_VERIFIED` | 5.7.4 | Epic Developer Docs (Gameplay Framework) | GameForge Native C++ | None (`E:\UE\UE_5.7`) |
| **Unreal Engine** | Interaction | Pickup collection actor (`t2-005`) | `REAL_ENGINE_VERIFIED` | Headless UE5 Overlap Probes | `REAL_ENGINE_VERIFIED` | 5.7.4 | Epic Developer Docs (Collision Filtering) | GameForge Native C++ | None (`E:\UE\UE_5.7`) |
| **Unreal Engine** | Composition | Native player composition (`t3-016`)| `REAL_ENGINE_VERIFIED` | Headless UE5 Scene Probes | `REAL_ENGINE_VERIFIED` | 5.7.4 | Epic Developer Docs (Actor Composition) | GameForge Native C++ | None (`E:\UE\UE_5.7`) |
| **Unreal Engine** | UI Systems | Health & stamina UMG HUD (`t3-017`)| `REAL_ENGINE_VERIFIED` | Headless UE5 Widget Probes | `REAL_ENGINE_VERIFIED` | 5.7.4 | Epic Developer Docs (UMG / Slate) | GameForge Native C++ | None (`E:\UE\UE_5.7`) |
| **Unreal Engine** | Combat / Physics | Projectile collision & damage (`t2-008`)| `REAL_ENGINE_VERIFIED` | Headless UE5 Collision Probes | `REAL_ENGINE_VERIFIED` | 5.7.4 | Epic Developer Docs (Projectiles / Hit) | GameForge Native C++ | None (`E:\UE\UE_5.7`) |
| **Unity** | Character Kinematics | CharacterController pilot (`t2-001`) | `AUTHORED` | Unity Test Framework | `BLOCKED` | 2022.3 LTS | Unity User Manual (CharacterController) | Unity EULA compliant | Unity Editor uninstalled |
| **Unity** | Resource Systems | HealthComponent pilot (`t2-004`) | `AUTHORED` | Unity Test Framework | `BLOCKED` | 2022.3 LTS | Unity Scripting API (MonoBehaviour) | GameForge Native C# | Unity Editor uninstalled |
| **Unity** | Interaction | PickupComponent & receiver (`t2-005`) | `AUTHORED` | Unity Test Framework | `BLOCKED` | 2022.3 LTS | Unity Scripting API (Collider.OnTrigger) | GameForge Native C# | Unity Editor uninstalled |
| **Unity** | Composition | Composed player character (`t3-016`) | `AUTHORED` | Unity Test Framework | `BLOCKED` | 2022.3 LTS | Unity Manual (Prefabs & Components) | GameForge Native C# | Unity Editor uninstalled |
| **Unity** | UI Systems | Health & stamina UI Toolkit (`t3-017`) | `AUTHORED` | Unity Test Framework | `BLOCKED` | 2022.3 LTS | Unity Manual (UI Toolkit / uGUI) | GameForge Native C# | Unity Editor uninstalled |
| **Unity** | Combat / Physics | Projectile collision script (`t2-008`)| `AUTHORED` | Unity Test Framework | `BLOCKED` | 2022.3 LTS | Unity Scripting API (Rigidbody / Hit) | GameForge Native C# | Unity Editor uninstalled |
| **Godot** | Character Kinematics | CharacterBody3D controller | `SPECIFIED` | GUT (Godot Unit Testing) | `BLOCKED` | 4.x | Godot Engine Docs (CharacterBody3D) | MIT License | Godot Engine uninstalled |
| **Godot** | Resource Systems | HealthNode / StaminaNode | `SPECIFIED` | GUT | `BLOCKED` | 4.x | Godot Engine Docs (Signals & Nodes) | MIT License | Godot Engine uninstalled |
| **Godot** | Interaction | Area3D pickup trigger | `SPECIFIED` | GUT | `BLOCKED` | 4.x | Godot Engine Docs (Area3D Collision) | MIT License | Godot Engine uninstalled |
| **Godot** | UI Systems | Control / ProgressBar HUD | `SPECIFIED` | GUT | `BLOCKED` | 4.x | Godot Engine Docs (UI / Controls) | MIT License | Godot Engine uninstalled |
| **Godot** | Combat / Physics | RigidBody3D / Area3D projectile | `SPECIFIED` | GUT | `BLOCKED` | 4.x | Godot Engine Docs (Physics & Collision) | MIT License | Godot Engine uninstalled |
| **Custom / C++** | Rendering & Engine | Minimal game loop & frame pacing | `PLANNED` | Custom Headless Harness | `PLANNED` | C++20 | ISO/IEC 14882 | Proprietary / Open | Toolchain ready |
