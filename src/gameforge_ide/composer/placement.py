"""Composer placement algorithms (WI-6.3).

Poisson-disk scatter inside polygon bounds with avoidance discs,
and arc-length uniform distribution along paths.
"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple


def is_point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """Ray-casting algorithm for point-in-polygon check."""
    x, y = point
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

    avoid = avoid or []

    # Compute bounding box
    xs = [p[0] for p in area_polygon]
    ys = [p[1] for p in area_polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    points: List[Tuple[float, float]] = []

    def is_valid(pt: Tuple[float, float]) -> bool:
        if not is_point_in_polygon(pt, area_polygon):
            return False
        # Avoid zones
        for ax, ay, ar in avoid:
            dist_sq = (pt[0] - ax) ** 2 + (pt[1] - ay) ** 2
            if dist_sq < ar ** 2:
                return False
        # Inter-point spacing
        for px, py in points:
            dist_sq = (pt[0] - px) ** 2 + (pt[1] - py) ** 2
            if dist_sq < min_spacing_cm ** 2:
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
            points.append(cand)
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
                points.append(cand)
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
                points.append(cand)
                if len(points) >= n:
                    break

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
