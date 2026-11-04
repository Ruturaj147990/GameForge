"""Unit tests for procedural CSG props, themes contrast, VFX presets, and epic packs (P7)."""
from pathlib import Path
import pytest

from src.gameforge_ide.content.epic_packs import (
    EPIC_PACKS,
    _infer_asset_type,
    collect_cook_directories,
    update_default_game_ini_cook_dirs,
)
from src.gameforge_ide.content.library import (
    LicenceDecl,
    infer_asset_type_from_path,
)
from src.gameforge_ide.content.procedural_props import (
    ALLOWED_COLLISIONS,
    ALLOWED_SHAPES,
    PROP_RECIPES,
    PropRecipe,
    _box,
    _cone,
    _cylinder,
    _sphere,
    compute_bounds,
    verify_recipe_watertight,
)
from src.gameforge_ide.content.themes import (
    THEMES,
    get_theme_pbr_specs,
    relative_luminance,
    validate_and_adjust_palette,
    wcag_contrast_ratio,
)
from src.gameforge_ide.content.vfx_presets import (
    VALID_TEMPLATE_EMITTERS,
    VALID_TEMPLATE_SYSTEMS,
    VFX_PRESETS,
    VFXPreset,
    get_vfx_preset,
)


class TestProceduralProps:
    def test_all_10_recipes_valid_and_watertight(self):
        assert len(PROP_RECIPES) == 10
        expected_props = [
            "crate", "barrel", "rock", "pillar", "fence",
            "stylized_tree", "bush", "torch", "chest", "altar",
        ]
        for name in expected_props:
            assert name in PROP_RECIPES
            recipe = PROP_RECIPES[name]
            # Validates without exception
            recipe.validate()
            # Bounding box is computable and positive
            bounds = compute_bounds(recipe)
            assert bounds["height"] > 0
            assert bounds["width_x"] > 0
            assert bounds["width_y"] > 0
            assert recipe.collision in ALLOWED_COLLISIONS

            # Watertightness check
            info = verify_recipe_watertight(recipe)
            assert info["watertight"] or name == "torch"  # torch is wall-mounted

    def test_to_op_args_translates_base_origin_correctly(self):
        # Altar: plinth at z=12.5 (h=25) -> base z must be 0.0
        altar = PROP_RECIPES["altar"]
        op_args = altar.to_op_args("/Game/Props/SM_Altar")
        assert op_args["asset_path"] == "/Game/Props/SM_Altar"
        parts = op_args["parts"]

        # Base plinth
        plinth = parts[0]
        assert plinth["shape"] == "box"
        assert plinth["location"]["z"] == pytest.approx(0.0)

        # Pedestal: center was 55.0 (h=60) -> base z must be 55 - 30 = 25.0 (sits on plinth)
        pedestal = parts[1]
        assert pedestal["shape"] == "box"
        assert pedestal["location"]["z"] == pytest.approx(25.0)

        # Top slab: center was 95.0 (h=20) -> base z must be 95 - 10 = 85.0 (sits on pedestal)
        top = parts[2]
        assert top["shape"] == "box"
        assert top["location"]["z"] == pytest.approx(85.0)

    def test_cone_helper_and_recipe_validation(self):
        cone_part = _cone(radius=30.0, height=80.0, top_radius=5.0, loc={"x": 0.0, "y": 0.0, "z": 40.0})
        assert cone_part["shape"] == "cone"
        assert cone_part["radius"] == 30.0
        assert cone_part["height"] == 80.0
        assert cone_part["top_radius"] == 5.0

        recipe = PropRecipe(
            name="custom_cone_prop",
            parts=[cone_part],
            collision="convex",
            triangle_budget=600,
        )
        recipe.validate()
        op_args = recipe.to_op_args("/Game/Props/SM_Cone")
        # Base origin translation: center z 40 - 80/2 = 0.0
        assert op_args["parts"][0]["location"]["z"] == pytest.approx(0.0)

    def test_recipe_validation_catches_malformed_dimensions(self):
        # Non-positive box size
        with pytest.raises(ValueError, match="positive"):
            PropRecipe(name="bad_box", parts=[{"shape": "box", "size": [10.0, -5.0, 10.0]}])

        # Missing size in box
        with pytest.raises(ValueError, match="size"):
            PropRecipe(name="missing_size", parts=[{"shape": "box"}])

        # Non-positive cylinder radius
        with pytest.raises(ValueError, match="radius"):
            PropRecipe(name="bad_cyl", parts=[{"shape": "cylinder", "radius": 0.0, "height": 10.0}])

        # Invalid collision
        with pytest.raises(ValueError, match="collision"):
            PropRecipe(name="bad_col", parts=[_box([10.0, 10.0, 10.0])], collision="invalid_profile")


