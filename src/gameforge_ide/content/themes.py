"""Art direction themes, surface roles, and master material definitions (P7 WI-7.3).

Provides master material templates, theme-to-role mappings for all 19 canonical themes,
procedural PBR texture set specifications, and WCAG contrast enforcement for game visual presentation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..backend.tools.pbr_texture_generator import PBRTextureSpec


@dataclass(frozen=True)
class SurfaceRoleConfig:
    role: str
    texture_set_name: str
    base_color: Tuple[float, float, float]
    roughness: float
    metallic: float
    normal_strength: float = 3.0
    emissive_strength: float = 0.0
    use_world_align: bool = True


def _make_theme_roles(
    prefix: str,
    floor_rgb: Tuple[float, float, float],
    wall_rgb: Tuple[float, float, float],
    prop_rgb: Tuple[float, float, float],
    accent_rgb: Tuple[float, float, float],
    roughness: float = 0.70,
    metallic: float = 0.0,
    accent_emissive: float = 0.0,
) -> Dict[str, SurfaceRoleConfig]:
    return {
        "floor": SurfaceRoleConfig("floor", f"T_{prefix}Floor", floor_rgb, roughness, metallic),
        "wall": SurfaceRoleConfig("wall", f"T_{prefix}Wall", wall_rgb, min(1.0, roughness + 0.05), metallic),
        "prop": SurfaceRoleConfig("prop", f"T_{prefix}Prop", prop_rgb, min(1.0, roughness + 0.10), 0.0),
        "accent": SurfaceRoleConfig("accent", f"T_{prefix}Accent", accent_rgb, 0.25, 0.6, emissive_strength=accent_emissive),
        "terrain_low": SurfaceRoleConfig("terrain_low", f"T_{prefix}Ground", floor_rgb, min(1.0, roughness + 0.15), 0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", f"T_{prefix}Cliff", wall_rgb, min(1.0, roughness + 0.15), 0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", f"T_{prefix}Peak", accent_rgb, 0.50, 0.0),
    }


THEMES: Dict[str, Dict[str, SurfaceRoleConfig]] = {
    "default": {
        "floor": SurfaceRoleConfig("floor", "T_StoneTiles", (0.35, 0.35, 0.38), 0.65, 0.0),
        "wall": SurfaceRoleConfig("wall", "T_PlasterWall", (0.55, 0.55, 0.58), 0.75, 0.0),
        "prop": SurfaceRoleConfig("prop", "T_WeatheredWood", (0.42, 0.30, 0.20), 0.80, 0.0),
        "accent": SurfaceRoleConfig("accent", "T_PolishedMetal", (0.95, 0.75, 0.15), 0.25, 0.9),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_LushGrass", (0.22, 0.38, 0.16), 0.85, 0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_CliffRock", (0.40, 0.38, 0.36), 0.90, 0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_MountainSnow", (0.90, 0.92, 0.95), 0.40, 0.0),
    },
    "stone_wood": {
        "floor": SurfaceRoleConfig("floor", "T_Cobblestone", (0.30, 0.29, 0.28), 0.70, 0.0),
        "wall": SurfaceRoleConfig("wall", "T_CastleStone", (0.45, 0.43, 0.42), 0.80, 0.0),
        "prop": SurfaceRoleConfig("prop", "T_OakPlanks", (0.48, 0.32, 0.18), 0.75, 0.0),
        "accent": SurfaceRoleConfig("accent", "T_OrnateBrass", (0.88, 0.70, 0.22), 0.30, 0.85),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_ForestSoil", (0.28, 0.22, 0.16), 0.90, 0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_DarkSlate", (0.25, 0.25, 0.27), 0.85, 0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_GranitePeak", (0.60, 0.60, 0.62), 0.50, 0.0),
    },
    "scifi_metal": {
        "floor": SurfaceRoleConfig("floor", "T_GratePanel", (0.20, 0.22, 0.26), 0.35, 0.8),
        "wall": SurfaceRoleConfig("wall", "T_HullPlates", (0.60, 0.63, 0.68), 0.40, 0.6),
        "prop": SurfaceRoleConfig("prop", "T_CarbonFiber", (0.12, 0.13, 0.15), 0.50, 0.2),
        "accent": SurfaceRoleConfig("accent", "T_NeonCyan", (0.10, 0.85, 0.95), 0.10, 0.1, emissive_strength=4.0),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_MoonDust", (0.40, 0.40, 0.42), 0.80, 0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_BasaltRock", (0.18, 0.18, 0.20), 0.70, 0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_MetalRidge", (0.50, 0.52, 0.55), 0.40, 0.7),
    },
    "desert_sand": {
        "floor": SurfaceRoleConfig("floor", "T_SandstoneFloor", (0.75, 0.62, 0.45), 0.80, 0.0),
        "wall": SurfaceRoleConfig("wall", "T_AdobeBrick", (0.68, 0.52, 0.38), 0.85, 0.0),
        "prop": SurfaceRoleConfig("prop", "T_SunbleachedWood", (0.58, 0.50, 0.42), 0.90, 0.0),
        "accent": SurfaceRoleConfig("accent", "T_LapisBead", (0.08, 0.25, 0.48), 0.20, 0.1),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_FineDuneSand", (0.82, 0.70, 0.52), 0.90, 0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_RedMesaRock", (0.65, 0.35, 0.25), 0.85, 0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_AridPeak", (0.78, 0.65, 0.48), 0.75, 0.0),
    },
    "snow_ice": {
        "floor": SurfaceRoleConfig("floor", "T_PackedSnow", (0.88, 0.90, 0.94), 0.60, 0.0),
        "wall": SurfaceRoleConfig("wall", "T_GlacierIce", (0.60, 0.78, 0.90), 0.15, 0.1),
        "prop": SurfaceRoleConfig("prop", "T_FrostedTimber", (0.35, 0.32, 0.30), 0.80, 0.0),
        "accent": SurfaceRoleConfig("accent", "T_WarmTorchlight", (0.72, 0.18, 0.04), 0.20, 0.0, emissive_strength=3.0),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_DeepPowder", (0.92, 0.94, 0.98), 0.70, 0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_FrozenRock", (0.42, 0.45, 0.50), 0.50, 0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_IceCap", (0.75, 0.85, 0.95), 0.20, 0.2),
    },
    "toon_flat": {
        "floor": SurfaceRoleConfig("floor", "T_ToonGrass", (0.30, 0.75, 0.30), 1.0, 0.0, normal_strength=0.0),
        "wall": SurfaceRoleConfig("wall", "T_ToonWall", (0.90, 0.85, 0.75), 1.0, 0.0, normal_strength=0.0),
        "prop": SurfaceRoleConfig("prop", "T_ToonWood", (0.60, 0.35, 0.18), 1.0, 0.0, normal_strength=0.0),
        "accent": SurfaceRoleConfig("accent", "T_ToonPurple", (0.35, 0.08, 0.65), 1.0, 0.0, normal_strength=0.0),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_ToonGround", (0.35, 0.70, 0.32), 1.0, 0.0, normal_strength=0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_ToonRock", (0.55, 0.55, 0.58), 1.0, 0.0, normal_strength=0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_ToonSnow", (0.98, 0.98, 1.0), 1.0, 0.0, normal_strength=0.0),
    },
    "forest": _make_theme_roles("Forest", (0.31, 0.48, 0.21), (0.49, 0.42, 0.34), (0.36, 0.23, 0.12), (0.95, 0.76, 0.19), roughness=0.80),
    "haunted": _make_theme_roles("Haunted", (0.18, 0.23, 0.18), (0.33, 0.33, 0.42), (0.17, 0.14, 0.13), (0.61, 0.36, 0.90), roughness=0.85, accent_emissive=2.0),
    "volcano": _make_theme_roles("Volcano", (0.23, 0.15, 0.13), (0.36, 0.23, 0.18), (0.29, 0.23, 0.21), (1.00, 0.42, 0.10), roughness=0.85, accent_emissive=3.5),
    "ice": _make_theme_roles("Ice", (0.88, 0.90, 0.94), (0.60, 0.78, 0.90), (0.35, 0.32, 0.30), (0.72, 0.18, 0.04), roughness=0.45, accent_emissive=2.5),
    "desert": _make_theme_roles("Desert", (0.75, 0.62, 0.45), (0.68, 0.52, 0.38), (0.58, 0.50, 0.42), (0.08, 0.25, 0.48), roughness=0.80),
    "island": _make_theme_roles("Island", (0.91, 0.83, 0.60), (0.48, 0.55, 0.42), (0.48, 0.32, 0.19), (0.00, 0.48, 0.58), roughness=0.75),
    "space": _make_theme_roles("Space", (0.16, 0.18, 0.27), (0.29, 0.31, 0.41), (0.35, 0.36, 0.47), (0.30, 0.79, 0.94), roughness=0.40, metallic=0.6, accent_emissive=3.0),
    "cyber": _make_theme_roles("Cyber", (0.11, 0.10, 0.18), (0.18, 0.17, 0.29), (0.24, 0.23, 0.36), (0.00, 0.96, 0.83), roughness=0.35, metallic=0.5, accent_emissive=4.0),
    "dungeon": _make_theme_roles("Dungeon", (0.29, 0.26, 0.23), (0.42, 0.38, 0.35), (0.42, 0.29, 0.17), (0.88, 0.64, 0.35), roughness=0.85, accent_emissive=1.5),
    "castle": _make_theme_roles("Castle", (0.49, 0.50, 0.49), (0.60, 0.61, 0.62), (0.45, 0.30, 0.18), (0.75, 0.22, 0.17), roughness=0.75),
    "city": _make_theme_roles("City", (0.33, 0.34, 0.37), (0.55, 0.60, 0.68), (0.43, 0.41, 0.46), (0.95, 0.80, 0.56), roughness=0.65),
    "candy": _make_theme_roles("Candy", (1.00, 0.78, 0.87), (0.74, 0.88, 1.00), (0.96, 0.64, 0.38), (0.75, 0.12, 0.45), roughness=0.50),
    "ocean": _make_theme_roles("Ocean", (0.11, 0.31, 0.54), (0.16, 0.44, 0.59), (0.29, 0.44, 0.54), (0.56, 0.88, 0.94), roughness=0.60),
}


def get_theme(theme_name: str = "default") -> Dict[str, SurfaceRoleConfig]:
    """Return surface role configuration dict for the requested theme."""
    return THEMES.get(theme_name, THEMES["default"])


def relative_luminance(rgb: Tuple[float, float, float] | List[float]) -> float:
    """Compute relative luminance according to WCAG 2.1 with safe bounds clamping."""
    import math

    vals = [float(v) for v in rgb[:3]]
    max_c = max(vals) if vals else 0.0
    scale = 255.0 if max_c > 1.05 else 1.0

    def _srgb(val: float) -> float:
        if math.isnan(val) or math.isinf(val):
            return 0.0
        v = val / scale
        v = max(0.0, min(1.0, v))
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = _srgb(vals[0]), _srgb(vals[1]), _srgb(vals[2])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_contrast_ratio(
    rgb1: Tuple[float, float, float] | List[float],
    rgb2: Tuple[float, float, float] | List[float],
) -> float:
    """Compute WCAG contrast ratio between two colours (>= 1.0)."""
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def validate_and_adjust_palette(
    floor_rgb: Tuple[float, float, float] | List[float],
    accent_rgb: Tuple[float, float, float] | List[float],
    palette_candidates: Optional[List[Tuple[float, float, float]]] = None,
    min_contrast: float = 3.0,
) -> Tuple[Tuple[float, float, float], Optional[str]]:
    """Verify accent-to-floor contrast; swap to candidate colour if contrast < min_contrast."""
    ratio = wcag_contrast_ratio(floor_rgb, accent_rgb)
    if ratio >= min_contrast:
        return (float(accent_rgb[0]), float(accent_rgb[1]), float(accent_rgb[2])), None

    candidates = palette_candidates or [
        (1.0, 0.85, 0.10),   # bright gold
        (0.10, 0.90, 0.95),  # bright cyan
        (0.95, 0.95, 0.95),  # near white
        (0.05, 0.05, 0.08),  # near black
        (0.95, 0.25, 0.15),  # vivid red
        (0.10, 0.25, 0.55),  # deep sapphire
        (0.35, 0.08, 0.65),  # deep violet
    ]

    for cand in candidates:
        if wcag_contrast_ratio(floor_rgb, cand) >= min_contrast:
            warn = (
                f"Accent contrast ratio {ratio:.2f}:1 against floor is below {min_contrast}:1; "
                f"swapped to alternative palette colour {cand}"
            )
            return cand, warn

    floor_lum = relative_luminance(floor_rgb)
    optimal_cand = (1.0, 1.0, 1.0) if floor_lum < 0.179 else (0.0, 0.0, 0.0)
    opt_ratio = wcag_contrast_ratio(floor_rgb, optimal_cand)
    warn = (
        f"Accent contrast ratio {ratio:.2f}:1 against floor is below {min_contrast}:1; "
        f"swapped to guaranteed polarity colour {optimal_cand} ({opt_ratio:.2f}:1)"
    )
    return optimal_cand, warn


def get_theme_pbr_specs(
    theme_name: str = "default",
    seed: int = 42,
    enforce_contrast: bool = True,
) -> List[PBRTextureSpec]:
    """Generate PBRTextureSpecs for all surface roles in the selected theme."""
    theme = get_theme(theme_name)
    specs: List[PBRTextureSpec] = []

    accent_override: Optional[Tuple[float, float, float]] = None
    if enforce_contrast and "floor" in theme and "accent" in theme:
        adj, _ = validate_and_adjust_palette(theme["floor"].base_color, theme["accent"].base_color)
        accent_override = adj

    for idx, (role, cfg) in enumerate(theme.items()):
        base_color = accent_override if (role == "accent" and accent_override is not None) else cfg.base_color
        spec = PBRTextureSpec(
            name=cfg.texture_set_name,
            size=512,
            seed=seed + idx * 17,
            base_color=base_color,
            color_variation=0.25 if theme_name != "toon_flat" else 0.05,
            roughness_range=(cfg.roughness * 0.8, min(1.0, cfg.roughness * 1.2)),
            metallic=cfg.metallic,
            normal_strength=cfg.normal_strength,
            tags=["theme", theme_name, role],
        )
        specs.append(spec)
    return specs
