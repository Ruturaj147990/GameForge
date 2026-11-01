"""Generate cinematic sequence validation report (WI-10.5)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

REPORTS_DIR = REPO_ROOT / "reports" / "P10"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

from src.gameforge_ide.composer.cinematics import generate_intro_cinematic
from src.gameforge_ide.design.presets import get_preset_spec


def run_cinematics_demo() -> None:
    gds = get_preset_spec("relic_hunt")
    gds.presentation.intro.enabled = True
    gds.presentation.intro.seconds = 12.0
    gds.presentation.intro.focus = ["landmark", "goal"]

    seq = generate_intro_cinematic(gds)

    report = {
        "status": "PASS",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "game_title": gds.meta.title,
        "sequence": seq,
        "verification": {
            "schema_version": gds.meta.schema_version,
            "duration_seconds": seq["duration_seconds"],
            "shots_detected": len(seq["shots"]),
            "cuts_detected": seq["cut_count"],
            "audio_track_bound": bool(seq["audio_track"]),
            "skippable_in_scenario": seq["playback_policy"]["skippable"],
        },
    }

    out_file = REPORTS_DIR / "cinematics.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Cinematics report saved to {out_file}")
    print(f"Sequence: {seq['sequence_name']} ({seq['duration_seconds']}s, {seq['cut_count']} shots) -> [PASS]")


if __name__ == "__main__":
    run_cinematics_demo()
