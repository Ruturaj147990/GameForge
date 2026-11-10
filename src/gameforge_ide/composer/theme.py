"""Art direction for composed levels: surface colours, light colours and decoration sets per theme.

Layouts used to reference ``/Game/LevelPrototyping/...`` grid materials. Those only exist when the Epic template
pack was copied into the project, so most generated levels rendered as flat white/grey boxes no matter whether the
prompt asked for a volcano, a neon city or a haunted graveyard. The composer now paints every layout primitive with a
role colour from the game's theme (``spawn_actor`` tints BasicShapeMaterial through its ``color`` argument), tints the
key light, and adds a themed decoration set (see ``composer/decor.py``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

RGB = Tuple[float, float, float]


def hex_to_rgb(code: str) -> RGB:
    code = code.lstrip("#")
    return (int(code[0:2], 16) / 255.0, int(code[2:4], 16) / 255.0, int(code[4:6], 16) / 255.0)


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(round(a[i] + (b[i] - a[i]) * t, 3) for i in range(3))  # type: ignore[return-value]


def _scale(a: RGB, f: float) -> RGB:
    return tuple(round(max(0.0, min(1.0, c * f)), 3) for c in a)  # type: ignore[return-value]


@dataclass(frozen=True)
class DecorPiece:
    """One decoration prop made of 1-3 basic shapes. Offsets/scales are in metres of the 1 m basic shapes."""
    name: str
    parts: Tuple[Tuple[str, str, Tuple[float, float, float], Tuple[float, float, float]], ...]
    # (shape, colour role, offset xyz in cm, scale xyz)
    radius_cm: float = 120.0
    light: Optional[Tuple[str, float]] = None   # (colour role, intensity) for an attached point light


@dataclass(frozen=True)
class Theme:
    theme_id: str
    roles: Dict[str, RGB]
    sun_color: RGB = (1.0, 0.95, 0.88)
    decor: Tuple[str, ...] = ("rock", "tree")
    fog: bool = True
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def color(self, role: str) -> List[float]:
        rgb = self.roles.get(role) or self.roles.get("wall") or (0.6, 0.6, 0.6)
        return [round(c, 3) for c in rgb] + [1.0]


DECOR: Dict[str, DecorPiece] = {
    "tree": DecorPiece("tree", (("Cylinder", "trunk", (0, 0, 120), (0.35, 0.35, 2.4)),
                                ("Cone", "foliage", (0, 0, 330), (2.2, 2.2, 2.6)),
                                ("Cone", "foliage_dark", (0, 0, 470), (1.5, 1.5, 1.8))), 180.0),
    "round_tree": DecorPiece("round_tree", (("Cylinder", "trunk", (0, 0, 110), (0.3, 0.3, 2.2)),
                                            ("Sphere", "foliage", (0, 0, 300), (2.4, 2.4, 2.2))), 170.0),
    "dead_tree": DecorPiece("dead_tree", (("Cylinder", "trunk_dark", (0, 0, 160), (0.3, 0.3, 3.2)),
                                          ("Cylinder", "trunk_dark", (40, 0, 260), (0.15, 0.15, 1.2))), 100.0),
    "palm": DecorPiece("palm", (("Cylinder", "trunk", (0, 0, 220), (0.28, 0.28, 4.4)),
                                ("Sphere", "foliage", (0, 0, 460), (2.6, 2.6, 0.6))), 160.0),
    "cactus": DecorPiece("cactus", (("Cylinder", "foliage", (0, 0, 120), (0.5, 0.5, 2.4)),
                                    ("Cylinder", "foliage", (45, 0, 150), (0.3, 0.3, 0.9))), 90.0),
    "rock": DecorPiece("rock", (("Sphere", "rock", (0, 0, 30), (1.6, 1.3, 0.9)),), 110.0),
    "boulder": DecorPiece("boulder", (("Sphere", "rock_dark", (0, 0, 60), (2.6, 2.2, 1.6)),
                                      ("Sphere", "rock", (90, 40, 30), (1.1, 1.0, 0.8))), 180.0),
    "crystal": DecorPiece("crystal", (("Cone", "accent", (0, 0, 90), (0.6, 0.6, 1.8)),
                                      ("Cone", "accent2", (50, 30, 55), (0.35, 0.35, 1.1))), 90.0, ("accent", 1800.0)),
    "pillar": DecorPiece("pillar", (("Cylinder", "wall", (0, 0, 200), (0.8, 0.8, 4.0)),
                                    ("Cube", "wall_dark", (0, 0, 410), (1.1, 1.1, 0.2))), 90.0),
    "broken_pillar": DecorPiece("broken_pillar", (("Cylinder", "wall", (0, 0, 90), (0.8, 0.8, 1.8)),
                                                  ("Cylinder", "wall_dark", (110, 20, 30), (0.8, 0.8, 0.6))), 120.0),
    "crate": DecorPiece("crate", (("Cube", "prop", (0, 0, 50), (1.0, 1.0, 1.0)),
                                  ("Cube", "prop", (25, 10, 125), (0.6, 0.6, 0.5))), 90.0),
    "barrel": DecorPiece("barrel", (("Cylinder", "prop", (0, 0, 55), (0.7, 0.7, 1.1)),), 60.0),
    "torch": DecorPiece("torch", (("Cylinder", "trunk_dark", (0, 0, 100), (0.12, 0.12, 2.0)),
                                  ("Sphere", "flame", (0, 0, 215), (0.35, 0.35, 0.45))), 50.0, ("flame", 2500.0)),
    "lamp_post": DecorPiece("lamp_post", (("Cylinder", "wall_dark", (0, 0, 200), (0.15, 0.15, 4.0)),
                                          ("Sphere", "light", (0, 0, 410), (0.5, 0.5, 0.5))), 60.0, ("light", 3000.0)),
    "neon_block": DecorPiece("neon_block", (("Cube", "wall_dark", (0, 0, 150), (1.4, 1.4, 3.0)),
                                            ("Cube", "accent", (0, 0, 310), (1.5, 1.5, 0.12))), 120.0, ("accent", 2500.0)),
    "tombstone": DecorPiece("tombstone", (("Cube", "rock", (0, 0, 55), (0.7, 0.2, 1.1)),
                                          ("Cylinder", "rock", (0, 0, 115), (0.7, 0.2, 0.25))), 70.0),
    "ice_spike": DecorPiece("ice_spike", (("Cone", "accent", (0, 0, 120), (0.9, 0.9, 2.4)),
                                          ("Cone", "accent2", (60, -30, 70), (0.5, 0.5, 1.4))), 100.0),
    "lava_rock": DecorPiece("lava_rock", (("Sphere", "rock_dark", (0, 0, 50), (1.8, 1.6, 1.1)),
                                          ("Sphere", "flame", (0, 0, 95), (0.5, 0.5, 0.25))), 130.0, ("flame", 1500.0)),
    "mushroom": DecorPiece("mushroom", (("Cylinder", "trunk_light", (0, 0, 60), (0.35, 0.35, 1.2)),
                                        ("Sphere", "accent", (0, 0, 130), (1.3, 1.3, 0.6))), 90.0),
    "candy_cane": DecorPiece("candy_cane", (("Cylinder", "accent", (0, 0, 150), (0.25, 0.25, 3.0)),
                                            ("Sphere", "accent2", (0, 0, 310), (0.6, 0.6, 0.6))), 60.0),
    "antenna": DecorPiece("antenna", (("Cylinder", "wall", (0, 0, 250), (0.12, 0.12, 5.0)),
                                      ("Sphere", "accent", (0, 0, 510), (0.3, 0.3, 0.3))), 50.0, ("accent", 1200.0)),
}


def _theme(theme_id: str, floor: str, wall: str, accent: str, accent2: str, *, trunk: str = "#5B3A1E",
           foliage: str = "#3E7D2C", rock: str = "#7A7570", prop: str = "#8B5A2B", flame: str = "#FF7A1A",
           light: str = "#FFE9B0", sun: RGB = (1.0, 0.95, 0.88), decor: Tuple[str, ...] = ("rock", "tree"),
           hazard: str = "#E53B1F") -> Theme:
    f, w, a, a2 = hex_to_rgb(floor), hex_to_rgb(wall), hex_to_rgb(accent), hex_to_rgb(accent2)
    roles: Dict[str, RGB] = {
        "floor": f, "floor_alt": _scale(f, 0.85), "path": _mix(f, (0.9, 0.85, 0.75), 0.35),
        "wall": w, "wall_dark": _scale(w, 0.65), "cover": _mix(w, a2, 0.25),
        "platform": _mix(w, a, 0.15), "platform_alt": _mix(w, a2, 0.3), "goal_pad": a, "start_pad": _mix(f, a2, 0.4),
        "accent": a, "accent2": a2, "hazard": hex_to_rgb(hazard),
        "trunk": hex_to_rgb(trunk), "trunk_dark": _scale(hex_to_rgb(trunk), 0.6), "trunk_light": _mix(hex_to_rgb(trunk), (1, 1, 1), 0.5),
        "foliage": hex_to_rgb(foliage), "foliage_dark": _scale(hex_to_rgb(foliage), 0.75),
        "rock": hex_to_rgb(rock), "rock_dark": _scale(hex_to_rgb(rock), 0.7), "prop": hex_to_rgb(prop),
        "flame": hex_to_rgb(flame), "light": hex_to_rgb(light), "safety": _scale(f, 0.5),
    }
    return Theme(theme_id, roles, sun, decor)


THEMES: Dict[str, Theme] = {
    "default": _theme("default", "#6E8B5A", "#9AA3AD", "#F2C230", "#3FA7D6", decor=("rock", "round_tree", "crate")),
    "forest": _theme("forest", "#4E7A35", "#7D6B57", "#F2C230", "#7CC6FE", foliage="#2F6B2A",
                     decor=("tree", "round_tree", "rock", "mushroom")),
    "haunted": _theme("haunted", "#2F3B2E", "#55536B", "#9B5DE5", "#7FD1B9", trunk="#2B2420", foliage="#3B4A3A",
                      rock="#6E6E7A", flame="#7FFFD4", light="#A8D8FF", sun=(0.55, 0.6, 0.85),
                      decor=("dead_tree", "tombstone", "torch", "rock")),
    "volcano": _theme("volcano", "#3A2620", "#5C3A2E", "#FF6B1A", "#FFC145", rock="#4A3B36", flame="#FF5A00",
                      sun=(1.0, 0.62, 0.42), decor=("lava_rock", "boulder", "dead_tree"), hazard="#FF3D00"),
    "ice": _theme("ice", "#E3EEF5", "#A9C7DB", "#4FC3F7", "#B3E5FC", trunk="#4E4A47", foliage="#E8F4FA",
                  rock="#9FB4C2", sun=(0.9, 0.95, 1.0), decor=("ice_spike", "tree", "rock")),
    "desert": _theme("desert", "#D9B47A", "#B98756", "#2E86C1", "#E74C3C", trunk="#7A5A3A", foliage="#5E8C3A",
                     rock="#B07850", sun=(1.0, 0.9, 0.72), decor=("cactus", "rock", "broken_pillar")),
    "island": _theme("island", "#E8D49A", "#7A8B6A", "#00B4D8", "#FF8C42", trunk="#7A5230", foliage="#2E9E5B",
                     rock="#8E8A80", decor=("palm", "rock", "barrel")),
    "space": _theme("space", "#2A2D45", "#4A4E69", "#4CC9F0", "#F72585", rock="#5A5D78", light="#BDE0FE",
                    sun=(0.75, 0.8, 1.0), decor=("crystal", "antenna", "boulder")),
    "cyber": _theme("cyber", "#1C1A2E", "#2E2B4A", "#00F5D4", "#F15BB5", rock="#3A3756", prop="#3D3A5C",
                    light="#00F5D4", sun=(0.6, 0.55, 1.0), decor=("neon_block", "lamp_post", "crate")),
    "dungeon": _theme("dungeon", "#4A433B", "#6B6158", "#E0A458", "#7FB7BE", rock="#5B5550", prop="#6B4A2B",
                      flame="#FFA040", sun=(1.0, 0.8, 0.6), decor=("pillar", "torch", "barrel", "crate")),
    "castle": _theme("castle", "#7D7F7D", "#9A9C9E", "#C0392B", "#F1C40F", decor=("pillar", "torch", "tree", "crate")),
    "city": _theme("city", "#55575E", "#8D99AE", "#F2CC8F", "#E07A5F", prop="#6D6875",
                   decor=("lamp_post", "crate", "barrel")),
    "candy": _theme("candy", "#FFC8DD", "#BDE0FE", "#FF5DA2", "#A2D2FF", trunk="#F4A261", foliage="#FFAFCC",
                    rock="#CDB4DB", decor=("candy_cane", "mushroom", "round_tree")),
    "ocean": _theme("ocean", "#1D4E89", "#2A6F97", "#90E0EF", "#F9C74F", foliage="#2A9D8F", rock="#4A6F8A",
                    sun=(0.7, 0.85, 1.0), decor=("rock", "crystal", "boulder")),
    "stone_wood": _theme("stone_wood", "#6B6560", "#8A7F74", "#D4A017", "#5DADE2", decor=("rock", "tree", "crate")),
    "scifi_metal": _theme("scifi_metal", "#33373D", "#6C7A89", "#00D2FF", "#FF8C00", decor=("crystal", "antenna", "crate")),
    "desert_sand": _theme("desert_sand", "#D9B47A", "#B98756", "#2E86C1", "#E74C3C", decor=("cactus", "rock")),
    "snow_ice": _theme("snow_ice", "#E3EEF5", "#A9C7DB", "#4FC3F7", "#B3E5FC", decor=("ice_spike", "tree")),
    "toon_flat": _theme("toon_flat", "#7CC66B", "#F2E3C6", "#9B5DE5", "#FF6B6B", decor=("round_tree", "mushroom")),
}

_BIOME_THEME = {"forest": "forest", "desert": "desert", "island": "island", "mountain": "castle",
                "dungeon": "dungeon", "indoor": "cyber"}


_THEME_SYNONYMS: Dict[str, str] = {
    "scifi": "scifi_metal",
    "sci_fi": "scifi_metal",
    "snow": "snow_ice",
    "cyberpunk": "cyber",
    "volcanic": "volcano",
    "haunted_house": "haunted",
    "spooky": "haunted",
    "tropical": "island",
    "pirate": "island",
    "retro": "toon_flat",
}


def resolve_theme(gds: Any) -> Theme:
    """Theme from art.material_theme, then the level biome, then the prompt text, then style."""
    art = getattr(gds, "art", None)
    tid = str(getattr(art, "material_theme", "default") or "default").strip().lower()
    tid = _THEME_SYNONYMS.get(tid, tid)
    if tid in THEMES and tid != "default":
        return THEMES[tid]
    try:
        level = gds.scene.levels[0]
        biome = str(getattr(level.biome, "value", level.biome))
        if biome in _BIOME_THEME:
            return THEMES[_BIOME_THEME[biome]]
    except Exception:
        pass
    try:
        from ..design.prompt_analysis import analyze_prompt
        brief = analyze_prompt(f"{gds.meta.source_prompt} {gds.overview.pitch} {gds.meta.title}")
        if brief.theme and brief.theme in THEMES:
            return THEMES[brief.theme]
    except Exception:
        pass
    style = str(getattr(art, "style", "stylized"))
    if style == "toon":
        return THEMES["toon_flat"]
    return THEMES["default"]


# label keyword -> role. First match wins; labels are the layout's own actor labels.
_ROLE_RULES: Tuple[Tuple[str, str], ...] = (
    ("safetyfloor", "safety"), ("safety", "safety"), ("goal", "goal_pad"), ("start", "start_pad"),
    ("walkway", "path"), ("bridge", "path"), ("ramp", "path"), ("road", "path"), ("lane", "floor_alt"),
    ("platform", "platform"), ("cover", "cover"), ("crate", "prop"), ("pillar", "wall"),
    ("wall", "wall"), ("floor", "floor"), ("ground", "floor"), ("board", "floor_alt"), ("table", "prop"),
    ("tile", "floor_alt"), ("cell", "floor_alt"), ("guardrail", "accent2"),
    ("console", "accent"), ("terminal", "accent"), ("switch", "accent"), ("door", "prop"), ("turret", "accent2"),
    ("bombsite", "goal_pad"), ("sitea", "goal_pad"), ("siteb", "accent"), ("divider", "wall_dark"), ("barrier", "wall_dark"),
)


def role_for_label(label: str, material: Optional[str] = None) -> str:
    low = (label or "").lower().replace("_", "")
    for key, role in _ROLE_RULES:
        if key in low:
            return role
    mat = (material or "").lower()
    if "orange" in mat:
        return "goal_pad"
    if "darkgray" in mat or "dark" in mat:
        return "wall"
    return "floor"


def paint_geometry_ops(ops: List[Any], theme: Theme, keep_existing_materials: bool = False) -> int:
    """Gives every StaticMeshActor spawn a theme colour. Returns how many ops were painted.

    Ops that already carry a ``color`` keep it. Prototype-grid material paths are dropped (they rarely exist in a
    generated project and override the tint)."""
    painted = 0
    for i, op in enumerate(ops):
        args = getattr(op, "args", None)
        if getattr(op, "op", None) != "spawn_actor" or not isinstance(args, dict):
            continue
        cls = str(args.get("actor_class", "StaticMeshActor"))
        if not cls.endswith("StaticMeshActor"):
            continue
        if "color" in args:
            continue
        material = args.get("material")
        role = role_for_label(str(args.get("label", "")), material)
        args["color"] = theme.color(role)
        # alternate platform tones so a course reads as distinct steps
        if role == "platform" and re.search(r"(\d+)$", str(args.get("label", ""))):
            n = int(re.search(r"(\d+)$", str(args["label"])).group(1))
            if n % 2:
                args["color"] = theme.color("platform_alt")
        if material and (not keep_existing_materials or "/LevelPrototyping/" in str(material)):
            args.pop("material", None)
        painted += 1
    return painted
