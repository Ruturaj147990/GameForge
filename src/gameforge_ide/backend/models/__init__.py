"""Backend Model Definitions, Specifications, and Capability Records for GameForge IDE."""

from __future__ import annotations

from .animation_spec import AnimationSpec
from .asset_spec import StaticMeshAssetSpec, MaterialSlotSpec, LODSpec
from .capability import CapabilityRecord, CapabilityRegistry, DataEgressClass, ModelRole
from .character_spec import CharacterSpec
from .modes import AutonomyProfile, TaskLifecycleStatus, TaskMode, can_transition
from .plan_artifact import PlanArtifact, PlanRevision, PlanStep
from .provenance import AssetProvenanceRecord, LicenseRecord, LicenseRegistry

__all__ = [
    "AnimationSpec",
    "AssetProvenanceRecord",
    "AutonomyProfile",
    "CapabilityRecord",
    "CapabilityRegistry",
    "CharacterSpec",
    "DataEgressClass",
    "LicenseRecord",
    "LicenseRegistry",
    "LODSpec",
    "MaterialSlotSpec",
    "ModelRole",
    "PlanArtifact",
    "PlanRevision",
    "PlanStep",
    "StaticMeshAssetSpec",
    "TaskLifecycleStatus",
    "TaskMode",
    "can_transition",
]
