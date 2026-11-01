"""Unit tests for ProjectGraph and level reconciliation (WI-8.3)."""
from __future__ import annotations

import pytest
from pathlib import Path

from src.gameforge_ide.forge.project_graph import (
    GeneratedBy,
    ProjectGraph,
    ProjectNode,
    compute_actor_state_hash,
)
from src.gameforge_ide.forge.reconciliation import (
    TAG_GF_OWNED,
    apply_resolutions,
    plan_reconciliation,
)


def test_project_graph_save_load(tmp_path: Path):
    graph = ProjectGraph()
    node = ProjectNode(
        id="level_1/guards_2",
        kind="actor",
        level="level_1",
        label="guards_2",
        owner="gameforge",
        generated_by=GeneratedBy(run_id="run_1", step="assemble_level_1", plan_hash="h123"),
        state_hash="sh_abc",
    )
    graph.upsert_node(node)
    graph.save(tmp_path)

    loaded = ProjectGraph.load(tmp_path)
    assert len(loaded.nodes) == 1
    found = loaded.find_node("level_1/guards_2")
    assert found is not None
    assert found.label == "guards_2"
    assert found.state_hash == "sh_abc"


def test_reconciliation_preserves_user_added_actors():
    graph = ProjectGraph()
    # User created a custom light actor without GF_Owned tag
    current_actors = [
        {"label": "MyCustomLight", "tags": [], "location": {"x": 0, "y": 0, "z": 500}},
        {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 100, "y": 100, "z": 0}},
    ]
    # Record initial guard state
    guard_hash = compute_actor_state_hash(current_actors[1])
    graph.upsert_node(
        ProjectNode(id="level_1/guard_1", kind="actor", level="level_1", label="guard_1", state_hash=guard_hash)
    )

    # New plan does not mention MyCustomLight, only guard_1
    planned_actors = [
        {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 100, "y": 100, "z": 0}}
    ]

    plan = plan_reconciliation(graph, "level_1", planned_actors, current_actors)

    assert "MyCustomLight" in plan.preserved_user_actors
    assert "MyCustomLight" not in plan.to_delete
    assert plan.to_delete == []
    assert plan.to_spawn == []
    assert plan.conflicts == []


def test_reconciliation_deletes_owned_actors_removed_from_plan():
    graph = ProjectGraph()
    current_actors = [
        {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 100, "y": 100, "z": 0}},
        {"label": "guard_2", "tags": [TAG_GF_OWNED], "location": {"x": 200, "y": 200, "z": 0}},
    ]
    graph.upsert_node(
        ProjectNode(id="level_1/guard_1", kind="actor", level="level_1", label="guard_1", state_hash=compute_actor_state_hash(current_actors[0]))
    )
    graph.upsert_node(
        ProjectNode(id="level_1/guard_2", kind="actor", level="level_1", label="guard_2", state_hash=compute_actor_state_hash(current_actors[1]))
    )

    # New plan removed guard_2
    planned_actors = [
        {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 100, "y": 100, "z": 0}}
    ]

    plan = plan_reconciliation(graph, "level_1", planned_actors, current_actors)
    assert plan.to_delete == ["guard_2"]
    assert plan.conflicts == []


def test_user_modified_actor_raises_conflict_and_resolves_keep_mine():
    graph = ProjectGraph()
    original_guard = {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 100, "y": 100, "z": 0}, "properties": {"move_speed": 400.0}}
    original_hash = compute_actor_state_hash(original_guard)

    graph.upsert_node(
        ProjectNode(id="level_1/guard_1", kind="actor", level="level_1", label="guard_1", owner="gameforge", state_hash=original_hash)
    )

    # User moved the guard in the editor outside Forge to (500, 500, 0)
    current_actors = [
        {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 500, "y": 500, "z": 0}, "properties": {"move_speed": 400.0}}
    ]

    # Change request wants to make guards faster (speed = 500.0) at original location
    planned_actors = [
        {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 100, "y": 100, "z": 0}, "properties": {"move_speed": 500.0}}
    ]

    # Without resolution: conflict is raised!
    plan = plan_reconciliation(graph, "level_1", planned_actors, current_actors)
    assert plan.has_conflicts is True
    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].actor_id == "level_1/guard_1"

    # User resolves with "keep_mine"
    resolved_plan = apply_resolutions(graph, plan, {"level_1/guard_1": "keep_mine"})
    assert resolved_plan.has_conflicts is False
    assert "guard_1" in resolved_plan.preserved_user_actors
    assert resolved_plan.to_update == []  # Not updated!

    node = graph.find_node("level_1/guard_1")
    assert node.owner == "user"  # Now user-owned!


def test_user_modified_actor_resolves_use_design():
    graph = ProjectGraph()
    original_guard = {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 100, "y": 100, "z": 0}}
    graph.upsert_node(
        ProjectNode(id="level_1/guard_1", kind="actor", level="level_1", label="guard_1", owner="gameforge", state_hash=compute_actor_state_hash(original_guard))
    )

    current_actors = [
        {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 999, "y": 999, "z": 0}}
    ]
    planned_actors = [
        {"label": "guard_1", "tags": [TAG_GF_OWNED], "location": {"x": 100, "y": 100, "z": 0}, "properties": {"move_speed": 500.0}}
    ]

    plan = plan_reconciliation(graph, "level_1", planned_actors, current_actors, resolutions={"level_1/guard_1": "use_design"})
    assert plan.has_conflicts is False
    assert len(plan.to_update) == 1
    assert plan.to_update[0]["properties"]["move_speed"] == 500.0
    node = graph.find_node("level_1/guard_1")
    assert node.owner == "gameforge"
