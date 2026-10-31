"""Composer runtime definition adapter (WI-6.5).

Wraps kit.runtime_def to emit gfdef/1 dictionary from GDS and Composition.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from ..kit.runtime_def import build_runtime_def as kit_build_runtime_def, validate_runtime_def


def build(gds: Any, comp: Optional[Any] = None) -> Dict[str, Any]:
    """Generate gfdef/1 dictionary from GameDesignSpec and Composition."""
    seed = 2026
    if hasattr(gds, "scene") and hasattr(gds.scene, "levels") and gds.scene.levels:
        seed = int(getattr(gds.scene.levels[0], "seed", 2026))

    gfdef = kit_build_runtime_def(gds, seed=seed)

    # Attach codegen custom rules if present
    if comp and hasattr(comp, "codegen") and comp.codegen:
        custom_rules = []
        for task in comp.codegen:
            custom_rules.append(
                {
                    "rule_id": task.rule_id,
                    "handler_name": task.handler_name,
                    "description": task.description,
                    "class": f"/Script/{comp.project_name}.{task.handler_name}",
                }
            )
        gfdef["custom_rules"] = custom_rules

    return gfdef
