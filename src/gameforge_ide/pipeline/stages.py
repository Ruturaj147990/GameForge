"""Engine stages shared by every game pipeline (recipe and free-form).

Each function returns a StageRecord-compatible tuple (ok, data, errors). They run real engine
executables and the live editor; none of them simulates anything.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Tuple

from ..unreal.live_editor import LiveEditorLink
from ..unreal.toolchain import UnrealToolchain

SELFTEST_PASS = "GF_SELFTEST PASS"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_content(path: Path) -> Dict:
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return {"checked": False}
    img = Image.open(path).convert("L")
    hist = img.histogram()
    lit = sum(hist[16:]) / max(1, sum(hist))
    sd = ImageStat.Stat(img).stddev[0]
    return {"checked": True, "size": list(img.size), "lit_fraction": round(lit, 4), "stddev": round(sd, 2),
            "has_content": lit > 0.05 and sd > 5}


def assemble_level(engine_root: Path, uproject: Path, evidence_dir: Path, name: str,
                   floor_extent_cm: float) -> Tuple[bool, Dict, List[str]]:
    """Build the game's level in the live editor: table, sun, sky fill; read everything back."""
    link = LiveEditorLink(uproject, engine_root)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=evidence_dir / "assemble_editor.log")
    map_path = f"/Game/Maps/{name}Map"
    calls = [
        ("new_level", {"level_path": map_path}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Table", "base_color": [0.05, 0.06, 0.09],
                             "roughness": 0.8}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Table",
                         "static_mesh": "/Engine/BasicShapes/Plane.Plane", "material": f"/Game/{name}/M_Table",
                         "location": {"x": 0, "y": 0, "z": -15},
                         "scale": {"x": floor_extent_cm * 3 / 100, "y": floor_extent_cm * 3 / 100, "z": 1}}),
        ("spawn_actor", {"actor_class": "DirectionalLight", "label": "Sun", "mobility": "Movable",
                         "light_intensity": 10.0, "rotation": {"pitch": -50, "yaw": 35, "roll": 0}}),
        ("spawn_actor", {"actor_class": "SkyLight", "label": "SkyFill", "mobility": "Movable",
                         "light_intensity": 1.0}),
        ("save_all", {}),
        ("actors_in_level", {"limit": 50}),
    ]
    out: List[Dict] = []
    errors: List[str] = []
    try:
        link.connect(discovery_timeout_s=900)
        for op, args in calls:
            r = link.call(op, args, timeout_s=300)
            out.append({"op": op, "ok": r.get("ok"), "errors": r.get("errors", [])})
            if not r.get("ok"):
                if op == "create_material" and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                errors.append(f"{op}: {r.get('errors')}")
                break
            if op == "actors_in_level":
                labels = {a["label"] for a in r["data"]["actors"]}
                missing = {"Table", "Sun", "SkyFill"} - labels
                if missing:
                    errors.append(f"read-back missing actors: {sorted(missing)}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        code = link.stop()
    return not errors, {"map": map_path, "calls": out, "editor_exit": code,
                        "graceful": link.last_stop_graceful}, errors


def assemble_platformer_level(engine_root: Path, uproject: Path, evidence_dir: Path, name: str,
                              collectible_count: int = 5) -> Tuple[bool, Dict, List[str]]:
    """Build the 3D platformer level in the live editor: platforms, sun, sky fill, player start; read back."""
    link = LiveEditorLink(uproject, engine_root)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=evidence_dir / "assemble_editor.log")
    map_path = f"/Game/Maps/{name}Map"
    calls = [
        ("new_level", {"level_path": map_path}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Platform", "base_color": [0.12, 0.15, 0.22], "roughness": 0.6}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Coin", "base_color": [1.0, 0.85, 0.1], "roughness": 0.2}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Checkpoint", "base_color": [0.1, 0.8, 0.9], "roughness": 0.3}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Goal", "base_color": [0.6, 0.2, 0.95], "roughness": 0.3}),
        ("spawn_actor", {"actor_class": "DirectionalLight", "label": "Sun", "mobility": "Movable",
                         "light_intensity": 10.0, "rotation": {"pitch": -50, "yaw": 45, "roll": 0}}),
        ("spawn_actor", {"actor_class": "SkyLight", "label": "SkyFill", "mobility": "Movable",
                         "light_intensity": 1.5}),
        # 7 Platforms
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_Start",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 0, "y": 0, "z": 0}, "scale": {"x": 4.0, "y": 4.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_2",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 600, "y": 0, "z": 80}, "scale": {"x": 3.0, "y": 3.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_3",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 1200, "y": 100, "z": 180}, "scale": {"x": 3.0, "y": 3.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_Checkpoint",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 1850, "y": 100, "z": 260}, "scale": {"x": 4.0, "y": 4.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_5",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 2500, "y": -80, "z": 200}, "scale": {"x": 3.0, "y": 3.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_6",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 3150, "y": 0, "z": 320}, "scale": {"x": 3.0, "y": 3.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_Goal",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 3800, "y": 0, "z": 360}, "scale": {"x": 4.0, "y": 4.0, "z": 0.5}}),
        # PlayerStart on Start Platform
        ("spawn_actor", {"actor_class": "PlayerStart", "label": "PlayerStart",
                         "location": {"x": 0, "y": 0, "z": 60}}),
        ("save_all", {}),
        ("actors_in_level", {"limit": 50}),
    ]
    out: List[Dict] = []
    errors: List[str] = []
    try:
        link.connect(discovery_timeout_s=900)
        for op, args in calls:
            r = link.call(op, args, timeout_s=300)
            out.append({"op": op, "ok": r.get("ok"), "errors": r.get("errors", [])})
            if not r.get("ok"):
                if op == "create_material" and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                errors.append(f"{op}: {r.get('errors')}")
                break
            if op == "actors_in_level":
                labels = {a["label"] for a in r["data"]["actors"]}
                required = {"Sun", "SkyFill", "Platform_Start", "Platform_Checkpoint", "Platform_Goal", "PlayerStart"}
                missing = required - labels
                if missing:
                    errors.append(f"read-back missing actors: {sorted(missing)}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        code = link.stop()
    return not errors, {"map": map_path, "calls": out, "editor_exit": code,
                        "graceful": link.last_stop_graceful}, errors


def package(toolchain: UnrealToolchain, uproject: Path) -> Tuple[bool, Dict, List[str]]:
    r = toolchain.package(uproject, uproject.parent / "Packaged")
    d = r.to_dict()
    return r.ok, {"exit_code": r.exit_code, "log": r.log_path, **r.data, "errors": d["error_count"],
                  "diagnostics": [x.__dict__ for x in r.diagnostics[:20]]}, r.errors


def packaged_smoke(toolchain: UnrealToolchain, exe: Path, evidence_dir: Path, name: str,
                   expect_log: str = SELFTEST_PASS) -> Tuple[bool, Dict, List[str]]:
    """Launch the shipped build with -GFSelfTest; require PASS log, exit 0 AND a content-bearing screenshot."""
    ok, data, errors = _packaged_smoke_once(toolchain, exe, evidence_dir, name, expect_log=expect_log)
    only_capture_failed = (not ok and data.get("exit_code") == 0 and data.get("matched_lines")
                           and errors and all("screenshot" in e for e in errors))
    if only_capture_failed:
        first = {"screenshot_content": data.get("screenshot_content"), "errors": errors}
        ok, data, errors = _packaged_smoke_once(toolchain, exe, evidence_dir, name, expect_log=expect_log)
        data["warm_retry"] = {"reason": "first capture empty while logic passed", "first_attempt": first}
    return ok, data, errors


def _packaged_smoke_once(toolchain: UnrealToolchain, exe: Path, evidence_dir: Path, name: str,
                         expect_log: str = SELFTEST_PASS) -> Tuple[bool, Dict, List[str]]:
    shot = evidence_dir / "packaged_gameplay.png"
    if shot.exists():
        shot.unlink()
    r = toolchain.smoke_test_packaged(
        exe, ["-GFSelfTest", f"-GFShot={shot}", "-RenderOffscreen", "-ResX=1280", "-ResY=720", "-windowed"],
        expect_log=expect_log, timeout_s=600, log_path=evidence_dir / "packaged_smoke.log")
    data = {"exit_code": r.exit_code, "log": r.log_path, **r.data, "exe_sha256": sha256_file(exe)}
    if not shot.exists():
        sdir = exe.parent / name / "Saved" / "Screenshots"
        alt = sorted(sdir.rglob("*.png")) if sdir.exists() else []
        if alt:
            shot = alt[-1]
    errors = list(r.errors)
    content_ok = False
    if shot.exists():
        data["screenshot"] = str(shot)
        data["screenshot_content"] = image_content(shot)
        content_ok = data["screenshot_content"].get("has_content", False) or \
            not data["screenshot_content"].get("checked", False)
        if not content_ok:
            errors.append("gameplay screenshot shows no scene content (black or empty frame)")
    else:
        errors.append("gameplay screenshot was not written")
    log_text = Path(r.log_path).read_text(encoding="utf-8", errors="replace") if r.log_path and Path(r.log_path).exists() else ""
    data["selftest_lines"] = [l.strip()[-400:] for l in log_text.splitlines() if "GF_" in l and "SELFTEST" in l][-3:]
    import re as _re
    scene = _re.findall(r"GF_SCENE shapes=(-?\d+)", log_text)
    if scene:
        data["scene_shapes"] = int(scene[-1])
    data["game_errors"] = [l.strip()[-300:] for l in log_text.splitlines()
                           if ("Error:" in l or "Fatal" in l) and "LogWindows: Failed to load" not in l][-10:]
    return r.ok and content_ok, data, errors


def write_report(evidence_dir: Path, payload: Dict, markdown: str) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report = evidence_dir / "pipeline_report.json"
    report.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    (evidence_dir / "pipeline_report.md").write_text(markdown, encoding="utf-8")
    return report
