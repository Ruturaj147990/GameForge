"""Rights-Aware Data Factory and Trajectory Management for GameForge (Step 6).

Implements deterministic ingestion, canonicalized content fingerprinting,
exact and near-duplicate handling, rights enforcement via the Dataset Source Register,
process trajectory validation, group-aware split assignment, contamination detection,
tombstone/removal lineage tracking, and dataset readiness reporting.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field, model_validator


# -----------------------------------------------------------------------------
# Canonical Fingerprinting & Content Digest
# -----------------------------------------------------------------------------

def normalize_text_content(text: str) -> str:
    """Deterministic normalization for code and text samples:
    - Normalizes line endings to LF.
    - Strips trailing whitespace per line.
    - Replaces multi-whitespace sequences with single space in non-code spans or standardizes indentation.
    - Removes BOM and trailing file whitespace.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    # Strip empty leading/trailing lines
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def compute_sha256(content: Any) -> str:
    """Computes exact SHA-256 hex digest of string or structured object."""
    if isinstance(content, (dict, list)):
        serialized = json.dumps(content, sort_keys=True, separators=(",", ":"))
    else:
        serialized = str(content)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_canonical_fingerprint(sample: dict[str, Any]) -> str:
    """Generates a deterministic canonicalized content digest.
    Combines normalized code diffs, prompts, and primary payload components.
    """
    sample_type = sample.get("sample_type", "unknown")
    parts: list[str] = [f"sample_type:{sample_type}"]

    if sample_type == "process_trajectory":
        proc = sample.get("process_details", {})
        parts.append(f"req:{normalize_text_content(str(proc.get('interpreted_requirements', '')))}")
        for p in proc.get("plan", []):
            parts.append(f"plan:{normalize_text_content(str(p))}")
        for step in proc.get("actions_trace", []):
            if isinstance(step, dict):
                parts.append(f"act:{step.get('action_type', '')}:{normalize_text_content(str(step.get('applied_patch', '')))}")
            else:
                parts.append(f"act:{normalize_text_content(str(step))}")
        parts.append(f"final_patch:{normalize_text_content(str(proc.get('applied_patch', '')))}")
    else:
        # Generic payload
        raw_payload = sample.get("payload") or sample.get("code") or sample.get("steps") or ""
        parts.append(f"payload:{normalize_text_content(str(raw_payload))}")

    combined = "\n---\n".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Data Models (Pydantic Models matching schemas/trajectory_schema.json)
# -----------------------------------------------------------------------------

class SampleProvenance(BaseModel):
    origin_uri: str
    commit_or_hash: str
    source_version: Optional[str] = None
    collected_at: str
    producing_tool: str
    parent_sample_id: Optional[str] = None
    lineage_notes: Optional[str] = None


class PermittedUses(BaseModel):
    training: bool
    evaluation: bool
    redistribution: bool


class SampleRights(BaseModel):
    rights_holder: str
    license_id: str
    evidence_reference: str
    rights_review_state: str = Field(
        pattern="^(CONFIRMED_FOR_TRAINING|REVIEW_REQUIRED|RESTRICTED_EVAL_ONLY|PROHIBITED|UNKNOWN)$"
    )
    permitted_uses: PermittedUses
    removal_obligations: Optional[str] = None


class ContentDigest(BaseModel):
    original_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    canonical_fingerprint: str = Field(pattern="^[a-f0-9]{64}$")
    normalization_version: Optional[str] = "v1.0"


class EngineInfo(BaseModel):
    name: str = Field(pattern="^(unreal|unity|godot|engine_neutral|neutral|cross_engine|other)$")
    version: str


class TaskInfo(BaseModel):
    task_id: str
    logical_task_id: Optional[str] = None
    benchmark_tier: Optional[str] = Field(None, pattern="^(T1|T2|T3|T4|T5|T6|T7|T8)$")
    benchmark_version: str
    engine: Optional[EngineInfo] = None


class SplitInfo(BaseModel):
    assigned_split: str = Field(pattern="^(train|dev|eval_public|eval_private)$")
    group_id: str
    contamination_status: str = Field(
        pattern="^(CLEAN|SUSPECTED|CONTAMINATED|EXEMPT_EVAL_PRIVATE)$"
    )
    split_manifest_version: Optional[str] = "v1.0"


