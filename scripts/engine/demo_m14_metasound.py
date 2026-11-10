"""Roadmap M14 MetaSound authoring on a disposable probe copy (plugin m14v2, editor with sound enabled).

Builds MS_GFChime with the MetaSound builder API: Sine (UE.Sine.Audio, 660 Hz) × AD Envelope (Audio, attack 0.01 s,
decay 0.6 s) → mono output; the source's OnPlay triggers the envelope and the envelope's On Done drives OnFinished.
Node class/pin names were taken from the 5.7 MetasoundStandardNodes source. Checks: build succeeds; a fresh builder
on the saved asset finds every node and connection; in PIE the spawned MetaSound plays and then stops by itself
between 0.5 s and 3 s. A one-shot MetaSound only finishes when its graph fires OnFinished, so stopping on its own
shows the built graph runs.

Evidence: reports/m14_metasound_demo.json. Usage: python scripts/engine/demo_m14_metasound.py
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
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = REPO / "reports" / "m14_metasound_demo.json"
ASSET = "/Game/M14/MetaSounds/MS_GFChime"
SPEC = {
    "nodes": [
        {"id": "osc", "class": ["UE", "Sine", "Audio"], "defaults": {"Frequency": 660.0}},
        {"id": "env", "class": ["AD Envelope", "AD Envelope", "Audio"], "defaults": {"Attack Time": 0.01, "Decay Time": 0.6}},
        {"id": "mul", "class": ["UE", "Multiply", "Audio"]},
    ],
    "edges": [{"from": ["osc", "Audio"], "to": ["mul", "PrimaryOperand"]},
              {"from": ["env", "Out Envelope"], "to": ["mul", "AdditionalOperands"]}],
    "on_play": [["env", "Trigger"]],
    "on_finished": ["env", "On Done"],
    "audio_out": ["mul", "Out"],
    "one_shot": True,
}


def run(rep: Dict[str, Any]) -> None:
    import demo_m11_landscape as land

    checks, steps = rep["checks"], rep["steps"]
    try:
        val_root = get_settings().require_dev("validation_root")
    except Exception:
        val_root = REPO / "scratch" / "validation"

    land.PLUGIN_BUILD = val_root / "GameForgePlugin_m14v2"
    land.PROJECT_DIR = val_root / f"m14_metasound_{time.strftime('%Y%m%d')}"
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=land.PROJECT_DIR / "metasound_editor.log",
                no_sound=False)
    try:
        link.connect(discovery_timeout_s=900)
        link.call("new_level", {"level_path": "/Game/M14/Maps/MetaSoundTest"})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Floor",
                                  "static_mesh": "/Engine/BasicShapes/Cube.Cube", "location": {"x": 0, "y": 0, "z": -50},
                                  "scale": {"x": 20, "y": 20, "z": 1}})
        link.call("spawn_actor", {"actor_class": "PlayerStart", "label": "GF_PlayerStart", "location": {"x": 0, "y": 0, "z": 120}})
        b = link.call("metasound_build_source", {"asset_path": ASSET, **SPEC}, timeout_s=120) or {}
        steps["build"] = {"ok": b.get("ok"), "errors": b.get("errors"), "data": b.get("data")}
        checks["metasound_built"] = bool(b.get("ok"))
        insp = link.call("metasound_inspect", {"asset_path": ASSET, "spec": SPEC}) or {}
        steps["inspect"] = {"ok": insp.get("ok"), "errors": insp.get("errors"), "data": insp.get("data")}
        checks["graph_read_back_from_saved_asset"] = bool(insp.get("ok"))
        checks["asset_is_metasound_source"] = (insp.get("data") or {}).get("asset_class") == "MetaSoundSource"
        link.call("save_all", {})

        link.call("pie_start", {})
        try:
            time.sleep(5.0)
            play = link.call("audio_play_at", {"sound_path": ASSET, "label": "GF_Chime", "location": {"x": 100, "y": 0, "z": 100}}) or {}
            t_play = time.monotonic()
            steps["play"] = {"ok": play.get("ok"), "errors": play.get("errors"), "data": play.get("data")}
            series, stopped_at = [], None
            while time.monotonic() - t_play < 6.0:
                st = (link.call("audio_status", {}) or {}).get("data") or {}
                comp = next((c for c in st.get("components", []) if c.get("label") == "GF_Chime"), {})
                t = round(time.monotonic() - t_play, 2)
                series.append({"t": t, "playing": comp.get("playing")})
                if comp.get("playing") is False and stopped_at is None:
                    stopped_at = t
                    break
                time.sleep(0.1)
            steps["series"] = series
            steps["stopped_at_s"] = stopped_at
            checks["plays_in_pie"] = bool(play.get("ok")) and any(s["playing"] for s in series)
            checks["stops_by_itself_via_graph_on_finished"] = stopped_at is not None and 0.5 <= stopped_at <= 3.0
        finally:
            with contextlib.suppress(Exception):
                link.call("pie_stop", {})
    finally:
        rep["editor_exit_code"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["audible output capture", "graph read-back after editor restart (node handles are kept in memory)"]}
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
