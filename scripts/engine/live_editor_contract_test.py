"""Live contract test for the GameForge <-> Unreal Editor link (Master Blueprint v2, WP1).

Launches a real UnrealEditor on a disposable project, drives every in-editor operation
through LiveEditorLink, checks read-back, checks token refusal, stops the editor and
writes a JSON evidence record next to the project.

Usage:
    python scripts/engine/live_editor_contract_test.py <path/to/Probe.uproject> [--nullrhi]
    python scripts/engine/live_editor_contract_test.py --disposable
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402


def image_content(path: Path) -> dict:
    """Prove the capture shows something: share of non-black pixels and luminance spread."""
    from PIL import Image, ImageStat
    img = Image.open(path).convert("L")
    hist = img.histogram()
    total = sum(hist)
    lit = sum(hist[16:]) / total
    stat = ImageStat.Stat(img)
    return {"size": img.size, "lit_fraction": round(lit, 4), "mean": round(stat.mean[0], 2),
            "stddev": round(stat.stddev[0], 2), "has_content": lit > 0.05 and stat.stddev[0] > 5}


def steps_for(project_dir: Path):
    shot = (project_dir / "Saved" / "GameForge" / "viewport.png").as_posix()
    return [
        ("handshake", {}, lambda r: r["data"]["engine_version"].startswith("5.7")),
        ("new_level", {"level_path": "/Game/Maps/GF_Probe"}, lambda r: r["data"]["exists"]),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Cube",
                         "location": {"x": 100, "y": 0, "z": 50},
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube"},
         lambda r: r["data"]["label"] == "GF_Cube" and abs(r["data"]["location"]["x"] - 100) < 0.01),
        ("actors_in_level", {"limit": 200},
         lambda r: any(a["label"] == "GF_Cube" for a in r["data"]["actors"])),
        ("create_material", {"asset_path": "/Game/GF/M_ProbeRed", "base_color": [1, 0, 0], "roughness": 0.4},
         lambda r: r["data"]["exists"] and r["data"]["expressions"] >= 2),
        ("asset_exists", {"asset_path": "/Game/GF/M_ProbeRed", "asset_class": "Material"},
         lambda r: r["data"]["exists"] and r["data"]["class_match"]),
        ("create_blueprint", {"asset_path": "/Game/GF/BP_ProbeActor", "parent_class": "Actor"},
         lambda r: r["data"]["exists"]),
        ("compile_blueprint", {"blueprint_path": "/Game/GF/BP_ProbeActor"}, lambda r: True),
        ("list_assets", {"directory": "/Game/GF"}, lambda r: r["data"]["count"] >= 2),
        ("save_all", {}, lambda r: r["data"]["level_saved"]),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Floor", "location": {"x": 0, "y": 0, "z": 0},
                         "static_mesh": "/Engine/BasicShapes/Plane.Plane", "scale": {"x": 10, "y": 10, "z": 1}},
         lambda r: r["data"]["label"] == "GF_Floor"),
        ("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun",
                         "rotation": {"pitch": -40, "yaw": 30, "roll": 0}},
         lambda r: r["data"]["label"] == "GF_Sun"),
        ("set_viewport_camera", {"location": {"x": -400, "y": -300, "z": 300},
                                 "rotation": {"pitch": -23, "yaw": 31, "roll": 0}},
         lambda r: abs(r["data"]["location"]["x"] + 400) < 1),
        ("viewport_screenshot", {"output_path": shot, "resolution": [1280, 720]},
         lambda r: r["data"].get("bytes", 0) > 0),
        ("delete_actor", {"label": "GF_Cube"}, lambda r: r["data"]["deleted"]),
        ("log_tail", {"max_lines": 20}, lambda r: isinstance(r["data"]["lines"], list)),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("uproject", nargs="?", help="omit with --disposable")
    ap.add_argument("--disposable", action="store_true",
                    help="copy the host-profile probe (with the host-profile plugin build) to a fresh folder")
    ap.add_argument("--nullrhi", action="store_true", help="known to crash spawn_actor on 5.7.4")
    ap.add_argument("--discovery-timeout", type=float, default=900)
    a = ap.parse_args()
    if a.disposable:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _harness import disposable_probe
        a.uproject = str(disposable_probe("contract"))
    elif not a.uproject:
        ap.error("give a uproject path or --disposable")

    link = LiveEditorLink(Path(a.uproject))
    project_dir = link.project_dir
    record = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "uproject": str(link.uproject), "steps": []}
    record["prepare"] = link.prepare_project()
    render = ["-nullrhi"] if a.nullrhi else ["-RenderOffscreen", "-ResX=1280", "-ResY=720"]
    record["launch_args"] = render
    t0 = time.monotonic()
    record["pid"] = link.launch(render, log_path=project_dir / "Saved" / "GameForge" / "editor.log")
    print("launched", record["pid"], render, flush=True)
    passed = 0
    try:
        record["node"] = link.connect(discovery_timeout_s=a.discovery_timeout)
        record["discovery_s"] = round(time.monotonic() - t0, 1)
        print("connected after", record["discovery_s"], "s", flush=True)
        for name, args, check in steps_for(project_dir):
            if name == "viewport_screenshot":
                r = link.capture_screenshot(Path(args["output_path"]), args["resolution"])
            else:
                r = link.call(name, args, timeout_s=300)
            try:
                verdict = bool(r.get("ok")) and bool(check(r))
            except Exception as exc:  # malformed data counts as failure
                verdict, r["check_error"] = False, repr(exc)
            r["contract_pass"] = verdict
            passed += verdict
            record["steps"].append(r)
            print(("PASS " if verdict else "FAIL ") + name, json.dumps(r, default=str)[:400], flush=True)
            if any(e in ("EDITOR_CRASHED", "EDITOR_LINK_LOST") for e in r.get("errors", [])):
                break
        if link.call("handshake").get("ok"):
            real = link._token
            link._token = "0" * 64
            refused = link.call("actors_in_level", {})
            link._token = real
            record["wrong_token_refused"] = (not refused.get("ok")) and any(
                "unauthorized" in e for e in refused.get("errors", []))
            print("wrong token refused:", record["wrong_token_refused"], flush=True)
        shot = project_dir / "Saved" / "GameForge" / "viewport.png"
        for _ in range(20):
            if shot.exists():
                break
            time.sleep(1)
        record["screenshot_exists"] = shot.exists()
        if shot.exists():
            time.sleep(1)
            record["screenshot_content"] = image_content(shot)
            print("screenshot content:", record["screenshot_content"], flush=True)
    except Exception as exc:
        record["fatal"] = f"{type(exc).__name__}: {exc}"
        print("FATAL", record["fatal"], flush=True)
    finally:
        record["editor_exit_code"] = link.stop()
        record["graceful_stop"] = link.last_stop_graceful
        record["passed"] = passed
        record["total"] = len(steps_for(project_dir))
        record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        out = project_dir / "Saved" / "GameForge" / "contract_result.json"
        out.write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
        print(f"result {passed}/{record['total']} -> {out}", flush=True)
    ok = passed == record["total"] and record.get("screenshot_content", {}).get("has_content")         and record.get("graceful_stop")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
