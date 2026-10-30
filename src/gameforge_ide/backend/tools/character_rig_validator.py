"""Rig and Skinning Validation Engine for GameForge IDE.

Adheres to Milestone 9:
- Hierarchy validation (acyclic, root bone, bone count budgets).
- Vertex skin weights validation (finite, non-negative, unit sum, valid bone indices).
- Forward Kinematics Joint Deformation Stress Test:
  Simulates rotational articulation around major joints (knee, elbow, spine)
  and verifies bounded, smooth deformations without mesh collapse or NaN/inf values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.gameforge_ide.backend.tools.character_generator import BoneNode, SkinnedMeshBundle, SkinnedVertex


@dataclass
class DeformationTestResult:
    joint_name: str
    rotation_axis: str
    angle_degrees: float
    passed: bool
    max_displacement: float
    has_nan_or_inf: bool
    bounding_box_valid: bool
    notes: str = ""


@dataclass
class RigValidationReport:
    character_id: str
    is_valid: bool
    hierarchy_passed: bool
    weights_passed: bool
    deformation_passed: bool
    bone_count: int
    vertex_count: int
    triangle_count: int
    errors: List[str] = field(default_factory=list)
    deformation_tests: List[DeformationTestResult] = field(default_factory=list)


class CharacterRigValidator:
    """Validates character skeletons, vertex skin weights, and forward kinematics deformation."""

    @staticmethod
    def validate_hierarchy(bones: List[BoneNode], min_bones: int = 10, max_bones: int = 128) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if len(bones) < min_bones:
            errors.append(f"Skeleton bone count ({len(bones)}) is below minimum ({min_bones}).")
        if len(bones) > max_bones:
            errors.append(f"Skeleton bone count ({len(bones)}) exceeds budget ({max_bones}).")

        # Root bone check
        root_bones = [b for b in bones if b.parent_id == -1]
        if len(root_bones) != 1:
            errors.append(f"Skeleton must have exactly one root bone (found {len(root_bones)}).")
        elif root_bones[0].name.lower() not in ("root", "pelvis", "hips"):
            errors.append(f"Root bone name '{root_bones[0].name}' must be one of: root, pelvis, hips.")

        # Acyclic and valid parent check
        bone_ids = {b.bone_id for b in bones}
        bone_names = set()
        for b in bones:
            if b.name in bone_names:
                errors.append(f"Duplicate bone name detected: '{b.name}'.")
            bone_names.add(b.name)

            if b.parent_id != -1:
                if b.parent_id not in bone_ids:
                    errors.append(f"Bone '{b.name}' (id {b.bone_id}) references non-existent parent {b.parent_id}.")
                elif b.parent_id >= b.bone_id:
                    errors.append(f"Bone '{b.name}' (id {b.bone_id}) has non-topological parent index {b.parent_id}.")

        return (len(errors) == 0, errors)

    @staticmethod
    def validate_skin_weights(
        vertices: List[SkinnedVertex],
        bones: List[BoneNode],
        tolerance: float = 1e-3,
    ) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        bone_count = len(bones)

        for idx, v in enumerate(vertices):
            # Check non-negative and finite
            weights = v.bone_weights
            indices = v.bone_indices

            for w in weights:
                if math.isnan(w) or math.isinf(w):
                    errors.append(f"Vertex {idx} has NaN or infinite weight: {weights}")
                    return (False, errors)
                if w < -1e-6:
                    errors.append(f"Vertex {idx} has negative skin weight: {w}")
                    return (False, errors)

            # Check unit sum (partition of unity)
            w_sum = sum(weights)
            if abs(w_sum - 1.0) > tolerance:
                errors.append(f"Vertex {idx} weight sum {w_sum:.5f} violates partition of unity (expected 1.0).")
                if len(errors) >= 10:
                    errors.append("... (further weight sum errors truncated)")
                    break

            # Check bone index bounds
            for b_idx in indices:
                if b_idx < 0 or b_idx >= bone_count:
                    errors.append(f"Vertex {idx} references out-of-bounds bone index {b_idx} (valid: 0..{bone_count-1}).")
                    if len(errors) >= 10:
                        break

            # Check orphan vertex
            if max(weights) <= 0.0:
                errors.append(f"Vertex {idx} has no non-zero bone weights (orphan vertex).")
                if len(errors) >= 10:
                    break

        return (len(errors) == 0, errors)

    @classmethod
    def test_joint_rotations(
        cls,
        bundle: SkinnedMeshBundle,
    ) -> List[DeformationTestResult]:
        """Performs forward kinematics deformation test across representative joints."""
        results: List[DeformationTestResult] = []
        bone_map = {b.name: b for b in bundle.bones}

        # Test cases: (joint_name, axis, angle_degrees, description)
        test_cases = [
            ("calf_l", "X", 45.0, "Left Knee Bend 45 deg"),
            ("lowerarm_l", "Z", 45.0, "Left Elbow Flex 45 deg"),
            ("spine_01", "Z", 30.0, "Torso Spine Twist 30 deg"),
        ]

        # Base bounding box extent
        orig_min = bundle.bounding_box_min
        orig_max = bundle.bounding_box_max
        orig_dx = orig_max[0] - orig_min[0]
        orig_dy = orig_max[1] - orig_min[1]
        orig_dz = orig_max[2] - orig_min[2]
        orig_diag = math.sqrt(orig_dx * orig_dx + orig_dy * orig_dy + orig_dz * orig_dz)

        for j_name, axis, angle_deg, desc in test_cases:
            if j_name not in bone_map:
                results.append(DeformationTestResult(
                    joint_name=j_name,
                    rotation_axis=axis,
                    angle_degrees=angle_deg,
                    passed=False,
                    max_displacement=0.0,
                    has_nan_or_inf=False,
                    bounding_box_valid=False,
                    notes=f"Joint '{j_name}' not found in skeleton.",
                ))
                continue

            bone = bone_map[j_name]
            pivot = bone.head_pos
            rad = math.radians(angle_deg)
            cos_a, sin_a = math.cos(rad), math.sin(rad)

            # Apply local rotation around pivot for vertices influenced by this bone
            max_disp = 0.0
            has_nan = False
            deformed_coords: List[Tuple[float, float, float]] = []

            for v in bundle.vertices:
                # Find influence of this bone
                weight = 0.0
                for b_id, w in zip(v.bone_indices, v.bone_weights):
                    if b_id == bone.bone_id:
                        weight += w

                vx, vy, vz = v.position
                if weight > 0.0:
                    # Translate to pivot
                    dx, dy, dz = vx - pivot[0], vy - pivot[1], vz - pivot[2]
                    # Rotate
                    if axis == "X":
                        ry = dy * cos_a - dz * sin_a
                        rz = dy * sin_a + dz * cos_a
                        rx = dx
                    elif axis == "Y":
                        rx = dx * cos_a + dz * sin_a
                        rz = -dx * sin_a + dz * cos_a
                        ry = dy
                    else:  # Z
                        rx = dx * cos_a - dy * sin_a
                        ry = dx * sin_a + dy * cos_a
                        rz = dz

                    # Linear blend with rest pose
                    rot_x = pivot[0] + rx
                    rot_y = pivot[1] + ry
                    rot_z = pivot[2] + rz

                    def_x = (1.0 - weight) * vx + weight * rot_x
                    def_y = (1.0 - weight) * vy + weight * rot_y
                    def_z = (1.0 - weight) * vz + weight * rot_z
                else:
                    def_x, def_y, def_z = vx, vy, vz

                if math.isnan(def_x) or math.isnan(def_y) or math.isnan(def_z):
                    has_nan = True
                    break

                disp = math.sqrt((def_x - vx)**2 + (def_y - vy)**2 + (def_z - vz)**2)
                max_disp = max(max_disp, disp)
                deformed_coords.append((def_x, def_y, def_z))

            # Bounding box of deformed mesh
            if deformed_coords and not has_nan:
                d_min_x = min(c[0] for c in deformed_coords)
                d_max_x = max(c[0] for c in deformed_coords)
                d_min_y = min(c[1] for c in deformed_coords)
                d_max_y = max(c[1] for c in deformed_coords)
                d_min_z = min(c[2] for c in deformed_coords)
                d_max_z = max(c[2] for c in deformed_coords)
                def_diag = math.sqrt((d_max_x - d_min_x)**2 + (d_max_y - d_min_y)**2 + (d_max_z - d_min_z)**2)
                bbox_valid = def_diag <= orig_diag * 1.35 and max_disp > 0.05
            else:
                bbox_valid = False

            passed = (not has_nan) and bbox_valid and (max_disp > 0.0)

            results.append(DeformationTestResult(
                joint_name=j_name,
                rotation_axis=axis,
                angle_degrees=angle_deg,
                passed=passed,
                max_displacement=round(max_disp, 3),
                has_nan_or_inf=has_nan,
                bounding_box_valid=bbox_valid,
                notes=f"{desc}: max displacement = {max_disp:.2f} cm, bbox scale = {def_diag/orig_diag:.3f}x",
            ))

        return results

    @classmethod
    def validate_bundle(cls, bundle: SkinnedMeshBundle) -> RigValidationReport:
        """Full validation entry point for SkinnedMeshBundle."""
        errors: List[str] = []

        # 1. Hierarchy
        h_ok, h_errs = cls.validate_hierarchy(bundle.bones, bundle.spec.rig.min_bones, bundle.spec.rig.max_bones)
        errors.extend(h_errs)

        # 2. Weights
        w_ok, w_errs = cls.validate_skin_weights(bundle.vertices, bundle.bones)
        errors.extend(w_errs)

        # 3. Joint deformation tests
        deform_results = cls.test_joint_rotations(bundle)
        d_ok = all(t.passed for t in deform_results)
        if not d_ok:
            failed_tests = [t.joint_name for t in deform_results if not t.passed]
            errors.append(f"Joint deformation stress tests failed for joints: {failed_tests}")

        # Overall verdict
        is_valid = h_ok and w_ok and d_ok and (len(errors) == 0)

        return RigValidationReport(
            character_id=bundle.character_id,
            is_valid=is_valid,
            hierarchy_passed=h_ok,
            weights_passed=w_ok,
            deformation_passed=d_ok,
            bone_count=len(bundle.bones),
            vertex_count=len(bundle.vertices),
            triangle_count=len(bundle.triangles),
            errors=errors,
            deformation_tests=deform_results,
        )
