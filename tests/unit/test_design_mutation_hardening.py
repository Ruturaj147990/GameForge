"""Unit and regression tests for GDS Patch & Mutation Specialists (DEF-090 through DEF-098).

Verifies:
- RFC 6902 JSON Patch engine robustness, ancestor protection, and named path navigation
- Discriminator and event name auto-normalization
- Entity removal cascades preventing cross-reference validation failures
- All 18 deterministic patch rules with natural phrasing variations
- Add-entity instantiation with schema-compliant kit modules and properties
- DraftEntity parameter preservation and CSG prop / key-value note extraction
- InputSpec camera, navigation, and jump action bindings
- Canonical design schema module and helper functions
"""
from __future__ import annotations

import pytest

from src.gameforge_ide.design.draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from src.gameforge_ide.design.expand import expand_draft
from src.gameforge_ide.design.gds import (
    CameraKind,
    EntityKind,
    GameDesignSpec,
    Genre,
    Lighting,
)
from src.gameforge_ide.design.patch import (
    PatchError,
    _compact_entities_list,
    apply_patch,
    propose_patch,
    summarize_patch,
)
from src.gameforge_ide.design.patch_rules import match_deterministic_rule
from src.gameforge_ide.design.presets import preset_platformer, preset_relic_hunt
from src.gameforge_ide.design.schema import (
    draft_json_schema,
    gds_json_schema,
    validate_draft,
    validate_gds,
)


# ── 1. Canonical Schema Module & Draft Normalization (DEF-098) ────────────────

def test_canonical_schema_module_exports_and_helpers():
    """Verify src.gameforge_ide.design.schema exports and validation functions."""
    assert gds_json_schema() is not None
    assert draft_json_schema() is not None

    draft_dict = {
        "title": "Runner",
        "genre": "platformer",
        "camera": "third_person",
        "win": [{"type": "reach_goal"}],
    }
    validated_d = validate_draft(draft_dict)
    assert validated_d.title == "Runner"

    spec = expand_draft(validated_d)
    validated_s = validate_gds(spec.model_dump())
    assert validated_s.meta.title == "Runner"


def test_draft_enum_hyphen_normalization():
    """Verify DesignDraft normalizes hyphenated enum strings from LLMs."""
    draft = DesignDraft.model_validate({
        "title": "Arena Brawl",
        "genre": "arena-combat",
        "camera": "first-person",
        "win": [{"type": "defeat-all"}],
        "lose": [{"type": "health-zero"}],
    })
    assert draft.genre == Genre.ARENA_COMBAT
    assert draft.camera == CameraKind.FIRST_PERSON
    assert draft.win[0].type == "defeat_all"
    assert draft.lose[0].type == "health_zero"


# ── 2. RFC 6902 Patch Security & Named Navigation (DEF-091, DEF-092) ──────────

def test_protected_path_ancestor_protection():
    """Verify that replacing /meta or / is strictly rejected to protect gds_id and created_at."""
    gds = preset_platformer(title="Protected Test")

    # Attempt replacing /meta directly
    with pytest.raises(PatchError) as exc_info:
        apply_patch(gds, [{"op": "replace", "path": "/meta", "value": {"title": "Hacked"}}])
    assert "protected" in str(exc_info.value)

    # Attempt non-dict op structure
    with pytest.raises(PatchError) as exc_info2:
        apply_patch(gds, ["invalid_string_op"])  # type: ignore
    assert "Patch op must be a JSON object" in str(exc_info2.value)


def test_named_identifier_path_navigation():
    """Verify RFC 6902 navigation allows targeting entities by entity_id instead of numeric index."""
    gds = preset_relic_hunt(title="Named Nav Test")
    guard_ent = next(e for e in gds.entities if e.entity_id == "guard")
    old_speed = guard_ent.props["move_speed"]

    # Patch targeting /entities/guard/props/move_speed
    ops = [{"op": "replace", "path": "/entities/guard/props/move_speed", "value": 475.0}]
    patched = apply_patch(gds, ops)
    p_guard = next(e for e in patched.entities if e.entity_id == "guard")
    assert p_guard.props["move_speed"] == 475.0


def test_condition_discriminator_and_event_normalization():
    """Verify that apply_patch tolerantly normalizes kind='count' and underscore events."""
    gds = preset_platformer(title="Norm Test")
    ops = [
        {
            "op": "add",
            "path": "/goals/win/-",
            "value": {
                "kind": "count",  # Normalized to count_at_least
                "event": "pickup_collected",  # Normalized to pickup.collected
                "n": 3,
            },
        }
    ]
    patched = apply_patch(gds, ops)
    added_cond = patched.goals.win[-1]
    assert added_cond.kind == "count_at_least"
    assert getattr(added_cond, "event") == "pickup.collected"
    assert patched.meta.updated_at is not None


# ── 3. Token Explosion Prevention (DEF-093) ───────────────────────────────────

