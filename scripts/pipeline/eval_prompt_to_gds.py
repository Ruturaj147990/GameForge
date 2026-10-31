"""Evaluation script: runs the 15 model prompts against local Ollama 9B model (P1 WI-1.9)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import urllib.request
from typing import Any, Dict, List

from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
from src.gameforge_ide.design.gds import EntityKind
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_FILE = REPO_ROOT / "tests" / "fixtures" / "gds_prompts.jsonl"
REPORT_FILE = REPO_ROOT / "reports" / "P1" / "prompt_to_gds_9b.json"

NOUN_TO_KIND = {
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
    try:
        url = f"http://{host}/api/version"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("version", "unknown")
    except Exception as exc:
        return f"unavailable ({exc})"


def evaluate_9b(model_id: str = "gameforge-qwen3.5-9b", host: str = "127.0.0.1:11434") -> Dict[str, Any]:
    provider = OllamaProvider(host=host)
    version = get_ollama_version(host)

    if not provider.is_available():
        raise RuntimeError(f"Ollama is not available on {host}")

    # Read fixtures
    fixtures = [json.loads(line) for line in FIXTURES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    model_cases = [f for f in fixtures if f["expect"] == "model"]

    print(f"Loaded {len(model_cases)} model evaluation prompts from {FIXTURES_FILE}")
    print(f"Ollama server version: {version}, Target model: {model_id}")

    complete_fn = lambda sys, usr, sch: provider.complete_json(
        model_id=model_id,
        system=sys,
        user=usr,
        schema=sch,
        num_ctx=8192,
        temperature=0.2,
        timeout_s=120.0,
    )

    results: List[Dict[str, Any]] = []
    first_try_valid_count = 0
    valid_after_repair_count = 0
    failed_closed_count = 0
    total_latency_s = 0.0
    fidelity_match_count = 0

    for i, case in enumerate(model_cases, start=1):
        prompt = case["prompt"]
        expected_nouns = case.get("checks", {}).get("nouns", [])
        print(f"\n[{i}/{len(model_cases)}] Evaluating: {prompt}")

        t0 = time.time()
        res = prompt_to_gds(prompt, complete_json=complete_fn, model=model_id, allow_model=True)
        latency_s = round(time.time() - t0, 2)
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
                fidelity_matches.append({"noun": noun, "expected_kind": expected_kind.value if expected_kind else None, "matched": matched})
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

    n = len(model_cases)
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

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to {REPORT_FILE}")
    print(f"Summary: Valid rate = {valid_rate*100:.1f}%, Failed closed rate = {failed_closed_rate*100:.1f}%, Mean latency = {mean_latency_s}s, Gate = {report['status']}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate prompt_to_gds on local Ollama 9B")
    parser.add_argument("--model", default="gameforge-qwen3.5-9b", help="Ollama model ID")
    parser.add_argument("--host", default="127.0.0.1:11434", help="Ollama host")
    args = parser.parse_args()

    evaluate_9b(model_id=args.model, host=args.host)
