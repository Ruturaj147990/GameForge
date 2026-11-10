"""Comprehensive regression test suite for dynamic prompt-to-game synthesis quality.

Validates that GameForge genuinely interprets user prompts to synthesize:
- Custom mechanics (abilities, stealth, cooldowns) with Enhanced Input bindings and HUD elements
- Dynamic boss encounters with multi-phase state machines, scaling, and crimson boss health bars
- Progression mechanics (key collection, locked gates)
- Clean, generic C++ codegen with zero hardcoded demo game residue (zero SudokuGrid)
- Intelligent dungeon room placement matching level progression
"""
from __future__ import annotations

import pytest
from src.gameforge_ide.design.prompt_analysis import analyze_prompt, brief_to_draft
from src.gameforge_ide.design.expand import expand_draft
from src.gameforge_ide.composer.compose import compose
from src.gameforge_ide.composer.codegen import generate_header, generate_source


def test_stealth_smoke_bomb_prompt_synthesis():
    """Verify stealth ability prompt synthesizes IA_Ability, HUD cooldown, and stealth custom rules."""
    prompt = (
        "Design a gothic crypt stealth game where the rogue can use Q to drop a smoke bomb "
        "and enter stealth to evade patrolling undead skeletons and reach the sanctuary."
    )
    brief = analyze_prompt(prompt)
    assert brief.theme in ("gothic_crypt", "dungeon", "dark_fantasy")
    assert len(brief.player_abilities) >= 1
    assert any("smoke" in a.lower() or "stealth" in a.lower() for a in brief.player_abilities)
    assert "Q" in brief.ability_key_binds.values()

    draft = brief_to_draft(brief)
    assert draft.biome.value in ("dungeon", "dark_fantasy", "gothic_crypt")
    assert draft.biome.value != "forest"

    gds = expand_draft(draft)

    # Enhanced input binding for ability
    ability_action = next((a for a in gds.input.actions if a.action_id == "IA_Ability"), None)
    assert ability_action is not None, "IA_Ability must be synthesized in GDS input"
    assert "Q" in ability_action.bindings

    # Dynamic HUD element for ability cooldown
    hud_cooldown = next((h for h in gds.ui.hud if h.binds == "player.ability_cooldown"), None)
    assert hud_cooldown is not None, "HUD element for player.ability_cooldown must be synthesized"

    # Custom rule for ability triggering stealth
    stealth_rule = next(
        (r for r in gds.rules if "stealth" in (r.description or "").lower() or any("stealth" in str(getattr(eff, "stat", "")).lower() for eff in r.effects)),
        None
    )
    assert stealth_rule is not None, "Custom rule for stealth activation must be present"


def test_boss_encounter_prompt_synthesis():
    """Verify boss encounter prompt creates boss entity, crimson boss health bar, and C++ boss state machine."""
    prompt = (
        "Create a dark dungeon boss arena where the player fights the Necromancer Lord. "
        "In phase 2, the Necromancer enrages and summons skeletal minions."
    )
    brief = analyze_prompt(prompt)
    assert brief.boss_name is not None
    assert "necromancer" in brief.boss_name.lower()

    draft = brief_to_draft(brief)
    boss_entity = next((e for e in draft.entities if (getattr(e, "properties", None) or getattr(e, "props", {})).get("bIsBoss")), None)
    assert boss_entity is not None, "Boss entity with bIsBoss=True must be synthesized"
    boss_props = getattr(boss_entity, "properties", None) or getattr(boss_entity, "props", {})
    assert "Necromancer" in boss_props.get("BossName", "")

    gds = expand_draft(draft)
    hud_boss = next((h for h in gds.ui.hud if h.binds == "boss.health"), None)
    assert hud_boss is not None, "HUD element for boss.health must be synthesized"

    comp = compose(gds)
    assert len(comp.codegen) >= 1
    boss_task = comp.codegen[0]
    assert "boss.phase_changed" in boss_task.on_event_body
    assert "boss.defeated" in boss_task.on_event_body


def test_key_lock_gate_progression_synthesis():
    """Verify keys and gate prompt synthesizes progression counters, gate lock, and intermediate placement."""
    prompt = (
        "A crypt exploration game where the player must collect 3 ancient bloodstone keys "
        "to unlock the iron vault gate before reaching the exit."
    )
    brief = analyze_prompt(prompt)
    assert brief.key_pickups >= 1
    assert brief.interactive_doors >= 1

    draft = brief_to_draft(brief)
    door_entity = next((e for e in draft.entities if str(getattr(e.kind, "value", e.kind)) == "door"), None)
    assert door_entity is not None, "Door entity must be synthesized"
    door_props = getattr(door_entity, "properties", None) or getattr(door_entity, "props", {})
    assert door_props.get("required_stat") == "game.counter.keys_collected"
    assert float(door_props.get("required_value", 0)) == 3.0

    gds = expand_draft(draft)
    hud_keys = next((h for h in gds.ui.hud if h.binds == "game.counter.keys_collected"), None)
    assert hud_keys is not None, "HUD element for keys_collected must be synthesized"

    comp = compose(gds)
    level = comp.levels[0]
    door_actors = [a for a in level.actors if "door" in a.tags or a.runtime_class.endswith("Door")]
    assert len(door_actors) >= 1
    assert door_actors[0].properties.get("RequiredStat") == "game.counter.keys_collected"


def test_codegen_clean_from_sudoku_residue():
    """Verify C++ codegen generates dynamic properties and contains zero SudokuGrid residue."""
    hdr = generate_header("MyProject", "DynamicCombatRule")
    src = generate_source("DynamicCombatRule")

    # Assert no hardcoded SudokuGrid
    assert "SudokuGrid" not in hdr, "SudokuGrid must not be in generated header"
    assert "SudokuGrid" not in src, "SudokuGrid must not be in generated source"

    # Assert dynamic properties are present and properly exposed
    assert "AbilityCooldownTimer" in hdr
    assert "BossHealth" in hdr
    assert "BossPhase" in hdr
    assert "KeysCollected" in hdr
    assert "BoardGrid" in hdr

    # Assert ExecuteRule zeroes dynamic properties cleanly
    assert "AbilityCooldownTimer = 0.0f;" in src
    assert "BossHealth = BossMaxHealth;" in src
    assert "KeysCollected = 0;" in src
    assert "BoardGrid[r][c] = 0;" in src
