"""Roadmap M12 step 3 engine check: build the modular kit in-engine and assemble a room from it.

Every kit piece is generated with Geometry Script (`mesh_generate_prop`), given collision, and read back; the
bounds must match the kit definition. A 3 x 2 room from `room_layout` is then placed and captured.

Evidence: reports/m12_kit_demo.json. Usage: python scripts/engine/demo_m12_kit.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import demo_m11_material as m11  # noqa: E402
import demo_m12_asset as m12  # noqa: E402
from src.gameforge_ide.backend.tools.modular_kit import build_kit, room_layout  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = REPO / "reports" / "m12_kit_demo.json"
KIT_PATH = "/Game/Kit"
ROOM = (3, 2)


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    m12.PROJECT_DIR = Path(str(m12.PROJECT_DIR).replace("m12_demo_", "m12_kit_demo_"))
    uproject = m12.make_disposable()
    rep["project"] = str(m12.PROJECT_DIR)
    kit = build_kit()
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=m12.PROJECT_DIR / "kit_editor.log")
    try:
        link.connect(discovery_timeout_s=900)
        built = {}
        for name, piece in kit.items():
            path = f"{KIT_PATH}/SM_Kit_{name}"
            gen = link.call("mesh_generate_prop", {"asset_path": path, "parts": piece.parts}, timeout_s=300)
            cfg = link.call("static_mesh_configure", {"static_mesh_path": path, "collision": piece.collision,
                                                      "lod_reduction": []}, timeout_s=120)
            insp = link.call("static_mesh_inspect", {"static_mesh_path": path})
            d = insp.get("data") or {}
            bounds_ok = bool(d.get("bounds_cm")) and all(abs(a - b) <= 0.01 * b + 0.5
                                                         for a, b in zip(d["bounds_cm"], piece.bounds_cm))
            built[name] = {"ok": bool(gen.get("ok")) and bool(cfg.get("ok")) and bool(insp.get("ok")),
                           "errors": (gen.get("errors") or []) + (cfg.get("errors") or []),
                           "triangles": (d.get("lod_triangles") or [None])[0], "bounds_cm": d.get("bounds_cm"),
                           "expected_bounds_cm": list(piece.bounds_cm), "bounds_ok": bounds_ok,
                           "collision": d.get("collision_complexity"), "simple_collisions": d.get("simple_collision_count")}
        steps["pieces"] = built
        checks["all_pieces_built"] = all(b["ok"] for b in built.values())
        checks["piece_bounds_match_kit"] = all(b["bounds_ok"] for b in built.values())
        tri = {k: v["triangles"] or 0 for k, v in built.items()}
        checks["openings_cut"] = tri["WallDoor"] > tri["Wall"] and tri["WallWindow"] > tri["Wall"]

        link.call("new_level", {"level_path": "/Game/Kit/Maps/KitRoom"})
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0,
                                  "rotation": {"pitch": -50, "yaw": 210, "roll": 0}, "location": {"x": 0, "y": 0, "z": 900}})
        layout = room_layout(*ROOM, door_side="south", door_cell=1)
        placed = 0
        for i, p in enumerate(layout):
            x, y, z = p["location"]
            r = link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": f"GF_Kit_{i:02d}",
                                          "static_mesh": f"{KIT_PATH}/SM_Kit_{p['piece']}",
                                          "location": {"x": x, "y": y, "z": z},
                                          "rotation": {"pitch": 0, "yaw": p["yaw"], "roll": 0}})
            placed += bool(r.get("ok"))
        steps["layout"] = {"pieces": len(layout), "placed": placed}
        checks["room_assembled"] = placed == len(layout)
        cx, cy = ROOM[0] * 200.0, ROOM[1] * 200.0
        link.call("set_viewport_camera", {"location": {"x": cx, "y": cy - 1500, "z": 1100},
                                          "rotation": {"pitch": -38, "yaw": 90, "roll": 0}})
        time.sleep(8.0)
        shot = link.capture_screenshot(m12.PROJECT_DIR / "Saved" / "Screenshots" / "m12_kit_room.png", wait_s=60.0)
        path = (shot.get("data") or {}).get("path")
        stats = m11.crop_stats(Path(path)) if path else None
        steps["screenshot"] = {"path": path, "stats": stats, "errors": shot.get("errors")}
        checks["screenshot_has_content"] = bool(stats) and sum(stats["crop_mean_rgb"]) > 60
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
