"""Tests verifying the AI, Agent Runtime, Prompt-to-GDS and Patching improvements."""
from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from src.gameforge_ide.pipeline.spec_from_prompt import is_game_creation_request
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.design.draft import DesignDraft, DraftEntity, DraftWin
from src.gameforge_ide.design.expand import expand_draft
from src.gameforge_ide.design.gds import CameraKind, EntityKind, GameDesignSpec, Genre, Lighting, Placement, Vec3
from src.gameforge_ide.design.patch import (
    apply_patch,
    propose_patch,
    _compact_entities_list,
)
from src.gameforge_ide.design.patch_rules import match_deterministic_rule
from src.gameforge_ide.design.presets import preset_platformer, preset_relic_hunt
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
from src.gameforge_ide.backend.agent.code_verify import propose_assistant_fix


# ── 1. Intent Classification Accuracy ──────────────────────────────────────────

def test_expanded_intent_classification():
    """Verify that expanded game genres and creation requests are properly recognized."""
    # Runner, racing, simulator, strategy, tower defense, dogfight
    assert is_game_creation_request("Create an endless runner with coin collection")
    assert is_game_creation_request("Design a tower defense with archers and orcs")
    assert is_game_creation_request("Build a space flight simulator")
    assert is_game_creation_request("Develop a fast-paced medieval strategy game")
    assert is_game_creation_request("Make a dungeon escape with traps and locked doors")
    assert is_game_creation_request("Author a sci-fi dogfight game")

    # Non-creation queries must remain false
    assert not is_game_creation_request("how does the character jump in Unreal?")
    assert not is_game_creation_request("fix the compile error in Player.cpp")
    assert not is_game_creation_request("what is the best way to handle inventory?")


# ── 2. Prevention of Template Hijacking on Creative Prompts ────────────────────

def test_creative_narrative_prompts_bypass_preset_hijacking():
    """Verify that thematic creative prompts do not fall back to static presets when a model is provided."""
    mock_complete = MagicMock(return_value=json.dumps({
        "title": "Spooky Attic",
        "genre": "custom",
        "camera": "first_person",
        "pitch": "Navigate a spooky haunted attic and find glowing relics",
        "entities": [
            {"kind": "hazard", "count": 2, "note": "cursed mirrors"},
            {"kind": "pickup", "count": 3, "note": "glowing relics"},
        ],
        "win": [{"type": "collect_all", "target": 3}],
        "lose": [{"type": "health_zero"}],
    }))

    res = prompt_to_gds(
        "A spooky platformer where you avoid cursed mirrors in a haunted attic",
        complete_json=mock_complete,
        allow_model=True,
    )

    assert res.status == "OK"
    assert res.path == "model"
    assert res.gds is not None
    assert res.gds.meta.title == "Spooky Attic"
    assert mock_complete.call_count == 1


# ── 3. Creative Input Actions Injection in expand_draft ────────────────────────

def test_expand_draft_injects_combat_actions():
    """Verify that draft expansion provides attack / fire actions when enemies or shooting are present."""
    draft = DesignDraft(
        title="Dungeon Shooter",
        genre=Genre.CUSTOM,
        camera=CameraKind.FIRST_PERSON,
        pitch="First-person combat against dungeon monsters",
        entities=[DraftEntity(kind=EntityKind.ENEMY, count=4)],
        win=[DraftWin(type="defeat_all")],
    )

    spec = expand_draft(draft)
    action_ids = [a.action_id for a in spec.input.actions]
    assert "IA_Move" in action_ids
    assert "IA_Look" in action_ids
    assert "IA_Fire" in action_ids


# ── 4. Robust Tool Call Extraction with Multiple Formats ──────────────────────

def test_extract_tool_call_supports_all_standard_schemas():
    """Verify runtime extracts tool calls in OpenAI and provider-neutral formats."""
    runtime = AgentRuntime(workspace_root=MagicMock(), session_manager=MagicMock(), model_router=MagicMock())

    # Format A: standard GameForge {"tool": "name", "args": {...}}
    raw_a = '```json\n{"tool": "list_dir", "args": {"subpath": "Source"}}\n```'
    call_a = runtime._extract_tool_call(raw_a)
    assert call_a is not None
    assert call_a["name"] == "list_dir"
    assert call_a["arguments"] == {"subpath": "Source"}

    # Format B: OpenAI function call {"name": "name", "arguments": {...}}
    raw_b = '{"name": "unreal_engine_info", "arguments": {"check_plugins": true}}'
    call_b = runtime._extract_tool_call(raw_b)
    assert call_b is not None
    assert call_b["name"] == "unreal_engine_info"
    assert call_b["arguments"] == {"check_plugins": True}

    # Format C: Anthropic / custom {"tool_name": "name", "parameters": {...}}
    raw_c = 'I will inspect the workspace.\n```\n{"tool_name": "search_index", "parameters": {"query": "Player"}}\n```'
    call_c = runtime._extract_tool_call(raw_c)
    assert call_c is not None
    assert call_c["name"] == "search_index"
    assert call_c["arguments"] == {"query": "Player"}


# ── 5. New and Enhanced Game Mutation Patch Rules ─────────────────────────────

def test_patch_rule_add_entities_when_none_existed():
    """Verify adding N entities creates new entity when not currently present."""
    gds = preset_platformer(title="Test Platformer")
    assert not any(e.kind == EntityKind.HAZARD for e in gds.entities)

    prop = propose_patch(gds, "add 3 hazards")
    assert prop.status == "OK"
    assert len(prop.ops) == 1
    assert prop.ops[0]["op"] == "add"
    assert prop.ops[0]["value"]["count"] == 3
    assert prop.ops[0]["value"]["kind"] == "hazard"

    patched = apply_patch(gds, prop.ops)
    hazard = next(e for e in patched.entities if e.kind == EntityKind.HAZARD)
    assert hazard.count == 3


