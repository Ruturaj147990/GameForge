"""Phase 4 Verification Suite — End-to-End Multimodal Asset Generation Pipeline.

Verifies conformance with GameForge Master Blueprint:
- REQ-040: Structured Asset Specification Validation
- REQ-041: Procedural 3D Mesh & Material Generation
- REQ-042: Mesh Geometry, UV, & Collision Bounds Validation
- REQ-043: Quarantine Import Workflow
- REQ-044: Asset Provenance & License Tracking
- REQ-045: Visual Human Review & Promotion Gate
"""

import os
import tempfile
import pytest
from pathlib import Path

from src.gameforge_ide.backend.models.provenance import (
    AssetProvenanceRecord,
    LicenseRecord,
    LicenseRegistry,
)
from src.gameforge_ide.backend.tools.asset_tools import (
    AssetSpec,
    GeometryValidationResult,
    ProceduralMeshGenerator,
)
from src.gameforge_ide.backend.tools.gpu_scheduler import (
    GPUScheduler,
    GPUServiceContract,
    GPUWorkloadType,
)
from src.gameforge_ide.backend.tools.quarantine import QuarantinePipeline
from tests.doubles.operations import UnrealOperationsLibrary


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        (root / "Saved" / "GeneratedAssets").mkdir(parents=True, exist_ok=True)
        yield root


def test_stage1_spec_validation():
    """REQ-040: Verify structured asset specification validation."""
    # Valid spec
    spec = AssetSpec(
        name="SM_HealthCrate",
        purpose="Interactive Health Pick-up Prop",
        size_cm=(50.0, 50.0, 40.0),
        triangle_budget=2000,
        collision_type="box",
        lod_count=3,
        material_type="PBR_Standard",
        target_territory="GLOBAL",
    )
    assert spec.name == "SM_HealthCrate"
    assert spec.size_cm == (50.0, 50.0, 40.0)

    # Invalid dimension <= 0
    with pytest.raises(ValueError):
        AssetSpec(
            name="SM_Bad",
            purpose="Bad Dimensions",
            size_cm=(50.0, -10.0, 40.0),
        )

    # Invalid triangle budget < 4
    with pytest.raises(ValueError):
        AssetSpec(
            name="SM_BadBudget",
            purpose="Degenerate Mesh",
            triangle_budget=2,
        )

    # Invalid collision type
    with pytest.raises(ValueError):
        AssetSpec(
            name="SM_BadCollision",
            purpose="Invalid Collision",
            collision_type="unsupported_shape",
        )


def test_stage3_license_territory_refusal():
    """REQ-044: Verify license registry and territory distribution compliance."""
    reg = LicenseRegistry()

    # Hunyuan 3D 2.1 Community License excludes EU, UK, KR
    ok_us, err_us = reg.validate_territory_compliance("Hunyuan3D-2.1", "US")
    assert ok_us is True
    assert err_us is None

    # EU distribution must be refused
    ok_eu, err_eu = reg.validate_territory_compliance("Hunyuan3D-2.1", "EU")
    assert ok_eu is False
    assert "LICENCE_TERRITORY_CONFLICT" in err_eu
    assert "excludes target territory 'EU'" in err_eu

    # UK distribution must be refused
    ok_uk, err_uk = reg.validate_territory_compliance("Hunyuan3D-2.1", "UK")
    assert ok_uk is False
    assert "LICENCE_TERRITORY_CONFLICT" in err_uk

    # KR distribution must be refused
    ok_kr, err_kr = reg.validate_territory_compliance("Hunyuan3D-2.1", "KR")
    assert ok_kr is False

    # GLOBAL distribution must be refused for models with excluded territories
    ok_global, err_global = reg.validate_territory_compliance("Hunyuan3D-2.1", "GLOBAL")
    assert ok_global is False
    assert "cannot be used for GLOBAL distribution" in err_global

    # MIT model (TRELLIS.2) allows GLOBAL distribution
    ok_trellis, err_trellis = reg.validate_territory_compliance("TRELLIS.2", "GLOBAL")
    assert ok_trellis is True
    assert err_trellis is None


def test_stage4_geometry_uv_validation(temp_workspace):
    """REQ-041 & REQ-042: Procedural mesh generation, UV bounds [0, 1], and manifold checks."""
    generator = ProceduralMeshGenerator(temp_workspace / "Generated")
    spec = AssetSpec(
        name="SM_TestChest",
        purpose="Storage chest",
        size_cm=(80.0, 60.0, 50.0),
        triangle_budget=500,
        collision_type="box",
    )

    res = generator.generate_from_spec(spec)
    assert res["status"] == "SUCCESS"
    assert Path(res["obj_file"]).exists()
    assert Path(res["mtl_file"]).exists()

    # Validate geometry
    geo = generator.validate_geometry_and_uvs(res["obj_file"], spec=spec)
    assert geo.valid is True
    assert geo.triangle_count == 12
    assert geo.uvs_in_bounds is True
    assert geo.is_watertight is True
    assert geo.bounding_box_within_spec is True
    assert len(geo.errors) == 0


