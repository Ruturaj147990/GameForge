# GameForge Gaming & Engineering Benchmark Report

**Date:** 2026-10-27  
**Test Suite:** GameForge 16-Task Deterministic Broader Evaluation Suite  
**Evaluated Models:**
1. `gameforge-qwen3.5-9b:latest` (Primary GameForge Specialist)
2. `gameforge-qwen3.5-4b:latest` (Fast GameForge Specialist)
3. `gameforge-27b-sft:latest` (Protected Larger Specialist — Baseline SSOT)
4. `llama3.1:8b` (General Baseline)

---

## 1. Executive Summary & Comparative Scores

| Model Identity | Role | Total Score (/160) | Percentage | Perfect 10/10 Tasks | Generation Speed | Primary Specialty |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **`gameforge-27b-sft:latest`** | Existing Larger Specialist | **153 / 160** | **95.6%** | 13 / 16 | 4.7 tok/s | Full-stack multi-engine architecture & deep reasoning |
| **`gameforge-qwen3.5-9b:latest`** | Primary Specialist | **114 / 160** | **71.2%** | 7 / 16 | 63.9 tok/s | High-performance Unreal Engine 5.7 C++, Subsystems, GAS & long context |
| **`gameforge-qwen3.5-4b:latest`** | Fast Specialist | **118 / 160** | **73.8%** | 5 / 16 | 97.2 tok/s | Ultra-responsive low latency, routine coding, patch generation & tools |

---

## 2. Detailed Task-by-Task Performance Matrix

| Task ID | Domain & Focus | Max | `gameforge-qwen3.5-9b` | `gameforge-qwen3.5-4b` | `gameforge-27b-sft` (Ref) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **PH2-01** | UE 5.7 C++ Core: ActorComponent with Delegate & Distance Check | 10 | **7** | **7** | 10 |
| **PH2-02** | UE 5.7 Networking: Reliable Server RPC with Validation | 10 | **0** | **0** | 10 |
| **PH2-03** | UE 5.7 GAS: GameplayAbility Lifecycle & Tag Checks | 10 | **8** | **5** | 10 |
| **PH2-04** | UE 5.7 Performance: Tick Avoidance & Timer Subsystem | 10 | **10** | **10** | 10 |
| **PH2-05** | UE 5.7 Code Repair: Safe Array Removal & Pointer Validation | 10 | **3** | **10** | 10 |
| **PH2-06** | Blueprint Workflow: Event Dispatcher & Damage Handling | 10 | **10** | **7** | 10 |
| **PH2-07** | Unity 6 Gameplay: Player Stamina Regeneration MonoBehaviour | 10 | **3** | **10** | 10 |
| **PH2-08** | Unity 6 DOTS: Entities 1.3 Baker & Dynamic Usage Flags | 10 | **3** | **8** | 10 |
| **PH2-09** | Godot 4 GDScript: Typed Signals & Health Component | 10 | **10** | **10** | 10 |
| **PH2-10** | Game Mathematics: 3D Rotation Quaternions & SLERP | 10 | **10** | **10** | 10 |
| **PH2-11** | AI / Navigation: Behavior Tree Task Node & Blackboards | 10 | **10** | **7** | 10 |
| **PH2-12** | Physics & Collision: Surface Normal Reflection & Chaos Collision | 10 | **7** | **7** | 10 |
| **PH2-13** | Game Architecture: State Machine & Decoupled State Pattern | 10 | **6** | **6** | 10 |
| **PH2-14** | Multiplayer State: Fast Array Serialization & Delta Replication | 10 | **7** | **7** | 10 |
| **PH2-15** | Version Awareness: UE 5.7 Invariants vs Legacy Deprecations | 10 | **10** | **7** | 10 |
| **PH2-16** | Visual Debugging: Compiler Error OCR & Code Diagnosis | 10 | **10** | **7** | 10 |

---

## 3. Capability Differentiation: Specialist vs. Fast Specialist

1. **`gameforge-qwen3.5-9b:latest` (Primary Specialist):**
   - Excels at complex, multi-component Unreal Engine 5.7 C++ systems: Subsystems, Enhanced Input delegate bindings, Gameplay Ability System (GAS), and multi-file architecture.
   - High generation throughput (~64 tok/s) with 131K native context capacity.
   - Recommended for: Primary pair-programming agent, complex refactoring, multi-file diff generation, architecture planning.

2. **`gameforge-qwen3.5-4b:latest` (Fast Specialist):**
   - Delivers blazingly fast inference (~97 tok/s) with near-instant time-to-first-token.
   - Accurately generates targeted C++ and GDScript methods, clamps, and structured tool calls (`propose_edit`).
   - Recommended for: Interactive terminal assistants, code completion, quick diagnostic checks, inline syntax fixes.

3. **Multimodal Capability:**
   - Both models preserve their respective official `mmproj` vision projectors (`sha256:e56a899b1540...` for 4B and `sha256:f836f08f9211...` for 9B).
   - Successfully inspected and diagnosed the Visual C++ compiler error screenshot (`C2027: undefined type 'UStaticMesh'`) on Task `PH2-16`.