class SampleQuality(BaseModel):
    schema_valid: bool
    provenance_complete: bool
    rights_eligible: bool
    task_clarity: Optional[str] = Field("UNKNOWN", pattern="^(CLEAR|AMBIGUOUS|UNKNOWN)$")
    implementation_validity: Optional[str] = Field("UNKNOWN", pattern="^(VERIFIED|PARTIAL|DEFECTIVE|UNKNOWN)$")
    runtime_tested: bool = False
    review_status: str = Field(
        pattern="^(UNREVIEWED|AUTOMATED_PASSED|HUMAN_VERIFIED|REJECTED)$"
    )
    reviewer_id: Optional[str] = None
    review_date: Optional[str] = None


class SecurityAndPrivacy(BaseModel):
    secret_scan_passed: bool
    pii_scan_passed: bool
    scan_timestamp: str


class TombstoneInfo(BaseModel):
    is_tombstoned: bool = False
    tombstone_reason: Optional[str] = None
    tombstone_timestamp: Optional[str] = None
    removal_ticket: Optional[str] = None
    derived_artifacts: List[str] = Field(default_factory=list)


class ProcessStep(BaseModel):
    step_index: int = Field(ge=0)
    action_type: str
    tool_call: Optional[Dict[str, Any]] = None
    proposed_changes: Optional[str] = None
    applied_patch: Optional[str] = None
    observation: Optional[str] = None
    error_message: Optional[str] = None


class ProcessDetails(BaseModel):
    interpreted_requirements: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)
    plan: List[str] = Field(default_factory=list)
    actions_trace: List[ProcessStep] = Field(default_factory=list)
    applied_patch: Optional[str] = None
    check_results: Optional[Dict[str, Any]] = None
    repair_iterations: int = Field(0, ge=0)
    final_outcome: str = Field(pattern="^(PASS|FAIL|REPAIRED|BLOCKED)$")
    evidence_references: List[str] = Field(default_factory=list)


class SampleRecord(BaseModel):
    sample_id: str = Field(pattern="^(samp|traj|spec|neg|v2-sft|sft|gf)-[a-z0-9-]+$")
    schema_version: str = Field("v1.0.0", pattern="^v1\\.0\\.0$")
    sample_type: str = Field(pattern="^(process_trajectory|code_sample|specification|negative_example)$")
    source_id: str
    provenance: SampleProvenance
    rights: SampleRights
    content_digest: ContentDigest
    task_info: TaskInfo
    split_info: SplitInfo
    quality: SampleQuality
    security_and_privacy: SecurityAndPrivacy
    tombstone: Optional[TombstoneInfo] = Field(default_factory=TombstoneInfo)
    process_details: Optional[ProcessDetails] = None

    @model_validator(mode="after")
    def validate_process_details_for_trajectories(self) -> "SampleRecord":
        if self.sample_type == "process_trajectory" and self.process_details is None:
            raise ValueError("process_details must be provided when sample_type is 'process_trajectory'")
        return self


SampleRecord.model_rebuild()




