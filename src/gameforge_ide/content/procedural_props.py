"""Procedural static mesh prop recipes (P7 WI-7.4).

Defines Geometry Script CSG primitive recipes for procedural props (crate, barrel,
rock, pillar, fence, stylized_tree, bush, torch, chest, altar) with LOD reduction,
collision profiles, material role assignments, and multi-primitive level op expansion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


ALLOWED_COLLISIONS = ("box", "sphere", "capsule", "convex", "complex_as_simple", "none")
ALLOWED_SHAPES = ("box", "cylinder", "sphere", "cone")
ALLOWED_OPS = ("union", "subtract")


@dataclass
class PropRecipe:
    name: str
    parts: List[Dict[str, Any]]
    triangle_budget: int = 2000
    lod_reduction: List[float] = field(default_factory=lambda: [0.5, 0.25])
    collision: str = "box"
    material_role: str = "prop"
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate recipe geometry parameters and engine constraints."""
        if not self.name or not isinstance(self.name, str):
            raise ValueError(f"Prop recipe name must be a non-empty string, got {self.name!r}")
        if self.triangle_budget <= 0:
            raise ValueError(f"triangle_budget must be positive, got {self.triangle_budget}")
        if self.collision not in ALLOWED_COLLISIONS:
            raise ValueError(f"Invalid collision type: {self.collision!r}. Allowed: {ALLOWED_COLLISIONS}")
        if not self.parts:
            raise ValueError("Prop recipe must contain at least one geometric part")
        for idx, part in enumerate(self.parts):
            if not isinstance(part, dict):
                raise TypeError(f"Part {idx} must be a dict, got {type(part)}")
            shape = part.get("shape")
            if shape not in ALLOWED_SHAPES:
                raise ValueError(f"Part {idx} has invalid shape: {shape!r}. Allowed: {ALLOWED_SHAPES}")
            op = part.get("op", "union")
            if op not in ALLOWED_OPS:
                raise ValueError(f"Part {idx} has invalid op: {op!r}. Allowed: {ALLOWED_OPS}")

            if shape == "box":
                size = part.get("size")
                if not isinstance(size, (list, tuple)) or len(size) != 3:
                    raise ValueError(f"Part {idx} (box) must have size [X, Y, Z], got {size!r}")
                if any(float(v) <= 0.0 for v in size):
                    raise ValueError(f"Part {idx} (box) size dimensions must be strictly positive, got {size}")
            elif shape == "cylinder":
                radius = part.get("radius")
                height = part.get("height")
                if radius is None or float(radius) <= 0.0:
                    raise ValueError(f"Part {idx} (cylinder) radius must be positive, got {radius}")
                if height is None or float(height) <= 0.0:
                    raise ValueError(f"Part {idx} (cylinder) height must be positive, got {height}")
            elif shape == "sphere":
                radius = part.get("radius")
                if radius is None or float(radius) <= 0.0:
                    raise ValueError(f"Part {idx} (sphere) radius must be positive, got {radius}")
            elif shape == "cone":
                radius = part.get("radius")
                height = part.get("height")
                if radius is None or float(radius) <= 0.0:
                    raise ValueError(f"Part {idx} (cone) radius must be positive, got {radius}")
                if height is None or float(height) <= 0.0:
                    raise ValueError(f"Part {idx} (cone) height must be positive, got {height}")

            loc = part.get("location")
            if loc is not None:
                if not isinstance(loc, dict) or not all(k in loc for k in ("x", "y", "z")):
                    raise ValueError(f"Part {idx} location must be a dict with 'x', 'y', 'z', got {loc!r}")
        if self.lod_reduction:
            prev = 1.0
            for frac in self.lod_reduction:
                if not (0.0 < frac < 1.0):
                    raise ValueError(f"LOD reduction fraction {frac} must be in (0.0, 1.0)")
                if frac >= prev:
                    raise ValueError(f"LOD reduction fractions must be strictly descending, got {self.lod_reduction}")
                prev = frac

    def to_op_args(self, asset_path: str, convert_to_base_origin: bool = True) -> Dict[str, Any]:
        """Convert recipe into arguments for mesh_generate_prop op."""
        self.validate()
        op_parts = []
        for part in self.parts:
            p = dict(part)
            if convert_to_base_origin and p.get("origin", "center") == "center":
                loc = dict(p.get("location", {"x": 0.0, "y": 0.0, "z": 0.0}))
                shape = p.get("shape")
                if shape == "box":
                    size = p.get("size", [100.0, 100.0, 100.0])
                    loc["z"] = float(loc.get("z", 0.0)) - float(size[2]) / 2.0
                elif shape in ("cylinder", "cone"):
                    height = float(p.get("height", 100.0))
                    loc["z"] = float(loc.get("z", 0.0)) - height / 2.0
                p["location"] = loc
                p["origin"] = "base"
            op_parts.append(p)

        return {
            "asset_path": asset_path,
            "parts": op_parts,
            "triangle_budget": self.triangle_budget,
        }

    def to_configure_args(self, asset_path: str, material_path: Optional[str] = None) -> Dict[str, Any]:
        """Convert recipe into arguments for static_mesh_configure op."""
        self.validate()
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
    if len(size) != 3 or any(float(v) <= 0.0 for v in size):
        raise ValueError(f"Box size must be 3 positive floats [X, Y, Z], got {size}")
    if op not in ALLOWED_OPS:
        raise ValueError(f"Invalid CSG op: {op!r}. Allowed: {ALLOWED_OPS}")
    return {"shape": "box", "size": [float(v) for v in size], "location": loc or {"x": 0.0, "y": 0.0, "z": 0.0}, "op": op}


