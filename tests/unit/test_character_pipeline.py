"""Unit test suite for Milestone 9: Character Creation, Rigging, and Unreal Pipeline.

Tests:
- REQ-M9-01: CharacterSpec validation and constraints enforcement
- REQ-M9-02: Procedural Skinned Character generation (geometry, UVs [0, 1], bones)
- REQ-M9-03: glTF 2.0 export with skins, joints, weights, and accessors
- REQ-M9-04: Rig hierarchy validation and broken skeleton rejection
- REQ-M9-05: Vertex skin weights partition of unity (sum = 1.0) and non-negativity
- REQ-M9-06: Forward kinematics joint deformation stress testing (knee, elbow, spine)
- REQ-M9-07: Provenance recording, territory compliance, and cryptographic sealing
- REQ-M9-08: Quarantine staging and broken-asset rejection
"""

import json
import math
import tempfile
from pathlib import Path
import pytest

from src.gameforge_ide.backend.models.character_spec import (
    BodyCoverageSpec,
    CharacterSpec,
    MaterialSpec,
    ProportionsSpec,
    RigSpec,
)
from src.gameforge_ide.backend.models.provenance import (
    AssetProvenanceRecord,
    LicenseRegistry,
)
from src.gameforge_ide.backend.tools.character_generator import (
    BoneNode,
    ProceduralSkinnedCharacterGenerator,
    SkinnedVertex,
)
from src.gameforge_ide.backend.tools.character_rig_validator import (
    CharacterRigValidator,
)
from src.gameforge_ide.pipeline.character_pipeline import (
    CharacterPipeline,
)


@pytest.fixture
def valid_spec():
    return CharacterSpec(
        character_id="char_test_knight",
        name="KnightHero",
        purpose="Player Avatar for Action RPG",
        category="humanoid",
        height_cm=185.0,
        triangle_budget=30000,
        target_territory="GLOBAL",
    )


def test_character_spec_validation(valid_spec):
    assert valid_spec.name == "KnightHero"
    assert valid_spec.height_cm == 185.0
    assert valid_spec.get_destination_asset_name() == "SK_KnightHero"
    sha = valid_spec.compute_sha256()
    assert len(sha) == 64

    # Rejection of invalid height (< 30 cm)
    with pytest.raises(ValueError, match="height_cm"):
        CharacterSpec(
            character_id="bad_height",
            name="Tiny",
            purpose="Invalid",
            height_cm=10.0,
        )

    # Rejection of invalid category
    with pytest.raises(ValueError, match="category must be one of"):
        CharacterSpec(
            character_id="bad_cat",
            name="AlienShip",
            purpose="Invalid",
            category="starship",
        )

    # Rejection of empty name
    with pytest.raises(ValueError, match="name must not be empty"):
        CharacterSpec(
            character_id="bad_name",
            name="",
            purpose="Invalid",
        )


def test_procedural_skinned_character_generation(valid_spec):
    with tempfile.TemporaryDirectory() as td:
        gen = ProceduralSkinnedCharacterGenerator(output_dir=Path(td))
        bundle = gen.generate_humanoid(valid_spec)

        assert len(bundle.vertices) > 200, "Mesh should have substantial vertex density"
        assert len(bundle.triangles) > 300, "Mesh should have substantial triangle count"
        assert len(bundle.bones) == 20, "Humanoid should have 20 standard bones"

        # Check all UVs in [0.0, 1.0]
        for v in bundle.vertices:
            assert 0.0 <= v.uv[0] <= 1.0, f"UV U {v.uv[0]} out of bounds"
            assert 0.0 <= v.uv[1] <= 1.0, f"UV V {v.uv[1]} out of bounds"

        # Check export
        gltf_file = gen.export_gltf(bundle)
        assert gltf_file.exists()
        bin_file = gltf_file.with_suffix(".bin")
        assert bin_file.exists()

        with open(gltf_file, "r", encoding="utf-8") as f:
            gltf_data = json.load(f)

        assert "skins" in gltf_data
        assert "meshes" in gltf_data
        assert gltf_data["skins"][0]["joints"] == list(range(20))