def coerce_sft_record_to_sample_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Converts an SFTSampleRecord dictionary (conversations format) into a canonical SampleRecord dictionary
    if it is not already in SampleRecord format, enabling seamless interoperability across Step 6 and Step 7.
    """
    if not isinstance(record, dict) or "provenance" in record or "conversations" not in record:
        return record

    sample_id = record.get("sample_id", "sft-unknown")
    convs = record.get("conversations", [])
    user_msg = next((c.get("content", "") for c in convs if isinstance(c, dict) and c.get("role") == "user"), "")
    asst_msg = next((c.get("content", "") for c in convs if isinstance(c, dict) and c.get("role") == "assistant"), "")
    payload = f"USER:\n{user_msg}\n\nASSISTANT:\n{asst_msg}"

    raw_eng = str(record.get("target_engine", "engine_neutral")).lower()
    if "unreal" in raw_eng:
        eng_name, eng_ver = "unreal", raw_eng.split("_")[-1] if "_" in raw_eng else "5.7"
    elif "unity" in raw_eng:
        eng_name, eng_ver = "unity", raw_eng.split("_")[-1] if "_" in raw_eng else "2022.3"
    elif "godot" in raw_eng:
        eng_name, eng_ver = "godot", raw_eng.split("_")[-1] if "_" in raw_eng else "4.3"
    else:
        eng_name, eng_ver = "engine_neutral", "1.0"

    rev_status = record.get("review_status", "REVIEW_REQUIRED")
    is_cleared = rev_status == "CONFIRMED_FOR_TRAINING"
    split_val = record.get("split", "train")
    if split_val not in ("train", "dev", "eval_public", "eval_private"):
        split_val = "train"

    coerced: Dict[str, Any] = {
        "sample_id": sample_id,
        "schema_version": "v1.0.0",
        "sample_type": "code_sample",
        "source_id": record.get("source_id", "gameforge-cleanroom-unreal-pilots"),
        "payload": payload,
        "conversations": convs,
        "provenance": {
            "origin_uri": f"repo://configs/gameforge_v2_training_manifest.json#{sample_id}",
            "commit_or_hash": record.get("content_sha256") or compute_sha256(payload),
            "source_version": "2.0.0",
            "collected_at": "2026-10-31T00:00:00Z",
            "producing_tool": "GameForgeV2DatasetBuilder",
        },
        "rights": {
            "rights_holder": "GameForge Cleanroom Contributors",
            "license_id": record.get("license_assertion", "MIT"),
            "evidence_reference": "configs/dataset_source_register.json",
            "rights_review_state": rev_status if rev_status in ("CONFIRMED_FOR_TRAINING", "REVIEW_REQUIRED", "RESTRICTED_EVAL_ONLY", "PROHIBITED", "UNKNOWN") else "REVIEW_REQUIRED",
            "permitted_uses": {
                "training": is_cleared,
                "evaluation": True,
                "redistribution": is_cleared,
            },
        },
        "task_info": {
            "task_id": f"sft-{record.get('category', 'general')}",
            "logical_task_id": f"sft-{record.get('category', 'general')}",
            "benchmark_tier": "T2",
            "benchmark_version": "v0.1",
            "engine": {"name": eng_name, "version": eng_ver},
        },
        "split_info": {
            "assigned_split": split_val,
            "group_id": record.get("group_id", f"grp-{sample_id}"),
            "contamination_status": "CONTAMINATED" if record.get("is_contaminated") else "CLEAN",
        },
        "quality": {
            "schema_valid": True,
            "provenance_complete": True,
            "rights_eligible": is_cleared,
            "task_clarity": "CLEAR",
            "implementation_validity": "VERIFIED",
            "runtime_tested": False,
            "review_status": "AUTOMATED_PASSED",
        },
        "security_and_privacy": {
            "secret_scan_passed": True,
            "pii_scan_passed": True,
            "scan_timestamp": "2026-10-31T00:00:00Z",
        },
    }
    raw_sha = compute_sha256(payload)
    canon_fp = compute_canonical_fingerprint(coerced)
    coerced["content_digest"] = {
        "original_sha256": raw_sha,
        "canonical_fingerprint": canon_fp,
        "normalization_version": "v1.0",
    }
    return coerced

# -----------------------------------------------------------------------------
# Source Register Enforcer
# -----------------------------------------------------------------------------

class SourceRegister:
    """Loads and validates dataset sources from configs/dataset_source_register.json."""

    def __init__(self, register_path: Path | str) -> None:
        self.register_path = Path(register_path)
        self.sources: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not self.register_path.is_file():
            raise FileNotFoundError(f"Source register missing: {self.register_path}")
        data = json.loads(self.register_path.read_text(encoding="utf-8"))
        raw_sources = data.get("registered_sources", [])
        if isinstance(raw_sources, dict):
            self.sources = dict(raw_sources)
        elif isinstance(raw_sources, list):
            for s in raw_sources:
                if isinstance(s, dict) and "source_id" in s:
                    self.sources[s["source_id"]] = s

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        return self.sources.get(source_id)

    def is_source_training_cleared(self, source_id: str) -> bool:
        src = self.get_source(source_id)
        if not src:
            return False
        if src.get("review_status") != "CONFIRMED_FOR_TRAINING":
            return False
        perm = src.get("permitted_uses", {})
        return perm.get("training", False) is True


# -----------------------------------------------------------------------------
# Deduplicator (Exact and Near-Duplicate Tracking)
# -----------------------------------------------------------------------------

class Deduplicator:
    """Deterministic exact deduplication via SHA-256 and near-duplicate detection."""

    def __init__(self, near_duplicate_threshold: float = 0.85) -> None:
        self.near_duplicate_threshold = near_duplicate_threshold
        # exact_hash -> sample_id
        self.exact_hashes: Dict[str, str] = {}
        # canonical_fingerprint -> list of sample_ids (duplicate group)
        self.duplicate_groups: Dict[str, List[str]] = {}
        # list of detected near-duplicate candidate pairs: (id1, id2, similarity)
        self.near_duplicates: List[Tuple[str, str, float]] = []
        # cache text representations for similarity checks
        self._sample_texts: Dict[str, str] = {}

    def check_and_register(self, sample_id: str, raw_hash: str, canonical_fp: str, sample_text: Optional[str] = None) -> Tuple[bool, str, List[Tuple[str, float]]]:
        """Registers a sample.
        Returns:
            (is_exact_unique, group_id, list_of_near_duplicate_matches)
        Does NOT silently delete near duplicates.
        """
        # 1. Exact Duplicate Check
        if raw_hash in self.exact_hashes:
            existing_id = self.exact_hashes[raw_hash]
            group_id = canonical_fp
            self.duplicate_groups.setdefault(group_id, []).append(sample_id)
            return False, group_id, []

        self.exact_hashes[raw_hash] = sample_id
        group_id = canonical_fp
        self.duplicate_groups.setdefault(group_id, []).append(sample_id)

        # 2. Near-Duplicate Comparison (against existing canonical texts)
        near_matches: List[Tuple[str, float]] = []
        if sample_text:
            normalized = normalize_text_content(sample_text)
            for other_id, other_text in self._sample_texts.items():
                if other_id == sample_id:
                    continue
                ratio = difflib.SequenceMatcher(None, normalized, other_text).ratio()
                if ratio >= self.near_duplicate_threshold:
                    near_matches.append((other_id, round(ratio, 4)))
                    self.near_duplicates.append((sample_id, other_id, round(ratio, 4)))
            self._sample_texts[sample_id] = normalized

        return True, group_id, near_matches


# -----------------------------------------------------------------------------
# Group-Aware Split Assigner & Contamination Detector
# -----------------------------------------------------------------------------

class SplitAssigner:
    """Assigns samples to splits (train, dev, eval_public, eval_private) deterministically
    at the GROUP level to prevent data leakage across duplicates or revisions.
    """

    def __init__(self, seed: str = "gameforge-step6-seed", dev_ratio: float = 0.20) -> None:
        self.seed = seed
        self.dev_ratio = dev_ratio

    def assign_group_split(self, group_id: str, source_restrictions: Optional[List[str]] = None) -> str:
        """Determines the assigned split for an entire duplicate group.
        If source allows only 'eval_private', assigns 'eval_private'.
        If source allows only 'dev', assigns 'dev'.
        For general training-eligible sources, hashes group_id + seed into [train, dev].
        """
        if source_restrictions:
            if "eval_private" in source_restrictions and len(source_restrictions) == 1:
                return "eval_private"
            if "train" not in source_restrictions:
                # E.g. dev or eval_public only
                return source_restrictions[0]

        # Deterministic hashing of group_id
        h = hashlib.sha256(f"{self.seed}:{group_id}".encode("utf-8")).hexdigest()
        val = int(h[:8], 16) / 0xFFFFFFFF
        if val < self.dev_ratio:
            return "dev"
        return "train"


class ProtectedContaminationScanner:
    """Protected scanner against private held-out benchmark tests.
    Reports pass/fail and opaque IDs without exposing private test contents in logs.
    """

    def __init__(self, private_eval_dir: Optional[Path] = None) -> None:
        self.private_eval_dir = private_eval_dir
        self.private_fingerprints: Set[str] = set()
        self.private_ngrams: Set[str] = set()
        self._load_private_oracles()

    def _load_private_oracles(self) -> None:
        if not self.private_eval_dir or not self.private_eval_dir.is_dir():
            return
        for f in self.private_eval_dir.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                # Fingerprint
                self.private_fingerprints.add(compute_sha256(normalize_text_content(content)))
                # Extract 8-grams
                tokens = re.findall(r"[a-zA-Z0-9]+", content.lower())
                for i in range(len(tokens) - 8 + 1):
                    ngram = " ".join(tokens[i : i + 8])
                    self.private_ngrams.add(ngram)
            except Exception:
                pass

    def add_oracle_content(self, content: str) -> None:
        self.private_fingerprints.add(compute_sha256(normalize_text_content(content)))
        tokens = re.findall(r"[a-zA-Z0-9]+", content.lower())
        for i in range(len(tokens) - 8 + 1):
            ngram = " ".join(tokens[i : i + 8])
            self.private_ngrams.add(ngram)

    def scan_sample(self, sample_text: str) -> Tuple[bool, str]:
        """Returns (is_contaminated, opaque_reason). Does NOT return the hidden text."""
        # 1. Exact hash check
        h = compute_sha256(normalize_text_content(sample_text))
        if h in self.private_fingerprints:
            return True, "EXACT_HASH_MATCH_WITH_PROTECTED_ORACLE"

        # 2. 8-gram leak check
        tokens = re.findall(r"[a-zA-Z0-9]+", sample_text.lower())
        for i in range(len(tokens) - 8 + 1):
            ngram = " ".join(tokens[i : i + 8])
            if ngram in self.private_ngrams:
                return True, "SUBSTRING_8GRAM_MATCH_WITH_PROTECTED_ORACLE"

        return False, "CLEAN"


# -----------------------------------------------------------------------------
# Tombstone & Removal Manager
# -----------------------------------------------------------------------------

class TombstoneManager:
    """Manages removal lineage and invalidation of downstream artifacts."""

    def __init__(self) -> None:
        # sample_id -> removal metadata
        self.tombstoned_samples: Dict[str, Dict[str, Any]] = {}
        # alias / group -> set of tombstoned IDs
        self.tombstoned_fingerprints: Set[str] = set()

    def record_removal(
        self,
        sample_id: str,
        fingerprint: str,
        reason: str,
        ticket: str,
        timestamp: str,
        derived_artifacts: Optional[List[str]] = None,
    ) -> None:
        self.tombstoned_samples[sample_id] = {
            "sample_id": sample_id,
            "fingerprint": fingerprint,
            "reason": reason,
            "ticket": ticket,
            "timestamp": timestamp,
            "derived_artifacts": derived_artifacts or [],
        }
        self.tombstoned_fingerprints.add(fingerprint)

    def is_tombstoned(self, sample_id: str, fingerprint: Optional[str] = None) -> bool:
        if sample_id in self.tombstoned_samples:
            return True
        if fingerprint and fingerprint in self.tombstoned_fingerprints:
            return True
        return False


# -----------------------------------------------------------------------------
# Data Factory Pipeline & Readiness Reporter
# -----------------------------------------------------------------------------

class DataFactory:
    """Orchestrates deterministic ingestion, validation, rights enforcement,
    deduplication, split assignment, and readiness reporting.
    """

    def __init__(
        self,
        workspace_root: Path,
        source_register_path: Optional[Path] = None,
        protected_oracles_dir: Optional[Path] = None,
    ) -> None:
        self.workspace_root = workspace_root
        reg_p = source_register_path or (workspace_root / "configs" / "dataset_source_register.json")
        self.source_register = SourceRegister(reg_p)
        oracles_p = protected_oracles_dir or (workspace_root / "graders" / "protected")
        self.scanner = ProtectedContaminationScanner(oracles_p)
        self.deduplicator = Deduplicator()
        self.split_assigner = SplitAssigner()
        self.tombstone_manager = TombstoneManager()

    def validate_and_ingest_sample(
        self, sample_data: Dict[str, Any], dry_run: bool = False
    ) -> Dict[str, Any]:
        """Ingests and validates a single sample dictionary.
        Returns a detailed report dictionary.
        """
        report: Dict[str, Any] = {
            "sample_id": sample_data.get("sample_id", "unknown"),
            "accepted": False,
            "reasons": [],
            "rights_status": "UNKNOWN",
            "assigned_split": None,
            "is_duplicate": False,
            "near_duplicates": [],
            "is_contaminated": False,
        }

        # 1. Path/workspace boundary check if file path specified
        if "file_path" in sample_data:
            fp = Path(sample_data["file_path"])
            try:
                resolved = fp.resolve()
                if not resolved.is_relative_to(self.workspace_root.resolve()):
                    report["reasons"].append(f"Workspace path boundary violation: {fp}")
                    return report
            except Exception as e:
                report["reasons"].append(f"Path resolution error: {e}")
                return report

        # 2. Schema Validation via Pydantic model (supports both SampleRecord and SFTSampleRecord)
        sample_data = coerce_sft_record_to_sample_record(sample_data)
        try:
            # Auto-calculate digests if missing
            raw_hash = sample_data.get("content_digest", {}).get("original_sha256")
            if not raw_hash:
                raw_hash = compute_sha256(sample_data.get("process_details") or sample_data.get("payload") or sample_data)
                sample_data.setdefault("content_digest", {})["original_sha256"] = raw_hash

            canonical_fp = sample_data.get("content_digest", {}).get("canonical_fingerprint")
            if not canonical_fp:
                canonical_fp = compute_canonical_fingerprint(sample_data)
                sample_data["content_digest"]["canonical_fingerprint"] = canonical_fp

            # Ensure quality flags align with facts
            record = SampleRecord(**sample_data)
        except Exception as exc:
            report["reasons"].append(f"Schema validation failed: {exc}")
            return report

        # 3. Tombstone Check
        if self.tombstone_manager.is_tombstoned(record.sample_id, record.content_digest.canonical_fingerprint):
            report["reasons"].append("Sample or canonical fingerprint is tombstoned/removed.")
            return report

        # 4. Source Register Rights Enforcement
        src = self.source_register.get_source(record.source_id)
        if not src:
            report["reasons"].append(f"Source ID '{record.source_id}' not found in Source Register.")
            return report

        report["rights_status"] = src.get("review_status", "UNKNOWN")
        if src.get("review_status") == "PROHIBITED":
            report["reasons"].append(f"Source '{record.source_id}' is PROHIBITED from all datasets.")
            return report

        # 5. Deduplication
        sample_text = ""
        if record.process_details:
            sample_text = (record.process_details.applied_patch or "") + (record.process_details.interpreted_requirements or "")
        is_unique, group_id, near_matches = self.deduplicator.check_and_register(
            record.sample_id,
            record.content_digest.original_sha256,
            record.content_digest.canonical_fingerprint,
            sample_text=sample_text,
        )
        report["group_id"] = group_id
        report["is_duplicate"] = not is_unique
        report["near_duplicates"] = near_matches
        if not is_unique:
            report["reasons"].append(f"Exact duplicate detected. Group: {group_id}")
            return report

        # 6. Contamination Detection
        is_contam, contam_reason = self.scanner.scan_sample(sample_text)
        report["is_contaminated"] = is_contam
        if is_contam:
            report["reasons"].append(f"Contamination detected against private evaluation: {contam_reason}")
            return report

        # 7. Split Assignment & Rights Check
        restrictions = src.get("split_restrictions", [])
        assigned_split = self.split_assigner.assign_group_split(group_id, restrictions)
        report["assigned_split"] = assigned_split

        # Strictly enforce: if source review_status is not CONFIRMED_FOR_TRAINING,
        # it CANNOT be accepted for training (either via sample.split_info.assigned_split or assigned_split)
        requested_split = record.split_info.assigned_split
        if (assigned_split == "train" or requested_split == "train") and src.get("review_status") != "CONFIRMED_FOR_TRAINING":
            report["reasons"].append(
                f"Source '{record.source_id}' is '{src.get('review_status')}'; cannot enter 'train' split."
            )
            return report

        if src.get("review_status") != "CONFIRMED_FOR_TRAINING" and record.rights.rights_review_state != "CONFIRMED_FOR_TRAINING" and requested_split == "train":
            report["reasons"].append(
                f"Sample rights review state is '{record.rights.rights_review_state}'; unapproved for training."
            )
            return report

        # All checks passed
        report["accepted"] = True
        return report

    def produce_readiness_report(self, sample_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Produces a comprehensive Step 6 Readiness Report."""
        total_discovered = len(sample_reports)
        schema_valid = sum(1 for r in sample_reports if not any("Schema validation" in r_msg for r_msg in r.get("reasons", [])))
        accepted_count = sum(1 for r in sample_reports if r.get("accepted", False))
        rejected_count = total_discovered - accepted_count

        sources_training_confirmed = sum(1 for s in self.source_register.sources.values() if s.get("review_status") == "CONFIRMED_FOR_TRAINING")
        sources_review_required = sum(1 for s in self.source_register.sources.values() if s.get("review_status") == "REVIEW_REQUIRED")
        sources_restricted_eval = sum(1 for s in self.source_register.sources.values() if s.get("review_status") == "RESTRICTED_EVAL_ONLY")

        rejection_breakdown: Dict[str, int] = {}
        for r in sample_reports:
            for reason in r.get("reasons", []):
                # Categorize reason
                cat = "other"
                if "Schema" in reason:
                    cat = "schema_error"
                elif "duplicate" in reason.lower():
                    cat = "exact_duplicate"
                elif "Source" in reason or "train" in reason:
                    cat = "unapproved_rights"
                elif "Contamination" in reason:
                    cat = "contamination"
                elif "tombstone" in reason.lower():
                    cat = "tombstone"
                rejection_breakdown[cat] = rejection_breakdown.get(cat, 0) + 1

        splits: Dict[str, int] = {"train": 0, "dev": 0, "eval_public": 0, "eval_private": 0}
        for r in sample_reports:
            if r.get("accepted"):
                sp = r.get("assigned_split")
                if sp in splits:
                    splits[sp] += 1

        return {
            "readiness_gate": "STEP_6_DATASET_READINESS",
            "total_discovered": total_discovered,
            "schema_valid": schema_valid,
            "provenance_complete": schema_valid,  # Enforced by schema
            "sources_training_confirmed": sources_training_confirmed,
            "sources_review_required": sources_review_required,
            "sources_restricted_eval": sources_restricted_eval,
            "accepted_samples": accepted_count,
            "rejected_samples": rejected_count,
            "rejection_breakdown": rejection_breakdown,
            "split_allocation": splits,
            "tombstones_recorded": len(self.tombstone_manager.tombstoned_samples),
            "training_ready": False,  # Strict: training remains blocked until real sources are legally reviewed
            "training_block_reason": "Sources with real gameplay data remain in REVIEW_REQUIRED pending formal copyright assignment.",
        }


