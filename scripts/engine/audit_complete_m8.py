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

import argparse
import contextlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = ROOT / "reports" / "audit_m8_completion.json"
START = {"x": -2500.0, "y": -2000.0, "z": 350.0}
LANDMARK = {"x": 2500.0, "y": 2000.0, "z": 450.0}


def _resolve_world_path() -> Path:
    env_override = os.environ.get("GAMEFORGE_AUDIT_WORLD")
    if env_override:
        return Path(env_override)
    return Path(r"E:\GameForge\projects\AuditWorld\AuditWorld.uproject")


def _resolve_probe_path() -> Path:
    s = get_settings()
    return s.require_dev("validation_root") / "live_ops_probe" / "GFProbe.uproject"


def _log_has(path: Path, offset: int, needle: str) -> bool:
    if not path.is_file():
        return False
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(max(0, offset))
        return needle in f.read()


def _merge_step(resp: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(resp, dict):
        return {"errors": ["non-dict response"]}
    data = resp.get("data")
    base = dict(data) if isinstance(data, dict) else {}
    base["errors"] = resp.get("errors")
    return base


def part_a(rep: Dict[str, Any], world_path: Optional[Path] = None) -> None:
    world = world_path or _resolve_world_path()
    world_log = world.parent / "Saved" / "Logs" / f"{world.stem}.log"
    checks, steps = rep["checks"], rep["steps"]
    link = LiveEditorLink(world)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    try:
        link.connect(discovery_timeout_s=900)
        steps["world_inspect"] = _merge_step(link.call("procedural_world_inspect", {}))
        link.call("nav_rebuild", {})
        path: Dict[str, Any] = {}
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            path = link.call("nav_find_path", {"start": START, "end": LANDMARK}) or {}
            if path.get("ok"):
                break
            time.sleep(3)
        nav_step = _merge_step(path)
        steps["nav_path"] = nav_step
        checks["navmesh_path_start_to_landmark"] = (
            bool(path.get("ok")) and float(nav_step.get("length_cm", 0.0)) > 5000.0
        )
        link.call("save_all", {})

        log_offset = world_log.stat().st_size if world_log.is_file() else 0
        link.call("pie_start", {})
        found = False
        trail: List[List[float]] = []
        try:
            time.sleep(6.0)
            move = link.call("pie_move_player_to", {"location": LANDMARK})
            steps["pie_move"] = _merge_step(move)
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline and not found:
                time.sleep(1.0)
                diag = (link.call("pie_character_diagnostics", {}) or {}).get("data", {}) or {}
                chars = diag.get("characters") or []
                if chars and isinstance(chars[0], dict) and "location" in chars[0]:
                    trail.append(chars[0]["location"])
                found = _log_has(world_log, log_offset, "GF_EVENT landmark_discovered")
        finally:
            with contextlib.suppress(Exception):
                link.call("pie_stop", {})
        steps["pie_trail"] = trail
        moved = (
            len(trail) >= 2
            and math.hypot(trail[-1][0] - trail[0][0], trail[-1][1] - trail[0][1]) > 2000.0
        )
        checks["character_traversed_by_navmesh"] = moved
        checks["landmark_discovered_on_arrival"] = found
    finally:
        rep["world_editor_exit"] = link.stop()


def part_b(rep: Dict[str, Any], probe_path: Optional[Path] = None) -> None:
    probe = probe_path or _resolve_probe_path()
    checks, steps = rep["checks"], rep["steps"]
    link = LiveEditorLink(probe)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    try:
        link.connect(discovery_timeout_s=900)
        digests: Dict[str, Dict[str, Any]] = {}
        for label, seed in (("A", 2026), ("B", 2026), ("C", 2027)):
            level = f"/Game/Audit/Maps/SeedWorld_{label}"
            link.call("delete_asset", {"asset_path": level})
            link.call("new_level", {"level_path": level, "if_exists": "replace"})
            land = link.call("landscape_create", {"component_count_x": 2, "component_count_y": 2, "quads_per_section": 63,
                                                  "sections_per_component": 1, "elevation_scale": 1800.0, "seed": seed,
                                                  "terrain_type": "Valley"}, timeout_s=300) or {}
            fol = link.call("foliage_scatter", {"cluster_name": "Foliage_PineValley", "instance_count": 40, "seed": seed + 100,
                                                "area_radius": 3000.0, "min_elevation": -500.0, "max_elevation": 2000.0,
                                                "max_slope_degrees": 35.0, "road_clearance": 0.0}, timeout_s=300) or {}
            dig = link.call("world_generation_digest", {"half_extent": 6000, "step": 500}) or {}
            dig_data = dig.get("data") if isinstance(dig.get("data"), dict) else {}
            digests[label] = {
                "seed": seed,
                "landscape_ok": bool(land.get("ok")),
                "foliage_ok": bool(fol.get("ok")),
                **dig_data,
            }
        steps["seed_digests"] = digests
        checks["same_seed_same_world"] = (
            digests.get("A", {}).get("digest") is not None
            and digests["A"].get("digest") == digests.get("B", {}).get("digest")
            and int(digests["A"].get("instances", 0)) > 0
            and all(d.get("landscape_ok") and d.get("foliage_ok") for d in digests.values())
        )
        checks["different_seed_different_world"] = (
            digests.get("A", {}).get("digest") is not None
            and digests.get("A", {}).get("digest") != digests.get("C", {}).get("digest")
        )

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
        steps["pcg_scatter"] = _merge_step(pcg)
        insp: Dict[str, Any] = {}
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            insp = link.call("pcg_inspect", {}) or {}
            insp_data = insp.get("data") if isinstance(insp.get("data"), dict) else {}
            if insp.get("ok") and not insp_data.get("generating"):
                break
            time.sleep(2)
        insp_step = _merge_step(insp)
        steps["pcg_inspect"] = insp_step
        checks["pcg_graph_generated_instances"] = (
            bool(insp.get("ok")) and int(insp_step.get("instances", 0)) > 0
        )
        link.call("set_viewport_camera", {"location": {"x": -5200, "y": -5200, "z": 3200}, "rotation": {"pitch": -28, "yaw": 45, "roll": 0}})
        shot = link.capture_screenshot(probe.parent / "Saved" / "Screenshots" / "audit_m8_pcg.png", wait_s=30)
        steps["pcg_screenshot"] = shot.get("data") if isinstance(shot, dict) else None
    finally:
        rep["probe_editor_exit"] = link.stop()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit M8 navigation, reproducibility, and PCG.")
    parser.add_argument("parts", nargs="*", choices=["a", "b"], help="Parts to run (default: a b)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    parts = args.parts or ["a", "b"]

    rep: Dict[str, Any] = {}
    if REPORT.is_file():
        try:
            rep = json.loads(REPORT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rep = {}
    rep.setdefault("checks", {})
    rep.setdefault("steps", {})
    rep["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        if "a" in parts:
            part_a(rep)
        if "b" in parts:
            part_b(rep)
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values())
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        tmp = REPORT.with_name(f".{REPORT.name}.tmp.{os.getpid()}")
        try:
            tmp.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, REPORT)
        finally:
            if tmp.exists():
                with contextlib.suppress(OSError):
                    tmp.unlink()
    print(json.dumps(rep["checks"], indent=2))
    print("M8 COMPLETION:", "PASS" if rep["ok"] else "FAIL")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
