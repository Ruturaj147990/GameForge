"""Audit 2026-10-30: rule-integrity regressions in generated recipe gameplay sources."""

from __future__ import annotations

from tests.fixtures.legacy_recipes.card_battler.recipe import CardBattlerParams, generate as gen_cards
from tests.fixtures.legacy_recipes.platformer.recipe import PlatformerParams, generate as gen_platformer


def _joined(files):
    return "\n".join(files.values())


def test_card_battler_rules_enforce_opponent_energy():
    src = _joined(gen_cards(CardBattlerParams()))
    # The state component, not the AI, owns and enforces the opponent's budget.
    assert "int32 OpponentEnergy;" in src
    assert "bForPlayer ? CurrentEnergy : OpponentEnergy" in src
    assert "OpponentEnergy -= Card.Def.EnergyCost;" in src
    assert "OpponentEnergy = GFCardConfig::BaseEnergyPerTurn;" in src
    assert "GFCardConfig::BaseEnergyPerTurn;\n\n\t// Strategic" not in src  # no AI-local budget
    assert "Opponent cannot play a costed card with 0 energy" in src


def test_platformer_triggers_require_player_pawn():
    src = _joined(gen_platformer(PlatformerParams()))
    assert "inline bool GFPlatformerIsPlayerPawn" in src
    assert src.count("GFPlatformerIsPlayerPawn(OtherActor)") == 3
    assert "OtherActor && OtherActor != this" not in src


def test_gameplay_event_markers_present_in_all_playable_recipes():
    """Packaged games log GF_EVENT markers at real transitions so real-input tests can check outcomes."""
    from tests.fixtures.legacy_recipes.arena_combat.recipe import ArenaCombatParams, generate as gen_arena
    from tests.fixtures.legacy_recipes.procedural_world.recipe import ProceduralWorldParams, generate as gen_world
    expected = {
        "platformer": (_joined(gen_platformer(PlatformerParams())), ["moved", "jump", "collect", "checkpoint", "respawn", "reset"]),
        "arena": (_joined(gen_arena(ArenaCombatParams())), ["moved", "attack", "player_damaged", "enemy_damaged", "reset"]),
        "cards": (_joined(gen_cards(CardBattlerParams())), ["card_play", "turn_end", "reset"]),
        "world": (_joined(gen_world(ProceduralWorldParams())), ["moved", "jump", "reset", "landmark_discovered"]),
    }
    for name, (src, events) in expected.items():
        assert '#define GF_EVENT(Format, ...)' in src, name
        for ev in events:
            assert f'GF_EVENT("{ev}' in src, (name, ev)


def test_procedural_world_binds_restart():
    from tests.fixtures.legacy_recipes.procedural_world.recipe import ProceduralWorldParams, generate as gen_world
    src = _joined(gen_world(ProceduralWorldParams()))
    assert 'BindAction(TEXT("Restart"), IE_Pressed, this, &AGFProceduralCharacter::RequestWorldReset)' in src


def test_real_input_verifier_requires_observed_gameplay_events():
    """Dispatching input is not a pass: the expected GF_EVENT (with key=value tokens) must be observed."""
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "verify_real_input_packaged", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "engine" / "verify_real_input_packaged.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    events = ["moved x=10 y=0 z=90", "card_play ok=0 hand=0 lane=1 energy=3"]
    assert mod._expectation_met("moved", events)
    assert mod._expectation_met("card_play", events)
    assert not mod._expectation_met("card_play ok=1", events)
    assert not mod._expectation_met("jump", events)
    assert not mod._expectation_met("move", events)  # name must match exactly


def test_platformer_sources_using_player_guard_include_its_header():
    files = gen_platformer(PlatformerParams())
    for path, src in files.items():
        if "GFPlatformerIsPlayerPawn(OtherActor)" in src:
            assert '#include "GFPlatformerConfig.h"' in src, path


def test_card_hud_reads_existing_turn_counter():
    """The HUD referenced State->TurnCount (not a member) so the recipe did not compile."""
    src = _joined(gen_cards(CardBattlerParams()))
    assert "State->TurnCount" not in src
    assert "State->CurrentTurnNumber" in src
