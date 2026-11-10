"""Audit 2026-10-30: import the GENERATED character (not an engine sample) into real UE 5.7.4.

The Milestone 9 script imported Engine/Content/FbxEditorAutomation/AnimatedCharacter.fbx and
reported it as the generated character. This check generates the procedural humanoid, exports
glTF, imports that file through Interchange, and compares Unreal's read-back of the skeleton and
bounds with what the generator produced. Evidence: reports/audit_m9_generated_character.json.

    python scripts/engine/audit_verify_generated_character.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.backend.models.animation_spec import LocomotionSetSpec  # noqa: E402
from src.gameforge_ide.backend.models.character_spec import CharacterSpec  # noqa: E402
from src.gameforge_ide.backend.tools.motion_generator import ProceduralKinematicMotionSynthesizer  # noqa: E402
from src.gameforge_ide.backend.tools.character_generator import ProceduralSkinnedCharacterGenerator  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

DEST = "/Game/Audit/GeneratedCharacter"
REPORT = ROOT / "reports" / "audit_m9_generated_character.json"
ANIM_REPORT = ROOT / "reports" / "audit_m10_generated_motion.json"
ANIM_DEST = "/Game/Audit/GeneratedMotion"


def _resolve_paths() -> Tuple[Path, Path, Path, Path]:
    s = get_settings()
    uproject = s.require_dev("validation_root") / "live_ops_probe" / "GFProbe.uproject"
    out_dir = s.data_root / "assets" / "generated" / "characters" / "audit_20261030"
    anim_dir = s.data_root / "assets" / "generated" / "animations" / "audit_20261030"
    shot = uproject.parent / "Saved" / "Screenshots" / "audit_m9_generated_character.png"
    return uproject, out_dir, anim_dir, shot


def _data(resp: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(resp, dict):
        return {}
    d = resp.get("data")
    return d if isinstance(d, dict) else {}


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()


def _quat_close(a: Sequence[float], b: Sequence[float], tol: float = 1e-3) -> bool:
    if len(a) != 4 or len(b) != 4:
        return False
    dot = abs(sum(float(x) * float(y) for x, y in zip(a, b)))  # q and -q are the same rotation
    return dot > 1.0 - tol


def verify_motion(link: LiveEditorLink, skeleton_path: str, anim_dir: Optional[Path] = None) -> bool:
    """M10: synthesized clips -> real UAnimSequences on the generated skeleton; engine-evaluated
    bone rotations must equal the synthesized keys (bind rotations are identity for this rig)."""
    if anim_dir is None:
        anim_dir = get_settings().data_root / "assets" / "generated" / "animations" / "audit_20261030"
    loco = LocomotionSetSpec.create_standard_humanoid_locomotion(
        character_id="char_adventurer_hero_01", target_skeleton_path=skeleton_path, destination_path=ANIM_DEST)
    synth = ProceduralKinematicMotionSynthesizer(output_dir=anim_dir)
    rep: Dict[str, Any] = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "skeleton": skeleton_path, "clips": [], "ok": False}
    link.call("delete_asset", {"asset_path": ANIM_DEST})
    for clip in loco.clips:
        bundle = synth.synthesize_clip(clip)
        path = synth.export_motion_json(bundle)
        res = link.call("anim_import_motion_clip", {"skeleton_path": skeleton_path, "motion_json_path": str(path),
                                                    "destination_path": ANIM_DEST, "destination_name": clip.name}, timeout_s=120) or {}
        res_data = _data(res)
        entry: Dict[str, Any] = {"clip": clip.name, "import": res}
        if res.get("ok") and res_data.get("anim_sequence_path"):
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            frames = int(data["total_frames"])
            probe_frames = sorted({0, frames // 3, (2 * frames) // 3})
            bones = ["pelvis", "thigh_l", "calf_r", "upperarm_l"]
            times = [f / float(data["sample_rate_hz"]) for f in probe_frames]
            sample = link.call("anim_sample_bone_pose", {"anim_sequence_path": res_data["anim_sequence_path"],
                                                         "bones": bones, "times": times}) or {}
            sample_data = _data(sample)
            samples_list = sample_data.get("samples") or []
            mismatches: List[Dict[str, Any]] = []
            for s in samples_list:
                t_val = float(s.get("time", 0.0))
                idx = min(range(len(times)), key=lambda i: abs(times[i] - t_val))
                bone_name = s.get("bone", "")
                key = data["tracks"][bone_name][probe_frames[idx]]["rotation_quat"]
                if not _quat_close(s.get("rotation_quat", []), key):
                    mismatches.append({"bone": bone_name, "time": t_val, "engine": s.get("rotation_quat"), "synth": key})
            entry.update({
                "bone_tracks": res_data.get("bone_tracks"),
                "play_length_s": res_data.get("play_length_s"),
                "expected_length_s": data["duration"],
                "samples_checked": len(samples_list),
                "rotation_mismatches": mismatches[:6],
            })
            entry["ok"] = (
                bool(sample.get("ok"))
                and not mismatches
                and entry["bone_tracks"] == len(data["tracks"])
                and entry["samples_checked"] == len(bones) * len(times)
            )
        else:
            entry["ok"] = False
        rep["clips"].append(entry)
    rep["ok"] = bool(rep["clips"]) and all(c["ok"] for c in rep["clips"])
    _atomic_write_json(ANIM_REPORT, rep)
    print("GENERATED MOTION IN UNREAL:", "PASS" if rep["ok"] else "FAIL",
          [(c["clip"], c["ok"]) for c in rep["clips"]])
    return bool(rep["ok"])


def main() -> int:
    uproject, out_dir, anim_dir, shot_path = _resolve_paths()
    spec = CharacterSpec(character_id="char_adventurer_hero_01", name="GFAdventurerHero",
                         purpose="Playable Humanoid Hero Avatar", category="humanoid",
                         height_cm=180.0, triangle_budget=25000, target_territory="GLOBAL")
    gen = ProceduralSkinnedCharacterGenerator(output_dir=out_dir)
    bundle = gen.generate_humanoid(spec)
    gltf = gen.export_gltf(bundle)
    generated_bones = [b.name for b in bundle.bones]
    report: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_file": str(gltf),
        "generated": {"bones": generated_bones, "bone_count": len(generated_bones),
                      "vertices": len(bundle.vertices), "triangles": len(bundle.triangles)},
        "checks": {},
        "ok": False,
    }

    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    try:
        link.connect(discovery_timeout_s=900)
        link.call("delete_asset", {"asset_path": DEST})
        imp = link.call("character_import_skeletal_mesh", {"source_file": str(gltf), "destination_path": DEST},
                        timeout_s=300) or {}
        imp_data = _data(imp)
        report["import"] = imp
        mesh = str(imp_data.get("skeletal_mesh_path", ""))
        checks = report["checks"]
        checks["imported_generated_file"] = bool(imp.get("ok")) and mesh.startswith(DEST)
        if checks["imported_generated_file"]:
            insp = link.call("character_inspect_skeletal_mesh", {"skeletal_mesh_path": mesh})
            report["inspect"] = insp
            d = _data(insp)
            ue_bones = d.get("bone_names", [])
            checks["bone_names_match_generator"] = ue_bones == generated_bones
            checks["root_is_generated_root"] = d.get("root_bone_name") == generated_bones[0]
            ext = d.get("bounds") or {}
            # 180 cm T-pose humanoid standing on Z: half-height ~90 cm; arm span (X) about the height;
            # shallow front-to-back depth (Y). A Y-up/Z-up mix-up or a cm/m error breaks all three.
            ez, ex, ey = float(ext.get("box_extent_z", 0)), float(ext.get("box_extent_x", 0)), float(ext.get("box_extent_y", 0))
            checks["upright_and_real_scale"] = 60 <= ez <= 120 and ex <= 1.1 * ez and ey < 0.5 * ez
            spawn = link.call("character_spawn_preview", {"skeletal_mesh_path": mesh, "location": {"x": 0, "y": 0, "z": 0},
                                                         "actor_label": "Audit_GeneratedCharacter"})
            report["spawn"] = spawn
            link.call("set_viewport_camera", {"location": {"x": 320, "y": 0, "z": 110}, "rotation": {"pitch": -8, "yaw": 180, "roll": 0}})
            shot = link.capture_screenshot(shot_path, resolution=(1280, 720), wait_s=30.0)
            report["screenshot"] = _data(shot)
            skeleton = str(imp_data.get("skeleton_path", ""))
            if skeleton and checks.get("bone_names_match_generator"):
                checks["motion_verified"] = verify_motion(link, skeleton, anim_dir=anim_dir)
        report["ok"] = bool(checks) and all(checks.values())
    finally:
        report["editor_exit_code"] = link.stop()
        _atomic_write_json(REPORT, report)
    print(json.dumps(report["checks"], indent=2))
    print("GENERATED CHARACTER IN UNREAL:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
