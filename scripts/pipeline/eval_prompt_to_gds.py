"""Evaluation script: runs model prompts against local Ollama 9B model (P1 WI-1.9)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
from src.gameforge_ide.design.gds import EntityKind
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
DEFAULT_FIXTURES_FILE = REPO_ROOT / "tests" / "fixtures" / "gds_prompts.jsonl"
DEFAULT_REPORT_FILE = REPO_ROOT / "reports" / "P1" / "prompt_to_gds_9b.json"

NOUN_TO_KIND: Dict[str, EntityKind] = {
    "relics": EntityKind.PICKUP,
    "pickup": EntityKind.PICKUP,
    "pickups": EntityKind.PICKUP,
    "crystals": EntityKind.PICKUP,
    "chalice": EntityKind.PICKUP,
    "terminals": EntityKind.PICKUP,
    "key": EntityKind.PICKUP,
    "treasure": EntityKind.PICKUP,
    "guards": EntityKind.GUARD,
    "guard": EntityKind.GUARD,
    "enemies": EntityKind.ENEMY,
    "enemy": EntityKind.ENEMY,
    "invaders": EntityKind.ENEMY,
    "boss": EntityKind.ENEMY,
    "skeleton": EntityKind.ENEMY,
    "goblins": EntityKind.ENEMY,
    "villagers": EntityKind.NPC,
    "npcs": EntityKind.NPC,
    "door": EntityKind.DOOR,
    "doors": EntityKind.DOOR,
    "switches": EntityKind.SWITCH,
    "switch": EntityKind.SWITCH,
    "spawner": EntityKind.SPAWNER,
    "waves": EntityKind.SPAWNER,
    "stations": EntityKind.CHECKPOINT,
    "checkpoints": EntityKind.CHECKPOINT,
    "altar": EntityKind.GOAL,
    "portal": EntityKind.GOAL,
    "goal": EntityKind.GOAL,
    "escape": EntityKind.GOAL,
    "islands": EntityKind.LANDMARK,
    "hazards": EntityKind.HAZARD,
}


def get_ollama_version(host: str = "127.0.0.1:11434") -> str:
    """Fetch running Ollama server version string or return unavailable message."""
    try:
        url = f"http://{host}/api/version"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("version", "unknown")
    except Exception as exc:
        return f"unavailable ({exc})"


def unload_ollama_model(host: str, model_id: str) -> bool:
    """Explicitly release model from GPU VRAM via Ollama API keep_alive=0."""
    try:
        url = f"http://{host}/api/generate"
        payload = json.dumps({"model": model_id, "keep_alive": 0}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False


def evaluate_9b(
    model_id: str = "gameforge-qwen3.5-9b:latest",
    host: str = "127.0.0.1:11434",
    fixtures_file: Optional[Path] = None,
    report_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run prompt-to-GDS evaluation and write structured benchmark report."""
    provider = OllamaProvider(host=host)
    version = get_ollama_version(host)
    fixtures_path = fixtures_file or DEFAULT_FIXTURES_FILE
    out_report_path = report_file or DEFAULT_REPORT_FILE

    if not provider.is_available():
        raise RuntimeError(f"Ollama is not available on {host}")

    if not fixtures_path.exists():
        raise FileNotFoundError(f"Evaluation fixtures file not found: {fixtures_path}")

    # Read fixtures
    fixtures = [json.loads(line) for line in fixtures_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    model_cases = [f for f in fixtures if f.get("expect") == "model"]

    n = len(model_cases)
    print(f"Loaded {n} model evaluation prompts from {fixtures_path}")
    print(f"Ollama server version: {version}, Target model: {model_id}")

    if n == 0:
        print("No evaluation cases found with expect == 'model'.")
        return {"status": "NO_CASES", "sample_size": 0, "gate_pass": False}

    complete_fn = lambda sys_p, usr_p, sch_p: provider.complete_json(
        model_id=model_id,
        system=sys_p,
        user=usr_p,
        schema=sch_p,
        num_ctx=8192,
        temperature=0.2,
        timeout_s=300.0,
    )

    results: List[Dict[str, Any]] = []
    first_try_valid_count = 0
    valid_after_repair_count = 0
    failed_closed_count = 0
    total_latency_s = 0.0
    fidelity_match_count = 0

    try:
        for i, case in enumerate(model_cases, start=1):
            prompt = case["prompt"]
            expected_nouns = case.get("checks", {}).get("nouns", [])
            print(f"\n[{i}/{n}] Evaluating: {prompt}")

            t0 = time.monotonic()
            res = prompt_to_gds(prompt, complete_json=complete_fn, model=model_id, allow_model=True)
            latency_s = round(time.monotonic() - t0, 2)
            total_latency_s += latency_s

            first_try = res.attempts == 1 and res.gds is not None
            valid_overall = res.gds is not None
            failed_closed = (res.status == "NEEDS_INPUT" and res.gds is None)

            if first_try:
                first_try_valid_count += 1
            if valid_overall:
                valid_after_repair_count += 1
            elif failed_closed:
                failed_closed_count += 1

            # Fidelity checklist
            fidelity_matches = []
            if res.gds is not None:
                present_kinds = {e.kind for e in res.gds.entities}
                for noun in expected_nouns:
                    expected_kind = NOUN_TO_KIND.get(noun.lower())
                    matched = expected_kind in present_kinds if expected_kind else True
                    fidelity_matches.append({
                        "noun": noun,
                        "expected_kind": expected_kind.value if expected_kind else None,
                        "matched": matched,
                    })
                all_fidelity_ok = all(m["matched"] for m in fidelity_matches)
            else:
                fidelity_matches = [{"noun": n, "matched": False} for n in expected_nouns]
                all_fidelity_ok = False

            if all_fidelity_ok:
                fidelity_match_count += 1

            print(f"  -> status={res.status}, attempts={res.attempts}, path={res.path}, latency={latency_s}s, fidelity_ok={all_fidelity_ok}")
            if res.errors:
                print(f"  -> errors: {res.errors}")

            results.append({
                "prompt": prompt,
                "status": res.status,
                "path": res.path,
                "attempts": res.attempts,
                "latency_s": latency_s,
                "first_try_valid": first_try,
                "valid": valid_overall,
                "failed_closed": failed_closed,
                "fidelity": fidelity_matches,
                "fidelity_ok": all_fidelity_ok,
                "errors": res.errors,
                "title": res.gds.meta.title if res.gds else None,
                "genre": res.gds.overview.genre.value if res.gds else None,
            })
    finally:
        # Mandatory teardown: release model VRAM back to host GPU
        unloaded = unload_ollama_model(host, model_id)
        if unloaded:
            print(f"Cleaned up Ollama model {model_id} from VRAM (keep_alive=0).")

    first_try_rate = round(first_try_valid_count / n, 4)
    valid_rate = round(valid_after_repair_count / n, 4)
    failed_closed_rate = round(failed_closed_count / (n - valid_after_repair_count), 4) if (n - valid_after_repair_count) > 0 else 1.0
    mean_latency_s = round(total_latency_s / n, 2)
    fidelity_rate = round(fidelity_match_count / n, 4)

    # Gate: >= 80% valid after repair, 100% of invalid outputs fail closed
    gate_pass = valid_rate >= 0.80 and failed_closed_rate >= 1.0

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model_id,
        "ollama_version": version,
        "sample_size": n,
        "first_try_valid_rate": first_try_rate,
        "valid_after_repair_rate": valid_rate,
        "failed_closed_rate": failed_closed_rate,
        "mean_latency_s": mean_latency_s,
        "fidelity_rate": fidelity_rate,
        "gate_pass": gate_pass,
        "status": "PASS" if gate_pass else "PARTIAL",
        "results": results,
    }

    out_report_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = out_report_path.parent
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=temp_dir, delete=False, suffix=".tmp") as tf:
        json.dump(report, tf, indent=2)
        tf_name = tf.name
    os.replace(tf_name, out_report_path)

    print(f"\nReport written to {out_report_path}")
    print(f"Summary: Valid rate = {valid_rate*100:.1f}%, Failed closed rate = {failed_closed_rate*100:.1f}%, Mean latency = {mean_latency_s}s, Gate = {report['status']}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate prompt_to_gds on local Ollama 9B")
    parser.add_argument("--model", default="gameforge-qwen3.5-9b:latest", help="Ollama model ID")
    parser.add_argument("--host", default="127.0.0.1:11434", help="Ollama host")
    parser.add_argument("--fixtures", type=Path, default=None, help="Path to evaluation fixtures JSONL")
    parser.add_argument("--output", type=Path, default=None, help="Path to write JSON evaluation report")
    args = parser.parse_args()

    report = evaluate_9b(
        model_id=args.model,
        host=args.host,
        fixtures_file=args.fixtures,
        report_file=args.output,
    )
    return 0 if report.get("gate_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
