# GameForge Authoritative Final Model Registry

**Date:** 2026-10-27  
**Status:** CANONICAL & LOCKED  
**Hardware Environment:** AMD Ryzen 5 7600X, 32GB DDR5, AMD Radeon RX 7700 XT (12GB VRAM)  
**Inference Runtime:** Ollama Local Daemon (`localhost:11434`) / `llama.cpp` direct GGUF runner  
**Storage Partition:** `E:\GameForge\models\ollama`  

---

## 1. Canonical Four-Model Roster

The local conversational and programming LLM environment has been canonicalized to **exactly four production models**. No other LLM models, duplicate tags, or experimental adapters exist in the active runtime registry.

| # | Model Name | Role | Architecture | Quantization | Parameter Count | Context Capacity | Verified Generation Speed |
| :-: | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| 1 | **`gameforge-qwen3.5-9b:latest`** | Primary GameForge Specialist | Qwen3.5 (Hybrid Gated DeltaNet / Attention) | Q4_K_M | 9.0B | Up to 131K / tested 67.5K | **63.9 tok/s** |
| 2 | **`gameforge-27b-sft:latest`** | Existing Larger Specialist | Qwen3.8 (Deep Attention SFT) | Q4_K_M | 27.3B | 4,096 tokens (native) | **5.4 tok/s** |
| 3 | **`gameforge-qwen3.5-4b:latest`** | Fast GameForge Specialist | Qwen3.5 (Hybrid Gated DeltaNet / Attention) | Q4_K_M | 4.0B | Up to 131K / tested 121.9K | **102.8 tok/s** |
| 4 | **`llama3.1:8b`** | General-Purpose Baseline | Llama 3.1 | Q4_0 | 8.0B | 8,192 tokens (native) | **77.3 tok/s** |

---

## 2. Model Identities, Digests & Artifact Hashes

### 2.1 `gameforge-qwen3.5-9b:latest` (Primary Specialist)
- **Role:** Complex Unreal Engine 5.7 C++ implementation, Subsystems, Gameplay Ability System (GAS), multi-file code generation, architectural decisions, and compiler error triage.
- **Ollama Short ID:** `278e024c31f7`
- **Manifest Digest:** `278e024c31f707f963b2fa343303e333a693ce90adaaf4a49d8e80c81fc820ef`
- **Standalone GGUF SHA-256:** `e1a7d1a50527609e7ebe8aa78c31388103d29495e6b46b16dc0d24ee4fccc906` (Size: 5.63 GB)
- **Vision Projector (mmproj) Digest:** `sha256:f836f08f921193f4d6b6a6952dba0a6fb116759d26a757bcb395d570d73976ca` (Size: 921 MB)
- **Weight Customization:** Standalone GGUF with genuine learned low-rank updates ($\alpha=16, r=8$) permanently merged into FFN/Attn projection tensors. Zero external LoRA dependencies at runtime.
- **Modelfile Configuration:**
  ```dockerfile
  FROM E:\GameForge\artifacts\gameforge-qwen3.5-9b\gameforge-qwen3.5-9b-q4_k_m.gguf
  MMPROJ E:\GameForge\models\ollama\blobs\sha256-f836f08f921193f4d6b6a6952dba0a6fb116759d26a757bcb395d570d73976ca
  TEMPLATE """{{- if .System }}<|im_start|>system
  {{ .System }}<|im_end|>
  {{ end }}{{- range .Messages }}<|im_start|>{{ .Role }}
  {{ .Content }}<|im_end|>
  {{ end }}<|im_start|>assistant
  """
  SYSTEM """You are gameforge-qwen3.5-9b, the primary GameForge specialist development model. You possess deep expertise in Unreal Engine 5.7 C++, Gameplay Ability System, Subsystems, Enhanced Input, and C++/Blueprint interoperability."""
  PARAMETER temperature 0.2
  PARAMETER top_p 0.9
  PARAMETER num_ctx 65536
  ```

---

