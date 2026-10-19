"""Training Runner, Dry-Run Verification, and Dependency Gate Enforcer for GameForge (Step 7).

Implements Section 5.1-5.6, 28.4, and Section 30.1.3:
Enforces mandatory prerequisite gates:
- Refuses training execution when Step 5 (baseline readiness) is unresolved or invalidated.
- Refuses training execution when Step 6 (data rights) has unconfirmed sources or zero eligible real records.
- Provides non-mutating dry-run validation of configuration, hardware budget, model availability, packages, and output paths.
- Enforces strict training configuration schema validation without permissive defaults.
- Verifies benchmark release identity and frozen baseline metadata.
- Formally enforces the Value-of-Training decision rule.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .data_factory import ProtectedContaminationScanner, SourceRegister, compute_canonical_fingerprint, compute_sha256
from .training_builder import FormattedTrainingSample, TrainingDatasetBuilder
from .training_validator import EligibilityReport, TrainingReadinessValidator


@dataclass
class DryRunResult:
    config_valid: bool
    packages_available: bool
    hardware_compatible: bool
    model_accessible: bool
    dataset_manifest_valid: bool
    step5_gate_passed: bool
    step6_gate_passed: bool
    can_execute_training: bool
    execution_plan: Dict[str, Any]
    blockers: List[str] = field(default_factory=list)
    resource_measurements: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValueDecisionRule:
    min_game_gain_threshold: float = 0.15
    max_general_regression_threshold: float = 0.03
    max_acceptable_vram_gb: float = 12.0
    max_acceptable_latency_increase_ratio: float = 1.30

    def evaluate_decision(
        self,
        base_game_score: float,
        adapted_game_score: float,
        base_general_score: float,
        adapted_general_score: float,
        latency_base: float,
        latency_adapted: float,
        vram_allocated_gb: Optional[float] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Evaluates the Value-of-Training decision rule strictly.
        Inputs:
            Scores must be in [0.0, 1.0].
            Latencies must be positive finite floats in seconds.
            vram_allocated_gb must be positive finite float if specified.
        Thresholds represent absolute score point differences [0.0, 1.0] (expressed in percentage points).
        Latency threshold represents relative ratio (adapted / base).
        """
        # Strict numeric validation
        scores = [base_game_score, adapted_game_score, base_general_score, adapted_general_score]
        for s in scores:
            if isinstance(s, bool) or not isinstance(s, (int, float)) or math.isnan(s) or math.isinf(s) or s < 0.0 or s > 1.0:
                raise ValueError(f"Invalid score value {s}: must be a finite float in [0.0, 1.0]")

        if isinstance(latency_base, bool) or not isinstance(latency_base, (int, float)) or math.isnan(latency_base) or math.isinf(latency_base) or latency_base <= 0.0:
            raise ValueError(f"Invalid latency_base value {latency_base}: must be a positive finite float > 0")

        if isinstance(latency_adapted, bool) or not isinstance(latency_adapted, (int, float)) or math.isnan(latency_adapted) or math.isinf(latency_adapted) or latency_adapted <= 0.0:
            raise ValueError(f"Invalid latency_adapted value {latency_adapted}: must be a positive finite float > 0")

        if vram_allocated_gb is not None:
            if isinstance(vram_allocated_gb, bool) or not isinstance(vram_allocated_gb, (int, float)) or math.isnan(vram_allocated_gb) or math.isinf(vram_allocated_gb) or vram_allocated_gb < 0.0:
                raise ValueError(f"Invalid vram_allocated_gb value {vram_allocated_gb}: must be a non-negative finite float")

        # Absolute score difference in score points [0, 1]
        game_gain_points = adapted_game_score - base_game_score
        general_regression_points = base_general_score - adapted_general_score
        latency_ratio = latency_adapted / latency_base

        metrics = {
            "base_game_score": round(base_game_score, 4),
            "adapted_game_score": round(adapted_game_score, 4),
            "game_gain_score_points": round(game_gain_points, 4),
            "game_gain_percentage_points": round(game_gain_points * 100.0, 2),
            "min_required_gain_score_points": self.min_game_gain_threshold,
            "base_general_score": round(base_general_score, 4),
            "adapted_general_score": round(adapted_general_score, 4),
            "general_regression_score_points": round(general_regression_points, 4),
            "general_regression_percentage_points": round(general_regression_points * 100.0, 2),
            "max_allowed_regression_score_points": self.max_general_regression_threshold,
            "latency_base_seconds": round(latency_base, 3),
            "latency_adapted_seconds": round(latency_adapted, 3),
            "latency_ratio": round(latency_ratio, 4),
            "max_allowed_latency_ratio": self.max_acceptable_latency_increase_ratio,
            "vram_allocated_gb": round(vram_allocated_gb, 2) if vram_allocated_gb is not None else None,
            "max_acceptable_vram_gb": self.max_acceptable_vram_gb,
            "metric_units": {
                "scores": "normalized [0.0, 1.0]",
                "gains_and_regressions": "absolute score points [0.0, 1.0]",
                "latency": "seconds",
                "latency_ratio": "relative multiplier (adapted / base)",
                "vram": "gigabytes",
            },
        }

        if vram_allocated_gb is not None and vram_allocated_gb > self.max_acceptable_vram_gb:
            return (
                False,
                f"REJECT: VRAM allocated ({vram_allocated_gb:.1f} GB) exceeds maximum budget ({self.max_acceptable_vram_gb:.1f} GB)",
                metrics,
            )

        if game_gain_points < self.min_game_gain_threshold:
            return (
                False,
                f"REJECT: Game capability gain ({game_gain_points:+.2f} score points / {game_gain_points*100.0:+.1f} percentage points) below required threshold ({self.min_game_gain_threshold:+.2f} score points)",
                metrics,
            )

        if general_regression_points > self.max_general_regression_threshold:
            return (
                False,
                f"REJECT: General reasoning regression ({general_regression_points:.2f} score points / {general_regression_points*100.0:.1f} percentage points) exceeds tolerance ({self.max_general_regression_threshold:.2f} score points)",
                metrics,
            )

        if latency_ratio > self.max_acceptable_latency_increase_ratio:
            return (
                False,
                f"REJECT: Latency increase ratio ({latency_ratio:.2f}x) exceeds threshold ({self.max_acceptable_latency_increase_ratio:.2f}x)",
                metrics,
            )

        return (
            True,
            f"ACCEPT: Significant held-out game capability gain ({game_gain_points*100.0:+.1f} percentage points) with general reasoning regression within tolerance ({general_regression_points*100.0:.1f} percentage points) and latency ratio {latency_ratio:.2f}x.",
            metrics,
        )


