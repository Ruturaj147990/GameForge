"""Roadmap M8 v2 / AD-7: World Partition level with a Data Layer that owns all generated content.

On a disposable probe copy: a partitioned level, DataLayer DL_GFGenerated, generated actors (floor, sun, props and
a PCG volume) added to it, and two user actors outside it, one deliberately labelled "GF_UserShrine" (the old
label-prefix ownership rule would delete it). Checks: the level is partitioned and saves One-File-Per-Actor
external actors; layer membership is read back, and again after an editor restart; clearing by Data Layer deletes
exactly the generated set and keeps both user actors.

Evidence: reports/m8v2_datalayers_demo.json. Usage: python scripts/engine/demo_m8v2_datalayers.py
"""

from __future__ import annotations

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

REPORT = REPO / "reports" / "m8v2_datalayers_demo.json"
LEVEL = "/Game/WP/Maps/WPVillage"
LAYER = "/Game/WP/DataLayers/DL_GFGenerated"
GENERATED = [
    {"actor_class": "StaticMeshActor", "label": "GF_Floor", "static_mesh": "/Engine/BasicShapes/Cube.Cube",
     "location": {"x": 0, "y": 0, "z": -50}, "scale": {"x": 40, "y": 40, "z": 1}},
    {"actor_class": "DirectionalLight", "label": "GF_Sun", "mobility": "Movable", "light_intensity": 6.0,
     "rotation": {"pitch": -45, "yaw": 30, "roll": 0}, "location": {"x": 0, "y": 0, "z": 800}},
    *[{"actor_class": "StaticMeshActor", "label": f"GF_Prop_{i:02d}", "static_mesh": "/Engine/BasicShapes/Cylinder.Cylinder",
       "location": {"x": -1500 + 600 * i, "y": 800, "z": 50}} for i in range(6)],
]
USER = [
    {"actor_class": "StaticMeshActor", "label": "User_Statue", "static_mesh": "/Engine/BasicShapes/Cone.Cone",
     "location": {"x": 0, "y": -900, "z": 50}},
    {"actor_class": "StaticMeshActor", "label": "GF_UserShrine", "static_mesh": "/Engine/BasicShapes/Sphere.Sphere",
     "location": {"x": 600, "y": -900, "z": 50}},
]


def run(rep: Dict[str, Any]) -> None:
    import demo_m11_landscape as land

    checks, steps = rep["checks"], rep["steps"]
    try:
        val_root = get_settings().require_dev("validation_root")
    except Exception:
        val_root = REPO / "scratch" / "validation"

    land.PROJECT_DIR = val_root / f"m8v2_datalayers_{time.strftime('%Y%m%d')}"
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    link = land.start(uproject, "dl_a")
    generated_labels = [a["label"] for a in GENERATED] + ["GF_PCGScatter"]
    try:
        nl = link.call("new_level", {"level_path": LEVEL, "partitioned": True}) or {}
        steps["new_level"] = nl.get("data")
        checks["level_is_partitioned"] = bool(nl.get("ok")) and (nl.get("data") or {}).get("partitioned") is True
        dl = link.call("datalayer_ensure", {"asset_path": LAYER}) or {}
        steps["datalayer"] = {"ok": dl.get("ok"), "data": dl.get("data"), "errors": dl.get("errors")}
        checks["data_layer_created"] = bool(dl.get("ok"))
        for a in GENERATED + USER:
            link.call("spawn_actor", a)
        pcg = link.call("pcg_scatter", {"center": {"x": 0, "y": 0, "z": 0}, "extent": {"x": 1500, "y": 1500, "z": 1000}}) or {}
        steps["pcg"] = {"ok": pcg.get("ok"), "errors": pcg.get("errors")}
        add = link.call("datalayer_add_actors", {"asset_path": LAYER, "labels": generated_labels}) or {}
        steps["add"] = {"ok": add.get("ok"), "data": add.get("data"), "errors": add.get("errors")}
        members = ((link.call("datalayer_list_actors", {"asset_path": LAYER}) or {}).get("data") or {}).get("actors", [])
        steps["members_before_restart"] = members
        checks["generated_actors_in_layer"] = sorted(members) == sorted(generated_labels)
        save = link.call("save_all", {}) or {}
        steps["save"] = save.get("data")
    finally:
        rep["editor_exit_code_a"] = link.stop()

    ext = land.PROJECT_DIR / "Content" / "__ExternalActors__" / "WP" / "Maps" / "WPVillage"
    files = list(ext.rglob("*.uasset")) if ext.exists() else []
    steps["external_actor_files"] = len(files)
    checks["one_file_per_actor_saved"] = len(files) >= len(generated_labels) + len(USER)

    link = land.start(uproject, "dl_b")
    try:
        link.call("load_level", {"level_path": LEVEL})
        members = ((link.call("datalayer_list_actors", {"asset_path": LAYER}) or {}).get("data") or {}).get("actors", [])
        steps["members_after_restart"] = members
        checks["layer_membership_persists_after_restart"] = sorted(members) == sorted(generated_labels)
        cleared = link.call("world_clear_generated", {"data_layer_asset": LAYER}) or {}
        data = cleared.get("data") or {}
        steps["clear"] = {"ok": cleared.get("ok"), "rule": data.get("rule"), "deleted": data.get("deleted"),
                          "kept": data.get("kept"), "errors": cleared.get("errors")}
        checks["clear_deletes_exactly_generated"] = bool(cleared.get("ok")) and sorted(data.get("deleted", [])) == sorted(generated_labels)
        kept = set(data.get("kept", []))
        checks["user_actors_kept_including_gf_labelled"] = {"User_Statue", "GF_UserShrine"} <= kept
        # What the interim label-prefix rule would have done to the same level:
        steps["label_prefix_rule_would_delete_user_actor"] = "GF_UserShrine".startswith("GF_")
        link.call("save_all", {})
        after = (link.call("datalayer_list_actors", {"asset_path": LAYER}) or {}).get("data") or {}
        steps["members_after_clear_and_save"] = after
        checks["layer_empty_after_clear_and_save"] = after.get("actors") == []
    finally:
        rep["editor_exit_code_b"] = link.stop()
    left = list(ext.rglob("*.uasset")) if ext.exists() else []
    steps["external_actor_files_after_clear"] = len(left)
    checks["external_actor_files_of_generated_removed"] = len(files) - len(left) == len(generated_labels)


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {},
           "not_covered": ["landscape inside a partitioned world", "runtime streaming / data layer activation in PIE"]}
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
