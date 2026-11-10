"""Roadmap M8 v2 acceptance: "create a forest village" on a disposable probe copy.

World = forest biome landscape with paint layers + LandscapeLayerBlend material + surface-sampled PCG trees/bushes
+ day lighting rig + three kit-built houses seated on the terrain + NavMesh. Checks:
  * saved level; every paint layer resolved; PCG instances follow the terrain;
  * NavMesh path between two POIs (house doors);
  * same seed in a fresh level gives the same world digest, another seed a different one;
  * regenerating in place with a new seed removes only generated content: a user-placed actor survives unchanged.
Not covered here (stays NOT VERIFIED): packaged real-input traversal, World Partition, Data Layers.

Evidence: reports/m8v2_village_demo.json. Usage: python scripts/engine/demo_m8v2_village.py
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
ENGINE_SCRIPTS = str(REPO / "scripts" / "engine")
if ENGINE_SCRIPTS not in sys.path:
    sys.path.insert(0, ENGINE_SCRIPTS)

from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.backend.tools import biomes  # noqa: E402
from src.gameforge_ide.backend.tools.modular_kit import GRID_CM, build_kit, room_layout  # noqa: E402

REPORT = REPO / "reports" / "m8v2_village_demo.json"
BIOME = "forest"
MAT = "/Game/Village/M_ForestLayers"
KIT = "/Game/Kit"
EXTENT = 6000.0
SEED_A, SEED_B = 1234, 98765
EXCLUDE_TAG, EXCLUDE_MARGIN = "GF_PCGExclude", 150.0
MIN_VISIBLE_LAYER_WEIGHT = 8.0  # mean weight out of 255; run 1 had Rock 0.2 and Moss 3.5 (effectively invisible)
USER_ACTOR = {"actor_class": "StaticMeshActor", "label": "User_Statue", "static_mesh": "/Engine/BasicShapes/Cylinder.Cylinder",
              "location": {"x": -4200, "y": 4200, "z": 2500}, "scale": {"x": 1, "y": 1, "z": 3}}


def village_plan(seed: int) -> List[Tuple[float, float, float]]:
    """Three 2x2-cell houses around the valley floor: (x, y, yaw) of each house's local origin."""
    rng = random.Random(seed)
    return [(rng.uniform(-2600, 1800), -2400 + i * 1900 + rng.uniform(-200, 200), rng.choice([0.0, 90.0]))
            for i in range(3)]


def house_placements(origin: Tuple[float, float, float], z: float) -> List[Dict[str, Any]]:
    ox, oy, yaw = origin
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    out = []
    for p in room_layout(2, 2, door_side="south", door_cell=0):
        x, y, _ = p["location"]
        out.append({"piece": p["piece"], "location": [ox + c * x - s * y, oy + s * x + c * y, z],
                    "yaw": (p["yaw"] + yaw) % 360})
    return out


def door_front(origin: Tuple[float, float, float], z: float) -> Dict[str, float]:
    ox, oy, yaw = origin
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    x, y = GRID_CM / 2, -250.0  # outside the south door of cell (0, 0)
    return {"x": ox + c * x - s * y, "y": oy + s * x + c * y, "z": z + 100}


