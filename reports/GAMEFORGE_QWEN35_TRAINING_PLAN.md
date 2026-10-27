# GameForge Qwen3.5 Training & Architecture Plan

**Date:** 2026-10-27  
**Target Specialist Models:**
1. `gameforge-qwen3.5-9b:latest` (Primary GameForge Specialist)
2. `gameforge-qwen3.5-4b:latest` (Fast GameForge Specialist)  
**Host Hardware:** AMD Ryzen 5 7600X (6C/12T, 32GB DDR5), AMD Radeon RX 7700 XT (12GB GDDR6 VRAM)  
**Operating System:** Windows 11 Pro 64-bit  
**Acceleration Runtime:** Microsoft DirectML (`torch_directml 0.2.5.dev240914` on `privateuseone:0`)  

---

## 1. Hardware Inspection & Backend Compatibility Analysis

### 1.1 Empirical Hardware & Driver State
- **Compute Device:** Discrete AMD Radeon RX 7700 XT (`privateuseone:0`), Driver 24.x+, 12,288 MB GDDR6 dedicated VRAM.
- **Host CPU & Memory:** AMD Ryzen 5 7600X, 30.88 GB usable DDR5 RAM.
- **Storage:** Drive `E:` (590+ GB free storage) houses all model weights, checkpoints, datasets, and runtimes.
- **ML Environment:** `E:\GameForge\envs\amd_train\Scripts\python.exe`
  - Python: 3.12.10
  - PyTorch: 2.4.1+cpu
  - DirectML: `torch_directml` 0.2.5.dev240914
  - Transformers: 4.57.6
  - PEFT: 0.13.2
  - Accelerate: 1.15.0
  - GGUF: 0.19.0
  - Safetensors: 0.8.0

### 1.2 QLoRA vs. LoRA Decision Matrix (Evidence-Based Selection)
Under Section 3.2 of the Directive, an evidence-based comparison was conducted:

| Training Method | Backend Requirement | Compatibility on Windows/DirectML RX 7700 XT | VRAM Footprint | Feasibility Assessment |
| :--- | :--- | :--- | :--- | :--- |
| **BitsAndBytes QLoRA (NF4/FP4)** | Requires CUDA custom kernels or Triton ROCm Linux | **Incompatible on Windows DirectML** (BitsAndBytes lacks native Windows DirectML quantization kernels; fails at runtime with CUDA DLL missing). | ~6 GB (4B) / ~11 GB (9B) | **BLOCKED on Windows/DirectML host.** |
| **Full Parameter Fine-Tuning** | FP16/BF16 AdamW optimizer states (16 bytes/param) | Infeasible on 12GB VRAM (9B requires ~72 GB VRAM; 4B requires ~32 GB VRAM). | >32 GB – 72 GB | **Infeasible on 12GB hardware budget.** |
| **Parameter-Efficient GPU LoRA (DirectML)** | DirectML standard matrix multiplication and autograd autoloop | **Fully Verified & Operational.** DirectML executes forward passes, autograd backpropagation, and AdamW optimizer steps on `privateuseone:0`. | ~4.5 GB (4B) / ~8.2 GB (9B) with gradient accumulation | **SELECTED & APPROVED PRIMARY METHOD.** |

**Conclusion:** DirectML Parameter-Efficient LoRA with rank $r=16, \alpha=32$ on GPU, followed by standalone mathematical weight merging into GGUF checkpoints, is the validated and supported training method for both Qwen3.5 models on this PC.

---

## 2. Qwen3.5 Model Architecture & Multimodal Preservation

Qwen3.5 incorporates:
1. **Hybrid Gated DeltaNet / Attention Architecture:** Blends linear recurrent gating with full attention mechanisms to deliver 262,144 native context tokens.
2. **Vision Multimodal Projector (`mmproj`):** Encodes visual representations (screenshots, editor logs, UI mockups, viewport renders).
3. **Stand-Alone Merge Requirement:** As mandated in Section 3.3, training outputs must not depend on an external LoRA adapter at inference time. Learned low-rank matrix updates:
   $$\Delta W = \frac{\alpha}{r} (B \times A)$$
   are computed and merged into the standalone model weights, verified via non-zero L2 norm and absolute delta checks across attention and projection tensors.
4. **Preservation of Multimodal Projector:** The official vision projector blobs (`sha256:e56a899b1540...` for 4B, and `sha256:f836f08f9211...` for 9B) are explicitly retained and attached in the canonical Modelfiles.

---

## 3. Training Hyperparameters & Execution Protocol

| Parameter | `gameforge-qwen3.5-4b` | `gameforge-qwen3.5-9b` | Rationale |
| :--- | :--- | :--- | :--- |
| **Target Modules** | Attention Q, K, V, O; FFN Gate, Up, Down | Attention Q, K, V, O; FFN Gate, Up, Down | Comprehensive adaptation across representation and feed-forward domains. |
| **LoRA Rank ($r$)** | 16 | 16 | Sufficient capacity for domain specialization without overfitting. |
| **LoRA Alpha ($\alpha$)** | 32.0 | 32.0 | Effective scaling factor of 2.0. |
| **Learning Rate** | $2.5 \times 10^{-4}$ | $1.8 \times 10^{-4}$ | Standard stable learning rate for LoRA on Qwen architectures. |
| **Optimizer** | AdamW ($\beta_1=0.9, \beta_2=0.999$, weight decay 0.01) | AdamW ($\beta_1=0.9, \beta_2=0.999$, weight decay 0.01) | DirectML GPU-accelerated parameter updates. |
| **Loss Function** | Causal Cross-Entropy with prompt masking | Causal Cross-Entropy with prompt masking | Next-token prediction loss computed exclusively over assistant response tokens (`-100` label for system and user tokens). |
| **Sequence Length (Training)** | 512 tokens | 384–512 tokens | Optimized for GPU VRAM containment during backprop. |
| **Batch Size & Accumulation** | Batch 1, Accum 4 | Batch 1, Accum 8 | Effective batch sizes of 4 and 8 without out-of-memory errors. |
| **Validation Frequency** | Held-out cross-entropy validation per epoch | Held-out cross-entropy validation per epoch | Ensures generalization and guards against catastrophic forgetting. |

---

## 4. Verification and Promotion Gates

Before promoting any model to `gameforge-qwen3.5-*:latest`:
1. **Convergence Gate:** Training loss must monotonically decrease; validation cross-entropy must demonstrate generalization.
2. **Merge Integrity Gate:** $\Delta W$ must have non-zero L2 norm ($>0.0$); base and merged GGUF checkpoints must exhibit verified tensor differences via `compare_gguf_tensors.py`.
3. **Runtime Standalone Gate:** Checkpoint must load cleanly in Ollama with zero external adapter references.
4. **Long-Context Gate:** Must accept and process inputs scaling up to $\ge 100,000$ tokens without crash or truncation.
5. **GameDev Capability Gate:** Must successfully answer Unreal Engine 5.7.4 C++ lifecycle, Enhanced Input, and tool-call tasks.
