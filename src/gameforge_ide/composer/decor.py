"""Themed set dressing for composed levels.

Every layout used to be a floor, four walls and a few identical cubes. ``decorate`` adds a deterministic, theme-specific
decoration pass (trees, rocks, crystals, tombstones, torches with lights, neon blocks, ...) built only from engine basic
shapes, so it works in a blank project. Decoration is kept out of gameplay space: away from the player start, placed
actors, cover and the course line, and never inside the arena's fighting area.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .model import LevelPlan, OpCall
from .theme import DECOR, DecorPiece, Theme

DECOR_LABEL_PREFIX = "GF_Decor"
MAX_DECOR_PIECES = 40


def _clear(x: float, y: float, r: float, avoid: Sequence[Tuple[float, float, float]]) -> bool:
    return all(math.hypot(x - ax, y - ay) >= r + ar for ax, ay, ar in avoid)


def _piece_ops(piece: DecorPiece, theme: Theme, idx: int, x: float, y: float, z: float, yaw: float,
               scale: float, snap: bool) -> List[OpCall]:
    ops: List[OpCall] = []
    rad = math.radians(yaw)
    cos_y, sin_y = math.cos(rad), math.sin(rad)
    for p_i, (shape, role, (ox, oy, oz), (sx, sy, sz)) in enumerate(piece.parts):
        rx = (ox * cos_y - oy * sin_y) * scale
        ry = (ox * sin_y + oy * cos_y) * scale
        args: Dict[str, Any] = {
            "actor_class": "StaticMeshActor",
            "label": f"{DECOR_LABEL_PREFIX}_{idx}_{p_i}",
            "static_mesh": f"/Engine/BasicShapes/{shape}.{shape}",
            "location": {"x": round(x + rx, 1), "y": round(y + ry, 1), "z": round(z + oz * scale, 1)},
            "rotation": {"pitch": 0.0, "yaw": round(yaw, 1), "roll": 0.0},
            "scale": {"x": round(sx * scale, 3), "y": round(sy * scale, 3), "z": round(sz * scale, 3)},
            "color": theme.color(role),
        }
        if snap:
            args["snap_to_ground"] = True
            args["ground_offset"] = round(oz * scale, 1)
        ops.append(OpCall(op="spawn_actor", args=args, purpose=f"Decor: {piece.name} part {p_i}"))
    if piece.light:
        role, intensity = piece.light
        top = max(oz for _s, _r, (_ox, _oy, oz), _sc in piece.parts) * scale
        largs: Dict[str, Any] = {
            "actor_class": "PointLight",
            "label": f"{DECOR_LABEL_PREFIX}_{idx}_light",
            "location": {"x": round(x, 1), "y": round(y, 1), "z": round(z + top + 30.0, 1)},
            "light_intensity": float(intensity),
            "light_color": theme.color(role),
        }
        if snap:
            largs["snap_to_ground"] = True
            largs["ground_offset"] = round(top + 30.0, 1)
        ops.append(OpCall(op="spawn_actor", args=largs, purpose=f"Decor light: {piece.name}"))
    return ops


def _avoid_from_plan(plan: LevelPlan, extra: Iterable[Tuple[float, float, float]] = ()) -> List[Tuple[float, float, float]]:
    avoid: List[Tuple[float, float, float]] = [(plan.player_start[0], plan.player_start[1], 500.0)]
    for a in plan.actors:
        avoid.append((a.location[0], a.location[1], 320.0))
    for op in plan.geometry_ops:
        args = op.args if isinstance(op.args, dict) else {}
        label = str(args.get("label", "")).lower()
        if op.op != "spawn_actor" or "floor" in label or "ground" in label or "safety" in label:
            continue
        loc = args.get("location") or {}
        sc = args.get("scale") or {}
        r = math.hypot(float(sc.get("x", 1.0)) * 50.0, float(sc.get("y", 1.0)) * 50.0) + 80.0
        if r < 2500.0:   # very long walls are handled by the layout-specific rings
            avoid.append((float(loc.get("x", 0.0)), float(loc.get("y", 0.0)), r))
    avoid.extend(extra)
    return avoid


def decorate(plan: LevelPlan, layout: str, theme: Theme, rng: random.Random, density: float = 1.0) -> List[OpCall]:
    """Return decoration OpCalls for ``plan`` (does not modify the plan)."""
    if density <= 0.0:
        return []
    names = [n for n in theme.decor if n in DECOR] or ["rock"]
    center, extent = plan.nav_bounds
    cx, cy = center[0], center[1]
    hx, hy = max(500.0, extent[0]), max(500.0, extent[1])
    avoid = _avoid_from_plan(plan)
    # Extra clearance around bomb sites and key objective actors
    for a in plan.actors:
        if "bomb_site" in str(a.runtime_class).lower() or any("bomb" in t.lower() for t in a.tags):
            avoid.append((a.location[0], a.location[1], 550.0))
    spots: List[Tuple[float, float, float, bool]] = []   # x, y, z, snap
    extra_ops: List[OpCall] = []

    if layout in ("arena", "tactical_fps"):
        # A ring of set dressing just inside the walls keeps the fighting area clear.
        half_x, half_y = hx - 200.0, hy - 200.0
        n = int(18 * density)
        for i in range(n * 3):
            if len(spots) >= n:
                break
            side = rng.randrange(4)
            t = rng.uniform(-0.9, 0.9)
            inset = rng.uniform(150.0, 380.0)
            if side == 0:
                x, y = cx + half_x - inset, cy + t * half_y
            elif side == 1:
                x, y = cx - half_x + inset, cy + t * half_y
            elif side == 2:
                x, y = cx + t * half_x, cy + half_y - inset
            else:
                x, y = cx + t * half_x, cy - half_y + inset
            if _clear(x, y, 150.0, avoid + [(sx, sy, 200.0) for sx, sy, _z, _s in spots]):
                spots.append((x, y, 0.0, False))
    elif layout == "open_world":
        n = int(MAX_DECOR_PIECES * density)
        for _ in range(n * 4):
            if len(spots) >= n:
                break
            x = cx + rng.uniform(-hx * 0.92, hx * 0.92)
            y = cy + rng.uniform(-hy * 0.92, hy * 0.92)
            if _clear(x, y, 200.0, avoid + [(sx, sy, 350.0) for sx, sy, _z, _s in spots]):
                spots.append((x, y, 0.0, True))
    elif layout in ("board", "lanes"):
        # Frame the table: a loose ring of props outside the play surface.
        radius = max(hx, hy) + 600.0
        n = int(14 * density)
        for i in range(n):
            ang = (i / n) * 2.0 * math.pi + rng.uniform(-0.15, 0.15)
            r = radius + rng.uniform(0.0, 500.0)
            spots.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r, 0.0, False))
    elif layout == "rooms":
        floors = [op.args.get("location", {}) for op in plan.geometry_ops
                  if op.op == "spawn_actor" and "Dungeon_Floor" in str(op.args.get("label", ""))]
        cells = {(round(float(f.get("x", 0)) / 400.0), round(float(f.get("y", 0)) / 400.0)) for f in floors}
        interior = [c for c in cells if all((c[0] + dx, c[1] + dy) in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1))]
        rng.shuffle(interior)
        for c in interior[: int(14 * density)]:
            x, y = c[0] * 400.0 + rng.uniform(-60, 60), c[1] * 400.0 + rng.uniform(-60, 60)
            if _clear(x, y, 120.0, avoid + [(sx, sy, 500.0) for sx, sy, _z, _s in spots]):
                spots.append((x, y, 0.0, False))
    elif layout == "course":
        # Columns under the floating platforms and props on islands beside the course line.
        for op in plan.geometry_ops:
            label = str(op.args.get("label", ""))
            if op.op != "spawn_actor" or not label.startswith("GF_Platform_") or rng.random() > 0.6 * density:
                continue
            loc = op.args.get("location", {})
            top = float(loc.get("z", 0.0)) - 30.0
            bottom = -450.0
            height = max(50.0, top - bottom)
            extra_ops.append(OpCall(op="spawn_actor", purpose="Decor: platform column", args={
                "actor_class": "StaticMeshActor",
                "label": f"{DECOR_LABEL_PREFIX}_Column_{label.rsplit('_', 1)[-1]}",
                "static_mesh": "/Engine/BasicShapes/Cylinder.Cylinder",
                "location": {"x": float(loc.get("x", 0.0)), "y": float(loc.get("y", 0.0)),
                             "z": round(bottom + height / 2.0, 1)},
                "scale": {"x": 1.1, "y": 1.1, "z": round(height / 100.0, 2)},
                "color": theme.color("wall_dark"),
            }))
        for op in plan.geometry_ops:
            label = str(op.args.get("label", ""))
            if op.op == "spawn_actor" and (label == "GF_Platform_Start" or
                                           (label.startswith("GF_Platform_") and rng.random() < 0.25 * density)):
                loc = op.args.get("location", {})
                side = rng.choice((-1.0, 1.0))
                spots.append((float(loc.get("x", 0.0)) + rng.uniform(-60, 60),
                              float(loc.get("y", 0.0)) + side * rng.uniform(700.0, 1100.0), -450.0, False))
    else:
        # Fallback perimeter ring for arbitrary or custom synthesized layouts
        half_x, half_y = hx - 200.0, hy - 200.0
        n = int(16 * density)
        for _ in range(n * 3):
            if len(spots) >= n:
                break
            side = rng.randrange(4)
            t = rng.uniform(-0.85, 0.85)
            inset = rng.uniform(150.0, 350.0)
            if side == 0:
                x, y = cx + half_x - inset, cy + t * half_y
            elif side == 1:
                x, y = cx - half_x + inset, cy + t * half_y
            elif side == 2:
                x, y = cx + t * half_x, cy + half_y - inset
            else:
                x, y = cx + t * half_x, cy - half_y + inset
            if _clear(x, y, 150.0, avoid + [(sx, sy, 200.0) for sx, sy, _z, _s in spots]):
                spots.append((x, y, 0.0, False))

    ops: List[OpCall] = list(extra_ops)
    for idx, (x, y, z, snap) in enumerate(spots[:MAX_DECOR_PIECES]):
        piece = DECOR[rng.choice(names)]
        scale = rng.uniform(0.8, 1.35) if layout != "course" else rng.uniform(1.2, 1.8)
        ops.extend(_piece_ops(piece, theme, idx, x, y, z, rng.uniform(0.0, 360.0), scale, snap))
    return ops