def test_compact_entities_list_bounds_and_token_efficiency():
    """Verify _compact_entities_list caps entity counts and truncates coordinates to save tokens."""
    # Generate 30 synthetic entities with large points arrays
    large_entities = []
    for i in range(30):
        large_entities.append({
            "entity_id": f"entity_{i}",
            "kind": "prop" if i > 2 else ("player" if i == 0 else "goal"),
            "placement": {
                "strategy": "fixed",
                "points_m": [{"x": float(j), "y": float(j), "z": 0.0} for j in range(50)],
            },
            "props": {"items": list(range(20))},
        })

    compacted = _compact_entities_list(large_entities, query_terms=["entity_5"], max_entities=10)
    assert len(compacted) <= 10
    # Relevant entity_5, player, and goal must be prioritized
    eids = [e["entity_id"] for e in compacted]
    assert "player" in [e.get("kind") for e in compacted]
    assert "entity_5" in eids

    # Coordinate points truncated to 2
    for e in compacted:
        pts = e["placement"]["points_m"]
        assert len(pts) <= 2
        assert len(e["props"]["items"]) <= 5


# ── 4. Entity Instantiation with Kit Schemas (DEF-090) ─────────────────────────

def test_add_n_entities_uses_valid_kit_modules_and_props():
    """Verify Rule 3 creates entities with correct module IDs (kit.enemy_melee) and valid props."""
    gds = preset_platformer(title="Add Kit Test")

    # Add 3 enemies (was failing with kit.enemy and invalid props)
    patch_enemy = match_deterministic_rule(gds, "add 3 enemies")
    assert patch_enemy is not None
    assert patch_enemy.status == "OK"
    patched = apply_patch(gds, patch_enemy.ops)
    enemy = next((e for e in patched.entities if e.kind == EntityKind.ENEMY), None)
    assert enemy is not None
    assert enemy.module == "kit.enemy_melee"
    assert enemy.count == 3
    assert "attack_damage" in enemy.props
    assert "move_speed" in enemy.props

    # Add 2 guards
    patch_guard = match_deterministic_rule(gds, "add two guards")
    assert patch_guard is not None
    patched2 = apply_patch(gds, patch_guard.ops)
    guard = next((e for e in patched2.entities if e.kind == EntityKind.GUARD), None)
    assert guard is not None
    assert guard.module == "kit.guard"
    assert guard.count == 2
    assert "patrol_radius" in guard.props
    assert "move_speed" in guard.props


# ── 5. Entity Removal Cascades (DEF-094) ───────────────────────────────────────

def test_remove_entity_cascades_and_preserves_cross_refs():
    """Verify Rule 10 cleanly removes entity and any rules/goals referencing its unique events."""
    draft = DesignDraft(
        title="Stealth Adventure",
        genre=Genre.ACTION_ADVENTURE,
        camera=CameraKind.THIRD_PERSON,
        entities=[DraftEntity(kind=EntityKind.GUARD, count=2)],
        win=[DraftWin(type="reach_goal")],
        lose=[DraftLose(type="caught_by_guard")],
    )
    gds = expand_draft(draft)
    # Verify stealth draft has guards and a loss condition for guard.spotted_player
    assert any(e.kind == EntityKind.GUARD for e in gds.entities)
    assert any(getattr(c, "event", None) == "guard.spotted_player" for c in gds.goals.lose)

    # Remove guard
    prop = match_deterministic_rule(gds, "remove guard")
    assert prop is not None
    assert prop.status == "OK"

    # Must apply without cross-reference validation error
    patched = apply_patch(gds, prop.ops)
    assert not any(e.kind == EntityKind.GUARD for e in patched.entities)
    # The lose condition for guard.spotted_player must have been cascaded and removed
    assert not any(getattr(c, "event", None) == "guard.spotted_player" for c in patched.goals.lose)


def test_fewer_relics_adjusts_win_goal_condition():
    """Verify Rule 2 decreases goal required count if count is reduced below win condition."""
    gds = preset_relic_hunt(title="Goal Adjust Test")
    relic = next(e for e in gds.entities if e.entity_id == "relics")
    assert relic.count == 5

    prop = match_deterministic_rule(gds, "fewer relics")
    assert prop is not None
    patched = apply_patch(gds, prop.ops)
    new_relic = next(e for e in patched.entities if e.entity_id == "relics")
    assert new_relic.count < 5

    # Any CountAtLeast in goals.win must not exceed new_count
    for c in patched.goals.win:
        if getattr(c, "kind", "") == "count_at_least" and getattr(c, "event", "") == "pickup.collected":
            assert c.n <= new_relic.count


# ── 6. Deterministic Patch Rules Robustness (DEF-095) ──────────────────────────

