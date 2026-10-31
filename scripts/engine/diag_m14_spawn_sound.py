"""Diagnostic (not acceptance): why GameplayStatics.spawn_sound_at_location returns None in 5.7 PIE.

Disposable probe copy, editor with sound enabled; imports a looping wind and a one-shot pickup, starts PIE and runs
`audio_diagnose_spawn` for both. Output: reports/m14_spawn_diag.json. Usage: python scripts/engine/diag_m14_spawn_sound.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import demo_m11_landscape as land  # noqa: E402
from src.gameforge_ide.backend.tools.sfx_synth import SFXSpec, generate_sfx  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = REPO / "reports" / "m14_spawn_diag.json"


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "results": {}}
    land.PROJECT_DIR = Path(str(land.PROJECT_DIR).replace("m11_landscape_", "m14_spawn_diag_"))
    uproject = land.make_disposable()
    sounds = {"Wind": generate_sfx(SFXSpec(name="Wind", kind="wind_loop", seed=2), land.PROJECT_DIR / "SourceAudio"),
              "Pickup": generate_sfx(SFXSpec(name="Pickup", kind="pickup", seed=4), land.PROJECT_DIR / "SourceAudio")}
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=land.PROJECT_DIR / "diag_editor.log",
                no_sound=False)
    try:
        link.connect(discovery_timeout_s=900)
        link.call("new_level", {"level_path": "/Game/M14/Maps/Diag"})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Floor",
                                  "static_mesh": "/Engine/BasicShapes/Cube.Cube", "location": {"x": 0, "y": 0, "z": -50},
                                  "scale": {"x": 20, "y": 20, "z": 1}})
        link.call("spawn_actor", {"actor_class": "PlayerStart", "label": "GF_PlayerStart", "location": {"x": 0, "y": 0, "z": 120}})
        for n, info in sounds.items():
            link.call("audio_import", {"source_file": info["path"], "destination_path": "/Game/M14/Audio",
                                       "destination_name": f"SFX_{n}", "looping": info["looping"]}, timeout_s=120)
        link.call("save_all", {})
        link.call("pie_start", {})
        time.sleep(6.0)
        for n in sounds:
            r = link.call("audio_diagnose_spawn", {"sound_path": f"/Game/M14/Audio/SFX_{n}",
                                                   "location": {"x": 150, "y": 0, "z": 100}})
            rep["results"][n] = {"ok": r.get("ok"), "data": r.get("data"), "errors": r.get("errors")}
        link.call("pie_stop", {})
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["editor_exit_code"] = link.stop()
        REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps(rep["results"], indent=1), rep.get("exception", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
