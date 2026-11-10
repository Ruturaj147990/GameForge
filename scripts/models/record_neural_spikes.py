"""Generate neural content spike records (WI-9.5, Exit Gate 3)."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REPORTS_DIR = REPO_ROOT / "reports" / "P9"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def record_spikes(output_dir: Path | None = None) -> None:
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

    spikes = {
        "spike_rocm.json": spike_rocm,
        "spike_hunyuan3d.json": spike_hunyuan,
        "spike_piper.json": spike_piper,
    }

    out_dir = output_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    for fname, data in spikes.items():
        target = out_dir / fname
        temp_file = target.with_suffix(".tmp")
        try:
            temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temp_file.replace(target)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise

    print(f"Recorded 3 neural content spikes to {out_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate neural content spike records")
    parser.add_argument("--output-dir", type=Path, default=None, help="Target reports directory")
    args = parser.parse_args()

    record_spikes(output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