def test_rig_hierarchy_validation():
    # Valid skeleton
    valid_bones = [
        BoneNode(0, "root", -1, (0, 0, 0), (0, 0, 90)),
        BoneNode(1, "pelvis", 0, (0, 0, 90), (0, 0, 110)),
        BoneNode(2, "spine_01", 1, (0, 0, 110), (0, 0, 130)),
        BoneNode(3, "spine_02", 2, (0, 0, 130), (0, 0, 150)),
        BoneNode(4, "neck", 3, (0, 0, 150), (0, 0, 160)),
        BoneNode(5, "head", 4, (0, 0, 160), (0, 0, 180)),
        BoneNode(6, "upperarm_l", 3, (-15, 0, 140), (-40, 0, 140)),
        BoneNode(7, "lowerarm_l", 6, (-40, 0, 140), (-65, 0, 140)),
        BoneNode(8, "thigh_l", 1, (-10, 0, 90), (-10, 0, 45)),
        BoneNode(9, "calf_l", 8, (-10, 0, 45), (-10, 0, 5)),
    ]
    ok, errs = CharacterRigValidator.validate_hierarchy(valid_bones, min_bones=10)
    assert ok is True, f"Valid hierarchy rejected: {errs}"

    # Too few bones
    ok_few, errs_few = CharacterRigValidator.validate_hierarchy(valid_bones[:5], min_bones=10)
    assert ok_few is False
    assert any("below minimum" in e for e in errs_few)

    # Invalid root bone name
    broken_root = list(valid_bones)
    broken_root[0] = BoneNode(0, "finger_tip", -1, (0, 0, 0), (0, 0, 10))
    ok_root, errs_root = CharacterRigValidator.validate_hierarchy(broken_root)
    assert ok_root is False
    assert any("must be one of: root, pelvis, hips" in e for e in errs_root)

    # Duplicate bone names
    dup_bones = list(valid_bones)
    dup_bones[2] = BoneNode(2, "pelvis", 0, (0, 0, 110), (0, 0, 130))
    ok_dup, errs_dup = CharacterRigValidator.validate_hierarchy(dup_bones)
    assert ok_dup is False
    assert any("Duplicate bone name" in e for e in errs_dup)


def test_skin_weights_partition_of_unity(valid_spec):
    with tempfile.TemporaryDirectory() as td:
        gen = ProceduralSkinnedCharacterGenerator(output_dir=Path(td))
        bundle = gen.generate_humanoid(valid_spec)

        # Validate weights on generated bundle
        w_ok, w_errs = CharacterRigValidator.validate_skin_weights(bundle.vertices, bundle.bones)
        assert w_ok is True, f"Weight validation failed: {w_errs}"

        # Test broken weights (sum != 1.0)
        broken_verts = list(bundle.vertices)
        broken_verts[0] = SkinnedVertex(
            position=broken_verts[0].position,
            normal=broken_verts[0].normal,
            uv=broken_verts[0].uv,
            bone_indices=(1, 2, 0, 0),
            bone_weights=(0.5, 0.2, 0.0, 0.0),  # sum = 0.7 != 1.0
        )
        b_ok, b_errs = CharacterRigValidator.validate_skin_weights(broken_verts, bundle.bones)
        assert b_ok is False
        assert any("violates partition of unity" in e for e in b_errs)


def test_forward_kinematics_joint_deformation(valid_spec):
    with tempfile.TemporaryDirectory() as td:
        gen = ProceduralSkinnedCharacterGenerator(output_dir=Path(td))
        bundle = gen.generate_humanoid(valid_spec)

        results = CharacterRigValidator.test_joint_rotations(bundle)
        assert len(results) == 3, "Expected 3 joint deformation stress tests"

        for r in results:
            assert r.passed is True, f"Joint test {r.joint_name} failed: {r.notes}"
            assert r.has_nan_or_inf is False
            assert r.bounding_box_valid is True
            assert r.max_displacement > 1.0, f"Expected non-trivial vertex displacement for {r.joint_name}"


def test_character_provenance_and_licensing(valid_spec):
    reg = LicenseRegistry()
    ok, err = reg.validate_territory_compliance("GameForge-ProceduralRig-V1", "US")
    assert ok is True

    ok_global, err_global = reg.validate_territory_compliance("GameForge-ProceduralRig-V1", "GLOBAL")
    assert ok_global is True

    rec = AssetProvenanceRecord(
        asset_id=valid_spec.character_id,
        asset_name=valid_spec.name,
        model_name="GameForge-ProceduralRig-V1",
        model_version="1.0.0",
        license_name="CC-BY-4.0",
        target_territory=valid_spec.target_territory,
        input_hashes={"spec_sha256": valid_spec.compute_sha256()},
        parameters=valid_spec.model_dump(),
    )
    seal = rec.seal()
    assert len(seal) == 64
    assert rec.provenance_hash == seal