def _cylinder(radius: float, height: float, loc: Optional[Dict[str, float]] = None, op: str = "union") -> Dict[str, Any]:
    if float(radius) <= 0.0 or float(height) <= 0.0:
        raise ValueError(f"Cylinder radius and height must be positive, got radius={radius}, height={height}")
    if op not in ALLOWED_OPS:
        raise ValueError(f"Invalid CSG op: {op!r}. Allowed: {ALLOWED_OPS}")
    return {"shape": "cylinder", "radius": float(radius), "height": float(height), "location": loc or {"x": 0.0, "y": 0.0, "z": 0.0}, "op": op}


def _sphere(radius: float, loc: Optional[Dict[str, float]] = None, op: str = "union") -> Dict[str, Any]:
    if float(radius) <= 0.0:
        raise ValueError(f"Sphere radius must be positive, got radius={radius}")
    if op not in ALLOWED_OPS:
        raise ValueError(f"Invalid CSG op: {op!r}. Allowed: {ALLOWED_OPS}")
    return {"shape": "sphere", "radius": float(radius), "location": loc or {"x": 0.0, "y": 0.0, "z": 0.0}, "op": op}


def _cone(
    radius: float,
    height: float,
    top_radius: float = 0.0,
    loc: Optional[Dict[str, float]] = None,
    op: str = "union",
) -> Dict[str, Any]:
    if float(radius) <= 0.0 or float(height) <= 0.0:
        raise ValueError(f"Cone radius and height must be positive, got radius={radius}, height={height}")
    if float(top_radius) < 0.0:
        raise ValueError(f"Cone top_radius must be non-negative, got top_radius={top_radius}")
    if op not in ALLOWED_OPS:
        raise ValueError(f"Invalid CSG op: {op!r}. Allowed: {ALLOWED_OPS}")
    return {
        "shape": "cone",
        "radius": float(radius),
        "height": float(height),
        "top_radius": float(top_radius),
        "location": loc or {"x": 0.0, "y": 0.0, "z": 0.0},
        "op": op,
    }


