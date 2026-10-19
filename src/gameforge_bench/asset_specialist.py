"""Asset Specialist Interface and Provider Contract Boundary for GameForge (Step 7).

Implements Section 5.4, 28.4, 28.8 and Requirement R-1:
"I want the LLM to be world class only focusing on game development,
with the other 3d models for generating."

This module defines typed provider contracts and validation boundaries so the core
GameForge LLM orchestrates 3D mesh, texture, rigging, animation, and audio generation
through explicit interfaces, distinguishing raw generated artifacts from
engine-imported, rigged, runtime-tested, and accepted assets.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class AssetModality(str, Enum):
    MESH_3D = "mesh_3d"
    TEXTURE = "texture"
    RIGGING = "rigging"
    ANIMATION = "animation"
    AUDIO = "audio"
    VISION_QA = "vision_qa"


class SpecialistStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    IN_PROGRESS = "IN_PROGRESS"
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class EngineIntegrationStatus(str, Enum):
    UNPROCESSED = "UNPROCESSED"
    IMPORTED = "IMPORTED"
    RIGGED = "RIGGED"
    RUNTIME_TESTED = "RUNTIME_TESTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass
class SpecialistProvider:
    provider_id: str
    model_name: str
    revision: str
    endpoint_or_command: str = ""
    is_available: bool = False
    is_test_double: bool = False
    notes: Optional[str] = None


@dataclass
class AssetConstraints:
    max_triangles: Optional[int] = None
    max_texture_dimension: Optional[int] = None
    target_engine: str = "unreal"
    target_engine_version: str = "5.7.4"
    skeleton_preset: Optional[str] = None
    animation_framerate: Optional[float] = 30.0


@dataclass
class AssetProvenance:
    license_id: str
    rights_holder: str
    rights_cleared: bool = False
    evidence_reference: Optional[str] = None


@dataclass
class AssetGenerationRequest:
    task_id: str
    modality: AssetModality
    prompt: str
    target_format: str
    destination_path: str
    constraints: AssetConstraints = field(default_factory=AssetConstraints)
    provenance: Optional[AssetProvenance] = None


@dataclass
class AssetGenerationResult:
    artifact_path: Optional[str] = None
    artifact_sha256: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


@dataclass
class AssetSpecialistJob:
    job_id: str
    modality: AssetModality
    provider: SpecialistProvider
    request: AssetGenerationRequest
    status: SpecialistStatus = SpecialistStatus.SUBMITTED
    engine_integration_status: EngineIntegrationStatus = EngineIntegrationStatus.UNPROCESSED
    result: Optional[AssetGenerationResult] = None
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "modality": self.modality.value,
            "provider": asdict(self.provider),
            "request": {
                "task_id": self.request.task_id,
                "modality": self.request.modality.value,
                "prompt": self.request.prompt,
                "target_format": self.request.target_format,
                "destination_path": self.request.destination_path,
                "constraints": asdict(self.request.constraints),
                "provenance": asdict(self.request.provenance) if self.request.provenance else None,
            },
            "status": self.status.value,
            "engine_integration_status": self.engine_integration_status.value,
            "result": asdict(self.result) if self.result else None,
            "validation_errors": self.validation_errors,
        }


class AssetSpecialistRouter:
    """Manages registered asset specialists and enforces verification boundaries."""

    def __init__(self, workspace_root: Optional[Path] = None, allow_test_doubles: bool = False) -> None:
        self.registered_providers: Dict[str, SpecialistProvider] = {}
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        self.allow_test_doubles = allow_test_doubles

    def register_provider(self, provider: SpecialistProvider) -> None:
        self.registered_providers[provider.provider_id] = provider

    def get_provider(self, provider_id: str) -> Optional[SpecialistProvider]:
        return self.registered_providers.get(provider_id)

    def validate_asset_output(
        self,
        job: AssetSpecialistJob,
        file_path: Optional[Path] = None,
    ) -> bool:
        """Unconditionally validates that a generated asset exists as a real non-empty file,
        satisfies workspace containment boundaries without traversal/symlink escapes, matches
        computed SHA-256 digest, contains valid provenance, and meets required metric budgets.
        Does NOT declare engine readiness merely because an artifact is validated.
        """
        # Always reset job state completely on every validation attempt
        job.validation_errors.clear()
        job.status = SpecialistStatus.FAILED
        job.engine_integration_status = EngineIntegrationStatus.UNPROCESSED

        # 1. Provider availability and test double policy
        if job.provider.is_test_double and not self.allow_test_doubles:
            job.status = SpecialistStatus.REJECTED
            job.validation_errors.append(
                f"Provider '{job.provider.provider_id}' is marked as a test double and cannot be used for production asset validation."
            )
            return False

        if not job.provider.is_available:
            job.status = SpecialistStatus.FAILED
            job.validation_errors.append(f"Provider '{job.provider.provider_id}' is not marked available.")
            return False

        # 2. Result & artifact path presence
        if not job.result or not job.result.artifact_path:
            job.status = SpecialistStatus.FAILED
            job.validation_errors.append("No artifact path returned by specialist.")
            return False

        # 3. Path disagreement check (caller file_path vs provider reported path)
        provider_path = Path(job.result.artifact_path)
        try:
            resolved_provider = provider_path.resolve()
        except Exception as e:
            job.status = SpecialistStatus.FAILED
            job.validation_errors.append(f"Failed to resolve provider artifact path: {e}")
            return False

        if file_path is not None:
            try:
                resolved_caller = Path(file_path).resolve()
            except Exception as e:
                job.status = SpecialistStatus.FAILED
                job.validation_errors.append(f"Failed to resolve caller file path: {e}")
                return False

            if resolved_caller != resolved_provider:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(
                    f"Path disagreement: caller specified '{resolved_caller}' but provider reported '{resolved_provider}'"
                )
                return False

        resolved_file = resolved_provider

        # 4. Workspace containment (strict resolved boundary, no parent traversal or symlink escapes)
        if self.workspace_root:
            try:
                if not resolved_file.is_relative_to(self.workspace_root):
                    job.status = SpecialistStatus.REJECTED
                    job.validation_errors.append(
                        f"Path traversal detected: artifact '{resolved_file}' outside workspace '{self.workspace_root}'"
                    )
                    return False
            except Exception as e:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(f"Workspace boundary check failed: {e}")
                return False

        # 5. Mandatory unconditional file existence and non-empty regular file check
        if not resolved_file.exists():
            job.status = SpecialistStatus.FAILED
            job.validation_errors.append(f"Artifact file not found: {resolved_file}")
            return False

        if not resolved_file.is_file():
            job.status = SpecialistStatus.FAILED
            job.validation_errors.append(f"Artifact path is not a regular file (e.g. directory): {resolved_file}")
            return False

        try:
            st = resolved_file.stat()
            if st.st_size == 0:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(f"Artifact file is empty (0 bytes): {resolved_file}")
                return False
        except Exception as e:
            job.status = SpecialistStatus.FAILED
            job.validation_errors.append(f"Failed to inspect artifact file stat: {e}")
            return False

        # 6. Mandatory real file SHA-256 computation and declared mismatch rejection
        try:
            content_bytes = resolved_file.read_bytes()
            computed_sha = hashlib.sha256(content_bytes).hexdigest()
        except Exception as e:
            job.status = SpecialistStatus.FAILED
            job.validation_errors.append(f"Failed to read and hash artifact file: {e}")
            return False

        if job.result.artifact_sha256:
            if job.result.artifact_sha256.lower() != computed_sha.lower():
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(
                    f"Artifact SHA-256 mismatch: expected {job.result.artifact_sha256}, got {computed_sha}"
                )
                return False
        else:
            job.result.artifact_sha256 = computed_sha

        # 7. Mandatory provenance and rights verification
        prov = job.request.provenance
        if prov is None:
            job.status = SpecialistStatus.REJECTED
            job.validation_errors.append("Asset provenance is mandatory for production validation.")
            return False

        if not prov.license_id or not prov.license_id.strip():
            job.status = SpecialistStatus.REJECTED
            job.validation_errors.append("Asset provenance missing required non-empty license_id.")
            return False

        if not prov.rights_holder or not prov.rights_holder.strip():
            job.status = SpecialistStatus.REJECTED
            job.validation_errors.append("Asset provenance missing required non-empty rights_holder.")
            return False

        if not prov.rights_cleared:
            job.status = SpecialistStatus.REJECTED
            job.validation_errors.append(
                f"Asset rights not cleared (rights_cleared is False, license: {prov.license_id})"
            )
            return False

        if not prov.evidence_reference or not prov.evidence_reference.strip():
            job.status = SpecialistStatus.REJECTED
            job.validation_errors.append("Asset provenance missing required non-empty evidence_reference.")
            return False

        # Validate that the evidence reference conforms to a resolvable/meaningful format
        ev_ref = prov.evidence_reference.strip()
        valid_schemes = ("doc://", "legal://", "file://", "tests/", "configs/", "evidence/")
        if not (any(ev_ref.startswith(prefix) for prefix in valid_schemes) or ev_ref.endswith((".md", ".json", ".txt", ".pdf"))):
            job.status = SpecialistStatus.REJECTED
            job.validation_errors.append(
                f"Asset provenance evidence_reference '{ev_ref}' does not match canonical project provenance conventions."
            )
            return False
            return False

        # 8. Modality-specific and configured metrics validation
        metrics = job.result.metrics if job.result.metrics is not None else {}

        # Max triangles constraint
        if job.request.constraints.max_triangles is not None:
            actual_tris = metrics.get("triangle_count")
            if actual_tris is None:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(
                    f"Required metric 'triangle_count' missing to verify budget {job.request.constraints.max_triangles}"
                )
                return False
            # Strict rejection of bools, non-integers, negative, non-finite
            if isinstance(actual_tris, bool) or not isinstance(actual_tris, int) or actual_tris < 0:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(f"Invalid triangle_count metric: {actual_tris} (must be non-negative integer)")
                return False
            if actual_tris > job.request.constraints.max_triangles:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(
                    f"Triangle count {actual_tris} exceeds limit {job.request.constraints.max_triangles}"
                )
                return False

        # Max texture dimension constraint
        if job.request.constraints.max_texture_dimension is not None:
            actual_dim = metrics.get("max_dimension")
            if actual_dim is None:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(
                    f"Required metric 'max_dimension' missing to verify texture budget {job.request.constraints.max_texture_dimension}"
                )
                return False
            if isinstance(actual_dim, bool) or not isinstance(actual_dim, int) or actual_dim <= 0:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(f"Invalid max_dimension metric: {actual_dim} (must be positive integer)")
                return False
            if actual_dim > job.request.constraints.max_texture_dimension:
                job.status = SpecialistStatus.REJECTED
                job.validation_errors.append(
                    f"Texture dimension {actual_dim} exceeds limit {job.request.constraints.max_texture_dimension}"
                )
                return False

        # All checks passed
        job.status = SpecialistStatus.VALIDATED
        job.engine_integration_status = EngineIntegrationStatus.UNPROCESSED
        return True