def test_patch_rules_phrasing_variations():
    """Verify deterministic rules withstand natural human wording variations."""
    gds = preset_relic_hunt(title="Phrasing Test")

    # Rule 1: speed variations
    p1 = match_deterministic_rule(gds, "make the guards move faster")
    assert p1 is not None and apply_patch(gds, p1.ops)

    p1b = match_deterministic_rule(gds, "increase guard speed to 450")
    assert p1b is not None and apply_patch(gds, p1b.ops)

    # Rule 4: lighting variations
    p4 = match_deterministic_rule(gds, "make it daytime")
    assert p4 is not None
    patched_light = apply_patch(gds, p4.ops)
    assert patched_light.scene.levels[0].lighting == Lighting.DAY

    # Rule 5: checkpoint variations
    p5 = match_deterministic_rule(gds, "create a checkpoint")
    assert p5 is not None and apply_patch(gds, p5.ops)

    # Rule 6: hazard variations
    p6 = match_deterministic_rule(gds, "add spikes")
    assert p6 is not None and apply_patch(gds, p6.ops)

    # Rule 7: second level dynamic id
    p7 = match_deterministic_rule(gds, "add another level")
    assert p7 is not None
    patched_lvl = apply_patch(gds, p7.ops)
    assert len(patched_lvl.scene.levels) == 2
    assert patched_lvl.scene.levels[1].level_id == "level_2"

    # Rule 9: title rename variations
    p9 = match_deterministic_rule(gds, "change game title to Ember Quest")
    assert p9 is not None
    patched_t = apply_patch(gds, p9.ops)
    assert patched_t.meta.title == "Ember Quest"

    # Rule 11: door with key variations
    p11 = match_deterministic_rule(gds, "add locked door with key")
    assert p11 is not None and apply_patch(gds, p11.ops)

    # Rule 13: health variations
    p13 = match_deterministic_rule(gds, "give player more health")
    assert p13 is not None and apply_patch(gds, p13.ops)

    # Rule 14: jump variations
    p14 = match_deterministic_rule(gds, "higher jump")
    assert p14 is not None and apply_patch(gds, p14.ops)

    # Rule 15: difficulty variations
    p15 = match_deterministic_rule(gds, "make the game harder")
    assert p15 is not None
    patched_diff = apply_patch(gds, p15.ops)
    assert patched_diff.progression.difficulty == "hard"

    # Rule 16: art style variations
    p16 = match_deterministic_rule(gds, "make style cartoon")
    assert p16 is not None
    patched_art = apply_patch(gds, p16.ops)
    assert patched_art.art.style == "toon"

    # Rule 17: camera variations
    p17 = match_deterministic_rule(gds, "switch to first person")
    assert p17 is not None
    patched_cam = apply_patch(gds, p17.ops)
    assert patched_cam.overview.camera == CameraKind.FIRST_PERSON

    # Rule 18: timer variations
    p18 = match_deterministic_rule(gds, "give player 45 seconds")
    assert p18 is not None and apply_patch(gds, p18.ops)


def test_rule_12_combat_adds_fire_action():
    """Verify Rule 12 adds IA_Fire action binding so player can shoot."""
    gds = preset_platformer(title="Combat Test")
    prop = match_deterministic_rule(gds, "add shooting combat with enemies")
    assert prop is not None
    patched = apply_patch(gds, prop.ops)
    action_ids = [a.action_id for a in patched.input.actions]
    assert "IA_Fire" in action_ids


# ── 7. Draft Expansion & Parameter Preservation (DEF-096, DEF-097) ────────────

def test_expand_draft_preserves_custom_props_and_note_recipes():
    """Verify expand_draft preserves custom props, tags, and extracts CSG prop recipes."""
    draft = DesignDraft(
        title="Custom Dungeon",
        genre=Genre.DUNGEON_CRAWLER,
        camera=CameraKind.THIRD_PERSON,
        pitch="Explore dungeon with custom prop chests and barrels",
        entities=[
            DraftEntity(kind=EntityKind.PROP, count=2, note="ancient chest"),
            DraftEntity(
                kind=EntityKind.ENEMY,
                count=3,
                note="speed: 400, health: 120",
                props={"attack_damage": 22.0},
                tags=["elite"],
            ),
        ],
        win=[DraftWin(type="defeat_all")],
        lose=[DraftLose(type="health_zero")],
    )

    spec = expand_draft(draft)

    # 1. Chest prop recipe extraction
    prop_ent = next(e for e in spec.entities if e.kind == EntityKind.PROP)
    assert prop_ent.props.get("recipe") == "chest"

    # 2. Custom enemy parameters preserved from props and note
    enemy_ent = next(e for e in spec.entities if e.kind == EntityKind.ENEMY)
    assert enemy_ent.props["move_speed"] == 400.0
    assert enemy_ent.props["max_health"] == 120.0
    assert enemy_ent.props["attack_damage"] == 22.0
    assert "elite" in enemy_ent.tags

    # 3. All kit entities receive valid default properties
    player_ent = next(e for e in spec.entities if e.kind == EntityKind.PLAYER)
    assert player_ent.props["move_speed"] == 600.0
    assert player_ent.props["jump_velocity"] == 600.0

    # 4. Input action bindings: 3D crawler camera includes IA_Jump, IA_Move, IA_Look, IA_Attack
    action_ids = [a.action_id for a in spec.input.actions]
    assert "IA_Move" in action_ids
    assert "IA_Look" in action_ids
    assert "IA_Jump" in action_ids
    assert "IA_Attack" in action_ids