def compute_bounds(recipe: PropRecipe, use_base_origin: bool = True) -> Dict[str, float]:
    """Calculate the global axis-aligned bounding box of a PropRecipe."""
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    op_args = recipe.to_op_args("dummy", convert_to_base_origin=use_base_origin)
    for part in op_args["parts"]:
        shape = part["shape"]
        loc = part.get("location", {"x": 0.0, "y": 0.0, "z": 0.0})
        lx, ly, lz = float(loc["x"]), float(loc["y"]), float(loc["z"])

        if shape == "box":
            sx, sy, sz = [float(v) for v in part["size"]]
            px_min, px_max = lx - sx / 2.0, lx + sx / 2.0
            py_min, py_max = ly - sy / 2.0, ly + sy / 2.0
            pz_min, pz_max = lz, lz + sz
        elif shape == "cylinder":
            r = float(part["radius"])
            h = float(part["height"])
            px_min, px_max = lx - r, lx + r
            py_min, py_max = ly - r, ly + r
            pz_min, pz_max = lz, lz + h
        elif shape == "sphere":
            r = float(part["radius"])
            px_min, px_max = lx - r, lx + r
            py_min, py_max = ly - r, ly + r
            pz_min, pz_max = lz - r, lz + r
        elif shape == "cone":
            r = max(float(part["radius"]), float(part.get("top_radius", 0.0)))
            h = float(part["height"])
            px_min, px_max = lx - r, lx + r
            py_min, py_max = ly - r, ly + r
            pz_min, pz_max = lz, lz + h
        else:
            continue

        min_x = min(min_x, px_min)
        max_x = max(max_x, px_max)
        min_y = min(min_y, py_min)
        max_y = max(max_y, py_max)
        min_z = min(min_z, pz_min)
        max_z = max(max_z, pz_max)

    return {
        "min_x": round(min_x, 2), "max_x": round(max_x, 2),
        "min_y": round(min_y, 2), "max_y": round(max_y, 2),
        "min_z": round(min_z, 2), "max_z": round(max_z, 2),
        "height": round(max_z - min_z, 2),
        "width_x": round(max_x - min_x, 2),
        "width_y": round(max_y - min_y, 2),
    }


def verify_recipe_watertight(recipe: PropRecipe) -> Dict[str, Any]:
    """Verify that a CSG recipe is structurally connected without floating/detached gaps."""
    bounds = compute_bounds(recipe, use_base_origin=True)
    contacts_ground = bounds["min_z"] <= 1.0
    return {
        "recipe": recipe.name,
        "contacts_ground": contacts_ground,
        "bounds": bounds,
        "parts_count": len(recipe.parts),
        "collision": recipe.collision,
        "triangle_budget": recipe.triangle_budget,
        "watertight": contacts_ground and len(recipe.parts) > 0,
    }


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

    # 11. Crystal
    "crystal": PropRecipe(
        name="crystal",
        parts=[
            _cylinder(35.0, 24.0, {"x": 0.0, "y": 0.0, "z": 12.0}),
            _cone(28.0, 130.0, top_radius=2.0, loc={"x": 0.0, "y": 0.0, "z": 80.0}),
            _cone(18.0, 80.0, top_radius=2.0, loc={"x": 20.0, "y": 12.0, "z": 50.0}),
            _cone(16.0, 70.0, top_radius=2.0, loc={"x": -18.0, "y": -14.0, "z": 45.0}),
        ],
        triangle_budget=1400,
        collision="capsule",
        material_role="accent",
        tags=["prop", "crystal", "collectible", "magic"],
    ),

    # 12. Arch
    "arch": PropRecipe(
        name="arch",
        parts=[
            _box([50.0, 50.0, 280.0], {"x": -140.0, "y": 0.0, "z": 140.0}),
            _box([50.0, 50.0, 280.0], {"x": 140.0, "y": 0.0, "z": 140.0}),
            _box([350.0, 60.0, 45.0], {"x": 0.0, "y": 0.0, "z": 295.0}),
        ],
        triangle_budget=1200,
        collision="box",
        material_role="wall",
        tags=["architecture", "arch", "gate"],
    ),

    # 13. Console
    "console": PropRecipe(
        name="console",
        parts=[
            _box([90.0, 60.0, 80.0], {"x": 0.0, "y": 0.0, "z": 40.0}),
            _box([84.0, 45.0, 35.0], {"x": 0.0, "y": -5.0, "z": 95.0}),
            _sphere(12.0, {"x": 25.0, "y": -18.0, "z": 115.0}),
        ],
        triangle_budget=1000,
        collision="box",
        material_role="accent",
        tags=["prop", "interactive", "console", "terminal"],
    ),

    # 14. Turret Base
    "turret_base": PropRecipe(
        name="turret_base",
        parts=[
            _cylinder(55.0, 35.0, {"x": 0.0, "y": 0.0, "z": 17.5}),
            _cylinder(38.0, 55.0, {"x": 0.0, "y": 0.0, "z": 60.0}),
            _sphere(36.0, {"x": 0.0, "y": 0.0, "z": 95.0}),
            _cylinder(10.0, 65.0, {"x": 35.0, "y": 0.0, "z": 95.0}),
        ],
        triangle_budget=1600,
        collision="capsule",
        material_role="prop",
        tags=["prop", "turret", "hazard", "defense"],
    ),
}

