"""Unit tests for review reconciliation and scene audit (WI-8.3)."""
from __future__ import annotations

import pytest

from src.gameforge_ide.forge.project_graph import ProjectGraph, ProjectNode, compute_actor_state_hash
from src.gameforge_ide.review.reconciliation import (
    TAG_GF_OWNED,
    ActorConflict,
    ReconciliationPlan,
    audit_reconciliation_review,
    plan_reconciliation,
)


def test_review_reconciliation_detects_conflicts_and_rates_risk():
    graph = ProjectGraph()
    node = ProjectNode(
        id="test_level/Enemy_1",
        kind="actor",
        level="test_level",
        label="Enemy_1",
        owner="gameforge",
        state_hash="initial_hash_123",
    )
    graph.upsert_node(node)

    # Actor in engine was modified by user outside GameForge
    current_actors = [
        {
            "label": "Enemy_1",
            "tags": [TAG_GF_OWNED],
            "transform": {"x": 500, "y": 200, "z": 0},
        }
    ]
    # New plan wants a different position
    new_plan = [
        {
            "label": "Enemy_1",
            "tags": [TAG_GF_OWNED],
            "transform": {"x": 100, "y": 100, "z": 0},
        }
    ]

    plan = plan_reconciliation(graph, "test_level", new_plan, current_actors)
    assert plan.has_conflicts is True
    assert len(plan.conflicts) == 1

    review_audit = audit_reconciliation_review(plan)
    assert review_audit["has_conflicts"] is True
    assert review_audit["total_conflicts"] == 1
    assert review_audit["risk_level"] == "HIGH"
    assert review_audit["actor_conflicts"][0]["label"] == "Enemy_1"


def test_review_reconciliation_clean_plan_low_risk():
    graph = ProjectGraph()
    current_actors = []
    new_plan = [
        {
            "label": "GF_Pickup_1",
            "tags": [TAG_GF_OWNED],
            "transform": {"x": 0, "y": 0, "z": 50},
        }
    ]

    plan = plan_reconciliation(graph, "test_level", new_plan, current_actors)
    assert plan.has_conflicts is False
    assert len(plan.to_spawn) == 1

    review_audit = audit_reconciliation_review(plan)
    assert review_audit["has_conflicts"] is False
    assert review_audit["risk_level"] == "LOW"
    assert review_audit["spawns_count"] == 1
