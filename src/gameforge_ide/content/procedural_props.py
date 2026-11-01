"""Procedural static mesh prop recipes (P7 WI-7.4).

Defines Geometry Script CSG primitive recipes for procedural props (crate, barrel,
rock, pillar, fence, stylized_tree, bush, torch, chest, altar) with LOD reduction,
collision profiles, and material role assignments.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PropRecipe:
    name: str
    parts: List[Dict[str, Any]]
    triangle_budget: int = 2000
    lod_reduction: List[float] = field(default_factory=lambda: [0.5, 0.25])
    collision: str = "box"
    material_role: str = "prop"
    tags: List[str] = field(default_factory=list)

    def to_op_args(self, asset_path: str) -> Dict[str, Any]:
        """Convert recipe into arguments for mesh_generate_prop op."""
        return {
            "asset_path": asset_path,
            "parts": self.parts,
            "triangle_budget": self.triangle_budget,
        }

    def to_configure_args(self, asset_path: str, material_path: Optional[str] = None) -> Dict[str, Any]:
        """Convert recipe into arguments for static_mesh_configure op."""
        args: Dict[str, Any] = {
            "static_mesh_path": asset_path,
            "lod_reduction": self.lod_reduction,
            "collision": self.collision,
            "nanite": False,
        }
        if material_path:
            args["materials"] = [material_path]
        return args


def _box(size: List[float], loc: Optional[Dict[str, float]] = None, op: str = "union") -> Dict[str, Any]:
    return {"shape": "box", "size": [float(v) for v in size], "location": loc or {"x": 0.0, "y": 0.0, "z": 0.0}, "op": op}


def _cylinder(radius: float, height: float, loc: Optional[Dict[str, float]] = None, op: str = "union") -> Dict[str, Any]:
    return {"shape": "cylinder", "radius": float(radius), "height": float(height), "location": loc or {"x": 0.0, "y": 0.0, "z": 0.0}, "op": op}


def _sphere(radius: float, loc: Optional[Dict[str, float]] = None, op: str = "union") -> Dict[str, Any]:
    return {"shape": "sphere", "radius": float(radius), "location": loc or {"x": 0.0, "y": 0.0, "z": 0.0}, "op": op}


PROP_RECIPES: Dict[str, PropRecipe] = {
    # 1. Crate
    "crate": PropRecipe(
        name="crate",
        parts=[
            _box([100.0, 100.0, 100.0], {"x": 0.0, "y": 0.0, "z": 50.0}),
            _box([104.0, 104.0, 12.0], {"x": 0.0, "y": 0.0, "z": 96.0}),
            _box([104.0, 104.0, 12.0], {"x": 0.0, "y": 0.0, "z": 6.0}),
        ],
        triangle_budget=800,
        collision="box",
        material_role="prop",
        tags=["prop", "container", "crate"],
    ),

    # 2. Barrel
    "barrel": PropRecipe(
        name="barrel",
        parts=[
            _cylinder(45.0, 100.0, {"x": 0.0, "y": 0.0, "z": 50.0}),
            _cylinder(48.0, 8.0, {"x": 0.0, "y": 0.0, "z": 20.0}),
            _cylinder(48.0, 8.0, {"x": 0.0, "y": 0.0, "z": 80.0}),
        ],
        triangle_budget=1200,
        collision="complex_as_simple",
        material_role="prop",
        tags=["prop", "container", "barrel"],
    ),

    # 3. Rock
    "rock": PropRecipe(
        name="rock",
        parts=[
            _sphere(75.0, {"x": 0.0, "y": 0.0, "z": 55.0}),
            _sphere(55.0, {"x": 35.0, "y": 20.0, "z": 45.0}),
            _sphere(45.0, {"x": -30.0, "y": -25.0, "z": 50.0}),
        ],
        triangle_budget=1500,
        collision="complex_as_simple",
        material_role="prop",
        tags=["nature", "rock", "boulder"],
    ),

    # 4. Pillar
    "pillar": PropRecipe(
        name="pillar",
        parts=[
            _box([80.0, 80.0, 20.0], {"x": 0.0, "y": 0.0, "z": 10.0}),
            _cylinder(28.0, 260.0, {"x": 0.0, "y": 0.0, "z": 150.0}),
            _box([80.0, 80.0, 20.0], {"x": 0.0, "y": 0.0, "z": 290.0}),
        ],
        triangle_budget=1400,
        collision="box",
        material_role="wall",
        tags=["architecture", "column", "pillar"],
    ),

    # 5. Fence
    "fence": PropRecipe(
        name="fence",
        parts=[
            _box([15.0, 15.0, 120.0], {"x": -95.0, "y": 0.0, "z": 60.0}),
            _box([15.0, 15.0, 120.0], {"x": 95.0, "y": 0.0, "z": 60.0}),
            _box([200.0, 8.0, 12.0], {"x": 0.0, "y": 0.0, "z": 90.0}),
            _box([200.0, 8.0, 12.0], {"x": 0.0, "y": 0.0, "z": 40.0}),
        ],
        triangle_budget=600,
        collision="box",
        material_role="prop",
        tags=["architecture", "barrier", "fence"],
    ),

    # 6. Stylized Tree
    "stylized_tree": PropRecipe(
        name="stylized_tree",
        parts=[
            _cylinder(22.0, 180.0, {"x": 0.0, "y": 0.0, "z": 90.0}),
            _sphere(70.0, {"x": 0.0, "y": 0.0, "z": 220.0}),
            _sphere(55.0, {"x": 25.0, "y": -20.0, "z": 260.0}),
            _sphere(50.0, {"x": -25.0, "y": 25.0, "z": 250.0}),
            _sphere(40.0, {"x": 0.0, "y": 0.0, "z": 300.0}),
        ],
        triangle_budget=2500,
        collision="complex_as_simple",
        material_role="prop",
        tags=["nature", "tree", "foliage"],
    ),

    # 7. Bush
    "bush": PropRecipe(
        name="bush",
        parts=[
            _sphere(45.0, {"x": 0.0, "y": 0.0, "z": 35.0}),
            _sphere(35.0, {"x": 25.0, "y": 15.0, "z": 30.0}),
            _sphere(35.0, {"x": -20.0, "y": -20.0, "z": 28.0}),
        ],
        triangle_budget=1200,
        collision="sphere",
        material_role="prop",
        tags=["nature", "vegetation", "bush"],
    ),

    # 8. Torch
    "torch": PropRecipe(
        name="torch",
        parts=[
            _box([10.0, 20.0, 40.0], {"x": 0.0, "y": 10.0, "z": 30.0}),
            _cylinder(6.0, 50.0, {"x": 0.0, "y": 25.0, "z": 45.0}),
            _cylinder(14.0, 15.0, {"x": 0.0, "y": 25.0, "z": 75.0}),
        ],
        triangle_budget=800,
        collision="box",
        material_role="prop",
        tags=["prop", "light", "torch"],
    ),

    # 9. Chest
    "chest": PropRecipe(
        name="chest",
        parts=[
            _box([90.0, 60.0, 40.0], {"x": 0.0, "y": 0.0, "z": 20.0}),
            _box([94.0, 64.0, 22.0], {"x": 0.0, "y": 0.0, "z": 50.0}),
            _box([12.0, 8.0, 16.0], {"x": 0.0, "y": -32.0, "z": 38.0}),
        ],
        triangle_budget=900,
        collision="box",
        material_role="prop",
        tags=["prop", "interactive", "chest"],
    ),

    # 10. Altar
    "altar": PropRecipe(
        name="altar",
        parts=[
            _box([160.0, 100.0, 25.0], {"x": 0.0, "y": 0.0, "z": 12.5}),
            _box([120.0, 70.0, 60.0], {"x": 0.0, "y": 0.0, "z": 55.0}),
            _box([180.0, 110.0, 20.0], {"x": 0.0, "y": 0.0, "z": 95.0}),
        ],
        triangle_budget=1200,
        collision="box",
        material_role="prop",
        tags=["prop", "landmark", "altar"],
    ),
}
