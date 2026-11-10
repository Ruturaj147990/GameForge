"""Roadmap M12 acceptance demo on a disposable copy of the probe project.

One prop (a recessed-panel crate) goes spec → in-engine Geometry Script generation (quarantine) → LODs +
collision → M11 material instance → engine verification (read-back + screenshot pixel statistics) → promote,
with every stage recorded in the asset registry.

Evidence: reports/m12_asset_demo.json. Usage: python scripts/engine/demo_m12_asset.py
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from src.gameforge_ide.core.settings import get_settings  # noqa: E402
ENGINE_SCRIPTS = str(REPO / "scripts" / "engine")
if ENGINE_SCRIPTS not in sys.path:
    sys.path.insert(0, ENGINE_SCRIPTS)

import demo_m11_material as m11  # noqa: E402
from src.gameforge_ide.backend.assets.registry import AssetRecord, AssetRegistry  # noqa: E402
from src.gameforge_ide.backend.models.asset_spec import LODSpec, MaterialSlotSpec, StaticMeshAssetSpec  # noqa: E402
from src.gameforge_ide.backend.tools.pbr_texture_generator import PBRTextureSpec, generate_texture_set  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

REPORT = REPO / "reports" / "m12_asset_demo.json"


def _get_paths() -> Tuple[Path, Path, Path, Path, Path]:
    s = get_settings()
    try:
        val_root = s.require_dev("validation_root")
        probe = val_root / "live_ops_probe"
        data_root = s.data_root
    except Exception:
        val_root = REPO / "scratch" / "validation"
        probe = REPO / "probe"
        data_root = REPO / "scratch" / "data"
    date_str = time.strftime("%Y%m%d")
    project_dir = val_root / f"m12_demo_{date_str}"
    tex_out = data_root / "assets" / f"generated/textures/m12_demo_{date_str}"
    shots = project_dir / "Saved" / "Screenshots"
    uproject = project_dir / "GFProbe.uproject"
    return probe, project_dir, tex_out, shots, uproject


def _remove_readonly(func: Any, path: str, exc_info: Any) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


SPEC = StaticMeshAssetSpec(asset_id="prop_crate_01", name="GFCrate", purpose="Recessed-panel wooden crate",
                           category="container", size_cm=(80.0, 80.0, 80.0), triangle_budget=2000,
                           lods=LODSpec(reduction=[0.5, 0.25]), collision="box",
                           material_slots=[MaterialSlotSpec(slot_name="Main", pbr_seed=21,
                                                            base_color=(0.55, 0.36, 0.2))])
W = SPEC.size_cm[0]
PANEL, DEPTH = 64.0, 6.0


GROOVES = (16.0, 32.0, 48.0)  # plank seams, measured up from the bottom of each panel


def crate_parts() -> list[dict]:
    """Body box (pivot at bottom centre) with a recessed, plank-grooved panel cut into each of the four sides."""
    half, z0 = W / 2.0, (W - PANEL) / 2.0
    parts = [{"shape": "box", "size": [W, W, W]}]
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        along_x = sy != 0  # the panel spans X when it sits on a ±Y face
        size = [PANEL, 2 * DEPTH, PANEL] if along_x else [2 * DEPTH, PANEL, PANEL]
        parts.append({"shape": "box", "size": size, "location": {"x": sx * half, "y": sy * half, "z": z0},
                      "op": "subtract"})
        inset = half - DEPTH  # panel surface
        for gz in GROOVES:
            gsize = [PANEL, 3.0, 2.0] if along_x else [3.0, PANEL, 2.0]
            parts.append({"shape": "box", "size": gsize,
                          "location": {"x": sx * inset, "y": sy * inset, "z": z0 + gz - 1.0}, "op": "subtract"})
    return parts


def make_disposable() -> Tuple[Path, Path, Path, Path, Path]:
    probe_dir, project_dir, tex_out, shots, uproject = _get_paths()
    if project_dir.exists():
        shutil.rmtree(project_dir, onexc=lambda f, p, e: _remove_readonly(f, p, e))
    shutil.copytree(probe_dir, project_dir, ignore=shutil.ignore_patterns(
        "DerivedDataCache", "Intermediate", "Saved", "__pycache__", ".gameforge"))
    if uproject.exists():
        try:
            data = json.loads(uproject.read_text(encoding="utf-8"))
            if not any(p.get("Name") == "GeometryScripting" for p in data.get("Plugins", [])):
                data.setdefault("Plugins", []).append({"Name": "GeometryScripting", "Enabled": True})
                uproject.write_text(json.dumps(data, indent="\t"), encoding="utf-8")
        except Exception:
            pass
    return probe_dir, project_dir, tex_out, shots, uproject


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    _, project_dir, tex_out, shots_dir, uproject = make_disposable()
    reg = AssetRegistry(project_dir)
    rid = reg.register(AssetRecord(name=SPEC.asset_name(), asset_type="mesh", purpose=SPEC.purpose,
                                   provenance="procedural", backend="UE5.7.4-GeometryScript", backend_version="5.7.4",
                                   license="project-owned (procedural)", spec=SPEC.model_dump(), tags=SPEC.tags))
    reg.advance(rid, "SPEC", True, "StaticMeshAssetSpec validated")
    steps["registry_id"] = rid
    quarantined = f"{SPEC.quarantine_path}/{SPEC.asset_name()}"
    promoted = f"{SPEC.destination_path}/{SPEC.asset_name()}"

    slot = SPEC.material_slots[0]
    manifest = generate_texture_set(PBRTextureSpec(name="GFProcRock", size=512, seed=slot.pbr_seed,
                                                   base_color=slot.base_color, color_variation=0.45), tex_out)

    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=project_dir / "m12_editor.log")
    try:
        link.connect(discovery_timeout_s=900)
        api = link.call("api_introspect", {"classes": ["GeometryScript_Primitives", "GeometryScript_MeshBooleans",
                                                       "GeometryScript_UVs", "GeometryScript_NewAssetUtils",
                                                       "GeometryScript_MeshSimplification", "StaticMeshEditorSubsystem",
                                                       "GeometryScript_MeshQueries", "GeometryScript_AssetUtils",
                                                       "GeometryScript_Normals", "StaticMesh"]})
        steps["api_detail"] = api.get("data")
        steps["api_available"] = {k: (v is not None) for k, v in ((api.get("data") or {}).get("classes") or {}).items()}

        # Generation in quarantine
        gen = link.call("mesh_generate_prop", {"asset_path": quarantined, "parts": crate_parts(),
                                               "triangle_budget": SPEC.triangle_budget}, timeout_s=300)
        steps["generate"] = (gen.get("data") or {}) | {"ok": gen.get("ok"), "errors": gen.get("errors")}
        checks["generated_in_engine"] = bool(gen.get("ok"))
        reg.advance(rid, "GENERATE", bool(gen.get("ok")), "; ".join(gen.get("errors") or []), unreal_path=quarantined)
        if not gen.get("ok"):
            return

        # Material (M11 ops) for the single slot
        link.call("new_level", {"level_path": "/Game/M12/Maps/M12Demo"})
        for role, tex_role in m11.ROLES.items():
            link.call("texture_import", {"source_file": manifest["files"][role]["path"], "role": tex_role,
                                         "destination_path": "/Game/M11/Textures",
                                         "destination_name": f"T_GFProcRock_{role}"}, timeout_s=180)
        link.call("material_build_graph", m11.material_graph(), timeout_s=300)
        mi = link.call("material_instance_create", {"asset_path": m11.MI, "parent": m11.MAT,
                                                    "scalars": {"Tiling": 1.0, "RoughnessScale": 0.95},
                                                    "vectors": {"Tint": [1.0, 0.9, 0.8, 1.0]}}, timeout_s=120)
        steps["material_instance"] = {"ok": mi.get("ok"), "errors": mi.get("errors")}

        # LODs, collision, Nanite flag, material binding — then read back
        cfg = link.call("static_mesh_configure", {"static_mesh_path": quarantined, "lod_reduction": SPEC.lods.reduction,
                                                  "collision": SPEC.collision, "nanite": SPEC.nanite,
                                                  "materials": [m11.MI]}, timeout_s=300)
        steps["configure"] = (cfg.get("data") or {}) | {"ok": cfg.get("ok"), "errors": cfg.get("errors")}
        insp = link.call("static_mesh_inspect", {"static_mesh_path": quarantined})
        d = insp.get("data") or {}
        steps["inspect_quarantine"] = d | {"ok": insp.get("ok"), "errors": insp.get("errors")}
        tris = d.get("lod_triangles") or []
        checks["lod_count_matches_spec"] = d.get("lod_count") == SPEC.lod_count
        checks["lod_triangles_decrease"] = (len(tris) == SPEC.lod_count and all(t for t in tris)
                                            and all(b < a for a, b in zip(tris, tris[1:])))
        checks["lod0_within_budget"] = bool(tris) and tris[0] <= SPEC.triangle_budget
        checks["simple_collision_present"] = (d.get("simple_collision_count") or 0) >= 1
        checks["bounds_match_spec"] = bool(d.get("bounds_cm")) and all(
            abs(a - b) <= 0.02 * b for a, b in zip(d["bounds_cm"], SPEC.size_cm))
        checks["material_bound"] = any(m11.MI in (m or "") for m in d.get("materials", []))
        valid = all(checks.get(k) for k in ("lod_count_matches_spec", "lod_triangles_decrease", "lod0_within_budget",
                                             "simple_collision_present", "bounds_match_spec", "material_bound"))
        reg.advance(rid, "VALIDATE", valid, json.dumps({"lod_triangles": tris, "bounds_cm": d.get("bounds_cm")}))
        reg.advance(rid, "QUARANTINE", valid, "in /Game/Quarantine/Props", unreal_path=quarantined)

        # Engine verification: place it, light it, capture it
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0,
                                  "rotation": {"pitch": -35, "yaw": 160, "roll": 0}, "location": {"x": 0, "y": 0, "z": 600}})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Crate", "static_mesh": quarantined,
                                  "location": {"x": 0, "y": 0, "z": 0}, "rotation": {"pitch": 0, "yaw": 30, "roll": 0}})
        link.call("set_viewport_camera", {"location": {"x": 230, "y": 0, "z": 120},
                                          "rotation": {"pitch": -15, "yaw": 180, "roll": 0}})
        time.sleep(8.0)
        shot = link.capture_screenshot(shots_dir / "m12_crate.png", wait_s=60.0) or {}
        path = (shot.get("data") or {}).get("path")
        stats = m11.crop_stats(Path(path)) if path else None
        steps["screenshot"] = {"path": path, "stats": stats, "errors": shot.get("errors")}
        checks["screenshot_shows_textured_prop"] = bool(stats) and stats["crop_lum_std"] > 3.0 and \
            stats["red_over_blue"] > 1.2 and sum(stats["crop_mean_rgb"]) > 60
        rel_report = str(REPORT.relative_to(REPO)).replace("\\", "/") if REPORT.is_relative_to(REPO) else str(REPORT)
        reg.advance(rid, "ENGINE_VERIFY", checks["screenshot_shows_textured_prop"] and valid,
                    "read-back + screenshot pixel statistics", [rel_report])

        # Promotion out of quarantine, only after the registry holds a passed ENGINE_VERIFY
        if reg.get(rid)["stage"] != "ENGINE_VERIFY":
            steps["promotion_skipped"] = f"registry stage is {reg.get(rid)['stage']}, not a passed ENGINE_VERIFY"
            checks["promoted_and_readable"] = False
            link.call("save_all", {})
            steps["registry_row"] = dict(reg.get(rid))
            steps["registry_history"] = [dict(r) for r in reg.history(rid)]
            return
        mv = link.call("rename_asset", {"source_path": quarantined, "destination_path": promoted})
        after = link.call("static_mesh_inspect", {"static_mesh_path": promoted})
        steps["promote"] = {"ok": mv.get("ok"), "errors": mv.get("errors"), "inspect": after.get("data")}
        checks["promoted_and_readable"] = bool(mv.get("ok")) and bool(after.get("ok")) and \
            (after.get("data") or {}).get("lod_triangles") == tris
        try:
            reg.advance(rid, "PROMOTE", checks["promoted_and_readable"], "rename_asset out of quarantine",
                        unreal_path=promoted if checks["promoted_and_readable"] else None)
        except ValueError as exc:  # no passed ENGINE_VERIFY: the registry refuses, as designed
            steps["promote_refused"] = str(exc)
        link.call("save_all", {})
        steps["registry_row"] = dict(reg.get(rid))
        steps["registry_history"] = [dict(r) for r in reg.history(rid)]
    finally:
        rep["editor_exit_code"] = link.stop()


def main() -> int:
    _, project_dir, _, _, _ = _get_paths()
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "project": str(project_dir), "spec": SPEC.model_dump(),
           "checks": {}, "steps": {}}
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
