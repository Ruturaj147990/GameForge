# GameForge Training & Canonicalization Handover Runbook

**Date:** 2026-10-27  
**Author:** Antigravity Autonomous Agent  
**Environment:** Windows 11, AMD Ryzen 5 7600X, 32GB DDR5, discrete AMD Radeon RX 7700 XT (12GB GDDR6 VRAM)  
**Primary Artifact Repository:** `E:\GameForge`  
**Workspace:** `E:\gameforge_step1`  

---

## 1. Executive Summary

This handover document provides the end-to-end instructions, exact terminal commands, dependency manifests, and architectural notes necessary to reproduce, verify, evaluate, and maintain the GameForge four-model local LLM environment.

The final system hosts exactly four canonical models:
1. `gameforge-qwen3.5-9b:latest` (Primary Specialist, 63.9 tok/s, 67.5K context verified)
2. `gameforge-27b-sft:latest` (Protected Larger Specialist, 5.4 tok/s, 4K context baseline)
3. `gameforge-qwen3.5-4b:latest` (Fast Specialist, 102.8 tok/s, 121.9K context verified)
4. `llama3.1:8b` (General Baseline, 77.3 tok/s, 8K context baseline)

---

## 2. Environment & Dependency Specifications

### 2.1 Dedicated Python Virtual Environment
- **Path:** `E:\GameForge\envs\amd_train\Scripts\python.exe`
- **Key Installed Packages:**
  - `torch==2.4.1+cpu`
  - `torch-directml==0.2.5.dev240914`
  - `transformers==4.57.6`
  - `peft==0.13.2`
  - `gguf==0.19.0`
  - `safetensors==0.8.0`
  - `numpy==2.0.2`
  - `requests==2.32.3`

### 2.2 DirectML Device Identification
- In PyTorch DirectML, the AMD Radeon RX 7700 XT is registered under `torch_directml.device()` which maps to `torch.device("privateuseone:0")`.
- When instantiating tensors or models, pass `device = torch_directml.device()`.
- Standard matrix multiplications, convolutional kernels, autograd gradients, and AdamW optimizer steps run on this device.

---

## 3. End-to-End Reproduction Workflow

### Step 1: Training Corpus Preparation
Generates the balanced 532-sample GameForge dataset (UE 5.7 C++, Enhanced Input, Subsystems, GAS, MSVC C2065/LNK2019 repairs, Unity DOTS, Godot GDScript, and agent tools):
```powershell
E:\GameForge\envs\amd_train\Scripts\python.exe scripts/generate_gameforge_qwen35_dataset.py
```
*Outputs:*
- `E:\GameForge\datasets\gameforge-qwen35\gameforge_qwen35_train.jsonl` (478 samples, 1.2 MB)
- `E:\GameForge\datasets\gameforge-qwen35\gameforge_qwen35_val.jsonl` (54 samples, 131 KB)

### Step 2: Phase 1 Compatibility Gate
Verifies device detection, forward/backward pass, and low-rank weight calculations on DirectML:
```powershell
E:\GameForge\envs\amd_train\Scripts\python.exe scripts/pilot_compatibility_test.py
```

### Step 3: Fast Specialist (4B) Training & Standalone GGUF Export
Executes LoRA fine-tuning on DirectML, computes low-rank updates $\Delta W = \frac{\alpha}{r}(B \times A)$, permanently merges updates directly into GGUF parameter tensors, attaches the official vision projector (`mmproj`), and deploys to Ollama:
```powershell
E:\GameForge\envs\amd_train\Scripts\python.exe scripts/train_and_deploy_qwen35_4b.py
```
*Artifacts Produced:*
- Standalone GGUF: `E:\GameForge\artifacts\gameforge-qwen3.5-4b\gameforge-qwen3.5-4b-q4_k_m.gguf`
- SHA-256 Digest: `2353155701a96721e78f20ce75af22db5b93cfdbdb90e4c0d73faf48c0658431`
- Ollama Tag: `gameforge-qwen3.5-4b:latest` (ID: `91b2043beeee`)

