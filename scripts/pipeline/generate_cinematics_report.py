"""Generate cinematic sequence validation report (WI-10.5)."""
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
DEFAULT_REPORT_FILE = DEFAULT_REPORTS_DIR / "cinematics.json"

from src.gameforge_ide.composer.cinematics import generate_intro_cinematic
from src.gameforge_ide.design.presets import get_preset_spec


def run_cinematics_validation(
    preset_name: str = "relic_hunt",
    duration_s: float = 12.0,
    focus_targets: Optional[List[str]] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate cinematic sequence generation for a game preset and save verification report."""
    targets = focus_targets or ["landmark", "goal"]
    report_file = output_path or DEFAULT_REPORT_FILE

    gds = get_preset_spec(preset_name)
    gds.presentation.intro.enabled = True
    gds.presentation.intro.seconds = duration_s
    gds.presentation.intro.focus = targets

    seq = generate_intro_cinematic(gds)

    shots = seq.get("shots", [])
    cut_count = seq.get("cut_count", 0)
    actual_duration = seq.get("duration_seconds", 0.0)
    seq_name = seq.get("sequence_name", "")

    # Contract assertions
    validation_passed = (
        bool(seq_name)
        and actual_duration > 0.0
        and len(shots) > 0
        and cut_count >= 1
        and seq.get("playback_policy", {}).get("skippable") is True
    )

    status = "PASS" if validation_passed else "FAIL"

    report: Dict[str, Any] = {
        "status": status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preset_name": preset_name,
        "game_title": gds.meta.title,
        "sequence": seq,
        "verification": {
            "schema_version": gds.meta.schema_version,
            "duration_seconds": actual_duration,
            "shots_detected": len(shots),
            "cuts_detected": cut_count,
            "audio_track_bound": bool(seq.get("audio_track")),
            "skippable_in_scenario": seq.get("playback_policy", {}).get("skippable", False),
            "contract_verified": validation_passed,
        },
    }

    report_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=report_file.parent, delete=False, suffix=".tmp") as tf:
        json.dump(report, tf, indent=2)
        tf_name = tf.name
    os.replace(tf_name, report_file)

    print(f"Cinematics report saved to {report_file}")
    print(f"Sequence: {seq_name} ({actual_duration}s, {cut_count} shots) -> [{status}]")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and validate cinematics report")
    parser.add_argument("--preset", default="relic_hunt", help="Game preset name (default: relic_hunt)")
    parser.add_argument("--duration", type=float, default=12.0, help="Intro duration in seconds")
    parser.add_argument("--output", type=Path, default=None, help="Output path for JSON report")
    args = parser.parse_args()

    report = run_cinematics_validation(
        preset_name=args.preset,
        duration_s=args.duration,
        output_path=args.output,
    )
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
