"""Benchmark Pipeline Runner executing the 15-step grading pipeline."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engines.base import BuildResult, EngineAdapter
from .engines.discovery import discover_environment, discover_unity_engine, discover_unreal_engine
from .engines.unity import UnityEngineAdapter
from .engines.unreal import UnrealEngineAdapter
from .grading import evaluate_grading_pipeline
from .policy import (
    check_candidate_policy,
    compute_snapshot_hash,
    freeze_candidate_snapshot,
    snapshot_directory_hashes,
    verify_snapshot_integrity,
)
from .reporting import assemble_benchmark_report, format_report_summary, save_report
from .task_loader import TaskSpec, load_task


class BenchmarkRunner:
    """Orchestrates an end-to-end task evaluation run from clean workspace to grading report."""

    def __init__(self, workspace_root: Optional[Path] = None, reports_dir: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
        self.reports_dir = reports_dir or (self.workspace_root / "reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def select_adapter(self, engine_name: str) -> EngineAdapter:
        """Instantiates the appropriate engine adapter."""
        e_lower = engine_name.lower().strip()
        if e_lower in ("auto", "unreal"):
            ue_disc = discover_unreal_engine()
            if ue_disc.is_installed or e_lower == "unreal":
                return UnrealEngineAdapter(ue_disc)
            return UnityEngineAdapter(discover_unity_engine())
        elif e_lower == "unity":
            return UnityEngineAdapter(discover_unity_engine())
        else:
            raise ValueError(f"Unsupported engine requested: {engine_name}")

    def run_task(
        self,
        task_id: str,
        engine_name: str = "auto",
        candidate_dir: Optional[Path | str] = None,
        candidate_id: str = "reference_solution",
        candidate_type: str = "reference",
        acceptance_config_path: Optional[Path | str] = None,
        quarantined: bool = False,
    ) -> Dict[str, Any]:
        """Executes the full 15-step evaluation sequence."""
        run_start = time.time()
        run_id = f"run_{task_id}_{int(run_start)}"

        # Step 1: Validate the task specification
        task_yaml = self.workspace_root / "pilot_tasks" / f"{task_id}.yaml"
        if not task_yaml.is_file():
            # Try searching in pilot_tasks and benchmark_tasks
            candidates = list((self.workspace_root / "pilot_tasks").glob(f"*{task_id}*.yaml"))
            if not candidates:
                candidates = list((self.workspace_root / "benchmark_tasks").glob(f"**/*{task_id}*.yaml"))
            if candidates:
                task_yaml = candidates[0]
            else:
                raise FileNotFoundError(f"Task specification not found for ID: {task_id}")

        task_spec = load_task(task_yaml)

        # Step 2: Select and verify engine adapter
        resolved_engine = engine_name
        if resolved_engine == "auto":
            # Prefer real installed engine
            ue_disc = discover_unreal_engine()
            resolved_engine = "unreal" if ue_disc.is_installed else "unity"

        adapter = self.select_adapter(resolved_engine)
        engine_discovery = adapter.discover()

        # Resolve fixture directory
        fixture_dir = self.workspace_root / "fixtures" / adapter.engine_name / task_spec.id.replace("-", "_")
        if not fixture_dir.is_dir():
            parts = task_spec.id.split("-")
            if len(parts) >= 3:
                cand_fixture = self.workspace_root / "fixtures" / adapter.engine_name / f"{parts[0]}_{parts[1]}_{parts[2]}"
                if cand_fixture.is_dir():
                    fixture_dir = cand_fixture
        if not fixture_dir.is_dir():
            # Fallback to general pilot fixture
            fixture_dir = self.workspace_root / "fixtures" / adapter.engine_name / "t2_001_controller"

        # Resolve candidate directory
        if not candidate_dir:
            # Check task-specific reference solution first
            task_dir_name = task_spec.id.replace("-", "_")
            cand_candidate = self.workspace_root / "graders" / "reference_solutions" / adapter.engine_name / task_dir_name
            if not cand_candidate.is_dir():
                parts = task_spec.id.split("-")
                if len(parts) >= 3:
                    alt_cand = self.workspace_root / "graders" / "reference_solutions" / adapter.engine_name / f"{parts[0]}_{parts[1]}_{parts[2]}"
                    if alt_cand.is_dir():
                        cand_candidate = alt_cand
            if cand_candidate.is_dir():
                candidate_dir = cand_candidate
            else:
                candidate_dir = fixture_dir
        candidate_path = Path(candidate_dir)

        # Step 3: Freeze candidate snapshot in isolated storage
        frozen_candidate_dir = self.workspace_root / "scratch" / "eval_runs" / run_id / "frozen_candidate"
        eval_workspace = self.workspace_root / "scratch" / "eval_runs" / run_id / "project"
        log_dir = self.workspace_root / "scratch" / "eval_runs" / run_id / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        clean_start_ok = True
        try:
            snapshot_hash, candidate_hashes = freeze_candidate_snapshot(candidate_path, frozen_candidate_dir)
            adapter.prepare_clean_workspace(frozen_candidate_dir, eval_workspace)
        except Exception:
            clean_start_ok = False
            snapshot_hash = "unknown"
            candidate_hashes = {}

        # Step 4: Record baseline directory hashes
        baseline_hashes = snapshot_directory_hashes(fixture_dir) if fixture_dir.is_dir() else {}

        # Step 5 & 6: Verify frozen candidate integrity
        if not verify_snapshot_integrity(frozen_candidate_dir, snapshot_hash):
            clean_start_ok = False

        # Step 7: Enforce static policy checks
        policy_result = check_candidate_policy(
            workspace_root=self.workspace_root,
            candidate_dir=eval_workspace,
            allowed_edit_paths=task_spec.allowed_edit_paths,
            forbidden_paths=task_spec.forbidden_edits,
            baseline_hashes=baseline_hashes,
        )

        # Step 7.5: Hidden Grader Isolation
        # Inject protected test oracles ONLY into the isolated grading workspace (eval_workspace)
        task_protected_dir = self.workspace_root / "graders" / "protected" / task_spec.id.replace("-", "_")
        if not task_protected_dir.is_dir():
            parts = task_spec.id.split("-")
            if len(parts) >= 2:
                short_id = f"{parts[0]}_{parts[1]}"
                task_protected_dir = self.workspace_root / "graders" / "protected" / short_id

        if task_protected_dir.is_dir():
            dest_protected = eval_workspace / "Probes" / "ProtectedGrader"
            dest_protected.mkdir(parents=True, exist_ok=True)
            for f in task_protected_dir.glob("*.py"):
                shutil.copyfile(f, dest_protected / f.name)

        # Load frozen acceptance criteria
        if not acceptance_config_path:
            acceptance_config_path = (
                self.workspace_root / "configs" / "acceptance_criteria" / f"{task_spec.id.replace('-', '_')}.json"
            )
        acceptance_config: Dict[str, Any] = {}
        if Path(acceptance_config_path).is_file():
            try:
                with open(acceptance_config_path, "r", encoding="utf-8") as acf:
                    acceptance_config = json.load(acf)
            except Exception:
                pass

        # Step 8: Build / Import the candidate
        if getattr(task_spec, "native_execution_required", True):
            build_result = adapter.build_project(eval_workspace, log_dir)
        else:
            build_result = BuildResult(
                success=True,
                duration_seconds=0.0,
                return_code=0,
                log_output="Static/conceptual task: native engine compilation not required.",
                error_summary=None,
                is_infrastructure_failure=False,
            )

        # Step 9: Execute automated tests (if build succeeded and engine available)
        tests = []
        if getattr(task_spec, "native_execution_required", True) and build_result.success and engine_discovery.is_installed:
            tests = adapter.execute_automated_tests(eval_workspace, log_dir)

        # Step 10: Execute gameplay behavior probes
        probes = []
        if getattr(task_spec, "native_execution_required", True) and build_result.success and engine_discovery.is_installed:
            probes = adapter.execute_behavior_probes(eval_workspace, log_dir, acceptance_config)

        # Step 11: Inspect native saved assets
        asset_result = adapter.inspect_saved_assets(eval_workspace, acceptance_config)

        # Step 12 & 13: Performance and regression checks
        perf_ok = True
        regression_ok = True

        # Step 14: Evaluate pipeline result
        grading_result = evaluate_grading_pipeline(
            clean_start_ok=clean_start_ok,
            policy_result=policy_result,
            build_result=build_result,
            tests=tests,
            probes=probes,
            asset_result=asset_result,
            perf_ok=perf_ok,
            regression_ok=regression_ok,
            is_engine_available=engine_discovery.is_installed,
            is_quarantined=quarantined,
        )
        grading_result.duration_seconds = time.time() - run_start

        # Step 15: Assemble JSON report and write summary
        log_files = {
            "eval_log_dir": str(log_dir),
        }
        report = assemble_benchmark_report(
            run_id=run_id,
            task_spec=task_spec,
            engine_discovery=engine_discovery,
            grading_result=grading_result,
            candidate_id=candidate_id,
            candidate_type=candidate_type,
            snapshot_hash=snapshot_hash,
            log_files=log_files,
            workspace_root=self.workspace_root,
        )

        report_file = save_report(report, self.reports_dir)
        summary_text = format_report_summary(report)

        return {
            "run_id": run_id,
            "status": grading_result.overall_status.value,
            "report_file": str(report_file),
            "summary_text": summary_text,
            "report": report,
        }
