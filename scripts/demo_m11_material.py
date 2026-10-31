"""Roadmap M11 acceptance demo on a disposable copy of the probe project.

Generate a procedural PBR set → import with per-role sRGB/compression → build M_ (texture samples, tiling,
tint and roughness parameters) → MI_ with overrides → assign to a cube → screenshot with the default material
and with the MI, compare pixel statistics → restart the editor → the read-back must be identical.

Evidence: reports/m11_material_demo.json and screenshots under the disposable project's Saved/Screenshots.
Usage: python scripts/demo_m11_material.py
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.gameforge_ide.backend.assets.registry import AssetRegistry  # noqa: E402
from src.gameforge_ide.backend.tools.pbr_texture_generator import (  # noqa: E402
    PBRTextureSpec, generate_texture_set, read_png, validate_texture_set)
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

PROBE = Path(r"E:\GameForge\validation\live_ops_probe")
DATE = time.strftime("%Y%m%d")
PROJECT_DIR = Path(rf"E:\GameForge\validation\m11_demo_{DATE}")
TEX_OUT = Path(rf"E:\GameForge\assets\generated\textures\m11_demo_{DATE}")
REPORT = REPO / "reports" / "m11_material_demo.json"
SHOTS = PROJECT_DIR / "Saved" / "Screenshots"

ROOT = "/Game/M11"
MAT = f"{ROOT}/Materials/M_GFProcRock"
MI = f"{ROOT}/Materials/MI_GFProcRock_Warm"
ROLES = {"BaseColor": "color", "Normal": "normal", "ORM": "masks"}
CAMERA = {"location": {"x": 420, "y": 0, "z": 100}, "rotation": {"pitch": 0, "yaw": 180, "roll": 0}}
MI_SCALARS = {"Tiling": 3.0, "RoughnessScale": 0.9}
MI_VECTORS = {"Tint": [1.0, 0.85, 0.7, 1.0]}


def tex_path(role: str) -> str:
    return f"{ROOT}/Textures/T_GFProcRock_{role}"


def material_graph() -> dict:
    sample = "MaterialExpressionTextureSample"
    return {
        "asset_path": MAT, "replace_existing": True,
        "nodes": [
            {"id": "uv", "class": "MaterialExpressionTextureCoordinate", "x": -1400, "y": 0},
            {"id": "tiling", "class": "MaterialExpressionScalarParameter", "x": -1400, "y": 150,
             "props": {"parameter_name": "Tiling", "default_value": 2.0}},
            {"id": "uvmul", "class": "MaterialExpressionMultiply", "x": -1200, "y": 50},
            {"id": "bc", "class": sample, "x": -900, "y": -300,
             "props": {"texture": tex_path("BaseColor"), "sampler_type": "color"}},
            {"id": "tint", "class": "MaterialExpressionVectorParameter", "x": -900, "y": -500,
             "props": {"parameter_name": "Tint", "default_value": [1.0, 1.0, 1.0, 1.0]}},
            {"id": "bcmul", "class": "MaterialExpressionMultiply", "x": -500, "y": -350},
            {"id": "n", "class": sample, "x": -900, "y": 0,
             "props": {"texture": tex_path("Normal"), "sampler_type": "normal"}},
            {"id": "orm", "class": sample, "x": -900, "y": 300,
             "props": {"texture": tex_path("ORM"), "sampler_type": "masks"}},
            {"id": "rscale", "class": "MaterialExpressionScalarParameter", "x": -900, "y": 550,
             "props": {"parameter_name": "RoughnessScale", "default_value": 1.0}},
            {"id": "rmul", "class": "MaterialExpressionMultiply", "x": -500, "y": 350},
        ],
        "edges": [
            {"from": "uv", "to": "uvmul", "input": "A"}, {"from": "tiling", "to": "uvmul", "input": "B"},
            {"from": "uvmul", "to": "bc", "input": "UVs"}, {"from": "uvmul", "to": "n", "input": "UVs"},
            {"from": "uvmul", "to": "orm", "input": "UVs"},
            {"from": "bc", "output": "RGB", "to": "bcmul", "input": "A"}, {"from": "tint", "to": "bcmul", "input": "B"},
            {"from": "orm", "output": "G", "to": "rmul", "input": "A"}, {"from": "rscale", "to": "rmul", "input": "B"},
        ],
        "outputs": [
            {"from": "bcmul", "property": "MP_BASE_COLOR"}, {"from": "n", "output": "RGB", "property": "MP_NORMAL"},
            {"from": "orm", "output": "R", "property": "MP_AMBIENT_OCCLUSION"},
            {"from": "rmul", "property": "MP_ROUGHNESS"}, {"from": "orm", "output": "B", "property": "MP_METALLIC"},
        ],
    }


MF = f"{ROOT}/Functions/MF_GFContrast"
MAT_MF = f"{ROOT}/Materials/M_GFProcRock_Contrast"


def contrast_function() -> dict:
    """MF_GFContrast(Color: vec3, Contrast: scalar) -> Result = Color ^ Contrast."""
    return {"asset_path": MF, "description": "GameForge contrast curve (Color ^ Contrast)",
            "nodes": [{"id": "color", "class": "MaterialExpressionFunctionInput", "x": -600, "y": 0,
                       "props": {"input_name": "Color", "input_type": "FUNCTION_INPUT_VECTOR3"}},
                      {"id": "contrast", "class": "MaterialExpressionFunctionInput", "x": -600, "y": 200,
                       "props": {"input_name": "Contrast", "input_type": "FUNCTION_INPUT_SCALAR"}},
                      {"id": "pow", "class": "MaterialExpressionPower", "x": -300, "y": 100},
                      {"id": "out", "class": "MaterialExpressionFunctionOutput", "x": 0, "y": 100,
                       "props": {"output_name": "Result"}}],
            "edges": [{"from": "color", "to": "pow", "input": "Base"}, {"from": "contrast", "to": "pow", "input": "Exp"},
                      {"from": "pow", "to": "out", "input": ""}]}


def function_material() -> dict:
    return {"asset_path": MAT_MF, "replace_existing": True,
            "nodes": [{"id": "bc", "class": "MaterialExpressionTextureSample", "x": -900, "y": 0,
                       "props": {"texture": tex_path("BaseColor"), "sampler_type": "color"}},
                      {"id": "k", "class": "MaterialExpressionConstant", "x": -900, "y": 250, "props": {"r": 1.6}},
                      {"id": "call", "class": "MaterialExpressionMaterialFunctionCall", "x": -500, "y": 0,
                       "props": {"material_function": MF}}],
            "edges": [{"from": "bc", "output": "RGB", "to": "call", "input": "Color"},
                      {"from": "k", "to": "call", "input": "Contrast"}],
            "outputs": [{"from": "call", "output": "Result", "property": "MP_BASE_COLOR"}]}


def crop_stats(path: Path) -> dict:
    """Centre-crop (the cube face) colour statistics of a screenshot."""
    try:
        from PIL import Image  # faster when present; the fallback reader handles every PNG filter
        img = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    except ImportError:
        img = read_png(path)[..., :3].astype(np.float64)
    h, w = img.shape[:2]
    c = img[int(h * 0.4):int(h * 0.6), int(w * 0.44):int(w * 0.56)]
    lum = c.mean(axis=2)
    mean = c.reshape(-1, 3).mean(axis=0)
    return {"size": [w, h], "crop_mean_rgb": [round(float(x), 2) for x in mean],
            "crop_lum_std": round(float(lum.std()), 2),
            "crop_hf_energy": round(float(np.abs(np.diff(lum, axis=1)).mean()), 3),
            "red_over_blue": round(float(mean[0] / max(mean[2], 1e-6)), 3)}


def readback(link) -> dict:
    out = {"material": link.call("material_readback_graph", {"material_path": MAT}),
           "instance": link.call("material_instance_inspect", {"instance_path": MI, "scalars": list(MI_SCALARS),
                                                               "vectors": list(MI_VECTORS)}),
           "textures": {r: link.call("texture_inspect", {"texture_path": tex_path(r)}) for r in ROLES}}
    return {"material": out["material"].get("data"), "material_ok": out["material"].get("ok"),
            "material_errors": out["material"].get("errors"),
            "instance": out["instance"].get("data"), "instance_ok": out["instance"].get("ok"),
            "textures": {r: v.get("data") for r, v in out["textures"].items()},
            "textures_ok": all(v.get("ok") for v in out["textures"].values())}


def make_disposable() -> Path:
    if PROJECT_DIR.exists():
        shutil.rmtree(PROJECT_DIR)
    shutil.copytree(PROBE, PROJECT_DIR, ignore=shutil.ignore_patterns(
        "DerivedDataCache", "Intermediate", "Saved", "__pycache__", ".gameforge"))
    return PROJECT_DIR / "GFProbe.uproject"


def start(uproject: Path, tag: str) -> LiveEditorLink:
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=PROJECT_DIR / f"m11_editor_{tag}.log")
    link.connect(discovery_timeout_s=900)
    return link


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    uproject = make_disposable()

    # 1. Procedural PBR set (provenance procedural), recorded in the disposable project's registry
    reg = AssetRegistry(PROJECT_DIR)
    spec = PBRTextureSpec(name="GFProcRock", size=512, seed=11, base_color=(0.62, 0.30, 0.18), color_variation=0.5)
    manifest = generate_texture_set(spec, TEX_OUT, reg)
    val = validate_texture_set(manifest)
    steps["pbr_manifest"] = {k: v for k, v in manifest.items() if k != "spec"}
    steps["pbr_validation"] = val
    checks["pbr_set_valid"] = val["valid"]

    link = start(uproject, "a")
    try:
        steps["new_level"] = link.call("new_level", {"level_path": f"{ROOT}/Maps/M11Demo"}).get("ok")
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0,
                                  "rotation": {"pitch": -35, "yaw": 160, "roll": 0}, "location": {"x": 0, "y": 0, "z": 600}})
        link.call("spawn_actor", {"actor_class": "SkyLight", "label": "GF_Sky", "location": {"x": 0, "y": 0, "z": 700}})

        # 2. Import with per-role sRGB / compression
        imports = {}
        for role, tex_role in ROLES.items():
            r = link.call("texture_import", {"source_file": manifest["files"][role]["path"], "role": tex_role,
                                             "destination_path": f"{ROOT}/Textures",
                                             "destination_name": f"T_GFProcRock_{role}"}, timeout_s=180)
            imports[role] = (r.get("data") or {}) | {"ok": r.get("ok"), "errors": r.get("errors")}
            if r.get("ok"):
                reg.advance(manifest["registry_ids"][role], "IMPORT", True, "texture_import read-back matched",
                            unreal_path=r["data"]["path"])
        steps["texture_import"] = imports
        checks["textures_imported_with_role_settings"] = all(v["ok"] for v in imports.values())
        checks["basecolor_srgb_normal_ormmasks"] = (imports["BaseColor"].get("srgb") is True
                                                    and imports["Normal"].get("compression") == "TC_NORMALMAP"
                                                    and imports["ORM"].get("compression") == "TC_MASKS"
                                                    and imports["ORM"].get("srgb") is False)

        # 3. Material graph + instance
        built = link.call("material_build_graph", material_graph(), timeout_s=300)
        steps["material_build"] = (built.get("data") or {}) | {"ok": built.get("ok"), "errors": built.get("errors")}
        checks["material_graph_built"] = bool(built.get("ok"))
        inst = link.call("material_instance_create", {"asset_path": MI, "parent": MAT, "scalars": MI_SCALARS,
                                                      "vectors": MI_VECTORS}, timeout_s=120)
        steps["material_instance"] = (inst.get("data") or {}) | {"ok": inst.get("ok"), "errors": inst.get("errors")}
        checks["material_instance_created"] = bool(inst.get("ok"))
        mf = link.call("material_function_build", contrast_function(), timeout_s=120)
        steps["material_function"] = (mf.get("data") or {}) | {"ok": mf.get("ok"), "errors": mf.get("errors")}
        checks["material_function_built"] = bool(mf.get("ok"))
        mfm = link.call("material_build_graph", function_material(), timeout_s=300)
        mfr = link.call("material_readback_graph", {"material_path": MAT_MF}).get("data") or {}
        steps["function_material"] = {"ok": mfm.get("ok"), "errors": mfm.get("errors"),
                                      "statistics": mfr.get("statistics"), "outputs": mfr.get("outputs"),
                                      "calls": [n for n in mfr.get("nodes", [])
                                                if n["class"] == "MaterialExpressionMaterialFunctionCall"]}
        checks["material_calls_function_and_compiles"] = (
            bool(mfm.get("ok")) and any(MF in (n.get("material_function") or "")
                                        for n in steps["function_material"]["calls"])
            and (mfr.get("statistics") or {}).get("pixel_shader_instructions", 0) > 0)
        before = readback(link)
        steps["readback_before_restart"] = before
        mat = before["material"] or {}
        props = {o["property"] for o in mat.get("outputs", [])}
        checks["material_outputs_connected"] = {"MP_BASE_COLOR", "MP_NORMAL", "MP_ROUGHNESS", "MP_AMBIENT_OCCLUSION",
                                                "MP_METALLIC"} <= props
        checks["material_compiled"] = (mat.get("statistics", {}).get("pixel_shader_instructions", 0) > 0
                                       and mat.get("statistics", {}).get("samplers", 0) >= 3)
        checks["material_uses_generated_textures"] = all(any(tex_path(r) in t for t in mat.get("used_textures", []))
                                                         for r in ROLES)
        inst_data = before["instance"] or {}
        checks["instance_overrides_read_back"] = (
            inst_data.get("scalars") == {k: round(v, 4) for k, v in MI_SCALARS.items()}
            and inst_data.get("vectors", {}).get("Tint") == MI_VECTORS["Tint"])

        # 4. Visual proof: same cube with the engine default material, then with the MI
        shots = {}
        for tag, material in (("default", None), ("mi", MI)):
            link.call("delete_actor", {"label": "GF_M11Cube"})
            args = {"actor_class": "StaticMeshActor", "label": "GF_M11Cube", "static_mesh": "/Engine/BasicShapes/Cube.Cube",
                    "location": {"x": 0, "y": 0, "z": 100}, "scale": {"x": 2, "y": 2, "z": 2}}
            if material:
                args["material"] = material
            link.call("spawn_actor", args)
            shots[f"{tag}_materials"] = link.call("actor_get_materials", {"label": "GF_M11Cube"}).get("data")
            link.call("set_viewport_camera", CAMERA)
            time.sleep(8.0)  # let shaders and textures stream in before capturing
            shot = link.capture_screenshot(SHOTS / f"m11_{tag}.png", wait_s=60.0)
            path = (shot.get("data") or {}).get("path")
            shots[tag] = {"path": path, "stats": crop_stats(Path(path)) if path else None, "errors": shot.get("errors")}
        steps["screenshots"] = shots
        slots = (shots.get("mi_materials") or {}).get("slots", [])
        checks["mi_assigned_to_cube"] = any(MI in (s.get("material") or "") for s in slots)
        d, m = (shots["default"].get("stats") or {}), (shots["mi"].get("stats") or {})
        checks["screenshot_shows_textured_warm_material"] = bool(d and m) and (
            m["red_over_blue"] > 1.3 and m["red_over_blue"] > d["red_over_blue"] + 0.2)
        reg.advance(manifest["registry_ids"]["BaseColor"], "ENGINE_VERIFY",
                    checks["screenshot_shows_textured_warm_material"], "m11 demo screenshot pixel statistics",
                    [str(REPORT.relative_to(REPO)).replace("\\", "/")])
        link.call("save_all", {})
    finally:
        rep["editor_exit_code_a"] = link.stop()

    # 5. Restart and compare read-back
    link = start(uproject, "b")
    try:
        after = readback(link)
        steps["readback_after_restart"] = after
        strip = lambda r: json.dumps({k: r[k] for k in ("material", "instance", "textures")}, sort_keys=True)  # noqa: E731
        checks["readback_identical_after_restart"] = after["material_ok"] and strip(after) == strip(before)
    finally:
        rep["editor_exit_code_b"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "project": str(PROJECT_DIR), "checks": {}, "steps": {}}
    try:
        run(rep)
    except Exception as exc:  # keep partial evidence; the failure is part of the record
        rep["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        rep["ok"] = bool(rep["checks"]) and all(rep["checks"].values()) and "exception" not in rep
        REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps(rep["checks"], indent=2), rep.get("exception", ""))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
