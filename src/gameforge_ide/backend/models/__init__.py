"""Backend Model Definitions, Specifications, and Capability Records for GameForge IDE."""

from __future__ import annotations

from .animation_spec import AnimationSpec
from .asset_spec import StaticMeshAssetSpec, MaterialSlotSpec, LODSpec
from .capability import CapabilityRecord, CapabilityRegistry, DataEgressClass, ModelRole
from .character_spec import CharacterSpec
from .modes import AutonomyProfile, PermissionsMode, TaskLifecycleStatus, TaskMode, can_transition
from .plan_artifact import PlanArtifact, PlanRevision, PlanStep
from .provenance import AssetProvenanceRecord, LicenseRecord, LicenseRegistry
from .context_usage import ContextBreakdown, ContextUsageReport
from .command_contract import CommandStatus, RiskCategory, CommandExecutionRequest, CommandExecutionResult

__all__ = [
    "AnimationSpec",
    "AssetProvenanceRecord",
    "AutonomyProfile",
    "CapabilityRecord",
    "CapabilityRegistry",
    "CharacterSpec",
    "CommandExecutionRequest",
    "CommandExecutionResult",
    "CommandStatus",
    "ContextBreakdown",
    "ContextUsageReport",
    "DataEgressClass",
    "LicenseRecord",
    "LicenseRegistry",
    "LODSpec",
    "MaterialSlotSpec",
    "ModelRole",
    "PermissionsMode",
    "PlanArtifact",
    "PlanRevision",
    "PlanStep",
    "RiskCategory",
    "StaticMeshAssetSpec",
    "TaskLifecycleStatus",
    "TaskMode",
    "can_transition",
]
