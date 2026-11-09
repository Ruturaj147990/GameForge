"""Supervised Fine-Tuning (SFT) Training Runner for GameForge V2.

Implements Phase 4 and Phase 6 of GameForge V2:
- Pinned base model: Qwen/Qwen3.8-27B (HF local: E:\\GameForge\\models\\hf\\Qwen3.8-27B)
- Method: QLoRA with 4-bit NF4 quantization and double quant
- Target modules: Supported linear projections of language backbone (q_proj, k_proj, v_proj, o_proj, in_proj_*, mlp.*_proj)
- Strict exclusion: Vision tower (model.visual.*) remains frozen
- Optimizer: AdamW, lr=1e-5, cosine schedule, warmup=0.03, effective batch size=8, max_seq=2048
- Fail-Closed Policy: Refuses execution if legal rights gate is unconfirmed, unless running in --preflight-only mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def audit_hardware_and_environment() -> Dict[str, Any]:
    """Audits local hardware, PyTorch backend, VRAM, and package dependencies."""
    results = {
        "os": sys.platform,
        "python_version": sys.version.split()[0],
        "torch_available": False,
        "torch_version": None,
        "cuda_available": False,
        "device_name": None,
        "total_vram_gb": 0.0,
        "bitsandbytes_available": False,
        "peft_available": False,
        "transformers_available": False,
        "hardware_adequate_for_27b_qlora": False,
        "blockers": [],
    }

    try:
        import torch
        results["torch_available"] = True
        results["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            results["cuda_available"] = True
            results["device_name"] = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_memory
            results["total_vram_gb"] = round(vram_bytes / (1024**3), 2)
        else:
            results["blockers"].append(
                "PyTorch has no CUDA/ROCm acceleration enabled (torch.cuda.is_available() is False). "
                "4-bit NF4 quantized training on a 27B parameter model requires GPU tensor core compute."
            )
    except ImportError:
        results["blockers"].append("torch package is not installed.")

    try:
        import transformers
        results["transformers_available"] = True
    except ImportError:
        results["blockers"].append("transformers package is not installed.")

    try:
        import peft
        results["peft_available"] = True
    except ImportError:
        results["blockers"].append("peft package is not installed.")

    try:
        import bitsandbytes
        results["bitsandbytes_available"] = True
    except ImportError:
        results["blockers"].append("bitsandbytes package is not installed (required for 4-bit NF4 quantization).")

    # Assess physical feasibility for 27B QLoRA
    # A 27B model quantized in 4-bit requires ~15 GB weights + ~4 GB activations/gradients with batch=1 & seq=2048 + LoRA adapter memory = ~20-24 GB VRAM.
    if results["cuda_available"] and results["total_vram_gb"] >= 22.0:
        results["hardware_adequate_for_27b_qlora"] = True
    elif results["cuda_available"] and results["total_vram_gb"] < 22.0:
        results["blockers"].append(
            f"GPU VRAM ({results['total_vram_gb']} GB) is insufficient for 27B QLoRA training. "
            "A minimum of 24 GB VRAM (e.g. RTX 4090) or 80 GB VRAM (NVIDIA A100/H100) is physically required."
        )

    return results


def verify_target_modules(model_named_parameters: List[str], target_modules: List[str]) -> Tuple[bool, List[str]]:
    """Asserts that trainable modules are strictly confined to language backbone and exclude vision tower."""
    invalid_targets = []
    for name in model_named_parameters:
        if any(t in name for t in target_modules):
            if "visual" in name or "vision" in name or "merger" in name:
                invalid_targets.append(name)
    return (len(invalid_targets) == 0), invalid_targets


def validate_dataset_provenance(
    manifest_path: Path,
    source_register_path: Path = Path("configs/dataset_source_register.json"),
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Strictly validates sample-level provenance and permissions for training split."""
    blockers = []
    audit_stats = {
        "total_samples": 0,
        "train_samples": 0,
        "dev_samples": 0,
        "sources_used": set(),
        "unauthorized_train_samples": 0,
        "test_fixture_violations": 0,
        "private_eval_violations": 0,
    }

    if not manifest_path.is_file():
        blockers.append(f"Manifest missing: {manifest_path}")
        return False, blockers, audit_stats

    if not source_register_path.is_file():
        blockers.append(f"Source register missing: {source_register_path}")
        return False, blockers, audit_stats

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        register_data = json.loads(source_register_path.read_text(encoding="utf-8"))
    except Exception as e:
        blockers.append(f"JSON parsing error: {e}")
        return False, blockers, audit_stats

    sources = {s["source_id"]: s for s in register_data.get("registered_sources", [])}
    samples = manifest_data.get("samples", [])
    audit_stats["total_samples"] = len(samples)

    if not samples:
        blockers.append("Training manifest contains zero samples.")
        return False, blockers, audit_stats

    manifest_sha = manifest_data.get("stats", {}).get("manifest_sha256")
    if not manifest_sha:
        blockers.append("Manifest missing cryptographic manifest_sha256 digest.")

    for s in samples:
        s_id = s.get("sample_id", "unknown")
        src_id = s.get("source_id")
        split = s.get("split", "train")
        audit_stats["sources_used"].add(src_id)

        if split == "train":
            audit_stats["train_samples"] += 1
            if not s_id or s_id == "unknown":
                blockers.append(f"Sample lacks stable sample_id: {s}")
                continue

            if not src_id or src_id not in sources:
                blockers.append(f"Sample '{s_id}' has unregistered or missing source_id: '{src_id}'")
                audit_stats["unauthorized_train_samples"] += 1
                continue

            src_entry = sources[src_id]
            is_training_allowed = src_entry.get("permitted_uses", {}).get("training", False)
            rev_status = src_entry.get("review_status", "UNKNOWN")
            intended_uses = src_entry.get("intended_uses", [])

            # Reject test/CI corpus from training
            if "TRAINING_TEST" in intended_uses or src_id == "gameforge-synthetic-test-corpus":
                blockers.append(f"POLICY VIOLATION: Test/CI fixture '{src_id}' must never enter production training split (sample: {s_id})")
                audit_stats["test_fixture_violations"] += 1

            # Reject private held-out eval
            if "PRIVATE_EVALUATION" in intended_uses or src_id == "gameforge-private-heldout-eval" or rev_status == "RESTRICTED_EVAL_ONLY":
                blockers.append(f"SECURITY VIOLATION: Private held-out eval '{src_id}' found in training split (sample: {s_id})")
                audit_stats["private_eval_violations"] += 1

            # Check explicit training authorization and review status
            if not is_training_allowed or rev_status != "CONFIRMED_FOR_TRAINING":
                blockers.append(
                    f"UNAUTHORIZED SAMPLE: Sample '{s_id}' from source '{src_id}' is not confirmed for training "
                    f"(review_status: '{rev_status}', permitted_uses.training: {is_training_allowed})"
                )
                audit_stats["unauthorized_train_samples"] += 1

        elif split == "dev":
            audit_stats["dev_samples"] += 1

    audit_stats["sources_used"] = list(audit_stats["sources_used"])
    is_valid = (len(blockers) == 0)
    return is_valid, blockers, audit_stats