def test_patch_rule_health_adjustments():
    """Verify setting and doubling player / enemy health."""
    gds = preset_platformer(title="Health Test")
    prop = propose_patch(gds, "set player health to 250")
    assert prop.status == "OK"
    patched = apply_patch(gds, prop.ops)
    player = next(e for e in patched.entities if e.kind == EntityKind.PLAYER)
    assert player.props.get("player_max_health") == 250.0

    prop_double = propose_patch(patched, "double player health")
    assert prop_double.status == "OK"
    patched_2 = apply_patch(patched, prop_double.ops)
    player_2 = next(e for e in patched_2.entities if e.kind == EntityKind.PLAYER)
    assert player_2.props.get("player_max_health") == 500.0


def test_patch_rule_jump_velocity():
    """Verify modifying jump velocity / force."""
    gds = preset_platformer(title="Jump Test")
    prop = propose_patch(gds, "increase jump height to 850")
    assert prop.status == "OK"
    patched = apply_patch(gds, prop.ops)
    player = next(e for e in patched.entities if e.kind == EntityKind.PLAYER)
    assert player.props.get("jump_velocity") == 850.0


def test_patch_rule_progression_difficulty():
    """Verify changing progression difficulty."""
    gds = preset_platformer(title="Diff Test")
    prop = propose_patch(gds, "set difficulty to hard")
    assert prop.status == "OK"
    patched = apply_patch(gds, prop.ops)
    assert patched.progression.difficulty == "hard"


def test_patch_rule_art_style():
    """Verify changing art style."""
    gds = preset_platformer(title="Art Test")
    prop = propose_patch(gds, "change art style to toon")
    assert prop.status == "OK"
    patched = apply_patch(gds, prop.ops)
    assert patched.art.style == "toon"


def test_patch_rule_camera():
    """Verify changing camera mode."""
    gds = preset_platformer(title="Cam Test")
    prop = propose_patch(gds, "change camera to first person")
    assert prop.status == "OK"
    patched = apply_patch(gds, prop.ops)
    assert patched.overview.camera == CameraKind.FIRST_PERSON


def test_patch_rule_timer():
    """Verify setting lose timer."""
    gds = preset_platformer(title="Timer Test")
    prop = propose_patch(gds, "set timer to 120 seconds")
    assert prop.status == "OK"
    patched = apply_patch(gds, prop.ops)
    timer_cond = next(c for c in patched.goals.lose if getattr(c, "kind", "") == "timer")
    assert timer_cond.seconds == 120.0


def test_patch_rule_removal_verbs():
    """Verify deletion/destroy verbs work for removing entities."""
    gds = preset_relic_hunt(title="Removal Test")
    assert any(e.entity_id == "guard" for e in gds.entities)

    prop = propose_patch(gds, "delete the guard")
    assert prop.status == "OK"
    patched = apply_patch(gds, prop.ops)
    assert not any(e.entity_id == "guard" for e in patched.entities)


def test_patch_rule_enhanced_lighting():
    """Verify dark/sunset lighting synonyms."""
    gds = preset_platformer(title="Light Test")
    prop = propose_patch(gds, "make it dark")
    assert prop.status == "OK"
    patched = apply_patch(gds, prop.ops)
    assert patched.scene.levels[0].lighting == Lighting.NIGHT

    prop_sunset = propose_patch(patched, "set lighting to sunset")
    assert prop_sunset.status == "OK"
    patched_sunset = apply_patch(patched, prop_sunset.ops)
    assert patched_sunset.scene.levels[0].lighting == Lighting.DUSK


# ── 6. Token Context Waste Prevention ──────────────────────────────────────────

def test_compact_entities_list_prunes_large_coordinates():
    """Verify large points_m coordinate arrays are trimmed before model delegation."""
    entities = [
        {
            "entity_id": "coins",
            "kind": "pickup",
            "placement": {
                "strategy": "fixed",
                "points_m": [{"x": float(i), "y": 0.0, "z": 0.0} for i in range(100)],
            },
        }
    ]
    compact = _compact_entities_list(entities)
    assert len(compact[0]["placement"]["points_m"]) == 2


# ── 7. Code Verify Markdown Diff Stripping ────────────────────────────────────

def test_code_verify_strips_markdown_diff_fences(tmp_path):
    """Verify propose_assistant_fix strips code block fences from model diff output."""
    project_dir = tmp_path / "MyProject"
    project_dir.mkdir()
    source_file = project_dir / "Source" / "MyGame" / "MyActor.cpp"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("int x = 10;\n", encoding="utf-8")

    mock_caller = MagicMock(return_value="```diff\n--- a/Source/MyGame/MyActor.cpp\n+++ b/Source/MyGame/MyActor.cpp\n@@ -1,1 +1,1 @@\n-int x = 10;\n+int x = 20;\n```")

    diags = [{"message": "syntax error", "file": "Source/MyGame/MyActor.cpp", "line": 1}]
    fix = propose_assistant_fix(project_dir, diags, model_caller=mock_caller)

    assert fix["status"] == "PROPOSED"
    assert not fix["diff"].startswith("```")
    assert not fix["diff"].endswith("```")
    assert "--- a/Source/MyGame/MyActor.cpp" in fix["diff"]
