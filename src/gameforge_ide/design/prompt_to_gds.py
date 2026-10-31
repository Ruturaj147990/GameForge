"""Orchestrates natural-language prompt -> GameDesignSpec via presets or model draft (P1 WI-1.6)."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import Callable, List, Literal, Optional

from pydantic import ValidationError

from src.gameforge_ide.pipeline.spec_from_prompt import is_game_creation_request
from .draft import DesignDraft
from .expand import ExpandError, expand_draft
from .gds import GameDesignSpec
from .presets import PRESETS, PRESET_KEYWORDS, extract_preset_overrides

logger = logging.getLogger(__name__)

CompleteJson = Callable[[str, str, dict], Optional[str]]

DRAFT_SYSTEM_PROMPT = """You turn a game idea into a JSON object that matches the given schema exactly.
Rules:
- Choose the closest genre and camera. Prefer simple, playable designs a small team could build in a day.
- entities: list what the player meets (pickups, enemies, guards, npcs, doors, hazards, checkpoints, goal). Counts must be small (1-20).
- win: 1-3 conditions the game can check (collect_all, reach_goal, defeat_all, survive_seconds, score_at_least, board_win, match_win).
- lose: conditions such as health_zero or timer_runs_out. Use [] if the player cannot lose.
- custom_rules: at most 3 short sentences for mechanics the lists above cannot express. Leave empty when possible.
- questions: only if the idea is ambiguous in a way that changes the game (max 3).
- title: short, no quotes. Output JSON only."""

PRESET_TITLES = [
    "Tic-Tac-Toe",
    "Connect Four",
    "Gomoku",
    "3D Platformer",
    "Arena Combat",
    "Card Battler",
    "Procedural World",
]


@dataclass
class PromptToGdsResult:
    status: Literal["OK", "NEEDS_INPUT", "UNSUPPORTED", "ERROR"]
    gds: Optional[GameDesignSpec] = None
    questions: List[str] = field(default_factory=list)
    suggested_patches: List[Dict[str, Any]] = field(default_factory=list)
    path: Literal["preset", "model", "none"] = "none"
    model: Optional[str] = None
    attempts: int = 0
    errors: List[str] = field(default_factory=list)


def prompt_to_gds(
    prompt: str,
    complete_json: Optional[CompleteJson] = None,
    model: Optional[str] = None,
    allow_model: bool = True,
) -> PromptToGdsResult:
    """Orchestrates turning a prompt into a GameDesignSpec.

    1. Checks if prompt is a game creation request (otherwise UNSUPPORTED).
    2. Tries deterministic preset matching.
    3. If allow_model and complete_json provided, requests a DesignDraft from the model and expands it,
       running one repair attempt on validation/JSON errors.
    4. If no model available or transport fails, returns NEEDS_INPUT asking user to pick a genre.
    """
    if not is_game_creation_request(prompt):
        return PromptToGdsResult(
            status="UNSUPPORTED",
            errors=["Prompt is not a game creation request"],
            path="none",
        )

    # 2. Preset path: keyword match
    text = " " + prompt.lower().replace("’", "'") + " "
    best_preset: Optional[str] = None
    best_kw: str = ""
    for preset_id, kws in PRESET_KEYWORDS.items():
        for kw in kws:
            if kw in text and len(kw) > len(best_kw):
                best_preset = preset_id
                best_kw = kw

    if best_preset is not None and best_preset in PRESETS:
        overrides = extract_preset_overrides(best_preset, prompt)
        title = overrides.pop("title", None)
        try:
            gds = PRESETS[best_preset](title=title, **overrides)
            return PromptToGdsResult(
                status="OK",
                gds=gds,
                path="preset",
            )
        except Exception as exc:
            logger.warning("Preset creation failed for %s: %s", best_preset, exc)

    # 3. Model path
    if allow_model and complete_json is not None:
        schema = DesignDraft.model_json_schema()
        attempts = 0
        errors: List[str] = []

        # Attempt 1
        attempts += 1
        raw_json = complete_json(DRAFT_SYSTEM_PROMPT, prompt, schema)
        draft: Optional[DesignDraft] = None

        if raw_json is not None:
            try:
                data = json.loads(raw_json)
                if isinstance(data, dict):
                    draft = DesignDraft.model_validate(data)
                else:
                    raise ValueError(f"Output is not a JSON object (got {type(data).__name__})")
            except Exception as exc:
                err_str = str(exc)
                errors.append(f"Attempt 1 validation error: {err_str}")

                # Repair attempt (exactly one repair call)
                attempts += 1
                repair_prompt = (
                    f"{prompt}\n\n"
                    f"Previous output:\n{raw_json}\n\n"
                    f"Validation errors:\n{err_str[:1500]}\n\n"
                    f"Please fix the errors above and return the corrected JSON object matching the schema only."
                )
                repair_raw = complete_json(DRAFT_SYSTEM_PROMPT, repair_prompt, schema)
                if repair_raw is not None:
                    try:
                        data2 = json.loads(repair_raw)
                        if isinstance(data2, dict):
                            draft = DesignDraft.model_validate(data2)
                        else:
                            raise ValueError(f"Repaired output is not a JSON object (got {type(data2).__name__})")
                    except Exception as exc2:
                        errors.append(f"Attempt 2 validation error: {exc2}")
                else:
                    errors.append("Repair call failed (transport error or no response)")
        else:
            errors.append("Initial model call failed (transport error or no response)")

        if draft is not None:
            try:
                gds = expand_draft(draft)
            except Exception as exc:
                errors.append(f"Draft expansion failed: {exc}")
                return PromptToGdsResult(
                    status="NEEDS_INPUT",
                    questions=[f"Could not construct a valid game specification: {exc}. Please clarify the game rules."],
                    path="model",
                    model=model,
                    attempts=attempts,
                    errors=errors,
                )

            if draft.questions:
                return PromptToGdsResult(
                    status="NEEDS_INPUT",
                    gds=gds,
                    questions=list(draft.questions),
                    path="model",
                    model=model,
                    attempts=attempts,
                    errors=errors,
                )

            return PromptToGdsResult(
                status="OK",
                gds=gds,
                path="model",
                model=model,
                attempts=attempts,
                errors=errors,
            )

        # Still invalid after repair or transport failed
        if attempts > 1 or errors:
            return PromptToGdsResult(
                status="NEEDS_INPUT",
                questions=[
                    "Could not generate a valid game design from this prompt. "
                    "Could you clarify the genre, primary goal, and win condition?"
                ],
                path="model",
                model=model,
                attempts=attempts,
                errors=errors,
            )

    # 4. No model available
    preset_list = ", ".join(PRESET_TITLES)
    return PromptToGdsResult(
        status="NEEDS_INPUT",
        questions=[f"Which kind of game is this closest to: {preset_list}?"],
        path="none",
        model=model,
    )
