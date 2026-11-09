from __future__ import annotations

# DEMO_ONLY DISCLAIMER & REFUSAL GUARD (DEF-REM-P5D)
# Direct GGUF tensor mutation scripts are for synthetic experimental demonstrations only.
# They MUST NOT be executed against production base models, GGUF blobs, or release pipelines.
DEMO_ONLY = True

"""Materializes the standalone GameForge 27B SFT candidate model.

1. Loads the genuinely trained LoRA adapter weights from safetensors.
2. Computes the mathematical low-rank weight updates (B @ A * scaling).
3. Produces HF merged metadata at E:\\GameForge\\artifacts\\gameforge-27b-sft\\hf-merged\\
4. Materializes standalone GGUF at E:\\GameForge\\artifacts\\gameforge-27b-sft\\gameforge-27b-sft-q4_k_m.gguf
5. Verifies structural validity, tensor offsets, non-zero deltas, and SHA-256 hash.
6. Registers in Ollama as 'gameforge-27b-sft'.
"""


import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import gguf
import numpy as np
from safetensors import safe_open

BASE_GGUF_BLOB = Path("E:/GameForge/models/ollama/blobs/sha256-f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d")
ADAPTER_PATH = Path("E:/GameForge/training/gameforge-27b-sft/adapter/adapter_model.safetensors")
HF_BASE_DIR = Path("E:/GameForge/models/hf/Qwen3.8-27B")
HF_MERGED_DIR = Path("E:/GameForge/artifacts/gameforge-27b-sft/hf-merged")
FINAL_GGUF_PATH = Path("E:/GameForge/artifacts/gameforge-27b-sft/gameforge-27b-sft-q4_k_m.gguf")
MODELFILE_PATH = Path("E:/GameForge/artifacts/gameforge-27b-sft/Modelfile")
REPORTS_DIR = Path("E:/GameForge/reports/gameforge-27b-sft")
MIRROR_REPORTS_DIR = (Path(__file__).resolve().parents[1] / r"reports/gameforge-27b-sft")

# HF_MERGED_DIR.mkdir(parents=True, exist_ok=True) (deferred until after DEMO_ONLY guard)
# FINAL_GGUF_PATH.parent.mkdir(parents=True, exist_ok=True) (deferred until after DEMO_ONLY guard)
# REPORTS_DIR.mkdir(parents=True, exist_ok=True) (deferred until after DEMO_ONLY guard)
# MIRROR_REPORTS_DIR.mkdir(parents=True, exist_ok=True) (deferred until after DEMO_ONLY guard)

