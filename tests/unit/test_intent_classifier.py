"""Model-assisted intent routing with heuristic fallback."""
from __future__ import annotations

import json

from src.gameforge_ide.backend.agent import intent_classifier as ic


class _Prov:
    def __init__(self, payload, available=True):
        self.payload = payload
        self.available = available
        self.calls = 0

    def is_available(self):
        return self.available

    def complete_json(self, model_id, system, user, schema, temperature=0.0, timeout_s=10.0):
        self.calls += 1
        assert schema["properties"]["intent"]["enum"] == list(ic.INTENTS)
        return self.payload if isinstance(self.payload, str) or self.payload is None else json.dumps(self.payload)


def setup_function(_):
    ic._cache.clear()


def test_confident_model_answer_is_used_and_cached():
    p = _Prov({"intent": "chat", "confidence": 0.9})
    r = ic.classify_intent("how do shooters handle recoil in games?", p, "m")
    assert r and r.intent == "chat"
    ic.classify_intent("how do shooters handle recoil in games?", p, "m")
    assert p.calls == 1


def test_low_confidence_or_bad_output_falls_back():
    assert ic.classify_intent("x", _Prov({"intent": "chat", "confidence": 0.3}), "m") is None
    assert ic.classify_intent("y", _Prov({"intent": "dance", "confidence": 0.9}), "m") is None
    assert ic.classify_intent("z", _Prov("not json"), "m") is None
    assert ic.classify_intent("w", _Prov(None), "m") is None


def test_unavailable_provider_or_disabled_env(monkeypatch):
    assert ic.classify_intent("hi", _Prov({"intent": "chat", "confidence": 1}, available=False), "m") is None
    monkeypatch.setenv("GAMEFORGE_DISABLE_LLM_ROUTING", "1")
    assert ic.classify_intent("hi there", _Prov({"intent": "chat", "confidence": 1}), "m") is None


def test_runtime_uses_model_intent_for_game_creation(tmp_path):
    from src.gameforge_ide.backend.agent.runtime import AgentRuntime
    from src.gameforge_ide.backend.providers.router import ModelRouter
    from src.gameforge_ide.backend.session_manager import SessionManager

    db = tmp_path / ".gameforge" / "s.db"
    db.parent.mkdir(parents=True)
    rt = AgentRuntime(tmp_path, SessionManager(db), ModelRouter())
    prompt = "what makes a good game loop?"
    rt._llm_intent_by_prompt[prompt] = ic.IntentResult("chat", 0.9, "model", 0.1)
    assert rt._is_game_creation_request(prompt) is False
    rt._llm_intent_by_prompt[prompt] = ic.IntentResult("create_game", 0.9, "model", 0.1)
    assert rt._is_game_creation_request(prompt) is True
