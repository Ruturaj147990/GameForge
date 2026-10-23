# GameForge 27B — Training Backend Feasibility Report

**Date:** October 23, 2026  
**Target Architecture:** Qwen 3.8 / 3.5 Causal Language Model (27.3 Billion Parameters)  
**Host Hardware:**
- **CPU:** AMD Ryzen 5 7600X (6 Cores / 12 Threads)
- **RAM:** 32 GB DDR5 (30.88 GB addressable)
- **GPU:** AMD Radeon RX 7700 XT (12 GB VRAM)
- **OS:** Windows 11 Pro 64-bit

---

## 1. Executive Summary & Objective

The objective is to establish an architecture-compatible, causal language-model (CLM) supervised fine-tuning pipeline for the 27.3B-parameter GameForge foundation model, replacing previous synthetic latent-feature MSE objectives with genuine next-token cross-entropy loss and real optimizer updates.

This feasibility report documents the empirical evaluation of two distinct local training pathways:
1. **Full-Model Dense Causal LM Training:** Attempting unquantized 64-layer forward, cross-entropy loss, and backward pass on host memory.
2. **Parameter-Efficient LoRA with DirectML GPU Offload:** Backpropagating gradients through trainable projection adapters on the AMD Radeon RX 7700 XT GPU.

---

## 2. Full-Model 27.3B Dense Architecture Feasibility Test

### 2.1 Theoretical Footprint Analysis
The Qwen 3.8 27B model architecture consists of:
- **Hidden Dimension ($d_{\text{model}}$):** 5,120
- **Intermediate MLP Dimension:** 17,408
- **Transformer Decoder Layers:** 64
- **Vocabulary Size:** 248,320
- **Total Parameters:** Approximately 27,300,000,000

| Component | Precision | Memory Requirement |
| :--- | :---: | :---: |
| Model Weights | BF16 (2 bytes/param) | **54.60 GB** |
| Model Weights | FP32 (4 bytes/param) | **109.20 GB** |
| Full Gradient Tensors ($dL/dW$) | BF16 (2 bytes/param) | **54.60 GB** |
| AdamW Optimizer States ($m, v$) | FP32 (8 bytes/param) | **218.40 GB** |
| **Total Full Dense Training State** | Mixed Precision | **~327.60 GB** |

### 2.2 Empirical Test Execution (`scripts/smoke_test_27b_clm.py`)
An architecture-exact CLM smoke test was executed using Python 3.12, PyTorch 2.4.1, and the official Qwen 248k tokenizer:
1. **Token Embedding Allocation:** Vocab 248,320 $\times$ 5,120 allocated in `torch.bfloat16` (2.37 GB).
2. **Decoder Layer Allocation:** All 64 decoder layers were sequentially allocated in `torch.bfloat16`.
   - At Layer 32/64, physical RAM reached saturation (30.87 GB / 30.88 GB).
   - Windows dynamically paged inactive blocks to disk, allowing all 64 layers to allocate (peak virtual memory: 69.56 GB).
3. **Forward Pass:** The 245-token authentic Unreal Engine 5.7 C++ training sequence was passed through all 64 layers.
   - **Logits Output Shape:** `[1, 245, 248320]` successfully materialized.
   - **Causal Loss Objective:** `nn.CrossEntropyLoss(ignore_index=-100)` computed shifted next-token loss:
     $$\mathcal{L} = 12.6574$$
     *(Note: $\ln(248320) \approx 12.42$, confirming mathematically valid cross-entropy distribution).*
4. **Full Dense Backward Pass Failure:**
   - Calling `loss.backward()` initiated gradient tensor allocation across all 27.3 billion parameters.
   - Allocating 54.6 GB of gradient tensors on top of 54.6 GB of model weights exceeded the Windows pagefile commit limit (~78 GB), triggering an OS commit exhaustion failure (`exit code 1`).

**Conclusion on Full Dense Training:** Full-parameter dense backpropagation of a 27B model cannot run on a 32 GB RAM / 12 GB VRAM workstation without distributed multi-GPU clustering.

---

## 3. Parameter-Efficient LoRA with DirectML Acceleration

### 3.1 LoRA Footprint Analysis
By freezing the base model weights (`requires_grad = False`) and attaching low-rank decomposition matrices ($W = W_0 + \frac{\alpha}{r} B \cdot A$) to key linear projections:
- **LoRA Rank ($r$):** 16
- **LoRA Alpha ($\alpha$):** 32.0
- **Target Modules:** `q_proj`, `v_proj`, `gate_proj`, `up_proj` across selected layers
- **Trainable Parameters:** ~10,000,000 to 25,000,000 (~0.05% to 0.09% of base model)
- **Trainable Weight Memory:** **20 to 50 MB**
- **Gradient Memory:** **20 to 50 MB**
- **AdamW Optimizer States:** **40 to 100 MB**

### 3.2 DirectML Hardware Validation
DirectML was tested on the local AMD Radeon RX 7700 XT:
- **Device Identified:** `AMD Radeon RX 7700 XT` (12 GB dedicated VRAM, 16.9 GB shared).
- **Execution Test:** DirectML executed tensor matrix multiplications, LoRA forward pass, autograd backward pass, and AdamW optimizer updates directly on GPU VRAM (`privateuseone:0`).

---

## 4. Final Selected Architecture & Workflow

1. **Training Engine:** Parameter-Efficient LoRA targeting key attention and MLP projections.
2. **Learning Objective:** Pure causal language model next-token prediction with prompt masking (`ignore_index=-100`).
3. **Compute Hardware:** Hybrid architecture—forward activations computed with base weights, adapter projections and gradients computed with DirectML GPU acceleration on the AMD Radeon RX 7700 XT.
4. **Adapter Merging:** LoRA updates ($B \cdot A \times \frac{\alpha}{r}$) mathematically merged into target weights, producing standalone GGUF (`gameforge-27b-sft-q4_k_m.gguf`).
