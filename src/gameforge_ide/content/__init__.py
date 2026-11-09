"""GameForge content, art direction, and asset integration package (Phase 7)."""
from .epic_packs import (
    EPIC_PACKS,
    install_pack,
    collect_cook_directories,
    update_default_game_ini_cook_dirs,
)
from .themes import (
    THEMES,
    SurfaceRoleConfig,
    get_theme,
    relative_luminance,
    wcag_contrast_ratio,
    validate_and_adjust_palette,
    get_theme_pbr_specs,
)
from .procedural_props import (
    PROP_RECIPES,
    PropRecipe,
    _box,
    _cylinder,
    _sphere,
    _cone,
    compute_bounds,
    verify_recipe_watertight,
    expand_prop_to_ops,
)
from .library import (
    ContentLibrary,
    LicenceDecl,
    infer_role_from_name,
    infer_asset_type_from_path,
    VALID_LICENCE_CLASSES,
)
from .audio import (
    AudioService,
    sfx_unreal_asset_path,
    verify_audio_loop,
    resample_audio,
    crossfade_loop,
)
from .vfx_presets import (
    VFX_PRESETS,
    VFXPreset,
    get_vfx_preset,
)
from .sfx_presets import (
    SFX_SETS,
    SFXPreset,
    get_sfx_preset,
    list_sfx_presets,
    synthesize_sfx_preset,
)
from .music import (
    generate_music_loop,
    analyze_music_loop,
    MOOD_CONFIGS,
    note_to_freq,
)
from .ambience import (
    generate_ambience_loop,
    analyze_ambience_loop,
)

__all__ = [
    "EPIC_PACKS",
    "install_pack",
    "collect_cook_directories",
    "update_default_game_ini_cook_dirs",
    "THEMES",
    "SurfaceRoleConfig",
    "get_theme",
    "relative_luminance",
    "wcag_contrast_ratio",
    "validate_and_adjust_palette",
    "get_theme_pbr_specs",
    "PROP_RECIPES",
    "PropRecipe",
    "_box",
    "_cylinder",
    "_sphere",
    "_cone",
    "compute_bounds",
    "verify_recipe_watertight",
    "expand_prop_to_ops",
    "ContentLibrary",
    "LicenceDecl",
    "infer_role_from_name",
    "infer_asset_type_from_path",
    "VALID_LICENCE_CLASSES",
    "AudioService",
    "sfx_unreal_asset_path",
    "verify_audio_loop",
    "resample_audio",
    "crossfade_loop",
    "VFX_PRESETS",
    "VFXPreset",
    "get_vfx_preset",
    "SFX_SETS",
    "SFXPreset",
    "get_sfx_preset",
    "list_sfx_presets",
    "synthesize_sfx_preset",
    "generate_music_loop",
    "analyze_music_loop",
    "MOOD_CONFIGS",
    "note_to_freq",
    "generate_ambience_loop",
    "analyze_ambience_loop",
]