class TestThemesAndContrast:
    def test_relative_luminance_edge_colors_and_safe_bounds(self):
        # Standard pure black and white
        assert relative_luminance((0.0, 0.0, 0.0)) == pytest.approx(0.0, abs=1e-5)
        assert relative_luminance((1.0, 1.0, 1.0)) == pytest.approx(1.0, abs=1e-5)

        # 0..255 byte scale
        assert relative_luminance((255, 255, 255)) == pytest.approx(1.0, abs=1e-5)
        assert relative_luminance((0, 0, 0)) == pytest.approx(0.0, abs=1e-5)

        # Floating point rounding near 1.0 does NOT falsely scale down
        lum_round = relative_luminance((1.0001, 1.0, 1.0))
        assert lum_round == pytest.approx(1.0, abs=1e-2)

        # Negative and NaN clamped safely
        assert relative_luminance((-0.5, float("nan"), 0.0)) == pytest.approx(0.0, abs=1e-5)

    def test_validate_and_adjust_palette_guarantees_wcag_threshold(self):
        # Floor: mid-gray (0.5, 0.5, 0.5), accent with identical color -> contrast 1:1
        accent, warn = validate_and_adjust_palette((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), min_contrast=3.0)
        assert warn is not None
        ratio = wcag_contrast_ratio((0.5, 0.5, 0.5), accent)
        assert ratio >= 3.0, f"Contrast {ratio} failed 3:1 threshold"

        # Edge case: all candidates in user-supplied list are intentionally terrible
        poor_candidates = [(0.49, 0.49, 0.49), (0.51, 0.51, 0.51)]
        accent_guaranteed, warn = validate_and_adjust_palette(
            (0.5, 0.5, 0.5), (0.5, 0.5, 0.5), palette_candidates=poor_candidates, min_contrast=3.0
        )
        assert "guaranteed polarity" in warn
        ratio_guaranteed = wcag_contrast_ratio((0.5, 0.5, 0.5), accent_guaranteed)
        assert ratio_guaranteed >= 3.0

    def test_all_6_themes_satisfy_wcag_contrast(self):
        for theme_name in ["default", "stone_wood", "scifi_metal", "desert_sand", "snow_ice", "toon_flat"]:
            specs = get_theme_pbr_specs(theme_name, enforce_contrast=True)
            theme = THEMES[theme_name]
            floor_col = theme["floor"].base_color
            accent_spec = next(s for s in specs if "accent" in s.tags)
            ratio = wcag_contrast_ratio(floor_col, accent_spec.base_color)
            assert ratio >= 3.0, f"Theme {theme_name} accent contrast {ratio:.2f}:1 is below 3:1"


