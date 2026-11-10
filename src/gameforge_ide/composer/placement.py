"""Composer placement algorithms (WI-6.3).

Poisson-disk scatter inside polygon bounds with avoidance discs,
and arc-length uniform distribution along paths.
"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple


def is_point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """Ray-casting algorithm with bounding box early exit for point-in-polygon check."""
    if not polygon or len(polygon) < 3:
        return False
    x, y = point
    # Fast bounding box rejection
    min_x = min(p[0] for p in polygon)
    max_x = max(p[0] for p in polygon)
    min_y = min(p[1] for p in polygon)
    max_y = max(p[1] for p in polygon)
    if x < min_x or x > max_x or y < min_y or y > max_y:
        return False

    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def scatter(
    area_polygon: List[Tuple[float, float]],
    n: int,
    min_spacing_cm: float,
    rng: random.Random,
    avoid: Optional[List[Tuple[float, float, float]]] = None,  # (x, y, radius_cm)
    max_attempts: int = 30,
) -> Tuple[List[Tuple[float, float]], Optional[str]]:
    """Poisson-disk scatter sampling within a 2D bounding polygon.

    Returns:
        (points, warning_message_if_incomplete)
    """
    if n <= 0:
        return [], None
    if not area_polygon or len(area_polygon) < 3:
        return [], "area_polygon must contain at least 3 points"

    avoid = avoid or []

    # Compute bounding box
    xs = [p[0] for p in area_polygon]
    ys = [p[1] for p in area_polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    points: List[Tuple[float, float]] = []
    cell_size = max(10.0, min_spacing_cm / 1.41421356)
    grid: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}

    def get_cell(x_pos: float, y_pos: float) -> Tuple[int, int]:
        return int(x_pos // cell_size), int(y_pos // cell_size)

    def add_point(pt: Tuple[float, float]) -> None:
        points.append(pt)
        c = get_cell(pt[0], pt[1])
        grid.setdefault(c, []).append(pt)

    def is_valid(pt: Tuple[float, float]) -> bool:
        if not is_point_in_polygon(pt, area_polygon):
            return False
        # Avoid zones
        for ax, ay, ar in avoid:
            dist_sq = (pt[0] - ax) ** 2 + (pt[1] - ay) ** 2
            if dist_sq < ar ** 2:
                return False
        # Spatial acceleration neighbor query
        cx, cy = get_cell(pt[0], pt[1])
        min_spacing_sq = min_spacing_cm ** 2
        for dcx in range(-2, 3):
            for dcy in range(-2, 3):
                cell_pts = grid.get((cx + dcx, cy + dcy))
                if cell_pts:
                    for px, py in cell_pts:
                        if (pt[0] - px) ** 2 + (pt[1] - py) ** 2 < min_spacing_sq:
                            return False
        return True

    # Initial seed point
    active: List[Tuple[float, float]] = []
    attempts = 0
    while len(points) < 1 and attempts < max_attempts * 10:
        attempts += 1
        rx = rng.uniform(min_x, max_x)
        ry = rng.uniform(min_y, max_y)
        cand = (rx, ry)
        if is_valid(cand):
            add_point(cand)
            active.append(cand)
            break

    if not points:
        return [], f"placed 0 of {n} points; free area is too small or obstructed"

    # Bridson Poisson-disk expansion
    while active and len(points) < n:
        idx = rng.randint(0, len(active) - 1)
        base = active[idx]
        found = False
        for _ in range(max_attempts):
            angle = rng.uniform(0, 2 * math.pi)
            rad = rng.uniform(min_spacing_cm, 2 * min_spacing_cm)
            cand = (base[0] + rad * math.cos(angle), base[1] + rad * math.sin(angle))
            if is_valid(cand):
                add_point(cand)
                active.append(cand)
                found = True
                if len(points) >= n:
                    break
        if not found:
            active.pop(idx)

    # Fallback rejection sampling if grid ran out of active points
    if len(points) < n:
        for _ in range(max_attempts * (n - len(points)) * 5):
            rx = rng.uniform(min_x, max_x)
            ry = rng.uniform(min_y, max_y)
            cand = (rx, ry)
            if is_valid(cand):
                add_point(cand)
                if len(points) >= n:
                    break

    # Deterministic grid scan fallback with relaxed spacing if random sampling did not place all points
    if len(points) < n:
        relaxed_spacing_sq = (min_spacing_cm * 0.45) ** 2
        grid_steps = max(8, int(math.ceil(math.sqrt(n * 4))))
        dx = (max_x - min_x) / max(1, grid_steps)
        dy = (max_y - min_y) / max(1, grid_steps)
        for gx_i in range(1, grid_steps):
            for gy_i in range(1, grid_steps):
                if len(points) >= n:
                    break
                cand = (min_x + gx_i * dx, min_y + gy_i * dy)
                if not is_point_in_polygon(cand, area_polygon):
                    continue
                if any((cand[0] - ax) ** 2 + (cand[1] - ay) ** 2 < (ar * 0.75) ** 2 for ax, ay, ar in avoid):
                    continue
                if any((cand[0] - px) ** 2 + (cand[1] - py) ** 2 < relaxed_spacing_sq for px, py in points):
                    continue
                add_point(cand)

    warning = None
    if len(points) < n:
        warning = f"placed {len(points)} of {n} points; level too small or congested"

    return points, warning


def along_path(points: List[Tuple[float, float, float]], n: int) -> List[Tuple[float, float, float]]:
    """Distribute n points uniformly by arc length along a 3D piecewise linear path."""
    if n <= 0 or not points:
        return []
    if n == 1:
        return [points[0]]
    if len(points) == 1:
        return [points[0]] * n

    # Compute cumulative arc lengths
    cum_dist = [0.0]
    for i in range(1, len(points)):
        d = math.sqrt(
            (points[i][0] - points[i - 1][0]) ** 2
            + (points[i][1] - points[i - 1][1]) ** 2
            + (points[i][2] - points[i - 1][2]) ** 2
        )
        cum_dist.append(cum_dist[-1] + d)

    total_length = cum_dist[-1]
    if total_length < 1e-4:
        return [points[0]] * n

    step = total_length / (n - 1)
    res: List[Tuple[float, float, float]] = []

    curr_seg = 0
    for i in range(n):
        target_dist = i * step
        while curr_seg < len(cum_dist) - 2 and cum_dist[curr_seg + 1] < target_dist:
            curr_seg += 1

        seg_start = cum_dist[curr_seg]
        seg_end = cum_dist[curr_seg + 1]
        seg_len = seg_end - seg_start
        if seg_len < 1e-4:
            res.append(points[curr_seg])
        else:
            alpha = (target_dist - seg_start) / seg_len
            px = points[curr_seg][0] + alpha * (points[curr_seg + 1][0] - points[curr_seg][0])
            py = points[curr_seg][1] + alpha * (points[curr_seg + 1][1] - points[curr_seg][1])
            pz = points[curr_seg][2] + alpha * (points[curr_seg + 1][2] - points[curr_seg][2])
            res.append((px, py, pz))

    return res


# Backward-compatible alias
distribute_along_path = along_path

