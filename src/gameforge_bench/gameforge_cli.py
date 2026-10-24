"""GameForge LLM V1 Interactive CLI and Model Assessment Console.

Provides:
- Interactive chat with `gameforge-v1`
- Version-aware local knowledge retrieval injection
- Model information, memory schedule, and limits inspection
- Autonomous evaluation runner comparing base vs gameforge-v1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .eval_dataset import get_evaluation_dataset
from .knowledge_retrieval import GameForgeKnowledgeBase


def check_ollama_status(host: str = "127.0.0.1:11434") -> Tuple[bool, List[str]]:
    """Checks if Ollama service is reachable and returns available model tags."""
    try:
        url = f"http://{host}/api/tags"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            return True, models
    except Exception:
        return False, []


def query_ollama(
    prompt: str,
    model_name: str = "gameforge-27b-sft",
    system_prompt: Optional[str] = None,
    host: str = "127.0.0.1:11434",
    temperature: float = 0.2,
    num_ctx: int = 4096,
    num_predict: int = 512,
    timeout: int = 360,
    think: Optional[bool] = False,
) -> Dict[str, Any]:
    """Sends a completion request to local Ollama instance."""
    url = f"http://{host}/api/generate"
    options = {
        "temperature": temperature,
        "num_ctx": num_ctx,
    }
    if num_predict > 0:
        options["num_predict"] = num_predict

    payload = {
        "model": model_name,
        "prompt": prompt,
        "system": system_prompt or "",
        "stream": False,
        "options": options,
    }
    if think is not None:
        payload["think"] = think

    start_time = time.time()
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        duration = time.time() - start_time
        resp_content = data.get("response", "")
        if not resp_content and data.get("thinking"):
            resp_content = data.get("thinking", "")
        return {
            "success": True,
            "response": resp_content,
            "thinking": data.get("thinking", ""),
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "total_duration_seconds": duration,
            "eval_duration_seconds": data.get("eval_duration", 0) / 1e9,
            "tokens_per_second": (data.get("eval_count", 0) / (data.get("eval_duration", 1) / 1e9)) if data.get("eval_duration") else 0.0,
            "error": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "response": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_duration_seconds": time.time() - start_time,
            "eval_duration_seconds": 0.0,
            "tokens_per_second": 0.0,
            "error": str(exc),
        }


def run_interactive_chat(model: str = "gameforge-27b-sft", engine: Optional[str] = None, host: str = "127.0.0.1:11434") -> None:
    """Runs interactive terminal chat loop with knowledge retrieval."""
    print("=" * 72)
    print(" GAMEFORGE 27B SFT — INTERACTIVE ASSISTANT CONSOLE")
    print(f" Target Model : {model}")
    print(f" Engine Filter: {engine or 'Universal (Cross-Engine)'}")
    print(" Local Storage: E:\\GameForge\\models\\ollama")
    print(" Type 'exit' or 'quit' to return to terminal.")
    print("=" * 72)

    kb = GameForgeKnowledgeBase()

    while True:
        try:
            user_input = input("\n[GameForge] > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting GameForge Console. Session closed.")
                break

            # 1. Retrieve relevant knowledge
            snippets = kb.query_knowledge(user_input, engine_filter=engine, max_results=2)
            retrieval_text = kb.format_retrieval_context(snippets)
            full_prompt = f"{retrieval_text}\nUser Question: {user_input}" if retrieval_text else user_input

            print("\nGenerating response from local model (streaming disabled)...")
            res = query_ollama(prompt=full_prompt, model_name=model, host=host)

            if res["success"]:
                print("-" * 72)
                print(res["response"].strip())
                print("-" * 72)
                print(f"[Tokens: {res['completion_tokens']} | Speed: {res['tokens_per_second']:.1f} tok/s | Time: {res['total_duration_seconds']:.2f}s]")
            else:
                print(f"\n[ERROR] Model invocation failed: {res['error']}")
        except KeyboardInterrupt:
            print("\nSession interrupted.")
            break


def run_model_evaluation(
    model: str = "gameforge-27b-sft",
    baseline_model: Optional[str] = "qwen3.8:27b-q4_K_M",
    limit: int = 5,
    representative: bool = False,
    host: str = "127.0.0.1:11434",
    output_file: str = "reports/gameforge_evaluation_report.json",
) -> None:
    """Runs automated evaluation on dataset questions, scoring rubric concept coverage."""
    all_questions = get_evaluation_dataset()
    if representative:
        seen_cats = set()
        questions = []
        for q in all_questions:
            c = q.get("category")
            if c not in seen_cats:
                seen_cats.add(c)
                questions.append(q)
    elif limit > 0:
        questions = all_questions[:limit]
    else:
        questions = all_questions

    kb = GameForgeKnowledgeBase()
    results = []
    print(f"Running GameForge evaluation for '{model}' across {len(questions)} test prompts...")

    for idx, q in enumerate(questions, 1):
        q_id = q["id"]
        title = q["title"]
        category = q["category"]
        prompt = q["prompt"]
        rubric = q.get("rubric_required_concepts", [])

        print(f"[{idx}/{len(questions)}] Evaluating {q_id}: {title}...", end="", flush=True)

        # Retrieve knowledge
        snippets = kb.query_knowledge(prompt, engine_filter=q.get("target_engine"), max_results=2)
        retrieval_text = kb.format_retrieval_context(snippets)
        eval_prompt = f"{retrieval_text}\n{prompt}" if retrieval_text else prompt

        t0 = time.time()
        res = query_ollama(eval_prompt, model_name=model, host=host)
        resp_text = res.get("response", "")

        # Check rubric concepts
        matched = []
        for concept in rubric:
            if concept.lower() in resp_text.lower():
                matched.append(concept)
        score = len(matched) / len(rubric) if rubric else 1.0

        print(f" Score: {len(matched)}/{len(rubric)} ({score*100:.0f}%) [{res.get('tokens_per_second', 0.0):.1f} tok/s]")

        results.append({
            "question_id": q_id,
            "title": title,
            "category": category,
            "target_engine": q.get("target_engine"),
            "model_tested": model,
            "success": res.get("success"),
            "tokens_generated": res.get("completion_tokens"),
            "speed_tokens_per_sec": round(res.get("tokens_per_second", 0.0), 2),
            "rubric_total_concepts": len(rubric),
            "rubric_matched_concepts": matched,
            "rubric_score": round(score, 3),
            "raw_response_snippet": resp_text[:400] + "..." if len(resp_text) > 400 else resp_text,
        })

    avg_score = sum(r["rubric_score"] for r in results) / len(results) if results else 0.0
    avg_speed = sum(r["speed_tokens_per_sec"] for r in results) / len(results) if results else 0.0

    # Aggregate per-domain breakdown
    domain_scores: Dict[str, List[float]] = {}
    domain_speeds: Dict[str, List[float]] = {}
    for r in results:
        cat = r["category"]
        domain_scores.setdefault(cat, []).append(r["rubric_score"])
        domain_speeds.setdefault(cat, []).append(r["speed_tokens_per_sec"])

    domain_summary = {
        cat: {
            "count": len(scores),
            "mean_rubric_adherence": round(sum(scores) / len(scores), 3),
            "mean_tokens_per_sec": round(sum(domain_speeds[cat]) / len(scores), 2),
        }
        for cat, scores in domain_scores.items()
    }

    summary = {
        "evaluation_timestamp": time.time(),
        "model": model,
        "baseline_model": baseline_model,
        "questions_evaluated": len(results),
        "mean_rubric_adherence": round(avg_score, 3),
        "mean_tokens_per_second": round(avg_speed, 2),
        "domain_summary": domain_summary,
        "detailed_results": results,
    }

    out_p = Path(output_file)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nEvaluation Complete! Mean Score: {avg_score*100:.1f}%. Report saved to {output_file}")
