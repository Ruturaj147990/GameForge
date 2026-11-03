"""Legacy recipe adapter: maps GameDesignSpec back to legacy recipe params (P1 WI-1.8)."""
from __future__ import annotations

import re
from typing import Union

from tests.fixtures.legacy_recipes.arena_combat.recipe import ArenaCombatParams
from tests.fixtures.legacy_recipes.card_battler.recipe import CardBattlerParams
from tests.fixtures.legacy_recipes.grid_board_game.recipe import GridBoardParams
from tests.fixtures.legacy_recipes.platformer.recipe import PlatformerParams
from tests.fixtures.legacy_recipes.procedural_world.recipe import ProceduralWorldParams
from .gds import EntityKind, GameDesignSpec, Genre

DEFAULT_PALETTE = ["#2E3440", "#88C0D0", "#EBCB8B", "#BF616A"]


class LegacyUnsupported(RuntimeError):
    """Raised when a GDS cannot be mapped back to one of the 5 legacy recipes."""
    pass


def _hex_to_rgb(hex_code: str) -> tuple[float, float, float]:
    hex_code = hex_code.lstrip("#")
    r = int(hex_code[0:2], 16) / 255.0
    g = int(hex_code[2:4], 16) / 255.0
    b = int(hex_code[4:6], 16) / 255.0
    return (round(r, 2), round(g, 2), round(b, 2))