def test_character_pipeline_broken_asset_rejection():
    # CharacterSpec with degenerate budgets
    with pytest.raises(ValueError):
        CharacterSpec(
            character_id="broken_char",
            name="Broken",
            purpose="Negative Budget Test",
            triangle_budget=-50,
        )


def test_gltf_export_is_a_valid_skinned_hierarchy(valid_spec, tmp_path):
    """Audit 2026-10-30: the exported glTF must carry a real joint tree, parent-relative joint
    translations, inverse bind matrices and glTF units/axes (metres, Y-up)."""
    import struct
    gen = ProceduralSkinnedCharacterGenerator(output_dir=tmp_path)
    bundle = gen.generate_humanoid(valid_spec)
    gltf_path = gen.export_gltf(bundle)
    g = json.loads(gltf_path.read_text(encoding="utf-8"))
    nodes = g["nodes"]
    skin = g["skins"][0]
    joints = skin["joints"]

    # One scene root joint ("root") plus the mesh node; every other joint is reachable via children.
    scene_roots = g["scenes"][0]["nodes"]
    assert [nodes[i]["name"] for i in scene_roots] == ["root", valid_spec.name]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            assert c not in parent, "a joint has two parents"
            parent[c] = i
    assert set(parent) == set(joints) - {scene_roots[0]}

    # World translation = sum of local translations up the chain; it must match the bone head.
    def world(i):
        t = nodes[i]["translation"]
        if i in parent:
            pw = world(parent[i])
            return [t[k] + pw[k] for k in range(3)]
        return list(t)

    for i, bone in enumerate(bundle.bones):
        hx, hy, hz = bone.head_pos
        assert world(i) == pytest.approx([hx / 100.0, hz / 100.0, hy / 100.0], abs=1e-6)

    # Inverse bind matrices invert each joint's world transform.
    acc = g["accessors"][skin["inverseBindMatrices"]]
    view = g["bufferViews"][acc["bufferView"]]
    blob = (tmp_path / g["buffers"][0]["uri"]).read_bytes()
    assert acc["type"] == "MAT4" and acc["count"] == len(joints)
    for j in range(len(joints)):
        m = struct.unpack_from("<16f", blob, view["byteOffset"] + j * 64)
        assert [m[12], m[13], m[14]] == pytest.approx([-v for v in world(j)], abs=1e-5)
        assert m[15] == 1.0 and m[0] == m[5] == m[10] == 1.0

    # glTF is metres and Y-up: the character stands ~1.85 m tall along +Y.
    pos = g["accessors"][0]
    assert pos["max"][1] == pytest.approx(valid_spec.height_cm / 100.0, rel=0.08)
    assert pos["max"][1] - pos["min"][1] > 1.5
    assert pos["max"][2] - pos["min"][2] < 1.0


def test_character_pipeline_registers_asset_and_reports_engine_gates_honestly(valid_spec, tmp_path):
    """Roadmap WP-A 4b: the run lands in the asset registry, and gates it never ran are not reported as passed."""
    pipeline = CharacterPipeline(workspace_dir=tmp_path, output_dir=tmp_path / "chars")
    result = pipeline.run_pipeline(valid_spec)
    assert result.success and result.rig_validation_passed
    assert not (result.unreal_import_passed or result.inspection_passed or result.promotion_passed)
    assert result.skeletal_mesh_path == "" and result.diagnostics["unreal_stages"] == "NOT_PERFORMED"
    row = pipeline.asset_registry.get(result.diagnostics["registry_id"])
    assert row["asset_type"] == "skeletal_mesh" and row["provenance"] == "procedural"
    assert row["stage"] == "VALIDATE"
    assert [e["stage"] for e in pipeline.asset_registry.history(row["asset_id"])] == ["SPEC", "GENERATE", "VALIDATE"]
    assert pipeline.asset_registry.artifact_unchanged(row["asset_id"])
