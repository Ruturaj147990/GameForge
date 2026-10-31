"""Roadmap M11 step 5: landscape layered material + paint layers, on a disposable probe copy.

A LandscapeLayerBlend material (Grass / Rock / Snow, weight-blended) is built with `material_build_graph`; the
landscape is created with three paint layers whose weightmaps come from height and slope
(`GameForgeLandscapeLibrary.CreateLandscape` "paint_layers"); the engine's own weightmaps are read back
(`landscape_inspect_layers`), the result is captured and its pixels classified, and the read-back must survive
an editor restart.

Requires the plugin build that contains `InspectLandscapeLayers` (PLUGIN_BUILD below).
Evidence: reports/m11_landscape_demo.json. Usage: python scripts/demo_m11_landscape.py
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

from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

PROBE = Path(r"E:\GameForge\validation\live_ops_probe")
PLUGIN_BUILD = Path(r"E:\GameForge\validation\GameForgePlugin_m15b")
DATE = time.strftime("%Y%m%d")
PROJECT_DIR = Path(rf"E:\GameForge\validation\m11_landscape_{DATE}")
REPORT = REPO / "reports" / "m11_landscape_demo.json"
MAT = "/Game/M11/Landscape/M_GFLandscapeLayers"
LAYERS = [("Grass", "low", [0.10, 0.32, 0.06]), ("Rock", "steep", [0.22, 0.21, 0.20]), ("Snow", "high", [0.85, 0.87, 0.9])]


def landscape_material(input_style: str) -> dict:
    nodes = [{"id": "blend", "class": "MaterialExpressionLandscapeLayerBlend", "x": -400, "y": 0,
              "props": {"layers": [{"name": n} for n, _, _ in LAYERS]}},
             {"id": "rough", "class": "MaterialExpressionConstant", "x": -400, "y": 300, "props": {"r": 0.85}}]
    edges = []
    for i, (name, _, color) in enumerate(LAYERS):
        nodes.append({"id": name, "class": "MaterialExpressionConstant3Vector", "x": -800, "y": i * 150,
                      "props": {"constant": color}})
        edges.append({"from": name, "to": "blend", "input": input_style.format(name=name)})
    return {"asset_path": MAT, "replace_existing": True, "nodes": nodes, "edges": edges,
            "outputs": [{"from": "blend", "property": "MP_BASE_COLOR"}, {"from": "rough", "property": "MP_ROUGHNESS"}]}


def classify(path: Path) -> dict:
    from PIL import Image
    img = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    lum = img.mean(axis=2)
    lit = lum > 25
    lit_mean = float(lum[lit].mean()) if lit.any() else 0.0
    green = lit & (g > r * 1.25) & (g > b * 1.25)
    snow = lit & (lum > 170) & (np.abs(r - b) < 30)
    grey = lit & ~green & ~snow & (np.abs(r - g) < 18) & (np.abs(g - b) < 18)
    n = float(lit.sum()) or 1.0
    return {"lit_fraction": round(float(lit.mean()), 3), "lit_mean_lum": round(lit_mean, 1), "green_of_lit": round(float(green.sum()) / n, 3),
            "grey_of_lit": round(float(grey.sum()) / n, 3), "snow_of_lit": round(float(snow.sum()) / n, 3)}


def make_disposable() -> Path:
    if PROJECT_DIR.exists():
        shutil.rmtree(PROJECT_DIR)
    shutil.copytree(PROBE, PROJECT_DIR, ignore=shutil.ignore_patterns(
        "DerivedDataCache", "Intermediate", "Saved", "__pycache__", ".gameforge"))
    dest = PROJECT_DIR / "Plugins" / "GameForge" / "Binaries"
    shutil.rmtree(dest)
    shutil.copytree(PLUGIN_BUILD / "Binaries", dest)
    return PROJECT_DIR / "GFProbe.uproject"


def start(uproject: Path, tag: str) -> LiveEditorLink:
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=PROJECT_DIR / f"landscape_editor_{tag}.log")
    link.connect(discovery_timeout_s=900)
    return link


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    uproject = make_disposable()
    link = start(uproject, "a")
    try:
        link.call("new_level", {"level_path": "/Game/M11/Maps/LandscapeLayers"})
        built = None
        for style in ("Layer {name}", "{name}"):
            built = link.call("material_build_graph", landscape_material(style), timeout_s=300)
            steps.setdefault("material_attempts", []).append({"input_style": style, "ok": built.get("ok"),
                                                              "errors": built.get("errors")})
            if built.get("ok"):
                break
        checks["layer_blend_material_built"] = bool(built and built.get("ok"))
        rb = link.call("material_readback_graph", {"material_path": MAT})
        steps["material_readback"] = rb.get("data")

        land = link.call("landscape_create", {"terrain_type": "Mountains", "elevation_scale": 4000, "seed": 7,
                                              "high_start": 0.86, "steep_start_cm_per_quad": 40,
                                              "material_path": MAT, "layer_info_path": "/Game/M11/Landscape/LayerInfo",
                                              "paint_layers": [{"name": n, "rule": rule} for n, rule, _ in LAYERS]},
                         timeout_s=600)
        steps["landscape_create"] = (land.get("data") or {}) | {"ok": land.get("ok"), "errors": land.get("errors"),
                                                               "warnings": land.get("warnings")}
        checks["landscape_created_with_layers"] = bool(land.get("ok")) and \
            (land.get("data") or {}).get("paint_layers") == [n for n, _, _ in LAYERS]
        # Weightmaps are resolved by the edit-layer merge on a later editor tick: poll until they appear.
        for attempt in range(30):
            before = link.call("landscape_inspect_layers", {})
            bd = before.get("data") or {}
            if sum(l.get("mean_weight", 0) for l in bd.get("layers", [])) > 200:
                break
            time.sleep(2.0)
        steps["weight_merge_polls"] = attempt + 1
        steps["layers_before_restart"] = bd | {"ok": before.get("ok"), "errors": before.get("errors")}
        layers = {l["name"]: l for l in bd.get("layers", [])}
        checks["all_layers_have_layer_info"] = all(layers.get(n, {}).get("layer_info") for n, _, _ in LAYERS)
        checks["weights_sum_to_full"] = abs(sum(l.get("mean_weight", 0) for l in layers.values()) - 255) < 3
        checks["every_layer_dominates_somewhere"] = all(layers.get(n, {}).get("dominant_fraction", 0) > 0.01
                                                        for n, _, _ in LAYERS)

        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 4.0,
                                  "rotation": {"pitch": -40, "yaw": 30, "roll": 0}, "location": {"x": 0, "y": 0, "z": 9000}})
        link.call("set_viewport_camera", {"location": {"x": -11000, "y": -2500, "z": 7000},
                                          "rotation": {"pitch": -28, "yaw": 12, "roll": 0}})
        # Exposure bracket: manual exposure (no eye adaptation), keep the frame whose lit mid-tones are best.
        brackets = []
        for bias in (6.0, 8.0, 10.0, 12.0):
            exp = link.call("scene_set_manual_exposure", {"exposure_bias": bias})
            time.sleep(6.0)
            shot = link.capture_screenshot(PROJECT_DIR / "Saved" / "Screenshots" / f"m11_landscape_ev{int(bias)}.png",
                                           wait_s=90.0)
            path = (shot.get("data") or {}).get("path")
            stats = classify(Path(path)) if path else None
            brackets.append({"bias": bias, "exposure_ok": exp.get("ok"), "path": path, "stats": stats,
                             "errors": shot.get("errors")})
        steps["exposure_brackets"] = brackets
        usable = [b for b in brackets if b["stats"] and b["stats"]["lit_fraction"] > 0.1]
        best = min(usable, key=lambda b: abs(b["stats"]["lit_mean_lum"] - 115.0)) if usable else None
        stats = best["stats"] if best else None
        steps["screenshot"] = best
        checks["screenshot_shows_grass_rock_snow"] = bool(stats) and stats["green_of_lit"] > 0.05 and \
            stats["grey_of_lit"] > 0.02 and stats["snow_of_lit"] > 0.01
        link.call("save_all", {})
    finally:
        rep["editor_exit_code_a"] = link.stop()

    link = start(uproject, "b")
    try:
        link.call("load_level", {"level_path": "/Game/M11/Maps/LandscapeLayers"})
        after = link.call("landscape_inspect_layers", {})
        steps["layers_after_restart"] = (after.get("data") or {}) | {"ok": after.get("ok"), "errors": after.get("errors")}
        key = lambda d: json.dumps(sorted(((l["name"], l.get("layer_info"), round(l.get("mean_weight", 0), 2))  # noqa: E731
                                           for l in (d or {}).get("layers", []))))
        checks["layers_identical_after_restart"] = bool(after.get("ok")) and key(after.get("data")) == key(bd)
    finally:
        rep["editor_exit_code_b"] = link.stop()


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "project": str(PROJECT_DIR), "checks": {}, "steps": {}}
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
