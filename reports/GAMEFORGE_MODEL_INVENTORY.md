# GameForge Model Inventory & Canonicalization Manifest

**Date:** 2026-10-27  
**System Hardware:** AMD Ryzen 5 7600X (6C/12T, 32GB DDR5), AMD Radeon RX 7700 XT (12GB GDDR6 VRAM)  
**Primary Storage:** `E:\GameForge` (Ollama storage: `E:\GameForge\models\ollama`)  
**Workspace:** `E:\gameforge_step1`  

---

## 1. Executive Summary & Objective

In accordance with the GameForge Four-Model Canonicalization, Weight Customization, and Long-Context Engineering directive, this document establishes the authoritative inventory of all local language models before, during, and after execution.

The mandated end-state requires **exactly four local conversational/programming LLM identities**:
1. `gameforge-qwen3.5-9b:latest` — Primary GameForge specialist (genuinely fine-tuned Qwen3.5-9B, merged standalone weights, long-context capable).
2. `gameforge-27b-sft:latest` — Existing larger GameForge specialist (**PROTECTED & UNTOUCHED**).
3. `gameforge-qwen3.5-4b:latest` — Fast GameForge specialist (genuinely fine-tuned Qwen3.5-4B, merged standalone weights, low latency, long-context capable).
4. `llama3.1:8b` — Existing default/general-purpose baseline (**PROTECTED & UNTOUCHED**).

All other local LLMs, obsolete checkpoints, temporary tags, and unmerged adapters are scheduled for systematic removal in Phase 8 without damaging shared content-addressed blobs required by the four canonical models.

---

## 2. Initial Model Inventory (Before State)

### 2.1 Protected Models (Zero-Mutation Policy)