def test_gpu_scheduler_serial_lock():
    """Verify GPU scheduler enforces single heavy workload at a time."""
    sched = GPUScheduler(vram_capacity_mb=12288)

    # 1. Acquire for LLM inference
    acq1 = sched.acquire(GPUWorkloadType.LLM_INFERENCE, owner_id="agent-turn-1", timeout_seconds=1.0)
    assert acq1 is True

    state = sched.get_state()
    assert state.active_workload == GPUWorkloadType.LLM_INFERENCE
    assert state.active_owner == "agent-turn-1"

    # 2. Competing asset generation attempt should time out
    acq2 = sched.acquire(GPUWorkloadType.ASSET_GENERATION, owner_id="asset-job-1", timeout_seconds=0.2)
    assert acq2 is False

    # 3. Release LLM inference
    rel = sched.release("agent-turn-1")
    assert rel is True

    # 4. Now asset generation can acquire
    acq3 = sched.acquire(GPUWorkloadType.ASSET_GENERATION, owner_id="asset-job-1", timeout_seconds=1.0)
    assert acq3 is True
    assert sched.get_state().active_workload == GPUWorkloadType.ASSET_GENERATION

    sched.release("asset-job-1")
    assert sched.get_state().active_workload is None


def test_gpu_service_contract_idempotency_and_auth():
    """Verify GPU Service Contract endpoints, authentication token, and input hash caching."""
    service = GPUServiceContract(auth_token="secret-token-123")

    # Unauthorized call rejected
    unauth = service.generate("a wooden crate", token="wrong-token")
    assert unauth["ok"] is False
    assert "UNAUTHORIZED" in unauth["error"]

    # Authorized call succeeds
    res1 = service.generate("a wooden crate", token="secret-token-123", seed=100)
    assert res1["ok"] is True
    assert res1["cached"] is False
    job_id = res1["job_id"]
    input_hash = res1["input_hash"]

    # Duplicate call is idempotent and returns cached result
    res2 = service.generate("a wooden crate", token="secret-token-123", seed=100)
    assert res2["ok"] is True
    assert res2["cached"] is True
    assert res2["job_id"] == job_id
    assert res2["input_hash"] == input_hash


def test_quarantine_pipeline_waiting_review(temp_workspace):
    """REQ-043 & REQ-045: Staging in quarantine and waiting for human review."""
    pipeline = QuarantinePipeline(workspace_root=temp_workspace, operations=UnrealOperationsLibrary(temp_workspace))
    spec = AssetSpec(
        name="SM_MilitaryCrate",
        purpose="Ammunition prop",
        size_cm=(60.0, 40.0, 40.0),
        triangle_budget=1000,
        collision_type="box",
        target_territory="GLOBAL",
    )

    # Run without human approval
    res = pipeline.execute_pipeline(
        spec=spec,
        model_name="TRELLIS.2",
        human_approval=False,
    )

    assert res["ok"] is True
    assert res["status"] == "WAITING_REVIEW"
    assert "/Game/Quarantine/" in res["current_path"]
    assert "Advisory Vision Summary" in res["advisory"]
    assert Path(res["provenance_file"]).exists()

    # Read back quarantine asset in operations library
    exists = pipeline.operations.asset_exists(res["current_path"])
    assert exists["exists"] is True


def test_quarantine_pipeline_promotion_on_approval(temp_workspace):
    """REQ-043, REQ-044, REQ-045: Full 8-stage pipeline ending in promotion and verified read-back."""
    pipeline = QuarantinePipeline(workspace_root=temp_workspace, operations=UnrealOperationsLibrary(temp_workspace))
    spec = AssetSpec(
        name="SM_PromotedChest",
        purpose="Loot container",
        size_cm=(100.0, 80.0, 60.0),
        triangle_budget=1500,
        collision_type="box",
        target_territory="GLOBAL",
    )

    # Run with human approval
    res = pipeline.execute_pipeline(
        spec=spec,
        model_name="TRELLIS.2",
        human_approval=True,
        target_destination="/Game/Props",
    )

    assert res["ok"] is True
    assert res["status"] == "PROMOTED"
    assert res["final_path"] == "/Game/Props/SM_PromotedChest"
    assert res["provenance_hash"] is not None

    # Read-back verification (Rule 7)
    readback = pipeline.operations.asset_exists("/Game/Props/SM_PromotedChest", asset_class="StaticMesh")
    assert readback["exists"] is True
    assert readback["class_match"] is True

    # Quarantine path should no longer exist
    quarantine_check = pipeline.operations.asset_exists(f"/Game/Quarantine/{res['asset_id']}/SM_PromotedChest")
    assert quarantine_check["exists"] is False
