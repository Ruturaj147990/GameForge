"""Analyze shipping build package size and verify <= 400 MB gate (WI-10.2)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_REPORTS_DIR = REPO_ROOT / "reports" / "P10"
DEFAULT_REPORT_FILE = DEFAULT_REPORTS_DIR / "shipping_package.json"
CANDIDATE_DIRS = [
    Path("E:/GameForge/validation/P3_kittest_20261031/package_ship/Windows"),
    REPO_ROOT / "dist" / "GameForge",
    REPO_ROOT / "dist",
]

DEBUG_SYMBOL_EXTS = {".pdb", ".sym", ".dbg", ".map"}


def _write_atomic_json(target_path: Path, data: Any) -> None:
    """Atomically write JSON data to file using a temporary file and replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False, suffix=".tmp") as tf:
        json.dump(data, tf, indent=2)
        tf_name = tf.name
    os.replace(tf_name, target_path)


def discover_archive_dir(explicit_path: Optional[Path] = None) -> Optional[Path]:
    """Resolve archive directory from explicit path or known candidate directories."""
    if explicit_path:
        return explicit_path if explicit_path.is_dir() else None
    for cand in CANDIDATE_DIRS:
        if cand.is_dir():
            return cand
    return None


def analyze_shipping_package(
    archive_dir: Optional[Path] = None,
    max_budget_mb: float = 400.0,
    output_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Inspect package file tree, calculate redistributable footprint, and verify budget."""
    out_file = output_file or DEFAULT_REPORT_FILE
    effective_dir = discover_archive_dir(archive_dir)

    iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if effective_dir is None or not effective_dir.is_dir():
        target_str = str(archive_dir) if archive_dir else "None"
        report: Dict[str, Any] = {
            "status": "BLOCKED",
            "timestamp": iso_timestamp,
            "archive_dir": target_str,
            "reason": f"Package archive directory not found or not a directory: {target_str}",
            "meets_budget": False,
        }
        _write_atomic_json(out_file, report)
        print(f"Shipping package report saved to {out_file} -> [BLOCKED: directory not found]")
        return report

    all_files: List[Dict[str, Any]] = []
    total_raw_bytes = 0
    redist_bytes = 0

    for p in effective_dir.rglob("*"):
        if p.is_file():
            sz = p.stat().st_size
            total_raw_bytes += sz
            rel = str(p.relative_to(effective_dir)).replace("\\", "/")
            is_symbol = p.suffix.lower() in DEBUG_SYMBOL_EXTS
            if not is_symbol:
                redist_bytes += sz
            all_files.append({"path": rel, "bytes": sz, "is_debug_symbol": is_symbol})

    all_files.sort(key=lambda x: x["bytes"], reverse=True)
    largest_files = all_files[:10]

    redist_mb = round(redist_bytes / (1024 * 1024), 2)
    total_raw_mb = round(total_raw_bytes / (1024 * 1024), 2)
    gate_passed = redist_mb <= max_budget_mb

    report = {
        "status": "PASS" if gate_passed else "FAIL",
        "timestamp": iso_timestamp,
        "archive_dir": str(effective_dir).replace("\\", "/"),
        "total_raw_mb": total_raw_mb,
        "redistributable_mb": redist_mb,
        "max_package_budget_mb": max_budget_mb,
        "meets_budget": gate_passed,
        "compression": {
            "format": "Oodle",
            "share_material_shader_code": True,
            "shared_material_native_libraries": True,
            "prerequisites_included": False,
        },
        "largest_files": [
            {
                "file": f["path"],
                "size_mb": round(f["bytes"] / (1024 * 1024), 2),
                "is_debug_symbol": f["is_debug_symbol"],
            }
            for f in largest_files
        ],
    }

    _write_atomic_json(out_file, report)
    print(f"Shipping package report saved to {out_file}")
    print(f"Redistributable size: {redist_mb} MB (Budget: {max_budget_mb} MB) -> [PASS: {gate_passed}]")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze shipping build package size and budget gate")
    parser.add_argument("--archive-dir", type=Path, default=None, help="Directory containing built package")
    parser.add_argument("--budget-mb", type=float, default=400.0, help="Maximum allowed package budget in MB")
    parser.add_argument("--output", type=Path, default=None, help="Output path for JSON report")
    args = parser.parse_args()

    report = analyze_shipping_package(
        archive_dir=args.archive_dir,
        max_budget_mb=args.budget_mb,
        output_file=args.output,
    )

    status = report.get("status")
    if status == "PASS":
        return 0
    elif status == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
