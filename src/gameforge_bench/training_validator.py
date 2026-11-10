"""Fail-Closed Training Readiness Validator and Split Isolation Engine for GameForge (Step 7).

Implements Section 5.5, 28.3, 28.4 and Section 30.1.3:
Enforces that a record is admitted to training iff:
- Schema and required provenance are valid.
- Source and exact intended training use are confirmed in configs/dataset_source_register.json.
- Record is not tombstoned or under pending removal.
- Deduplication and quality state meet the training policy.
- Contains no secrets or PII.
- Source and lineage do not violate evaluation split boundaries.
- Content digests (original_sha256 and canonical_fingerprint) are verified from canonical representations.
- It is NOT hidden grader content, a private held-out solution, or a derivative thereof.
- Non-approved states (REVIEW_REQUIRED, UNKNOWN, RESTRICTED_EVAL_ONLY, PROHIBITED) fail closed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .data_factory import (
    DataFactory,
    Deduplicator,
    ProtectedContaminationScanner,
    SampleRecord,
    SourceRegister,
    TombstoneManager,
    coerce_sft_record_to_sample_record,
    compute_canonical_fingerprint,
    compute_sha256,
    normalize_text_content,
)


@dataclass
class ValidationRejection:
    sample_id: str
    reason: str
    source_id: Optional[str] = None
    field_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert rejection to serializable dictionary."""
        return asdict(self)


@dataclass
class EligibilityReport:
    total_examined: int = 0
    total_eligible: int = 0
    total_rejected: int = 0
    rejections_by_reason: Dict[str, int] = field(default_factory=dict)
    admitted_sources: Dict[str, int] = field(default_factory=dict)
    rejected_sources: Dict[str, int] = field(default_factory=dict)
    split_breakdown: Dict[str, int] = field(default_factory=dict)
    pending_removals_detected: int = 0
    is_training_ready: bool = False
    blocker_summary: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_examined": self.total_examined,
            "total_eligible": self.total_eligible,
            "total_rejected": self.total_rejected,
            "rejections_by_reason": self.rejections_by_reason,
            "admitted_sources": self.admitted_sources,
            "rejected_sources": self.rejected_sources,
            "split_breakdown": self.split_breakdown,
            "pending_removals_detected": self.pending_removals_detected,
            "is_training_ready": self.is_training_ready,
            "blocker_summary": self.blocker_summary,
        }

    def format_summary(self) -> str:
        """Formats eligibility report into human-readable text."""
        lines = [
            f"Training Readiness: {'READY' if self.is_training_ready else 'NOT READY / BLOCKED'}",
            f"Examined: {self.total_examined} | Eligible: {self.total_eligible} | Rejected: {self.total_rejected}",
            f"Pending Removals / Tombstones: {self.pending_removals_detected}",
        ]
        if self.blocker_summary:
            lines.append("Blockers:")
            for b in self.blocker_summary:
                lines.append(f"  * {b}")
        if self.rejections_by_reason:
            lines.append("Rejections by Reason:")
            for r, count in sorted(self.rejections_by_reason.items(), key=lambda x: -x[1]):
                lines.append(f"  - {r}: {count}")
        return "\n".join(lines)


