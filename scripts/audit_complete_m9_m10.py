"""Audit 2026-10-30 (completion): M9 skinning + promotion and M10 locomotion in real UE 5.7.4.

1. Generated character glTF -> /Game/Quarantine (Interchange); validate skeleton, bounds and
   in-engine skin deformation (Unreal's imported weights), then promote to /Game/Characters.
2. Synthesized Idle/Walk/Run/Jump/Fall/Land -> AnimSequences on the promoted skeleton.
3. ABP_CharacterLocomotion (parent UGameForgeLocomotionAnimInstance) with the six clips.
4. PIE: an AI-possessed character walks, runs and jumps; the anim instance must change state
   because of that movement (Idle->Walk->Run->Jump->Fall->Land->Idle) and pose the mesh.
5. IK retargeting of the synthesized Walk onto a different skeleton (Epic's FbxEditorAutomation
   AnimatedCharacter, used only as a target with other bone names).
Evidence: reports/audit_m9_m10_completion.json and screenshots in the probe's Saved/Screenshots.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gameforge_ide.backend.models.animation_spec import LocomotionSetSpec  # noqa: E402
from src.gameforge_ide.backend.models.character_spec import CharacterSpec  # noqa: E402
from src.gameforge_ide.backend.tools.character_generator import ProceduralSkinnedCharacterGenerator  # noqa: E402
from src.gameforge_ide.backend.tools.character_rig_validator import CharacterRigValidator  # noqa: E402
from src.gameforge_ide.backend.tools.motion_generator import ProceduralKinematicMotionSynthesizer  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402

UPROJECT = Path(r"E:\GameForge\validation\live_ops_probe\GFProbe.uproject")
SHOTS = UPROJECT.parent / "Saved" / "Screenshots"
CHAR_DIR = Path(r"E:\GameForge\assets\generated\characters\audit_20261030")
ANIM_DIR = Path(r"E:\GameForge\assets\generated\animations\audit_20261030")
QUARANTINE = "/Game/Quarantine/Characters/GFAdventurerHero"
PROMOTED = "/Game/Characters/GFAdventurerHero"
ANIMS = "/Game/Characters/GFAdventurerHero/Animations"
ABP = "ABP_CharacterLocomotion"
RETARGET_TARGET_FBX = r"E:\UE\UE_5.7\Engine\Content\FbxEditorAutomation\AnimatedCharacter.fbx"
REPORT = ROOT / "reports" / "audit_m9_m10_completion.json"

DEFORM_TESTS = [("calf_l", "X", 45.0), ("lowerarm_l", "Z", 45.0), ("spine_01", "Z", 30.0)]
EXPECTED_TRANSITIONS = ["Idle->Walk", "Walk->Run", "Run->Jump", "Jump->Fall", "Fall->Land", "Land->Idle"]
SOURCE_RIG = {"root": "pelvis", "chains": {
    "Spine": ["spine_01", "spine_02"], "Head": ["neck", "head"],
    "LeftArm": ["upperarm_l", "hand_l"], "RightArm": ["upperarm_r", "hand_r"],
    "LeftLeg": ["thigh_l", "foot_l"], "RightLeg": ["thigh_r", "foot_r"]}}
TARGET_RIG = {"root": "Hips1", "chains": {
    "Spine": ["AbdoBottom1", "Brachius1"], "Head": ["Neck", "HeadEnd"],
    "LeftArm": ["ShoulderLeft1", "HandLeft"], "RightArm": ["ShoulderRight1", "HandRight"],
    "LeftLeg": ["HipLeft", "FootLeft"], "RightLeg": ["HipRight", "FootRight"]}}


def _ok(r):
    return bool(r.get("ok"))


def main() -> int:
    rep = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}, "steps": {}}
    checks, steps = rep["checks"], rep["steps"]

    spec = CharacterSpec(character_id="char_adventurer_hero_01", name="GFAdventurerHero",
                         purpose="Playable Humanoid Hero Avatar", category="humanoid",
                         height_cm=180.0, triangle_budget=25000, target_territory="GLOBAL")
    gen = ProceduralSkinnedCharacterGenerator(output_dir=CHAR_DIR)
    bundle = gen.generate_humanoid(spec)
    gltf = gen.export_gltf(bundle)
    py_deform = {t.joint_name: t.max_displacement for t in CharacterRigValidator.validate_bundle(bundle).deformation_tests}
    steps["python_validator_max_displacement_cm"] = py_deform

    link = LiveEditorLink(UPROJECT)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    try:
        link.connect(discovery_timeout_s=900)
        for path in (QUARANTINE, PROMOTED, "/Game/Audit/Retarget", "/Game/Audit/RetargetTarget", "/Game/RTG_Anim_Walk"):
            link.call("delete_asset", {"asset_path": path})

        # 1. Quarantine import + validation + promotion
        imp = link.call("character_import_skeletal_mesh", {"source_file": str(gltf), "destination_path": QUARANTINE}, timeout_s=300)
        steps["quarantine_import"] = imp.get("data")
        mesh_q = imp.get("data", {}).get("skeletal_mesh_path", "")
        insp = link.call("character_inspect_skeletal_mesh", {"skeletal_mesh_path": mesh_q})
        checks["quarantine_skeleton_matches_generator"] = insp.get("data", {}).get("bone_names") == [b.name for b in bundle.bones]
        deform = {}
        for bone, axis, angle in DEFORM_TESTS:
            r = link.call("character_measure_deformation", {"skeletal_mesh_path": mesh_q, "bone_name": bone, "axis": axis,
                                                            "angle_degrees": angle})
            deform[bone] = {"ok": _ok(r), **r.get("data", {}), "errors": r.get("errors", [])}
        steps["unreal_skin_deformation"] = deform
        checks["unreal_skin_deformation"] = all(d["ok"] for d in deform.values())
        if checks["quarantine_skeleton_matches_generator"] and checks["unreal_skin_deformation"]:
            moved = []
            for asset in imp["data"]["imported"]:
                clean = asset.split(".")[0]
                dst = clean.replace(QUARANTINE, PROMOTED, 1)
                moved.append(link.call("rename_asset", {"source_path": clean, "destination_path": dst}))
            steps["promotion"] = [m.get("data") for m in moved]
            checks["promoted_from_quarantine"] = all(_ok(m) for m in moved) and bool(moved)
        else:
            checks["promoted_from_quarantine"] = False
        mesh = mesh_q.replace(QUARANTINE, PROMOTED, 1)
        insp2 = link.call("character_inspect_skeletal_mesh", {"skeletal_mesh_path": mesh})
        skeleton = insp2.get("data", {}).get("skeleton_path", "").split(".")[0]
        checks["promoted_mesh_valid"] = _ok(insp2) and bool(skeleton)

        # Posed preview (GPU skinning) for visual evidence of deformation.
        link.call("character_measure_deformation", {"skeletal_mesh_path": mesh, "bone_name": "calf_l", "axis": "X",
                                                    "angle_degrees": 70.0, "posed_preview": {"x": 0, "y": 150, "z": 0}})
        link.call("character_spawn_preview", {"skeletal_mesh_path": mesh, "location": {"x": 0, "y": -150, "z": 0},
                                              "actor_label": "GF_BindPose"})
        link.call("set_viewport_camera", {"location": {"x": 420, "y": 0, "z": 110}, "rotation": {"pitch": -8, "yaw": 180, "roll": 0}})
        steps["posed_screenshot"] = link.capture_screenshot(SHOTS / "audit_m9_posed_vs_bind.png", wait_s=30.0).get("data")

        # 2. Clips on the promoted skeleton
        loco = LocomotionSetSpec.create_standard_humanoid_locomotion(
            character_id="char_adventurer_hero_01", target_skeleton_path=skeleton, destination_path=ANIMS)
        synth = ProceduralKinematicMotionSynthesizer(output_dir=ANIM_DIR)
        clips = {}
        for clip in loco.clips:
            path = synth.export_motion_json(synth.synthesize_clip(clip))
            r = link.call("anim_import_motion_clip", {"skeleton_path": skeleton, "motion_json_path": str(path),
                                                      "destination_path": ANIMS, "destination_name": clip.name}, timeout_s=120)
            if _ok(r):
                clips[clip.action.value.capitalize()] = r["data"]["anim_sequence_path"].split(".")[0]
        steps["clips"] = clips
        checks["six_clips_imported"] = sorted(clips) == sorted(["Idle", "Walk", "Run", "Jump", "Fall", "Land"])

        # 3. Locomotion AnimBP
        abp = link.call("anim_create_locomotion_blueprint", {"blueprint_name": ABP, "destination_path": PROMOTED,
                                                             "skeleton_path": skeleton, "clips": clips})
        steps["anim_blueprint"] = (abp.get("data") or {}) | {"errors": abp.get("errors")}
        checks["anim_blueprint_compiled_with_clips"] = (_ok(abp) and abp["data"].get("parent_class") == "GameForgeLocomotionAnimInstance"
                                                        and len([k for k in abp["data"].get("assigned_clips", {}) if k != "persisted_after_recompile"]) == 6
                                                        and abp["data"]["assigned_clips"].get("persisted_after_recompile") == 6)

        # 4. PIE: movement-driven transitions
        link.call("pie_start", {})
        time.sleep(4.0)
        start = link.call("anim_start_locomotion_test", {"skeletal_mesh_path": mesh, "anim_blueprint_path": f"{PROMOTED}/{ABP}",
                                                         "location": {"x": -900, "y": 900, "z": 150}})
        steps["pie_start_test"] = (start.get("data") or {}) | {"errors": start.get("errors")}
        link.call("pie_view_from", {"location": {"x": 300, "y": 100, "z": 250}, "rotation": {"pitch": -12, "yaw": 90, "roll": 0}})
        samples = []
        deadline = time.time() + 25
        shot_at = {"walk": 2.8, "run": 5.2}
        result = {}
        while time.time() < deadline:
            res = link.call("anim_locomotion_test_result", {})
            result = res.get("data", {})
            samples.append({k: result.get(k) for k in ("elapsed_s", "current_state", "ground_speed", "thigh_l_deviation_deg")})
            if "pie_diagnostics" not in steps and result.get("elapsed_s", 0) >= 2.5:
                steps["pie_diagnostics"] = link.call("pie_character_diagnostics", {}).get("data")
            for name, t in list(shot_at.items()):
                if result.get("elapsed_s", 0) >= t:
                    link.capture_screenshot(SHOTS / f"audit_m10_pie_{name}.png", wait_s=15.0, show_ui=True)
                    shot_at.pop(name)
            if result.get("finished"):
                break
            time.sleep(0.4)
        link.call("pie_stop", {})
        transitions = [t.split()[0] for t in result.get("transitions", [])]
        steps["pie_transitions"] = result.get("transitions", [])
        steps["pie_phases"] = result.get("phases", [])
        steps["pie_samples"] = samples
        it = iter(transitions)
        checks["movement_driven_transitions_in_order"] = all(any(t == want for t in it) for want in EXPECTED_TRANSITIONS)
        checks["clips_pose_the_mesh"] = max((s.get("thigh_l_deviation_deg") or 0) for s in samples) > 5.0

        # 5. IK retargeting onto a different skeleton
        tgt = link.call("character_import_skeletal_mesh", {"source_file": RETARGET_TARGET_FBX, "destination_path": "/Game/Audit/RetargetTarget",
                                                           "destination_name": "SK_RetargetTarget"}, timeout_s=300)
        tgt_mesh = tgt.get("data", {}).get("skeletal_mesh_path", "")
        walk = clips.get("Walk", "")
        rt = link.call("anim_ik_retarget", {"source_mesh": mesh, "target_mesh": tgt_mesh, "source_rig": SOURCE_RIG,
                                            "target_rig": TARGET_RIG, "animations": [walk + "." + walk.rsplit("/", 1)[-1]],
                                            "destination_path": "/Game/Audit/Retarget"}, timeout_s=300)
        steps["ik_retarget"] = (rt.get("data") or {}) | {"errors": rt.get("errors")}
        moving = False
        if _ok(rt) and rt["data"].get("on_target_skeleton"):
            seq = rt["data"]["on_target_skeleton"][0]
            s = link.call("anim_sample_bone_pose", {"anim_sequence_path": seq, "bones": ["HipLeft", "KneeLeft"], "times": [0.0, 0.3, 0.6]})
            steps["retarget_samples"] = s.get("data")
            for bone in ("HipLeft", "KneeLeft"):
                qs = [x["rotation_quat"] for x in s.get("data", {}).get("samples", []) if x["bone"] == bone]
                if len(qs) >= 2:
                    dots = [abs(sum(a * b for a, b in zip(qs[0], q))) for q in qs[1:]]
                    moving |= min(dots) < 0.9990  # > ~5 degrees of change across the gait
        checks["retargeted_onto_different_skeleton"] = _ok(rt)
        checks["retargeted_legs_animate"] = moving
    finally:
        rep["editor_exit_code"] = link.stop()
        rep["ok"] = bool(checks) and all(checks.values())
        REPORT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps(checks, indent=2))
    print("M9/M10 COMPLETION:", "PASS" if rep["ok"] else "FAIL")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
