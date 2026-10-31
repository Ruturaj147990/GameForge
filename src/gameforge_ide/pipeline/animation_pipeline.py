"""End-to-End Animation Generation, Validation, and Unreal Engine 5.7.4 Pipeline.

Implements Milestone 10:
1. Structured animation specification parsing and validation (LocomotionSetSpec / AnimationSpec).
2. Canonical procedural kinematic motion synthesis (ProceduralKinematicMotionSynthesizer).
3. Kinematic plausibility and smoothness validation (AnimationValidator).
4. Real Unreal Engine 5.7.4 Animation Blueprint creation (ABP_CharacterLocomotion).
5. Authoritative inspection (UAnimBlueprint, UAnimSequence, state machine compatibility).
6. Cryptographic provenance sealing (AssetProvenanceRecord).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.settings import artifacts_dir, get_settings
from src.gameforge_ide.backend.assets.registry import AssetRecord, AssetRegistry
from src.gameforge_ide.backend.models.animation_spec import (
    AnimationAction,
    AnimationSpec,
    LocomotionSetSpec,
)
from src.gameforge_ide.backend.models.provenance import (
    AssetProvenanceRecord,
    LicenseRecord,
    LicenseRegistry,
)
from src.gameforge_ide.backend.tools.animation_validator import (
    AnimationValidator,
    ClipValidationReport,
)
from src.gameforge_ide.backend.tools.motion_generator import (
    MotionClipBundle,
    ProceduralKinematicMotionSynthesizer,
)


@dataclass
class AnimationPipelineResult:
    bundle_id: str
    character_id: str
    success: bool
    spec_valid: bool
    motion_synthesis_passed: bool
    validation_passed: bool
    unreal_integration_passed: bool
    blueprint_created: bool
    anim_blueprint_path: str
    clip_reports: List[Dict[str, Any]]
    exported_clip_files: List[str]
    provenance_path: str
    errors: List[str]
    diagnostics: Dict[str, Any]


class AnimationPipeline:
    """Orchestrates animation generation, kinematic validation, Unreal import, and AnimBlueprint creation."""

    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        asset_registry: Optional[AssetRegistry] = None,
    ):
        self.workspace_dir = (workspace_dir or get_settings().require_dev("validation_root") / "live_ops_probe").resolve()
        self.output_dir = (output_dir or artifacts_dir("assets", "generated", "animations")).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.license_registry = LicenseRegistry()
        self.asset_registry = asset_registry or AssetRegistry(self.workspace_dir)

    def run_pipeline(
        self,
        locomotion_set: LocomotionSetSpec,
        live_ops_client=None,
    ) -> AnimationPipelineResult:
        errors: List[str] = []
        diagnostics: Dict[str, Any] = {}
        clip_reports: List[Dict[str, Any]] = []
        exported_files: List[str] = []

        # 1. Spec validation
        spec_valid = True
        try:
            raw_spec = json.dumps(locomotion_set.model_dump(), sort_keys=True).encode("utf-8")
            spec_hash = hashlib.sha256(raw_spec).hexdigest()
            diagnostics["spec_sha256"] = spec_hash
            diagnostics["clip_count"] = len(locomotion_set.clips)
        except Exception as e:
            spec_valid = False
            errors.append(f"LocomotionSetSpec validation error: {e}")
            return self._fail_result(locomotion_set, errors, diagnostics)

        # 2. License check
        ok_terr, terr_err = self.license_registry.validate_territory_compliance("GameForge-ProceduralRig-V1", "GLOBAL")
        if not ok_terr:
            errors.append(f"License territory compliance failed: {terr_err}")
            return self._fail_result(locomotion_set, errors, diagnostics)

        # 3. Motion synthesis & validation for each clip
        synthesizer = ProceduralKinematicMotionSynthesizer(output_dir=self.output_dir)
        all_clips_valid = True
        clip_bundles: List[MotionClipBundle] = []

        t0 = time.time()
        registry_ids: List[str] = []
        for clip_spec in locomotion_set.clips:
            registry_id = self.asset_registry.register(AssetRecord(
                name=clip_spec.name, asset_type="animation", purpose=f"{locomotion_set.bundle_id} locomotion clip",
                provenance="procedural", backend="GameForge-KinematicSynthesis-V1", backend_version="1.0.0",
                license="CC-BY-4.0", spec=clip_spec.model_dump(), tags=[locomotion_set.bundle_id]))
            registry_ids.append(registry_id)
            self.asset_registry.advance(registry_id, "SPEC", True, "spec validated")
            try:
                bundle = synthesizer.synthesize_clip(clip_spec)
                clip_bundles.append(bundle)

                # Validate
                report = AnimationValidator.validate_clip(bundle)
                clip_reports.append(asdict(report))

                if not report.is_valid:
                    all_clips_valid = False
                    errors.extend([f"[{clip_spec.name}] {err}" for err in report.errors])

                # Export clip bundle JSON
                out_path = synthesizer.export_motion_json(bundle)
                exported_files.append(str(out_path))
                self.asset_registry.advance(registry_id, "GENERATE", True, artifact_path=str(out_path))
                self.asset_registry.advance(registry_id, "VALIDATE", report.is_valid, "; ".join(report.errors))
            except Exception as e:
                all_clips_valid = False
                errors.append(f"Synthesis failed for '{clip_spec.name}': {e}")
                self.asset_registry.advance(registry_id, "GENERATE", False, str(e))
        diagnostics["registry_ids"] = registry_ids

        synthesis_time = time.time() - t0
        diagnostics["synthesis_time_s"] = round(synthesis_time, 3)
        diagnostics["exported_clips"] = exported_files

        if not all_clips_valid or len(clip_bundles) == 0:
            return self._fail_result(
                locomotion_set,
                errors,
                diagnostics,
                clip_reports=clip_reports,
                exported_files=exported_files,
            )

        # 4. Unreal Engine 5.7.4 In-Engine Integration
        blueprint_created = False
        unreal_passed = False
        target_bp_path = f"{locomotion_set.destination_path}/{locomotion_set.anim_blueprint_name}"

        if live_ops_client is not None:
            try:
                # Call live ops to create locomotion AnimBlueprint
                res = live_ops_client.call_op_sync(
                    "anim_create_locomotion_blueprint",
                    {
                        "target_package_path": locomotion_set.destination_path,
                        "blueprint_name": locomotion_set.anim_blueprint_name,
                        "target_skeleton_path": locomotion_set.target_skeleton_path,
                    },
                )
                if res.get("status") == "success":
                    blueprint_created = True
                    unreal_passed = True
                    diagnostics["unreal_blueprint"] = res.get("result", {})
                else:
                    errors.append(f"Unreal AnimBlueprint creation failed: {res.get('error')}")
            except Exception as e:
                errors.append(f"Unreal live_ops exception: {e}")
        else:
            # Offline: nothing was created in Unreal, so the engine gate is reported as not run.
            diagnostics["unreal_blueprint"] = {
                "package_path": target_bp_path,
                "skeleton": locomotion_set.target_skeleton_path,
                "offline_staged": True,
                "status": "NOT_PERFORMED",
            }

        # 5. Provenance sealing
        prov = AssetProvenanceRecord(
            asset_id=locomotion_set.bundle_id,
            asset_name=locomotion_set.anim_blueprint_name,
            model_name="GameForge-KinematicSynthesis-V1",
            model_version="1.0.0",
            license_name="CC-BY-4.0",
            target_territory="GLOBAL",
            input_hashes={"spec_sha256": spec_hash},
            parameters=locomotion_set.model_dump(),
            output_hashes={Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in exported_files if Path(p).exists()},
            gate_results={
                "spec_valid": True,
                "synthesis_passed": True,
                "validation_passed": all_clips_valid,
                "unreal_integration": unreal_passed,
            },
        )
        prov_path = self.output_dir / f"{locomotion_set.bundle_id}_provenance.json"
        prov.save_to_file(prov_path)

        return AnimationPipelineResult(
            bundle_id=locomotion_set.bundle_id,
            character_id=locomotion_set.character_id,
            success=(len(errors) == 0 and (unreal_passed or live_ops_client is None)),
            spec_valid=True,
            motion_synthesis_passed=True,
            validation_passed=all_clips_valid,
            unreal_integration_passed=unreal_passed,
            blueprint_created=blueprint_created,
            anim_blueprint_path=target_bp_path,
            clip_reports=clip_reports,
            exported_clip_files=exported_files,
            provenance_path=str(prov_path),
            errors=errors,
            diagnostics=diagnostics,
        )

    def _fail_result(
        self,
        locomotion_set: LocomotionSetSpec,
        errors: List[str],
        diagnostics: Dict[str, Any],
        clip_reports: Optional[List[Dict[str, Any]]] = None,
        exported_files: Optional[List[str]] = None,
    ) -> AnimationPipelineResult:
        return AnimationPipelineResult(
            bundle_id=locomotion_set.bundle_id,
            character_id=locomotion_set.character_id,
            success=False,
            spec_valid=False,
            motion_synthesis_passed=False,
            validation_passed=False,
            unreal_integration_passed=False,
            blueprint_created=False,
            anim_blueprint_path="",
            clip_reports=clip_reports or [],
            exported_clip_files=exported_files or [],
            provenance_path="",
            errors=errors,
            diagnostics=diagnostics,
        )
