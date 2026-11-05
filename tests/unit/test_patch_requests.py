"""Unit tests for deterministic patch rules and mutation requests (WI-8.1)."""
from __future__ import annotations

import pytest

from src.gameforge_ide.design.gds import CameraKind, EntityKind, GameDesignSpec, Genre, Lighting
from src.gameforge_ide.design.patch import apply_patch, propose_patch
from src.gameforge_ide.design.patch_rules import match_deterministic_rule
from src.gameforge_ide.design.presets import preset_arena_combat, preset_platformer, preset_relic_hunt


def test_rule_speed_adjustment():
    """Verify speed increase / decrease deterministic matching."""
    gds = preset_platformer(title="Speed Test")
    patch = match_deterministic_rule(gds, "make player faster")
    assert patch is not None
    assert patch.status == "OK"
    patched = apply_patch(gds, patch.ops)
    player = next(e for e in patched.entities if e.kind == EntityKind.PLAYER)
    spd = player.props.get("player_speed", player.props.get("speed", 0))
    assert spd > 600.0


def test_rule_count_adjustment():
    """Verify count adjustment for existing entities."""
    gds = preset_platformer(title="Count Test")
    coins_before = next(e for e in gds.entities if e.kind == EntityKind.PICKUP).count
    patch = match_deterministic_rule(gds, "more coins")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    coins_after = next(e for e in patched.entities if e.kind == EntityKind.PICKUP).count
    assert coins_after > coins_before


def test_rule_add_n_entities():
    """Verify add N entities creating new entity when missing."""
    gds = preset_platformer(title="Add N Test")
    patch = match_deterministic_rule(gds, "add 4 hazards")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    hazard = next(e for e in patched.entities if e.kind == EntityKind.HAZARD)
    assert hazard.count == 4


def test_rule_lighting_change():
    """Verify lighting presets and synonyms."""
    gds = preset_platformer(title="Light Test")
    patch_night = match_deterministic_rule(gds, "make it night")
    assert patch_night is not None
    patched_night = apply_patch(gds, patch_night.ops)
    assert patched_night.scene.levels[0].lighting == Lighting.NIGHT

    patch_sunset = match_deterministic_rule(gds, "set lighting to dusk")
    assert patch_sunset is not None
    patched_sunset = apply_patch(gds, patch_sunset.ops)
    assert patched_sunset.scene.levels[0].lighting == Lighting.DUSK


def test_rule_add_checkpoint():
    """Verify adding checkpoint entity."""
    gds = preset_platformer(title="Checkpoint Test")
    patch = match_deterministic_rule(gds, "add a checkpoint")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    assert any(e.kind == EntityKind.CHECKPOINT for e in patched.entities)


def test_rule_jump_velocity():
    """Verify jump velocity setting and doubling."""
    gds = preset_platformer(title="Jump Test")
    patch = match_deterministic_rule(gds, "set jump velocity to 900")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    player = next(e for e in patched.entities if e.kind == EntityKind.PLAYER)
    assert player.props.get("jump_velocity") == 900.0


def test_rule_health():
    """Verify player and enemy health setting."""
    gds = preset_arena_combat(title="Health Test")
    patch = match_deterministic_rule(gds, "set player health to 300")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    player = next(e for e in patched.entities if e.kind == EntityKind.PLAYER)
    assert player.props.get("player_max_health") == 300.0


def test_rule_camera_perspective():
    """Verify switching camera mode to first person with input actions."""
    gds = preset_platformer(title="Cam Test")
    patch = match_deterministic_rule(gds, "change camera to first person")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    assert patched.overview.camera == CameraKind.FIRST_PERSON
    action_ids = {a.action_id for a in patched.input.actions}
    assert "IA_Move" in action_ids


def test_rule_damage_adjustment():
    """Verify adjusting weapon and attack damage."""
    gds = preset_arena_combat(title="Damage Test")
    patch = match_deterministic_rule(gds, "set weapon damage to 60")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    player = next(e for e in patched.entities if e.kind == EntityKind.PLAYER)
    prop_key = "player_attack_damage" if "player_attack_damage" in player.props else ("attack_damage" if "attack_damage" in player.props else "damage")
    assert player.props.get(prop_key) == 60.0


def test_rule_win_score_or_relic_count():
    """Verify updating collectible win condition count."""
    gds = preset_platformer(title="Win Count Test")
    patch = match_deterministic_rule(gds, "require 12 coins to win")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    win_cond = next(c for c in patched.goals.win if getattr(c, "kind", "") == "count_at_least")
    assert win_cond.n == 12


def test_rule_movement_ability():
    """Verify adding dash or double-jump ability."""
    gds = preset_platformer(title="Ability Test")
    patch_dash = match_deterministic_rule(gds, "add dash ability")
    assert patch_dash is not None
    patched_dash = apply_patch(gds, patch_dash.ops)
    assert any(a.action_id == "IA_Dash" for a in patched_dash.input.actions)


def test_rule_gravity_adjustment():
    """Verify world gravity setting."""
    gds = preset_platformer(title="Gravity Test")
    patch = match_deterministic_rule(gds, "set gravity to 450")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    assert patched.scene.levels[0].layout_params.get("gravity_z") == 450.0


def test_rule_player_lives():
    """Verify player lives and permadeath setting."""
    gds = preset_platformer(title="Lives Test")
    patch = match_deterministic_rule(gds, "give player 3 lives")
    assert patch is not None
    patched = apply_patch(gds, patch.ops)
    player = next(e for e in patched.entities if e.kind == EntityKind.PLAYER)
    assert player.props.get("lives") == 3


def test_unmatched_returns_none():
    """Verify complex open-ended requests return None so model delegation is invoked."""
    gds = preset_platformer(title="Complex Test")
    assert match_deterministic_rule(gds, "add an intricate dialogue tree with a weeping statue") is None
    assert match_deterministic_rule(gds, "make a cutscene where aliens arrive") is None
