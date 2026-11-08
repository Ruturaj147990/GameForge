"""Biome presets (roadmap M8 v2 step 2) and lighting presets (step 4).

A biome turns one seed into concrete arguments for the editor ops that are already verified:
``landscape_create`` (heightfield + paint layers), ``material_build_graph`` (LandscapeLayerBlend material),
``pcg_build_graph`` (surface-sampled scatter) and ``spawn_actor`` (lighting rig). Nothing here talks to Unreal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BASIC = "/Engine/BasicShapes"


@dataclass(frozen=True)
class ScatterSpec:
    name: str
    mesh: str
    points_per_m2: float
    density_min: float = 0.3  # PCG density filter lower bound: higher = sparser
    max_height_norm: float = 1.0  # keep out of the snow line etc. (fraction of the elevation range)


@dataclass(frozen=True)
class Biome:
    name: str
    terrain_type: str
    elevation_scale: float
    layers: tuple[tuple[str, str, tuple[float, float, float]], ...]  # (layer name, rule, colour)
    high_start: float
    steep_start_cm_per_quad: float
    scatter: tuple[ScatterSpec, ...]
    lighting: str
    tags: tuple[str, ...] = field(default_factory=tuple)


BIOMES: dict[str, Biome] = {b.name: b for b in [
    # Forest thresholds lowered 2026-10-31 (high 0.80 → 0.62, steep 45 → 22 cm/quad): the village demo measured
    # mean layer weights Grass 251 / Rock 0.2 / Moss 3.5, so rock and moss never showed.
    Biome("forest", "Valley", 1800.0,
          (("Grass", "low", (0.10, 0.30, 0.06)), ("Rock", "steep", (0.25, 0.24, 0.22)),
           ("Moss", "high", (0.16, 0.26, 0.10))),
          0.62, 22.0,
          (ScatterSpec("Trees", f"{BASIC}/Cone.Cone", 0.020, 0.35, 0.85),
           ScatterSpec("Bushes", f"{BASIC}/Sphere.Sphere", 0.015, 0.55, 0.9)),
          "day_clear", ("vegetated",)),
    Biome("desert", "Plateau", 1500.0,
          (("Sand", "low", (0.76, 0.62, 0.38)), ("Rock", "steep", (0.55, 0.36, 0.24)),
           ("Dune", "high", (0.84, 0.72, 0.48))),
          0.82, 55.0,
          (ScatterSpec("Cacti", f"{BASIC}/Cylinder.Cylinder", 0.004, 0.6, 0.8),
           ScatterSpec("Boulders", f"{BASIC}/Sphere.Sphere", 0.003, 0.7, 1.0)),
          "day_harsh", ("arid",)),
    Biome("island", "Valley", 1200.0,
          (("Sand", "low", (0.80, 0.72, 0.52)), ("Grass", "high", (0.14, 0.40, 0.10)),
           ("Rock", "steep", (0.30, 0.29, 0.27))),
          0.45, 50.0,
          (ScatterSpec("Palms", f"{BASIC}/Cylinder.Cylinder", 0.006, 0.5, 0.95),),
          "day_clear", ("coastal",)),
    Biome("mountain", "Mountains", 4000.0,
          (("Grass", "low", (0.10, 0.32, 0.06)), ("Rock", "steep", (0.22, 0.21, 0.20)),
           ("Snow", "high", (0.85, 0.87, 0.90))),
          0.86, 40.0,
          (ScatterSpec("Pines", f"{BASIC}/Cone.Cone", 0.010, 0.4, 0.7),),
          "overcast", ("alpine",)),
]}

LIGHTING: dict[str, list[dict]] = {
    "day_clear": [
        {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 6.0,
         "rotation": {"pitch": -45, "yaw": 35, "roll": 0}},
        {"actor_class": "SkyLight", "label": "GF_SkyLight"},
        {"actor_class": "SkyAtmosphere", "label": "GF_SkyAtmosphere"},
        {"actor_class": "ExponentialHeightFog", "label": "GF_Fog"},
        {"actor_class": "VolumetricCloud", "label": "GF_Clouds"},
    ],
    "day_harsh": [
        {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 9.0,
         "rotation": {"pitch": -70, "yaw": 10, "roll": 0}},
        {"actor_class": "SkyLight", "label": "GF_SkyLight"},
        {"actor_class": "SkyAtmosphere", "label": "GF_SkyAtmosphere"},
    ],
    "overcast": [
        {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 2.0,
         "rotation": {"pitch": -30, "yaw": 200, "roll": 0}},
        {"actor_class": "SkyLight", "label": "GF_SkyLight"},
        {"actor_class": "SkyAtmosphere", "label": "GF_SkyAtmosphere"},
        {"actor_class": "ExponentialHeightFog", "label": "GF_Fog"},
        {"actor_class": "VolumetricCloud", "label": "GF_Clouds"},
    ],
    # P6 Composer presets (WI-6.4)
    "dusk": [
        {"actor_class": "DirectionalLight", "label": "GF_Sun", "light_intensity": 2.5,
         "rotation": {"pitch": -8, "yaw": 250, "roll": 0}},
        {"actor_class": "SkyLight", "label": "GF_SkyLight"},
        {"actor_class": "SkyAtmosphere", "label": "GF_SkyAtmosphere"},
        {"actor_class": "ExponentialHeightFog", "label": "GF_Fog"},
    ],
    "night": [
        {"actor_class": "DirectionalLight", "label": "GF_Moon", "light_intensity": 0.6,
         "rotation": {"pitch": -35, "yaw": 20, "roll": 0}},
        {"actor_class": "SkyLight", "label": "GF_SkyLight", "light_intensity": 0.4},
        {"actor_class": "ExponentialHeightFog", "label": "GF_Fog"},
    ],
    "indoor": [
        {"actor_class": "DirectionalLight", "label": "GF_Indoor_Key", "light_intensity": 1.5,
         "rotation": {"pitch": -50, "yaw": 45, "roll": 0}},
        {"actor_class": "SkyLight", "label": "GF_SkyLight", "light_intensity": 1.0},
        {"actor_class": "PointLight", "label": "GF_Indoor_Fill", "light_intensity": 5000.0,
         "location": {"x": 0.0, "y": 0.0, "z": 250.0}},
    ],
}


def _check(biome: Biome) -> None:
    rules = [rule for _, rule, _ in biome.layers]
    if len(set(rules)) != len(rules) or not set(rules) <= {"low", "steep", "high"}:
        raise ValueError(f"{biome.name}: layer rules must be distinct members of low/steep/high")
    if biome.lighting not in LIGHTING:
        raise ValueError(f"{biome.name}: unknown lighting preset {biome.lighting}")


def landscape_args(biome: str, seed: int, layer_info_path: str, material_path: str) -> dict:
    b = BIOMES[biome]
    _check(b)
    return {"terrain_type": b.terrain_type, "elevation_scale": b.elevation_scale, "seed": int(seed),
            "material_path": material_path, "layer_info_path": layer_info_path, "high_start": b.high_start,
            "steep_start_cm_per_quad": b.steep_start_cm_per_quad,
            "paint_layers": [{"name": n, "rule": r} for n, r, _ in b.layers]}


def layer_material_graph(biome: str, asset_path: str) -> dict:
    """LandscapeLayerBlend material for the biome's paint layers (input pins are named "Layer <Name>")."""
    b = BIOMES[biome]
    nodes = [{"id": "blend", "class": "MaterialExpressionLandscapeLayerBlend", "x": -400, "y": 0,
              "props": {"layers": [{"name": n} for n, _, _ in b.layers]}},
             {"id": "rough", "class": "MaterialExpressionConstant", "x": -400, "y": 300, "props": {"r": 0.85}}]
    edges = []
    for i, (name, _, colour) in enumerate(b.layers):
        nodes.append({"id": name, "class": "MaterialExpressionConstant3Vector", "x": -800, "y": i * 150,
                      "props": {"constant": list(colour)}})
        edges.append({"from": name, "to": "blend", "input": f"Layer {name}"})
    return {"asset_path": asset_path, "replace_existing": True, "nodes": nodes, "edges": edges,
            "outputs": [{"from": "blend", "property": "MP_BASE_COLOR"}, {"from": "rough", "property": "MP_ROUGHNESS"}]}


