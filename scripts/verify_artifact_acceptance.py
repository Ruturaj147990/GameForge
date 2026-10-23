import struct
import hashlib
import os
import json
import time
from pathlib import Path

GGUF_PATH = Path(r"E:\GameForge\artifacts\gameforge-27b\gameforge-27b-q4_k_m.gguf")

def verify_gguf(path: Path):
    assert path.exists(), f"File does not exist: {path}"
    file_size = path.stat().st_size
    print(f"File: {path}")
    print(f"Size: {file_size} bytes ({file_size / (1024**3):.4f} GiB / {file_size / 1e9:.4f} GB)")

    # Read GGUF Header
    with open(path, "rb") as f:
        magic = f.read(4)
        print(f"Magic bytes: {magic}")
        assert magic == b"GGUF", f"Invalid GGUF magic: {magic}"
        version, tensor_count, kv_count = struct.unpack("<IQI", f.read(4 + 8 + 4)) # wait, in GGUF v2/v3, kv_count is uint64
        # Let's check GGUF spec:
        # uint32 magic = 0x46554747
        # uint32 version
        # uint64 tensor_count
        # uint64 metadata_kv_count
    
    # Re-read with standard uint64
    with open(path, "rb") as f:
        f.seek(4)
        version = struct.unpack("<I", f.read(4))[0]
        tensor_count, kv_count = struct.unpack("<QQ", f.read(16))
        print(f"GGUF Version: {version}")
        print(f"Tensor Count: {tensor_count}")
        print(f"Metadata KV Count: {kv_count}")

    # Compute SHA-256
    print("Computing SHA-256...")
    t0 = time.time()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(64 * 1024 * 1024):
            h.update(chunk)
    sha256_hash = h.hexdigest()
    t_elapsed = time.time() - t0
    print(f"SHA-256: {sha256_hash} (computed in {t_elapsed:.2f}s)")

    return {
        "path": str(path),
        "size_bytes": file_size,
        "size_gib": file_size / (1024**3),
        "size_gb": file_size / 1e9,
        "magic": magic.decode("latin1"),
        "version": version,
        "tensor_count": tensor_count,
        "kv_count": kv_count,
        "sha256": sha256_hash,
    }

if __name__ == "__main__":
    res = verify_gguf(GGUF_PATH)
    out_path = Path(r"E:\GameForge\reports\gameforge-27b\acceptance\artifact_verification_raw.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2))
    print(f"Saved raw verification to {out_path}")
