# GAMEFORGE 27B — AUTHORITATIVE 50-TASK BENCHMARK SUITE

**Date:** 2026-10-23  
**Benchmark Version:** 1.0.0 (Dedicated 27B Engineering Evaluation)  
**Governing Standard:** Section 5 ("Establish a proper GameForge benchmark")  

---

## 1. Benchmark Specification & Domain Allocation

The benchmark contains **50 independently scored tasks** evaluated under identical inference settings (Temperature $0.2$, Top-P $0.9$, Context Length 4096):

| Domain / Engine | Task Count | Share (%) | Key Covered Topics |
| :--- | :--- | :--- | :--- |
| **Unreal Engine 5.7** | **30 Tasks** | **60.0%** | Reflection (`UCLASS`/`UPROPERTY`), Replication (`GetLifetimeReplicatedProps`), RPC security, `TObjectPtr`/`FGCObject` GC, Gameplay Ability System (GAS), Enhanced Input, Subsystems, AI/BehaviorTrees, Collision/Traces, Niagara, Anim Montages, World Partition, Build.cs, FastArraySerializer, Smart Pointers, CI Packaging. |
| **Unity C#** | **4 Tasks** | **8.0%** | Job System & Burst compilation, ScriptableObject event channels, FixedUpdate physics interpolation, UniTask async loading. |
| **Godot 4 GDScript** | **4 Tasks** | **8.0%** | `CharacterBody3D` controller, typed signals & callables, `@rpc` reliable networking, Scene node lifecycle order. |
| **Roblox Luau** | **3 Tasks** | **6.0%** | Server-authoritative `RemoteEvent` security, task scheduler budget (`task.spawn`/`task.defer`), ProfileService session locking. |
| **UEFN Verse** | **3 Tasks** | **6.0%** | Concurrency primitives (`race`/`sync`), spatial vector lerping, custom `creative_device` event triggers. |
| **Bevy Rust ECS** | **3 Tasks** | **6.0%** | Parallel queries `Query<(&mut Position, &Velocity)>`, `EventReader`/`EventWriter`, `Res<T>` vs `ResMut<T>` scheduling. |
| **Game Mathematics & Architecture**| **3 Tasks** | **6.0%** | Quaternion/vector angular deltas, Spatial Hashing vs BVH complexity, tick-based snapshot interpolation buffers. |
| **Total** | **50 Tasks** | **100.0%** | Comprehensive cross-engine game development coverage |

---

## 2. Objective Scoring Rubrics

Each task carries a maximum score of **10 points** (total 500 points possible).
Scoring is determined by automated AST / keyword and invariant match:
- Mandatory Macro / Class Declaration: 2.0 pts
- Method Signature & Type Accuracy: 2.5 pts
- Algorithmic / Architectural Correctness: 3.5 pts
- Security / Lifecycle Invariants (e.g. Server validation, clamping): 2.0 pts
- Negative Points for Dangerous Anti-Patterns (e.g., Client trust, raw pointers in UCLASS): -2.0 pts

All benchmark specifications are persisted at `E:\GameForge\reports\gameforge-27b\baseline_benchmark.json`.