class TrainingRunner:
    """Manages Step 7 training pipeline, pre-execution gates, and non-mutating dry-run auditing."""

    def __init__(self, workspace_root: Path, config_path: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.config_path = config_path.resolve() if config_path.is_absolute() else (workspace_root / config_path).resolve()
        self.config_data = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.is_file():
            raise FileNotFoundError(f"Training configuration not found: {self.config_path}")
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def validate_configuration_syntax(self) -> Tuple[bool, List[str]]:
        """Validates configuration comprehensively against schemas/training_config_schema.json
        and applies strict semantic validation (rejecting booleans as ints/floats, non-finite numbers, etc.).
        """
        blockers: List[str] = []

        if not isinstance(self.config_data, dict):
            return False, ["Configuration root must be a JSON object"]

        schema_file = self.workspace_root / "schemas" / "training_config_schema.json"
        if not schema_file.is_file():
            blockers.append("schemas/training_config_schema.json is missing.")
            return False, blockers

        try:
            schema_data = json.loads(schema_file.read_text(encoding="utf-8"))
        except Exception as exc:
            blockers.append(f"Failed to read/parse schemas/training_config_schema.json: {exc}")
            return False, blockers

        # Strict JSON Schema validation across the complete structure
        def _validate_json_schema(instance: Any, schema: Dict[str, Any], path: str = "root") -> List[str]:
            errs: List[str] = []
            expected_type = schema.get("type")

            if expected_type == "object":
                if not isinstance(instance, dict) or isinstance(instance, bool):
                    return [f"{path}: expected object, got {type(instance).__name__}"]
                for req_key in schema.get("required", []):
                    if req_key not in instance:
                        errs.append(f"{path}: missing required field '{req_key}'")
                props = schema.get("properties", {})
                for k, v in instance.items():
                    if k in props:
                        errs.extend(_validate_json_schema(v, props[k], path=f"{path}.{k}"))
            elif expected_type == "array":
                if not isinstance(instance, list) or isinstance(instance, bool):
                    return [f"{path}: expected array, got {type(instance).__name__}"]
                items_schema = schema.get("items")
                if items_schema:
                    for idx, item in enumerate(instance):
                        errs.extend(_validate_json_schema(item, items_schema, path=f"{path}[{idx}]"))
            elif expected_type == "string":
                if not isinstance(instance, str):
                    errs.append(f"{path}: expected string, got {type(instance).__name__}")
                elif "enum" in schema and instance not in schema["enum"]:
                    errs.append(f"{path}: value '{instance}' not in allowed enum {schema['enum']}")
            elif expected_type == "integer":
                if isinstance(instance, bool) or not isinstance(instance, int):
                    errs.append(f"{path}: expected integer, got {type(instance).__name__}")
            elif expected_type == "number":
                if isinstance(instance, bool) or not isinstance(instance, (int, float)) or math.isnan(instance) or math.isinf(instance):
                    errs.append(f"{path}: expected finite number, got {instance}")
            elif expected_type == "boolean":
                if not isinstance(instance, bool):
                    errs.append(f"{path}: expected boolean, got {type(instance).__name__}")

            return errs

        schema_errors = _validate_json_schema(self.config_data, schema_data)
        blockers.extend(schema_errors)

        if blockers:
            return False, blockers

        # Additional domain semantic validation
        # 1. Base model validation
        bm = self.config_data.get("base_model", {})
        for k in ["candidate_id", "model_name", "immutable_revision", "license"]:
            val = bm.get(k)
            if not isinstance(val, str) or not val.strip():
                blockers.append(f"base_model missing or invalid required string field: '{k}'")
        if "context_window" in bm:
            cw = bm["context_window"]
            if isinstance(cw, bool) or not isinstance(cw, int) or cw <= 0:
                blockers.append(f"Invalid context_window: {cw} (must be positive integer)")

        # 2. Hyperparameters
        hp = self.config_data.get("hyperparameters", {})
        lr = hp.get("learning_rate")
        if lr is not None:
            if isinstance(lr, bool) or not isinstance(lr, (int, float)) or math.isnan(lr) or math.isinf(lr) or lr <= 0:
                blockers.append(f"Invalid hyperparameter 'learning_rate': {lr} (must be positive finite number)")
        for int_k in ["batch_size", "gradient_accumulation_steps", "epochs", "seed"]:
            ival = hp.get(int_k)
            if ival is not None:
                if isinstance(ival, bool) or not isinstance(ival, int) or ival <= 0:
                    blockers.append(f"Invalid hyperparameter '{int_k}': {ival} (must be positive integer)")

        # 3. Resource budget
        rb = self.config_data.get("resource_budget", {})
        vram = rb.get("max_vram_gb")
        if vram is not None:
            if isinstance(vram, bool) or not isinstance(vram, (int, float)) or math.isnan(vram) or math.isinf(vram) or vram <= 0:
                blockers.append(f"Invalid resource_budget 'max_vram_gb': {vram} (must be positive finite number)")
        disk = rb.get("max_disk_gb")
        if disk is not None:
            if isinstance(disk, bool) or not isinstance(disk, (int, float)) or math.isnan(disk) or math.isinf(disk) or disk <= 0:
                blockers.append(f"Invalid resource_budget 'max_disk_gb': {disk} (must be positive finite number)")

        # 4. Evaluation manifest
        em = self.config_data.get("evaluation_manifest", {})
        if not isinstance(em.get("frozen_manifest_id"), str) or not em.get("frozen_manifest_id", "").strip():
            blockers.append("evaluation_manifest 'frozen_manifest_id' must be non-empty string")
        if not isinstance(em.get("held_out_tasks"), list) or len(em.get("held_out_tasks", [])) == 0:
            blockers.append("evaluation_manifest 'held_out_tasks' must be a non-empty list of task IDs")
        if not isinstance(em.get("general_reasoning_tasks"), list) or len(em.get("general_reasoning_tasks", [])) == 0:
            blockers.append("evaluation_manifest 'general_reasoning_tasks' must be a non-empty list of task IDs")

        # 5. Stopping criteria
        sc = self.config_data.get("stopping_criteria", {})
        for k in ["min_game_gain_threshold", "max_general_regression_threshold"]:
            v = sc.get(k)
            if v is not None:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v) or v <= 0:
                    blockers.append(f"Invalid stopping_criteria '{k}': {v} (must be positive finite number)")

        return len(blockers) == 0, blockers

    def check_prerequisite_gates(self) -> Tuple[bool, bool, List[str]]:
        """Audits Step 5 baseline readiness and Step 6 rights clearance strictly fail-closed
        using structured records, authoritative digest verification, reconciliation audit consistency,
        and single-source-of-truth dataset validation.
        """
        blockers: List[str] = []

        # Step 5 Audit Check: inspect structured milestone records and formal reconciliation audit
        step5_passed = False
        step5_record_file = self.workspace_root / "configs" / "step5_acceptance_record.json"
        roadmap_file = self.workspace_root / "GAMEFORGE_ROADMAP.csv"
        reconciliation_audit_file = self.workspace_root / "STEP5_RECONCILIATION_AUDIT.md"

        if step5_record_file.is_file():
            try:
                rec_data = json.loads(step5_record_file.read_text(encoding="utf-8"))

                # 1. Validate acceptance record against formal schema requirements
                schema_file = self.workspace_root / "schemas" / "step5_acceptance_schema.json"
                if schema_file.is_file():
                    try:
                        s5_schema = json.loads(schema_file.read_text(encoding="utf-8"))
                        req_fields = s5_schema.get("required", [])
                        for rf in req_fields:
                            if rf not in rec_data:
                                blockers.append(f"Step 5 Gate BLOCKED: acceptance record missing required schema field '{rf}'")
                    except Exception as se:
                        blockers.append(f"Step 5 Gate BLOCKED: failed to parse step5_acceptance_schema.json: {se}")
                else:
                    blockers.append("Step 5 Gate BLOCKED: schemas/step5_acceptance_schema.json is missing.")

                acceptance_state = rec_data.get("acceptance_status")
                model_id = rec_data.get("accepted_model_id")
                immutable_rev = rec_data.get("immutable_revision")
                frozen_manifest = rec_data.get("frozen_benchmark_manifest_id")
                manifest_digest = rec_data.get("benchmark_manifest_digest")
                evidence_files = rec_data.get("evidence_files", [])
                run_ids = rec_data.get("referenced_baseline_run_ids", [])
                audit_rel = rec_data.get("reconciliation_audit_file", "STEP5_RECONCILIATION_AUDIT.md")
                audit_path = self.workspace_root / audit_rel

                if acceptance_state != "ACCEPTED":
                    blockers.append(
                        f"Step 5 Gate BLOCKED: Step 5 acceptance record status is '{acceptance_state}' (must be 'ACCEPTED')."
                    )

                # Reconcile configured base model with accepted baseline model
                cfg_bm = self.config_data.get("base_model", {})
                if model_id and cfg_bm.get("candidate_id") != model_id:
                    blockers.append(
                        f"Step 5 Gate BLOCKED: Accepted model ID '{model_id}' does not match configured base_model candidate '{cfg_bm.get('candidate_id')}'."
                    )
                if immutable_rev and cfg_bm.get("immutable_revision") != immutable_rev:
                    blockers.append(
                        f"Step 5 Gate BLOCKED: Accepted immutable revision '{immutable_rev}' does not match configured revision '{cfg_bm.get('immutable_revision')}'."
                    )

                # Reconcile frozen benchmark release
                cfg_eval = self.config_data.get("evaluation_manifest", {})
                if frozen_manifest and cfg_eval.get("frozen_manifest_id") != frozen_manifest:
                    blockers.append(
                        f"Step 5 Gate BLOCKED: Accepted benchmark manifest ID '{frozen_manifest}' does not match configured evaluation manifest '{cfg_eval.get('frozen_manifest_id')}'."
                    )

                # Verify reconciliation audit file existence and contents
                if not audit_path.is_file():
                    blockers.append(f"Step 5 Gate BLOCKED: Mandatory reconciliation audit file '{audit_rel}' missing.")
                else:
                    audit_text = audit_path.read_text(encoding="utf-8")
                    if "INVALIDATED_PENDING_REVIEW" in audit_text or "STEP5 FAIL" in audit_text:
                        blockers.append(
                            f"Step 5 Gate BLOCKED: {audit_rel} registers historical baseline runs as INVALIDATED_PENDING_REVIEW / STEP5 FAIL."
                        )

                # Verify each referenced evidence object (schema, nonzero size, content digest)
                if not evidence_files or len(evidence_files) == 0:
                    blockers.append("Step 5 Gate BLOCKED: evidence_files is empty.")
                else:
                    for ev in evidence_files:
                        if isinstance(ev, str):
                            ev_path = self.workspace_root / ev
                            ev_expected_sha = None
                            ev_type = "run_report"
                        elif isinstance(ev, dict):
                            ev_path = self.workspace_root / ev.get("path", "")
                            ev_expected_sha = ev.get("expected_digest_sha256")
                            ev_type = ev.get("evidence_type", "run_report")
                        else:
                            blockers.append(f"Step 5 Gate BLOCKED: malformed evidence item: {ev}")
                            continue

                        if not ev_path.is_file():
                            blockers.append(f"Step 5 Gate BLOCKED: evidence file missing: {ev_path}")
                            continue

                        if ev_path.stat().st_size == 0:
                            blockers.append(f"Step 5 Gate BLOCKED: evidence file is empty (0 bytes): {ev_path}")
                            continue

                        try:
                            ev_bytes = ev_path.read_bytes()
                            ev_actual_sha = hashlib.sha256(ev_bytes).hexdigest()
                            if ev_expected_sha and ev_actual_sha.lower() != ev_expected_sha.lower():
                                blockers.append(
                                    f"Step 5 Gate BLOCKED: evidence digest mismatch for {ev_path.name}: expected {ev_expected_sha}, computed {ev_actual_sha}"
                                )

                            ev_json = json.loads(ev_bytes.decode("utf-8"))
                            if not isinstance(ev_json, dict) or len(ev_json) == 0:
                                blockers.append(f"Step 5 Gate BLOCKED: evidence file {ev_path.name} contains empty JSON object {{}} (placeholder rejected).")
                            else:
                                # Reconcile run status and patch counts
                                if ev_type == "run_report":
                                    patches_applied = ev_json.get("candidate", {}).get("patches_applied_count", ev_json.get("patches_applied_count"))
                                    if patches_applied == 0 and ev_json.get("status") == "PASS":
                                        blockers.append(
                                            f"Step 5 Gate BLOCKED: evidence {ev_path.name} reports PASS with 0 applied patches (invalidated fixture-only run)."
                                        )
                        except Exception as ee:
                            blockers.append(f"Step 5 Gate BLOCKED: failed to parse/validate evidence {ev_path.name}: {ee}")

                if len(blockers) == 0 and acceptance_state == "ACCEPTED":
                    step5_passed = True

            except Exception as e:
                blockers.append(f"Step 5 Gate BLOCKED: Failed to parse step5_acceptance_record.json: {e}")
        else:
            # Fall back to roadmap inspection if structured record is absent
            if roadmap_file.is_file():
                content = roadmap_file.read_text(encoding="utf-8")
                if "STEP5 FAIL" in content or "INVALIDATED_PENDING_REVIEW" in content:
                    blockers.append(
                        "Step 5 Gate BLOCKED: Milestone ledger registers Step 5 as INVALIDATED_PENDING_REVIEW due to historical zero-applied-patch anomaly; clean retest pending."
                    )
                else:
                    blockers.append(
                        "Step 5 Gate BLOCKED: Formal structured Step 5 acceptance record (configs/step5_acceptance_record.json) missing."
                    )
            else:
                blockers.append("Step 5 Gate BLOCKED: GAMEFORGE_ROADMAP.csv missing.")

        # Step 6 Audit Check: derived from the SAME authoritative dataset evaluation operation
        step6_passed, ds_details = self._evaluate_authoritative_dataset()
        if not step6_passed:
            for b in ds_details.get("blockers", []):
                blockers.append(f"Step 6 Gate BLOCKED: {b}")

        return step5_passed, step6_passed, blockers

    def check_packages(self) -> Tuple[bool, List[str]]:
        missing: List[str] = []
        try:
            import torch
        except ImportError:
            missing.append("torch")

        try:
            import transformers
        except ImportError:
            missing.append("transformers")

        try:
            import peft
        except ImportError:
            missing.append("peft")

        return (len(missing) == 0), missing

    def check_model_artifact(self) -> Tuple[bool, List[str]]:
        """Verifies that the requested model candidate is registered, has approved license,
        and is compatible with the selected training framework.
        """
        blockers: List[str] = []
        base_model_info = self.config_data.get("base_model", {})
        cand_id = base_model_info.get("candidate_id")
        training_method = self.config_data.get("training_method", "lora")

        model_register_file = self.workspace_root / "configs" / "model_register.json"
        if not model_register_file.is_file():
            return False, ["configs/model_register.json missing."]

        reg_data = json.loads(model_register_file.read_text(encoding="utf-8"))
        candidate = next((c for c in reg_data.get("candidates", []) if c.get("candidate_id") == cand_id), None)
        if not candidate:
            return False, [f"Candidate '{cand_id}' not registered in configs/model_register.json"]

        # Check license confirmation
        if not candidate.get("license_verified"):
            blockers.append(f"Candidate '{cand_id}' license is not verified for training.")

        # Check framework compatibility: Ollama local service tag vs PEFT/Transformers weights
        provider = candidate.get("provider")
        if provider == "ollama" and training_method in ("lora", "qlora", "sft_full"):
            blockers.append(
                f"Model candidate '{cand_id}' is deployed via Ollama local runtime. PEFT/Transformers LoRA requires local HuggingFace/Safetensors PyTorch weights; Ollama model tag cannot be directly fine-tuned with PEFT."
            )

        return len(blockers) == 0, blockers

    def _evaluate_authoritative_dataset(self) -> Tuple[bool, Dict[str, Any]]:
        """Single authoritative dataset validation operation consumed by both
        Step 6 gate checking and check_dataset_readiness.
        Enforces:
        - Manifest file existence and typed root parsing.
        - Mandatory protected contamination scanner wired to graders/protected.
        - Strict non-empty real eligible records (rejecting pure test-only synthetic fixtures).
        - Source register clearance and intended use permissions.
        - Source manifest digest and constructed dataset digest derivation.
        """
        details: Dict[str, Any] = {
            "manifest_valid": False,
            "manifest_identity": "",
            "total_records": 0,
            "eligible_records_count": 0,
            "real_eligible_records_count": 0,
            "source_manifest_digest": "",
            "constructed_dataset_digest": "",
            "blockers": [],
        }

        ds_info = self.config_data.get("dataset", {})
        manifest_rel = ds_info.get("manifest_path")
        if not manifest_rel:
            details["blockers"].append("No manifest_path declared in training configuration.")
            return False, details

        manifest_path = self.workspace_root / manifest_rel
        details["manifest_identity"] = manifest_rel

        if not manifest_path.is_file():
            details["blockers"].append(f"Dataset manifest does not exist at {manifest_path} (cannot train on missing manifest).")
            return False, details

        try:
            raw_manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest_content = json.loads(raw_manifest_text)

            # Require correct root type: must be dict with 'samples' or list of records
            if isinstance(manifest_content, dict):
                if "samples" in manifest_content and isinstance(manifest_content["samples"], list):
                    records = manifest_content["samples"]
                else:
                    details["blockers"].append("Dataset manifest object root missing 'samples' array.")
                    return False, details
            elif isinstance(manifest_content, list):
                records = manifest_content
            else:
                details["blockers"].append(f"Dataset manifest root has invalid type '{type(manifest_content).__name__}' (must be object or list).")
                return False, details

            details["total_records"] = len(records)
            if len(records) == 0:
                details["blockers"].append("Dataset manifest contains 0 records (empty dataset is untrainable).")
                return False, details

            # Source register check
            src_reg_path = self.workspace_root / ds_info.get("source_register_path", "configs/dataset_source_register.json")
            if not src_reg_path.is_file():
                details["blockers"].append(f"Source register missing at {src_reg_path}")
                return False, details

            src_reg = SourceRegister(src_reg_path)

            # Mandatory Protected Contamination Scanner initialization
            oracles_dir = self.workspace_root / "graders" / "protected"
            scanner = ProtectedContaminationScanner(private_eval_dir=oracles_dir)

            # Authoritative TrainingReadinessValidator with mandatory scanner
            validator = TrainingReadinessValidator(
                source_register=src_reg,
                contamination_scanner=scanner,
            )

            # Compute source manifest digest
            source_manifest_digest = hashlib.sha256(raw_manifest_text.encode("utf-8")).hexdigest()
            details["source_manifest_digest"] = source_manifest_digest

            builder = TrainingDatasetBuilder(validator)
            formatted, constructed_digest, rep = builder.build_dataset(
                records,
                source_manifest_id=manifest_rel,
                source_manifest_digest=source_manifest_digest,
            )

            details["eligible_records_count"] = rep.total_eligible
            details["constructed_dataset_digest"] = constructed_digest

            # Count real gameplay records (exclude synthetic test corpus)
            real_eligible = [
                r for r in formatted
                if r.metadata.get("source_id") != "gameforge-synthetic-test-corpus"
            ]
            details["real_eligible_records_count"] = len(real_eligible)

            if not rep.is_training_ready or rep.total_eligible == 0:
                details["blockers"].extend(rep.blocker_summary)

            if len(real_eligible) == 0:
                details["blockers"].append(
                    "Zero real gameplay records eligible for training (synthetic test-only corpus cannot authorize production training)."
                )

            # Compare declared constructed dataset digest if specified
            declared_digest = ds_info.get("manifest_digest", "")
            if declared_digest and constructed_digest != declared_digest:
                details["blockers"].append(
                    f"Dataset manifest digest mismatch: declared {declared_digest}, computed {constructed_digest}"
                )

            is_ready = len(details["blockers"]) == 0 and len(real_eligible) > 0
            details["manifest_valid"] = is_ready
            return is_ready, details

        except Exception as exc:
            details["blockers"].append(f"Failed to read/validate dataset manifest: {exc}")
            return False, details

    def check_dataset_readiness(self) -> Tuple[bool, List[str]]:
        """Verifies dataset manifest presence, digest integrity, and non-empty eligible records
        using the authoritative dataset evaluation operation.
        """
        is_ready, details = self._evaluate_authoritative_dataset()
        return is_ready, details.get("blockers", [])

    def check_hardware_and_resources(self) -> Tuple[bool, Dict[str, Any], List[str]]:
        """Non-mutating measurement of actual system resources (RAM, disk space, PyTorch GPU acceleration).
        Never creates output directories during dry-run preflight.
        """
        blockers: List[str] = []
        measurements: Dict[str, Any] = {}

        # 1. Non-mutating disk space check: resolve nearest existing ancestor
        out_rel = self.config_data.get("resource_budget", {}).get("output_dir", "artifacts/training_checkpoints")
        out_path = self.workspace_root / out_rel
        try:
            # Find nearest existing ancestor without creating directories
            curr = out_path
            while not curr.exists() and curr != curr.parent:
                curr = curr.parent

            if not curr.exists():
                blockers.append(f"Cannot resolve filesystem for output_dir: {out_path}")
            else:
                total, used, free = shutil.disk_usage(curr)
                free_gb = free / (1024 ** 3)
                measurements["disk_free_gb"] = round(free_gb, 2)
                required_disk = self.config_data.get("resource_budget", {}).get("max_disk_gb", 5.0)
                if free_gb < required_disk:
                    blockers.append(f"Insufficient disk space: {free_gb:.1f} GB available, {required_disk:.1f} GB required.")
        except Exception as e:
            measurements["disk_error"] = str(e)
            blockers.append(f"Failed to measure disk space: {e}")

        # 2. Host RAM check
        try:
            import psutil
            mem = psutil.virtual_memory()
            free_ram_gb = mem.available / (1024 ** 3)
            measurements["host_ram_free_gb"] = round(free_ram_gb, 2)
            measurements["host_ram_total_gb"] = round(mem.total / (1024 ** 3), 2)
        except Exception as e:
            measurements["ram_error"] = str(e)
            blockers.append(f"Failed to measure host RAM: {e}")

        # 3. GPU / PyTorch Backend check
        req_device = self.config_data.get("resource_budget", {}).get("device", "unknown")
        try:
            import torch
            measurements["torch_version"] = torch.__version__
            measurements["cuda_available"] = torch.cuda.is_available()
            measurements["device_name"] = req_device
            # Check requested backend compatibility
            req_lower = req_device.lower()
            needs_gpu = any(tok in req_lower for tok in ("cuda", "rocm", "gpu", "radeon", "nvidia"))
            if needs_gpu and not torch.cuda.is_available():
                measurements["hardware_status"] = "GPU_UNAVAILABLE"
                blockers.append(
                    f"Requested compute backend requires GPU acceleration ('{req_device}'), but active PyTorch build '{torch.__version__}' has cuda.is_available() = False."
                )
            elif not torch.cuda.is_available() and "+cpu" in torch.__version__:
                measurements["hardware_status"] = "CPU_ONLY_TORCH"
                blockers.append(
                    f"PyTorch build '{torch.__version__}' is CPU-only; ROCm GPU acceleration unavailable for device '{req_device}'."
                )
        except ImportError:
            measurements["torch"] = "NOT_INSTALLED"
            blockers.append("PyTorch is not installed.")

        hardware_ok = len(blockers) == 0
        return hardware_ok, measurements, blockers

    def check_benchmark_version_integrity(self) -> Tuple[bool, List[str]]:
        """Verifies that the configured benchmark manifest matches the frozen baseline
        and confirms version/digest reconciliation across tasks, schemas, and reports.
        """
        blockers: List[str] = []
        eval_cfg = self.config_data.get("evaluation_manifest", {})
        frozen_id = eval_cfg.get("frozen_manifest_id")

        baseline_manifest_file = self.workspace_root / "configs" / "baseline_release_manifest.json"
        if baseline_manifest_file.is_file():
            try:
                manifest_raw = baseline_manifest_file.read_text(encoding="utf-8")
                base_man = json.loads(manifest_raw)
                expected_id = base_man.get("benchmark_release_id")
                base_ver = base_man.get("version")

                # Verify mandatory frozen release metadata fields
                for rf in ["benchmark_release_id", "version", "status", "governing_strategy", "task_subsets", "candidate_protocol"]:
                    if rf not in base_man:
                        blockers.append(f"Baseline release manifest missing mandatory field: '{rf}'")

                if base_man.get("status") != "FROZEN":
                    blockers.append(f"Baseline release manifest status is '{base_man.get('status')}' (must be 'FROZEN').")

                if frozen_id != expected_id:
                    blockers.append(
                        f"Benchmark manifest ID mismatch: training config declares '{frozen_id}', but baseline manifest is '{expected_id}'"
                    )

                # Check tasks in baseline manifest
                tasks = base_man.get("task_subsets", {}).get("initial_baseline_tasks", [])
                if len(tasks) == 0:
                    blockers.append("Baseline release manifest contains zero baseline tasks.")

                # Ensure held-out tasks in evaluation_manifest match baseline private tasks
                declared_held_out = set(eval_cfg.get("held_out_tasks", []))
                private_baseline_tasks = {t["task_id"] for t in tasks if t.get("split") == "private_held_out"}
                if not declared_held_out.issubset(private_baseline_tasks):
                    mismatched = declared_held_out - private_baseline_tasks
                    blockers.append(
                        f"Evaluation manifest declared held-out tasks {mismatched} not configured as private_held_out in baseline manifest."
                    )

            except Exception as e:
                blockers.append(f"Failed to parse configs/baseline_release_manifest.json: {e}")
        else:
            blockers.append("configs/baseline_release_manifest.json missing.")

        return len(blockers) == 0, blockers

    def dry_run(self) -> DryRunResult:
        """Executes a full preflight audit without modifying weights, creating directories,
        or launching GPU training. All fields are dynamically derived from actual checks.
        """
        blockers: List[str] = []

        # 1. Config syntax validation
        config_valid, cfg_blockers = self.validate_configuration_syntax()
        blockers.extend(cfg_blockers)

        # 2. Package availability
        pkgs_ok, missing_pkgs = self.check_packages()
        if not pkgs_ok:
            blockers.append(f"Missing required training packages: {', '.join(missing_pkgs)}")

        # 3. Model artifact compatibility
        model_ok, model_blockers = self.check_model_artifact()
        blockers.extend(model_blockers)

        # 4. Dataset readiness
        dataset_ok, dataset_blockers = self.check_dataset_readiness()
        blockers.extend(dataset_blockers)

        # 5. Hardware & resource check (non-mutating)
        hw_ok, res_measurements, hw_blockers = self.check_hardware_and_resources()
        blockers.extend(hw_blockers)

        # 6. Benchmark release manifest reconciliation
        bench_ok, bench_blockers = self.check_benchmark_version_integrity()
        blockers.extend(bench_blockers)

        # 7. Prerequisite gates (Step 5 and Step 6)
        s5_ok, s6_ok, gate_blockers = self.check_prerequisite_gates()
        blockers.extend(gate_blockers)

        can_execute = (
            config_valid
            and pkgs_ok
            and model_ok
            and dataset_ok
            and hw_ok
            and bench_ok
            and s5_ok
            and s6_ok
        )

        base_model_info = self.config_data.get("base_model", {})
        execution_plan = {
            "experiment_id": self.config_data.get("experiment_id"),
            "base_model": base_model_info.get("model_name"),
            "revision": base_model_info.get("immutable_revision"),
            "training_method": self.config_data.get("training_method"),
            "adapter_params": self.config_data.get("adapter_config"),
            "hyperparameters": self.config_data.get("hyperparameters"),
            "device": self.config_data.get("resource_budget", {}).get("device"),
            "output_dir": self.config_data.get("resource_budget", {}).get("output_dir"),
            "value_decision_rule": self.config_data.get("stopping_criteria"),
            "status": "READY_FOR_EXECUTION" if can_execute else "GATED_AND_BLOCKED",
        }

        return DryRunResult(
            config_valid=config_valid,
            packages_available=pkgs_ok,
            hardware_compatible=hw_ok,
            model_accessible=model_ok,
            dataset_manifest_valid=dataset_ok,
            step5_gate_passed=s5_ok,
            step6_gate_passed=s6_ok,
            can_execute_training=can_execute,
            execution_plan=execution_plan,
            blockers=blockers,
            resource_measurements=res_measurements,
        )

    def execute_training(self) -> Dict[str, Any]:
        """Attempts training execution, failing closed if gates or packages are unresolved.
        Guarantees ZERO mutation to weights or checkpoint directories when blocked.
        """
        dry_run_res = self.dry_run()
        if not dry_run_res.can_execute_training:
            return {
                "success": False,
                "status": "EXECUTION_REFUSED_FAIL_CLOSED",
                "message": "Training execution blocked by mandatory prerequisite gates and readiness checks.",
                "blockers": dry_run_res.blockers,
                "dry_run": asdict(dry_run_res),
            }

        # If ever authorized and prerequisites met, an authorized executor is required:
        # We do not return TRAINING_COMPLETED without verified execution evidence!
        return {
            "success": False,
            "status": "TRAINING_EXECUTOR_UNAVAILABLE",
            "message": "Prerequisites satisfied but genuine training executor is not configured or authorized.",
        }
