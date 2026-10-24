# GameForge 27B SFT — Cleanup & Model Retirement Manifest

**Date:** October 24, 2026  
**Auditor:** GameForge Model Optimization & Release Engineer  

---

## 1. Model Retirement Actions

| Target Model Tag | Action | Method | Verification Check | Status | Rationale |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`gameforge-v1:latest`** | **Retired** | `ollama rm gameforge-v1:latest` | Confirmed absence in `ollama list` | **RETIRED** | Obsolete prompt-wrapper baseline superseded by genuinely fine-tuned `gameforge-27b-sft:latest`. All historical evaluation reports and Modelfile definitions are preserved. |
| **`gameforge-27b-sft-v2:latest`** | **Cleaned Up** | `ollama rm gameforge-27b-sft-v2:latest` | Confirmed absence in `ollama list` | **REMOVED** | Temporary test candidate tag used for before-and-after validation. Successfully promoted into the canonical `gameforge-27b-sft:latest` tag. |

---

## 2. Preserved Critical Artifacts & Models

The following core artifacts, baseline models, checkpoints, and reports were strictly preserved to guarantee complete provenance and reproducibility:

### Registered Models
- **`gameforge-27b-sft:latest`** (`17 GB`, ID: `38d78286fde2`): The canonical production model with fine-tuned LoRA weights, multimodal vision support, ChatML template, and code-first game development prompt.
- **`qwen3.8:27b-q4_K_M`** (`17 GB`, ID: `25b843619e94`): The original base foundation model required for delta comparisons and baseline regressions.
- **`gameforge-27b:latest`** (`17 GB`, ID: `7bc56a87ebcc`): The previous MSE candidate required for independent acceptance and historical audit.
- **`gameforge-v2:latest`** (`1.9 GB`, ID: `9f6fae7cd1ff`): The compact specialist candidate.

### Model Weights & Artifacts (E: Drive)
- `E:\GameForge\artifacts\gameforge-27b-sft\gameforge-27b-sft-q4_k_m.gguf` (16,810,714,464 bytes, SHA-256: `d73eb68413c0226e1a4a24c81a987d611b7b7375af8594fbebfa7aec4b912f2b`)
- `E:\GameForge\training\gameforge-27b-sft\adapter\adapter_model.safetensors` (11,143,696 bytes, 2,785,280 trainable params)
- `E:\GameForge\training\gameforge-27b-sft\adapter\adapter_config.json`
- `E:\GameForge\training\gameforge-27b-sft\smoke_test\clm_smoke_test_result.json`
- `E:\GameForge\datasets\gameforge-27b-sft\gameforge_27b_sft_train.jsonl` (SHA-256: `df5ccc71c00e2a81...`, 470 samples)
- `E:\GameForge\datasets\gameforge-27b-sft\gameforge_27b_sft_val.jsonl` (SHA-256: `a8ec5be009ca412e...`, 48 samples)

### Reports & Records
- `reports/gameforge-27b-sft/` (All 14 feasibility, dataset quality, training, verification, benchmark, and upgrade reports).
- `reports/gameforge-27b/acceptance/` (Independent audit reports).
- `reports/GAMEFORGE_V1_MODEL_DELIVERY_REPORT.md` (Historical delivery log of retired V1 model).
- `reports/gameforge_v1_evaluation_report.json` (V1 baseline evaluation metrics).

---

## 3. Codebase Cleanliness & Synchronization
1. `src/gameforge_bench/cli.py`: Updated parser default `--model` from `gameforge-v1` to `gameforge-27b-sft`.
2. `src/gameforge_bench/gameforge_cli.py`: Updated function signatures and interactive banner from `gameforge-v1` to `gameforge-27b-sft`.
3. `configs/engine_knowledge_registry.json`: Updated to version 2.0.0 with 2026 UE5.7, Unity 6 DOTS, and Godot 4.3 API families.