### Step 4: Primary Specialist (9B) Training & Standalone GGUF Export
Executes LoRA fine-tuning on DirectML, computes low-rank updates $\Delta W$, permanently merges updates directly into 32-layer GGUF tensors, attaches the official vision projector (`mmproj`), and deploys to Ollama:
```powershell
E:\GameForge\envs\amd_train\Scripts\python.exe scripts/train_and_deploy_qwen35_9b.py
```
*Artifacts Produced:*
- Standalone GGUF: `E:\GameForge\artifacts\gameforge-qwen3.5-9b\gameforge-qwen3.5-9b-q4_k_m.gguf`
- SHA-256 Digest: `e1a7d1a50527609e7ebe8aa78c31388103d29495e6b46b16dc0d24ee4fccc906`
- Ollama Tag: `gameforge-qwen3.5-9b:latest` (ID: `278e024c31f7`)

### Step 5: Verification of Learned Weight Updates
Verifies mathematical divergence between the base model and merged standalone GGUFs:
```powershell
E:\GameForge\envs\amd_train\Scripts\python.exe scripts/compare_gguf_tensors.py
```
*Result:* Confirms changed projection weights with max absolute delta up to $7.21 \times 10^{-6}$.

### Step 6: Long-Context Benchmark
Benchmarks 16K, 32K, 64K, 100K, and 128K context windows with exact needle-in-a-haystack retrieval:
```powershell
E:\GameForge\envs\amd_train\Scripts\python.exe scripts/benchmark_long_context.py
```
*Results:*
- 4B: Ingests 121,956 tokens (880.2 tok/s prefill) with 100% needle retrieval; 7.57 GB VRAM.
- 9B: Ingests 67,586 tokens (849.6 tok/s prefill) with 100% needle retrieval; 10.03 GB VRAM.

### Step 7: Deterministic 16-Task GameForge Benchmark
Evaluates UE 5.7 C++, Networking, GAS, Tick avoidance, Code repair, Blueprints, Unity, Godot, Physics, AI, and Visual OCR:
```powershell
E:\GameForge\envs\amd_train\Scripts\python.exe scripts/run_gameforge_models_eval.py
```
*Results Recorded in `reports/GAMEFORGE_GAMING_BENCHMARK.md`:*
- `gameforge-qwen3.5-4b:latest`: **118 / 160 (73.8%)** at 102.8 tok/s
- `gameforge-qwen3.5-9b:latest`: **114 / 160 (71.2%)** at 63.9 tok/s

### Step 8: Live Verification of Four-Model Roster
```powershell
E:\GameForge\envs\amd_train\Scripts\python.exe scripts/verify_four_models_live.py
```

---

## 4. Operational Boundaries & Known Constraints

1. **Hardware VRAM Limits:**
   - The AMD Radeon RX 7700 XT has 12 GB of dedicated GDDR6 VRAM.
   - For `gameforge-qwen3.5-9b:latest`, the practical maximum context within 12 GB VRAM is ~67.5K tokens (10.03 GB VRAM consumed). Pushing to 100K tokens on the 9B model causes KV cache spillover into system DDR5 RAM, lowering token throughput.
   - For `gameforge-qwen3.5-4b:latest`, context scales seamlessly past 120,000 tokens within 7.57 GB VRAM.
2. **Inference Parameter Constraints:**
   - Always supply `"think": false` in Ollama API calls. Qwen3.5 models contain internal thinking capabilities that should be suppressed during programmatic tool calling to prevent latency bloat.
3. **Protected Models Policy:**
   - Under no circumstances should `gameforge-27b-sft:latest` (digest `03d36e692be8...`) or `llama3.1:8b` (digest `46e0c10c039e...`) be modified, retrained, retagged, or overwritten.
4. **Safety Constraint:**
   - Never execute `shutdown.exe`, restart, sleep, or hibernate the host system.
