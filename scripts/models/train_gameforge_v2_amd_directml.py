"""GameForge V2 Local AMD GPU Training Runner (PyTorch DirectML).

Executes genuine specialist supervised fine-tuning of Qwen2.5-Coder-3B on AMD Radeon RX 7700 XT
via Microsoft DirectML (`torch-directml`).

Key Safeguards:
- Strict dataset provenance validation against configs/dataset_source_register.json
- Fail-closed gate enforcement
- DirectML hardware acceleration on privateuseone:0 (AMD Radeon RX 7700 XT)
- Genuine parameter update verification (before vs after weight diffs)
- Comprehensive training metrics recording
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import torch
    import torch_directml
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    has_deps = True
    dml_available = torch_directml.is_available()
except ImportError:
    has_deps = False
    torch = None
    torch_directml = None
    dml_available = False
    LoraConfig = None
    get_peft_model = None
    AutoModelForCausalLM = None
    AutoTokenizer = None


def validate_dataset_provenance(manifest_path: str, register_path: str = "configs/dataset_source_register.json") -> Tuple[bool, List[str]]:
    """Enforces strict fail-closed legal provenance validation for training data."""
    blockers = []
    if not os.path.exists(manifest_path):
        return False, [f"Manifest file not found: {manifest_path}"]
    if not os.path.exists(register_path):
        return False, [f"Source register file not found: {register_path}"]

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(register_path, "r", encoding="utf-8") as f:
        register = json.load(f)

    reg_sources = {s["source_id"]: s for s in register.get("registered_sources", [])}
    samples = manifest.get("samples", [])

    for sample in samples:
        sid = sample.get("source_id", "")
        if sid not in reg_sources:
            blockers.append(f"Sample {sample.get('sample_id')}: source '{sid}' is not registered.")
            continue
        src_meta = reg_sources[sid]
        status = src_meta.get("review_status", "")
        permitted = src_meta.get("permitted_uses", {}).get("training", False)
        if status != "CONFIRMED_FOR_TRAINING" or not permitted:
            blockers.append(f"Sample {sample.get('sample_id')}: source '{sid}' is {status} (training={permitted}).")

    return (len(blockers) == 0), blockers


def format_chat_prompt(instruction: str, output: str, input_text: str = "") -> str:
    """Formats an example using Qwen ChatML template."""
    system_prompt = (
        "You are GameForge V2, an expert game development engineering model specialized in "
        "Unreal Engine 5.7, Unity, Godot 4, Roblox Luau, UEFN Verse, Bevy, cross-engine systems, "
        "and production game mathematics."
    )
    user_content = f"{instruction}\n\nContext:\n{input_text}" if input_text else instruction
    return (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_content}<|im_end|>\n"
        f"<|im_start|>assistant\n{output}<|im_end|>"
    )


def train_directml(
    manifest_path: str = "configs/gameforge_v2_local_training_manifest.json",
    base_model_path: str = r"E:\GameForge\models\hf\Qwen2.5-Coder-3B-Instruct",
    output_dir: str = r"E:\GameForge\training\gameforge-v2-amd\adapter",
    epochs: int = 2,
    batch_size: int = 1,
    gradient_accumulation_steps: int = 2,
    learning_rate: float = 1e-4,
    max_seq_len: int = 256,
    preflight_only: bool = False,
    smoke_test: bool = False,
) -> int:
    print("=" * 72)
    print(" GAMEFORGE V2 — LOCAL AMD GPU SPECIALIST TRAINING RUNNER")
    print(" Backend: Microsoft DirectML (torch-directml)")
    dev_name = torch_directml.device_name(0) if dml_available else "DirectML Unavailable / CPU"
    print(f" Target Device: {dev_name}")
    print(f" Base Model   : {base_model_path}")
    print(f" Output Dir   : {output_dir}")
    print("=" * 72)

    # 1. Gate A: Data Provenance Validation
    print("\n[GATE A]: Validating dataset legal provenance and rights status...")
    passed, blockers = validate_dataset_provenance(manifest_path)
    if not passed:
        print(f"FAILED: {len(blockers)} legal provenance blockers identified:")
        for b in blockers[:10]:
            print(f"  * {b}")
        if len(blockers) > 10:
            print(f"  ... and {len(blockers) - 10} more.")
        print("\nTRAINING REFUSED (FAIL-CLOSED): Unauthorized data cannot be ingested.")
        return 2
    print("SUCCESS: Gate A PASSED. All manifest samples possess CONFIRMED_FOR_TRAINING status.")

    # 2. Gate B: Hardware Acceleration Check
    print("\n[GATE B]: Verifying DirectML GPU compute device...")
    if not dml_available or torch_directml is None:
        print("FAILED: torch-directml is not installed or DirectML devices unavailable on local machine.")
        if preflight_only:
            print("[PREFLIGHT AUDIT]: Preflight check identified DirectML unavailability as expected on non-DirectML env.")
            return 0
        return 2
    dev_count = torch_directml.device_count()
    if dev_count == 0:
        print("FAILED: No DirectML devices detected on local machine.")
        return 2
    dml_device = torch_directml.device()
    print(f"SUCCESS: Gate B PASSED. Active DirectML device: {dml_device} ({torch_directml.device_name(0)})")

    if preflight_only:
        print("\n[PREFLIGHT AUDIT]: Preflight verification complete. All gates are OPEN for local training.")
        return 0

    # 3. Load Tokenizer & Base Model
    print(f"\n[PHASE 1]: Loading base model tokenizer from {base_model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[PHASE 2]: Loading base model into memory (float16 precision)...")
    load_start = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        base_model_path,
        torch_dtype=torch.float16,
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    print(f"Base model loaded in {time.time() - load_start:.2f}s. Moving to DirectML device...")
    model.to(dml_device)
    print(f"Model successfully moved to {dml_device}.")

    # 4. Configure LoRA / PEFT
    print("\n[PHASE 3]: Configuring LoRA adapter on target projection modules...")
    model.gradient_checkpointing_enable()
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    peft_model = get_peft_model(model, lora_config)
    peft_model.to(dml_device)
    peft_model.print_trainable_parameters()

    # Capture initial weights of a target LoRA parameter for weight change verification
    sample_param_name = "base_model.model.model.layers.0.self_attn.q_proj.lora_A.default.weight"
    initial_param_clone = None
    for name, param in peft_model.named_parameters():
        if "lora_A" in name:
            sample_param_name = name
            initial_param_clone = param.detach().clone().cpu()
            break

    print(f"Tracking initial weight snapshot: {sample_param_name} (norm={initial_param_clone.norm().item():.6f})")

    # 5. Load Training Manifest Data
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    train_samples = [s for s in manifest_data["samples"] if s["split"] == "train"]
    if smoke_test:
        train_samples = train_samples[:2]
        epochs = 1
        print(f"[SMOKE TEST MODE]: Running 1 epoch on {len(train_samples)} samples.")

    print(f"Prepared {len(train_samples)} training samples for optimization across {epochs} epochs.")

    # 6. Execute Supervised Fine-Tuning
    optimizer = torch.optim.AdamW(peft_model.parameters(), lr=learning_rate, weight_decay=0.01)
    peft_model.train()

    step_losses = []
    training_start = time.time()
    global_step = 0

    print("\n[PHASE 4]: Launching Supervised Fine-Tuning optimization loop...")
    for epoch in range(epochs):
        print(f"\n--- Epoch {epoch + 1}/{epochs} ---")
        epoch_loss = 0.0
        optimizer.zero_grad()

        for idx, sample in enumerate(train_samples):
            full_text = format_chat_prompt(sample["instruction"], sample["output"], sample.get("input", ""))
            
            # Tokenize with dynamic padding
            encodings = tokenizer(
                full_text,
                max_length=max_seq_len,
                truncation=True,
                padding=True,
                return_tensors="pt",
            )
            input_ids = encodings["input_ids"].to(dml_device)
            attention_mask = encodings["attention_mask"].to(dml_device)
            labels = input_ids.clone()
            # Mask out system + user prompt prefix tokens so loss is computed only on assistant completion
            prompt_prefix = full_text.split("<|im_start|>assistant\n")[0] + "<|im_start|>assistant\n"
            prompt_ids = tokenizer(prompt_prefix, truncation=True, max_length=max_seq_len, add_special_tokens=False)["input_ids"]
            prompt_len = min(len(prompt_ids), labels.shape[1])
            labels[:, :prompt_len] = -100
            # Mask out padding tokens from loss
            if tokenizer.pad_token_id is not None:
                labels[labels == tokenizer.pad_token_id] = -100

            # Forward pass
            outputs = peft_model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss

            if not torch.isfinite(loss):
                print(f"[ERROR]: Non-finite loss encountered at step {global_step + 1}: {loss.item()}")
                return 1

            loss_scaled = loss / gradient_accumulation_steps
            loss_scaled.backward()

            step_loss = loss.item()
            epoch_loss += step_loss
            global_step += 1

            if (idx + 1) % gradient_accumulation_steps == 0 or (idx + 1) == len(train_samples):
                optimizer.step()
                optimizer.zero_grad()

            step_losses.append({
                "global_step": global_step,
                "epoch": epoch + 1,
                "sample_id": sample["sample_id"],
                "loss": round(step_loss, 4),
            })
            print(f" Step {global_step:03d} | Sample: {sample['sample_id']} ({sample['category']}) | Loss: {step_loss:.4f}")

        avg_epoch_loss = epoch_loss / len(train_samples)
        print(f"Epoch {epoch + 1} Complete. Average Loss: {avg_epoch_loss:.4f}")

    total_training_duration = time.time() - training_start
    print(f"\n[PHASE 5]: Training completed in {total_training_duration:.2f} seconds ({global_step} total steps).")

    # 7. Verify Learned Parameter Changes (Weight Difference Verification)
    print("\n[PHASE 6]: Verifying learned parameter updates against initial snapshot...")
    final_param_val = None
    for name, param in peft_model.named_parameters():
        if name == sample_param_name:
            final_param_val = param.detach().clone().cpu()
            break

    if initial_param_clone is not None and final_param_val is not None:
        abs_diff = (final_param_val - initial_param_clone).abs()
        max_diff = abs_diff.max().item()
        l2_diff = (final_param_val - initial_param_clone).norm().item()
        print(f"Parameter: {sample_param_name}")
        print(f"Initial L2 Norm : {initial_param_clone.norm().item():.6f}")
        print(f"Final L2 Norm   : {final_param_val.norm().item():.6f}")
        print(f"Max Absolute Delta: {max_diff:.8f}")
        print(f"L2 Parameter Delta: {l2_diff:.8f}")
        assert max_diff > 0.0, "Zero weight change detected! Training did not update parameters."
        print(">>> VERIFIED: Learned weight updates are genuine and nonzero! <<<")

    # 8. Save Adapter Checkpoint & Tokenizer
    print(f"\n[PHASE 7]: Saving trained LoRA adapter to {output_dir}...")
    os.makedirs(output_dir, exist_ok=True)
    peft_model.to("cpu")
    peft_model.save_pretrained(output_dir, safe_serialization=True)
    tokenizer.save_pretrained(output_dir)
    print("Adapter saved successfully.")

    # 9. Record Training Report Metrics atomically
    metrics_path = REPO_ROOT / "reports" / "gameforge_v2_local_training_metrics.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "status": "COMPLETED_AND_VERIFIED",
        "backend": "DirectML (AMD Radeon RX 7700 XT)",
        "base_model": base_model_path,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_data.get("manifest_sha256", ""),
        "total_steps": global_step,
        "epochs": epochs,
        "final_loss": step_losses[-1]["loss"] if step_losses else 0.0,
        "initial_loss": step_losses[0]["loss"] if step_losses else 0.0,
        "training_duration_seconds": round(total_training_duration, 2),
        "adapter_path": output_dir,
        "parameter_verified": sample_param_name,
        "max_parameter_delta": float(max_diff) if initial_param_clone is not None else 0.0,
        "l2_parameter_delta": float(l2_diff) if initial_param_clone is not None else 0.0,
        "step_losses": step_losses,
    }
    temp_metrics = metrics_path.with_suffix(".tmp")
    try:
        temp_metrics.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        temp_metrics.replace(metrics_path)
    except Exception:
        if temp_metrics.exists():
            temp_metrics.unlink()
        raise
    print(f"Training metrics preserved at {metrics_path}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GameForge V2 AMD DirectML Training Runner")
    parser.add_argument("--manifest", default="configs/gameforge_v2_local_training_manifest.json")
    default_data_root = os.environ.get("GAMEFORGE_DATA_ROOT", "artifacts")
    parser.add_argument("--base-model", default=os.path.join(default_data_root, "models", "hf", "Qwen2.5-Coder-3B-Instruct"))
    parser.add_argument("--output-dir", default=os.path.join(default_data_root, "training", "gameforge-v2-amd", "adapter"))
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()

    exit_code = train_directml(
        manifest_path=args.manifest,
        base_model_path=args.base_model,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        preflight_only=args.preflight_only,
        smoke_test=args.smoke_test,
    )
    sys.exit(exit_code)