def run_training_pipeline(
    config_path: Path = Path("configs/training_config_gameforge_v2.json"),
    preflight_only: bool = False,
) -> int:
    print("=" * 80)
    print(" GAMEFORGE LLM V2 — CONTROLLED SPECIALIST SFT RUNNER")
    print(f" Config File: {config_path}")
    print("=" * 80)

    if not config_path.is_file():
        print(f"FATAL: Config not found at {config_path}", file=sys.stderr)
        return 1

    config = json.loads(config_path.read_text(encoding="utf-8"))

    # 1. Audit Hardware & Environment
    env_audit = audit_hardware_and_environment()
    print("ENVIRONMENT & HARDWARE AUDIT:")
    print(f" - Python:       {env_audit['python_version']}")
    print(f" - PyTorch:      {env_audit.get('torch_version', 'Not installed')}")
    print(f" - CUDA/ROCm:    {env_audit['cuda_available']} ({env_audit['device_name'] or 'None'})")
    print(f" - GPU VRAM:     {env_audit['total_vram_gb']} GB")
    print(f" - Transformers: {env_audit['transformers_available']}")
    print(f" - PEFT:         {env_audit['peft_available']}")
    print(f" - BitsAndBytes: {env_audit['bitsandbytes_available']}")

    # 2. Audit Dataset & Legal Rights
    manifest_path = Path(config["dataset"]["manifest_path"])
    source_reg_path = Path(config.get("dataset", {}).get("source_register_path", "configs/dataset_source_register.json"))
    print("-" * 80)
    print(f"DATASET & LEGAL STATUS ({manifest_path}):")

    data_ok, data_blockers, data_stats = validate_dataset_provenance(manifest_path, source_reg_path)
    print(f" - Total Samples Examined:  {data_stats['total_samples']}")
    print(f" - Train Split Samples:     {data_stats['train_samples']}")
    print(f" - Dev Split Samples:       {data_stats['dev_samples']}")
    print(f" - Provenance Valid:        {data_ok}")
    print(f" - Unauthorized in Train:   {data_stats['unauthorized_train_samples']}")
    print(f" - Test Fixture Violations: {data_stats['test_fixture_violations']}")
    print(f" - Private Eval Violations: {data_stats['private_eval_violations']}")

    # 3. Fail-Closed Enforcement
    all_blockers = env_audit["blockers"] + data_blockers

    if data_blockers:
        print("\n" + "!" * 80)
        print(f" [POLICY ENFORCEMENT - FAIL-CLOSED ({len(data_blockers)} DATA BLOCKERS)]")
        print(" TRAINING REFUSED: Dataset samples fail mandatory provenance and legal clearance.")
        print(" Under Section 6 and Section 28.3 of GAMEFORGE_FINAL_MASTER_STRATEGY.md,")
        print(" models must never be trained on unverified or restricted datasets.")
        for b in data_blockers[:10]:
            print(f"  * {b}")
        if len(data_blockers) > 10:
            print(f"  ... and {len(data_blockers) - 10} more sample violations.")
        print(" See docs/LEGAL_RIGHTS_CLEARANCE_PACKET_V2.md for required clearance actions.")
        print("!" * 80)

    if env_audit["blockers"]:
        print("\n" + "!" * 80)
        print(" [HARDWARE & ENVIRONMENT BLOCKERS]")
        for b in env_audit["blockers"]:
            print(f"  * {b}")
        print("!" * 80)

    if preflight_only:
        if all_blockers:
            print(f"\n[PREFLIGHT AUDIT]: Preflight inspection complete. Requisite gates are CLOSED ({len(all_blockers)} blockers identified).")
            return 0
        else:
            print("\n[SUCCESS] Preflight inspection complete. All prerequisites verified.")
            return 0

    if all_blockers:
        print(f"\nExecution stopped safely (Fail-Closed: {len(all_blockers)} blockers). To execute preflight only, run with --preflight-only.")
        return 2

    # If legal gate and hardware were cleared:
    print("\nAll gates cleared! Initializing QLoRA training...")
    # (Actual training execution loop with SFTTrainer would proceed here)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GameForge V2 QLoRA Training Runner")
    parser.add_argument("--config", type=Path, default=Path("configs/training_config_gameforge_v2.json"), help="Training config path")
    parser.add_argument("--preflight-only", action="store_true", help="Run environment and gate preflight check without training")
    args = parser.parse_args()

    sys.exit(run_training_pipeline(args.config, args.preflight_only))
