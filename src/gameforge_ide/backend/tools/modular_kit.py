"""Modular building kit on a fixed grid (roadmap M12 step 3), for M8 v2 villages and dungeons.

Each piece is a list of Geometry Script parts for the ``mesh_generate_prop`` editor op, so the meshes are built
in-engine. Conventions: grid 400 cm; walls run along +X from the origin, centred on Y = 0, pivot at the bottom;
floors cover [0, grid] x [0, grid] with their top at Z = 0. Every piece's footprint is a whole number of grid
cells, so pieces snap when placed at grid multiples with 90° yaw steps. ``room_layout`` places pieces for a
rectangular room with one door.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GRID_CM = 400.0
WALL_HEIGHT_CM = 300.0
WALL_THICKNESS_CM = 20.0
FLOOR_THICKNESS_CM = 20.0
DOOR_W, DOOR_H = 120.0, 220.0
WINDOW_W, WINDOW_H, WINDOW_SILL = 120.0, 100.0, 100.0


@dataclass
class KitPiece:
    name: str
    parts: list[dict]
    footprint_cells: tuple[int, int]
    bounds_cm: tuple[float, float, float]
    collision: str = "complex_as_simple"
    tags: list[str] = field(default_factory=list)


def _box(size, x=0.0, y=0.0, z=0.0, op="union"):
    return {"shape": "box", "size": [float(v) for v in size], "location": {"x": x, "y": y, "z": z}, "op": op}


def _wall(name: str, openings: list[tuple[float, float, float]], grid: float) -> KitPiece:
    """openings: (width, height, sill z) cut through the wall centre."""
    parts = [_box((grid, WALL_THICKNESS_CM, WALL_HEIGHT_CM), x=grid / 2)]
    for w, h, sill in openings:
        parts.append(_box((w, WALL_THICKNESS_CM * 2, h), x=grid / 2, z=sill, op="subtract"))
    return KitPiece(name, parts, (1, 0), (grid, WALL_THICKNESS_CM, WALL_HEIGHT_CM), tags=["wall"])


def build_kit(grid: float = GRID_CM) -> dict[str, KitPiece]:
    if grid < 200 or grid % 100:
        raise ValueError("grid must be a multiple of 100 cm and at least 200 cm")
    pillar = WALL_THICKNESS_CM * 1.5
    pieces = [
        _wall("Wall", [], grid),
        _wall("WallDoor", [(DOOR_W, DOOR_H, 0.0)], grid),
        _wall("WallWindow", [(WINDOW_W, WINDOW_H, WINDOW_SILL)], grid),
        KitPiece("Floor", [_box((grid, grid, FLOOR_THICKNESS_CM), x=grid / 2, y=grid / 2, z=-FLOOR_THICKNESS_CM)],
                 (1, 1), (grid, grid, FLOOR_THICKNESS_CM), tags=["floor"]),
        KitPiece("Pillar", [_box((pillar, pillar, WALL_HEIGHT_CM))], (0, 0), (pillar, pillar, WALL_HEIGHT_CM),
                 collision="box", tags=["corner"]),
    ]
    for p in pieces:
        if p.name.startswith("Wall") and p.bounds_cm[0] != grid:
            raise AssertionError(f"{p.name} does not span one grid cell")
    return {p.name: p for p in pieces}


def validate_parts(piece: KitPiece) -> list[str]:
    """Cheap offline checks: positive sizes, openings fully inside the wall, nothing outside the bounds."""
    if not piece.parts:
        return ["piece has no parts"]
    errors = []
    bx, by, bz = piece.bounds_cm
    body = piece.parts[0]
    for i, part in enumerate(piece.parts):
        sx, sy, sz = part["size"]
        if min(sx, sy, sz) <= 0:
            errors.append(f"part {i}: non-positive size")
        loc = part["location"]
        if part["op"] == "subtract":
            if not (loc["x"] - sx / 2 >= body["location"]["x"] - bx / 2 + 1
                    and loc["x"] + sx / 2 <= body["location"]["x"] + bx / 2 - 1
                    and loc["z"] + sz <= bz - 1):
                errors.append(f"part {i}: opening would cut the wall edge or top")
    return errors


def room_layout(cells_x: int, cells_y: int, door_side: str = "south", door_cell: int = 0,
                grid: float = GRID_CM) -> list[dict]:
    """Placements {piece, location, yaw} for a closed rectangular room with one door."""
    if grid <= 0:
        raise ValueError(f"grid must be strictly positive, got {grid}")
    if cells_x < 1 or cells_y < 1:
        raise ValueError("room needs at least one cell per side")
    sides = {"south": cells_x, "north": cells_x, "west": cells_y, "east": cells_y}
    if door_side not in sides or not 0 <= door_cell < sides[door_side]:
        raise ValueError("door must be on an existing wall cell")
    out = []
    for i in range(cells_x):
        for j in range(cells_y):
            out.append({"piece": "Floor", "location": [i * grid, j * grid, 0.0], "yaw": 0.0})
    # Walls run along +X locally; yaw rotates them onto each side of the room.
    for side, n in sides.items():
        for k in range(n):
            if side == "south":
                loc, yaw = [k * grid, 0.0, 0.0], 0.0
            elif side == "north":
                loc, yaw = [(k + 1) * grid, cells_y * grid, 0.0], 180.0
            elif side == "west":
                loc, yaw = [0.0, (k + 1) * grid, 0.0], 270.0
            else:
                loc, yaw = [cells_x * grid, k * grid, 0.0], 90.0
            piece = "WallDoor" if (side == door_side and k == door_cell) else "Wall"
            out.append({"piece": piece, "location": loc, "yaw": yaw})
    for x in (0, cells_x):
        for y in (0, cells_y):
            out.append({"piece": "Pillar", "location": [x * grid, y * grid, 0.0], "yaw": 0.0})
    return out