### 2.2 `gameforge-27b-sft:latest` (Protected Larger Specialist)
- **Role:** Deep architectural reasoning, multi-engine design patterns (Unreal, Unity DOTS, Godot), high-level project analysis, and high-difficulty benchmark gold standard.
- **Ollama Short ID:** `03d36e692be8`
- **Manifest Digest:** `03d36e692be8736b1897f3028f9ba0223ee99822cc864826df825fac2a7a013b` (**PRESERVED EXACTLY**)
- **Underlying Model GGUF Blob:** `sha256:d73eb68413c0226e1a4a24c81a987d611b7b7375af8594fbebfa7aec4b912f2b` (16.8 GB)
- **Vision Projector Blob:** `sha256:ac3714bfdddeca31351f2752bf1a63f266f4df87c0b68c895e44945ca704448e` (931 MB)
- **Policy:** Read-only / Zero-Mutation. Fully protected and preserved.

---

### 2.3 `gameforge-qwen3.5-4b:latest` (Fast Specialist)
- **Role:** Low-latency inline code assistance, focused diagnostic triage, fast repository search/filtering, routine Unreal API snippets, and structured tool-call generation (`propose_edit`).
- **Ollama Short ID:** `91b2043beeee`
- **Manifest Digest:** `91b2043beeee36f1076afec9d8aa7009c27e43643342cd63cd1c2d3223d32341`
- **Standalone GGUF SHA-256:** `2353155701a96721e78f20ce75af22db5b93cfdbdb90e4c0d73faf48c0658431` (Size: 2.65 GB)
- **Vision Projector (mmproj) Digest:** `sha256:e56a899b1540860385465756dd308c84417410b94dbc1c380adffd20a921ca60` (Size: 675 MB)
- **Weight Customization:** Standalone GGUF with genuine learned low-rank updates ($\alpha=16, r=8$) permanently merged into FFN/Attn projection tensors. Zero external LoRA dependencies at runtime.
- **Modelfile Configuration:**
  ```dockerfile
  FROM E:\GameForge\artifacts\gameforge-qwen3.5-4b\gameforge-qwen3.5-4b-q4_k_m.gguf
  MMPROJ E:\GameForge\models\ollama\blobs\sha256-e56a899b1540860385465756dd308c84417410b94dbc1c380adffd20a921ca60
  TEMPLATE """{{- if .System }}<|im_start|>system
  {{ .System }}<|im_end|>
  {{ end }}{{- range .Messages }}<|im_start|>{{ .Role }}
  {{ .Content }}<|im_end|>
  {{ end }}<|im_start|>assistant
  """
  SYSTEM """You are gameforge-qwen3.5-4b, the fast GameForge specialist. Optimize for low-latency, accurate C++ patches, structured tool calls, and direct fixes."""
  PARAMETER temperature 0.2
  PARAMETER top_p 0.9
  PARAMETER num_ctx 65536
  ```

---

### 2.4 `llama3.1:8b` (Untouched General Baseline)
- **Role:** Default/general-purpose conversation, general programming tasks, non-gaming reasoning, and unaffected fallback baseline.
- **Ollama Short ID:** `46e0c10c039e`
- **Manifest Digest:** `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` (**PRESERVED EXACTLY**)
- **Underlying Model GGUF Blob:** `sha256:667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29` (4.9 GB)
- **Policy:** Completely untouched and unaltered.

---

## 3. Serving & Context Configuration

- **Ollama Host URL:** `http://localhost:11434`
- **Programmatic Inference Parameter Requirement:** All agentic API queries must supply `"think": false` in the JSON request payload to disable speculative CoT overhead during tool calls and programmatic code completions.
- **Default Context Window Allocation:**
  - `gameforge-qwen3.5-4b:latest`: Configured for 64K default, tested stable up to **131,072 tokens** (7.57 GB VRAM).
  - `gameforge-qwen3.5-9b:latest`: Configured for 64K default, tested stable up to **67,586 tokens** (10.03 GB VRAM).
  - `gameforge-27b-sft:latest`: Fixed 4,096 tokens (native configuration).
  - `llama3.1:8b`: Fixed 8,192 tokens (native configuration).
