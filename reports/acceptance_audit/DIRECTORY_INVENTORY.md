# GameForge 1.0 — Comprehensive Host Directory & Project Inventory

**Date:** 2026-11-02T08:08:00Z  
**Auditor:** Antigravity Autonomous Inspector  
**Host:** Windows 11 Pro, AMD Ryzen 5 7600X, 32GB DDR5, Radeon RX 7700 XT 12GB VRAM  

---

## 1. Inventory Summary Across Partitions

| Directory Path | Role / Content | File Count | Size (MB) | Project Roots | Consolidation Action |
|---|---|---|---|---|---|
| `E:\gameforge_step1` | Source code repository (Git checkout `master`) | ~1,200 | ~35 MB | 0 | Preserved as primary canonical source repository. |
| `E:\GameForge\projects` | Developer & benchmark project storage | ~30,000 | ~115,000 MB | 16 | Consolidated: benchmarked CS_Regeneration & Platformer_Diversity. Redundant test copies tagged for safe archival. |
| `E:\GameForge\models\ollama` | Local quantized GGUF weights & Ollama blobs | ~15 | ~52,000 MB | 0 | Untouched per non-negotiable rule (contains 9B, 4B, 27B-SFT, 8B). |
| `E:\GameForge\artifacts` | Fine-tuned weights, GGUFs, and modelfiles | ~35 | ~45,000 MB | 0 | Untouched per non-negotiable rule. |
| `E:\GameForge\datasets` | Model evaluation & flywheel training sets | ~10 | ~850 MB | 0 | Preserved as training lineage. |
| `E:\GameForge\validation` | P0–P11 testbed projects & scenario environments | ~45,000 | ~180,000 MB | 35 | Preserved as protected test harness / historical testbeds (e.g. `P3_kittest_20261031`). |
| `C:\Users\limbk\Documents\GameForge` | Default user workspace | ~50 | ~1.5 MB | 0 | Reset and verified as Location 1 (sessions/approvals only). |
| `E:\UE\UE_5.7` | Unreal Engine 5.7.4 installation | ~180,000 | ~120,000 MB | 0 | Discovered automatically via Epic manifest; untouched. |

---

## 2. Detailed Project Inventory in `E:\GameForge\projects`

| Project Folder | .uproject | GDS Present | Packaged Exe | Size (MB) | Purpose / Status |
|---|---|---|---|---|---|
| `CS_Regeneration` | `Yes` | `Yes` (gds/1.1) | `Ready` | 7,420 MB | **Active Benchmark:** Fresh CounterStrikeLite regeneration (first-person, rooms layout, combat bots, 120s timer). |
| `Platformer_Diversity` | `Yes` | `Yes` (gds/1.1) | `Ready` | 7,150 MB | **Active Benchmark:** Fresh 3D Platformer course (third-person, course platforms, checkpoints, relics). |
| `CounterStrikeLite` | `Yes` | `Yes` (gds/1.1) | `Yes` (892 MB) | 7,569 MB | Previous E2E acceptance test build. |
| `AuditArena` | `Yes` | `No` (recipe) | `Yes` | 7,183 MB | Historical test project from Phase 0/1 audit. |
| `AuditCards` | `Yes` | `No` (recipe) | `Yes` | 7,180 MB | Historical test project from Phase 5 card battler audit. |
| `AuditPlatformer` | `Yes` | `No` (recipe) | `Yes` | 7,185 MB | Historical test project from Phase 0 platformer audit. |
| `AuditWorld` | `Yes` | `No` (recipe) | `Yes` | 7,327 MB | Historical test project from Phase 10 world partition audit. |
| `CubeClicker` | `Yes` | `No` (recipe) | `Yes` | 7,058 MB | Legacy UI recipe test project. |
| `FourInARow` | `Yes` | `No` (recipe) | `Yes` | 7,055 MB | Legacy grid board test project. |
| `GFArenaCombat` | `Yes` | `No` (recipe) | `Yes` | 7,118 MB | Phase 1 legacy recipe verification project. |
| `GFCardBattler` | `Yes` | `No` (recipe) | `Yes` | 7,110 MB | Phase 5 kit test project. |
| `GFPlatformer` | `Yes` | `No` (recipe) | `Yes` | 7,159 MB | Phase 1 platformer verification project. |
| `GFProceduralWorld` | `Yes` | `No` (recipe) | `Yes` | 7,133 MB | Phase 1 procedural world verification project. |
| `ide_e2e` | `No` | `No` | `No` | 7,050 MB | Stale intermediate testbed from P4 testing. |
| `Platformer` | `Yes` | `Yes` (gds/1) | `Yes` | 7,259 MB | P1 GDS engine gate project. |
| `TicTacToe` | `Yes` | `Yes` (gds/1) | `Yes` | 7,269 MB | P1 GDS engine gate project. |
| `WhackAMole` | `Yes` | `No` (recipe) | `Yes` | 7,064 MB | Legacy recipe test project. |

---

## 3. Findings & Consolidation Actions

1. **Self-Contained Compliance:** All modern projects (`CS_Regeneration`, `Platformer_Diversity`, `CounterStrikeLite`) strictly contain their `.uproject`, `Source/`, `Config/`, `Plugins/GameForge`, and `GameForge/design/game.gds.json` within their root folder.
2. **Intermediate Bloat:** The large file sizes (~7 GB per project) are overwhelmingly driven by `Intermediate/Build/Win64/UnrealEditor/Development/` object files (`.obj`, `.pch`). When packaged, the standalone distributable game is only ~400–890 MB.
3. **Location 1 Purity:** Confirmed that `C:\Users\limbk\Documents\GameForge\.gameforge` and `E:\gameforge_step1\.gameforge` contain zero C++ source files, zero `.uproject` files, and zero compiled binaries.