def exclusion_nodes(tag: str) -> list[dict]:
    """PCG nodes that remove sampled points inside the bounds of every actor tagged `tag` (e.g. house footprints):
    Get Actor Data (one point per actor, carrying its bounds) feeding a binary Difference."""
    return [
        {"id": "exclude", "settings": "PCGDataFromActorSettings",
         "props": {"mode": {"__enum__": "PCGGetDataFromActorMode.GET_SINGLE_POINT"},
                   "actor_selector": {"__struct__": "PCGActorSelectorSettings",
                                      "actor_filter": {"__enum__": "PCGActorFilter.ALL_WORLD_ACTORS"},
                                      "actor_selection": {"__enum__": "PCGActorSelection.BY_TAG"},
                                      "actor_selection_tag": tag, "select_multiple": True}}},
        {"id": "diff", "settings": "PCGDifferenceSettings",
         "props": {"density_function": {"__enum__": "PCGDifferenceDensityFunction.BINARY"}}},
    ]


def scatter_graphs(biome: str, seed: int, graph_folder: str, extent_cm: float,
                   exclusion_tag: str | None = None) -> list[dict]:
    """One surface-sampled PCG graph per scatter set (Get Landscape → Surface Sampler → Density Filter → Spawner).
    With `exclusion_tag`, a binary Difference against the tagged actors' bounds sits before the density filter, so
    excluded points (density 0) are culled there."""
    out = []
    for i, sc in enumerate(BIOMES[biome].scatter):
        nodes = [{"id": "land", "settings": "PCGGetLandscapeSettings"},
                 {"id": "sample", "settings": "PCGSurfaceSamplerSettings",
                  "props": {"points_per_squared_meter": sc.points_per_m2}},
                 {"id": "density", "settings": "PCGDensityFilterSettings",
                  "props": {"lower_bound": sc.density_min, "upper_bound": 1.0}},
                 {"id": "spawn", "settings": "PCGStaticMeshSpawnerSettings",
                  "meshes": [{"mesh": sc.mesh, "weight": 1}]}]
        edges = [{"from": "land", "from_pin": "Out", "to": "sample", "to_pin": "Surface"},
                 {"from": "density", "from_pin": "Out", "to": "spawn", "to_pin": "In"}]
        if exclusion_tag:
            nodes += exclusion_nodes(exclusion_tag)
            edges += [{"from": "sample", "from_pin": "Out", "to": "diff", "to_pin": "Source"},
                      {"from": "exclude", "from_pin": "Out", "to": "diff", "to_pin": "Differences"},
                      {"from": "diff", "from_pin": "Out", "to": "density", "to_pin": "In"}]
        else:
            edges.append({"from": "sample", "from_pin": "Out", "to": "density", "to_pin": "In"})
        out.append({
            "graph_path": f"{graph_folder}/PCG_{biome}_{sc.name}", "label": f"GF_PCG_{sc.name}", "seed": seed * 31 + i,
            "center": {"x": 0, "y": 0, "z": 0}, "extent": {"x": extent_cm, "y": extent_cm, "z": 8000},
            "nodes": nodes, "edges": edges,
        })
    return out


def lighting_rig(preset: str, height_cm: float = 10000.0) -> list[dict]:
    rig = []
    for actor in LIGHTING[preset]:
        # Lights that declare their own location (indoor fill PointLight) keep it; previously every light was
        # forced to z=height_cm, which put the 5000-lumen indoor fill light 100 m above the level.
        loc = actor.get("location") or {"x": 0, "y": 0, "z": height_cm}
        rig.append({**actor, "location": dict(loc)})
    return rig
