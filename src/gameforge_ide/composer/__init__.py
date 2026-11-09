"""GameForge Composer package (Phase 6, WI-6.1 - WI-6.10).

Transforms Game Design Specs into verified, playable packaged Unreal games
via data-driven runtime composition and automated Forge execution.
"""
from __future__ import annotations

from .cinematics import generate_intro_cinematic
from .codegen import plan_architecture_codegen, synthesize_cpp_bodies_for_architecture
from .compose import compose
from .content import plan_content_ops, resolve_sfx_path, resolve_vfx_path
from .level_ops import plan_to_op_calls, verify_placed_actor_transforms
from .model import (
    CodegenTask,
    Composition,
    CompositionError,
    LevelPlan,
    OpCall,
    PlacedActor,
)
from .plan import composition_to_run_spec
from .runtime_def import build as build_gfdef
from .theme import THEMES, resolve_theme

__all__ = [
    "CodegenTask",
    "Composition",
    "CompositionError",
    "LevelPlan",
    "OpCall",
    "PlacedActor",
    "THEMES",
    "build_gfdef",
    "compose",
    "composition_to_run_spec",
    "generate_intro_cinematic",
    "plan_architecture_codegen",
    "plan_content_ops",
    "plan_to_op_calls",
    "resolve_sfx_path",
    "resolve_theme",
    "resolve_vfx_path",
    "synthesize_cpp_bodies_for_architecture",
    "verify_placed_actor_transforms",
]
