"""Seeded grid dungeon generator (roadmap M8 v2 step 3) that emits M12 modular-kit placements.

Rooms are axis-aligned rectangles of grid cells that never overlap; a spanning tree of L-shaped corridors connects
them, so every room is reachable. ``kit_placements`` turns the occupied cells into Floor pieces and puts a Wall
on every cell edge between an occupied and an empty cell, in the same placement format as
``modular_kit.room_layout``.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from ...backend.tools.modular_kit import GRID_CM


@dataclass(frozen=True)
class Room:
    x: int
    y: int
    w: int
    h: int

    def cells(self) -> set[tuple[int, int]]:
        return {(i, j) for i in range(self.x, self.x + self.w) for j in range(self.y, self.y + self.h)}

    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def overlaps(self, other: "Room", margin: int = 1) -> bool:
        return not (self.x + self.w + margin <= other.x or other.x + other.w + margin <= self.x
                    or self.y + self.h + margin <= other.y or other.y + other.h + margin <= self.y)


def generate(seed: int, width: int = 12, height: int = 12, rooms: int = 5, min_size: int = 2,
             max_size: int = 4, attempts: int = 200) -> dict:
    if width < 4 or height < 4 or rooms < 1 or min_size < 1 or max_size < min_size:
        raise ValueError("invalid dungeon parameters")
    rng = random.Random(seed)
    placed: list[Room] = []
    for _ in range(attempts):
        if len(placed) == rooms:
            break
        w, h = rng.randint(min_size, max_size), rng.randint(min_size, max_size)
        if w > width or h > height:
            continue
        room = Room(rng.randint(0, width - w), rng.randint(0, height - h), w, h)
        if not any(room.overlaps(o) for o in placed):
            placed.append(room)
    if not placed:
        raise ValueError("no room fits the grid")
    cells: set[tuple[int, int]] = set()
    for r in placed:
        cells |= r.cells()
    corridors = []
    # Connect rooms in a chain sorted by centre (a spanning tree), each link an L-shaped corridor.
    order = sorted(placed, key=lambda r: r.center())
    for a, b in zip(order, order[1:]):
        (ax, ay), (bx, by) = a.center(), b.center()
        path = [(x, ay) for x in range(min(ax, bx), max(ax, bx) + 1)]
        path += [(bx, y) for y in range(min(ay, by), max(ay, by) + 1)]
        corridors.append(path)
        cells |= set(path)
    return {"seed": seed, "width": width, "height": height, "rooms": placed, "corridors": corridors,
            "cells": sorted(cells)}


def is_connected(cells: list[tuple[int, int]] | set[tuple[int, int]]) -> bool:
    cells = set(cells)
    if not cells:
        return False
    start = next(iter(cells))
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in cells and n not in seen:
                seen.add(n)
                queue.append(n)
    return seen == cells


def kit_placements(cells: list[tuple[int, int]], grid: float = GRID_CM) -> list[dict]:
    occupied = set(cells)
    out = [{"piece": "Floor", "location": [x * grid, y * grid, 0.0], "yaw": 0.0} for x, y in sorted(occupied)]
    for x, y in sorted(occupied):
        # Wall pieces run along +X from their pivot (see modular_kit); yaw rotates them onto each cell edge.
        if (x, y - 1) not in occupied:
            out.append({"piece": "Wall", "location": [x * grid, y * grid, 0.0], "yaw": 0.0})
        if (x, y + 1) not in occupied:
            out.append({"piece": "Wall", "location": [(x + 1) * grid, (y + 1) * grid, 0.0], "yaw": 180.0})
        if (x - 1, y) not in occupied:
            out.append({"piece": "Wall", "location": [x * grid, (y + 1) * grid, 0.0], "yaw": 270.0})
        if (x + 1, y) not in occupied:
            out.append({"piece": "Wall", "location": [(x + 1) * grid, y * grid, 0.0], "yaw": 90.0})
    return out
