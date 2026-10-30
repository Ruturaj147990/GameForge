"""Quarantine Import & 8-Stage Gated Asset Pipeline for GameForge IDE.

Compliant with GameForge Master Blueprint:
- Stages 1-8 execution and gate checks.
- Staged quarantine staging in /Game/Quarantine/<asset_id>/.
- Provenance tracking with SHA-256 hashes and territory compliance.
- Advisory human review gate before promotion to /Game/Props/.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..assets import AssetRecord, AssetRegistry
from ..models.provenance import AssetProvenanceRecord, LicenseRegistry
from ...unreal.op_result import OperationResult
from ...unreal.snapshot import SnapshotManager
from .asset_tools import AssetSpec, GeometryValidationResult, ProceduralMeshGenerator


# The only generator this pipeline actually runs. Provenance must name it; recording a neural model here
# (e.g. TRELLIS.2) while ProceduralMeshGenerator produced the mesh would be false provenance.
PROCEDURAL_GENERATOR = "GameForge-Procedural"


class QuarantinePipeline:
    """Orchestrates 8-stage multimodal asset pipeline with quarantine and human review."""

    def __init__(
        self,
        workspace_root: Path,
        operations: Any = None,
        snapshot_manager: Optional[SnapshotManager] = None,
        license_registry: Optional[LicenseRegistry] = None,
        asset_registry: Optional[AssetRegistry] = None,
    ):
        self.workspace_root = workspace_root.resolve()
        self.snapshot_mgr = snapshot_manager or SnapshotManager(self.workspace_root)
        if operations is None:
            raise ValueError("QuarantinePipeline needs an editor operations backend "
                             "(unreal.live_operations.LiveOperations in production)")
        self.operations = operations
        self.license_reg = license_registry or LicenseRegistry()
        self.asset_registry = asset_registry or AssetRegistry(self.workspace_root)
        self.mesh_generator = ProceduralMeshGenerator(self.workspace_root / "Saved" / "GeneratedAssets")
        self.session_token = self.operations.security.get_session_token()

    def _run_sync(self, coro_or_val: Any) -> Any:
        """Executes a coroutine safely in synchronous callers."""
        if not asyncio.iscoroutine(coro_or_val):
            return coro_or_val
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    return executor.submit(asyncio.run, coro_or_val).result()
            else:
                return loop.run_until_complete(coro_or_val)
        except RuntimeError:
            return asyncio.run(coro_or_val)

    def _res_ok(self, res: Any) -> bool:
        if hasattr(res, "ok"):
            return bool(res.ok)
        if isinstance(res, dict):
            return bool(res.get("ok"))
        return False

    def _res_errors(self, res: Any) -> List[str]:
        if hasattr(res, "errors"):
            return list(res.errors)
        if isinstance(res, dict):
            return list(res.get("errors", []))
        return []

    def _res_data(self, res: Any) -> Dict[str, Any]:
        if hasattr(res, "data"):
            return res.data or {}
        if isinstance(res, dict):
            return res.get("data", res)
        return {}

    def execute_pipeline(
        self,
        spec: AssetSpec,
        model_name: str = PROCEDURAL_GENERATOR,
        model_version: str = "1.0",
        seed: int = 42,
        concept_prompt: Optional[str] = None,
        human_approval: bool = False,
        target_destination: str = "/Game/Props",
    ) -> Dict[str, Any]:
        """Executes Stages 1 through 8 of the multimodal pipeline."""
        asset_id = f"asset-{uuid.uuid4().hex[:8]}"
        gate_results: Dict[str, Any] = {}
        quarantine_folder = f"/Game/Quarantine/{asset_id}"
        quarantine_asset_path = f"{quarantine_folder}/{spec.name}"
        final_asset_path = f"{target_destination}/{spec.name}"

        # Track input hashes
        input_data = f"{spec.model_dump_json()}:{concept_prompt or ''}:{seed}"
        prompt_hash = hashlib.sha256(input_data.encode("utf-8")).hexdigest()

        # ==========================================
        # STAGE 1: SPEC VALIDATION
        # ==========================================
        stage1_ok = True
        stage1_errors = []
        if spec.triangle_budget < 4:
            stage1_ok = False
            stage1_errors.append("Triangle budget too low")
        gate_results["stage_1_spec"] = {
            "passed": stage1_ok,
            "spec": spec.model_dump(),
            "errors": stage1_errors,
        }
        if not stage1_ok:
            return {"ok": False, "stage": 1, "error": "STAGE_1_FAILED: Spec validation failed", "gate_results": gate_results}

        # ==========================================
        # STAGE 2: CONCEPT (OPTIONAL)
        # ==========================================
        gate_results["stage_2_concept"] = {
            "passed": True,
            "concept_prompt": concept_prompt or "N/A",
            "prompt_hash": prompt_hash,
        }

        lic_record = self.license_reg.get_license(model_name)
        registry_id = self.asset_registry.register(AssetRecord(
            name=spec.name, asset_type="mesh", purpose=spec.purpose, provenance="procedural",
            backend=model_name, backend_version=model_version,
            license=lic_record.license_name if lic_record else "unrecorded",
            spec={**spec.model_dump(), "seed": seed, "concept_prompt": concept_prompt}))
        self.asset_registry.advance(registry_id, "SPEC", True, "spec validated")

        # ==========================================
        # STAGE 3: GENERATE (LICENSE & TERRITORY CHECK)
        # ==========================================
        if model_name != PROCEDURAL_GENERATOR:
            error = (f"MODEL_NOT_WIRED: {model_name} has no generation backend in this pipeline; "
                     f"only {PROCEDURAL_GENERATOR} runs here")
            gate_results["stage_3_generate"] = {"passed": False, "error": error, "model": model_name}
            self.asset_registry.advance(registry_id, "GENERATE", False, error)
            return {"ok": False, "stage": 3, "error": f"STAGE_3_BLOCKED: {error}", "gate_results": gate_results}

        compliant, territory_err = self.license_reg.validate_territory_compliance(
            model_name=model_name, target_territory=spec.target_territory
        )
        if not compliant:
            gate_results["stage_3_generate"] = {
                "passed": False,
                "error": territory_err,
                "model": model_name,
            }
            return {
                "ok": False,
                "stage": 3,
                "error": f"STAGE_3_BLOCKED: {territory_err}",
                "gate_results": gate_results,
            }

        # Generate mesh
        gen_result = self.mesh_generator.generate_from_spec(spec, subfolder=f"quarantine/{asset_id}")
        obj_file = Path(gen_result["obj_file"])
        obj_sha = gen_result["sha256"]

        gate_results["stage_3_generate"] = {
            "passed": True,
            "model": model_name,
            "version": model_version,
            "seed": seed,
            "artifact_sha256": obj_sha,
        }
        self.asset_registry.advance(registry_id, "GENERATE", True, artifact_path=str(obj_file))

        # ==========================================
        # STAGE 4: POST-PROCESS & GEOMETRY VALIDATION
        # ==========================================
        geo_result = self.mesh_generator.validate_geometry_and_uvs(obj_file, spec=spec)
        gate_results["stage_4_postprocess"] = {
            "passed": geo_result.valid,
            "triangle_count": geo_result.triangle_count,
            "uvs_in_bounds": geo_result.uvs_in_bounds,
            "is_watertight": geo_result.is_watertight,
            "bounding_box_within_spec": geo_result.bounding_box_within_spec,
            "errors": geo_result.errors,
        }
        self.asset_registry.advance(registry_id, "VALIDATE", geo_result.valid, "; ".join(geo_result.errors))
        if not geo_result.valid:
            return {
                "ok": False,
                "stage": 4,
                "error": f"STAGE_4_FAILED: Geometry validation errors: {geo_result.errors}",
                "gate_results": gate_results,
            }

        # ==========================================
        # STAGE 5: QUARANTINE IMPORT
        # ==========================================
        import_res = self._run_sync(
            self.operations.import_asset(
                source_file=str(obj_file),
                destination_path=quarantine_folder,
                asset_class="StaticMesh",
                token=self.session_token,
            )
        )
        import_ok = self._res_ok(import_res)
        gate_results["stage_5_import"] = {
            "passed": import_ok,
            "quarantine_path": quarantine_asset_path,
            "errors": self._res_errors(import_res),
        }
        self.asset_registry.advance(registry_id, "QUARANTINE", import_ok, "; ".join(self._res_errors(import_res)),
                                    unreal_path=quarantine_asset_path if import_ok else None)
        if not import_ok:
            return {
                "ok": False,
                "stage": 5,
                "error": f"STAGE_5_FAILED: Import to quarantine failed: {self._res_errors(import_res)}",
                "gate_results": gate_results,
            }

        # ==========================================
        # STAGE 6: ENGINE CHECKS (TEST LEVEL SPAWN & BOUNDS)
        # ==========================================
        test_level = "/Game/Maps/Test_AssetQuarantine"
        spawn_res = self._run_sync(
            self.operations.spawn_actor(
                actor_class="StaticMeshActor",
                label=f"Preview_{spec.name}",
                location={"x": 0, "y": 0, "z": 50},
                level_path=test_level,
                token=self.session_token,
            )
        )
        spawn_ok = self._res_ok(spawn_res)
        gate_results["stage_6_engine_checks"] = {
            "passed": spawn_ok,
            "spawn_actor": self._res_data(spawn_res).get("actor_label"),
            "collision_configured": spec.collision_type != "none",
        }
        self.asset_registry.advance(registry_id, "ENGINE_VERIFY", spawn_ok, "preview actor spawn in test level")

        # ==========================================
        # STAGE 7: HUMAN REVIEW GATE
        # ==========================================
        advisory_description = (
            f"Advisory Vision Summary: {spec.name} is a {spec.purpose} with {geo_result.triangle_count} triangles. "
            f"Collision: {spec.collision_type}. UVs: Valid. Manifold: {geo_result.is_watertight}."
        )
        gate_results["stage_7_review"] = {
            "advisory_description": advisory_description,
            "human_approved": human_approval,
        }

        # Build complete Provenance Record up to review gate
        provenance = AssetProvenanceRecord(
            asset_id=asset_id,
            asset_name=spec.name,
            model_name=model_name,
            model_version=model_version,
            license_name=lic_record.license_name if lic_record else "Custom",
            territory_flags=lic_record.excluded_territories if lic_record else [],
            target_territory=spec.target_territory,
            input_hashes={"spec_hash": prompt_hash},
            parameters=spec.model_dump(),
            seed=seed,
            tool_versions={"ProceduralGenerator": "1.0", "UnrealInterchange": "5.7.4"},
            output_hashes={"obj": obj_sha},
            gate_results=gate_results,
        )
        prov_file = obj_file.parent / f"{spec.name}.provenance.json"
        provenance.save_to_file(prov_file)

        if not human_approval:
            return {
                "ok": True,
                "status": "WAITING_REVIEW",
                "asset_id": asset_id,
                "registry_id": registry_id,
                "current_path": quarantine_asset_path,
                "advisory": advisory_description,
                "provenance_file": str(prov_file),
                "gate_results": gate_results,
            }

        # ==========================================
        # STAGE 8: PROMOTION
        # ==========================================
        promote_res = self._run_sync(
            self.operations.promote_quarantined_asset(
                quarantine_path=quarantine_asset_path,
                approved_path=final_asset_path,
                token=self.session_token,
            )
        )
        promote_ok = self._res_ok(promote_res)
        gate_results["stage_8_promote"] = {
            "passed": promote_ok,
            "promoted_path": final_asset_path,
            "errors": self._res_errors(promote_res),
        }
        if spawn_ok:
            self.asset_registry.advance(registry_id, "PROMOTE", promote_ok, "; ".join(self._res_errors(promote_res)),
                                        unreal_path=final_asset_path if promote_ok else None)

        # Update and reseal provenance record
        provenance.gate_results = gate_results
        provenance.save_to_file(prov_file)

        return {
            "ok": promote_ok,
            "status": "PROMOTED" if promote_ok else "PROMOTION_FAILED",
            "asset_id": asset_id,
            "registry_id": registry_id,
            "final_path": final_asset_path,
            "provenance_file": str(prov_file),
            "provenance_hash": provenance.provenance_hash,
            "gate_results": gate_results,
        }
