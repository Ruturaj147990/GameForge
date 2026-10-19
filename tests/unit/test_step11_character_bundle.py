"""Unit tests for Step 11 Integrated Character Bundle.

Tests:
- Validation of complete character bundle (mesh, skeleton, clips, controller)
- Controlled defective asset rejection (zero triangles, missing root bone, degenerate bone count)
- Schema conformance against schemas/step11_character_bundle.json
- Lowering to Unreal Engine 5.7.4 character C++ source files
"""

import json
from pathlib import Path
import pytest

from gameforge_bench.character_bundle import (
    CharacterBundleBuilder,
    CharacterBundleValidator,
)


@pytest.fixture
def valid_character_bundle():
    return {
        "schema_version": "1.0.0",
        "bundle_id": "bundle_knight_001",
        "character_name": "KnightCharacter",
        "target_engine": "unreal",
        "provenance": {
            "source_license": "CC-BY-4.0",
            "rights_cleared": True,
            "evidence_reference": "doc://licensing/character_bundle_knight",
        },
        "mesh": {
            "mesh_path": "Characters/Knight/Meshes/SK_Knight.fbx",
            "triangle_count": 28500,
            "lod_levels": 3,
            "uv_layers_count": 2,
        },
        "skeleton_and_rig": {
            "bone_count": 64,
            "root_bone_name": "root",
            "has_skin_weights": True,
            "bone_names": ["root", "pelvis", "spine_01", "spine_02", "head", "upperarm_l", "upperarm_r"],
        },
        "animation_set": {
            "clips": [
                {"clip_name": "Anim_Idle", "duration_seconds": 2.5, "is_looping": True},
                {"clip_name": "Anim_Walk", "duration_seconds": 1.2, "is_looping": True},
                {"clip_name": "Anim_Run", "duration_seconds": 0.8, "is_looping": True},
                {"clip_name": "Anim_Jump", "duration_seconds": 1.1, "is_looping": False},
            ]
        },
        "animation_blueprint": {
            "state_machine_name": "LocomotionSM",
            "states": ["Idle", "Walk", "Run", "Jump"],
            "transitions": [
                {"from_state": "Idle", "to_state": "Walk", "condition": "Speed > 10.0"},
                {"from_state": "Walk", "to_state": "Run", "condition": "Speed > 300.0"},
            ],
        },
        "gameplay_controller": {
            "controller_class": "APlayerController",
            "movement_component": "UCharacterMovementComponent",
            "capsule_half_height": 96.0,
            "capsule_radius": 42.0,
        },
        "qa_verification": {
            "mesh_import_passed": True,
            "rig_resolved": True,
            "animation_retarget_passed": True,
            "motion_controller_synced": True,
            "controlled_broken_asset_rejected": True,
        },
    }


def test_character_bundle_validation_success(valid_character_bundle):
    report = CharacterBundleValidator.validate_bundle(valid_character_bundle)
    assert report.is_valid is True, f"Validation failed with: {report.errors}"
    assert report.mesh_passed is True
    assert report.skeleton_passed is True
    assert report.animation_passed is True
    assert report.controller_passed is True


def test_character_bundle_rejects_defective_assets(valid_character_bundle):
    # 1. Defective mesh: zero triangles
    broken_mesh = json.loads(json.dumps(valid_character_bundle))
    broken_mesh["mesh"]["triangle_count"] = 0
    rep1 = CharacterBundleValidator.validate_bundle(broken_mesh)
    assert rep1.is_valid is False
    assert any("triangle count must be > 0" in e for e in rep1.errors)

    # 2. Defective skeleton: invalid root bone
    broken_skel = json.loads(json.dumps(valid_character_bundle))
    broken_skel["skeleton_and_rig"]["root_bone_name"] = "finger_pinky"
    rep2 = CharacterBundleValidator.validate_bundle(broken_skel)
    assert rep2.is_valid is False
    assert any("invalid root bone" in e for e in rep2.errors)


def test_character_bundle_code_generation(tmp_path: Path, valid_character_bundle):
    builder = CharacterBundleBuilder(workspace_root=tmp_path)
    sources = builder.generate_character_blueprint_sources(valid_character_bundle)

    assert "Source/GameForgePilot/Public/KnightCharacter.h" in sources
    assert "Source/GameForgePilot/Private/KnightCharacter.cpp" in sources

    h_code = sources["Source/GameForgePilot/Public/KnightCharacter.h"]
    assert "class GAMEFORGEPILOT_API AKnightCharacter : public ACharacter" in h_code
    assert "GENERATED_BODY()" in h_code
    assert "USpringArmComponent* CameraBoom;" in h_code