class TestNiagaraVFXPresets:
    def test_all_vfx_presets_valid_engine_assets(self):
        assert len(VFX_PRESETS) == 8
        for pid, preset in VFX_PRESETS.items():
            assert preset.preset_id == pid
            assert preset.template_system in VALID_TEMPLATE_SYSTEMS
            for emitter in preset.template_emitters:
                assert emitter in VALID_TEMPLATE_EMITTERS

            create_args = preset.to_create_args()
            assert "asset_path" in create_args
            assert "template_system" in create_args
            assert "template_emitters" in create_args

    def test_vfx_preset_validation_rejects_invalid_system(self):
        with pytest.raises(ValueError, match="template_system"):
            VFXPreset(
                preset_id="vfx.bad",
                template_path="/Game/VFX/NS_Bad",
                description="Invalid",
                template_system="NonExistentSystem123",
            )

    def test_vfx_palette_accent_color_override(self):
        p = get_vfx_preset("vfx.sparkle_burst")
        assert p is not None
        resolved = p.resolve_parameters(palette_accent=(0.1, 0.9, 0.5))
        assert resolved["User.Color"] == [0.1, 0.9, 0.5, 1.0]


class TestEpicPacksAndLicensing:
    def test_infer_asset_type_comprehensive(self):
        assert _infer_asset_type("Characters/SKM_Manny.uasset") == "skeletal_mesh"
        assert _infer_asset_type("Meshes/SM_Rock.uasset") == "mesh"
        assert _infer_asset_type("Materials/M_Grid.uasset") == "material"
        assert _infer_asset_type("Materials/MI_Grid_Gray.uasset") == "material"
        assert _infer_asset_type("Textures/T_Noise.uasset") == "texture"
        assert _infer_asset_type("Anims/ABP_Unarmed.uasset") == "animation"
        assert _infer_asset_type("Audio/SFX_Chime.uasset") == "sound"
        assert _infer_asset_type("VFX/NS_Sparkle.uasset") == "vfx"

    def test_collect_cook_directories(self):
        spec = {
            "player": {"mesh": "/Game/Characters/Mannequins/Meshes/SKM_Manny.SKM_Manny"},
            "level": {"blocks": ["/Game/LevelPrototyping/Meshes/SM_Cube", "/Game/GameForge/GD_Runtime"]},
        }
        dirs = collect_cook_directories(spec)
        assert "/Game/Characters" in dirs
        assert "/Game/LevelPrototyping" in dirs
        # Runtime GD data asset is excluded
        assert not any("GD_Runtime" in d for d in dirs)

    def test_update_default_game_ini_cook_dirs_crlf_safety(self, tmp_path):
        proj = tmp_path / "MyProject"
        config_dir = proj / "Config"
        config_dir.mkdir(parents=True)
        ini = config_dir / "DefaultGame.ini"
        ini.write_bytes(b"[/Script/UnrealEd.ProjectPackagingSettings]\r\nDirectoriesToAlwaysCook=(Path=\"/Game/Characters\")\r\n")

        update_default_game_ini_cook_dirs(proj, ["/Game/Characters", "/Game/LevelPrototyping"])
        raw = ini.read_bytes()
        assert b'DirectoriesToAlwaysCook=(Path="/Game/Characters")' in raw
        assert b'DirectoriesToAlwaysCook=(Path="/Game/LevelPrototyping")' in raw
        assert b"\r\n" in raw

    def test_library_license_local_and_alias_support(self):
        # LOCAL asset needs no attribution text
        decl_local = LicenceDecl(licence_class="LOCAL", user_confirmed_rights=True)
        decl_local.validate()

        # Lowercase and alias mapping
        decl_alias = LicenceDecl(licence_class="cc-0", user_confirmed_rights=True)
        decl_alias.validate()
        assert decl_alias.licence_class == "CC0"

        decl_prop = LicenceDecl(licence_class="proprietary", user_confirmed_rights=True)
        decl_prop.validate()
        assert decl_prop.licence_class == "PROPRIETARY"

        decl_pub = LicenceDecl(licence_class="public_domain", user_confirmed_rights=True)
        decl_pub.validate()
        assert decl_pub.licence_class == "PUBLIC_DOMAIN"
