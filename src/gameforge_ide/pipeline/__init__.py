"""GameForge game, character, animation, and freeform generation pipelines."""
from .animation_pipeline import AnimationPipeline, AnimationPipelineResult
from .authoring import ModelAuthor, parse_files, safety_scan
from .autofix import autofix, hints_for
from .character_pipeline import CharacterPipeline, CharacterPipelineResult
from .freeform import FreeformGamePipeline, derive_title, pascal
from .game_pipeline import GamePipeline, PipelineResult, StageRecord, render_markdown
from .project_import import (
    ProjectInspection,
    enable_gameforge_management,
    generate_reverse_draft,
    inspect_project,
)
from .spec_from_prompt import (
    RECIPES,
    SPEC_SCHEMA,
    GameSpec,
    RecipeEntry,
    expand_game_flags,
    is_game_creation_request,
    match_prompt,
    refine_with_model,
    spec_from_prompt,
)

__all__ = [
    "AnimationPipeline",
    "AnimationPipelineResult",
    "CharacterPipeline",
    "CharacterPipelineResult",
    "FreeformGamePipeline",
    "GamePipeline",
    "GameSpec",
    "ModelAuthor",
    "PipelineResult",
    "ProjectInspection",
    "RECIPES",
    "RecipeEntry",
    "SPEC_SCHEMA",
    "StageRecord",
    "autofix",
    "derive_title",
    "enable_gameforge_management",
    "expand_game_flags",
    "generate_reverse_draft",
    "hints_for",
    "inspect_project",
    "is_game_creation_request",
    "match_prompt",
    "parse_files",
    "pascal",
    "refine_with_model",
    "render_markdown",
    "safety_scan",
    "spec_from_prompt",
]
