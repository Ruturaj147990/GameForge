# Independent Regression Test Report (15 Tasks)

**Subject:** Live Multi-Engine Engineering Regression Suite  
**Evaluated Models:** `gameforge-27b` vs. `qwen3.8:27b-q4_K_M`  
**Execution Environment:** Ollama v0.15.6 / Vulkan Backend (AMD Radeon RX 7700 XT 12GB VRAM)  
**Configuration:** `temperature: 0.2`, `top_p: 0.9`, `num_predict: 140`, `think: false` (Direct streaming)  
**Date:** October 23, 2026  

---

## 1. Executive Summary

An independently authored 15-task regression suite was executed directly against both the newly engineered **`gameforge-27b`** and the foundation baseline **`qwen3.8:27b-q4_K_M`** under strictly identical generation conditions.

**Overall Results:**
- **`gameforge-27b`**: **70 / 150 points (46.7%)** | Average Throughput: **6.0 tokens/sec** | Mean TTFT: **1.03s**
- **`qwen3.8:27b-q4_K_M`**: **74 / 150 points (49.3%)** | Average Throughput: **5.9 tokens/sec** | Mean TTFT: **0.91s**

---

## 2. Per-Task Score Breakdown

| Task ID | Engineering Domain | Max Points | `gameforge-27b` | `qwen3.8:27b-q4_K_M` | Notable Observation |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **REG-01** | Unreal C++ Replication & Authority | 10 | 2 | 2 | Both generated `UCLASS` and `GENERATED_BODY()`; token budget capped before `GetLifetimeReplicatedProps`. |
| **REG-02** | Unreal RPC Validation & Security | 10 | **1** | **0** | `gameforge-27b` declared `UFUNCTION(Server, Reliable, WithValidation)`; base model hallucinated signature. |
| **REG-03** | Unreal Memory & TObjectPtr | 10 | 0 | 0 | Both outputted explanation before declaring member variable under concise token limit. |
| **REG-04** | Unreal Delegates & Events | 10 | 3 | **6** | `qwen3.8` emitted declaration and broadcast syntax; `gameforge-27b` emitted declaration only. |
| **REG-05** | Gameplay Ability System (GAS) | 10 | 4 | 4 | Both generated `ATTRIBUTE_ACCESSORS` macro block correctly. |
| **REG-06** | Collision & Sweep LineTrace | 10 | **8** | **8** | Both models generated accurate `LineTraceSingleByChannel` with `FCollisionQueryParams` and ignored actors. |
| **REG-07** | AI & Behavior Tree Task | 10 | **7** | **7** | Both models correctly implemented `UBTTaskNode::ExecuteTask` and returned `EBTNodeResult::Succeeded`. |
| **REG-08** | Network Optimization (`COND_OwnerOnly`) | 10 | **10** | **10** | **Perfect 10/10 on both models:** `DOREPLIFETIME_CONDITION(..., COND_OwnerOnly)` cleanly implemented. |
| **REG-09** | Enhanced Input Action Binding | 10 | 0 | 4 | `qwen3.8` captured `UEnhancedInputComponent::BindAction`; `gameforge-27b` truncated before bind call. |
| **REG-10** | Performance & Tick Avoidance | 10 | **6** | **6** | Both cleanly disabled `PrimaryActorTick.bCanEverTick = false` and used `GetWorldTimerManager()`. |
| **REG-11** | Godot 4 GDScript 2.0 Character | 10 | **7** | **7** | Modern Godot 4 `CharacterBody3D`, `velocity`, and `move_and_slide()` generated without deprecated `yield()`. |
| **REG-12** | Unity 6 DOTS / ECS Burst Job | 10 | **10** | **10** | **Perfect 10/10 on both models:** `IJobEntity` with `[BurstCompile]` and `ref Health` correctly implemented. |
| **REG-13** | UEFN Verse Concurrency | 10 | **2** | **0** | `gameforge-27b` formatted Verse `race:` block; base model emitted invalid non-Verse syntax. |
| **REG-14** | Game Mathematics - Quaternions | 10 | **4** | **4** | Both correctly explained gimbal lock and dot product interpolation. |
| **REG-15** | Game Mathematics - PID Controller | 10 | **6** | **6** | Both generated clean proportional, integral, and derivative terms with delta time scaling. |
| **TOTAL** | **Multi-Engine Engineering Suite** | **150** | **70 (46.7%)** | **74 (49.3%)** | **Both models validated as capable 27B engineering models.** |

---

## 3. Engineering Analysis

1. **Equivalence in Low-Level Logic:** Both models demonstrated strong capabilities in modern game architectures (perfect 10/10 in Unity DOTS `IJobEntity` and Unreal Network Optimization `COND_OwnerOnly`).
2. **UEFN Verse Specialization:** `gameforge-27b` successfully produced the Verse concurrency `race:` construct, whereas the baseline foundation model failed and produced 0 points.
3. **Throughput Parity:** Both models operated at **5.9 – 6.0 tokens/sec** with sub-1.1s time-to-first-token under active GPU Vulkan offload.
4. **Token Truncation Impact:** With `num_predict: 140` and `think: false`, several extensive C++ class implementations (e.g. REG-01, REG-03, REG-09) were partially truncated before completing all trailing boilerplate, accounting for the ~47–49% score bracket on strict substring matching.
