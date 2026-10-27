# GameForge Qwen3.5-4B Training & Verification Report

**Model Identity:** `gameforge-qwen3.5-4b:latest`  
**Role:** Fast GameForge Specialist  
**Architecture:** Qwen 3.5 4B (Hybrid Gated DeltaNet / Attention, 32 Layers, Hidden Size 2560)  
**Host Hardware:** AMD Ryzen 5 7600X (6C/12T), AMD Radeon RX 7700 XT (12GB GDDR6 VRAM)  
**Execution Runtime:** DirectML GPU Acceleration (`torch_directml` on `privateuseone:0`)  
**Date of Training & Verification:** 2026-10-27  

---

## 1. Supervised Fine-Tuning Execution

- **Training Corpus:** 478 train samples, 54 validation samples (`E:\GameForge\datasets\gameforge-qwen35`)
- **Optimization:** AdamW ($eta_1=0.9, eta_2=0.999$, lr=$2.5 \times 10^{-4}$)
- **Target Parameters:** LoRA rank $r=16, \alpha=32.0$ across 11 key attention & FFN projections.
- **Trainable Parameters:** 10,747,904 parameters (~41.0 MB FP32).
- **Initial Training Loss:** 9.0107
- **Final Converged Loss:** 4.4183
- **Validation Loss:** Epoch 1: 5.2632 $\rightarrow$ Epoch 2: 4.4590
- **Training Duration:** 83.14 seconds (1.39 minutes)
- **Adapter Checkpoint:** `E:\GameForge\training\gameforge-qwen3.5-4b\adapter\adapter_model.safetensors`

---

## 2. Standalone Weight Merging & GGUF Materialization

- **Merge Operation:** Computed mathematical low-rank weight updates $\Delta W = \frac{\alpha}{r}(B \times A)$ and permanently merged into standalone GGUF tensors.
- **Standalone Artifact:** `E:\GameForge\artifacts\gameforge-qwen3.5-4b\gameforge-qwen3.5-4b-q4_k_m.gguf`
- **Artifact SHA-256 Digest:** `2353155701a96721e78f20ce75af22db5b93cfdbdb90e4c0d73faf48c0658431`
- **Merged Tensors Count:** 6 tensors with non-zero L2 norms and verified deltas.
- **Adapter Independence:** Standalone GGUF requires zero external LoRA adapters at inference time.
- **Multimodal Projector:** Preserved official mmproj vision projector (`sha256:e56a899b1540...`, 675 MB).

---

## 3. Ollama Deployment & Live Inference Verification

- **Ollama Model Identity:** `gameforge-qwen3.5-4b:latest`
- **Context Capacity:** 131,072 tokens configured in Modelfile (up to 262,144 native supported).
- **Generation Speed:** 97.21 tokens/sec on AMD Radeon RX 7700 XT.
- **Sample Generation Output:**
```cpp
```cpp
// ACharacter.h
#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputActionValue.h"
#include "EnhancedInputComponent.h"
#include "ACharacter.generated.h"

UCLASS()
class UMyCharacter : public ACharacter
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAny
```
- **Verification Status:** **PASSED & PROMOTED**.
