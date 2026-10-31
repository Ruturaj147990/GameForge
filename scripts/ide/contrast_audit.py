"""WCAG 2.1 Contrast Ratio Audit for Studio Themes (WI-4.12).

Computes contrast ratios for every (text role, background role) pair
in both Midnight Purple Dark and Glossy Purple Light themes.
Fails (exits non-zero) if any body text contrast ratio is below 4.5:1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Tuple

# Add repo to sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.desktop.styles import tokens
from src.gameforge_ide.desktop.styles.dark_theme import _DARK_TO_LIGHT


def _hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
    h = hex_str.lstrip("#")
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


def audit_theme(theme_name: str, text_colors: Dict[str, str], bg_colors: Dict[str, str]) -> Dict:
    results = {}
    failures = []
    for t_name, t_hex in text_colors.items():
        for b_name, b_hex in bg_colors.items():
            ratio = round(contrast_ratio(t_hex, b_hex), 2)
            pair_key = f"{t_name} on {b_name}"
            # Primary and secondary must meet WCAG AA normal text (4.5:1)
            passed = ratio >= 4.5
            results[pair_key] = {
                "text": t_hex,
                "background": b_hex,
                "ratio": ratio,
                "passed": passed,
            }
            if not passed:
                failures.append(f"{theme_name}: {pair_key} ratio {ratio}:1 < 4.5:1")
    return {"results": results, "failures": failures}


def main() -> int:
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

    dark_audit = audit_theme("Dark", dark_texts, dark_bgs)
    light_audit = audit_theme("Light", light_texts, light_bgs)

    all_failures = dark_audit["failures"] + light_audit["failures"]

    output_dir = REPO_ROOT / "reports" / "P4"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_file = output_dir / "contrast_audit.json"
    report_file.write_text(
        json.dumps(
            {
                "dark": dark_audit["results"],
                "light": light_audit["results"],
                "failures": all_failures,
                "passed": len(all_failures) == 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Contrast audit written to {report_file}")
    if all_failures:
        print("FAILURES DETECTED:")
        for f in all_failures:
            print("  -", f)
        return 1

    print("[OK] All theme pairs meet WCAG AA contrast threshold (>= 4.5:1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
