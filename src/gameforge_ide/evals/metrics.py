"""Metrics computation for GameForge Agentic Eval Suite (WI-9.1)."""
from __future__ import annotations

import statistics
from typing import Any, Dict, List


def compute_task_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate summary metrics for a suite of task execution results."""
    total = len(results)
    if total == 0:
        return {
            "total_tasks": 0,
            "passed_tasks": 0,
            "pass_rate": 0.0,
            "valid_json_rate": 0.0,
            "first_try_valid_rate": 0.0,
            "median_latency_s": 0.0,
            "p90_latency_s": 0.0,
            "mean_tok_per_sec": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "estimated_cost_usd": 0.0,
        }

    passed_count = sum(1 for r in results if r.get("passed", False))
    valid_json_count = sum(1 for r in results if r.get("valid_json", False))
    first_try_count = sum(1 for r in results if r.get("first_try_valid", False))

    latencies = [r.get("duration_s", 0.0) for r in results if "duration_s" in r]
    if latencies:
        latencies.sort()
        med_lat = statistics.median(latencies)
        p90_idx = int(len(latencies) * 0.90)
        p90_idx = min(p90_idx, len(latencies) - 1)
        p90_lat = latencies[p90_idx]
    else:
        med_lat = 0.0
        p90_lat = 0.0

    tok_rates = [r.get("tok_per_sec", 0.0) for r in results if r.get("tok_per_sec", 0.0) > 0]
    mean_tok_rate = statistics.mean(tok_rates) if tok_rates else 0.0

    tok_in = sum(r.get("tokens_in", 0) for r in results)
    tok_out = sum(r.get("tokens_out", 0) for r in results)
    cost_usd = sum(r.get("cost_usd", 0.0) for r in results)

    return {
        "total_tasks": total,
        "passed_tasks": passed_count,
        "pass_rate": round((passed_count / total) * 100.0, 2),
        "valid_json_rate": round((valid_json_count / total) * 100.0, 2),
        "first_try_valid_rate": round((first_try_count / total) * 100.0, 2),
        "median_latency_s": round(med_lat, 3),
        "p90_latency_s": round(p90_lat, 3),
        "mean_tok_per_sec": round(mean_tok_rate, 1),
        "total_tokens_in": tok_in,
        "total_tokens_out": tok_out,
        "estimated_cost_usd": round(cost_usd, 4),
    }


def calculate_task_deltas(
    baseline_scores: Dict[str, float],
    candidate_scores: Dict[str, float],
) -> Dict[str, Any]:
    """Calculates per-task deltas, total points delta, and counts improved/regressed/unchanged tasks."""
    improved = 0
    regressed = 0
    unchanged = 0
    deltas: Dict[str, float] = {}
    total_delta = 0.0

    for task_id, b_score in baseline_scores.items():
        c_score = candidate_scores.get(task_id, 0.0)
        delta = c_score - b_score
        deltas[task_id] = round(delta, 3)
        total_delta += delta
        if delta > 0.001:
            improved += 1
        elif delta < -0.001:
            regressed += 1
        else:
            unchanged += 1

    return {
        "improved_count": improved,
        "regressed_count": regressed,
        "unchanged_count": unchanged,
        "total_delta": round(total_delta, 2),
        "per_task_deltas": deltas,
    }


__all__ = [
    "compute_task_metrics",
    "calculate_task_deltas",
]