_SHAPE_TO_BASIC_MESH = {
    "box": "/Engine/BasicShapes/Cube.Cube",
    "cylinder": "/Engine/BasicShapes/Cylinder.Cylinder",
    "sphere": "/Engine/BasicShapes/Sphere.Sphere",
    "cone": "/Engine/BasicShapes/Cone.Cone",
}


def expand_prop_to_ops(
    actor_id: str,
    recipe_name: str,
    location: Tuple[float, float, float],
    yaw: float = 0.0,
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    color: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """Expand a PropRecipe into multi-primitive StaticMeshActor spawn_actor op args dicts."""
    recipe_key = "stylized_tree" if recipe_name == "tree" else recipe_name
    recipe = PROP_RECIPES.get(recipe_key)
    if recipe is None:
        return []

    rad = math.radians(yaw)
    cos_y, sin_y = math.cos(rad), math.sin(rad)
    sx_mult, sy_mult, sz_mult = float(scale[0]), float(scale[1]), float(scale[2])
    bx, by, bz = float(location[0]), float(location[1]), float(location[2])

    spawn_args_list: List[Dict[str, Any]] = []
    for idx, part in enumerate(recipe.parts):
        if part.get("op", "union") != "union":
            continue
        shape = part["shape"]
        mesh_path = _SHAPE_TO_BASIC_MESH.get(shape, "/Engine/BasicShapes/Cube.Cube")
        ploc = part.get("location", {"x": 0.0, "y": 0.0, "z": 0.0})
        ox = float(ploc.get("x", 0.0)) * sx_mult
        oy = float(ploc.get("y", 0.0)) * sy_mult
        oz = float(ploc.get("z", 0.0)) * sz_mult
        rx = ox * cos_y - oy * sin_y
        ry = ox * sin_y + oy * cos_y

        if shape == "box":
            sz = part["size"]
            pscale = {
                "x": round((float(sz[0]) / 100.0) * sx_mult, 3),
                "y": round((float(sz[1]) / 100.0) * sy_mult, 3),
                "z": round((float(sz[2]) / 100.0) * sz_mult, 3),
            }
        elif shape in ("cylinder", "cone"):
            r_cm = float(part["radius"])
            h_cm = float(part["height"])
            pscale = {
                "x": round((r_cm * 2.0 / 100.0) * sx_mult, 3),
                "y": round((r_cm * 2.0 / 100.0) * sy_mult, 3),
                "z": round((h_cm / 100.0) * sz_mult, 3),
            }
        else:  # sphere
            r_cm = float(part["radius"])
            pscale = {
                "x": round((r_cm * 2.0 / 100.0) * sx_mult, 3),
                "y": round((r_cm * 2.0 / 100.0) * sy_mult, 3),
                "z": round((r_cm * 2.0 / 100.0) * sz_mult, 3),
            }

        part_label = actor_id if idx == 0 else f"{actor_id}_part_{idx}"
        args: Dict[str, Any] = {
            "actor_class": "StaticMeshActor",
            "label": part_label,
            "static_mesh": mesh_path,
            "location": {
                "x": round(bx + rx, 1),
                "y": round(by + ry, 1),
                "z": round(bz + oz, 1),
            },
            "rotation": {"pitch": 0.0, "yaw": round(yaw, 1), "roll": 0.0},
            "scale": pscale,
        }
        if color is not None:
            args["color"] = list(color)
        spawn_args_list.append(args)

    return spawn_args_list
