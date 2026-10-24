# GameForge — Canonical Project Context & Memory

**Last Updated:** 2026-10-24T12:10:00+05:30  
**Current Milestone:** Phase 2 Verified Release (`gameforge-27b-sft:latest` v2.1.0)  
**Primary Repository Root:** `E:\gameforge_step1`  
**Storage & Large-Artifact Root:** `E:\GameForge`  
**Active Production Model:** `gameforge-27b-sft:latest` (Ollama ID: `03d36e692be8`, GGUF SHA-256: `d73eb684...`)  
**Context Protocol:** Mandatory reading & updating on every session ([AGENTS.md](file:///e:/gameforge_step1/AGENTS.md))  

---

## A. Project Identity & Mission

GameForge is an autonomous, open-weights, multi-engine game development artificial intelligence.
- **Intended Capabilities:** Expert-level code generation, refactoring, and debugging across Unreal Engine 5.7 (GAS, Networking, Subsystems, TObjectPtr), Unity 6 (DOTS Entities 1.3, Baker Authoring, C# Gameplay), Godot 4.3 (GDScript, CharacterBody3D, Typed Signals), and universal Game Mathematics.
- **Multimodal Perception:** Direct screenshot-based visual debugging of compiler error logs, editor crashes, shader artifacts, and scene hierarchies.
- **Primary Deliverable:** Local, reproducible GGUF models running via Ollama/llama-server with hybrid GPU/CPU offload on consumer AMD hardware, backed by a deterministic evaluation benchmark and version-aware engine knowledge registry.

---

## B. Non-Negotiable Constraints

1. **Hardware & OS:** Windows 11 Pro, AMD Ryzen 5 7600X (6C/12T, 32GB DDR5), AMD Radeon RX 7700 XT (12GB GDDR6 VRAM). `[VERIFIED]`
2. **Storage Boundaries:** 100% of large models, datasets, caches, training checkpoints, and GGUFs must remain on the `E:` drive (`E:\GameForge`). No 10+ GB artifacts on the OS `C:` drive. `[VERIFIED]`
3. **Computer Safety Rule:** **NEVER shut down, restart, sleep, or hibernate the system. Never invoke `shutdown.exe`.** `[VERIFIED]`
4. **Local Execution Only:** Zero paid cloud APIs, zero external model downloading during tasks, zero simulated/fake training updates. `[VERIFIED]`
5. **Rollback & Provenance Safeguards:** Never overwrite working models or Modelfiles without preserving rollback configurations. Distinguish weight training from prompt/configuration improvements. `[VERIFIED]`
6. **Inference Directives:** When querying Ollama API programmatically, set `"think": False` for direct code generation to prevent hidden reasoning token exhaustion. `[VERIFIED]`

---

## C. Current System Architecture

```
E:\gameforge_step1\ (Canonical Git Repo)
├── configs/
│   ├── engine_knowledge_registry.json   <- v2.1.0: Version-aware API invariants (UE 5.7, Unity 6, Godot 4.3)
│   ├── Modelfile.gameforge-27b-sft-v2   <- Rollback Modelfile (v2.0)
│   └── Modelfile.gameforge-27b-sft-v2.1 <- Canonical production Modelfile (v2.1)
├── src/gameforge_bench/
│   ├── cli.py / gameforge_cli.py        <- CLI routing & interactive chat defaults (points to gameforge-27b-sft)
│   ├── grading.py                       <- 9-layer benchmark grading engine
│   └── knowledge_retrieval.py           <- In-memory engine knowledge retrieval
├── scripts/
│   ├── run_phase2_broader_eval.py       <- 16-task deterministic broader benchmark harness
│   └── run_phase2_targeted_and_holdout_test.py <- 7-task comparative retest and holdout validator
├── tests/unit/
│   └── test_evaluation_harness.py       <- Unit tests for evaluation arithmetic, syntax, and rubric normalization
└── reports/gameforge-27b-sft/           <- Detailed release reports, manifests, execution logs, and raw outputs

E:\GameForge\ (Large-Artifact Storage Root)
├── artifacts/gameforge-27b-sft/         <- Standalone Q4_K_M GGUF (16.8 GB)
├── models/ollama/                       <- Ollama storage ($env:OLLAMA_MODELS): blobs, manifests-v2
├── ollama_bin/ollama.exe                <- Canonical Ollama binary v0.40.6 (Vulkan backend)
├── training/gameforge-27b-sft/          <- SFT LoRA adapter safetensors (2.78M params)
└── datasets/gameforge-27b-sft/          <- Original 518-sample multi-engine SFT dataset
```

---

## D. Model Inventory & Deployment State

| Tag | Ollama ID | Format | Size | SHA-256 / Digest | Status | Evidence State |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`gameforge-27b-sft:latest`** | `03d36e692be8` | Q4_K_M GGUF | 16.8 GB | `d73eb68413c0226e1a4a24c81a987d611b7b7375af8594fbebfa7aec4b912f2b` | **PRODUCTION CANONICAL (v2.1)** | `VERIFIED` |
| `qwen3.8:27b-q4_K_M` | `25b843619e94` | Q4_K_M GGUF | 16.8 GB | Foundation base model | Preserved for baseline delta checks | `VERIFIED` |
| `gameforge-27b:latest` | `7bc56a87ebcc` | Q4_K_M GGUF | 16.8 GB | Pre-SFT candidate | Preserved for regression audits | `VERIFIED` |
| `gameforge-v2:latest` | `9f6fae7cd1ff` | Q4_K_M GGUF | 1.9 GB | Compact 3B specialist | Preserved | `VERIFIED` |
| `gameforge-v1:latest` | — | GGUF | — | Obsolete prompt-wrapper baseline | **RETIRED & REMOVED** | `VERIFIED` |

- **Vision Projector:** Attached blob `sha256:ac3714bfdddeca31351f2752bf1a63f266f4df87c0b68c895e44945ca704448e` (931 MB). Verified functional in Ollama. `[VERIFIED]`
- **Inference Runtime:** `E:\GameForge\ollama_bin\ollama.exe serve` on port 11434 with 37 GPU offloaded layers and 28 CPU/DDR5 layers (~4.7 tokens/sec). `[VERIFIED]`

---

## E. Latest Verified Metrics (Phase 2 Results)

1. **Broader 16-Task Multi-Engine Benchmark:** `[VERIFIED]` (2026-10-24)
   - Score: **153 / 160 points (95.62%)**
   - Perfect 10/10 Tasks: **13 / 16 (81.25%)**
   - UE 5.7 Tick Avoidance (`PH2-04`): **10 / 10** (Resolved prior 0/10 failure caused by conversational preamble).
   - Visual Debugging (`PH2-16`): **10 / 10** (OCR + include diagnosis in 429 tokens).
   - Source: [`reports/gameforge-27b-sft/phase2_evaluation_results.csv`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_evaluation_results.csv)
2. **Comparative Targeted Retest & Holdout Suite:** `[VERIFIED]` (2026-10-24)
   - Targeted Retest (3 tasks): **30 / 30 (100.0%)** (Candidate v2.1 reduced token usage on `PH2-02` from 512 [TRUNC] to 272 [COMPLETE]).
   - Unseen Holdout Suite (4 tasks): **40 / 40 (100.0%)** (Zero regressions across UE LineTrace, Unity Audio event, Godot Lerp, Math Euler-Quat).
   - Source: [`reports/gameforge-27b-sft/phase2_holdout_results.csv`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_holdout_results.csv)
3. **Full Project Unit Tests:** `[VERIFIED]` (2026-10-24)
   - Command: `pytest tests/unit/` $\to$ **141 passed in 18.44 seconds (100% pass rate)**.
4. **Historical Discrepancy Note:** `[SUPERSEDED]`
   - Prior report stated *"3 tasks improved"* on the short 8-task test. Audit of `before_after_results.csv` confirmed **4 tasks improved** (+9, +1, +10, +10), with `TASK-03` (+1) overlooked in the earlier summary.

---

## F. Completed Work & Key Engineering Decisions

- **DirectML Parameter-Efficient SFT:** Trained 940 optimizer steps across 470 verified multi-engine samples on RX 7700 XT. Converged cross-entropy loss: 8.5610 $\to$ 4.0715 (val: 3.5461). Learned adapters permanently merged into Q4_K_M weights. `[VERIFIED]`
- **Anti-Scaffolding Directives (v2.1):** Solved token budget exhaustion by instructing the model to focus on requested method bodies rather than emitting redundant dual `.h`/`.cpp` files with duplicate `#include` headers. `[VERIFIED]`
- **Multimodal Projector Restoration:** Re-attached vision projector blob into Modelfile, restoring OCR screenshot error diagnosis. `[VERIFIED]`
- **Retirement of V1:** Removed obsolete prompt-wrapper `gameforge-v1:latest` from registry. `[VERIFIED]`

---

## G. Current State & Active Objective

- **Current State:** `gameforge-27b-sft:latest` v2.1 is fully verified, operational in Ollama (ID: `03d36e692be8`), passing 100% of holdout tests and 141 unit tests. The permanent Antigravity memory and context-compaction survival system (`context.md`, `AGENTS.md`, `.agents/rules/context-protocol.md`, and `E:\GameForge\context.md`) is fully implemented, active, and verified.
- **Active Objective:** Phase 2 Verified Release and durable project memory protocol fully operational.
- **Next Concrete Action:** Ready for future user instructions or Phase 3 feature development (e.g., expanding UE 5.7 Blueprint graphs or engine-specific tool integrations). All future sessions must consult `context.md` upon initialization.

---

## H. Test & Execution Reference

```powershell
# 1. Start Ollama Server with Canonical Storage (if stopped)
$env:OLLAMA_MODELS = "E:\GameForge\models\ollama"; & "E:\GameForge\ollama_bin\ollama.exe" serve

# 2. Run Full Unit Test Suite (141 tests)
pytest tests/unit/

# 3. Run Broader 16-Task Deterministic Evaluation
python scripts/run_phase2_broader_eval.py gameforge-27b-sft:latest

# 4. Run Targeted Retest and Holdout Validation
python scripts/run_phase2_targeted_and_holdout_test.py

# 5. Interactive Chat CLI
python -m src.gameforge_bench.cli chat --model gameforge-27b-sft
```

---

## I. Known Problems & Lessons Learned

1. **Hidden Reasoning Token Exhaustion:** When querying Ollama API, omitting `"think": False` causes models with reasoning capability (Qwen3.8 architecture) to burn generation tokens inside `<think>` tags, leaving the response empty. Always specify `"think": False` for direct code generation.
2. **Dual Translation Unit Bloat:** When asked for Unreal C++ classes, models tend to output both full `.h` and `.cpp` with 10 includes each, burning >400 tokens on boilerplate. Prompts must steer models to focus on requested method implementations.
3. **Ollama Windows Process Binding:** Running `ollama list` without setting `$env:OLLAMA_MODELS` defaults to `C:\Users\limbk\.ollama`. Always set `$env:OLLAMA_MODELS = "E:\GameForge\models\ollama"`.

---

## J. Important Artifacts & Source of Truth

- **Canonical Context:** [`context.md`](file:///e:/gameforge_step1/context.md) (This file)
- **Phase 2 Release Report:** [`reports/gameforge-27b-sft/phase2_final_report.md`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_final_report.md)
- **Phase 2 Release Manifest:** [`reports/gameforge-27b-sft/phase2_final_manifest.json`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_final_manifest.json)
- **Phase 2 Evaluation Report:** [`reports/gameforge-27b-sft/phase2_evaluation_report.md`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_evaluation_report.md)
- **Phase 2 Changes Manifest:** [`reports/gameforge-27b-sft/phase2_changes.md`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_changes.md)
- **Phase 2 Execution Log:** [`reports/gameforge-27b-sft/phase2_execution_log.md`](file:///e:/gameforge_step1/reports/gameforge-27b-sft/phase2_execution_log.md)
- **Production Modelfile:** [`configs/Modelfile.gameforge-27b-sft-v2.1`](file:///e:/gameforge_step1/configs/Modelfile.gameforge-27b-sft-v2.1)
- **Engine Knowledge Registry:** [`configs/engine_knowledge_registry.json`](file:///e:/gameforge_step1/configs/engine_knowledge_registry.json)

---

## K. Resume Instructions for Antigravity Sessions

1. **Read `context.md`:** Review current state, production tags, and active constraints before taking any action.
2. **Check Daemon Status:** Run `netstat -ano | findstr :11434` or query `http://127.0.0.1:11434/api/tags` to ensure Ollama is responsive.
3. **Verify Git & Artifacts:** Confirm `git status` and verify referenced paths on `E:` drive.
4. **Execute Bounded Steps:** Resume directly from the documented active objective; do not repeat completed milestones.
5. **Preserve Rules:** Never invoke `shutdown.exe`, never write large artifacts to `C:`, never modify model weights without authorization.
6. **Update `context.md`:** Update this file at major milestones and before concluding every session.

---

## L. Recent Context Changes

- **2026-10-24T12:15:** Fully integrated persistent Antigravity memory system (`AGENTS.md`, `.agents/rules/context-protocol.md`, `.agents/skills/00-ml-orchestrator.md`, and mirrored `E:\GameForge\context.md`).
- **2026-10-24T12:10:** Created canonical `context.md` covering architecture, non-negotiable constraints, verified Phase 2 metrics (153/160 broader, 40/40 holdout, 141 unit tests), and deployment state.
- **2026-10-24T11:50:** Promoted candidate configuration to production `gameforge-27b-sft:latest` (Ollama ID: `03d36e692be8`).
- **2026-10-24T00:35:** Verified SFT weight convergence and retired `gameforge-v1:latest`.
