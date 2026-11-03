"""GameForge Composer package (Phase 6, WI-6.1 - WI-6.10).

Transforms Game Design Specs into verified, playable packaged Unreal games
via data-driven runtime composition and automated Forge execution.
"""
from __future__ import annotations

from .model import (
    CodegenTask,
    Composition,
    CompositionError,
    LevelPlan,
    OpCall,
    PlacedActor,
)
from .compose import compose
from .level_ops import plan_to_op_calls, verify_placed_actor_transforms
from .plan import composition_to_run_spec
from .runtime_def import build as build_gfdef

__all__ = [
    "CodegenTask",
    "Composition",
    "CompositionError",
    "LevelPlan",
    "OpCall",
    "PlacedActor",
    "compose",
    "plan_to_op_calls",
    "verify_placed_actor_transforms",
    "composition_to_run_spec",
    "build_gfdef",
]
