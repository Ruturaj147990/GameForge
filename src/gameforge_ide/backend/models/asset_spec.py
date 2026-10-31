"""Static-mesh prop specification (roadmap M12 step 1).

One spec drives generation (Geometry Script in the editor), LOD and collision setup, material binding (M11) and
the quarantine → promote lifecycle in the asset registry. Dimensions are Unreal centimetres, X = width,
Y = depth, Z = height, pivot at the bottom centre.
"""

from __future__ import annotations

import hashlib
import json
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

CATEGORIES = ("prop", "furniture", "container", "light_fixture", "foliage", "rock", "architecture", "modular_kit",
              "vehicle", "weapon", "tool")
COLLISION_TYPES = ("none", "box", "sphere", "capsule", "convex", "complex_as_simple")


class MaterialSlotSpec(BaseModel):
    """One material slot; ``material_path`` binds an existing M_/MI_, otherwise an M11 PBR set is generated."""
    slot_name: str
    material_path: Optional[str] = None
    pbr_seed: int = 0
    base_color: Tuple[float, float, float] = (0.5, 0.5, 0.5)

    @field_validator("slot_name")
    @classmethod
    def _slot_name(cls, v: str) -> str:
        if not v or not v.replace("_", "").isalnum():
            raise ValueError("slot_name must be non-empty alphanumeric/underscore")
        return v


class LODSpec(BaseModel):
    """Triangle fraction of LOD0 kept by each extra LOD (LOD1, LOD2, ...); strictly decreasing."""
    reduction: List[float] = Field(default_factory=lambda: [0.5, 0.25])

    @field_validator("reduction")
    @classmethod
    def _reduction(cls, v: List[float]) -> List[float]:
        if len(v) > 7:
            raise ValueError("at most 7 extra LODs")
        if any(not 0.0 < r < 1.0 for r in v) or any(b >= a for a, b in zip(v, v[1:])):
            raise ValueError("reduction fractions must be in (0, 1) and strictly decreasing")
        return v


class StaticMeshAssetSpec(BaseModel):
    asset_id: str
    name: str
    purpose: str
    category: str = "prop"
    size_cm: Tuple[float, float, float] = (100.0, 100.0, 100.0)
    triangle_budget: int = 5000
    lods: LODSpec = Field(default_factory=LODSpec)
    collision: str = "box"
    nanite: bool = False
    material_slots: List[MaterialSlotSpec] = Field(default_factory=lambda: [MaterialSlotSpec(slot_name="Main")])
    quarantine_path: str = "/Game/Quarantine/Props"
    destination_path: str = "/Game/Props"
    tags: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v or not v.replace("_", "").isalnum():
            raise ValueError("name must be non-empty alphanumeric/underscore")
        return v

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        return v

    @field_validator("size_cm")
    @classmethod
    def _size(cls, v: Tuple[float, float, float]) -> Tuple[float, float, float]:
        if any(not 1.0 <= d <= 100000.0 for d in v):
            raise ValueError("each dimension must be between 1 cm and 1 km")
        return v

    @field_validator("triangle_budget")
    @classmethod
    def _budget(cls, v: int) -> int:
        if not 12 <= v <= 2_000_000:
            raise ValueError("triangle_budget must be between 12 and 2,000,000")
        return v

    @field_validator("collision")
    @classmethod
    def _collision(cls, v: str) -> str:
        if v not in COLLISION_TYPES:
            raise ValueError(f"collision must be one of {COLLISION_TYPES}")
        return v

    @field_validator("quarantine_path", "destination_path")
    @classmethod
    def _game_path(cls, v: str) -> str:
        if not v.startswith("/Game/") or v.endswith("/") or ".." in v:
            raise ValueError("paths must be /Game/... without a trailing slash or '..'")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "StaticMeshAssetSpec":
        names = [s.slot_name for s in self.material_slots]
        if not names or len(set(names)) != len(names):
            raise ValueError("material_slots must be non-empty with unique slot names")
        if not self.quarantine_path.startswith("/Game/Quarantine"):
            raise ValueError("quarantine_path must live under /Game/Quarantine")
        if self.destination_path.startswith("/Game/Quarantine"):
            raise ValueError("destination_path must be outside quarantine")
        return self

    @property
    def lod_count(self) -> int:
        return 1 + len(self.lods.reduction)

    def lod_triangle_targets(self, lod0_triangles: int) -> List[int]:
        return [lod0_triangles] + [max(1, int(lod0_triangles * r)) for r in self.lods.reduction]

    def asset_name(self) -> str:
        return f"SM_{self.name}"

    def compute_sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode("utf-8")).hexdigest()
