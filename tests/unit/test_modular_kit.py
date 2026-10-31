"""Roadmap M12 step 3: modular building kit on a 400 cm grid."""

import math

import pytest

from src.gameforge_ide.backend.tools.modular_kit import GRID_CM, build_kit, room_layout, validate_parts


def test_kit_pieces_are_grid_sized_and_valid():
    kit = build_kit()
    assert {"Wall", "WallDoor", "WallWindow", "Floor", "Pillar"} <= set(kit)
    for name, piece in kit.items():
        assert validate_parts(piece) == [], name
        if name.startswith("Wall"):
            assert piece.bounds_cm[0] == GRID_CM and piece.footprint_cells == (1, 0)
    assert kit["Floor"].bounds_cm[:2] == (GRID_CM, GRID_CM)
    assert [p["op"] for p in kit["WallDoor"].parts] == ["union", "subtract"]


def test_opening_that_cuts_the_wall_edge_is_rejected():
    piece = build_kit()["WallWindow"]
    piece.parts[1]["size"][0] = GRID_CM + 50  # wider than the wall
    assert any("opening" in e for e in validate_parts(piece))


def test_room_layout_is_closed_with_one_door():
    layout = room_layout(3, 2, door_side="north", door_cell=1)
    pieces = [p["piece"] for p in layout]
    assert pieces.count("Floor") == 6 and pieces.count("WallDoor") == 1
    assert pieces.count("Wall") + pieces.count("WallDoor") == 2 * (3 + 2)
    assert pieces.count("Pillar") == 4
    # Every wall lies on the room boundary, snapped to the grid, with a 90° yaw step.
    for p in layout:
        x, y, _ = p["location"]
        assert x % GRID_CM == 0 and y % GRID_CM == 0 and p["yaw"] % 90 == 0
        if p["piece"].startswith("Wall"):
            yaw = math.radians(p["yaw"])
            end = (x + GRID_CM * math.cos(yaw), y + GRID_CM * math.sin(yaw))
            on_boundary = lambda px, py: (abs(px) < 1e-6 or abs(px - 3 * GRID_CM) < 1e-6  # noqa: E731
                                          or abs(py) < 1e-6 or abs(py - 2 * GRID_CM) < 1e-6)
            assert on_boundary(x, y) and on_boundary(*end)
            assert -1e-6 <= min(x, end[0]) and max(x, end[0]) <= 3 * GRID_CM + 1e-6
            assert -1e-6 <= min(y, end[1]) and max(y, end[1]) <= 2 * GRID_CM + 1e-6


def test_wall_segments_cover_each_side_exactly_once():
    layout = room_layout(2, 2)
    segments = set()
    for p in layout:
        if p["piece"].startswith("Wall"):
            x, y, _ = p["location"]
            yaw = math.radians(p["yaw"])
            a = (round(x), round(y))
            b = (round(x + GRID_CM * math.cos(yaw)), round(y + GRID_CM * math.sin(yaw)))
            seg = tuple(sorted([a, b]))
            assert seg not in segments
            segments.add(seg)
    assert len(segments) == 8


@pytest.mark.parametrize("kw", [{"cells_x": 0, "cells_y": 1}, {"cells_x": 2, "cells_y": 2, "door_cell": 2},
                                {"cells_x": 1, "cells_y": 1, "door_side": "up"}])
def test_invalid_rooms_rejected(kw):
    with pytest.raises(ValueError):
        room_layout(**kw)


def test_grid_must_be_whole_metres():
    with pytest.raises(ValueError):
        build_kit(grid=350)
