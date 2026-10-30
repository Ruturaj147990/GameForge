"""Unit test suite for Milestone 10: Prompt-Driven Animation V1.

Tests:
- REQ-M10-01: AnimationSpec and LocomotionSetSpec validation and constraints
- REQ-M10-02: ProceduralKinematicMotionSynthesizer gait synthesis for 6 standard actions
- REQ-M10-03: Mathematical unit quaternion normalization (x^2 + y^2 + z^2 + w^2 = 1.0)
- REQ-M10-04: Exact mathematical loop boundary continuity for cyclic locomotion
- REQ-M10-05: AnimationValidator rejection of non-normalized quaternions, NaNs, and infinities
- REQ-M10-06: AnimationValidator rejection of rotational jitter exceeding threshold
- REQ-M10-07: AnimationValidator rejection of loop boundary jumps on cyclic clips
- REQ-M10-08: AnimationPipeline end-to-end execution and provenance sealing
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
import pytest

from src.gameforge_ide.backend.models.animation_spec import (
    AnimationAction,
    AnimationSpec,
    LocomotionSetSpec,
    MovementStyle,
    QualityCriteria,
)
from src.gameforge_ide.backend.models.provenance import (
    AssetProvenanceRecord,
    LicenseRegistry,
)
from src.gameforge_ide.backend.tools.animation_validator import (
    AnimationValidator,
    ClipValidationReport,
    quaternion_distance_degrees,
)
from src.gameforge_ide.backend.tools.motion_generator import (
    BoneMotionTrack,
    KeyframeTransform,
    MotionClipBundle,
    ProceduralKinematicMotionSynthesizer,
    euler_to_quaternion,
)
from src.gameforge_ide.pipeline.animation_pipeline import (
    AnimationPipeline,
    AnimationPipelineResult,
)


@pytest.fixture
def standard_locomotion_spec():
    return LocomotionSetSpec.create_standard_humanoid_locomotion(
        character_id="char_test_hero",
        target_skeleton_path="/Game/Characters/TestHero/SK_TestHero_Skeleton",
        destination_path="/Game/Animations",
    )


def test_animation_spec_validation():
    # Valid spec
    spec = AnimationSpec(
        spec_id="test_idle",
        name="Anim_TestIdle",
        action=AnimationAction.IDLE,
        target_character_id="char_test",
        target_skeleton_path="/Game/Characters/SK_Test_Skeleton",
        duration_seconds=1.5,
        sample_rate_hz=30,
        is_looping=True,
    )
    assert spec.total_frames == 45
    assert len(spec.compute_sha256()) == 64

    # Invalid duration (< 0.05s)
    with pytest.raises(ValueError, match="duration_seconds"):
        AnimationSpec(
            spec_id="bad_dur",
            name="Anim_BadDur",
            action=AnimationAction.WALK,
            target_character_id="char_test",
            target_skeleton_path="/Game/Skeleton",
            duration_seconds=0.01,
        )

    # Invalid sample rate
    with pytest.raises(ValueError, match="sample_rate_hz"):
        AnimationSpec(
            spec_id="bad_fps",
            name="Anim_BadFps",
            action=AnimationAction.WALK,
            target_character_id="char_test",
            target_skeleton_path="/Game/Skeleton",
            sample_rate_hz=45,  # non-standard
        )

    # Empty target skeleton
    with pytest.raises(ValueError, match="target_skeleton_path"):
        AnimationSpec(
            spec_id="bad_skel",
            name="Anim_BadSkel",
            action=AnimationAction.WALK,
            target_character_id="char_test",
            target_skeleton_path="",
        )


def test_locomotion_set_spec_authoring(standard_locomotion_spec):
    assert standard_locomotion_spec.character_id == "char_test_hero"
    assert len(standard_locomotion_spec.clips) == 6

    actions = [c.action for c in standard_locomotion_spec.clips]
    assert AnimationAction.IDLE in actions
    assert AnimationAction.WALK in actions
    assert AnimationAction.RUN in actions
    assert AnimationAction.JUMP in actions
    assert AnimationAction.FALL in actions
    assert AnimationAction.LAND in actions

    # Looping flags
    idle_clip = next(c for c in standard_locomotion_spec.clips if c.action == AnimationAction.IDLE)
    assert idle_clip.is_looping is True
    jump_clip = next(c for c in standard_locomotion_spec.clips if c.action == AnimationAction.JUMP)
    assert jump_clip.is_looping is False


def test_euler_to_quaternion_normalization():
    # Zero rotation produces identity (0, 0, 0, 1)
    q0 = euler_to_quaternion(0.0, 0.0, 0.0)
    assert pytest.approx(q0[0], abs=1e-6) == 0.0
    assert pytest.approx(q0[1], abs=1e-6) == 0.0
    assert pytest.approx(q0[2], abs=1e-6) == 0.0
    assert pytest.approx(q0[3], abs=1e-6) == 1.0

    # Arbitrary angle produces normalized unit quaternion (norm = 1.0)
    q1 = euler_to_quaternion(35.5, -42.1, 88.0)
    norm_sq = sum(c * c for c in q1)
    assert pytest.approx(norm_sq, abs=1e-6) == 1.0


def test_quaternion_distance_degrees():
    q_ident = (0.0, 0.0, 0.0, 1.0)
    # 90 degrees yaw about Z
    q_yaw90 = euler_to_quaternion(0.0, 90.0, 0.0)
    dist = quaternion_distance_degrees(q_ident, q_yaw90)
    assert pytest.approx(dist, abs=0.1) == 90.0

    # Same quaternion produces 0 degrees
    assert pytest.approx(quaternion_distance_degrees(q_yaw90, q_yaw90), abs=1e-6) == 0.0


def test_procedural_motion_synthesis_all_actions(standard_locomotion_spec, tmp_path):
    synthesizer = ProceduralKinematicMotionSynthesizer(output_dir=tmp_path)

    for clip_spec in standard_locomotion_spec.clips:
        bundle = synthesizer.synthesize_clip(clip_spec)
        assert bundle.duration == clip_spec.duration_seconds
        assert bundle.total_frames == clip_spec.total_frames
        assert len(bundle.tracks) >= 18

        # Verify keyframes non-empty
        for b_name, trk in bundle.tracks.items():
            assert len(trk.keyframes) == bundle.total_frames
            for k in trk.keyframes:
                norm_sq = sum(c * c for c in k.rotation_quat)
                assert pytest.approx(norm_sq, abs=1e-4) == 1.0

        # Verify loop continuity if looping
        if clip_spec.is_looping:
            for b_name, trk in bundle.tracks.items():
                first_q = trk.keyframes[0].rotation_quat
                last_q = trk.keyframes[-1].rotation_quat
                assert quaternion_distance_degrees(first_q, last_q) <= clip_spec.quality_criteria.max_loop_discontinuity_deg

        # Validate with AnimationValidator
        report = AnimationValidator.validate_clip(bundle)
        assert report.is_valid is True, f"Clip {clip_spec.name} failed: {report.errors}"


def test_motion_export_json(standard_locomotion_spec, tmp_path):
    synthesizer = ProceduralKinematicMotionSynthesizer(output_dir=tmp_path)
    walk_spec = next(c for c in standard_locomotion_spec.clips if c.action == AnimationAction.WALK)
    bundle = synthesizer.synthesize_clip(walk_spec)

    out_file = synthesizer.export_motion_json(bundle)
    assert out_file.exists()
    assert out_file.stat().st_size > 500

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["name"] == walk_spec.name
    assert data["action"] == "walk"
    assert data["total_frames"] == walk_spec.total_frames
    assert "pelvis" in data["tracks"]


def test_animation_validator_rejects_unnormalized_quaternion(standard_locomotion_spec, tmp_path):
    synthesizer = ProceduralKinematicMotionSynthesizer(output_dir=tmp_path)
    idle_spec = next(c for c in standard_locomotion_spec.clips if c.action == AnimationAction.IDLE)
    bundle = synthesizer.synthesize_clip(idle_spec)

    # Corrupt keyframe with unnormalized quaternion
    bundle.tracks["spine_01"].keyframes[10].rotation_quat = (2.0, 2.0, 2.0, 2.0)
    report = AnimationValidator.validate_clip(bundle)
    assert report.is_valid is False
    assert report.quaternions_passed is False
    assert any("not normalized" in err for err in report.errors)


def test_animation_validator_rejects_nans_and_infinities(standard_locomotion_spec, tmp_path):
    synthesizer = ProceduralKinematicMotionSynthesizer(output_dir=tmp_path)
    idle_spec = next(c for c in standard_locomotion_spec.clips if c.action == AnimationAction.IDLE)
    bundle = synthesizer.synthesize_clip(idle_spec)

    bundle.tracks["head"].keyframes[5].rotation_quat = (float("nan"), 0.0, 0.0, 1.0)
    report = AnimationValidator.validate_clip(bundle)
    assert report.is_valid is False
    assert report.quaternions_passed is False
    assert any("NaN or infinite" in err for err in report.errors)


def test_animation_validator_rejects_loop_discontinuity(standard_locomotion_spec, tmp_path):
    synthesizer = ProceduralKinematicMotionSynthesizer(output_dir=tmp_path)
    walk_spec = next(c for c in standard_locomotion_spec.clips if c.action == AnimationAction.WALK)
    bundle = synthesizer.synthesize_clip(walk_spec)

    # Inject 90 degree discontinuity on last frame of looping clip
    bundle.tracks["thigh_l"].keyframes[-1].rotation_quat = euler_to_quaternion(90.0, 0.0, 0.0)
    report = AnimationValidator.validate_clip(bundle)
    assert report.is_valid is False
    assert report.loop_continuity_passed is False
    assert any("loop discontinuity" in err for err in report.errors)


def test_animation_validator_rejects_excessive_jitter(standard_locomotion_spec, tmp_path):
    synthesizer = ProceduralKinematicMotionSynthesizer(output_dir=tmp_path)
    walk_spec = next(c for c in standard_locomotion_spec.clips if c.action == AnimationAction.WALK)
    bundle = synthesizer.synthesize_clip(walk_spec)

    # Inject 45 degree rotational step between frames 10 and 11 (limit is 25 deg)
    bundle.tracks["upperarm_r"].keyframes[11].rotation_quat = euler_to_quaternion(55.0, 0.0, 0.0)
    report = AnimationValidator.validate_clip(bundle)
    assert report.is_valid is False
    assert report.smoothness_passed is False
    assert any("exceeds jitter limit" in err for err in report.errors)


def test_animation_pipeline_end_to_end(standard_locomotion_spec, tmp_path):
    pipeline = AnimationPipeline(workspace_dir=tmp_path, output_dir=tmp_path / "assets")
    result = pipeline.run_pipeline(standard_locomotion_spec)

    assert result.success is True
    assert result.spec_valid is True
    assert result.motion_synthesis_passed is True
    assert result.validation_passed is True
    assert result.blueprint_created is True
    assert len(result.clip_reports) == 6
    assert len(result.exported_clip_files) == 6
    assert Path(result.provenance_path).exists()

    # Verify provenance content
    with open(result.provenance_path, "r", encoding="utf-8") as f:
        prov = json.load(f)
    assert prov["asset_id"] == standard_locomotion_spec.bundle_id
    assert prov["model_name"] == "GameForge-KinematicSynthesis-V1"
    assert prov["license_name"] == "CC-BY-4.0"
    assert "provenance_hash" in prov and len(prov["provenance_hash"]) == 64
