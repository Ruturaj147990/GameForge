"""Review-level scene reconciliation, visual change audit, and user-edit protection (WI-8.3).

Provides review inspection and auditing of ReconciliationPlans generated between
designed state and disk / engine state. Ensures user modifications are identified
and safeguarded before automated design updates are applied.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from ..forge.project_graph import ProjectGraph
from ..forge.reconciliation import (
    TAG_GF_OWNED,
    ActorConflict,
    AssetConflict,
    ReconciliationPlan,
    apply_resolutions,
    plan_reconciliation,
)


def audit_reconciliation_review(plan: ReconciliationPlan) -> Dict[str, Any]:
    """Audit a reconciliation plan for review, highlighting conflicts and protected user edits.

    Returns:
        Structured review dictionary with conflict summary, risk level, and action counts.
    """
    actor_conflicts = [
        {
            "actor_id": c.actor_id,
            "label": c.label,
            "level": c.level,
            "recorded_hash": c.recorded_hash,
            "current_hash": c.current_hash,
        }
        for c in plan.conflicts
    ]

    asset_conflicts = [
        {
            "asset_id": c.asset_id,
            "path": c.path,
            "recorded_sha256": c.recorded_sha256,
            "current_sha256": c.current_sha256,
        }
        for c in plan.asset_conflicts
    ]

    total_conflicts = len(actor_conflicts) + len(asset_conflicts)
    risk_level = "HIGH" if total_conflicts > 0 else ("MEDIUM" if len(plan.to_delete) > 0 else "LOW")

    return {
        "level_id": plan.level_id,
        "has_conflicts": plan.has_conflicts,
        "total_conflicts": total_conflicts,
        "risk_level": risk_level,
        "spawns_count": len(plan.to_spawn),
        "updates_count": len(plan.to_update),
        "deletes_count": len(plan.to_delete),
        "preserved_user_actors_count": len(plan.preserved_user_actors),
        "actor_conflicts": actor_conflicts,
        "asset_conflicts": asset_conflicts,
        "to_delete_labels": list(plan.to_delete),
        "preserved_labels": list(plan.preserved_user_actors),
    }


__all__ = [
    "TAG_GF_OWNED",
    "ActorConflict",
    "AssetConflict",
    "ReconciliationPlan",
    "plan_reconciliation",
    "apply_resolutions",
    "audit_reconciliation_review",
]
