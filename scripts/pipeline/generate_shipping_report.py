"""Analyze shipping build package size and verify <= 400 MB gate (WI-10.2)."""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "P10"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def analyze_shipping_package(archive_dir: Path) -> dict:
    if not archive_dir.is_dir():
        raise FileNotFoundError(f"Archive directory {archive_dir} not found")

    all_files = []
    total_raw_bytes = 0
    redist_bytes = 0

    for p in archive_dir.rglob("*"):
        if p.is_file():
            sz = p.stat().st_size
            total_raw_bytes += sz
            rel = str(p.relative_to(archive_dir)).replace("\\", "/")
            is_symbol = p.suffix.lower() in (".pdb", ".sym")
            if not is_symbol:
                redist_bytes += sz
            all_files.append({"path": rel, "bytes": sz, "is_debug_symbol": is_symbol})

    all_files.sort(key=lambda x: x["bytes"], reverse=True)
    largest_files = all_files[:10]

    redist_mb = round(redist_bytes / (1024 * 1024), 2)
    total_raw_mb = round(total_raw_bytes / (1024 * 1024), 2)
    gate_passed = redist_mb <= 400.0

    report = {
        "status": "PASS" if gate_passed else "FAIL",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "archive_dir": str(archive_dir).replace("\\", "/"),
        "total_raw_mb": total_raw_mb,
        "redistributable_mb": redist_mb,
        "max_package_budget_mb": 400.0,
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

    out_file = REPORTS_DIR / "shipping_package.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Shipping package report saved to {out_file}")
    print(f"Redistributable size: {redist_mb} MB (Budget: 400.0 MB) -> [PASS: {gate_passed}]")
    return report


if __name__ == "__main__":
    pkg_dir = Path("E:/GameForge/validation/P3_kittest_20261031/package_ship/Windows")
    analyze_shipping_package(pkg_dir)
