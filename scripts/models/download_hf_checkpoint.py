"""Downloads official pinned Hugging Face checkpoint files for Qwen/Qwen3.8-27B to E:\\GameForge\\models\\hf\\Qwen3.8-27B.

Preserves exact immutable revision SHA: 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0.
Supports metadata-only download (config, tokenizer, chat template) or full safetensors download.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from huggingface_hub import HfApi, hf_hub_download

PINNED_REPO_ID = "Qwen/Qwen3.8-27B"
PINNED_REVISION_SHA = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
DEFAULT_TARGET_DIR = Path("E:/GameForge/models/hf/Qwen3.8-27B")

METADATA_FILES = [
    "config.json",
    "generation_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "chat_template.jinja",
    "model.safetensors.index.json",
    "preprocessor_config.json",
    "video_preprocessor_config.json",
    "LICENSE",
    "README.md",
]


def download_checkpoint(
    target_dir: Path = DEFAULT_TARGET_DIR,
    include_weights: bool = False,
    token: str = None,
) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    api = HfApi(token=token)

    print("=" * 80)
    print(" GAMEFORGE BASE CHECKPOINT PINNING & INGESTION")
    print(f" Target Repository: {PINNED_REPO_ID}")
    print(f" Pinned Revision:   {PINNED_REVISION_SHA}")
    print(f" Local Destination: {target_dir}")
    print(f" Include Weights:   {include_weights}")
    print("=" * 80)

    try:
        model_info = api.model_info(PINNED_REPO_ID, revision=PINNED_REVISION_SHA, files_metadata=True)
    except Exception as exc:
        print(f"Error fetching model info from Hugging Face Hub: {exc}", file=sys.stderr)
        return 1

    actual_sha = model_info.sha
    if actual_sha != PINNED_REVISION_SHA:
        print(f"FATAL: Revision mismatch! Expected {PINNED_REVISION_SHA}, got {actual_sha}", file=sys.stderr)
        return 1

    print(f"Verified remote revision SHA: {actual_sha}")

    # Determine files to download
    files_to_download = list(METADATA_FILES)
    if include_weights:
        safetensor_files = [s.rfilename for s in model_info.siblings if s.rfilename.endswith(".safetensors")]
        files_to_download.extend(safetensor_files)

    manifest_record = {
        "repo_id": PINNED_REPO_ID,
        "pinned_revision_sha": PINNED_REVISION_SHA,
        "license": "Apache-2.0",
        "download_target": str(target_dir),
        "files": {},
    }

    for idx, fname in enumerate(files_to_download, 1):
        print(f"[{idx}/{len(files_to_download)}] Downloading {fname}...", end="", flush=True)
        try:
            downloaded_path = hf_hub_download(
                repo_id=PINNED_REPO_ID,
                filename=fname,
                revision=PINNED_REVISION_SHA,
                local_dir=str(target_dir),
                local_dir_use_symlinks=False,
                token=token,
            )
            local_file = Path(downloaded_path)
            file_bytes = local_file.read_bytes()
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()
            manifest_record["files"][fname] = {
                "size_bytes": len(file_bytes),
                "sha256": sha256_hash,
            }
            print(f" DONE ({len(file_bytes)} bytes | SHA: {sha256_hash[:12]}...)")
        except Exception as exc:
            print(f" FAILED: {exc}", file=sys.stderr)
            return 1

    # Write local manifest
    manifest_file = target_dir / "gameforge_checkpoint_manifest.json"
    manifest_file.write_text(json.dumps(manifest_record, indent=2), encoding="utf-8")
    print("=" * 80)
    print(f"Checkpoint verification manifest written to: {manifest_file}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download pinned Qwen3.8-27B checkpoint files")
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR, help="Destination directory on E: drive")
    parser.add_argument("--include-weights", action="store_true", help="Download 51.77 GB full safetensors weights")
    parser.add_argument("--token", default=None, help="Hugging Face auth token (optional)")
    args = parser.parse_args()

    sys.exit(download_checkpoint(args.target_dir, args.include_weights, args.token))
