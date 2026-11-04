"""GameForge Game Design Spec (GDS) package."""
from .semantic_validate import semantic_validate_gds
from .intent import IntentType, IntentResult, classify_prompt_intent, is_game_creation_request
from .prompt_to_gds import prompt_to_gds, PromptToGdsResult
from .schema import GameDesignSpec, DesignDraft, validate_gds, validate_draft
from .expand import expand_draft
from .patch import apply_patch, propose_patch, PatchError

