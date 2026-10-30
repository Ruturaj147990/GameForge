"""Structured Animation Specification for GameForge IDE.

Adheres to Milestone 10:
- Target character and skeleton.
- Desired action and movement style.
- Duration and frame/sample rate.
- In-place or root-motion behavior.
- Coordinate convention and scale.
- Required start and end poses where applicable.
- Looping and transition requirements.
- Target Animation Blueprint or animation sequence path.
- Motion and quality acceptance criteria.
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


class AnimationAction(str, Enum):
    IDLE = "idle"
    WALK = "walk"
    RUN = "run"
    JUMP = "jump"
    FALL = "fall"
    LAND = "land"
    ATTACK = "attack"


class MovementStyle(str, Enum):
    STANDARD_BIPED = "standard_biped"
    ATHLETIC = "athletic"
    SNEAKING = "sneaking"
    HEAVY = "heavy"


class QualityCriteria(BaseModel):
    """Kinematic plausibility and smoothness criteria."""
    max_rotation_jitter_deg: float = 25.0
    max_loop_discontinuity_deg: float = 5.0
    enforce_unit_quaternions: bool = True
    enforce_finite_values: bool = True


class AnimationSpec(BaseModel):
    """Specification for an individual animation clip."""
    spec_id: str
    name: str
    action: AnimationAction
    target_character_id: str
    target_skeleton_path: str
    movement_style: MovementStyle = MovementStyle.STANDARD_BIPED
    duration_seconds: float = 1.0
    sample_rate_hz: int = 30
    is_looping: bool = True
    is_root_motion: bool = False
    speed_threshold_cm_s: float = 0.0
    coordinate_convention: str = "Z-Up_X-Forward"
    quarantine_path: str = "/Game/Quarantine/Animations"
    destination_path: str = "/Game/Animations"
    quality_criteria: QualityCriteria = Field(default_factory=QualityCriteria)

    @field_validator("spec_id", "name", "target_character_id", "target_skeleton_path")
    @classmethod
    def validate_non_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty.")
        return v.strip()

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, v: float) -> float:
        if v <= 0.05 or v > 60.0:
            raise ValueError(f"duration_seconds ({v}) must be in range [0.05, 60.0].")
        return v

    @field_validator("sample_rate_hz")
    @classmethod
    def validate_sample_rate(cls, v: int) -> int:
        if v not in (15, 24, 30, 60, 120):
            raise ValueError(f"sample_rate_hz ({v}) must be standard rate (15, 24, 30, 60, 120).")
        return v

    @property
    def total_frames(self) -> int:
        return int(math.ceil(self.duration_seconds * self.sample_rate_hz))

    def compute_sha256(self) -> str:
        raw = json.dumps(self.model_dump(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class LocomotionSetSpec(BaseModel):
    """Locomotion bundle containing Idle, Walk, Run, Jump, Fall, Land specifications."""
    bundle_id: str
    character_id: str
    target_skeleton_path: str
    anim_blueprint_name: str = "ABP_CharacterLocomotion"
    destination_path: str = "/Game/Animations"
    clips: List[AnimationSpec] = Field(default_factory=list)

    @classmethod
    def create_standard_humanoid_locomotion(
        cls,
        character_id: str,
        target_skeleton_path: str,
        destination_path: str = "/Game/Animations",
    ) -> LocomotionSetSpec:
        """Constructs canonical standard humanoid locomotion set spec."""
        clips = [
            AnimationSpec(
                spec_id=f"{character_id}_idle",
                name="Anim_Idle",
                action=AnimationAction.IDLE,
                target_character_id=character_id,
                target_skeleton_path=target_skeleton_path,
                duration_seconds=2.0,
                sample_rate_hz=30,
                is_looping=True,
                is_root_motion=False,
                speed_threshold_cm_s=0.0,
                destination_path=destination_path,
            ),
            AnimationSpec(
                spec_id=f"{character_id}_walk",
                name="Anim_Walk",
                action=AnimationAction.WALK,
                target_character_id=character_id,
                target_skeleton_path=target_skeleton_path,
                duration_seconds=1.2,
                sample_rate_hz=30,
                is_looping=True,
                is_root_motion=False,
                speed_threshold_cm_s=15.0,
                destination_path=destination_path,
            ),
            AnimationSpec(
                spec_id=f"{character_id}_run",
                name="Anim_Run",
                action=AnimationAction.RUN,
                target_character_id=character_id,
                target_skeleton_path=target_skeleton_path,
                duration_seconds=0.8,
                sample_rate_hz=30,
                is_looping=True,
                is_root_motion=False,
                speed_threshold_cm_s=300.0,
                destination_path=destination_path,
            ),
            AnimationSpec(
                spec_id=f"{character_id}_jump",
                name="Anim_Jump",
                action=AnimationAction.JUMP,
                target_character_id=character_id,
                target_skeleton_path=target_skeleton_path,
                duration_seconds=0.6,
                sample_rate_hz=30,
                is_looping=False,
                is_root_motion=False,
                destination_path=destination_path,
            ),
            AnimationSpec(
                spec_id=f"{character_id}_fall",
                name="Anim_Fall",
                action=AnimationAction.FALL,
                target_character_id=character_id,
                target_skeleton_path=target_skeleton_path,
                duration_seconds=0.8,
                sample_rate_hz=30,
                is_looping=True,
                is_root_motion=False,
                destination_path=destination_path,
            ),
            AnimationSpec(
                spec_id=f"{character_id}_land",
                name="Anim_Land",
                action=AnimationAction.LAND,
                target_character_id=character_id,
                target_skeleton_path=target_skeleton_path,
                duration_seconds=0.4,
                sample_rate_hz=30,
                is_looping=False,
                is_root_motion=False,
                destination_path=destination_path,
            ),
        ]
        return cls(
            bundle_id=f"{character_id}_locomotion",
            character_id=character_id,
            target_skeleton_path=target_skeleton_path,
            anim_blueprint_name="ABP_CharacterLocomotion",
            destination_path=destination_path,
            clips=clips,
        )

