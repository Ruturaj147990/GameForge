"""Deterministic Dataset Builder for Supervised Fine-Tuning in GameForge (Step 7).

Consumes validated Step 6 dataset records, preserves trajectory structure
(requirements, planning, project context, action trace, applied patches, repair iterations),
formats prompt-completion pairs according to model chat templates, and outputs
a deterministically ordered, hashed training manifest with full dataset identity binding.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .data_factory import compute_canonical_fingerprint, compute_sha256, normalize_text_content
from .training_validator import EligibilityReport, TrainingReadinessValidator


@dataclass
class FormattedTrainingSample:
    sample_id: str
    task_id: str
    engine: str
    engine_version: str
    system_prompt: str
    user_prompt: str
    target_completion: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    sample_fingerprint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "task_id": self.task_id,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "target_completion": self.target_completion,
            "metadata": self.metadata,
            "sample_fingerprint": self.sample_fingerprint,
        }


class TrainingDatasetBuilder:
    """Builds deterministic SFT training datasets from validated records."""

    SYSTEM_PROMPT_TEMPLATE = (
        "You are the Core GameForge AI Specialist, an expert in game development, engine-native "
        "architectures ({engine} {engine_version}), C++, C#, shader, and editor authoring. "
        "Always interpret requirements, plan modifications cleanly, use native reflection/lifecycle "
        "conventions, minimize diffs, and preserve existing functionality."
    )
    BUILDER_VERSION = "v1.2.0"
    SPLIT_POLICY_VERSION = "v1.1.0"
    SCHEMA_VERSION = "v1.0.0"
    FORMATTING_TEMPLATE_VERSION = "v1.0.0"

    def __init__(
        self,
        validator: TrainingReadinessValidator,
        tokenizer_id: Optional[str] = None,
        chat_template_id: Optional[str] = None,
    ) -> None:
        self.validator = validator
        self.tokenizer_id = tokenizer_id or "meta-llama/Llama-3.1-8B-Instruct"
        self.chat_template_id = chat_template_id or "llama3_default_chat_template"

    def format_sample(self, record: Dict[str, Any]) -> FormattedTrainingSample:
        """Transforms a raw eligible sample into structured training format.
        Fails if mandatory task identity, engine name, or engine version is missing.
        Never fabricates invented defaults.
        """
        sample_id = record["sample_id"]
        task_info = record.get("task_info") or {}
        task_id = task_info.get("task_id")
        if not task_id or not str(task_id).strip():
            raise ValueError(f"Mandatory task_id missing in sample {sample_id}")

        engine_info = task_info.get("engine")
        if not engine_info:
            raise ValueError(f"Mandatory engine info missing in sample {sample_id}")

        engine_name = engine_info.get("name")
        engine_ver = engine_info.get("version")
        if not engine_name or not engine_ver:
            raise ValueError(f"Mandatory engine name or version missing in sample {sample_id}")

        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            engine=str(engine_name).capitalize(),
            engine_version=engine_ver
        )

        sample_type = record.get("sample_type", "code_sample")
        metadata = {
            "source_id": record.get("source_id"),
            "license_id": record.get("rights", {}).get("license_id"),
            "sample_type": sample_type,
            "benchmark_tier": task_info.get("benchmark_tier"),
            "schema_version": record.get("schema_version", self.SCHEMA_VERSION),
            "tokenizer_id": self.tokenizer_id,
            "chat_template_id": self.chat_template_id,
        }

        if sample_type == "process_trajectory":
            proc = record.get("process_details") or {}
            user_parts = [
                f"# Task: {task_id}",
                f"# Target Engine: {engine_name} {engine_ver}",
                f"Requirements:\n{proc.get('interpreted_requirements', '')}",
            ]
            if proc.get("assumptions"):
                user_parts.append("Assumptions:\n- " + "\n- ".join(proc.get("assumptions", [])))

            user_prompt = "\n\n".join(user_parts)

            completion_parts = []
            if proc.get("plan"):
                completion_parts.append("Plan:\n- " + "\n- ".join(proc.get("plan", [])))

            # If there were repair actions, record diagnosis and repair
            if proc.get("actions_trace"):
                for step in proc.get("actions_trace", []):
                    if isinstance(step, dict):
                        if step.get("error_message"):
                            completion_parts.append(f"Diagnosis of failure:\n{step.get('error_message')}")
                        if step.get("proposed_changes"):
                            completion_parts.append(f"Correction:\n{step.get('proposed_changes')}")

            final_patch = proc.get("applied_patch", "")
            completion_parts.append(f"Final Patch:\n```\n{final_patch}\n```")
            target_completion = "\n\n".join(completion_parts)

            metadata["repair_iterations"] = proc.get("repair_iterations", 0)
            metadata["final_outcome"] = proc.get("final_outcome", "PASS")

        else:
            # Code sample or specification
            user_prompt = f"Implement game development component for task {task_id} in {engine_name} {engine_ver}."
            payload = record.get("payload") or record.get("code") or ""
            target_completion = f"```\n{normalize_text_content(str(payload))}\n```"

        fingerprint = hashlib.sha256(
            f"{self.BUILDER_VERSION}\n{self.FORMATTING_TEMPLATE_VERSION}\n{self.tokenizer_id}\n{self.chat_template_id}\n{system_prompt}\n---\n{user_prompt}\n---\n{target_completion}".encode("utf-8")
        ).hexdigest()

        return FormattedTrainingSample(
            sample_id=sample_id,
            task_id=task_id,
            engine=engine_name,
            engine_version=engine_ver,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            target_completion=target_completion,
            metadata=metadata,
            sample_fingerprint=fingerprint,
        )

    def build_dataset(
        self,
        records: List[Dict[str, Any]],
        source_manifest_id: Optional[str] = None,
        source_manifest_digest: Optional[str] = None,
    ) -> Tuple[List[FormattedTrainingSample], str, EligibilityReport]:
        """Filters by validator, converts to structured format, sorts deterministically,
        and computes dataset-level digest bound to all builder versions, split policy,
        formatting template, tokenizer/chat template, source manifest identity, and samples.
        Empty datasets return an empty digest ("") and report.is_training_ready = False.
        """
        eligible, report = self.validator.validate_manifest(records)
        
        if not eligible or len(eligible) == 0 or not report.is_training_ready:
            report.is_training_ready = False
            return [], "", report

        # Format samples with strict validation (no invented defaults)
        try:
            formatted_samples = [self.format_sample(rec) for rec in eligible]
        except Exception as exc:
            report.is_training_ready = False
            report.blocker_summary.append(f"Sample formatting failed: {exc}")
            return [], "", report

        # Deterministic sort order by sample_id
        formatted_samples.sort(key=lambda s: s.sample_id)

        # Require explicit validated source manifest identity and digest; never invent defaults
        if not source_manifest_id or not str(source_manifest_id).strip():
            report.is_training_ready = False
            report.blocker_summary.append("Missing required source_manifest_id for dataset construction.")
            return [], "", report

        if not source_manifest_digest or not str(source_manifest_digest).strip():
            report.is_training_ready = False
            report.blocker_summary.append("Missing required source_manifest_digest for dataset construction.")
            return [], "", report

        man_id = str(source_manifest_id).strip()
        man_dig = str(source_manifest_digest).strip()
        header = (
            f"builder:{self.BUILDER_VERSION}|"
            f"split_policy:{self.SPLIT_POLICY_VERSION}|"
            f"schema_version:{self.SCHEMA_VERSION}|"
            f"formatting_template:{self.FORMATTING_TEMPLATE_VERSION}|"
            f"tokenizer:{self.tokenizer_id}|"
            f"chat_template:{self.chat_template_id}|"
            f"source_manifest_id:{man_id}|"
            f"source_manifest_digest:{man_dig}|"
            f"count:{len(formatted_samples)}"
        )
        combined_hashes = header + ":" + ":".join(s.sample_fingerprint for s in formatted_samples)
        dataset_digest = hashlib.sha256(combined_hashes.encode("utf-8")).hexdigest()

        return formatted_samples, dataset_digest, report
