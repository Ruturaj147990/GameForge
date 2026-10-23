# GAMEFORGE 27B — ENVIRONMENT AND DISK FEASIBILITY REPORT

**Date:** 2026-10-23  
**Target Architecture:** 27B Foundation Family (`Qwen/Qwen3.8-27B` / `qwen3.8:27b-q4_K_M`)  
**Storage Compliance:** Strict E:\ Drive Isolation (`E:\GameForge\*`)  

---

## 1. Host Hardware Specifications

| Component | Specification | Operational Status |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 Pro 64-bit (Build 26100) | Validated |
| **CPU** | AMD Ryzen 5 7600X (6 Cores, 12 Threads @ 4.70 GHz base / 5.30 GHz boost) | Validated |
| **System Memory (RAM)** | 32 GB DDR5 | Healthy (~22 GB available) |
| **Dedicated GPU** | AMD Radeon RX 7700 XT (12 GB GDDR6 VRAM, Navi 32 / RDNA 3) | Validated (DirectML & Vulkan active) |
| **Display Driver** | AMD Software: Adrenalin Edition 32.0.31041.1004 | Operational |
| **Local Game Engine** | Unreal Engine 5.7 installed at `E:\UE\UE_5.7` | Verified |
| **Inference Server** | Ollama v0.40.6 (Vulkan 0 backend on RX 7700 XT, 11.0 GiB available VRAM) | Active on 127.0.0.1:11434 |

---

## 2. Storage Inventory & Disk Budgeting (E:\ Drive Only)

### Filesystem Baseline
- **Filesystem Drive:** `E:\` (NTFS)
- **Drive Free Space (Pre-Execution):** **587.98 GB**
- **Drive Used Space:** 364.64 GB
- **C:\ Storage Rule:** Zero project files, zero model weights, zero checkpoints, zero caches stored on C:\.

### Directory Allocation Table
```text
E:\GameForge\training\gameforge-27b\   -> Dedicated training artifacts, checkpoints, and loss telemetry
E:\GameForge\datasets\gameforge-27b\   -> Synthetic legally-cleared game dev corpus, manifests, and digests
E:\GameForge\artifacts\gameforge-27b\  -> Standalone merged weights and final Q4_K_M GGUF (~16.8 - 17.8 GB)
E:\GameForge\reports\gameforge-27b\    -> Authoritative engineering reports, benchmark logs, and audits
E:\GameForge\cache\gameforge-27b\      -> Redirected HF_HOME and PIP_CACHE_DIR
E:\GameForge\tmp\gameforge-27b\        -> Redirected TMP and TEMP working scratchpad
```

### Disk Space Budget Projection
| Phase Artifact | Estimated Size | Actual Size | Status |
| :--- | :--- | :--- | :--- |
| Training Dataset & Manifests | ~10 MB | Budgeted | Pending |
| Checkpoint / Weight Updates | ~2 - 5 GB | Budgeted | Pending |
| Standalone Full Checkpoint | ~17 - 18 GB | Budgeted | Pending |
| Temporary Conversion Buffers | ~5 GB | Budgeted | Pending |
| Final Q4_K_M GGUF Model | ~16.8 - 17.8 GB | Target: 17.8 GB | Budgeted |
| **Total Projected Consumption** | **~40 - 45 GB** | **< 8% of Free Space** | **PASSED (Substantial Headroom)** |

---

## 3. Environment Variable Enforcement

All operations in this session execute with the following strict environment paths:
- `HF_HOME=E:\GameForge\cache\gameforge-27b\hf`
- `PIP_CACHE_DIR=E:\GameForge\cache\gameforge-27b\pip`
- `TMP=E:\GameForge\tmp\gameforge-27b`
- `TEMP=E:\GameForge\tmp\gameforge-27b`
- `OLLAMA_MODELS=E:\GameForge\models\ollama`
- `OLLAMA_HOST=127.0.0.1:11434`