def build_world(link: Any, seed: int, steps: Dict[str, Any], tag: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    la = biomes.landscape_args(BIOME, seed, f"/Game/Village/LayerInfo/{tag}", MAT)
    r = link.call("landscape_create", la, timeout_s=600) or {}
    out["landscape"] = {k: (r.get("data") or {}).get(k) for k in ("min_elevation_cm", "max_elevation_cm", "paint_layers")} \
        | {"ok": r.get("ok"), "errors": r.get("errors")}
    lay: Dict[str, Any] = {}
    for _ in range(30):
        lay = link.call("landscape_inspect_layers", {}) or {}
        if sum(l.get("mean_weight", 0) for l in (lay.get("data") or {}).get("layers", [])) > 200:
            break
        time.sleep(2.0)
    out["layers"] = [(l["name"], round(l.get("mean_weight", 0), 1)) for l in (lay.get("data") or {}).get("layers", [])]
    for actor in biomes.lighting_rig(biomes.BIOMES[BIOME].lighting):
        link.call("spawn_actor", actor)
    houses = []
    for i, origin in enumerate(village_plan(seed)):
        ox, oy, yaw = origin
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        local = [(dx, dy) for dx in (-50, 2 * GRID_CM + 50) for dy in (-50, 2 * GRID_CM + 50)]
        corners = [[ox + c * dx - s * dy, oy + s * dx + c * dy] for dx, dy in local]
        h = link.call("landscape_height_at", {"points": corners}) or {}
        height_vals = [v for v in (h.get("data") or {}).get("heights", [0]) if v is not None]
        z = (max(height_vals, default=0.0)) + 5.0
        placed = 0
        for j, p in enumerate(house_placements(origin, z)):
            x, y, pz = p["location"]
            res = link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": f"GF_House{i}_{j:02d}",
                                            "static_mesh": f"{KIT}/SM_Kit_{p['piece']}", "location": {"x": x, "y": y, "z": pz},
                                            "rotation": {"pitch": 0, "yaw": p["yaw"], "roll": 0}}) or {}
            placed += bool(res.get("ok"))
        xs, ys = [p[0] for p in corners], [p[1] for p in corners]
        center = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2]
        half = [(max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2]
        ex = link.call("spawn_actor", {"actor_class": "TriggerBox", "label": f"GF_House{i}_Exclude",
                                       "location": {"x": center[0], "y": center[1], "z": z},
                                       "scale": {"x": (half[0] + EXCLUDE_MARGIN) / 40.0, "y": (half[1] + EXCLUDE_MARGIN) / 40.0,
                                                 "z": 3000.0 / 40.0}}) or {}
        tg = link.call("set_actor_property", {"label": f"GF_House{i}_Exclude", "property": "tags", "value": [EXCLUDE_TAG]}) or {}
        houses.append({"origin": origin, "floor_z": z, "placed": placed, "door": door_front(origin, z),
                       "footprint": {"center": center, "half": half},
                       "exclusion": {"ok": bool(ex.get("ok")) and bool(tg.get("ok")), "tags": (tg.get("data") or {}).get("value")}})
    out["houses"] = houses
    pcg = []
    for g in biomes.scatter_graphs(BIOME, seed, "/Game/Village/PCG", EXTENT, exclusion_tag=EXCLUDE_TAG):
        b = link.call("pcg_build_graph", g, timeout_s=300) or {}
        pcg.append({"label": g["label"], "ok": b.get("ok"), "errors": b.get("errors")})
    boxes = [h["footprint"] for h in houses]
    for g in pcg:
        v: Dict[str, Any] = {}
        for _ in range(45):
            v = link.call("pcg_verify_authenticity", {"label": g["label"], "exclusion_boxes": boxes}) or {}
            if v.get("ok"):
                break
            time.sleep(2.0)
        g["instances"] = (v.get("data") or {}).get("pcg_instances")
        g["heights"] = (v.get("data") or {}).get("instance_heights")
        g["inside_house_footprints"] = (v.get("data") or {}).get("instances_inside_exclusion_boxes")
        g["node_settings"] = (v.get("data") or {}).get("node_settings")
    out["pcg"] = pcg
    link.call("spawn_actor", {"actor_class": "NavMeshBoundsVolume", "label": "GF_NavBounds",
                              "location": {"x": 0, "y": 0, "z": 0}, "scale": {"x": 60.0, "y": 60.0, "z": 40.0}})
    link.call("nav_rebuild", {})
    time.sleep(3.0)
    digest = link.call("world_generation_digest", {"half_extent": EXTENT, "step": 500}) or {}
    out["digest"] = (digest.get("data") or {}).get("digest")
    out["digest_instances"] = (digest.get("data") or {}).get("instances")
    steps[f"world_{tag}"] = out
    return out


def exclusion_control(link: Any, houses: List[Dict[str, Any]]) -> Dict[str, Any]:
    boxes = [h["footprint"] for h in houses]
    out: Dict[str, Any] = {}
    for name, tag in (("without", None), ("with", EXCLUDE_TAG)):
        g = biomes.scatter_graphs(BIOME, 7, "/Game/Village/PCG/Control", EXTENT, exclusion_tag=tag)[0]
        g["label"], g["graph_path"] = f"GF_PCGCtrl_{name}", f"/Game/Village/PCG/Control/PCG_Ctrl_{name}"
        for n in g["nodes"]:
            if n["id"] == "sample":
                n["props"]["points_per_squared_meter"] = 2.0
            if n["id"] == "density":
                n["props"]["lower_bound"] = 0.0001
        b = link.call("pcg_build_graph", g, timeout_s=300) or {}
        v: Dict[str, Any] = {}
        for _ in range(45):
            v = link.call("pcg_verify_authenticity", {"label": g["label"], "exclusion_boxes": boxes}) or {}
            if v.get("ok"):
                break
            time.sleep(2.0)
        d = v.get("data") or {}
        out[name] = {"build_ok": b.get("ok"), "errors": b.get("errors"), "instances": d.get("pcg_instances"),
                     "inside_per_house": d.get("instances_inside_exclusion_boxes"),
                     "inside": sum(d.get("instances_inside_exclusion_boxes") or [0])}
        link.call("delete_actor", {"label": g["label"]})
    return out


def run(rep: Dict[str, Any]) -> None:
    import demo_m11_landscape as land

    checks, steps = rep["checks"], rep["steps"]
    try:
        val_root = get_settings().require_dev("validation_root")
    except Exception:
        val_root = REPO / "scratch" / "validation"

    land.PROJECT_DIR = val_root / f"m8v2_village_{time.strftime('%Y%m%d')}"
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    data = json.loads(uproject.read_text(encoding="utf-8"))
    if not any(p.get("Name") == "GeometryScripting" for p in data.get("Plugins", [])):
        data.setdefault("Plugins", []).append({"Name": "GeometryScripting", "Enabled": True})
        uproject.write_text(json.dumps(data, indent="\t"), encoding="utf-8")
    link = land.start(uproject, "village")
    try:
        kit_ok = True
        for name, piece in build_kit().items():
            g = link.call("mesh_generate_prop", {"asset_path": f"{KIT}/SM_Kit_{name}", "parts": piece.parts}, timeout_s=300) or {}
            link.call("static_mesh_configure", {"static_mesh_path": f"{KIT}/SM_Kit_{name}", "collision": piece.collision,
                                                "lod_reduction": []}, timeout_s=120)
            kit_ok &= bool(g.get("ok"))
        checks["kit_built"] = kit_ok
        mat = link.call("material_build_graph", biomes.layer_material_graph(BIOME, MAT), timeout_s=300) or {}
        checks["biome_material_built"] = bool(mat.get("ok"))

        # World A, then the same seed in a fresh level (A'), then a different seed (B)
        link.call("new_level", {"level_path": "/Game/Village/Maps/Village_A"})
        a = build_world(link, SEED_A, steps, "A")
        checks["landscape_layers_resolved"] = sum(w for _, w in a["layers"]) > 250
        checks["houses_placed"] = all(h["placed"] == len(room_layout(2, 2)) for h in a["houses"])
        checks["pcg_scatter_follows_terrain"] = all((g.get("instances") or 0) > 0 and
                                                    (g.get("heights") or {}).get("std_z", 0) > 50 for g in a["pcg"])
        checks["every_paint_layer_visible"] = all(w >= MIN_VISIBLE_LAYER_WEIGHT for _, w in a["layers"])
        checks["exclusion_volumes_tagged"] = all(h["exclusion"]["ok"] for h in a["houses"])
        checks["pcg_graph_has_exclusion_nodes"] = all({"PCGDataFromActorSettings", "PCGDifferenceSettings"} <=
                                                      set(g.get("node_settings") or []) for g in a["pcg"])
        checks["no_scatter_inside_houses"] = all(g.get("inside_house_footprints") is not None and
                                                 sum(g["inside_house_footprints"]) == 0 for g in a["pcg"])
        path: Dict[str, Any] = {}
        for _ in range(40):
            path = link.call("nav_find_path", {"start": a["houses"][0]["door"], "end": a["houses"][2]["door"]}) or {}
            if path.get("ok"):
                break
            time.sleep(3.0)
        steps["nav_path"] = (path.get("data") or {}) | {"errors": path.get("errors")}
        checks["navmesh_path_between_pois"] = bool(path.get("ok")) and (path.get("data") or {}).get("length_cm", 0) > 1000
        link.call("set_viewport_camera", {"location": {"x": -7500, "y": -6500, "z": 4200},
                                          "rotation": {"pitch": -22, "yaw": 42, "roll": 0}})
        link.call("scene_set_manual_exposure", {"exposure_bias": 10.0})
        time.sleep(10.0)
        shot = link.capture_screenshot(land.PROJECT_DIR / "Saved" / "Screenshots" / "m8v2_village.png", wait_s=90.0) or {}
        steps["screenshot"] = {"path": (shot.get("data") or {}).get("path"), "errors": shot.get("errors")}
        link.call("save_all", {})
        asset_info = (link.call("asset_exists", {"asset_path": "/Game/Village/Maps/Village_A"}) or {}).get("data") or {}
        checks["level_saved"] = bool(asset_info.get("exists"))

        steps["exclusion_control"] = exclusion_control(link, a["houses"])
        ctl = steps["exclusion_control"]
        checks["exclusion_control_discriminates"] = (ctl["without"]["inside"] or 0) >= 20 and ctl["with"]["inside"] == 0 \
            and (ctl["with"]["instances"] or 0) > 0.5 * (ctl["without"]["instances"] or 1)

        link.call("new_level", {"level_path": "/Game/Village/Maps/Village_A2"})
        a2 = build_world(link, SEED_A, steps, "A2")
        checks["same_seed_same_digest"] = bool(a["digest"]) and a["digest"] == a2["digest"]

        # Regenerate A2 in place with seed B: generated content goes, the user's actor stays put.
        link.call("spawn_actor", USER_ACTOR)
        actors_res = link.call("actors_in_level", {}) or {}
        before = (actors_res.get("data") or {}).get("actors", [])
        user_before = next((x for x in before if x.get("label") == USER_ACTOR["label"]), None)
        cleared = link.call("world_clear_generated", {}) or {}
        steps["clear_generated"] = {"ok": cleared.get("ok"), "deleted": len((cleared.get("data") or {}).get("deleted", [])),
                                    "kept": (cleared.get("data") or {}).get("kept"), "errors": cleared.get("errors")}
        b = build_world(link, SEED_B, steps, "B")
        actors_after_res = link.call("actors_in_level", {}) or {}
        after = (actors_after_res.get("data") or {}).get("actors", [])
        user_after = next((x for x in after if x.get("label") == USER_ACTOR["label"]), None)
        checks["different_seed_different_digest"] = bool(b["digest"]) and b["digest"] != a["digest"]
        checks["user_actor_survives_regeneration"] = bool(user_before) and user_after is not None and \
            user_after.get("location") == user_before.get("location")
        link.call("save_all", {})
    finally:
        rep["editor_exit_code"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["packaged real-input traversal", "World Partition", "Data Layers"]}
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
