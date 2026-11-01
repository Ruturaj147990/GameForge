"""Model adapters for GameForge Agentic Eval Suite (WI-9.1, WI-9.2)."""
from __future__ import annotations

import abc
import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class ModelAdapter(abc.ABC):
    """Base interface for model evaluation adapters."""

    @property
    @abc.abstractmethod
    def model_id(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def provider_kind(self) -> str:
        pass

    @abc.abstractmethod
    def complete(self, prompt: str, schema_json: Optional[Dict[str, Any]] = None, num_ctx: int = 4096) -> Dict[str, Any]:
        """Execute completion and return dict with response text, latency, token metrics."""
        pass

    def get_version_info(self) -> str:
        return "unknown"


class OllamaAdapter(ModelAdapter):
    """Ollama API adapter enforcing non-negotiable constraints ('think': False, explicit num_ctx)."""

    def __init__(self, model_name: str, host: str = "127.0.0.1:11434"):
        self._model_name = model_name
        self.host = host
        self._api_url = f"http://{host}/api/generate"
        self._version_url = f"http://{host}/api/version"

    @property
    def model_id(self) -> str:
        return self._model_name

    @property
    def provider_kind(self) -> str:
        return "ollama"

    def get_version_info(self) -> str:
        try:
            req = urllib.request.Request(self._version_url, headers={"User-Agent": "GameForge-Eval"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("version", "unknown")
        except Exception:
            return "unknown"

    def complete(self, prompt: str, schema_json: Optional[Dict[str, Any]] = None, num_ctx: int = 4096) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": num_ctx,
            },
        }

        # If schema or json is requested
        if schema_json is not None:
            payload["format"] = "json"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._api_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-Eval"},
            method="POST",
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                duration_s = time.time() - t0
                body = json.loads(resp.read().decode("utf-8"))
                response_text = body.get("response", "")
                prompt_eval_count = body.get("prompt_eval_count", 0)
                eval_count = body.get("eval_count", 0)
                eval_duration_ns = body.get("eval_duration", 1)
                tok_per_sec = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0.0

                return {
                    "text": response_text,
                    "duration_s": duration_s,
                    "tokens_in": prompt_eval_count,
                    "tokens_out": eval_count,
                    "tok_per_sec": round(tok_per_sec, 2),
                    "cost_usd": 0.0,
                    "error": None,
                }
        except Exception as e:
            duration_s = time.time() - t0
            return {
                "text": "",
                "duration_s": duration_s,
                "tokens_in": 0,
                "tokens_out": 0,
                "tok_per_sec": 0.0,
                "cost_usd": 0.0,
                "error": str(e),
            }


class HostedAdapter(ModelAdapter):
    """Adapter for hosted model providers (Claude Messages API, OpenAI compatible)."""

    def __init__(self, provider_id: str, model_id: str, usd_per_mtok_in: float = 3.0, usd_per_mtok_out: float = 15.0):
        self._provider_id = provider_id
        self._model_id = model_id
        self.usd_per_mtok_in = usd_per_mtok_in
        self.usd_per_mtok_out = usd_per_mtok_out

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def provider_kind(self) -> str:
        return f"hosted:{self._provider_id}"

    def complete(self, prompt: str, schema_json: Optional[Dict[str, Any]] = None, num_ctx: int = 4096) -> Dict[str, Any]:
        # Without explicit approval/keys, this returns BLOCKED
        return {
            "text": "",
            "duration_s": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "tok_per_sec": 0.0,
            "cost_usd": 0.0,
            "error": "BLOCKED (needs approval: hosted provider API key and egress consent)",
        }


class DeterministicMockAdapter(ModelAdapter):
    """Deterministic fast mock adapter for unit tests and local verification."""

    def __init__(self, model_name: str = "mock-model:latest", fail_on_id: Optional[str] = None):
        self._model_name = model_name
        self._fail_on_id = fail_on_id

    @property
    def model_id(self) -> str:
        return self._model_name

    @property
    def provider_kind(self) -> str:
        return "mock"

    def get_version_info(self) -> str:
        return "mock-1.0.0"

    def complete(self, prompt: str, schema_json: Optional[Dict[str, Any]] = None, num_ctx: int = 4096) -> Dict[str, Any]:
        t0 = time.time()
        plower = prompt.lower()
        if "design agent" in plower or "draft" in plower or "genre" in plower:
            genre = "grid_board" if ("tic tac toe" in plower or "connect four" in plower) else "action_adventure"
            res_dict = {
                "title": "Evaluated Game",
                "genre": genre,
                "camera": "third_person" if genre != "grid_board" else "top_down",
                "pitch": "A thrilling evaluated game.",
                "win": [{"type": "collect", "target": 5}],
            }
        elif "rfc 6902" in plower or "patch" in plower or "ops" in plower:
            res_dict = {
                "ops": [{"op": "replace", "path": "/scene/levels/0/lighting", "value": "night"}],
                "summary": "Applied lighting patch to night",
                "questions": [],
            }
        elif "compiler error" in plower or "diagnostic" in plower or "cpp_repair" in plower:
            res_dict = {
                "fixed_code": "#include \"CoreMinimal.h\"\nHealth = 100.0f;\n}",
                "explanation": "Added missing semicolon",
            }
        elif "gameplay rule" in plower or "codegen" in plower or "uclass" in plower:
            res_dict = {
                "class_name": "UGameForgeRule_Custom",
                "code": "#pragma once\n#include \"CoreMinimal.h\"\nUCLASS()\nclass UGameForgeRule_Custom : public UObject {};",
            }
        else:
            res_dict = {"status": "OK", "evaluated": True}

        text = json.dumps(res_dict)
        return {
            "text": text,
            "duration_s": round(time.time() - t0, 3) + 0.015,
            "tokens_in": len(prompt) // 4,
            "tokens_out": len(text) // 4,
            "tok_per_sec": 75.0,
            "cost_usd": 0.0,
            "error": None,
        }