| Model Name | Ollama ID (Short) | Full Manifest Digest | Total Size (Bytes) | Model Blob Digest | Status & Policy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`gameforge-27b-sft:latest`** | `03d36e692be8` | `03d36e692be8736b1897f3028f9ba0223ee99822cc864826df825fac2a7a013b` | 17,741,863,644 | `sha256:d73eb68413c0226e1a4a24c81a987d611b7b7375af8594fbebfa7aec4b912f2b` (16.8 GB) | **PROTECTED**. Do not modify, retag, overwrite, or mutate. Vision projector `sha256:ac3714bfdddec...` attached. |
| **`llama3.1:8b`** | `46e0c10c039e` | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` | 4,920,753,328 | `sha256:667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29` (4.9 GB) | **PROTECTED**. Baseline general model. Do not alter parameters or Modelfile. |

### 2.2 Existing Obsolete / Unwanted Models (Scheduled for Phase 8 Cleanup)

| Model Name | Ollama ID | Manifest Digest | Size (Bytes) | Underlying Model Blob | Scheduled Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `qwen3.8:27b` | `aaee06c39dcf` | `aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813` | 17,741,872,154 | `sha256:f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d` | Remove tag & unshared blobs |
| `gameforge-27b:latest` | `7bc56a87ebcc` | `7bc56a87ebccd603702faf4189f48c359fbfbc95a5ee5439045d2614f202fab6` | 17,741,861,011 | `sha256:5d525cfd5dbad1f27eb1cd6c561e00f5a5c7806e9b8c797712dfeb2c5da5ba71` | Remove tag & unshared blobs |
| `gameforge-v2:latest` | `9f6fae7cd1ff` | `9f6fae7cd1ffb112caae532e8be4e935bfeeaaa1e19d07314adebb98d7d9aeab` | 1,929,903,204 | `sha256:dfe14c9d771535c51cfc31637c1ac384debe3c0425316ed96fde5e661a00d9db` | Remove tag & unshared blobs |
| `qwen3.8:27b-q4_K_M` | `25b843619e94` | `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e` | 17,741,872,132 | `sha256:f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d` | Remove duplicate alias tag |
| `llama3.1-specialist:8b` | `8ee3d20c2d79` | `8ee3d20c2d79ac11c9ceb439b6a45f9a7f4629ebce532383ceefa70bbda16f0d` | 4,920,753,055 | `sha256:667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29` | Remove redundant specialist tag |

---

## 3. Planned Target State (Final 4-Model Roster)

| Target Identity | Role | Architecture | Checkpoint Status | Export Format | Context Target |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`gameforge-qwen3.5-9b:latest`** | Primary GameForge Specialist | Qwen3.5-9B (Gated DeltaNet / Attention Hybrid) | Genuinely fine-tuned on GameForge SFT corpus; merged standalone weights | Standalone Q4_K_M GGUF with mmproj vision projector | $\ge 100,000$ tokens native / practical |
| **`gameforge-27b-sft:latest`** | Existing Larger Specialist | Qwen3.8-27B | Verified Production SFT (v2.1) | Q4_K_M GGUF with attached vision projector | 4,096 tokens (native configuration preserved) |
| **`gameforge-qwen3.5-4b:latest`** | Fast GameForge Specialist | Qwen3.5-4B (Gated DeltaNet / Attention Hybrid) | Genuinely fine-tuned on GameForge SFT corpus; merged standalone weights | Standalone Q4_K_M GGUF with mmproj vision projector | $\ge 100,000$ tokens native / practical |
| **`llama3.1:8b`** | General Coding / Instruction Baseline | Llama 3.1 8B | Default base weights untouched | Official Ollama Q4_0 GGUF | 8,192 tokens (native baseline preserved) |

---

## 4. Preservation of Non-LLM Assets

The local disk environment contains multi-modal asset creation pipelines (procedural geometry, meshes, physics colliders, quarantine assets under `E:\GameForge\assets` and `.gameforge/quarantine/`). In strict compliance with Section 1 of the Directive:
- **No 3D, image, or video models/assets will be deleted.**
- Cleanup mechanisms are strictly constrained to Ollama model tag removal via the supported API/CLI and selective removal of intermediate training checkpoints.

---

## 5. Final Verified Inventory (After State)

Following Phase 8 cleanup, the active local LLM environment hosts **EXACTLY FOUR** conversational/programming LLM identities:

| Model Name | Ollama ID | Full Manifest Digest | Total Size | Underlying Model Blob | Status & Verification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`gameforge-qwen3.5-9b:latest`** | `278e024c31f7` | `278e024c31f707f963b2fa343303e333a693ce90adaaf4a49d8e80c81fc820ef` | 6,550,815,033 | `sha256:e1a7d1a50527609e7ebe8aa78c31388103d29495e6b46b16dc0d24ee4fccc906` (5.63 GB) | **DEPLOYED & ACTIVE**. Primary GameForge Specialist. Standalone merged weights; mmproj attached. |
| **`gameforge-27b-sft:latest`** | `03d36e692be8` | `03d36e692be8736b1897f3028f9ba0223ee99822cc864826df825fac2a7a013b` | 17,741,863,644 | `sha256:d73eb68413c0226e1a4a24c81a987d611b7b7375af8594fbebfa7aec4b912f2b` (16.8 GB) | **PROTECTED & VERIFIED**. Digest exactly identical to before-state. Vision projector attached. |
| **`gameforge-qwen3.5-4b:latest`** | `91b2043beeee` | `91b2043beeee36f1076afec9d8aa7009c27e43643342cd63cd1c2d3223d32341` | 3,324,163,223 | `sha256:2353155701a96721e78f20ce75af22db5b93cfdbdb90e4c0d73faf48c0658431` (2.65 GB) | **DEPLOYED & ACTIVE**. Fast GameForge Specialist. Standalone merged weights; mmproj attached. |
| **`llama3.1:8b`** | `46e0c10c039e` | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` | 4,920,753,328 | `sha256:667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29` (4.9 GB) | **PROTECTED & VERIFIED**. Digest exactly identical to before-state. Base model intact. |

All 7 obsolete models (`qwen3.8:27b`, `gameforge-27b:latest`, `gameforge-v2:latest`, `qwen3.8:27b-q4_K_M`, `llama3.1-specialist:8b`, `qwen3.5:4b`, `qwen3.5:9b`) have been purged. Zero external LoRA adapters are loaded at runtime.