def to_legacy_params(
    gds: GameDesignSpec,
) -> Union[GridBoardParams, PlatformerParams, ArenaCombatParams, CardBattlerParams, ProceduralWorldParams]:
    """Convert a preset-derived GDS to legacy recipe params, or raise LegacyUnsupported."""
    if getattr(gds.meta, "generator", "").startswith("model:"):
        raise LegacyUnsupported("Model-generated designs route to modern Composer + Forge DAG path")
    if hasattr(gds.overview, "camera") and str(getattr(gds.overview.camera, "value", gds.overview.camera)) == "first_person":
        raise LegacyUnsupported("First-person games route to modern Composer + Forge DAG path")
    genre = gds.overview.genre

    if genre == Genre.GRID_BOARD:
        board = next((e for e in gds.entities if e.kind == EntityKind.BOARD), None)
        if not board:
            raise LegacyUnsupported("grid_board requires a board entity")
        props = dict(board.props)

        if gds.art.palette == DEFAULT_PALETTE and "player1_color" not in props:
            p1_color = (0.10, 0.45, 1.00)
            p2_color = (1.00, 0.25, 0.20)
            board_color = (0.85, 0.85, 0.88)
        else:
            p1_color = props.get("player1_color") or _hex_to_rgb(gds.art.palette[0])
            p2_color = props.get("player2_color") or _hex_to_rgb(gds.art.palette[1])
            board_color = props.get("board_color") or _hex_to_rgb(gds.art.palette[2])

        params = GridBoardParams(
            project_name=gds.meta.project_name,
            display_title=gds.meta.title,
            board_size=int(props.get("board_size", 3)),
            win_length=int(props.get("win_length", 3)),
            vs_ai=bool(props.get("vs_ai", True)),
            gravity=bool(props.get("gravity", False)),
            ai_level=str(props.get("ai_level", "perfect")),
            cell_size_cm=float(props.get("cell_size_cm", 200.0)),
            player1_color=p1_color,
            player2_color=p2_color,
            board_color=board_color,
        )

    elif genre == Genre.PLATFORMER:
        player = next((e for e in gds.entities if e.kind == EntityKind.PLAYER), None)
        if not player:
            raise LegacyUnsupported("platformer requires a player entity")
        pickups = next((e for e in gds.entities if e.kind == EntityKind.PICKUP), None)
        target = pickups.count if pickups else 5
        props = dict(player.props)

        params = PlatformerParams(
            project_name=gds.meta.project_name,
            display_title=gds.meta.title,
            collectible_target=target,
            difficulty=gds.progression.difficulty,
            starting_level="Level1",
            player_speed=float(props.get("player_speed", 600.0)),
            jump_velocity=float(props.get("jump_velocity", 650.0)),
            gravity_scale=float(props.get("gravity_scale", 1.2)),
            air_control=float(props.get("air_control", 0.35)),
            kill_z=float(props.get("kill_z", -500.0)),
        )

    elif genre == Genre.ARENA_COMBAT:
        spawner = next((e for e in gds.entities if e.kind == EntityKind.SPAWNER), None)
        player = next((e for e in gds.entities if e.kind == EntityKind.PLAYER), None)
        s_props = dict(spawner.props) if spawner else {}
        p_props = dict(player.props) if player else {}

        params = ArenaCombatParams(
            project_name=gds.meta.project_name,
            display_title=gds.meta.title,
            difficulty=gds.progression.difficulty,
            starting_level="Level1",
            wave_count=int(s_props.get("wave_count", 3)),
            enemies_per_wave=int(s_props.get("enemies_per_wave", 4)),
            player_max_health=float(p_props.get("player_max_health", 100.0)),
            player_attack_damage=float(p_props.get("player_attack_damage", 35.0)),
            player_attack_range=float(p_props.get("player_attack_range", 250.0)),
            player_attack_cooldown=float(p_props.get("player_attack_cooldown", 0.4)),
            enemy_max_health=float(s_props.get("enemy_max_health", 50.0)),
            enemy_attack_damage=float(s_props.get("enemy_attack_damage", 15.0)),
            enemy_attack_range=float(s_props.get("enemy_attack_range", 120.0)),
            enemy_attack_cooldown=float(s_props.get("enemy_attack_cooldown", 1.0)),
            enemy_speed=float(s_props.get("enemy_speed", 350.0)),
        )

    elif genre == Genre.CARD_BATTLER:
        table = next((e for e in gds.entities if e.kind == EntityKind.CARD_TABLE), None)
        t_props = dict(table.props) if table else {}

        params = CardBattlerParams(
            project_name=gds.meta.project_name,
            display_title=gds.meta.title,
            difficulty=gds.progression.difficulty,
            starting_level="Level1",
            player_base_health=int(t_props.get("player_base_health", 30)),
            opponent_base_health=int(t_props.get("opponent_base_health", 30)),
            starting_hand_size=int(t_props.get("starting_hand_size", 4)),
            max_hand_size=int(t_props.get("max_hand_size", 7)),
            base_energy_per_turn=int(t_props.get("base_energy_per_turn", 3)),
            lane_count=int(t_props.get("lane_count", 3)),
        )

    elif genre == Genre.EXPLORATION:
        if not gds.scene.levels or not gds.scene.levels[0].layout_params:
            raise LegacyUnsupported("exploration genre without procedural layout_params needs the composer (planned for phase 6)")
        lvl = gds.scene.levels[0]
        lp = dict(lvl.layout_params)

        params = ProceduralWorldParams(
            project_name=gds.meta.project_name,
            display_title=gds.meta.title,
            seed=int(lvl.seed or 2026),
            terrain_type=str(lp.get("terrain_type", "Valley")),
            elevation_scale=float(lp.get("elevation_scale", 1800.0)),
            component_count_x=int(lp.get("component_count_x", 2)),
            component_count_y=int(lp.get("component_count_y", 2)),
            quads_per_section=int(lp.get("quads_per_section", 63)),
            sections_per_component=int(lp.get("sections_per_component", 1)),
            road_width=float(lp.get("road_width", 350.0)),
            foliage_density=int(lp.get("foliage_density", 40)),
            landmark_type=str(lp.get("landmark_type", "Ruins")),
            player_speed=float(lp.get("player_speed", 650.0)),
            starting_level="Level1",
        )

    else:
        raise LegacyUnsupported(f"genre '{genre.value}' needs the composer (planned for phase 6)")

    params.validate()
    return params
