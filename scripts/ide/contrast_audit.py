"""WCAG 2.1 Contrast Ratio Audit for Studio Themes (WI-4.12).

Computes contrast ratios for every (text role, background role) pair
in both Midnight Purple Dark and Glossy Purple Light themes.
Fails (exits non-zero) if any body text contrast ratio is below 4.5:1.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Tuple

# Add repo to sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.desktop.styles import tokens
from src.gameforge_ide.desktop.styles.dark_theme import _DARK_TO_LIGHT


def _hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    elif len(h) == 8:
        h = h[:6]
    elif len(h) != 6:
        raise ValueError(f"Invalid hex color string: {hex_str}")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255.0, g / 255.0, b / 255.0


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb: Tuple[float, float, float]) -> float:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex1: str, hex2: str) -> float:
    lum1 = _relative_luminance(_hex_to_rgb(hex1))
    lum2 = _relative_luminance(_hex_to_rgb(hex2))
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def audit_theme(
    theme_name: str,
    text_colors: Dict[str, str],
    bg_colors: Dict[str, str],
    threshold: float = 4.5,
) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    failures: List[str] = []
    for t_name, t_hex in text_colors.items():
        for b_name, b_hex in bg_colors.items():
            ratio = round(contrast_ratio(t_hex, b_hex), 2)
            pair_key = f"{t_name} on {b_name}"
            # Primary and secondary must meet WCAG AA normal text (default 4.5:1)
            passed = ratio >= threshold
            results[pair_key] = {
                "text": t_hex,
                "background": b_hex,
                "ratio": ratio,
                "passed": passed,
            }
            if not passed:
                failures.append(f"{theme_name}: {pair_key} ratio {ratio}:1 < {threshold}:1")
    return {"results": results, "failures": failures}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="WCAG 2.1 Contrast Ratio Audit for Studio Themes")
    parser.add_argument("--threshold", type=float, default=4.5, help="Minimum contrast ratio for body text (default 4.5)")
    parser.add_argument("--out", type=Path, default=None, help="Custom output path for audit report")
    args = parser.parse_args(argv)

    # Dark tokens
    dark_texts = {
        "TEXT_PRIMARY": tokens.TEXT_PRIMARY,
        "TEXT_SECONDARY": tokens.TEXT_SECONDARY,
    }
    dark_bgs = {
        "BG_ROOT": tokens.BG_ROOT,
        "BG_PANEL": tokens.BG_PANEL,
        "BG_SURFACE": tokens.BG_SURFACE,
        "BG_HOVER": tokens.BG_HOVER,
    }

    # Light tokens
    light_texts = {
        name: _DARK_TO_LIGHT.get(val.lower(), val) for name, val in dark_texts.items()
    }
    light_bgs = {
        name: _DARK_TO_LIGHT.get(val.lower(), val) for name, val in dark_bgs.items()
    }

    dark_audit = audit_theme("Dark", dark_texts, dark_bgs, threshold=args.threshold)
    light_audit = audit_theme("Light", light_texts, light_bgs, threshold=args.threshold)

    all_failures = dark_audit["failures"] + light_audit["failures"]

    report_file = args.out or (REPO_ROOT / "reports" / "P4" / "contrast_audit.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "dark": dark_audit["results"],
        "light": light_audit["results"],
        "failures": all_failures,
        "threshold": args.threshold,
        "passed": len(all_failures) == 0,
    }
    tmp_report = report_file.with_suffix(".tmp")
    tmp_report.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    tmp_report.replace(report_file)

    print(f"Contrast audit written to {report_file}")
    if all_failures:
        print("FAILURES DETECTED:")
        for f in all_failures:
            print("  -", f)
        return 1

    print(f"[OK] All theme pairs meet WCAG AA contrast threshold (>= {args.threshold}:1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
