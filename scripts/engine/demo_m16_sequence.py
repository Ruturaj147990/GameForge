"""Roadmap M16 acceptance on a disposable probe copy: a 3-shot LevelSequence rendered to frames.

Scene: red / green / blue cubes, one CineCamera shot per cube (camera-cut track), a sphere keyed from x=-200 to
x=+200, and the M14 pickup sound on an audio track. Checks: read-back of cuts, keys and audio; editor scrubbing
moves the sphere as keyed; Movie Render Queue writes a PNG per frame; the frame-to-frame pixel difference spikes
exactly at the cut frames and each shot is dominated by its cube's colour.

Evidence: reports/m16_sequence_demo.json. Usage: python scripts/engine/demo_m16_sequence.py
"""

from __future__ import annotations

import glob
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts" / "engine"))

import demo_m11_landscape as land  # noqa: E402
from src.gameforge_ide.backend.tools.sfx_synth import SFXSpec, generate_sfx  # noqa: E402

REPORT = REPO / "reports" / "m16_sequence_demo.json"
SEQ = "/Game/M16/Cinematics/LS_GFThreeShots"
MAP = "/Game/M16/Maps/Cinematic"
FPS, END = 24, 72
CUTS = (24, 48)
# CineCamera defaults (f/2.8, 1/60 s, ISO 100) meter about EV100 8.9; a 20,000 lux sun is about EV100 13,
# so the lit pass needs roughly -4 EV of compensation.
EXPOSURE_BIAS = -4.0
TARGETS = [("Red", (1.0, 0.05, 0.05), {"x": 0, "y": -600, "z": 100}),
           ("Green", (0.05, 1.0, 0.05), {"x": 0, "y": 0, "z": 100}),
           ("Blue", (0.05, 0.05, 1.0), {"x": 0, "y": 600, "z": 100})]


def frame_stats(paths: list[str]) -> dict:
    from PIL import Image
    imgs = [np.asarray(Image.open(p).convert("RGB")).astype(np.float64) for p in paths]
    diffs = [float(np.abs(a - b).mean()) for a, b in zip(imgs, imgs[1:])]
    dominant = []
    for img in imgs:
        mean = img.reshape(-1, 3).mean(axis=0)
        dominant.append("RGB"[int(np.argmax(mean))])
    return {"diffs": [round(d, 2) for d in diffs], "dominant": "".join(dominant),
            "first_mean": [round(float(c), 2) for c in imgs[0].reshape(-1, 3).mean(axis=0)]}


