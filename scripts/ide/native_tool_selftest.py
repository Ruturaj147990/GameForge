"""Live native tool-calling self-test for every installed Ollama model (Blueprint v2 §6 gate).

    python scripts/ide/native_tool_selftest.py [--out reports/native_tool_selftest.json]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/native_tool_selftest.json")
    a = ap.parse_args()
    prov = OllamaProvider()
    if not prov.is_available():
        print("Ollama offline")
        return 2
    results = []
    for m in prov.list_models():
        r = prov.native_tool_self_test(m.id)
        # unload after each model so the next one gets the whole GPU
        try:
            prov.chat_with_tools(m.id, [{"role": "user", "content": "ok"}], [], num_ctx=512, max_tokens=1, keep_alive="0")
        except Exception:
            pass
        results.append(r)
        print(json.dumps(r)[:300], flush=True)
    Path(a.out).write_text(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "results": results}, indent=1),
                           encoding="utf-8")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
