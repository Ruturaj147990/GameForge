"""Unit tests for GDS JSON Patch engine and deterministic rules (WI-8.1)."""
from __future__ import annotations

import pytest

from src.gameforge_ide.design.gds import GameDesignSpec, Lighting
from src.gameforge_ide.design.patch import (
    PatchError,
    apply_patch,
    propose_patch,
    summarize_patch,
)
from src.gameforge_ide.design.presets import preset_relic_hunt


@pytest.fixture
def base_gds() -> GameDesignSpec:
    return preset_relic_hunt(title="Base Relic Hunt")


def test_protected_paths_cannot_be_patched(base_gds: GameDesignSpec):
    # /meta/gds_id is protected
    with pytest.raises(PatchError) as exc_info:
        apply_patch(base_gds, [{"op": "replace", "path": "/meta/gds_id", "value": "hacked_id"}])
    assert "protected" in str(exc_info.value)

    # /meta/created_at is protected
    with pytest.raises(PatchError):
        apply_patch(base_gds, [{"op": "replace", "path": "/meta/created_at", "value": "2099-01-01"}])

    # /meta/schema_version is protected
    with pytest.raises(PatchError):
        apply_patch(base_gds, [{"op": "replace", "path": "/meta/schema_version", "value": "gds/99"}])


def test_apply_patch_bumps_revision_and_sets_generator(base_gds: GameDesignSpec):
    orig_rev = base_gds.meta.revision
    ops = [{"op": "replace", "path": "/meta/title", "value": "Updated Title"}]
    patched = apply_patch(base_gds, ops)

    assert patched.meta.revision == orig_rev + 1
    assert patched.meta.generator == "patch"
    assert patched.meta.title == "Updated Title"


def test_shortcut_faster_guards(base_gds: GameDesignSpec):
    # Guard move speed is 400.0 initially
    guard_ent = next(e for e in base_gds.entities if e.entity_id == "guard")
    assert guard_ent.props["move_speed"] == 400.0

    prop = propose_patch(base_gds, "make the guards faster")
    assert prop.status == "OK"
    assert len(prop.ops) == 1
    assert prop.ops[0]["value"] == 500.0  # 400 * 1.25

    patched = apply_patch(base_gds, prop.ops)
    p_guard = next(e for e in patched.entities if e.entity_id == "guard")
    assert p_guard.props["move_speed"] == 500.0


def test_shortcut_slower_guards(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "make guards slower")
    assert prop.status == "OK"
    assert prop.ops[0]["value"] == 320.0  # 400 * 0.8

    patched = apply_patch(base_gds, prop.ops)
    p_guard = next(e for e in patched.entities if e.entity_id == "guard")
    assert p_guard.props["move_speed"] == 320.0


def test_shortcut_more_relics(base_gds: GameDesignSpec):
    # 5 relics initially
    relic_ent = next(e for e in base_gds.entities if e.entity_id == "relics")
    assert relic_ent.count == 5

    prop = propose_patch(base_gds, "more relics")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    p_relics = next(e for e in patched.entities if e.entity_id == "relics")
    assert p_relics.count == 7  # 5 + round(2.5) [round-half-to-even] = 7


def test_shortcut_night_lighting(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "make it night")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    assert patched.scene.levels[0].lighting == Lighting.NIGHT


def test_shortcut_add_checkpoint(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "add a checkpoint")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    cp = next((e for e in patched.entities if e.kind.value == "checkpoint"), None)
    assert cp is not None
    assert cp.entity_id == "checkpoint_1"


def test_shortcut_add_hazard(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "add a hazard area")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    h = next((e for e in patched.entities if e.kind.value == "hazard"), None)
    assert h is not None
    assert h.props["damage_per_second"] == 25.0


def test_shortcut_add_second_level(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "add a second level")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    assert len(patched.scene.levels) == 2
    assert patched.scene.levels[1].level_id == "level_2"


def test_shortcut_reach_gate_win(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "change the win to also require reaching the gate")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    assert any(getattr(c, "event", None) == "goal.reached" for c in patched.goals.win)


def test_shortcut_rename_title(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "rename the title to Forest Shadows")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    assert patched.meta.title == "Forest Shadows"


def test_shortcut_remove_guards(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "remove guards")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    guard = next((e for e in patched.entities if e.entity_id == "guard"), None)
    assert guard is None


def test_shortcut_add_door_with_key(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "add a door with a key")
    assert prop.status == "OK"

    patched = apply_patch(base_gds, prop.ops)
    door = next((e for e in patched.entities if e.entity_id == "door_gate"), None)
    key = next((e for e in patched.entities if e.entity_id == "key_bronze"), None)
    assert door is not None
    assert key is not None
    assert door.props["required_stat"] == "entity.key_bronze.collected"


def test_summarize_patch_sentences(base_gds: GameDesignSpec):
    prop = propose_patch(base_gds, "make the guards faster")
    sentences = summarize_patch(base_gds, prop.ops)
    assert len(sentences) == 1
    assert "Guard: move_speed 400.0 -> 500.0" in sentences[0]