def run(rep: dict) -> None:
    checks, steps = rep["checks"], rep["steps"]
    land.PROJECT_DIR = Path(str(land.PROJECT_DIR).replace("m11_landscape_", "m16_sequence_"))
    rep["project"] = str(land.PROJECT_DIR)
    uproject = land.make_disposable()
    data = json.loads(uproject.read_text(encoding="utf-8"))
    if not any(p.get("Name") == "MovieRenderPipeline" for p in data["Plugins"]):
        data["Plugins"].append({"Name": "MovieRenderPipeline", "Enabled": True})
        uproject.write_text(json.dumps(data, indent="\t"), encoding="utf-8")
    chime = generate_sfx(SFXSpec(name="Pickup", kind="pickup", seed=4), land.PROJECT_DIR / "SourceAudio")
    out_dir = land.PROJECT_DIR / "Saved" / "MovieRenders" / "LS_GFThreeShots"
    # Run 1 with -RenderOffscreen rendered all-black MRQ frames; the PIE executor needs a real window.
    from src.gameforge_ide.unreal.live_editor import LiveEditorLink
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-ResX=1280", "-ResY=720"], log_path=land.PROJECT_DIR / "seq_editor.log")
    link.connect(discovery_timeout_s=900)
    try:
        link.call("new_level", {"level_path": MAP})
        # Run 6: Unlit frames were correct while Lit stayed RGB 0: Static/Stationary lights with unbuilt lighting
        # contribute nothing in the MRQ -game process, so the lights must be Movable. Run 7: still black; the sun
        # (yaw 160) shone toward -X and lit only the cube faces facing away from the cameras (x=-450, looking +X),
        # and with no sky atmosphere the SkyLight adds no ambient, so the visible faces were exactly 0. Yaw 20
        # shines toward +X onto the faces the cameras see.
        # Runs 2-3 (4 lux sun + manual exposure volume) rendered all-zero MRQ frames through the CineCameras, whose
        # physical-camera exposure (~EV 8.9) needs a daylight-level sun.
        link.call("spawn_actor", {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 20000.0, "mobility": "Movable",
                                  "rotation": {"pitch": -40, "yaw": 20, "roll": 0}, "location": {"x": 0, "y": 0, "z": 800}})
        link.call("spawn_actor", {"actor_class": "SkyLight", "label": "GF_Sky", "mobility": "Movable", "location": {"x": 0, "y": 0, "z": 900}})
        for name, colour, loc in TARGETS:
            link.call("create_material", {"asset_path": f"/Game/M16/Materials/M_{name}", "base_color": list(colour),
                                          "roughness": 0.6})
            link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": f"GF_{name}Cube",
                                      "static_mesh": "/Engine/BasicShapes/Cube.Cube", "location": loc,
                                      "scale": {"x": 2.5, "y": 2.5, "z": 2.5}, "material": f"/Game/M16/Materials/M_{name}"})
        link.call("spawn_actor", {"actor_class": "StaticMeshActor", "label": "GF_Mover",
                                  "static_mesh": "/Engine/BasicShapes/Sphere.Sphere", "location": {"x": -200, "y": 0, "z": 400}})
        link.call("audio_import", {"source_file": chime["path"], "destination_path": "/Game/M16/Audio",
                                   "destination_name": "SFX_Pickup"})
        shots = [{"camera_label": f"GF_Cam{name}", "start": i * 24, "end": (i + 1) * 24,
                  "location": {"x": -1400, "y": loc["y"], "z": 300}, "rotation": {"pitch": -6, "yaw": 0, "roll": 0}}
                 for i, (name, _, loc) in enumerate(TARGETS)]
        built = link.call("sequence_build", {
            "asset_path": SEQ, "fps": FPS, "end_frame": END, "shots": shots,
            "bindings": [{"actor_label": "GF_Mover", "keys": [{"frame": 0, "location": {"x": -200, "y": 0, "z": 400}},
                                                             {"frame": END, "location": {"x": 200, "y": 0, "z": 400}}]}],
            "audio": [{"sound_path": "/Game/M16/Audio/SFX_Pickup", "start": 24}]}, timeout_s=180)
        steps["build"] = {"ok": built.get("ok"), "errors": built.get("errors")}
        insp = link.call("sequence_inspect", {"sequence_path": SEQ}).get("data") or {}
        steps["inspect"] = insp
        checks["sequence_built"] = bool(built.get("ok"))
        checks["three_camera_cuts"] = [c["range"] for c in insp.get("camera_cuts", [])] == [[0, 24], [24, 48], [48, 72]]
        checks["transform_keys_read_back"] = any(t["type"] == "MovieScene3DTransformTrack" and t["keys"] >= 6
                                                 for b in insp.get("bindings", []) for t in b["tracks"])
        checks["audio_in_sequence"] = any("SFX_Pickup" in (a.get("sound") or "") for a in insp.get("audio", []))
        ev = link.call("sequence_evaluate", {"sequence_path": SEQ, "frames": [0, 36, 71], "actor_labels": ["GF_Mover"]})
        samples = (ev.get("data") or {}).get("samples", [])
        steps["evaluate"] = samples
        xs = [s.get("GF_Mover", [None])[0] for s in samples]
        checks["scrubbing_moves_actor_as_keyed"] = len(xs) == 3 and None not in xs and \
            abs(xs[0] + 200) < 1 and abs(xs[1]) < 25 and xs[2] > 180  # frame 72 = exclusive end, evaluates as start
        # Runs 2-5 rendered pure-black lit frames (RGB 0, every frame identical). Run 6 renders an Unlit pass
        # (base colour, independent of lighting and exposure) next to a Lit pass with manual exposure, so the
        # report separates "nothing visible to the camera" from "lighting/exposure".
        link.call("scene_set_manual_exposure", {"exposure_bias": float(EXPOSURE_BIAS)})
        link.call("save_all", {})
        steps["variants"] = {}
        for variant in ("unlit", "lit"):
            vdir = out_dir / variant
            r = link.call("sequence_render", {"sequence_path": SEQ, "map_path": MAP, "output_dir": str(vdir),
                                              "resolution": [640, 360], "render_pass": variant, "warmup_frames": 32,
                                              "executor": "MoviePipelineNewProcessExecutor"}, timeout_s=120)
            deadline, files = time.time() + 600, []
            while time.time() < deadline:
                time.sleep(5.0)
                files = sorted(glob.glob(str(vdir / "*.png")))
                status = link.call("sequence_render_status", {}).get("data") or {}
                if len(files) >= END and not status.get("rendering"):
                    break
            v = {"render_request": {"ok": r.get("ok"), "errors": r.get("errors")}, "rendered_frames": len(files)}
            if len(files) >= END:
                st = frame_stats(files[:END])
                top = sorted(range(len(st["diffs"])), key=lambda i: st["diffs"][i], reverse=True)[:2]
                v.update(frame_stats=st, largest_diffs_after_frame=sorted(i + 1 for i in top),
                         cuts_ok=sorted(i + 1 for i in top) == list(CUTS),
                         colours_ok=(st["dominant"][:24].count("R") > 20 and st["dominant"][24:48].count("G") > 20
                                     and st["dominant"][48:72].count("B") > 20),
                         mean_rgb_first_frame=st["first_mean"])
            steps["variants"][variant] = v
        lit = steps["variants"]["lit"]
        checks["frames_rendered"] = lit["rendered_frames"] >= END
        # Acceptance is on the Lit render; Unlit is diagnostic only.
        checks["cuts_detected_at_24_and_48"] = bool(lit.get("cuts_ok"))
        checks["shots_show_expected_colours"] = bool(lit.get("colours_ok"))
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