class TrainingReadinessValidator:
    """Enforces fail-closed training eligibility on dataset samples using canonical DataFactory rules."""

    HELD_OUT_TASK_FAMILIES = {
        "t2-008-projectile-collision",
        "t3-016-player-composition",
        "t3-017-health-hud",
        "t3-017-health-stamina-hud",
    }

    FORBIDDEN_ORIGIN_PATTERNS = [
        "graders/protected/",
        "graders/reference_solutions/",
        "private_held_out",
        "eval_private",
        "fixtures/",
    ]

    def __init__(
        self,
        source_register: SourceRegister,
        deduplicator: Optional[Deduplicator] = None,
        tombstone_manager: Optional[TombstoneManager] = None,
        contamination_scanner: Optional[ProtectedContaminationScanner] = None,
    ) -> None:
        self.source_register = source_register
        self.deduplicator = deduplicator or Deduplicator()
        self.tombstone_manager = tombstone_manager or TombstoneManager()
        self.contamination_scanner = contamination_scanner
        self.seen_sample_ids: Set[str] = set()
        self.group_to_splits: Dict[str, Set[str]] = {}

    def reset_state(self) -> None:
        """Resets deduplicator, seen sample IDs, and group-split mapping for fresh validation."""
        self.deduplicator = Deduplicator()
        self.seen_sample_ids.clear()
        self.group_to_splits.clear()

    def validate_sample_record(self, record: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates a single record against fail-closed training requirements.
        Returns (is_eligible, rejection_reason).
        """
        record = coerce_sft_record_to_sample_record(record)
        sample_id = record.get("sample_id", "unknown")

        # 0. Canonical Pydantic Schema Validation
        try:
            sample_model = SampleRecord(**record)
        except Exception as exc:
            return False, f"SCHEMA_VALIDATION_FAILED: {exc}"

        # Duplicate ID check
        if sample_model.sample_id in self.seen_sample_ids:
            return False, f"DUPLICATE_SAMPLE_ID: {sample_model.sample_id} already registered"

        # 1. Content digest verification (cross-check hashes against actual payload/patch before deduplication)
        # Verify original_sha256
        if sample_model.sample_type == "process_trajectory":
            if not sample_model.process_details:
                return False, "TRAJECTORY_MISSING_PROCESS_DETAILS"
            proc_dict = record.get("process_details") or sample_model.process_details.model_dump()
            expected_raw_sha = compute_sha256(proc_dict)
        else:
            raw_payload = record.get("payload") or record.get("code") or record.get("steps")
            if raw_payload is None:
                expected_raw_sha = compute_sha256(record)
            else:
                expected_raw_sha = compute_sha256(raw_payload)

        declared_raw_sha = sample_model.content_digest.original_sha256
        if declared_raw_sha.lower() != expected_raw_sha.lower():
            return False, f"CONTENT_DIGEST_MISMATCH: declared original_sha256 {declared_raw_sha} != recomputed {expected_raw_sha}"

        # Verify canonical_fingerprint
        expected_fp = compute_canonical_fingerprint(record)
        declared_fp = sample_model.content_digest.canonical_fingerprint
        if declared_fp.lower() != expected_fp.lower():
            return False, f"CANONICAL_FINGERPRINT_MISMATCH: declared canonical_fingerprint {declared_fp} != recomputed {expected_fp}"

        # 2. Check tombstone status (record level + TombstoneManager)
        tombstone = sample_model.tombstone
        if tombstone and tombstone.is_tombstoned:
            return False, f"TOMBSTONED: {tombstone.tombstone_reason or 'Removed by policy'}"

        if self.tombstone_manager.is_tombstoned(sample_model.sample_id, declared_fp):
            return False, f"TOMBSTONED: sample {sample_model.sample_id} or fingerprint is registered as tombstoned"

        # 3. Check source registration and rights review state
        source_id = sample_model.source_id
        src_entry = self.source_register.get_source(source_id)
        if not src_entry:
            return False, f"UNREGISTERED_SOURCE: {source_id}"

        # Check source review status in register
        src_status = src_entry.get("review_status")
        if src_status != "CONFIRMED_FOR_TRAINING":
            return False, f"UNAPPROVED_SOURCE_STATUS: {src_status} (source: {source_id})"

        # Check permitted uses in register
        perm = src_entry.get("permitted_uses", {})
        if perm.get("training") is not True:
            return False, f"TRAINING_USE_NOT_PERMITTED in source register for {source_id}"

        # Check sample-level rights
        rights = sample_model.rights
        if rights.rights_review_state != "CONFIRMED_FOR_TRAINING":
            return False, f"UNAPPROVED_SAMPLE_RIGHTS_STATE: {rights.rights_review_state}"

        training_permitted = (
            getattr(rights.permitted_uses, "training", False)
            if hasattr(rights.permitted_uses, "training")
            else (rights.permitted_uses.get("training", False) if isinstance(rights.permitted_uses, dict) else False)
        )
        if not training_permitted:
            return False, "SAMPLE_TRAINING_PERMISSION_FALSE"

        # 4. Check split boundaries and contamination
        split_info = sample_model.split_info
        if split_info.assigned_split != "train":
            return False, f"INVALID_SPLIT_FOR_TRAINING: {split_info.assigned_split}"

        if split_info.contamination_status != "CLEAN":
            return False, f"CONTAMINATION_STATUS_NOT_CLEAN: {split_info.contamination_status}"

        # 5. Check provenance and origin leakage
        provenance = sample_model.provenance
        origin_uri = provenance.origin_uri.lower()
        for forbidden in self.FORBIDDEN_ORIGIN_PATTERNS:
            if forbidden.lower() in origin_uri:
                return False, f"FORBIDDEN_EVAL_ORIGIN_LEAKAGE: {forbidden} in {origin_uri}"

        # Check lineage notes and parent sample ID for evaluation leakage
        lineage_str = f"{provenance.lineage_notes or ''} {provenance.parent_sample_id or ''}".lower()
        for forbidden in self.FORBIDDEN_ORIGIN_PATTERNS:
            if forbidden.lower() in lineage_str:
                return False, f"FORBIDDEN_LINEAGE_LEAKAGE: {forbidden} in lineage metadata"

        # 6. Check task info: must not belong to private held-out tasks
        task_info = sample_model.task_info
        if task_info.task_id in self.HELD_OUT_TASK_FAMILIES or (task_info.logical_task_id and task_info.logical_task_id.lower() in self.HELD_OUT_TASK_FAMILIES):
            return False, f"HELD_OUT_TASK_CONTAMINATION: task {task_info.task_id} is reserved for evaluation"

        # 7. Check protected contamination scanner if available
        sample_text = ""
        if sample_model.process_details:
            sample_text = (sample_model.process_details.applied_patch or "") + (sample_model.process_details.interpreted_requirements or "")
        elif "code" in record or "payload" in record:
            sample_text = str(record.get("code") or record.get("payload") or "")

        if self.contamination_scanner and sample_text:
            is_contam, contam_reason = self.contamination_scanner.scan_sample(sample_text)
            if is_contam:
                return False, f"PROTECTED_ORACLE_CONTAMINATION: {contam_reason}"

        # 8. Quality indicators
        quality = sample_model.quality
        if quality.schema_valid is not True:
            return False, "SCHEMA_VALID_FALSE"
        if quality.provenance_complete is not True:
            return False, "PROVENANCE_COMPLETE_FALSE"
        if quality.rights_eligible is not True:
            return False, "RIGHTS_ELIGIBLE_FALSE"

        # Trajectories must have verified implementation validity or pass grade
        if sample_model.sample_type == "process_trajectory":
            proc = sample_model.process_details
            if not proc:
                return False, "TRAJECTORY_MISSING_PROCESS_DETAILS"
            if proc.final_outcome not in ("PASS", "REPAIRED"):
                return False, f"UNSUCCESSFUL_TRAJECTORY_OUTCOME: {proc.final_outcome}"
            
            # Must have non-empty applied patch
            if not proc.applied_patch or not proc.applied_patch.strip():
                return False, "TRAJECTORY_MISSING_APPLIED_PATCH"

        # 9. Security & privacy
        sec = sample_model.security_and_privacy
        if sec.secret_scan_passed is not True:
            return False, "SECRET_SCAN_FAILED"
        if sec.pii_scan_passed is not True:
            return False, "PII_SCAN_FAILED"

        # 10. Deduplication check using independently verified hashes
        is_unique, group_id, near_matches = self.deduplicator.check_and_register(
            sample_model.sample_id,
            expected_raw_sha,
            expected_fp,
            sample_text=sample_text,
        )
        if not is_unique:
            return False, f"EXACT_DUPLICATE_SAMPLE: matches group {group_id}"

        # Register sample ID
        self.seen_sample_ids.add(sample_model.sample_id)
        return True, None

    def validate_manifest(self, samples: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], EligibilityReport]:
        """Scans a list of sample records and generates a machine-readable audit report.
        Enforces cross-record duplicate IDs, group/split isolation, and fatal contamination.
        """
        self.reset_state()
        report = EligibilityReport()
        report.total_examined = len(samples)
        eligible_records: List[Dict[str, Any]] = []

        if len(samples) == 0:
            report.is_training_ready = False
            report.blocker_summary.append("Empty dataset manifest: zero records provided.")
            return eligible_records, report

        # Pre-pass: check for duplicate sample IDs across the manifest
        manifest_sample_ids: Set[str] = set()
        duplicate_manifest_ids: Set[str] = set()
        for r in samples:
            sid = r.get("sample_id", "unknown")
            if sid in manifest_sample_ids:
                duplicate_manifest_ids.add(sid)
            manifest_sample_ids.add(sid)

        # Cross-record group-split mapping: check that no group_id spans both train and eval splits
        group_split_map: Dict[str, Set[str]] = {}
        for r in samples:
            grp = r.get("split_info", {}).get("group_id") or r.get("group_id")
            sp = r.get("split_info", {}).get("assigned_split") or r.get("split")
            if grp and sp:
                group_split_map.setdefault(grp, set()).add(sp)

        leaking_groups = {grp: sps for grp, sps in group_split_map.items() if len(sps) > 1 and "train" in sps and any(e in sps for e in ("eval_private", "eval_public", "dev"))}

        fatal_integrity_issue = False

        for record in samples:
            sample_id = record.get("sample_id", "unknown")
            source_id = record.get("source_id", "unknown")
            split_info = record.get("split_info") or {}
            split = split_info.get("assigned_split") or record.get("split", "unknown")
            grp_id = split_info.get("group_id") or record.get("group_id", "default")

            report.split_breakdown[split] = report.split_breakdown.get(split, 0) + 1

            tombstone = record.get("tombstone") or {}
            if tombstone.get("is_tombstoned") or self.tombstone_manager.is_tombstoned(sample_id):
                report.pending_removals_detected += 1

            # Check cross-record split leakage
            if grp_id in leaking_groups:
                report.total_rejected += 1
                reason = f"SPLIT_GROUP_LEAKAGE: group {grp_id} spans incompatible splits {list(leaking_groups[grp_id])}"
                report.rejections_by_reason["SPLIT_GROUP_LEAKAGE"] = report.rejections_by_reason.get("SPLIT_GROUP_LEAKAGE", 0) + 1
                report.rejected_sources[source_id] = report.rejected_sources.get(source_id, 0) + 1
                fatal_integrity_issue = True
                continue

            # Check duplicate ID pre-pass
            if sample_id in duplicate_manifest_ids:
                report.total_rejected += 1
                report.rejections_by_reason["DUPLICATE_SAMPLE_ID"] = report.rejections_by_reason.get("DUPLICATE_SAMPLE_ID", 0) + 1
                report.rejected_sources[source_id] = report.rejected_sources.get(source_id, 0) + 1
                continue

            is_eligible, reason = self.validate_sample_record(record)
            if is_eligible:
                report.total_eligible += 1
                report.admitted_sources[source_id] = report.admitted_sources.get(source_id, 0) + 1
                eligible_records.append(record)
            else:
                report.total_rejected += 1
                reason_key = reason.split(":")[0] if reason else "UNKNOWN"
                report.rejections_by_reason[reason_key] = report.rejections_by_reason.get(reason_key, 0) + 1
                report.rejected_sources[source_id] = report.rejected_sources.get(source_id, 0) + 1
                if "CONTAMINATION" in reason_key or "LEAKAGE" in reason_key:
                    fatal_integrity_issue = True

        # Determine readiness: fail closed if zero eligible, fatal issue, duplicate IDs, or unapproved sources
        if fatal_integrity_issue:
            report.is_training_ready = False
            report.blocker_summary.append("Manifest contains fatal split leakage, evaluation contamination, or prohibited lineage.")
            # Clear eligible records if manifest has fatal contamination/leakage
            eligible_records = []
        elif len(duplicate_manifest_ids) > 0:
            report.is_training_ready = False
            report.blocker_summary.append("Manifest contains duplicate sample IDs.")
            eligible_records = []
        elif report.total_eligible == 0:
            report.is_training_ready = False
            report.blocker_summary.append("Zero records passed fail-closed training eligibility checks.")
        elif any("UNAPPROVED" in r for r in report.rejections_by_reason):
            report.is_training_ready = False
            report.blocker_summary.append("Manifest contains records from unapproved sources.")
            eligible_records = []
        elif any("TOMBSTONED" in r for r in report.rejections_by_reason):
            report.is_training_ready = False
            report.blocker_summary.append("Manifest contains tombstoned or revoked records.")
            eligible_records = []
        else:
            report.is_training_ready = True

        return eligible_records, report

    @staticmethod
    def export_report(report: EligibilityReport, output_path: Path | str) -> Path:
        """Exports eligibility report to JSON file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)
        return out
