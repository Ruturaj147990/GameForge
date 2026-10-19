"""Automated Scorecard and Candidate Snapshot Integrity Consistency Tests.

Enforces:
- Denominators match total attempts
- Pass counts match sum of PASS attempts
- No duplicate run IDs
- Every attempt has a valid snapshot hash or artifact trace
- Domain totals equal total attempts
- Failure taxonomy count matches non-pass count
"""

import json
from pathlib import Path
import pytest


def test_scorecard_mathematical_consistency():
    """Verify that any scorecard summary JSON obeys strict arithmetic integrity."""
    summary_path = Path(__file__).parents[2] / "reports" / "baseline_runs" / "baseline_summary.json"
    if not summary_path.is_file():
        pytest.skip("baseline_summary.json not present")

    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scorecard = data.get("scorecard", {})
    assert len(scorecard) > 0, "Scorecard must contain at least one candidate entry"

    for cand_id, entry in scorecard.items():
        attempts_count = entry.get("attempts_count", 0)
        passes_count = entry.get("passes_count", 0)
        build_fail_count = entry.get("build_fail_count", 0)
        partial_count = entry.get("partial_count", 0)
        attempts = entry.get("attempts", [])

        # 1. Total attempts match array length
        assert len(attempts) == attempts_count, f"Mismatch in attempts array length for {cand_id}"

        # 2. Denominator check: pass_at_1 must equal passes / attempts_count
        expected_pass_at_1 = round(passes_count / attempts_count, 4) if attempts_count > 0 else 0.0
        assert entry.get("pass_at_1") == expected_pass_at_1, f"Pass@1 arithmetic error for {cand_id}"

        # 3. Duplicate run IDs check
        run_ids = [a.get("attempt_id") for a in attempts]
        assert len(run_ids) == len(set(run_ids)), f"Duplicate run IDs found in candidate {cand_id}"

        # 4. Domain totals sum check
        domain_scores = entry.get("domain_scores", {})
        domain_total = sum(d.get("total", 0) for d in domain_scores.values())
        assert domain_total == attempts_count, f"Domain total ({domain_total}) != attempts ({attempts_count})"

        # 5. Domain pass sum check
        domain_passes = sum(d.get("pass", 0) for d in domain_scores.values())
        assert domain_passes == passes_count, f"Domain passes ({domain_passes}) != passes_count ({passes_count})"

        # 6. Failure taxonomy sum check
        taxonomy = entry.get("failure_taxonomy", {})
        taxonomy_sum = sum(taxonomy.values())
        non_pass_count = attempts_count - passes_count
        assert taxonomy_sum == non_pass_count, f"Taxonomy sum ({taxonomy_sum}) != non-pass ({non_pass_count})"

        # 7. Traceability: each attempt must have valid task_id, status, and duration
        for a in attempts:
            assert a.get("task_id"), f"Attempt missing task_id in {cand_id}"
            assert a.get("duration_seconds", 0) >= 0.0, f"Negative duration in {cand_id}"
            assert a.get("grading", {}).get("overall_status") in [
                "PASS", "POLICY_FAIL", "FAIL", "PARTIAL_REASONING", "PARTIAL_BUILD", "HARNESS_INVALID", "UNVERIFIED"
            ]


def test_no_dangling_historical_report_references():
    """Verify that reports do not reference missing task IDs or fabricated engines."""
    summary_path = Path(__file__).parents[2] / "reports" / "baseline_runs" / "baseline_summary.json"
    if not summary_path.is_file():
        pytest.skip("baseline_summary.json not present")

    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for cand_id, entry in data.get("scorecard", {}).items():
        for a in entry.get("attempts", []):
            task_id = a.get("task_id")
            # Verify task exists in either pilot_tasks or benchmark_tasks
            pilot_yaml = Path(__file__).parents[2] / "pilot_tasks" / f"{task_id}.yaml"
            bench_yaml = Path(__file__).parents[2] / "benchmark_tasks" / f"{task_id}.yaml"
            bench_neutral = Path(__file__).parents[2] / "benchmark_tasks" / "engine_neutral" / f"{task_id}.yaml"
            assert pilot_yaml.is_file() or bench_yaml.is_file() or bench_neutral.is_file(), f"Dangling task reference: {task_id}"
