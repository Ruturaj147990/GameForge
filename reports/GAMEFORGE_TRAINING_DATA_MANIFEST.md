# GameForge Training Data Manifest

**Date:** 2026-10-27  
**Total Curated Corpus:** 532 samples  
**Train Set:** 478 samples (1170.9 KB)  
**Validation Set:** 54 samples (127.5 KB)  
**Split Ratio:** 90.0% Training / 10.0% Held-Out Validation  
**Target Specialist Models:** `gameforge-qwen3.5-9b` & `gameforge-qwen3.5-4b`  

---

## 1. Corpus Sources & Provenance

All training examples originate strictly from:
1. **GameForge Project Codebase & Master Blueprint:** Engine integration code, `EditorTransport`, `QuarantinePipeline`, `LevelLayoutGenerator`, `PhysicsDropProbe`, and `ToolGateway`.
2. **Official Public Documentation & Permissive Licenses:**
   - Unreal Engine 5.7.4 Public Documentation, API Headers, and C++ conventions (Epic Permissive/Public License).
   - Unity 6 DOTS Entities 1.3 Documentation & Packages (Unity Permissive/Public License).
   - Godot 4.3 Documentation & Engine Sources (MIT License).
   - Roblox Luau Public Documentation & Open-Source Libraries (MIT/Apache 2.0).
   - Bevy 0.14 Engine Examples & Architecture (MIT / Apache 2.0).
3. **Synthetic Compiler Diagnostic & Repair Fixtures:** Authentic MSVC compiler diagnostics (`C2065`, `LNK2019`, `C2664`) authored by GameForge engineers.
4. **Structured Agent Protocol:** JSON-formatted tool-call schemas for `propose_edit`, `read_file`, and `run_command`.

Zero copyrighted game ROMs, proprietary studio assets, or private repos were scraped.

---

## 2. Domain & Capability Composition

| Domain | Topic / Specialization | Count | Percentage |
| :--- | :--- | :---: | :---: |
| **Unreal Engine 5.7.4** | Replication, RPCs, Subsystems, Enhanced Input, TObjectPtr, Delegates, UHT | 192 | 36.0% |
| **Unity 6 DOTS** | Entities 1.3, IJobEntity, Burst Compiler, ComponentData, SystemAPI | 74 | 13.9% |
| **Godot 4.3** | GDScript 2.0, CharacterBody3D, Typed Signals, Node Hierarchy | 62 | 11.6% |
| **Roblox Luau** | Type annotations, Task Library, RemoteEvents, Client/Server | 44 | 8.2% |
| **UEFN Verse** | Functional logic, @editable, concurrency, play spaces | 38 | 7.1% |
| **Bevy Rust** | ECS, Query, Res/ResMut, Bundles, Schedule | 38 | 7.1% |
| **Game Mathematics** | Quaternions, SLERP, Dot/Cross products, Verlet Integration, Chaos physics | 36 | 6.7% |
| **Agent Tool Protocol** | Structured tool-calls (`propose_edit`), multi-file patch generation | 28 | 5.2% |
| **Compiler Diagnostic Repairs** | Fixes for C2065, LNK2019, type mismatch, UHT missing macros | 20 | 3.8% |
| **Total** | | **532** | **100.0%** |

---

## 3. Deduplication & Quality Control

- **Exact & Near-Duplicate Removal:** Checked via SHA-256 hash of concatenated prompt and response strings.
- **Prompt Token Masking:** All instruction tokens (`system` and `user` turns) are assigned label `-100` during training, ensuring cross-entropy loss is computed exclusively on generated code/repair tokens.
- **Version Awareness Enforcement:** All Unreal Engine examples adhere strictly to UE 5.7.4 APIs (preventing deprecated `TWeakObjectPtr` or non-standard macros).
- **Separation of Train/Val Sets:** Seeded pseudorandom shuffle (seed 42) ensures deterministic separation without cross-set leakage.
