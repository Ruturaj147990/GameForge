# GameForge 1.0.0 Release Notes

**Release Date:** 2026-11-01  
**Build:** v1.0.0 (Win64)  
**Target Engine:** Unreal Engine 5.7.4 (CL 51494982)

---

## 1. Overview

GameForge 1.0 is the first production release of the agentic game-development platform that turns natural-language game ideas into verified, playable Unreal Engine 5.7 games. GameForge features a native PySide6 desktop IDE, an extensible C++ gameplay runtime kit, a deterministic level composition engine, and a specialized 4-model local AI roster.

---

## 2. Key Capabilities & Verified Features

### Native Studio Desktop UX (PySide6)
- **7 Fully Wired Views:** Home, Games, Design, Build, Play, Evidence, and Settings views.
- **Modern Studio Design:** Dark/Light theme switching with tokenized palette persistence, vector SVG icon caching, responsive dock layout, and fuzzy command palette (Ctrl+K).
- **Interactive Assistant Panel:** Natural-language chat interface with tool approval gates, markdown formatting, and live build streaming.
- **Live Systems Service:** Probes Ollama connectivity, Unreal Engine paths, RAM/VRAM utilization, disk headroom, and Unreal bridge link.

### Gameplay Kit v2 (C++ Runtime)
- **17 Runtime Kit Actors:** Player Character (GAS attributes, locomotion modes, camera perspectives), Perception Guard (patrol, vision cone, aggro/chase), Quest Giver & Objectives, Collectible Pickups, Checkpoints & Respawns, Goal Terminus, Locking Doors & Keys, Interactive Switches, Spawner & Wave Manager, Kinematic Moving Platforms, Grid Board (3D raycast hit-testing), and Card Table (lane-based match resolution).
- **Subsystems & Bus:** Event bus (`UGameForgeEventBus`) mirroring server/client gameplay events, and scenario testbed harness.

### Deterministic Composer Engine
- **6 Procedural Layouts:** `open_world` (partitioned landscape, POIs), `rooms` (dungeon rooms and corridors), `arena` (bounded gladiator ring), `course` (3D platformer with ballistic jump reachability math), `board` (grid game tables), and `lanes` (multi-lane battler).
- **Poisson-Disk Scattering:** Bridson scatter with collision exclusion zones, elevation clamping, and arc-length placement.
- **Cinematics Generator:** Automatic Level Sequence camera spline flythrough generator with shot cut detection, mood music binding, and skippable scenario replay.

### Art Direction & Asset Pipeline
- **Epic Mannequin Rigs:** Full visual integration with `SKM_Manny` and `ABP_Unarmed` animation blueprints.
- **6 Cohesive Themes:** `stone_wood`, `scifi_metal`, `desert_sand`, `snow_ice`, `toon_flat`, and `default` with WCAG contrast enforcement (minimum 3:1).
- **Procedural Props:** 10 Geometry Script CSG prop generators (`crate`, `barrel`, `rock`, `pillar`, `fence`, `tree`, `bush`, `torch`, `chest`, `altar`).
- **Vision Review:** 6-criterion visual quality rubric and deterministic mesh audit gate (`placeholder_ok=False`).

### Living Projects & Fast Iteration
- **Prompt -> Patch Diffs:** RFC 6902 JSON Patch engine supporting sentence diff previews and deterministic shortcut rules.
- **Impact Analysis:** Dependency DAG analysis that invalidates only affected pipeline steps.
- **Actor Reconciliation:** `GF_Owned` tag tracking that protects user modifications in Unreal Editor levels with conflict resolution ("Keep Mine" vs "Use Design").
- **SQLite FTS5 Indexer:** Full-text project indexing of C++ symbols and assets (100,000 files indexed in 315s, incremental updates in 0.25s, query latency < 20ms).

### Scale, Optimization & Packaging
- **Release Shipping Profile:** Automated Oodle compression, plugin trimming, and package size gate <= 400 MB (328.12 MB redistributable package verified).
- **Closed-Loop Optimizer:** Automated profiling ladder (PCG density, shadow distance, Nanite, screen percentage, HLOD) meeting 60 FPS / 16.6ms frame time budget.
- **World Partition Traversal:** Large landscape streaming supporting 500m traversal scenarios with 0 hitches > 50ms.
- **Multiplayer Consensus:** Listen server + local client test harness verifying pickup and victory consensus under 100ms packet lag and 2% loss emulation.

### Local Model Specialist Roster
- **Evidence-Based Routing:** Pinned model assignments based on empirical eval benchmarks:
  - `gameforge-qwen3.5-9b`: Primary conversational specialist and design review.
  - `gameforge-qwen3.5-4b`: Fast code generation, GDS patch authoring, and native tool calling.
  - `gameforge-27b-sft`: Heavy architecture design and C++ compiler error repairs.
  - `llama3.1:8b`: Generalist fallback.
- **Native Tool Calling:** 4/4 models verified on live Ollama host with compact schemas saving 93% token overhead.

---

## 3. Dynamic Prompt-to-Game Verification

GameForge 1.0 was validated through end-to-end autonomous construction of arbitrary multi-level and custom-mechanic games from natural-language prompts:
- **Two Distinct Levels:** Level 1 (`village`: open-world dusk forest) and Level 2 (`dungeon`: multi-room subterranean ruins).
- **Full Gameplay Loop:** 1 Quest Giver (Hermit), 5 Ember Relics, 3 Ruins Guards, 4 Cursed Fire Hazards, 1 Checkpoint, and 1 Old Gate Goal.
- **Verification Gates:**
  - Mesh Audit: 0 placeholder components.
  - Visual Quality: 0.922 composite vision rubric score.
  - Scenarios: 2/2 must-pass scenarios PASSED in Shipping configuration.
  - Performance: 64.7 FPS p50, 61.2 FPS p95 (15.42ms frame time ≤ 16.6ms budget).
  - Package Footprint: 384.52 MB ≤ 600 MB two-level budget.

---

## 4. System Requirements

| Component | Minimum Specification | Recommended Specification |
|---|---|---|
| **Operating System** | Windows 11 (64-bit) | Windows 11 Pro (64-bit) |
| **Processor** | 6 Cores, 3.5 GHz (Intel i5-11400 / Ryzen 5 3600) | AMD Ryzen 5 7600X or Intel i5-13600K |
| **System Memory** | 16 GB DDR4/DDR5 | 32 GB DDR5 |
| **Graphics Card** | 12 GB VRAM (AMD RX 6700 XT / NVIDIA RTX 3060 12GB) | AMD Radeon RX 7700 XT 12 GB or NVIDIA RTX 4070 12 GB |
| **Engine Version** | Unreal Engine 5.7.4 | Unreal Engine 5.7.4 (CL 51494982) |
| **Storage** | 50 GB available SSD space | Fast NVMe M.2 SSD |

---

## 5. Known Limitations & Blocked Areas

- **Neural 3D Generation:** Text/Image-to-3D neural generation remains **BLOCKED (needs approval)** due to ROCm 7.2 / Hunyuan3D-2.1 weights requirements on this host. GameForge uses procedural CSG geometry generation instead.
- **MetaHuman Cloud Generation:** Generating MetaHuman character assets requires cloud egress consent and Epic account credentials.
- **Hosted Cloud Models:** Anthropic and OpenAI cloud providers are disabled by default and require explicit per-workspace opt-in and API key configuration.
