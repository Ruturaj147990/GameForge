"""Structured 3D Character Specification for GameForge IDE.

Adheres to Milestone 9:
- Character purpose and visual description.
- Humanoid, creature, or other supported category.
- Approximate height, proportions, and scale.
- Required body coverage and visible features.
- Materials and texture expectations.
- Target skeleton and rig requirements.
- Animation readiness requirements.
- Output format and asset path.
- Polygon and performance budgets.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


class ProportionsSpec(BaseModel):
    """Proportional scaling factors relative to standard human anatomy."""
    head_ratio: float = 1.0       # Standard head scale relative to 1/7.5 of height
    arm_span_ratio: float = 1.0   # Arm span relative to height
    torso_leg_ratio: float = 1.0  # Torso to leg height ratio
    shoulder_width_cm: float = 45.0
    hip_width_cm: float = 32.0


class BodyCoverageSpec(BaseModel):
    """Anatomical segment coverage and feature flags."""
    has_head: bool = True
    has_torso: bool = True
    has_arms: bool = True
    has_legs: bool = True
    has_hands: bool = True
    has_feet: bool = True
    facial_features: bool = False
    clothing_style: str = "adventurer_tunic"


class MaterialSpec(BaseModel):
    """PBR material and texturing parameters."""
    material_name: str = "M_Character_Default"
    base_color_rgba: Tuple[float, float, float, float] = (0.75, 0.65, 0.55, 1.0)
    metallic: float = 0.1
    roughness: float = 0.6
    texture_slots: List[str] = Field(default_factory=lambda: ["BaseColor", "Normal", "Roughness"])


class RigSpec(BaseModel):
    """Skeletal hierarchy and rigging constraints."""
    target_skeleton: str = "UE5_Humanoid_17"
    root_bone_name: str = "root"
    min_bones: int = 10
    max_bones: int = 128
    max_influences_per_vertex: int = 4
    bind_pose_type: str = "T-Pose"  # 'T-Pose' or 'A-Pose'
    enforce_unit_weight_sum: bool = True


class CharacterSpec(BaseModel):
    """Complete, validated Character Specification adhering to Milestone 9."""
    character_id: str
    name: str
    purpose: str
    category: str = "humanoid"  # 'humanoid', 'creature', 'quadruped', 'mechanical'
    height_cm: float = 180.0
    triangle_budget: int = 25000
    lod_count: int = 1
    collision_radius_cm: float = 42.0
    collision_half_height_cm: float = 96.0
    proportions: ProportionsSpec = Field(default_factory=ProportionsSpec)
    body_coverage: BodyCoverageSpec = Field(default_factory=BodyCoverageSpec)
    materials: MaterialSpec = Field(default_factory=MaterialSpec)
    rig: RigSpec = Field(default_factory=RigSpec)
    output_format: str = "FBX"  # 'FBX' or 'GLTF'
    quarantine_path: str = "/Game/Quarantine/Characters"
    target_destination_path: str = "/Game/Characters"
    target_territory: str = "GLOBAL"

    @field_validator("character_id", "name", "purpose")
    @classmethod
    def validate_non_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty.")
        return v.strip()

    @field_validator("height_cm")
    @classmethod
    def validate_height(cls, v: float) -> float:
        if v < 30.0 or v > 500.0:
            raise ValueError(f"height_cm ({v}) must be within physical range [30.0, 500.0] cm.")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid_cats = {"humanoid", "creature", "quadruped", "mechanical"}
        if v.lower() not in valid_cats:
            raise ValueError(f"category must be one of {valid_cats}, got '{v}'.")
        return v.lower()

    @field_validator("triangle_budget")
    @classmethod
    def validate_triangle_budget(cls, v: int) -> int:
        if v < 100 or v > 100000:
            raise ValueError(f"triangle_budget ({v}) must be between 100 and 100,000.")
        return v

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        if v.upper() not in {"FBX", "GLTF"}:
            raise ValueError(f"output_format must be FBX or GLTF, got '{v}'.")
        return v.upper()

    def get_destination_asset_name(self) -> str:
        return f"SK_{self.name.replace(' ', '_')}"

    def compute_sha256(self) -> str:
        raw = json.dumps(self.model_dump(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
