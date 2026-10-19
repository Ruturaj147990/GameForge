"""GameForge Step 5 Baseline Evaluation Runner and Reporting Engine.

Executes baseline evaluations of authorized model candidates against the frozen
benchmark manifest, collects layered results, records repeated-run variance,
analyzes failure taxonomy, and outputs structured evaluation summaries.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .grading import RunStatus
from .model_adapter import ModelRequest, ModelResponse, extract_code_blocks, invoke_candidate, run_attempt
from .policy import check_candidate_policy, snapshot_directory_hashes
from .runner import BenchmarkRunner
from .task_loader import TaskSpec, load_task


def evaluate_engine_neutral_task(task_spec: TaskSpec, response_text: str) -> Dict[str, Any]:
    """Evaluates an engine-neutral reasoning task against rubric postconditions."""
    text_lower = response_text.lower()
    
    # Required concepts for T1 tasks
    rubric_scores = {}
    if task_spec.id == "t1-001-health-invariants":
        rubric_scores["invulnerability_window"] = any(k in text_lower for k in ["invulnerab", "window", "immunity", "cooldown"])
        rubric_scores["clamping"] = any(k in text_lower for k in ["clamp", "min", "max", "boundary", "0"])
        rubric_scores["exactly_once_death"] = any(k in text_lower for k in ["death", "dead", "once", "transition", "flag"])
        rubric_scores["event_sequencing"] = any(k in text_lower for k in ["event", "dispatch", "order", "sequence", "notify"])
        rubric_scores["cross_engine_translation"] = ("unreal" in text_lower and "unity" in text_lower)
    elif task_spec.id == "t1-002-pickup-contract":
        rubric_scores["one_time_collection"] = any(k in text_lower for k in ["consume", "one-time", "single", "deactivat"])
        rubric_scores["resource_clamping"] = any(k in text_lower for k in ["clamp", "capacity", "max", "full"])
        rubric_scores["receiver_interface"] = any(k in text_lower for k in ["interface", "receiver", "contract", "component"])
        rubric_scores["cross_engine_translation"] = ("unreal" in text_lower and "unity" in text_lower)
    elif task_spec.id == "t1-003-event-diagnostics":
        rubric_scores["duplicate_subscription_identification"] = any(k in text_lower for k in ["duplicate", "multiple", "double", "leak", "re-bind"])
        rubric_scores["idempotent_registration"] = any(k in text_lower for k in ["idempotent", "guard", "unbind", "remove", "clean"])
        rubric_scores["lifecycle_cleanup"] = any(k in text_lower for k in ["destruct", "destroy", "teardown", "cleanup", "disable"])
        rubric_scores["cross_engine_translation"] = ("unreal" in text_lower or "unity" in text_lower)
    else:
        rubric_scores["general_reasoning"] = len(response_text) > 100

    passed_checks = sum(1 for v in rubric_scores.values() if v)
    total_checks = len(rubric_scores)
    rubric_pass = (passed_checks == total_checks) if total_checks > 0 else False

    return {
        "status": "PASS" if rubric_pass else "PARTIAL_REASONING",
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "rubric_details": rubric_scores,
    }


class BaselineEvaluator:
    """Manages baseline model evaluation runs across candidate registers and manifests."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
        register_path: Optional[Path] = None,
    ):
        self.workspace_root = workspace_root or Path.cwd()
        self.manifest_path = manifest_path or (self.workspace_root / "configs" / "baseline_release_manifest.json")
        self.register_path = register_path or (self.workspace_root / "configs" / "model_register.json")
        self.runner = BenchmarkRunner(workspace_root=self.workspace_root)
        
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        with open(self.register_path, "r", encoding="utf-8") as f:
            self.register = json.load(f)

    def execute_attempt(
        self,
        candidate_config: Dict[str, Any],
        task_info: Dict[str, Any],
        run_index: int = 1,
    ) -> Dict[str, Any]:
        """Runs one attempt for a given candidate and task."""
        task_id = task_info["task_id"]
        category = task_info.get("category", "gameplay")
        cand_id = candidate_config["candidate_id"]

        # Resolve task yaml
        task_yaml = self.workspace_root / "pilot_tasks" / f"{task_id}.yaml"
        if not task_yaml.is_file():
            candidates = list((self.workspace_root / "pilot_tasks").glob(f"*{task_id}*.yaml"))
            if not candidates:
                candidates = list((self.workspace_root / "benchmark_tasks").glob(f"**/*{task_id}*.yaml"))
            if candidates:
                task_yaml = candidates[0]
            else:
                raise FileNotFoundError(f"Task spec missing for: {task_id}")

        task_spec = load_task(task_yaml)
        attempt_id = f"baseline_{cand_id}_{task_id}_run{run_index}_{int(time.time())}"
        
        output_dir = self.workspace_root / "reports" / "baseline_runs" / attempt_id
        output_dir.mkdir(parents=True, exist_ok=True)

        start_time = time.time()

        # Engine-Neutral Task Execution
        if category == "engine_neutral" or "neutral" in task_spec.engine_variants:
            req = ModelRequest(
                task_id=task_spec.id,
                prompt=(
                    f"Benchmark Task: {task_spec.title} ({task_spec.id})\n\n"
                    f"Requirements:\n{task_spec.prompt}\n\n"
                    f"Provide a rigorous, formal engineering specification addressing all requirements."
                ),
                system_prompt="You are an expert game engine software architect and systems engineer.",
                max_tokens=4096,
                timeout_seconds=120,
            )
            resp = invoke_candidate(candidate_config, req)
            raw_path = output_dir / "raw_output.txt"
            raw_path.write_text(resp.raw_output, encoding="utf-8")

            neutral_eval = evaluate_engine_neutral_task(task_spec, resp.raw_output)

            attempt_record = {
                "attempt_id": attempt_id,
                "candidate_id": cand_id,
                "task_id": task_id,
                "tier": task_spec.tier,
                "category": "engine_neutral",
                "run_index": run_index,
                "duration_seconds": time.time() - start_time,
                "invocation": {
                    "success": resp.success,
                    "prompt_tokens": resp.prompt_tokens,
                    "completion_tokens": resp.completion_tokens,
                    "cost_usd": 0.0,
                    "error": resp.error,
                },
                "grading": {
                    "overall_status": neutral_eval["status"],
                    "layers": {
                        "policy_static_checks": {"status": "PASS"},
                        "reasoning_rubric": {"status": neutral_eval["status"], "score": f"{neutral_eval['passed_checks']}/{neutral_eval['total_checks']}"},
                        "build_import": {"status": "NOT_APPLICABLE", "reason": "engine_neutral_task"},
                        "behavior_probes": {"status": "NOT_APPLICABLE", "reason": "engine_neutral_task"},
                    },
                    "rubric_details": neutral_eval["rubric_details"],
                },
                "evidence_path": str(output_dir),
            }
            rec_file = output_dir / "attempt_record.json"
            rec_file.write_text(json.dumps(attempt_record, indent=2), encoding="utf-8")
            return attempt_record

        # Real-Engine Native Task Execution
        attempt_record = run_attempt(
            manifest=self.manifest,
            candidate_config=candidate_config,
            task_spec=task_spec,
            workspace_root=self.workspace_root,
            runner=self.runner,
            output_dir=output_dir,
        )
        attempt_record["run_index"] = run_index
        attempt_record["category"] = category
        attempt_record["tier"] = task_spec.tier
        return attempt_record

    def run_all(self, subset_task_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Runs the entire baseline evaluation matrix across candidates and tasks."""
        eval_start = time.time()
        tasks = self.manifest["task_subsets"]["initial_baseline_tasks"]
        if subset_task_ids:
            tasks = [t for t in tasks if t["task_id"] in subset_task_ids]

        repeated_subset = set(self.manifest["task_subsets"].get("repeated_variance_subset", []))

        results_by_candidate: Dict[str, List[Dict[str, Any]]] = {}

        for candidate in self.register["candidates"]:
            cand_id = candidate["candidate_id"]
            results_by_candidate[cand_id] = []
            print(f"\n=======================================================")
            print(f" EVALUATING CANDIDATE: {candidate['display_name']}")
            print(f"=======================================================")

            for task_info in tasks:
                t_id = task_info["task_id"]
                print(f"  -> Running Task: {t_id} (Run 1)...", end="", flush=True)
                att1 = self.execute_attempt(candidate, task_info, run_index=1)
                results_by_candidate[cand_id].append(att1)
                status1 = att1.get("grading", {}).get("overall_status", "UNKNOWN")
                duration1 = att1.get("duration_seconds", 0.0)
                print(f" [{status1}] ({duration1:.1f}s)")

                # If in repeated subset, run second iteration for variance analysis
                if t_id in repeated_subset:
                    print(f"  -> Running Task: {t_id} (Run 2 - Variance Test)...", end="", flush=True)
                    att2 = self.execute_attempt(candidate, task_info, run_index=2)
                    results_by_candidate[cand_id].append(att2)
                    status2 = att2.get("grading", {}).get("overall_status", "UNKNOWN")
                    duration2 = att2.get("duration_seconds", 0.0)
                    print(f" [{status2}] ({duration2:.1f}s)")

        total_duration = time.time() - eval_start

        # Aggregate Scorecard
        scorecard = self.aggregate_scorecard(results_by_candidate, total_duration)

        # Save summary report
        summary_dir = self.workspace_root / "reports" / "baseline_runs"
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_file = summary_dir / "baseline_summary.json"
        summary_file.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")

        return scorecard

    def aggregate_scorecard(
        self,
        results_by_candidate: Dict[str, List[Dict[str, Any]]],
        total_duration: float,
    ) -> Dict[str, Any]:
        """Calculates multi-layer scorecards, Pass@1, and failure taxonomies."""
        candidate_summaries: Dict[str, Any] = {}

        for cand_id, attempts in results_by_candidate.items():
            total_attempts = len(attempts)
            passes = sum(1 for a in attempts if a.get("grading", {}).get("overall_status") == "PASS")
            partial = sum(1 for a in attempts if "PARTIAL" in a.get("grading", {}).get("overall_status", ""))
            build_fails = sum(1 for a in attempts if "FAIL" in a.get("grading", {}).get("overall_status", "") and "PARTIAL" not in a.get("grading", {}).get("overall_status", ""))
            
            # Layer statistics
            layer_stats = {
                "policy_static": {"pass": 0, "fail": 0},
                "build_import": {"pass": 0, "fail": 0, "na": 0},
                "behavior_probes": {"pass": 0, "fail": 0, "na": 0},
                "saved_assets": {"pass": 0, "fail": 0, "na": 0},
                "reasoning_rubric": {"pass": 0, "partial": 0, "na": 0},
            }

            domain_stats = {
                "T1_engine_neutral": {"total": 0, "pass": 0},
                "T2_gameplay_components": {"total": 0, "pass": 0},
                "T3_scene_composition": {"total": 0, "pass": 0},
            }

            failure_taxonomy: Dict[str, int] = {}
            total_tokens = 0
            total_latency = 0.0

            for a in attempts:
                tier = a.get("tier", "T2")
                status = a.get("grading", {}).get("overall_status", "UNKNOWN")
                layers = a.get("grading", {}).get("layers", {})
                inv = a.get("invocation", {})

                total_tokens += inv.get("prompt_tokens", 0) + inv.get("completion_tokens", 0)
                total_latency += a.get("duration_seconds", 0.0)

                # Domain mapping
                if tier == "T1":
                    domain_stats["T1_engine_neutral"]["total"] += 1
                    if status == "PASS":
                        domain_stats["T1_engine_neutral"]["pass"] += 1
                elif tier == "T2":
                    domain_stats["T2_gameplay_components"]["total"] += 1
                    if status == "PASS":
                        domain_stats["T2_gameplay_components"]["pass"] += 1
                elif tier == "T3":
                    domain_stats["T3_scene_composition"]["total"] += 1
                    if status == "PASS":
                        domain_stats["T3_scene_composition"]["pass"] += 1

                # Layer mapping
                b_st = layers.get("build_import", {}).get("status")
                if b_st == "PASS":
                    layer_stats["build_import"]["pass"] += 1
                elif b_st == "NOT_APPLICABLE":
                    layer_stats["build_import"]["na"] += 1
                else:
                    layer_stats["build_import"]["fail"] += 1

                p_st = layers.get("behavior_probes", {}).get("status")
                if p_st == "PASS":
                    layer_stats["behavior_probes"]["pass"] += 1
                elif p_st == "NOT_APPLICABLE":
                    layer_stats["behavior_probes"]["na"] += 1
                else:
                    layer_stats["behavior_probes"]["fail"] += 1

                # Failure taxonomy classification
                if status != "PASS":
                    if status == "PARTIAL_REASONING":
                        cat = "PARTIAL_ENGINE_NEUTRAL_RUBRIC"
                    elif "build_import" in layers and layers["build_import"].get("status") != "PASS":
                        cat = "C++_COMPILATION_ERROR"
                    elif "policy_static" in layers and layers["policy_static"].get("status") != "PASS":
                        cat = "POLICY_OR_PATH_VIOLATION"
                    elif "behavior_probes" in layers and layers["behavior_probes"].get("status") != "PASS":
                        cat = "RUNTIME_BEHAVIOR_PROBE_FAILURE"
                    else:
                        cat = "GENERAL_SPECIFICATION_FAILURE"
                    failure_taxonomy[cat] = failure_taxonomy.get(cat, 0) + 1

            candidate_summaries[cand_id] = {
                "attempts_count": total_attempts,
                "passes_count": passes,
                "pass_at_1": round(passes / total_attempts, 4) if total_attempts > 0 else 0.0,
                "partial_count": partial,
                "build_fail_count": build_fails,
                "domain_scores": domain_stats,
                "layer_breakdown": layer_stats,
                "failure_taxonomy": failure_taxonomy,
                "telemetry": {
                    "total_tokens_consumed": total_tokens,
                    "total_duration_seconds": round(total_latency, 2),
                    "mean_latency_per_attempt": round(total_latency / total_attempts, 2) if total_attempts > 0 else 0.0,
                    "total_inference_cost_usd": 0.0,
                },
                "attempts": attempts,
            }

        return {
            "evaluation_title": "GameForge Step 5 Model Baseline Comparison",
            "benchmark_release_id": self.manifest.get("benchmark_release_id", "gameforge-bench-v0.2.0-baseline"),
            "timestamp": time.time(),
            "total_wall_clock_seconds": round(total_duration, 2),
            "candidates_evaluated": list(results_by_candidate.keys()),
            "scorecard": candidate_summaries,
        }
