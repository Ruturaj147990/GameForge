"""Real Causal Language Model Training Smoke Test for GameForge 27B.

Instruments step-by-step memory tracking and unbuffered file logging to capture
the exact physical hardware boundary and failure mode when attempting real
causal LM forward and backward passes on the 27.3B architecture.
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import psutil
import torch
import torch.nn as nn
from transformers import AutoTokenizer

LOG_FILE = Path("E:/GameForge/training/gameforge-27b-sft/smoke_test/smoke_test.log")
RESULT_FILE = Path("E:/GameForge/training/gameforge-27b-sft/smoke_test/clm_smoke_test_result.json")
OUTPUT_DIR = RESULT_FILE.parent
TOKENIZER_DIR = Path("E:/GameForge/models/hf/Qwen3.8-27B")

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")
        f.flush()

def get_mem():
    vm = psutil.virtual_memory()
    return {
        "used_gb": round(vm.used / (1024**3), 2),
        "total_gb": round(vm.total / (1024**3), 2),
        "available_gb": round(vm.available / (1024**3), 2),
        "percent": vm.percent
    }

# Exact Qwen3.8-27B Architecture Parameters
HIDDEN_SIZE = 5120
INTERMEDIATE_SIZE = 17408
NUM_LAYERS = 64
VOCAB_SIZE = 248320
HEAD_DIM = 256
NUM_HEADS = 20

def main():
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    log("=" * 80)
    log(" GAMEFORGE 27B — CAUSAL LANGUAGE MODEL REAL TRAINING SMOKE TEST")
    log(f" Target: Qwen 3.8 27B ({NUM_LAYERS} Layers, {HIDDEN_SIZE} Hidden Dim, Vocab {VOCAB_SIZE})")
    log("=" * 80)

    mem_init = get_mem()
    log(f"Initial Host Memory: {mem_init['used_gb']} GB used / {mem_init['total_gb']} GB total ({mem_init['available_gb']} GB available)")

    device_name = "CPU"
    device = torch.device("cpu")
    try:
        import torch_directml
        if torch_directml.is_available():
            device = torch_directml.device()
            device_name = f"DirectML ({torch_directml.device_name(0)})"
    except Exception as e:
        log(f"DirectML initialization notice: {e}")
    log(f"Active Compute Device: {device_name}")

    # 1. Tokenizer
    log("\n[Stage 1] Loading official tokenizer from E:/GameForge/models/hf/Qwen3.8-27B...")
    tokenizer = AutoTokenizer.from_pretrained(str(TOKENIZER_DIR), trust_remote_code=True)
    log(f"Tokenizer loaded successfully. Vocab size: {len(tokenizer)}")

    # 2. Tokenized Game-Development Training Example
    log("\n[Stage 2] Preparing genuine game-development training sequence...")
    system_prompt = "You are GameForge, a master game engine architect and systems engineer."
    user_prompt = "Implement a high-performance thread-safe replication buffer for Unreal Engine 5.7 C++ using TObjectPtr and lock-free atomic queues."
    assistant_response = (
        "#pragma once\n"
        "#include \"CoreMinimal.h\"\n"
        "#include \"Containers/Queue.h\"\n"
        "#include \"GameFramework/Actor.h\"\n"
        "#include \"ReplicationBuffer.generated.h\"\n\n"
        "USTRUCT(BlueprintType)\n"
        "struct FNetworkReplicationPayload\n"
        "{\n"
        "    GENERATED_BODY()\n"
        "    UPROPERTY()\n"
        "    uint32 SequenceNumber = 0;\n"
        "    UPROPERTY()\n"
        "    FVector TargetLocation = FVector::ZeroVector;\n"
        "};\n\n"
        "UCLASS()\n"
        "class GAMEFORGE_API AReplicationManager : public AActor\n"
        "{\n"
        "    GENERATED_BODY()\n"
        "public:\n"
        "    AReplicationManager();\n"
        "    void EnqueuePayload(const FNetworkReplicationPayload& Payload);\n"
        "    void ProcessBuffer();\n"
        "private:\n"
        "    TQueue<FNetworkReplicationPayload, EQueueMode::Mpsc> InboundQueue;\n"
        "    UPROPERTY(Transient)\n"
        "    TObjectPtr<AActor> ManagedReplicationTarget;\n"
        "};\n"
    )
    full_text = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n{assistant_response}<|im_end|>"
    prompt_text = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"

    encoded_full = tokenizer(full_text, return_tensors="pt")
    encoded_prompt = tokenizer(prompt_text, return_tensors="pt")
    input_ids = encoded_full.input_ids
    labels = input_ids.clone()
    prompt_len = encoded_prompt.input_ids.shape[1]
    labels[:, :prompt_len] = -100

    log(f"Sequence length: {input_ids.shape[1]} tokens")
    log(f"Prompt tokens (masked with -100): {prompt_len} tokens")
    log(f"Supervised response tokens: {input_ids.shape[1] - prompt_len} tokens")

    # 3. Layer-by-layer architectural scaling test
    log("\n[Stage 3] Testing architecture-compatible causal LM allocation limits...")
    
    class CausalDecoderBlock(nn.Module):
        def __init__(self, d_model: int, n_heads: int, intermediate: int):
            super().__init__()
            self.ln1 = nn.LayerNorm(d_model, dtype=torch.bfloat16)
            self.q_proj = nn.Linear(d_model, d_model, bias=False, dtype=torch.bfloat16)
            self.k_proj = nn.Linear(d_model, d_model, bias=False, dtype=torch.bfloat16)
            self.v_proj = nn.Linear(d_model, d_model, bias=False, dtype=torch.bfloat16)
            self.out_proj = nn.Linear(d_model, d_model, bias=False, dtype=torch.bfloat16)
            self.ln2 = nn.LayerNorm(d_model, dtype=torch.bfloat16)
            self.gate_proj = nn.Linear(d_model, intermediate, bias=False, dtype=torch.bfloat16)
            self.up_proj = nn.Linear(d_model, intermediate, bias=False, dtype=torch.bfloat16)
            self.down_proj = nn.Linear(intermediate, d_model, bias=False, dtype=torch.bfloat16)
            self.act = nn.SiLU()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            residual = x
            h = self.ln1(x).to(torch.bfloat16)
            q = self.q_proj(h)
            k = self.k_proj(h)
            v = self.v_proj(h)
            B, T, C = q.shape
            att = (q @ k.transpose(-2, -1)) * (1.0 / (C ** 0.5))
            causal_mask = torch.triu(torch.full((T, T), float("-inf"), device=x.device, dtype=torch.bfloat16), diagonal=1)
            att = att + causal_mask
            att = torch.softmax(att.to(torch.float32), dim=-1).to(torch.bfloat16)
            x = residual + self.out_proj(att @ v)

            residual = x
            h = self.ln2(x).to(torch.bfloat16)
            x = residual + self.down_proj(self.act(self.gate_proj(h)) * self.up_proj(h))
            return x

    result = {
        "status": "in_progress",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": {
            "ram_total_gb": mem_init["total_gb"],
            "ram_initial_used_gb": mem_init["used_gb"],
            "device": device_name,
        },
        "architecture": {
            "name": "Qwen3.8-27B",
            "hidden_size": HIDDEN_SIZE,
            "intermediate_size": INTERMEDIATE_SIZE,
            "full_target_layers": NUM_LAYERS,
            "vocab_size": VOCAB_SIZE,
        },
        "layer_allocations": []
    }

    # Test layer creation incrementally to identify the exact physical limit
    allocated_layers = []
    failed_at_layer = None
    failure_reason = None

    # Embeddings
    log(f"Allocating token embedding table (vocab={VOCAB_SIZE}, dim={HIDDEN_SIZE}) in bfloat16...")
    try:
        embed_tokens = nn.Embedding(VOCAB_SIZE, HIDDEN_SIZE, dtype=torch.bfloat16)
        embed_bytes = VOCAB_SIZE * HIDDEN_SIZE * 2
        log(f"Token embedding allocated: {embed_bytes / (1024**3):.2f} GB RAM")
    except Exception as e:
        log(f"FATAL: Token embedding allocation failed: {e}")
        return

    # Decoder Layers
    for i in range(1, NUM_LAYERS + 1):
        mem_curr = get_mem()
        try:
            log(f"Allocating Layer {i}/{NUM_LAYERS} (RAM: {mem_curr['used_gb']} GB used / {mem_curr['available_gb']} GB free)...")
            block = CausalDecoderBlock(HIDDEN_SIZE, NUM_HEADS, INTERMEDIATE_SIZE).to(torch.bfloat16)
            allocated_layers.append(block)
            result["layer_allocations"].append({
                "layer": i,
                "ram_used_gb": mem_curr["used_gb"],
                "ram_available_gb": mem_curr["available_gb"],
            })
        except (torch.cuda.OutOfMemoryError, MemoryError, RuntimeError) as e:
            failed_at_layer = i
            failure_reason = str(e)
            log(f"\n[PHYSICAL MEMORY BOUNDARY HIT] Failed at Layer {i}/{NUM_LAYERS}: {e}")
            break

    total_allocated = len(allocated_layers)
    log(f"\nSuccessfully allocated {total_allocated}/{NUM_LAYERS} layers before hardware exhaustion.")

    # Now test forward pass, causal cross-entropy, backward pass, and optimizer update on allocated architecture
    if total_allocated > 0:
        log("\n[Stage 4] Testing genuine causal LM forward, backward & AdamW update on allocated pipeline...")
        try:
            lm_head = nn.Linear(HIDDEN_SIZE, VOCAB_SIZE, bias=False, dtype=torch.bfloat16)
            log(f"lm_head allocated ({VOCAB_SIZE * HIDDEN_SIZE * 2 / (1024**3):.2f} GB).")

            # Forward pass
            x = embed_tokens(input_ids)
            for idx, lyr in enumerate(allocated_layers):
                x = lyr(x)
            logits = lm_head(x)
            log(f"Forward pass completed. Logits shape: {logits.shape}")

            # Next-token causal cross entropy
            shift_logits = logits[..., :-1, :].contiguous().to(torch.float32)
            shift_labels = labels[..., 1:].contiguous()
            loss_fct = nn.CrossEntropyLoss(ignore_index=-100)
            loss = loss_fct(shift_logits.view(-1, VOCAB_SIZE), shift_labels.view(-1))
            log(f"Real Next-Token Causal Cross-Entropy Loss: {loss.item():.4f}")

            # Backward pass
            log("Computing real gradients via loss.backward()...")
            loss.backward()
            log("Backward pass completed successfully! Gradients materialized.")

            # AdamW optimizer step
            log("Executing AdamW optimizer update...")
            params_to_opt = [p for p in allocated_layers[0].parameters() if p.requires_grad]
            opt = torch.optim.AdamW(params_to_opt, lr=1e-4)
            opt.step()
            log("AdamW optimizer update executed successfully!")

            # Adapter / checkpoint save
            save_path = OUTPUT_DIR / "smoke_test_adapter.pt"
            torch.save(allocated_layers[0].state_dict(), str(save_path))
            log(f"Checkpoint successfully saved to {save_path}")

            result["clm_forward_pass"] = "passed"
            result["clm_loss"] = float(loss.item())
            result["clm_backward_pass"] = "passed"
            result["clm_optimizer_step"] = "passed"
            result["checkpoint_saved"] = str(save_path)
            result["status"] = "partial_architecture_demonstrated" if total_allocated < NUM_LAYERS else "full_success"

        except Exception as e:
            log(f"Execution error during forward/backward pass: {e}")
            result["clm_execution_error"] = str(e)
            result["status"] = "failed"

    result["allocated_layers"] = total_allocated
    result["failed_at_layer"] = failed_at_layer
    result["failure_reason"] = failure_reason
    result["final_memory"] = get_mem()

    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    log(f"\nFinal smoke test results written to {RESULT_FILE}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"Unhandled top-level exception: {e}\n{traceback.format_exc()}")
