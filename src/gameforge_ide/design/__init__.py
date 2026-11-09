"""GameForge Game Design Spec (GDS) package."""
from .draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from .expand import ExpandError, expand_draft, sanitize_props
from .gds import GameDesignSpec
from .intent import IntentResult, IntentType, classify_prompt_intent, is_game_creation_request
from .patch import PatchError, ProposedPatch, apply_patch, propose_patch, summarize_patch
from .prompt_analysis import NamedThing, PromptBrief, analyze_prompt, brief_for_model, brief_to_draft, reconcile_draft
from .prompt_to_gds import PromptToGdsResult, prompt_to_gds
from .render import render_markdown, sentence
from .schema import validate_draft, validate_gds
from .semantic_validate import semantic_validate_gds
from .template_registry import GenerationStrategy, SemanticTemplateRegistry, StrategyDecision, default_registry

__all__ = [
    "DesignDraft",
    "DraftEntity",
    "DraftLose",
    "DraftWin",
    "ExpandError",
    "GenerationStrategy",
    "GameDesignSpec",
    "IntentResult",
    "IntentType",
    "NamedThing",
    "PatchError",
    "PromptBrief",
    "PromptToGdsResult",
    "ProposedPatch",
    "SemanticTemplateRegistry",
    "StrategyDecision",
    "analyze_prompt",
    "apply_patch",
    "brief_for_model",
    "brief_to_draft",
    "classify_prompt_intent",
    "default_registry",
    "expand_draft",
    "is_game_creation_request",
    "prompt_to_gds",
    "propose_patch",
    "reconcile_draft",
    "render_markdown",
    "sanitize_props",
    "semantic_validate_gds",
    "sentence",
    "summarize_patch",
    "validate_draft",
    "validate_gds",
]
