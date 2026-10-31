"""Roadmap M13 (Niagara) engine check on a disposable probe copy.

Creates two systems (one duplicated from the engine's SimpleExplosion template system, one built from the
Fountain template emitter), spawns them in a running PIE session and reads the live particle counts of each
emitter instance back through `GameForgeVFXLibrary.InspectParticles`, then captures the PIE view.
Not covered (M13 acceptance stays PARTIAL): spawning from a real gameplay event, renderer material from M11,
`stat Niagara` cost.

Evidence: reports/m13_vfx_demo.json. Usage: python scripts/engine/demo_m13_vfx.py
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

REPORT = REPO / "reports" / "m13_vfx_demo.json"
SYSTEMS = {
    "Explosion": {"asset_path": "/Game/M13/VFX/NS_GFExplosion", "template_system": "SimpleExplosion"},
    # NiagaraSystemFactoryNew does not take emitters from Python in 5.7 (run 1 made an empty system), so the
    # continuous effect comes from the lightweight (stateless) fountain template instead.
    "Fountain": {"asset_path": "/Game/M13/VFX/NS_GFFountain", "template_system": "FountainLightweight"},
}


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    land.PROJECT_DIR = Path(str(land.PROJECT_DIR).replace("m11_landscape_", "m13_vfx_"))
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    link = land.start(uproject, "vfx")
    try:
        link.call("new_level", {"level_path": "/Game/M13/Maps/VFXTest"})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Floor",
                                  "static_mesh": "/Engine/BasicShapes/Cube.Cube", "location": {"x": 0, "y": 0, "z": -50},
                                  "scale": {"x": 30, "y": 30, "z": 1}})
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0,
                                  "rotation": {"pitch": -45, "yaw": 30, "roll": 0}, "location": {"x": 0, "y": 0, "z": 800}})
        link.call("spawn_actor", {"actor_class": "PlayerStart", "label": "GF_PlayerStart",
                                  "location": {"x": -600, "y": 0, "z": 120}})
        created = {}
        for name, spec in SYSTEMS.items():
            r = link.call("vfx_create_system", spec, timeout_s=120)
            insp = link.call("vfx_inspect_system", {"system_path": spec["asset_path"]})
            created[name] = {"ok": r.get("ok"), "errors": r.get("errors"), "inspect_ok": insp.get("ok"),
                             "path": (r.get("data") or {}).get("asset_path")}
        steps["systems"] = created
        checks["systems_created"] = all(v["ok"] and v["inspect_ok"] for v in created.values())
        link.call("save_all", {})

        steps["pie_start"] = link.call("pie_start", {}).get("ok")
        time.sleep(6.0)
        spawned = {}
        for i, (name, spec) in enumerate(SYSTEMS.items()):
            r = link.call("vfx_spawn", {"system_path": spec["asset_path"], "label": f"GF_{name}", "world": "pie",
                                        "location": {"x": 0, "y": -200 + 400 * i, "z": 50}})
            spawned[name] = {"ok": r.get("ok"), "errors": r.get("errors"), "data": r.get("data")}
        steps["spawned"] = spawned
        peaks, series = {n: 0 for n in SYSTEMS}, []
        t0 = time.time()
        while time.time() - t0 < 6.0:
            c = link.call("vfx_particle_counts", {"world": "pie"})
            sample = {comp["label"]: comp["particles"] for comp in (c.get("data") or {}).get("components", [])}
            series.append({"t": round(time.time() - t0, 2), "counts": sample})
            for n in SYSTEMS:
                peaks[n] = max(peaks[n], int(sample.get(f"GF_{n}", 0)))
            time.sleep(0.25)
        last = link.call("vfx_particle_counts", {"world": "pie"})
        steps["particle_series"] = series
        steps["particle_peaks"] = peaks
        steps["emitters_last"] = (last.get("data") or {}).get("components")
        for n in SYSTEMS:
            checks[f"pie_{n.lower()}_has_live_particles"] = peaks[n] > 0
        link.call("pie_view_from", {"location": {"x": -700, "y": 0, "z": 250}, "rotation": {"pitch": -12, "yaw": 0, "roll": 0}})
        time.sleep(1.0)
        shot = link.capture_screenshot(land.PROJECT_DIR / "Saved" / "Screenshots" / "m13_vfx_pie.png", wait_s=30.0,
                                       show_ui=True)
        steps["screenshot"] = {"path": (shot.get("data") or {}).get("path"), "errors": shot.get("errors")}
        link.call("pie_stop", {})
    finally:
        rep["editor_exit_code"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["gameplay-event trigger", "M11 renderer material", "stat Niagara cost"]}
    try:
        run(rep)
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps(rep["checks"], indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
