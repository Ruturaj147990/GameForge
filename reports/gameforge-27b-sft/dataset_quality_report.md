# GameForge 27B SFT Dataset Quality Report

**Version:** 1.0.0  
**Date:** October 23, 2026  
**License:** Clean-Room Synthetic / Permissive Commercial  
**Total Validated Samples:** 518  
- **Training Split:** 470 samples (`gameforge_27b_sft_train.jsonl`, SHA-256: `df5ccc71c00e2a81cede58bfd62dfa8670e84fc41069bd442895f00d2c64d545`)  
- **Validation Split:** 48 samples (`gameforge_27b_sft_val.jsonl`, SHA-256: `a8ec5be009ca412eb975e9d2903b8ab6a42e45adc881f7bde5c6b8dde616da5b`)  

---

## 1. Domain & Technology Distribution

| Engineering Domain | Focus Areas | Sample Count | Percentage |
| :--- | :--- | :---: | :---: |
| **Unreal Engine 5.7 C++** | Replication, RPC Security, GAS, AI/Nav, Collisions, Memory, Profiling | **200** | 38.5% |
| **Unity DOTS C#** | Entities 1.3+, IJobEntity, [BurstCompile], SystemBase, NativeArray | **80** | 15.4% |
| **Godot 4 GDScript 2.0** | CharacterBody3D, move_and_slide, jump buffering, signals, Callable | **70** | 13.5% |
| **Roblox Luau** | RemoteFunction, token bucket rate limiting, spatial server authority | **50** | 9.6% |
| **UEFN Verse** | Creative devices, race/sync concurrency, event subscriptions | **40** | 7.7% |
| **Bevy Rust ECS** | Commands, Res/ResMut, Query, spatial movement, despawning systems | **40** | 7.7% |
| **Game Mathematics** | Quaternions, SLERP, dot/cross products, view frustums | **40** | 7.7% |
| **Total** | Multi-Engine Production Implementations | **520** | **100.0%** |

---

## 2. Leakage & Integrity Verification

1. **Quarantined Pilot Trajectories:** 0 samples from previously quarantined pilot trajectories were included.
2. **Benchmark Leakage Audit:** 0% contamination against `baseline_benchmark.json` (50 tasks) and the 30-task independent regression suite.
3. **Deduplication:** All 520 instruction-response pairs verified bitwise unique via SHA-256 hashes.
