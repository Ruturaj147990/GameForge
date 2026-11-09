"""Audit 2026-10-30 (completion): M8 navigation, traversal, reproducibility and PCG in real UE 5.7.4.

A. AuditWorld (the generated procedural game): a complete NavMesh path from PlayerStart to the
   Ancient Ruins landmark; then, in PIE, the player's own character pathfinds there and the game's
   landmark trigger must fire (GF_EVENT landmark_discovered) because the character arrived.
B. Probe project: same seed -> identical world digest (terrain heights + every instance transform);
   different seed -> different digest. A real PCG graph (Landscape -> Surface Sampler -> Static
   Mesh Spawner) generated over a landscape must produce instances.
Evidence: reports/audit_m8_completion.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.gameforge_ide.core.settings import get_settings  # noqa: E402

from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

WORLD = Path(r"E:\GameForge\projects\AuditWorld\AuditWorld.uproject")
PROBE = (get_settings().require_dev("validation_root") / r"live_ops_probe\GFProbe.uproject")
REPORT = ROOT / "reports" / "audit_m8_completion.json"
START = {"x": -2500.0, "y": -2000.0, "z": 350.0}
LANDMARK = {"x": 2500.0, "y": 2000.0, "z": 450.0}
WORLD_LOG = WORLD.parent / "Saved" / "Logs" / "AuditWorld.log"


def _log_has(path: Path, offset: int, needle: str) -> bool:
    if not path.is_file():
        return False
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        return needle in f.read()


def part_a(rep):
    checks, steps = rep["checks"], rep["steps"]
    link = LiveEditorLink(WORLD)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    try:
        link.connect(discovery_timeout_s=900)
        steps["world_inspect"] = link.call("procedural_world_inspect", {}).get("data")
        link.call("nav_rebuild", {})
        path = {}
        deadline = time.time() + 120
        while time.time() < deadline:
            path = link.call("nav_find_path", {"start": START, "end": LANDMARK})
            if path.get("ok"):
                break
            time.sleep(3)
        steps["nav_path"] = path.get("data") | {"errors": path.get("errors")}
        checks["navmesh_path_start_to_landmark"] = bool(path.get("ok")) and path["data"]["length_cm"] > 5000
        link.call("save_all", {})

        log_offset = WORLD_LOG.stat().st_size if WORLD_LOG.is_file() else 0
        link.call("pie_start", {})
        time.sleep(6.0)
        move = link.call("pie_move_player_to", {"location": LANDMARK})
        steps["pie_move"] = move.get("data") | {"errors": move.get("errors")}
        found, trail = False, []
        deadline = time.time() + 60
        while time.time() < deadline and not found:
            time.sleep(1.0)
            diag = link.call("pie_character_diagnostics", {}).get("data", {}).get("characters", [])
            if diag:
                trail.append(diag[0]["location"])
            found = _log_has(WORLD_LOG, log_offset, "GF_EVENT landmark_discovered")
        link.call("pie_stop", {})
        steps["pie_trail"] = trail
        moved = len(trail) >= 2 and ((trail[-1][0] - trail[0][0]) ** 2 + (trail[-1][1] - trail[0][1]) ** 2) ** 0.5 > 2000
        checks["character_traversed_by_navmesh"] = moved
        checks["landmark_discovered_on_arrival"] = found
    finally:
        rep["world_editor_exit"] = link.stop()


def part_b(rep):
    checks, steps = rep["checks"], rep["steps"]
    link = LiveEditorLink(PROBE)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    try:
        link.connect(discovery_timeout_s=900)
        digests = {}
        for label, seed in (("A", 2026), ("B", 2026), ("C", 2027)):
            level = f"/Game/Audit/Maps/SeedWorld_{label}"
            link.call("delete_asset", {"asset_path": level})
            link.call("new_level", {"level_path": level, "if_exists": "replace"})
            land = link.call("landscape_create", {"component_count_x": 2, "component_count_y": 2, "quads_per_section": 63,
                                                  "sections_per_component": 1, "elevation_scale": 1800.0, "seed": seed,
                                                  "terrain_type": "Valley"}, timeout_s=300)
            fol = link.call("foliage_scatter", {"cluster_name": "Foliage_PineValley", "instance_count": 40, "seed": seed + 100,
                                                "area_radius": 3000.0, "min_elevation": -500.0, "max_elevation": 2000.0,
                                                "max_slope_degrees": 35.0, "road_clearance": 0.0}, timeout_s=300)
            dig = link.call("world_generation_digest", {"half_extent": 6000, "step": 500})
            digests[label] = {"seed": seed, "landscape_ok": land.get("ok"), "foliage_ok": fol.get("ok"), **dig.get("data", {})}
        steps["seed_digests"] = digests
        checks["same_seed_same_world"] = (digests["A"]["digest"] == digests["B"]["digest"] and digests["A"]["instances"] > 0
                                          and all(d["landscape_ok"] and d["foliage_ok"] for d in digests.values()))
        checks["different_seed_different_world"] = digests["A"]["digest"] != digests["C"]["digest"]

        # PCG on a fresh landscape
        link.call("delete_asset", {"asset_path": "/Game/Audit/Maps/PCGWorld"})
        link.call("new_level", {"level_path": "/Game/Audit/Maps/PCGWorld", "if_exists": "replace"})
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "Sun", "mobility": "Movable",
                                  "light_intensity": 10.0, "rotation": {"pitch": -50, "yaw": 45, "roll": 0}})
        link.call("landscape_create", {"component_count_x": 2, "component_count_y": 2, "quads_per_section": 63,
                                       "sections_per_component": 1, "elevation_scale": 1800.0, "seed": 2026,
                                       "terrain_type": "Valley"}, timeout_s=300)
        pcg = link.call("pcg_scatter", {"points_per_m2": 0.005, "center": {"x": 0, "y": 0, "z": 500},
                                        "extent": {"x": 4000, "y": 4000, "z": 3000}})
        steps["pcg_scatter"] = pcg.get("data") | {"errors": pcg.get("errors")}
        insp = {}
        deadline = time.time() + 90
        while time.time() < deadline:
            insp = link.call("pcg_inspect", {})
            if insp.get("ok") and not insp["data"].get("generating"):
                break
            time.sleep(2)
        steps["pcg_inspect"] = insp.get("data") | {"errors": insp.get("errors")}
        checks["pcg_graph_generated_instances"] = bool(insp.get("ok")) and insp["data"]["instances"] > 0
        link.call("set_viewport_camera", {"location": {"x": -5200, "y": -5200, "z": 3200}, "rotation": {"pitch": -28, "yaw": 45, "roll": 0}})
        steps["pcg_screenshot"] = link.capture_screenshot(PROBE.parent / "Saved" / "Screenshots" / "audit_m8_pcg.png", wait_s=30).get("data")
    finally:
        rep["probe_editor_exit"] = link.stop()


def main(argv) -> int:
    rep = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.is_file() else {}
    rep.setdefault("checks", {}); rep.setdefault("steps", {})
    rep["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    parts = argv or ["a", "b"]
    try:
        if "a" in parts:
            part_a(rep)
        if "b" in parts:
            part_b(rep)
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values())
        REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps(rep["checks"], indent=2))
    print("M8 COMPLETION:", "PASS" if rep["ok"] else "FAIL")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
