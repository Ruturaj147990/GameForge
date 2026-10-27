"""Level Layout Generation from Structured Specification for GameForge IDE.

Compliant with GameForge Master Blueprint:
- REQ-060: Level Layout from a written spec.
- Spatial bounding box verification, overlap prevention, and navigation clearance.
- Actor placement and genuine read-back via Unreal Operations Library.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from .operations import UnrealOperationsLibrary


class BoundingBox(BaseModel):
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def overlaps(self, other: BoundingBox, margin: float = 0.0) -> bool:
        """Determines if this AABB overlaps another with an optional safety margin."""
        return not (
            self.max_x + margin <= other.min_x
            or self.min_x - margin >= other.max_x
            or self.max_y + margin <= other.min_y
            or self.min_y - margin >= other.max_y
            or self.max_z + margin <= other.min_z
            or self.min_z - margin >= other.max_z
        )

    def contains_point(self, x: float, y: float, z: float) -> bool:
        return (
            self.min_x <= x <= self.max_x
            and self.min_y <= y <= self.max_y
            and self.min_z <= z <= self.max_z
        )


class PropPlacementSpec(BaseModel):
    label: str
    actor_class: str = "StaticMeshActor"
    location: Tuple[float, float, float]  # (X, Y, Z)
    extent: Tuple[float, float, float] = (50.0, 50.0, 50.0)  # Half-extents (DX, DY, DZ)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # (Pitch, Yaw, Roll)
    is_interactive: bool = False

    def get_bounds(self) -> BoundingBox:
        x, y, z = self.location
        dx, dy, dz = self.extent
        return BoundingBox(
            min_x=x - dx,
            min_y=y - dy,
            min_z=z - dz,
            max_x=x + dx,
            max_y=y + dy,
            max_z=z + dz,
        )


class RoomSpec(BaseModel):
    room_id: str
    room_type: str = "arena"  # 'start', 'arena', 'corridor', 'exit'
    bounds: BoundingBox
    doorways: List[Tuple[float, float, float]] = Field(default_factory=list)


class LevelLayoutSpec(BaseModel):
    level_name: str
    level_path: str = "/Game/Maps/GeneratedLevel"
    rooms: List[RoomSpec] = Field(default_factory=list)
    props: List[PropPlacementSpec] = Field(default_factory=list)
    navigation_clearance_radius: float = 45.0  # Player capsule clearance (cm)


class LevelLayoutGenerator:
    """Validates and instantiates structured level designs."""

    def __init__(self, operations: Optional[UnrealOperationsLibrary] = None):
        self.operations = operations

    def validate_layout(self, spec: LevelLayoutSpec) -> Tuple[bool, List[str]]:
        """Verifies spatial integrity, containment, collision overlaps, and navigation clearance."""
        errors: List[str] = []

        # 1. Verify rooms are valid
        if not spec.rooms:
            errors.append("Layout spec must define at least one room")

        # 2. Verify all props are contained inside a room
        for prop in spec.props:
            prop_bounds = prop.get_bounds()
            contained = False
            for room in spec.rooms:
                if (
                    room.bounds.min_x <= prop_bounds.min_x
                    and room.bounds.max_x >= prop_bounds.max_x
                    and room.bounds.min_y <= prop_bounds.min_y
                    and room.bounds.max_y >= prop_bounds.max_y
                    and room.bounds.min_z <= prop_bounds.min_z
                    and room.bounds.max_z >= prop_bounds.max_z
                ):
                    contained = True
                    break
            if not contained:
                errors.append(f"Prop '{prop.label}' at {prop.location} is outside all room bounds")

        # 3. Verify no prop-on-prop collision overlaps
        for i in range(len(spec.props)):
            b1 = spec.props[i].get_bounds()
            for j in range(i + 1, len(spec.props)):
                b2 = spec.props[j].get_bounds()
                if b1.overlaps(b2):
                    errors.append(
                        f"Collision overlap detected between '{spec.props[i].label}' and '{spec.props[j].label}'"
                    )

        # 4. Verify navigation clearance around doorways
        for room in spec.rooms:
            for door_x, door_y, door_z in room.doorways:
                for prop in spec.props:
                    px, py, _ = prop.location
                    dist_to_door = math.hypot(px - door_x, py - door_y)
                    required_dist = spec.navigation_clearance_radius + max(prop.extent[0], prop.extent[1])
                    if dist_to_door < required_dist:
                        errors.append(
                            f"Navigation blocked: Prop '{prop.label}' at {dist_to_door:.1f}cm violates "
                            f"clearance radius ({required_dist:.1f}cm) of doorway at ({door_x}, {door_y})"
                        )

        return len(errors) == 0, errors

    async def instantiate_layout(
        self, spec: LevelLayoutSpec, token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Instantiates all validated props into the target level via Unreal Operations Library."""
        valid, errors = self.validate_layout(spec)
        if not valid:
            return {"ok": False, "error": "LAYOUT_VALIDATION_FAILED", "errors": errors}

        if not self.operations:
            return {"ok": False, "error": "No operations library provided for layout instantiation"}

        placed_actors = []
        for prop in spec.props:
            res = await self.operations.spawn_actor(
                actor_class=prop.actor_class,
                label=prop.label,
                location={"x": prop.location[0], "y": prop.location[1], "z": prop.location[2]},
                rotation={"pitch": prop.rotation[0], "yaw": prop.rotation[1], "roll": prop.rotation[2]},
                level_path=spec.level_path,
                token=token,
            )
            if not res.ok:
                return {
                    "ok": False,
                    "error": f"Failed to spawn actor {prop.label}: {res.errors}",
                    "placed_actors": placed_actors,
                }
            placed_actors.append(prop.label)

        # Read-back verification (Rule 7)
        level_actors = self.operations.actors_in_level(spec.level_path)
        spawned_labels = [a.get("label") for a in level_actors]
        all_present = all(p in spawned_labels for p in placed_actors)

        return {
            "ok": all_present,
            "level_path": spec.level_path,
            "placed_count": len(placed_actors),
            "placed_actors": placed_actors,
            "verified_in_level": all_present,
        }
