"""Verify GGUF binary header structure and compute streaming SHA-256 digest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DATA_ROOT = Path(os.environ.get("GAMEFORGE_DATA_ROOT", str(REPO_ROOT)))
DEFAULT_GGUF_PATH = DEFAULT_DATA_ROOT / "artifacts" / "gameforge-27b" / "gameforge-27b-q4_k_m.gguf"


def verify_gguf(path: Path) -> dict:
    assert path.exists(), f"File does not exist: {path}"
    file_size = path.stat().st_size
    print(f"File: {path}")
    print(f"Size: {file_size} bytes ({file_size / (1024**3):.4f} GiB / {file_size / 1e9:.4f} GB)")

    with open(path, "rb") as f:
        magic = f.read(4)
        print(f"Magic bytes: {magic}")
        assert magic == b"GGUF", f"Invalid GGUF magic: {magic}"
        version = struct.unpack("<I", f.read(4))[0]
        tensor_count, kv_count = struct.unpack("<QQ", f.read(16))
        print(f"GGUF Version: {version}")
        print(f"Tensor Count: {tensor_count}")
        print(f"Metadata KV Count: {kv_count}")

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify GGUF binary header and SHA-256")
    ap.add_argument("--gguf", type=Path, default=DEFAULT_GGUF_PATH, help="Path to GGUF file")
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "reports" / "gameforge-27b" / "acceptance" / "artifact_verification_raw.json",
        help="Output JSON report path",
    )
    ap.add_argument("--dry-run", action="store_true", help="Check arguments without processing large file")
    args = ap.parse_args()

    if args.dry_run:
        print(f"Dry run passed: Target GGUF={args.gguf}, Out={args.out}")
        return 0

    if not args.gguf.exists():
        print(f"Error: Target GGUF file does not exist: {args.gguf}", file=sys.stderr)
        return 1

    res = verify_gguf(args.gguf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temp_out = args.out.with_suffix(".tmp")
    try:
        temp_out.write_text(json.dumps(res, indent=2), encoding="utf-8")
        temp_out.replace(args.out)
    except Exception:
        if temp_out.exists():
            temp_out.unlink()
        raise
    print(f"Saved raw verification to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
