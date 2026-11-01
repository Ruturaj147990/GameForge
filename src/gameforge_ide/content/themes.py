"""Art direction themes, surface roles, and master material definitions (P7 WI-7.3).

Provides master material templates, theme-to-role mappings, procedural PBR texture
set specifications, and WCAG contrast enforcement for game visual presentation.
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
        "accent": SurfaceRoleConfig("accent", "T_TurquoiseBead", (0.15, 0.75, 0.70), 0.20, 0.1),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_FineDuneSand", (0.82, 0.70, 0.52), 0.90, 0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_RedMesaRock", (0.65, 0.35, 0.25), 0.85, 0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_AridPeak", (0.78, 0.65, 0.48), 0.75, 0.0),
    },
    "snow_ice": {
        "floor": SurfaceRoleConfig("floor", "T_PackedSnow", (0.88, 0.90, 0.94), 0.60, 0.0),
        "wall": SurfaceRoleConfig("wall", "T_GlacierIce", (0.60, 0.78, 0.90), 0.15, 0.1),
        "prop": SurfaceRoleConfig("prop", "T_FrostedTimber", (0.35, 0.32, 0.30), 0.80, 0.0),
        "accent": SurfaceRoleConfig("accent", "T_WarmTorchlight", (0.95, 0.55, 0.15), 0.20, 0.0, emissive_strength=3.0),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_DeepPowder", (0.92, 0.94, 0.98), 0.70, 0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_FrozenRock", (0.42, 0.45, 0.50), 0.50, 0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_IceCap", (0.75, 0.85, 0.95), 0.20, 0.2),
    },
    "toon_flat": {
        "floor": SurfaceRoleConfig("floor", "T_ToonGrass", (0.30, 0.75, 0.30), 1.0, 0.0, normal_strength=0.0),
        "wall": SurfaceRoleConfig("wall", "T_ToonWall", (0.90, 0.85, 0.75), 1.0, 0.0, normal_strength=0.0),
        "prop": SurfaceRoleConfig("prop", "T_ToonWood", (0.60, 0.35, 0.18), 1.0, 0.0, normal_strength=0.0),
        "accent": SurfaceRoleConfig("accent", "T_ToonYellow", (1.0, 0.88, 0.10), 1.0, 0.0, normal_strength=0.0),
        "terrain_low": SurfaceRoleConfig("terrain_low", "T_ToonGround", (0.35, 0.70, 0.32), 1.0, 0.0, normal_strength=0.0),
        "terrain_steep": SurfaceRoleConfig("terrain_steep", "T_ToonRock", (0.55, 0.55, 0.58), 1.0, 0.0, normal_strength=0.0),
        "terrain_high": SurfaceRoleConfig("terrain_high", "T_ToonSnow", (0.98, 0.98, 1.0), 1.0, 0.0, normal_strength=0.0),
    },
}


def relative_luminance(rgb: Tuple[float, float, float]) -> float:
    """Compute relative luminance according to WCAG 2.1."""
    def _srgb(val: float) -> float:
        return val / 12.92 if val <= 0.04045 else ((val + 0.055) / 1.055) ** 2.4

    r, g, b = _srgb(rgb[0]), _srgb(rgb[1]), _srgb(rgb[2])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_contrast_ratio(rgb1: Tuple[float, float, float], rgb2: Tuple[float, float, float]) -> float:
    """Compute WCAG contrast ratio between two colours (>= 1.0)."""
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def validate_and_adjust_palette(
    floor_rgb: Tuple[float, float, float],
    accent_rgb: Tuple[float, float, float],
    palette_candidates: Optional[List[Tuple[float, float, float]]] = None,
    min_contrast: float = 3.0,
) -> Tuple[Tuple[float, float, float], Optional[str]]:
    """Verify accent-to-floor contrast; swap to candidate colour if contrast < min_contrast."""
    ratio = wcag_contrast_ratio(floor_rgb, accent_rgb)
    if ratio >= min_contrast:
        return accent_rgb, None

    # Need adjustment
    candidates = palette_candidates or [
        (1.0, 0.9, 0.1),  # bright gold
        (0.1, 0.9, 0.9),  # cyan
        (0.95, 0.2, 0.2), # bright red
        (0.95, 0.95, 0.95), # white
        (0.1, 0.1, 0.1),  # dark
    ]

    for cand in candidates:
        if wcag_contrast_ratio(floor_rgb, cand) >= min_contrast:
            warn = (
                f"Accent contrast ratio {ratio:.2f}:1 against floor is below {min_contrast}:1; "
                f"swapped to alternative palette colour {cand}"
            )
            return cand, warn

    warn = f"Accent contrast ratio {ratio:.2f}:1 against floor is below {min_contrast}:1 (no suitable candidate)"
    return accent_rgb, warn


def get_theme_pbr_specs(theme_name: str = "default", seed: int = 42) -> List[PBRTextureSpec]:
    """Generate PBRTextureSpecs for all surface roles in the selected theme."""
    theme = THEMES.get(theme_name, THEMES["default"])
    specs: List[PBRTextureSpec] = []
    for idx, (role, cfg) in enumerate(theme.items()):
        spec = PBRTextureSpec(
            name=cfg.texture_set_name,
            size=512,
            seed=seed + idx * 17,
            base_color=cfg.base_color,
            color_variation=0.25 if theme_name != "toon_flat" else 0.05,
            roughness_range=(cfg.roughness * 0.8, min(1.0, cfg.roughness * 1.2)),
            metallic=cfg.metallic,
            normal_strength=cfg.normal_strength,
            tags=["theme", theme_name, role],
        )
        specs.append(spec)
    return specs
