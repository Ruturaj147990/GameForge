"""Roadmap M8 v2 step 1: a real surface-sampled PCG graph on a generated landscape (disposable probe copy).

Graph: Get Landscape Data → Surface Sampler → Density Filter → Static Mesh Spawner, built with `pcg_build_graph`.
Proof that the instances came from surface sampling, not a grid: the graph holds those PCG node classes, the
instances sit in PCG-tagged ISM components, and their heights vary with the terrain inside its elevation range.

Evidence: reports/m8v2_pcg_demo.json. Usage: python scripts/demo_m8v2_pcg.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import demo_m11_landscape as land  # noqa: E402

REPORT = REPO / "reports" / "m8v2_pcg_demo.json"
GRAPH = {
    "graph_path": "/Game/M8v2/PCG/PCG_SurfaceScatter", "label": "GF_SurfacePCG", "seed": 42,
    "center": {"x": 0, "y": 0, "z": 0}, "extent": {"x": 6000, "y": 6000, "z": 6000},
    "nodes": [
        {"id": "land", "settings": "PCGGetLandscapeSettings"},
        {"id": "sample", "settings": "PCGSurfaceSamplerSettings", "props": {"points_per_squared_meter": 0.03}},
        {"id": "density", "settings": "PCGDensityFilterSettings", "props": {"lower_bound": 0.35, "upper_bound": 1.0}},
        {"id": "spawn", "settings": "PCGStaticMeshSpawnerSettings",
         "meshes": [{"mesh": "/Engine/BasicShapes/Cone.Cone", "weight": 1}]},
    ],
    "edges": [
        {"from": "land", "from_pin": "Out", "to": "sample", "to_pin": "Surface"},
        {"from": "sample", "from_pin": "Out", "to": "density", "to_pin": "In"},
        {"from": "density", "from_pin": "Out", "to": "spawn", "to_pin": "In"},
    ],
}


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    land.PROJECT_DIR = Path(str(land.PROJECT_DIR).replace("m11_landscape_", "m8v2_pcg_"))
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    link = land.start(uproject, "pcg")
    try:
        link.call("new_level", {"level_path": "/Game/M8v2/Maps/SurfacePCG"})
        terrain = link.call("landscape_create", {"terrain_type": "Valley", "elevation_scale": 2500, "seed": 11},
                            timeout_s=600)
        td = terrain.get("data") or {}
        steps["landscape"] = {k: td.get(k) for k in ("min_elevation_cm", "max_elevation_cm", "size_x", "size_y")} | \
            {"ok": terrain.get("ok"), "errors": terrain.get("errors")}
        built = link.call("pcg_build_graph", GRAPH, timeout_s=300)
        steps["pcg_build"] = (built.get("data") or {}) | {"ok": built.get("ok"), "errors": built.get("errors")}
        checks["graph_built_all_edges"] = bool(built.get("ok"))
        ver = {}
        for _ in range(45):
            ver = link.call("pcg_verify_authenticity", {"label": GRAPH["label"]})
            if ver.get("ok"):
                break
            time.sleep(2.0)
        vd = ver.get("data") or {}
        steps["pcg_verify"] = vd | {"ok": ver.get("ok"), "errors": ver.get("errors")}
        nodes = vd.get("node_settings", [])
        checks["graph_uses_surface_sampler_and_density_filter"] = (
            "PCGSurfaceSamplerSettings" in nodes and "PCGDensityFilterSettings" in nodes
            and "PCGCreatePointsGridSettings" not in nodes)
        checks["instances_in_pcg_tagged_components"] = bool(ver.get("ok"))
        h = vd.get("instance_heights") or {}
        lo, hi = td.get("min_elevation_cm"), td.get("max_elevation_cm")
        checks["instances_follow_terrain"] = bool(h.get("sampled")) and h.get("std_z", 0) > 50 and \
            lo is not None and h["min_z"] >= lo - 100 and h["max_z"] <= hi + 100
        link.call("set_viewport_camera", {"location": {"x": -9000, "y": -3000, "z": 5000},
                                          "rotation": {"pitch": -25, "yaw": 15, "roll": 0}})
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 4.0,
                                  "rotation": {"pitch": -40, "yaw": 30, "roll": 0}, "location": {"x": 0, "y": 0, "z": 9000}})
        link.call("scene_set_manual_exposure", {"exposure_bias": 10.0})
        time.sleep(8.0)
        shot = link.capture_screenshot(land.PROJECT_DIR / "Saved" / "Screenshots" / "m8v2_surface_pcg.png", wait_s=90.0)
        steps["screenshot"] = {"path": (shot.get("data") or {}).get("path"), "errors": shot.get("errors")}
        link.call("save_all", {})
    finally:
        rep["editor_exit_code"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {}}
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
