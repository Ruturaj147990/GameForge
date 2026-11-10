"""Roadmap M12 step 3 engine check: build the modular kit in-engine and assemble a room from it.

Every kit piece is generated with Geometry Script (`mesh_generate_prop`), given collision, and read back; the
bounds must match the kit definition. A 3 x 2 room from `room_layout` is then placed and captured.

Evidence: reports/m12_kit_demo.json. Usage: python scripts/engine/demo_m12_kit.py
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
from src.gameforge_ide.backend.tools.modular_kit import build_kit, room_layout  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = REPO / "reports" / "m12_kit_demo.json"
KIT_PATH = "/Game/Kit"
ROOM = (3, 2)


def run(rep: Dict[str, Any]) -> None:
    import demo_m11_material as m11
    import demo_m12_asset as m12

    checks, steps = rep["checks"], rep["steps"]
    try:
        val_root = get_settings().require_dev("validation_root")
    except Exception:
        val_root = REPO / "scratch" / "validation"
    proj_dir = val_root / f"m12_kit_demo_{time.strftime('%Y%m%d')}"
    rep["project"] = str(proj_dir)

    # Prepare probe project
    probe_dir, _, _, _, _ = m12._get_paths()
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir, onexc=lambda f, p, e: m12._remove_readonly(f, p, e))
    import shutil
    shutil.copytree(probe_dir, proj_dir, ignore=shutil.ignore_patterns(
        "DerivedDataCache", "Intermediate", "Saved", "__pycache__", ".gameforge"))
    uproject = proj_dir / "GFProbe.uproject"
    if uproject.exists():
        try:
            data = json.loads(uproject.read_text(encoding="utf-8"))
            if not any(p.get("Name") == "GeometryScripting" for p in data.get("Plugins", [])):
                data.setdefault("Plugins", []).append({"Name": "GeometryScripting", "Enabled": True})
                uproject.write_text(json.dumps(data, indent="\t"), encoding="utf-8")
        except Exception:
            pass

    kit = build_kit()
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=proj_dir / "kit_editor.log")
    try:
        link.connect(discovery_timeout_s=900)
        built = {}
        for name, piece in kit.items():
            path = f"{KIT_PATH}/SM_Kit_{name}"
            gen = link.call("mesh_generate_prop", {"asset_path": path, "parts": piece.parts}, timeout_s=300) or {}
            cfg = link.call("static_mesh_configure", {"static_mesh_path": path, "collision": piece.collision,
                                                      "lod_reduction": []}, timeout_s=120) or {}
            insp = link.call("static_mesh_inspect", {"static_mesh_path": path}) or {}
            d = insp.get("data") if isinstance(insp.get("data"), dict) else {}
            bounds_ok = bool(d.get("bounds_cm")) and all(abs(a - b) <= 0.01 * b + 0.5
                                                         for a, b in zip(d["bounds_cm"], piece.bounds_cm))
            built[name] = {"ok": bool(gen.get("ok")) and bool(cfg.get("ok")) and bool(insp.get("ok")),
                           "errors": (gen.get("errors") or []) + (cfg.get("errors") or []),
                           "triangles": (d.get("lod_triangles") or [None])[0], "bounds_cm": d.get("bounds_cm"),
                           "expected_bounds_cm": list(piece.bounds_cm), "bounds_ok": bounds_ok,
                           "collision": d.get("collision_complexity"), "simple_collisions": d.get("simple_collision_count")}
        steps["pieces"] = built
        checks["all_pieces_built"] = bool(built) and all(b["ok"] for b in built.values())
        checks["piece_bounds_match_kit"] = bool(built) and all(b["bounds_ok"] for b in built.values())
        tri = {k: v["triangles"] or 0 for k, v in built.items()}
        checks["openings_cut"] = (
            tri.get("WallDoor", 0) > tri.get("Wall", 0) and
            tri.get("WallWindow", 0) > tri.get("Wall", 0)
        )

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
                                          "rotation": {"pitch": 0, "yaw": p["yaw"], "roll": 0}}) or {}
            placed += bool(r.get("ok"))
        steps["layout"] = {"pieces": len(layout), "placed": placed}
        checks["room_assembled"] = placed == len(layout)
        cx, cy = ROOM[0] * 200.0, ROOM[1] * 200.0
        link.call("set_viewport_camera", {"location": {"x": cx, "y": cy - 1500, "z": 1100},
                                          "rotation": {"pitch": -38, "yaw": 90, "roll": 0}})
        time.sleep(8.0)
        shot = link.capture_screenshot(proj_dir / "Saved" / "Screenshots" / "m12_kit_room.png", wait_s=60.0) or {}
        path = (shot.get("data") or {}).get("path")
        stats = m11.crop_stats(Path(path)) if path else None
        steps["screenshot"] = {"path": path, "stats": stats, "errors": shot.get("errors")}
        checks["screenshot_has_content"] = bool(stats) and sum(stats["crop_mean_rgb"]) > 60
        link.call("save_all", {})
    finally:
        rep["editor_exit_code"] = link.stop()


def main() -> int:
    rep: Dict[str, Any] = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {}}
    try:
        run(rep)
    except Exception as exc:
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        tmp = REPORT.with_name(f".{REPORT.name}.tmp.{os.getpid()}")
        try:
            tmp.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, REPORT)
        finally:
            if tmp.exists():
                with contextlib.suppress(OSError):
                    tmp.unlink()
    print(json.dumps(rep["checks"], indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
