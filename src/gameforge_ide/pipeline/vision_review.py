"""Advisory vision review of gameplay evidence (Master Blueprint v1/v2: vision output is advisory).

A vision-capable model (hosted when enabled for the workspace, else a local model with a vision
projector) compares the gameplay screenshot with the request and design. Its verdict can trigger a
bounded quality-improvement round, but it can never make a failing build pass or a passing build fail.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Dict, Optional

from ..backend.providers.ollama_provider import OllamaProvider

LOCAL_VISION_MODEL = "gameforge-qwen3.5-4b:latest"


def _parse(text: str) -> Optional[Dict]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def review_screenshot(image: Path, request: str, design: str, scene_facts: str,
                      model: str = LOCAL_VISION_MODEL) -> Dict:
    prompt = (
        "You are a strict game QA reviewer. Judge ONLY what is visible.\n"
        f"Player request: {request}\nIntended design: {design[:900]}\nScene facts from the engine: {scene_facts}\n"
        "This screenshot was taken from the running, packaged game. Does it look like a playable version of the "
        "request (readable layout, sensible number and size of objects, HUD text that matches)? Reply with JSON only: "
        '{"matches_request": true|false, "problems": ["..."], "suggestions": ["..."]}')
    try:
        img = base64.b64encode(Path(image).read_bytes()).decode("ascii")
        prov = OllamaProvider(timeout_seconds=300)
        res = prov.chat_with_tools(model, [{"role": "user", "content": prompt, "images": [img]}], [],
                                   num_ctx=8192, max_tokens=500, keep_alive="0")
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    data = _parse(res.get("content", "")) or {}
    return {"available": bool(data), "model": model,
            "matches_request": bool(data.get("matches_request", True)) if data else None,
            "problems": [str(p)[:200] for p in (data.get("problems") or [])][:6],
            "suggestions": [str(s)[:200] for s in (data.get("suggestions") or [])][:6],
            "raw": res.get("content", "")[:1500]}
