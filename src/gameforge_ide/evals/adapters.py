"""Model adapters for GameForge Agentic Eval Suite (WI-9.1, WI-9.2)."""
from __future__ import annotations

import abc
import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


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
        except urllib.error.HTTPError as e:
            duration_s = time.time() - t0
            body_err = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
            err_msg = f"HTTP {e.code}: {body_err.strip() or e.reason}"
            return {
                "text": "",
                "duration_s": duration_s,
                "tokens_in": 0,
                "tokens_out": 0,
                "tok_per_sec": 0.0,
                "cost_usd": 0.0,
                "error": err_msg,
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

    def _build_mock_gds_patch(self, prompt: str) -> Dict[str, Any]:
        ops: List[Dict[str, Any]] = []
        base_doc: Dict[str, Any] = {}
        m_base = re.search(r"Base GDS JSON:\n(\{.*?\})\n", prompt, re.DOTALL)
        if m_base:
            try:
                base_doc = json.loads(m_base.group(1))
            except Exception:
                base_doc = {}

        entities = base_doc.get("entities", []) if isinstance(base_doc, dict) else []
        plower = prompt.lower()

        if "guards faster" in plower:
            for idx, ent in enumerate(entities):
                props = ent.get("props", {})
                if "movement_speed" in props:
                    ops.append({"op": "replace", "path": f"/entities/{idx}/props/movement_speed", "value": float(props["movement_speed"]) * 1.5})
        elif "player faster" in plower:
            for idx, ent in enumerate(entities):
                props = ent.get("props", {})
                if "speed" in props:
                    ops.append({"op": "replace", "path": f"/entities/{idx}/props/speed", "value": float(props["speed"]) * 1.5})
                elif ent.get("entity_id") == "player":
                    ops.append({"op": "add", "path": f"/entities/{idx}/props/speed", "value": 900.0})
        elif "guards slower" in plower:
            for idx, ent in enumerate(entities):
                props = ent.get("props", {})
                if "movement_speed" in props:
                    ops.append({"op": "replace", "path": f"/entities/{idx}/props/movement_speed", "value": float(props["movement_speed"]) * 0.5})
        elif "more relics" in plower or "more coins" in plower:
            delta = 5 if "5" in plower else 3
            for idx, ent in enumerate(entities):
                if ent.get("kind") in ("collectible", "pickup") or "relic" in ent.get("entity_id", "") or "coin" in ent.get("entity_id", ""):
                    ops.append({"op": "replace", "path": f"/entities/{idx}/count", "value": int(ent.get("count", 1)) + delta})
                    break
        elif "reduce enemies" in plower:
            for idx, ent in enumerate(entities):
                if ent.get("count", 1) > 1 and ent.get("entity_id") != "player":
                    ops.append({"op": "replace", "path": f"/entities/{idx}/count", "value": max(1, int(ent["count"] * 0.4))})
        elif "remove all guards" in plower:
            for idx in range(len(entities) - 1, -1, -1):
                if entities[idx].get("kind") == "guard" or "guard" in entities[idx].get("entity_id", ""):
                    ops.append({"op": "remove", "path": f"/entities/{idx}"})
        elif "remove all hazards" in plower:
            for idx in range(len(entities) - 1, -1, -1):
                if entities[idx].get("kind") == "hazard" or "hazard" in entities[idx].get("entity_id", ""):
                    ops.append({"op": "remove", "path": f"/entities/{idx}"})
        elif "hazard" in plower or "spikes" in plower:
            ops.append({
                "op": "add",
                "path": f"/entities/{len(entities)}",
                "value": {"entity_id": "hazard_zone", "display_name": "Hazard Zone", "kind": "hazard", "count": 2, "props": {"damage": 25.0}},
            })
        elif "checkpoint" in plower:
            ops.append({
                "op": "add",
                "path": f"/entities/{len(entities)}",
                "value": {"entity_id": "checkpoint_station", "display_name": "Checkpoint", "kind": "checkpoint", "count": 2, "props": {}},
            })
        elif "locked door" in plower:
            ops.append({
                "op": "add",
                "path": f"/entities/{len(entities)}",
                "value": {"entity_id": "locked_door", "display_name": "Locked Door", "kind": "door", "count": 1, "props": {}},
            })
        elif "lighting" in plower:
            if "night" in plower:
                val = "night"
            elif "dusk" in plower:
                val = "dusk"
            elif "dawn" in plower:
                val = "dawn"
            elif "sunset" in plower:
                val = "sunset"
            elif "overcast" in plower:
                val = "overcast"
            else:
                val = "day"
            ops.append({"op": "replace", "path": "/scene/levels/0/lighting", "value": val})
            ops.append({"op": "add", "path": "/scene/lighting", "value": val})
        elif "escape gate" in plower or "also require" in plower:
            goals = base_doc.get("goals", []) if isinstance(base_doc, dict) else []
            ops.append({
                "op": "add",
                "path": f"/goals/{len(goals)}",
                "value": {"goal_id": "reach_escape_gate", "kind": "reach_zone", "target_entity": "exit_zone", "target_count": 1},
            })
        elif "shadow keep" in plower:
            ops.append({"op": "replace", "path": "/meta/title", "value": "Shadow Keep"})
        elif "crystal valley" in plower:
            ops.append({"op": "replace", "path": "/meta/title", "value": "Crystal Valley"})
        elif "second level" in plower:
            levels = base_doc.get("scene", {}).get("levels", []) if isinstance(base_doc, dict) else []
            ops.append({
                "op": "add",
                "path": f"/scene/levels/{len(levels)}",
                "value": {"level_id": "level_2", "title": "Level 2", "lighting": "dusk", "layout": "arena", "size_meters": [60, 60]},
            })

        if not ops:
            ops = [{"op": "replace", "path": "/scene/levels/0/lighting", "value": "night"}]

        return {"ops": ops, "summary": "Applied requested GDS patch", "questions": []}

    def _build_mock_cpp_repair(self, prompt: str) -> Dict[str, Any]:
        plower = prompt.lower()
        if "c2065" in plower or "maxspeed" in plower:
            code = '#include "CoreMinimal.h"\nfloat s = 600.0f;\n'
        elif "c2440" in plower or "fromint" in plower or "cannot convert from 'int' to 'fstring'" in plower:
            code = '#include "CoreMinimal.h"\nFString Name = FString::FromInt(42);\n'
        elif "c2027" in plower or "ugameforgeeventbus" in plower:
            code = '#include "CoreMinimal.h"\n#include "GameForgeEventBus.h"\nUGameForgeEventBus* Bus = nullptr;\n'
        elif "c2511" in plower or "overloaded member function" in plower:
            code = '#include "CoreMinimal.h"\nvoid Apply(AGameForgeCharacter* Character) override;\n'
        elif "c2662" in plower or "const_qualification" in plower:
            code = '#include "CoreMinimal.h"\nfloat GetValue() const { return Value; }\n'
        elif "c4716" in plower or "must return a value" in plower:
            code = '#include "CoreMinimal.h"\nfloat Calculate() { float x = 10.0f; return x; }\n'
        elif "c6011" in plower or "dereferencing null pointer" in plower:
            code = '#include "CoreMinimal.h"\nif (Player) { Player->SetActorLocation(Loc); }\n'
        elif "lnk2019" in plower or "unresolved external" in plower:
            code = '#include "CoreMinimal.h"\nvoid Reset() {}\n'
        elif "c2664" in plower or "wrong_cast" in plower:
            code = '#include "CoreMinimal.h"\nProcessChar(Cast<AGameForgeCharacter>(GetOwner()));\n'
        else:
            code = '#include "CoreMinimal.h"\nHealth = 100.0f;\n}\n'
        return {"fixed_code": code, "explanation": "Repaired compiler diagnostic"}

    def complete(self, prompt: str, schema_json: Optional[Dict[str, Any]] = None, num_ctx: int = 4096) -> Dict[str, Any]:
        t0 = time.time()
        if self._fail_on_id and self._fail_on_id in prompt:
            return {
                "text": "",
                "duration_s": 0.005,
                "tokens_in": len(prompt) // 4,
                "tokens_out": 0,
                "tok_per_sec": 0.0,
                "cost_usd": 0.0,
                "error": f"Simulated failure for {self._fail_on_id}",
            }

        plower = prompt.lower()
        if "rfc 6902" in plower or ("patch" in plower and "ops" in plower):
            res_dict = self._build_mock_gds_patch(prompt)
        elif "compiler error" in plower or "diagnostic:" in plower or "cpp_repair" in plower:
            res_dict = self._build_mock_cpp_repair(prompt)
        elif "gameplay rule" in plower or "codegen" in plower or "uclass" in plower:
            res_dict = {
                "class_name": "UGameForgeRule_Custom",
                "code": '#pragma once\n#include "CoreMinimal.h"\nUCLASS()\nclass UGameForgeRule_Custom : public UObject {};',
            }
        elif "visual quality rubric" in plower or "framerate_stability" in plower:
            res_dict = {
                "criteria": {
                    "mesh_quality": 4,
                    "lighting_coherence": 4,
                    "composition_readability": 4,
                    "thematic_consistency": 4,
                    "no_placeholders": 5,
                    "framerate_stability": 5,
                },
                "overall": 4.33,
                "passed": True,
            }
        elif "design agent" in plower or "draft" in plower or "genre" in plower:
            if "tic tac toe" in plower or "connect four" in plower:
                genre = "grid_board"
            elif "platformer" in plower:
                genre = "platformer"
            elif "card" in plower or "deck" in plower:
                genre = "card_battler"
            elif "shooter" in plower:
                genre = "top_down_shooter"
            elif "arena" in plower or "wave" in plower:
                genre = "arena_combat"
            elif "dungeon" in plower:
                genre = "dungeon_crawler"
            elif "puzzle" in plower:
                genre = "puzzle"
            elif "procedural" in plower or "island" in plower or "exploration" in plower:
                genre = "exploration"
            else:
                genre = "action_adventure"
            res_dict = {
                "title": "Evaluated Game",
                "genre": genre,
                "camera": "third_person" if genre != "grid_board" else "top_down",
                "pitch": "A thrilling evaluated game.",
                "win": [{"type": "collect", "target": 5}],
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


__all__ = [
    "ModelAdapter",
    "OllamaAdapter",
    "HostedAdapter",
    "DeterministicMockAdapter",
]
