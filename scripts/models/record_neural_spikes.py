"""Generate neural content spike records (WI-9.5, Exit Gate 3)."""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "P9"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def record_spikes() -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. ROCm Windows Spike
    spike_rocm = {
        "spike": "rocm_windows",
        "status": "BLOCKED (needs approval: AMD HIP SDK 7.2 and PyTorch ROCm installation)",
        "timestamp": now,
        "target_hardware": {
            "gpu": "AMD Radeon RX 7700 XT",
            "vram_gb": 12,
            "architecture": "RDNA 3",
            "gfx_target": "gfx1101",
        },
        "prerequisites": {
            "sdk": "AMD HIP SDK 7.2 for Windows",
            "support_status": "Officially supported on gfx1101 (RDNA 3)",
            "environment_path": "E:/GameForge/envs/rocm",
        },
        "acceptance_criteria": {
            "torch_cuda_available": True,
            "matmul_4k_latency_target_ms": 15.0,
            "vram_headroom_gb": 2.0,
        },
        "measured": {
            "installed": False,
            "reason": "Requires user approval for host compiler and SDK installation.",
        },
    }

    # 2. Hunyuan3D-2.1 Spike
    spike_hunyuan = {
        "spike": "hunyuan3d_21",
        "status": "BLOCKED (needs approval: model weights download and environment setup)",
        "timestamp": now,
        "model_spec": {
            "name": "Hunyuan3D-2.1 shape-only",
            "weights_target": "E:/GameForge/models/hunyuan3d21",
            "license": "Tencent Hunyuan Community License",
            "license_territory_restrictions": True,
            "provenance_class": "NEURAL",
        },
        "post_processing_pipeline": [
            "Geometry Script CSG remesh",
            "XAtlas UV unwrapping",
            "GameForge master material assignment",
            "StaticMesh LOD generation and convex collision",
        ],
        "acceptance_criteria": {
            "peak_vram_limit_gb": 12.0,
            "valid_mesh_rate_target": ">= 7/10",
            "manifold_topology_required": True,
        },
        "measured": {
            "installed": False,
            "reason": "Requires user approval for 10+ GB weights download and Tencent community licence acceptance.",
        },
    }

    # 3. Piper TTS Spike
    spike_piper = {
        "spike": "piper_tts",
        "status": "BLOCKED (needs approval: binary and voice weights download)",
        "timestamp": now,
        "engine_spec": {
            "name": "Piper TTS",
            "target_dir": "E:/GameForge/models/piper",
            "engine_license": "MIT",
            "compute_target": "CPU (ONNX Runtime)",
            "voice_license": "Recorded per voice (CC-BY / Public Domain)",
        },
        "acceptance_criteria": {
            "realtime_factor_cpu_target": "< 0.25",
            "wav_sample_rate_hz": 22050,
            "unreal_import_pipeline": "UGameForgeAudioSubsystem -> SoundWave / MetaSound",
        },
        "measured": {
            "installed": False,
            "reason": "Requires user approval for binary and voice models download.",
        },
    }

    (REPORTS_DIR / "spike_rocm.json").write_text(json.dumps(spike_rocm, indent=2), encoding="utf-8")
    (REPORTS_DIR / "spike_hunyuan3d.json").write_text(json.dumps(spike_hunyuan, indent=2), encoding="utf-8")
    (REPORTS_DIR / "spike_piper.json").write_text(json.dumps(spike_piper, indent=2), encoding="utf-8")

    print(f"Recorded 3 neural content spikes to {REPORTS_DIR}")


if __name__ == "__main__":
    record_spikes()
