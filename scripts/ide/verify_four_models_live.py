"""Verify live inference on the four canonical roster models in Ollama.

    python scripts/ide/verify_four_models_live.py [--out reports/live_models_verification.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_MODELS: List[str] = [
    "llama3.1:8b",
    "gameforge-27b-sft:latest",
    "gameforge-qwen3.5-4b:latest",
    "gameforge-qwen3.5-9b:latest",
]


def _unload_model(endpoint: str, model_name: str) -> None:
    """Explicitly unloads model from VRAM to preserve 12GB budget on RX 7700 XT."""
    try:
        payload = {
            "model": model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{endpoint}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass


def test_model(endpoint: str, model_name: str) -> Dict[str, Any]:
    t0 = time.monotonic()
    payload = {
        "model": model_name,
        "prompt": "Hello! Please identify your system role and confirm you are operational.",
        "stream": False,
        "think": False,
        "options": {
            "num_predict": 40,
            "temperature": 0.2,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    result: Dict[str, Any] = {"model": model_name, "ok": False}
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.monotonic() - t0
            resp_txt = res.get("response", "").strip().replace("\n", " ")
            eval_count = res.get("eval_count", 0)
            eval_dur = res.get("eval_duration", 1) / 1e9
            tps = eval_count / eval_dur if eval_dur > 0 else 0.0
            result.update({
                "ok": True,
                "latency_s": round(elapsed, 2),
                "tps": round(tps, 1),
                "eval_count": eval_count,
                "response_sample": resp_txt[:80],
            })
            print(f"[OK] {model_name:30s} | {tps:5.1f} tok/s | Latency: {elapsed:4.1f}s | Response: {resp_txt[:60]}...")
    except Exception as e:
        result["error"] = str(e)
        print(f"[FAIL] {model_name:30s} | Error: {e}")
    finally:
        _unload_model(endpoint, model_name)

    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify live inference on roster models")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434", help="Ollama API base URL")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "reports" / "live_models_verification.json")
    parser.add_argument("models", nargs="*", default=DEFAULT_MODELS, help="List of models to verify")
    args = parser.parse_args(argv)

    print("=" * 70)
    print(" VERIFYING LIVE INFERENCE ON FOUR CANONICAL ROSTER MODELS")
    print("=" * 70)

    results: List[Dict[str, Any]] = []
    for m in args.models:
        results.append(test_model(args.endpoint.rstrip("/"), m))

    print("=" * 70)

    report_path: Path = args.out
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "endpoint": args.endpoint,
        "models": results,
        "all_passed": bool(results) and all(r.get("ok") for r in results),
    }
    tmp_report = report_path.with_suffix(".tmp")
    tmp_report.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    tmp_report.replace(report_path)
    print(f"Report written to {report_path}")

    return 0 if report_data["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