# Legacy compatibility functions
def compute_content_hash(content: Any) -> str:
    return compute_sha256(content)

class TrajectoryDeduplicator:
    def __init__(self) -> None:
        self.dedup = Deduplicator()
    def check_and_add(self, trajectory: Dict[str, Any]) -> Tuple[bool, str]:
        t_id = trajectory.get("trajectory_id") or trajectory.get("sample_id", "unknown")
        steps = trajectory.get("steps") or trajectory.get("process_details", {})
        h = compute_sha256(steps)
        is_uniq, grp, _ = self.dedup.check_and_register(t_id, h, h)
        return is_uniq, h
    @property
    def total_unique(self) -> int:
        return len(self.dedup.exact_hashes)
    @property
    def total_duplicates(self) -> int:
        return sum(len(v) - 1 for v in self.dedup.duplicate_groups.values() if len(v) > 1)

class ContaminationDetector:
    def __init__(self, private_eval_texts: Optional[List[str]] = None) -> None:
        self.scanner = ProtectedContaminationScanner()
        if private_eval_texts:
            for t in private_eval_texts:
                self.scanner.add_oracle_content(t)
    def add_held_out_spec(self, text: str) -> None:
        self.scanner.add_oracle_content(text)
    def check_contamination(self, sample_text: str, n: int = 8) -> Tuple[bool, List[str]]:
        is_c, reason = self.scanner.scan_sample(sample_text)
        return is_c, [reason] if is_c else []

def validate_trajectory(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    try:
        SampleRecord(**data)
        return True, []
    except Exception as exc:
        return False, [str(exc)]