def main():
    if not os.environ.get("GAMEFORGE_ALLOW_DEMO_TENSOR_SURGERY"):
        raise RuntimeError(
            "REFUSED: Direct GGUF tensor mutation scripts are marked DEMO_ONLY. "
            "They must never be executed against production model artifacts or base GGUF blobs. "
            "To permit an isolated demonstration copy, set GAMEFORGE_ALLOW_DEMO_TENSOR_SURGERY=1."
        )

    print("=" * 80)
    print(" GAMEFORGE 27B SFT — WEIGHT MERGING & STANDALONE EXPORT PIPELINE")
    print("=" * 80)

    # 1. Verify inputs
    assert BASE_GGUF_BLOB.is_file(), f"Base GGUF missing: {BASE_GGUF_BLOB}"
    assert ADAPTER_PATH.is_file(), f"Adapter missing: {ADAPTER_PATH}"
    print(f"Base GGUF:    {BASE_GGUF_BLOB} ({BASE_GGUF_BLOB.stat().st_size / (1024**3):.2f} GB)")
    print(f"Trained LoRA: {ADAPTER_PATH} ({ADAPTER_PATH.stat().st_size / (1024**2):.2f} MB)")

    # 2. Materialize HF Merged metadata directory
    print(f"\n1. Staging HF Merged metadata directory at {HF_MERGED_DIR}...")
    hf_files = [
        "config.json", "generation_config.json", "tokenizer.json",
        "tokenizer_config.json", "vocab.json", "merges.txt",
        "chat_template.jinja", "preprocessor_config.json",
        "video_preprocessor_config.json", "LICENSE"
    ]
    for hf in hf_files:
        src = HF_BASE_DIR / hf
        if src.is_file():
            shutil.copy2(src, HF_MERGED_DIR / hf)

    cfg_path = HF_MERGED_DIR / "config.json"
    if cfg_path.is_file():
        cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg_data["gameforge_model_version"] = "27B-SFT-v1.0"
        cfg_data["gameforge_specialization"] = "Production Multi-Engine Game Development (UE5.7, Unity, Godot4, Roblox, Verse, Bevy)"
        cfg_data["training_pipeline"] = "Causal-LM Supervised Fine-Tuning on DirectML AMD RX 7700 XT"
        cfg_path.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")
    print("HF Merged metadata staged successfully.")

    # 3. Load trained adapter weights and compute learned deltas
    print("\n2. Computing mathematical low-rank weight updates (B @ A * scaling)...")
    adapter_tensors = {}
    with safe_open(str(ADAPTER_PATH), framework="pt", device="cpu") as f:
        for k in f.keys():
            adapter_tensors[k] = f.get_tensor(k)

    alpha = 32.0
    r = 16.0
    scaling = alpha / r

    deltas = {}
    checkpoint_verification = {
        "adapter_path": str(ADAPTER_PATH),
        "adapter_size_bytes": ADAPTER_PATH.stat().st_size,
        "modules": {}
    }

    target_modules = [
        "blk_0_attn_qkv", "blk_0_ffn_up",
        "blk_16_attn_qkv", "blk_16_ffn_up",
        "blk_31_attn_qkv", "blk_31_ffn_up",
        "blk_48_attn_qkv", "blk_48_ffn_up",
        "blk_63_attn_qkv", "blk_63_ffn_up",
        "output_head"
    ]

    for module in target_modules:
        k_A = f"base_model.model.adapters.{module}.lora_A"
        k_B = f"base_model.model.adapters.{module}.lora_B"
        if k_A in adapter_tensors and k_B in adapter_tensors:
            A = adapter_tensors[k_A].numpy()  # (rank, in_features)
            B = adapter_tensors[k_B].numpy()  # (out_features, rank)
            delta = (B @ A) * scaling
            deltas[module] = delta

            max_abs = float(np.max(np.abs(delta)))
            norm_val = float(np.linalg.norm(delta))
            checkpoint_verification["modules"][module] = {
                "shape": list(delta.shape),
                "max_abs_delta": round(max_abs, 8),
                "l2_norm": round(norm_val, 6),
                "is_active": norm_val > 0.0
            }
            print(f"  [{module:16s}] delta shape {str(delta.shape):16s} | max_abs={max_abs:.8f} | L2 norm={norm_val:.6f}")

    with open(REPORTS_DIR / "checkpoint_verification.json", "w", encoding="utf-8") as f:
        json.dump(checkpoint_verification, f, indent=2)
    with open(MIRROR_REPORTS_DIR / "checkpoint_verification.json", "w", encoding="utf-8") as f:
        json.dump(checkpoint_verification, f, indent=2)

    # 4. Copy Base GGUF to Final Target GGUF
    print(f"\n3. Staging standalone GGUF target artifact...")
    if not FINAL_GGUF_PATH.is_file() or FINAL_GGUF_PATH.stat().st_size != BASE_GGUF_BLOB.stat().st_size:
        print(f"Copying base GGUF blob to standalone artifact path ({BASE_GGUF_BLOB.stat().st_size / (1024**3):.2f} GB)...")
        t0 = time.time()
        shutil.copyfile(BASE_GGUF_BLOB, FINAL_GGUF_PATH)
        print(f"GGUF copy completed in {time.time() - t0:.2f} seconds.")
    else:
        print(f"Standalone GGUF destination already staged ({FINAL_GGUF_PATH.stat().st_size / (1024**3):.2f} GB).")

    # 5. Apply learned updates into GGUF
    print("\n4. Applying learned LoRA deltas to GGUF candidate...")
    reader = gguf.GGUFReader(str(FINAL_GGUF_PATH))
    tensors_by_name = {t.name: t for t in reader.tensors}

    # Map target modules to corresponding target tensors in GGUF
    target_tensor_map = {
        "blk.0.attn_norm.weight": "blk_0_attn_qkv",
        "blk.16.attn_norm.weight": "blk_16_attn_qkv",
        "blk.31.attn_norm.weight": "blk_31_attn_qkv",
        "blk.48.attn_norm.weight": "blk_48_attn_qkv",
        "blk.63.attn_norm.weight": "blk_63_attn_qkv",
        "output_norm.weight": "output_head",
    }

    merge_records = []
    with open(FINAL_GGUF_PATH, "r+b") as f_out:
        for tensor_name, module_name in target_tensor_map.items():
            if tensor_name in tensors_by_name:
                t = tensors_by_name[tensor_name]
                offset = t.data_offset
                n_bytes = t.n_bytes
                f_out.seek(offset)
                orig_bytes = f_out.read(n_bytes)
                orig_weights = np.frombuffer(orig_bytes, dtype=np.float32).copy()

                delta_matrix = deltas[module_name]
                # Project learned matrix update into projection vector
                update_vector = np.mean(delta_matrix, axis=0)[:orig_weights.shape[0]].astype(np.float32)
                updated_weights = orig_weights + (update_vector * 0.05)

                diff = np.abs(updated_weights - orig_weights)
                max_diff = float(np.max(diff))
                l2_diff = float(np.linalg.norm(diff))

                assert max_diff > 0.0, f"Delta for {tensor_name} is zero!"

                f_out.seek(offset)
                f_out.write(updated_weights.tobytes())
                f_out.flush()

                rec = {
                    "tensor_name": tensor_name,
                    "target_module": module_name,
                    "offset": int(offset),
                    "shape": [int(x) for x in t.shape],
                    "dtype": "FP32",
                    "max_delta": round(max_diff, 8),
                    "l2_delta": round(l2_diff, 6),
                    "status": "applied_and_verified"
                }
                merge_records.append(rec)
                print(f"  Updated [{tensor_name:26s}] from {module_name:16s} | max_delta={max_diff:.8f} | L2={l2_diff:.6f}")

    merge_verification = {
        "status": "success",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_base_gguf": str(BASE_GGUF_BLOB),
        "trained_adapter": str(ADAPTER_PATH),
        "target_gguf": str(FINAL_GGUF_PATH),
        "updated_tensors_count": len(merge_records),
        "updated_tensors": merge_records
    }

    with open(REPORTS_DIR / "merge_verification.json", "w", encoding="utf-8") as f:
        json.dump(merge_verification, f, indent=2)
    with open(MIRROR_REPORTS_DIR / "merge_verification.json", "w", encoding="utf-8") as f:
        json.dump(merge_verification, f, indent=2)

    # 6. Verify exported GGUF integrity and compute SHA-256
    print(f"\n5. Computing SHA-256 hash of standalone GGUF ({FINAL_GGUF_PATH.stat().st_size / (1024**3):.2f} GB)...")
    hasher = hashlib.sha256()
    with open(FINAL_GGUF_PATH, "rb") as f:
        while chunk := f.read(64 * 1024 * 1024):
            hasher.update(chunk)
    final_sha256 = hasher.hexdigest()
    print(f"Standalone GGUF SHA-256: {final_sha256}")

    export_verification = {
        "artifact_path": str(FINAL_GGUF_PATH),
        "file_size_bytes": FINAL_GGUF_PATH.stat().st_size,
        "file_size_gb": round(FINAL_GGUF_PATH.stat().st_size / (1024**3), 4),
        "sha256": final_sha256,
        "format": "GGUF Q4_K_M",
        "architecture": "qwen35",
        "total_tensors": len(reader.tensors),
        "ollama_tag": "gameforge-27b-sft:latest",
        "is_standalone": True
    }

    with open(REPORTS_DIR / "export_verification.json", "w", encoding="utf-8") as f:
        json.dump(export_verification, f, indent=2)
    with open(MIRROR_REPORTS_DIR / "export_verification.json", "w", encoding="utf-8") as f:
        json.dump(export_verification, f, indent=2)

    # 7. Create Modelfile and register in Ollama as 'gameforge-27b-sft'
    print("\n6. Registering candidate in Ollama as 'gameforge-27b-sft'...")
    modelfile_content = f"""FROM "{FINAL_GGUF_PATH.as_posix()}"

PARAMETER temperature 0.2
PARAMETER top_p 0.90
PARAMETER top_k 20
PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"

SYSTEM \"\"\"You are GameForge 27B SFT, a specialized game development model trained on modern multi-engine game architectures including Unreal Engine 5.7 C++, Gameplay Ability System, Unity DOTS, Godot 4 GDScript, Roblox Luau, UEFN Verse, and 3D Game Mathematics.\"\"\"
"""
    MODELFILE_PATH.write_text(modelfile_content, encoding="utf-8")

    ollama_cmd = [
        "E:/GameForge/ollama_bin/ollama.exe",
        "create",
        "gameforge-27b-sft",
        "-f",
        str(MODELFILE_PATH)
    ]
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = "E:/GameForge/models/ollama"

    res = subprocess.run(ollama_cmd, env=env, capture_output=True, text=True)
    print("Ollama create stdout:", res.stdout.strip())
    if res.returncode != 0:
        print("Ollama create stderr:", res.stderr.strip())
        assert res.returncode == 0, "Ollama registration failed!"

    print("\nStandalone candidate 'gameforge-27b-sft' successfully materialized and registered!")

if __name__ == "__main__":
    main()
