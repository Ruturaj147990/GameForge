"""Animation Track and Kinematic Validation Engine for GameForge IDE.

Adheres to Milestone 10:
- Track mapping and frame count verification.
- Finite coordinates and unit quaternion normalization.
- Loop boundary continuity for cyclic locomotion.
- Smoothness and angular velocity jitter checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ...backend.tools.motion_generator import KeyframeTransform, MotionClipBundle


@dataclass
class ClipValidationReport:
    clip_name: str
    action: str
    is_valid: bool
    frame_count_passed: bool
    quaternions_passed: bool
    loop_continuity_passed: bool
    smoothness_passed: bool
    total_frames: int
    duration_seconds: float
    max_loop_error_deg: float
    errors: List[str] = field(default_factory=list)


def quaternion_distance_degrees(q1: Tuple[float, float, float, float], q2: Tuple[float, float, float, float]) -> float:
    """Computes angular distance between two unit quaternions in degrees."""
    if len(q1) < 4 or len(q2) < 4:
        return 0.0
    dot = abs(q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3])
    dot = max(-1.0, min(1.0, dot))
    angle_rad = 2.0 * math.acos(dot)
    return math.degrees(angle_rad)


class AnimationValidator:
    """Validates skeletal animation clip bundles against kinematic acceptance criteria."""

    @classmethod
    def validate_clip(cls, bundle: MotionClipBundle) -> ClipValidationReport:
        errors: List[str] = []
        spec = bundle.spec

        # 1. Frame count & tracks check
        expected_frames = bundle.total_frames
        fc_passed = True
        if len(bundle.tracks) == 0:
            errors.append(f"Clip '{spec.name}' has no bone tracks.")
            fc_passed = False

        for b_name, trk in bundle.tracks.items():
            if len(trk.keyframes) != expected_frames:
                errors.append(f"Bone '{b_name}' has {len(trk.keyframes)} frames, expected {expected_frames}.")
                fc_passed = False
                break

        # 2. Quaternion normalization & finite values check
        quat_passed = True
        for b_name, trk in bundle.tracks.items():
            for idx, k in enumerate(trk.keyframes):
                qx, qy, qz, qw = k.rotation_quat
                lx, ly, lz = k.location

                # Finite coordinates
                if any(math.isnan(c) or math.isinf(c) for c in (qx, qy, qz, qw, lx, ly, lz)):
                    errors.append(f"Bone '{b_name}' frame {idx} has NaN or infinite values.")
                    quat_passed = False
                    break

                # Unit quaternion check
                norm_sq = qx * qx + qy * qy + qz * qz + qw * qw
                if abs(norm_sq - 1.0) > 1e-3:
                    errors.append(f"Bone '{b_name}' frame {idx} quaternion not normalized (norm^2 = {norm_sq:.5f}).")
                    quat_passed = False
                    break
            if not quat_passed:
                break

        # 3. Loop boundary continuity check
        loop_passed = True
        max_loop_err = 0.0
        if spec.is_looping and expected_frames > 1:
            for b_name, trk in bundle.tracks.items():
                if not trk.keyframes:
                    continue
                first_k = trk.keyframes[0]
                last_k = trk.keyframes[-1]
                ang_err = quaternion_distance_degrees(first_k.rotation_quat, last_k.rotation_quat)
                max_loop_err = max(max_loop_err, ang_err)

                loc_err = math.sqrt(
                    (first_k.location[0] - last_k.location[0]) ** 2 +
                    (first_k.location[1] - last_k.location[1]) ** 2 +
                    (first_k.location[2] - last_k.location[2]) ** 2
                )

                if ang_err > spec.quality_criteria.max_loop_discontinuity_deg:
                    errors.append(f"Bone '{b_name}' loop discontinuity {ang_err:.2f} deg exceeds threshold ({spec.quality_criteria.max_loop_discontinuity_deg} deg).")
                    loop_passed = False
                if loc_err > 0.5:  # 0.5 cm
                    errors.append(f"Bone '{b_name}' loop location error {loc_err:.2f} cm exceeds 0.5 cm.")
                    loop_passed = False

        # 4. Smoothness & jitter check
        smooth_passed = True
        max_jitter = spec.quality_criteria.max_rotation_jitter_deg
        for b_name, trk in bundle.tracks.items():
            for idx in range(len(trk.keyframes) - 1):
                k1 = trk.keyframes[idx]
                k2 = trk.keyframes[idx + 1]
                step_deg = quaternion_distance_degrees(k1.rotation_quat, k2.rotation_quat)
                if step_deg > max_jitter:
                    errors.append(f"Bone '{b_name}' frame {idx}->{idx+1} rotational step ({step_deg:.2f} deg) exceeds jitter limit ({max_jitter} deg).")
                    smooth_passed = False
                    break
            if not smooth_passed:
                break

        is_valid = fc_passed and quat_passed and loop_passed and smooth_passed and (len(errors) == 0)

        action_name = spec.action.value if hasattr(spec.action, "value") else str(spec.action)
        return ClipValidationReport(
            clip_name=spec.name,
            action=action_name,
            is_valid=is_valid,
            frame_count_passed=fc_passed,
            quaternions_passed=quat_passed,
            loop_continuity_passed=loop_passed,
            smoothness_passed=smooth_passed,
            total_frames=expected_frames,
            duration_seconds=bundle.duration,
            max_loop_error_deg=round(max_loop_err, 4),
            errors=errors,
        )
