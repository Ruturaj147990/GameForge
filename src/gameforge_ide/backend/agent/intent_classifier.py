"""Model-assisted intent routing for the universal assistant.

Routing used to rely only on keyword heuristics (``AgentRuntime._is_conversational`` and
``spec_from_prompt.is_game_creation_request``). Those were patched many times (DEF-088/089/090,
DEF-204/205, ...) because single words such as "game", "build" or "status" pulled questions into
the wrong path. This module asks the already-loaded chat model for a structured classification
(JSON schema output, ``think: false``) and returns ``None`` whenever the model is unavailable,
slow, or not confident, so the caller falls back to the existing heuristics. The keyword rules
therefore remain the safety net; the model only overrides them when it is confident.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

INTENTS = ("chat", "code_change", "create_game", "modify_game", "project_query")

_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "confidence": {"type": "number"},
    },
    "required": ["intent", "confidence"],
}

_SYSTEM = (
    "You route requests inside GameForge, an IDE that builds Unreal Engine games from prompts.\n"
    "Classify the user's message into exactly one intent:\n"
    "- chat: greetings, thanks, opinions, or questions that can be answered from knowledge alone "
    "(e.g. 'how do shooters handle recoil?', 'what is a GameMode?').\n"
    "- code_change: write, edit, fix, refactor, or delete source code or files in the workspace.\n"
    "- create_game: make a NEW complete game from a description.\n"
    "- modify_game: change gameplay, levels, rules or content of the current/existing game.\n"
    "- project_query: questions that need looking at this workspace/project/build state/logs/files.\n"
    "Return JSON only. confidence is 0..1."
)

MIN_CONFIDENCE = 0.6


@dataclass(frozen=True)
class IntentResult:
    intent: str
    confidence: float
    source: str  # "model"
    seconds: float


_cache: Dict[str, IntentResult] = {}
_cache_lock = threading.Lock()


def _timeout_s() -> float:
    try:
        return max(1.0, float(os.environ.get("GAMEFORGE_INTENT_TIMEOUT_S", "15")))
    except ValueError:
        return 15.0


def classify_intent(prompt: str, provider: Any, model_id: str) -> Optional[IntentResult]:
    """Return a confident model classification, or None to fall back to heuristics."""
    text = (prompt or "").strip()
    if not text or provider is None or not model_id:
        return None
    if os.environ.get("GAMEFORGE_DISABLE_LLM_ROUTING") == "1":
        return None
    if not hasattr(provider, "complete_json"):
        return None
    key = f"{model_id}\x00{text}"
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    try:
        if hasattr(provider, "is_available") and not provider.is_available():
            return None
    except Exception:
        return None

    t0 = time.monotonic()
    try:
        raw = provider.complete_json(
            model_id=model_id,
            system=_SYSTEM,
            user=f"Message:\n{text[:4000]}",
            schema=_SCHEMA,
            temperature=0.0,
            timeout_s=_timeout_s(),
        )
    except TypeError:
        # Providers with a narrower complete_json signature.
        try:
            raw = provider.complete_json(model_id, _SYSTEM, f"Message:\n{text[:4000]}", _SCHEMA)
        except Exception as exc:
            logger.debug("Intent classification unavailable: %s", exc)
            return None
    except Exception as exc:
        logger.debug("Intent classification failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        intent = str(data.get("intent", "")).strip()
        conf = float(data.get("confidence", 0.0))
    except (ValueError, TypeError, AttributeError):
        return None
    if intent not in INTENTS or not (0.0 <= conf <= 1.0) or conf < MIN_CONFIDENCE:
        return None
    result = IntentResult(intent=intent, confidence=conf, source="model", seconds=round(time.monotonic() - t0, 2))
    with _cache_lock:
        if len(_cache) > 256:
            _cache.clear()
        _cache[key] = result
    return result
