# GameForge Local LLM Model Cleanup & Canonicalization Report

**Date:** 2026-10-27  
**Execution Host:** Local PC (Windows 11, AMD Ryzen 5 7600X, 32GB DDR5, AMD Radeon RX 7700 XT 12GB VRAM)  
**Model Store Root:** `E:\GameForge\models\ollama`  
**Ollama Version:** Ollama v0.5+ API & CLI  

---

## 1. Executive Summary & Objective

In accordance with Phase 8 ("Remove all other local LLMs") of the GameForge Four-Model Canonicalization, Weight Customization, and Long-Context Engineering directive:
1. All obsolete, redundant, experimental, and temporary local LLM entries have been removed from the managed Ollama environment.
2. The exact four canonical model identities are retained and operational:
   - `gameforge-qwen3.5-9b:latest` (Primary GameForge Specialist)
   - `gameforge-27b-sft:latest` (Protected Larger Specialist — Baseline SSOT)
   - `gameforge-qwen3.5-4b:latest` (Fast GameForge Specialist)
   - `llama3.1:8b` (General Instruction Baseline)
3. Content-addressed blobs shared with retained models were strictly preserved.
4. Non-LLM assets (procedural 3D geometry, Unreal Engine meshes, materials, and quarantine pipelines) were completely excluded from deletion.

---

## 2. Inventory of Removed Local LLM Entries

The following 7 local LLM models/tags were systematically removed using Ollama's native model management API (`DELETE /api/delete`):

| Model Name | Removed Ollama ID | Manifest Digest | Size | Rationale for Removal |
| :--- | :--- | :--- | :--- | :--- |
| `qwen3.8:27b` | `aaee06c39dcf` | `aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813` | 17.7 GB | Obsolete uncustomized base model |
| `gameforge-27b:latest` | `7bc56a87ebcc` | `7bc56a87ebccd603702faf4189f48c359fbfbc95a5ee5439045d2614f202fab6` | 17.7 GB | Superseded pre-SFT checkpoint |
| `gameforge-v2:latest` | `9f6fae7cd1ff` | `9f6fae7cd1ffb112caae532e8be4e935bfeeaaa1e19d07314adebb98d7d9aeab` | 1.9 GB | Obsolete v2 legacy test model |
| `qwen3.8:27b-q4_K_M` | `25b843619e94` | `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e` | 17.7 GB | Redundant tag/alias for Qwen3.8 |
| `llama3.1-specialist:8b` | `8ee3d20c2d79` | `8ee3d20c2d79ac11c9ceb439b6a45f9a7f4629ebce532383ceefa70bbda16f0d` | 4.9 GB | Redundant alias tag referencing base Llama 3.1 blob |
| `qwen3.5:4b` | `d8b0f5e9760c` | `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04` | 3.3 GB | Temporary base pull used for 4B training |
| `qwen3.5:9b` | `56671c2ab938` | `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90` | 6.6 GB | Temporary base pull used for 9B training |

---

## 3. Shared Content-Addressed Blob Preservation Audit

Ollama uses a content-addressed storage layout (`blobs/sha256-<hash>`). Per Section 12 requirements, shared blobs required by retained models were verified before and after cleanup:

1. **`gameforge-27b-sft:latest` (Protected):**
   - Model GGUF Blob: `sha256:d73eb68413c0226e1a4a24c81a987d611b7b7375af8594fbebfa7aec4b912f2b` (16.8 GB) — **VERIFIED INTACT**
   - Vision Projector Blob: `sha256:ac3714bfdddeca31351f2752bf1a63f266f4df87c0b68c895e44945ca704448e` (931 MB) — **VERIFIED INTACT**
   - Manifest Digest: `03d36e692be8736b1897f3028f9ba0223ee99822cc864826df825fac2a7a013b` — **IDENTICAL TO START**

2. **`llama3.1:8b` (Protected):**
   - Model GGUF Blob: `sha256:667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29` (4.9 GB) — **VERIFIED INTACT** (Shared previously with removed `llama3.1-specialist:8b`; blob remained preserved without corruption)
   - Manifest Digest: `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` — **IDENTICAL TO START**

3. **`gameforge-qwen3.5-9b:latest` (New Standalone Specialist):**
   - Merged Standalone Model GGUF Blob: `sha256:e1a7d1a50527609e7ebe8aa78c31388103d29495e6b46b16dc0d24ee4fccc906` (5.63 GB) — **VERIFIED INTACT**
   - Vision Projector Blob: `sha256:f836f08f921193f4d6b6a6952dba0a6fb116759d26a757bcb395d570d73976ca` (921 MB) — **VERIFIED INTACT** (Preserved from official Qwen3.5-9B multi-modal stack)
   - Manifest Digest: `278e024c31f707f963b2fa343303e333a693ce90adaaf4a49d8e80c81fc820ef` — **ACTIVE**

4. **`gameforge-qwen3.5-4b:latest` (New Standalone Specialist):**
   - Merged Standalone Model GGUF Blob: `sha256:2353155701a96721e78f20ce75af22db5b93cfdbdb90e4c0d73faf48c0658431` (2.65 GB) — **VERIFIED INTACT**
   - Vision Projector Blob: `sha256:e56a899b1540860385465756dd308c84417410b94dbc1c380adffd20a921ca60` (675 MB) — **VERIFIED INTACT** (Preserved from official Qwen3.5-4B multi-modal stack)
   - Manifest Digest: `91b2043beeee36f1076afec9d8aa7009c27e43643342cd63cd1c2d3223d32341` — **ACTIVE**

---

## 4. Preservation of Non-LLM Assets

In compliance with Directive Section 1 & 12:
- No file system wipe was executed.
- Assets under `E:\GameForge\assets\` (procedural geometry, meshes, audio, textures) and quarantine directories (`.gameforge/quarantine/`) were untouched.
- Training scripts, datasets, adapter checkpoints, and evaluation logs under `E:\GameForge\training\` and `E:\GameForge\datasets\` are preserved for reproducibility.

---

## 5. Post-Cleanup Verification Evidence

Execution of `ollama list` and HTTP `GET /api/tags` confirms **EXACTLY FOUR** models remain:

```text
NAME                           ID              SIZE      MODIFIED
gameforge-qwen3.5-9b:latest    278e024c31f7    6.6 GB    18 minutes ago
gameforge-qwen3.5-4b:latest    91b2043beeee    3.3 GB    29 minutes ago
gameforge-27b-sft:latest       03d36e692be8    17 GB     3 days ago
llama3.1:8b                    46e0c10c039e    4.9 GB    2 weeks ago
```

### Live Inference Test on the 4 Retained Models:
- `llama3.1:8b`: Operational (77.3 tok/s)
- `gameforge-27b-sft:latest`: Operational (5.4 tok/s)
- `gameforge-qwen3.5-4b:latest`: Operational (102.8 tok/s)
- `gameforge-qwen3.5-9b:latest`: Operational (64.2 tok/s)

Canonicalization and cleanup status: **PASSED & COMPLETE**.
