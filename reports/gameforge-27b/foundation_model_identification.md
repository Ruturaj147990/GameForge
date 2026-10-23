# GAMEFORGE 27B — FOUNDATION MODEL FORENSIC IDENTIFICATION

**Date:** 2026-10-23  
**Auditor:** ML Systems & Autonomous AI Model Engineering  
**Governing Objective:** Section 3 ("Identify and recover the real foundation checkpoint")  

---

## 1. Upstream Model Forensics

| Attribute | Measured Technical Value | Verification Source |
| :--- | :--- | :--- |
| **Upstream Repository** | `Qwen/Qwen3.8-27B` | Hugging Face Hub API |
| **Pinned Revision SHA** | `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` | Remote git commit SHA & manifest |
| **Model Type** | `qwen3_5` | `config.json` |
| **Architecture Class** | `Qwen3_5ForConditionalGeneration` | `config.json` |
| **Total Parameter Count** | **27.3 Billion Parameters** (27,338,460,160) | Ollama inspection & GGUF metadata |
| **Language Backbone** | 26.8B Dense Hybrid Linear/Full Attention | 64 Layers (48 Linear Attention, 16 Full Attention) |
| **Vision Projector (CLIP)**| 460.73M Parameters (`mmproj`) | `mmproj-qwen3.8-27b-bf16.gguf` |
| **Context Window** | 262,144 Tokens (Native 256k) | `config.json` (`max_position_embeddings`) |
| **Hidden Size ($d_{model}$)**| 5,120 | `config.json` |
| **Intermediate Size** | 17,408 | `config.json` |
| **Attention Heads** | 24 Query Heads, 4 Key/Value Heads (GQA) | `config.json` |
| **Tokenizer** | Byte-Pair Encoding (`Qwen2TokenizerFast`) | `tokenizer.json` (SHA: `0997f410c57a...`) |
| **Vocabulary Size** | 248,320 Tokens (Padded) | `vocab.json` & `tokenizer_config.json` |
| **License** | **Apache-2.0** (Fully permissive commercial use) | `LICENSE` file on HF Hub & Ollama layer |

---

## 2. Local Ollama Runtime Foundation Checkpoint

The local runtime foundation model registered in Ollama as `qwen3.8:27b-q4_K_M` was directly inspected from the on-disk storage manifests:

- **Manifest Path:** `E:\GameForge\models\ollama\manifests-v2\ollama.com\library\qwen3.8\27b-q4_K_M`
- **Model Tensor Blob:** `E:\GameForge\models\ollama\blobs\sha256-f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d`
- **Blob File Size:** **16,810,714,464 bytes** (~16.81 GB / 15.65 GiB)
- **Multimodal Projector Blob:** `sha256-ac3714bfdddeca31351f2752bf1a63f266f4df87c0b68c895e44945ca704448e` (931,146,016 bytes)
- **Internal GGUF Tensors:** 866 tensors
- **Quantization Profile:** **Q4_K_M** (Mixed precision: Q4_K for linear projections, Q6_K for output/embeddings, F32 for normalization layers and gates)
- **Inference Runtime:** Vulkan 0 compute engine running on AMD Radeon RX 7700 XT (12 GB VRAM)

---

## 3. Remote Hugging Face Unquantized BF16 Checkpoint Status

- **Hub Availability:** Validated via `huggingface_hub.HfApi.model_info()`.
- **Shard Composition:** 18 `.safetensors` shards (`model-00001-of-00018.safetensors` through `model-00018-of-00018.safetensors`).
- **Unquantized File Size:** **55,563,006,776 bytes (51.75 GB)**.
- **Local HF Metadata:** Pinned and cached at `E:\GameForge\models\hf\Qwen3.8-27B`.
- **Framework Version:** Requires Transformers `>= 5.8.0.dev0` for native HF class definitions of `Qwen3_5ForConditionalGeneration`.
