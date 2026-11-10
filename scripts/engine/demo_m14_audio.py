"""Roadmap M14 engine check on a disposable probe copy, with the real audio device (no -NoSound).

Procedural SFX (pickup chime, looping wind) → USoundWave import with read-back (duration, channels, rate,
looping) → SoundAttenuation asset with read-back → PIE: sounds started at locations, playing state and
listener distance read back, GF_EVENT marker found in the editor log.
The attenuation gain at the listener is *computed* from the read-back settings and distance (linear model);
the engine's mixed output level is not measured, so that part stays NOT VERIFIED.

Evidence: reports/m14_audio_demo.json. Usage: python scripts/engine/demo_m14_audio.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
ENGINE_SCRIPTS = str(REPO / "scripts" / "engine")
if ENGINE_SCRIPTS not in sys.path:
    sys.path.insert(0, ENGINE_SCRIPTS)

from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.backend.tools.sfx_synth import SFXSpec, generate_sfx  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = REPO / "reports" / "m14_audio_demo.json"
ATT = "/Game/M14/Audio/ATT_GFDefault"
SOUNDS = {"Pickup": SFXSpec(name="Pickup", kind="pickup", seed=4), "Wind": SFXSpec(name="Wind", kind="wind_loop", seed=9)}


def _get_sfx_out() -> Path:
    try:
        data_root = get_settings().data_root
    except Exception:
        data_root = REPO / "scratch" / "data"
    return data_root / "assets" / f"generated/audio/m14_demo_{time.strftime('%Y%m%d')}"


def linear_gain(distance: float, inner: float, falloff: float) -> float:
    if distance <= inner:
        return 1.0
    return max(0.0, 1.0 - (distance - inner) / falloff)


def run(rep: Dict[str, Any]) -> None:
    import demo_m11_landscape as land

    checks, steps = rep["checks"], rep["steps"]
    try:
        val_root = get_settings().require_dev("validation_root")
    except Exception:
        val_root = REPO / "scratch" / "validation"
    land.PROJECT_DIR = val_root / f"m14_audio_{time.strftime('%Y%m%d')}"
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()

    sfx_out = _get_sfx_out()
    sfx_out.mkdir(parents=True, exist_ok=True)
    infos = {n: generate_sfx(spec, sfx_out) for n, spec in SOUNDS.items()}
    steps["generated"] = {n: {"path": i["path"], "sha256": i["sha256"], "analysis": i["analysis"]} for n, i in infos.items()}

    link = LiveEditorLink(uproject)
    link.prepare_project()
    log_path = land.PROJECT_DIR / "audio_editor.log"
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=log_path, no_sound=False)
    try:
        link.connect(discovery_timeout_s=900)
        link.call("new_level", {"level_path": "/Game/M14/Maps/AudioTest"})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Floor",
                                  "static_mesh": "/Engine/BasicShapes/Cube.Cube", "location": {"x": 0, "y": 0, "z": -50},
                                  "scale": {"x": 60, "y": 60, "z": 1}})
        link.call("spawn_actor", {"actor_class": "PlayerStart", "label": "GF_PlayerStart", "location": {"x": 0, "y": 0, "z": 120}})
        att = link.call("audio_create_attenuation", {"asset_path": ATT, "inner_radius": 300, "falloff_distance": 2500}) or {}
        att_rb = (link.call("audio_inspect_attenuation", {"attenuation_path": ATT}) or {}).get("data") or {}
        steps["attenuation"] = att_rb | {"ok": att.get("ok"), "errors": att.get("errors")}
        checks["attenuation_read_back"] = bool(att.get("ok")) and att_rb.get("falloff_distance") == 2500 and \
            att_rb.get("inner_radius") == 300 and att_rb.get("spatialize") is True
        imported = {}
        for n, info in infos.items():
            r = link.call("audio_import", {"source_file": info["path"], "destination_path": "/Game/M14/Audio",
                                           "destination_name": f"SFX_{n}", "looping": info["looping"],
                                           "attenuation_path": ATT}, timeout_s=120) or {}
            rb = (link.call("audio_inspect", {"sound_path": f"/Game/M14/Audio/SFX_{n}"}) or {}).get("data") or {}
            imported[n] = rb | {"ok": r.get("ok"), "errors": r.get("errors")}
        steps["imported"] = imported
        checks["sounds_imported_with_matching_duration"] = all(
            v["ok"] and abs((v.get("duration") or 0) - infos[n]["analysis"]["duration_s"]) < 0.05
            and v.get("num_channels") == 1 and v.get("attenuation", "").startswith(ATT) for n, v in imported.items())
        checks["wind_is_looping"] = imported.get("Wind", {}).get("looping") is True
        placed = {}
        for n, loc in (("Wind", {"x": 1200, "y": 0, "z": 100}), ("Pickup", {"x": 150, "y": 0, "z": 100})):
            r = link.call("audio_place_ambient", {"sound_path": f"/Game/M14/Audio/SFX_{n}", "label": f"GF_Amb{n}",
                                                  "location": loc, "auto_activate": False}) or {}
            placed[n] = (r.get("data") or {}) | {"ok": r.get("ok"), "errors": r.get("errors")}
        steps["ambient_placed"] = placed
        link.call("save_all", {})

        steps["pie_start"] = bool((link.call("pie_start", {}) or {}).get("ok"))
        try:
            time.sleep(6.0)
            offset = (link.call("log_tail", {"max_lines": 1}) or {}).get("data")
            plays = {}
            for n, loc in (("Wind", {"x": 1200, "y": 0, "z": 100}), ("Pickup", {"x": 150, "y": 0, "z": 100})):
                r = link.call("audio_play_at", {"sound_path": f"/Game/M14/Audio/SFX_{n}", "label": f"GF_{n}", "location": loc}) or {}
                plays[n] = {"ok": r.get("ok"), "errors": r.get("errors"), "data": r.get("data")}
            steps["plays_spawn_at_location"] = dict(plays)
            checks["spawn_sound_at_location_works"] = bool(plays) and all(p.get("ok") for p in plays.values())
            plays = {}
            for n in ("Wind", "Pickup"):
                r = link.call("audio_play_actor", {"label": f"GF_Amb{n}"}) or {}
                plays[n] = {"ok": r.get("ok"), "errors": r.get("errors"), "data": r.get("data")}
            steps["plays"] = plays
            time.sleep(0.1)
            status = link.call("audio_status", {}) or {}
            comps = {c["label"]: c for c in (status.get("data") or {}).get("components", [])}
            steps["status_t0"] = comps
            checks["pickup_playing_in_pie"] = bool(comps.get("GF_AmbPickup", {}).get("playing"))
            checks["wind_playing_in_pie"] = bool(comps.get("GF_AmbWind", {}).get("playing"))
            time.sleep(1.5)
            later = {c["label"]: c for c in ((link.call("audio_status", {}) or {}).get("data") or {}).get("components", [])}
            steps["status_t1_6s"] = later
            checks["one_shot_finished_loop_continues"] = (not later.get("GF_AmbPickup", {}).get("playing", True)
                                                          and bool(later.get("GF_AmbWind", {}).get("playing")))
            gains = {}
            for label, c in comps.items():
                d = c.get("distance_to_listener")
                if d is not None:
                    gains[label] = {"distance": d, "computed_linear_gain": round(linear_gain(d, 300, 2500), 3)}
            steps["computed_attenuation"] = gains
            tail = (link.call("log_tail", {"max_lines": 400}) or {}).get("data") or {}
            lines = tail.get("lines") or []
            steps["log_offset_probe"] = offset
            checks["gf_event_marker_logged"] = any("GF_EVENT audio_play GF_AmbPickup" in str(l) for l in lines)
        finally:
            with contextlib.suppress(Exception):
                link.call("pie_stop", {})
    finally:
        rep["editor_exit_code"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["engine output level / audible attenuation measurement", "packaged playback",
                           "MetaSound builder", "Sound Class / Submix"]}
    try:
        run(rep)
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        tmp_report = REPORT.with_suffix(".tmp")
        tmp_report.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
        os.replace(tmp_report, REPORT)
    print(json.dumps(rep["checks"], indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
