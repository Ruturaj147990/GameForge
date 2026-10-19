# GameForge — Game-Engine Intelligence Scope & Taxonomy

## Strategic Purpose

GameForge is being constructed as the evaluation and training foundation for a world-leading game-development AI.
A core architectural principle governs this project:

> **Execution Scope is Unreal-First; Intelligence Scope is Broad Game Development Across Engines.**

The future AI must not be an Unreal-only model. It must possess deep, nuanced comprehension of general game development principles, native idioms for major commercial and open-source engines (Unreal, Unity, Godot, and custom engines), and the technical capability to reason across engine boundaries.

---

## Three-Layer Knowledge Architecture

### Layer A — Engine-Independent Game-Development Knowledge

Core concepts and mathematical/architectural foundations that apply universally across game engines:

1. **Gameplay Architecture & Design Patterns:**
   - Component-based architecture (Entity-Component-System vs Actor-Component patterns).
   - Event-driven programming, observer pattern, delegate decoupling, and reentrancy protection.
   - Resource invariants (monotonicity, clamped capacities, discrete state transitions).
2. **Movement & Controller Mathematics:**
   - Kinematics equations: acceleration, velocity, drag, friction, braking deceleration.
   - Jump mechanics: initial velocity, gravity scaling, jump apex calculations, coyote time, and jump buffering.
   - Numerical integration: Euler, Verlet, fixed vs variable delta-time implications.
3. **Collision & Physics Fundamentals:**
   - Broadphase vs narrowphase collision detection.
   - Continuous collision detection (CCD) vs discrete sweep tests to prevent tunneling.
   - Collision filtering matrices, collision channels, response types (Ignore, Overlap, Block).
4. **State Machines & Behavior Modeling:**
   - Finite State Machines (FSM), Hierarchical State Machines (HFSM), and Behavior Trees.
   - State transition invariants, entry/exit actions, and tick isolation.
5. **Character Rigging, Animation & Spatial Reasoning:**
   - Coordinate frames (left-handed Z-up vs right-handed Y-up), Euler angles vs quaternions, gimbal lock prevention.
   - Skeletal hierarchies, bone transforms, forward and inverse kinematics (IK).
   - Animation blending, blend trees, state machines, root motion vs in-place translation.
6. **Rendering Fundamentals & Shading:**
   - Forward vs deferred rendering, visibility culling (frustum, occlusion).
   - Shader pipeline: vertex, pixel/fragment, compute stages, PBR material models.
7. **Multiplayer, Networking & Synchronization:**
   - Client-server authoritative topology vs peer-to-peer.
   - Client-side prediction, server reconciliation, interpolation, lag compensation.
   - Deterministic lockstep vs snapshot/delta replication.
8. **UI Architecture & Presentation:**
   - Model-View-Controller (MVC) and Model-View-ViewModel (MVVM) in games.
   - Data-binding lifecycles, event dispatch vs per-frame polling, widget memory management.
9. **Profiling, Performance & Debugging:**
   - Frame budget allocation (CPU game thread, render thread, GPU raster/shading).
   - Memory allocation patterns, heap fragmentation, garbage collection spikes, cache-friendly data layouts.

---

### Layer B — Engine-Specific Technical Knowledge

Specialized idioms, APIs, lifecycle rules, and tooling conventions:

#### 1. Unreal Engine
- **Languages & Scripting:** Modern C++ (C++20), Blueprints visual scripting, Python for editor automation.
- **Object Hierarchy:** `UObject`, `AActor`, `UActorComponent`, `APawn`, `ACharacter`, `APlayerController`, `AGameModeBase`.
- **Gameplay Framework:** Gameplay Ability System (GAS), Enhanced Input Subsystem, Character Movement Component (`UCharacterMovementComponent`).
- **UI & Presentation:** Unreal Motion Graphics (`UMG`), Slate C++ framework, widget blueprints, delegate bindings.
- **Animation & Visuals:** Animation Blueprints, State Machines, Control Rig, Niagara visual effects, Lumen, Nanite.
- **Build & Packaging:** UnrealBuildTool (UBT), UnrealHeaderTool (UHT), AutomationTool (RunUAT), Modular Rules (`.Build.cs`, `.Target.cs`), commandlets.
- **Memory & Garbage Collection:** Reference counting, reflection macros (`UPROPERTY`, `UFUNCTION`, `UCLASS`), GC clusters, soft object paths (`TSoftObjectPtr`).

#### 2. Unity
- **Languages & Scripting:** C# (.NET / Mono), assembly definitions (`.asmdef`), unsafe pointers.
- **Object Hierarchy:** `GameObject`, `MonoBehaviour`, `Component`, `ScriptableObject`, Prefabs and Prefab Variants.
- **Engine Systems:** Input System (new) vs Input Manager, Rigidbody / PhysX, CharacterController, Mecanim Animator and Blend Trees.
- **UI Systems:** UI Toolkit (UIElements / USS), Unity UI (uGUI), Canvas scalar and batching.
- **Rendering Pipelines:** Universal Render Pipeline (URP), High Definition Render Pipeline (HDRP), Built-in Pipeline, Shader Graph.
- **Build & Profiling:** Player Settings, BuildPipeline, Unity Memory Profiler, Deep Profiling.

#### 3. Godot
- **Languages & Scripting:** GDScript, C# (.NET), GDExtension (C/C++).
- **Scene Tree & Object Model:** `Object`, `RefCounted`, `Node`, `Node2D`, `Node3D`, `Resource`, `PackedScene`.
- **Engine Systems:** Signals, Groups, `CharacterBody3D`, `RigidBody3D`, `CollisionShape3D`, AnimationPlayer, AnimationTree.
- **UI Systems:** Control nodes, Themes, Containers, anchor offsets.
- **Rendering & Shading:** Godot Shading Language (GLSL-derived), Forward+ vs Mobile vs Compatibility renderers.

#### 4. Custom & Emerging Engines
- Project-specific headers, custom game loops, data-driven entity stores, explicit hardware abstractions (Vulkan, DirectX 12, Metal).

---

### Layer C — Cross-Engine Engineering

Technical proficiencies enabling the AI to operate across different game ecosystems:

1. **System Translation & Porting:**
   - Translating an Unreal `UHealthComponent` with dynamic multicast delegates to a Unity `MonoBehaviour` using `System.Action` / `UnityEvent`, or Godot node with `[Signal]`.
   - Adapting Unreal character movement parameters (cm/s, cm/s²) to Unity/Godot SI units (m/s, m/s²).
2. **Coordinate & Transform Mapping:**
   - Unreal (Left-Handed, Z-Up: X-Forward, Y-Right, Z-Up) $\leftrightarrow$ Unity (Left-Handed, Y-Up: X-Right, Y-Up, Z-Forward) $\leftrightarrow$ Godot (Right-Handed, Y-Up: X-Right, Y-Up, Z-Backwards).
3. **Engine-Specific Trap Identification:**
   - Unreal: Delegate shadowing (`UActorComponent::bIsActive`), GC collection of unreferenced `UObject` pointers, spawning actors in constructors.
   - Unity: Garbage generation from string concatenation or boxing in `Update()`, `GetComponent` calls in tight loops, physics queries without layer masks.
   - Godot: Calling `queue_free()` during active iteration, forgetting `super._process(delta)`.
4. **Testing & Verification Translation:**
   - Defining equivalent test approaches across engines: Unreal Automation Controller vs Unity Test Runner (NUnit) vs Godot GUT framework.
