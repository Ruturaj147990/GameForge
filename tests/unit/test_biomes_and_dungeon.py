"""Roadmap M8 v2 steps 2–4: biome/lighting presets and the seeded dungeon generator."""

import math

import pytest

from src.gameforge_ide.backend.tools import biomes
from src.gameforge_ide.backend.tools.dungeon_layout import generate, is_connected, kit_placements
from src.gameforge_ide.backend.tools.modular_kit import GRID_CM


@pytest.mark.parametrize("name", sorted(biomes.BIOMES))
def test_every_biome_produces_consistent_op_arguments(name):
    land = biomes.landscape_args(name, 7, "/Game/W/LayerInfo", "/Game/W/M_Land")
    mat = biomes.layer_material_graph(name, "/Game/W/M_Land")
    layer_names = [l["name"] for l in land["paint_layers"]]
    assert [l["name"] for l in mat["nodes"][0]["props"]["layers"]] == layer_names
    assert {e["input"] for e in mat["edges"]} == {f"Layer {n}" for n in layer_names}
    graphs = biomes.scatter_graphs(name, 7, "/Game/W/PCG", 6000)
    assert graphs and all(g["nodes"][1]["settings"] == "PCGSurfaceSamplerSettings" for g in graphs)
    assert len({g["label"] for g in graphs}) == len(graphs)
    rig = biomes.lighting_rig(biomes.BIOMES[name].lighting)
    assert any(a["actor_class"] == "DirectionalLight" for a in rig)


def test_seed_changes_scatter_seed_only():
    a, b = biomes.scatter_graphs("forest", 1, "/G", 6000), biomes.scatter_graphs("forest", 2, "/G", 6000)
    assert [g["seed"] for g in a] != [g["seed"] for g in b]
    assert [g["nodes"] for g in a] == [g["nodes"] for g in b]


def test_exclusion_routes_samples_through_binary_difference():
    for g in biomes.scatter_graphs("forest", 3, "/G", 6000, exclusion_tag="GF_PCGExclude"):
        ids = {n["id"]: n for n in g["nodes"]}
        edges = {(e["from"], e["to"], e["to_pin"]) for e in g["edges"]}
        assert ("sample", "diff", "Source") in edges and ("exclude", "diff", "Differences") in edges
        assert ("diff", "density", "In") in edges
        assert not any(e["from"] == "sample" and e["to"] == "density" for e in g["edges"])  # no bypass
        sel = ids["exclude"]["props"]["actor_selector"]
        assert sel["actor_selection_tag"] == "GF_PCGExclude" and sel["select_multiple"] is True
        assert ids["diff"]["props"]["density_function"] == {"__enum__": "PCGDifferenceDensityFunction.BINARY"}
    plain = biomes.scatter_graphs("forest", 3, "/G", 6000)
    assert all("diff" not in {n["id"] for n in g["nodes"]} for g in plain)


def test_bad_biome_definition_is_rejected():
    bad = biomes.Biome("x", "Valley", 1000, (("A", "low", (0, 0, 0)), ("B", "low", (0, 0, 0))), 0.8, 40, (),
                       "day_clear")
    with pytest.raises(ValueError):
        biomes._check(bad)


@pytest.mark.parametrize("seed", range(12))
def test_dungeon_is_connected_non_overlapping_and_deterministic(seed):
    d = generate(seed)
    assert d == generate(seed)
    assert is_connected(d["cells"])
    rooms = d["rooms"]
    assert all(not a.overlaps(b, margin=0) for i, a in enumerate(rooms) for b in rooms[i + 1:])
    assert all(0 <= x < d["width"] and 0 <= y < d["height"] for x, y in d["cells"])


def test_kit_placements_enclose_every_cell():
    cells = generate(3)["cells"]
    placements = kit_placements(cells)
    assert sum(p["piece"] == "Floor" for p in placements) == len(cells)
    occupied = set(cells)
    walls = set()
    for p in placements:
        if p["piece"] != "Wall":
            continue
        x, y, _ = p["location"]
        yaw = math.radians(p["yaw"])
        a = (round(x / GRID_CM), round(y / GRID_CM))
        b = (round((x + GRID_CM * math.cos(yaw)) / GRID_CM), round((y + GRID_CM * math.sin(yaw)) / GRID_CM))
        walls.add(tuple(sorted([a, b])))
    # Every boundary edge of the occupied region carries exactly one wall, and no interior edge does.
    boundary = set()
    for x, y in occupied:
        for (dx, dy), edge in (((0, -1), ((x, y), (x + 1, y))), ((0, 1), ((x, y + 1), (x + 1, y + 1))),
                               ((-1, 0), ((x, y), (x, y + 1))), ((1, 0), ((x + 1, y), (x + 1, y + 1)))):
            if (x + dx, y + dy) not in occupied:
                boundary.add(tuple(sorted(edge)))
    assert walls == boundary


def test_dungeon_rejects_bad_parameters():
    with pytest.raises(ValueError):
        generate(1, width=2)
