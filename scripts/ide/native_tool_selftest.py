"""Live native tool-calling self-test for installed Ollama models (Blueprint v2 §6 gate).

    python scripts/ide/native_tool_selftest.py [--model <model_id>] [--out reports/native_tool_selftest.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Live native tool-calling self-test for Ollama models")
    ap.add_argument("--model", default=None, help="Specific model ID to test (default: all installed models)")
    ap.add_argument("--out", default="reports/native_tool_selftest.json", help="Path to output JSON report")
    a = ap.parse_args(argv)

    prov = OllamaProvider()
    if not prov.is_available():
        print("Ollama offline")
        return 2

    models = prov.list_models()
    if a.model:
        models = [m for m in models if m.id == a.model or m.id.startswith(a.model)]
        if not models:
            print(f"Model '{a.model}' not found in installed models.")
            return 1

    results: List[Dict[str, Any]] = []
    for m in models:
        r = prov.native_tool_self_test(m.id)
        # unload after each model so the next one gets the whole GPU
        try:
            prov.chat_with_tools(
                m.id,
                [{"role": "user", "content": "ok"}],
                [],
                num_ctx=512,
                max_tokens=1,
                keep_alive="0",
                think=False,
            )
        except Exception:
            pass
        results.append(r)
        print(json.dumps(r, default=str)[:300], flush=True)

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "models_tested": len(results),
        "results": results,
    }
    tmp_out = out_path.with_suffix(".tmp")
    tmp_out.write_text(json.dumps(report_data, indent=2, default=str), encoding="utf-8")
    tmp_out.replace(out_path)

    all_passed = bool(results) and all(bool(r.get("ok")) for r in results)
    print(f"Native tool selftest: {'ALL PASSED' if all_passed else 'SOME FAILED'} ({len(results)} models tested)")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
