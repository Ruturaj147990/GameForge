"""Task loader and normalization for GameForge benchmark specifications."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field, ValidationError


class TaskLimits(BaseModel):
    wall_clock_seconds: int = 1800
    max_tool_calls: int = 100
    max_model_tokens: Optional[int] = None
    network_access: str = "disabled"


class TaskPermissions(BaseModel):
    allowed_edit_paths: List[str] = Field(default_factory=list)
    forbidden_paths: List[str] = Field(default_factory=list)
    can_modify_tests: bool = False
    can_modify_grader: bool = False
    can_install_dependencies: bool = False


class TaskAcceptance(BaseModel):
    required_behavior: List[str] = Field(default_factory=list)
    required_assets: List[str] = Field(default_factory=list)
    invariants: List[str] = Field(default_factory=list)
    performance_budgets: List[str] = Field(default_factory=list)


class TaskGrading(BaseModel):
    build_required: bool = True
    static_policy_checks: List[str] = Field(default_factory=list)
    visible_tests: List[str] = Field(default_factory=list)
    hidden_tests_ref: Optional[str] = None
    probes_ref: Optional[str] = None
    saved_asset_checks: List[str] = Field(default_factory=list)
    performance_checks: List[str] = Field(default_factory=list)
    visual_review: str = "none"
    regression_suite_ref: Optional[str] = None


class TaskReproducibility(BaseModel):
    fixed_timestep_seconds: Optional[float] = 0.016667
    random_seed: Optional[int] = 42
    tolerance_policy: str = "documented_tolerances"
    clean_snapshot_required: bool = True


class TaskProvenance(BaseModel):
    fixture_origin: str = "pending"
    rights_review: str = "pending"
    project_fixture_origin: Optional[str] = None
    code_asset_license_or_permission: Optional[str] = None
    allowed_use_review_status: str = "pending"
    reviewer: Optional[str] = None
    notes: str = ""


class TaskSpec(BaseModel):
    """Normalized, validated specification for an executable or draft benchmark task."""
    id: str
    logical_task_id: str
    tier: str
    title: str
    category: str = "gameplay"
    status: str = "specification-draft"
    engine_variants: List[str] = Field(default_factory=lambda: ["unity", "unreal"])
    prompt: str
    limits: TaskLimits
    allowed_edit_paths: List[str]
    forbidden_edits: List[str]
    required_checks: List[str] = Field(default_factory=list)
    probe_fields: List[str] = Field(default_factory=list)
    permissions: TaskPermissions = Field(default_factory=TaskPermissions)
    acceptance: TaskAcceptance = Field(default_factory=TaskAcceptance)
    grading: TaskGrading = Field(default_factory=TaskGrading)
    reproducibility: TaskReproducibility = Field(default_factory=TaskReproducibility)
    provenance: TaskProvenance = Field(default_factory=TaskProvenance)
    engine_scope: str = "ENGINE_SPECIFIC"
    engines_supported: List[str] = Field(default_factory=lambda: ["unreal", "unity"])
    engine_versions: Dict[str, str] = Field(default_factory=dict)
    verification_level: str = "REAL_ENGINE_VERIFIED"
    knowledge_domains: List[str] = Field(default_factory=list)
    parity_group: Optional[str] = None
    native_execution_required: bool = True
    source_references: List[str] = Field(default_factory=list)
    data_provenance_status: str = "verified"
    raw_source_path: Optional[str] = None


@dataclass
class LogicalTask:
    """Represents a logical task entry from TASK_INVENTORY.csv."""
    id: str
    tier: str
    title: str
    category: str
    engine_pairing: str
    primary_grading: str
    pilot: bool
    notes: str = ""


def normalize_task_dict(raw: Dict[str, Any], source_path: Optional[Path] = None) -> Dict[str, Any]:
    """Normalizes concise pilot-task YAML formats into the canonical schema dictionary."""
    data = dict(raw)

    # Derive category if missing
    if "category" not in data:
        lid = data.get("logical_task_id", "")
        tier = data.get("tier", "")
        if tier == "T3" or lid.startswith("T3-"):
            data["category"] = "editor_authoring"
        else:
            data["category"] = "gameplay"

    # Normalize limits
    raw_limits = data.get("limits") or {}
    if isinstance(raw_limits, dict):
        data["limits"] = {
            "wall_clock_seconds": raw_limits.get("wall_clock_seconds", 1800),
            "max_tool_calls": raw_limits.get("max_tool_calls", 100),
            "max_model_tokens": raw_limits.get("max_model_tokens"),
            "network_access": raw_limits.get("network_access", "disabled"),
        }
    else:
        data["limits"] = {"wall_clock_seconds": 1800, "max_tool_calls": 100}

    # Normalize permissions
    data["permissions"] = {
        "allowed_edit_paths": data.get("allowed_edit_paths", []),
        "forbidden_paths": data.get("forbidden_edits", []),
        "can_modify_tests": False,
        "can_modify_grader": False,
        "can_install_dependencies": False,
    }

    # Normalize grading based on required_checks
    req_checks = data.get("required_checks", [])
    data["grading"] = {
        "build_required": "build" in req_checks,
        "static_policy_checks": ["path_allowlist", "tampering_check"],
        "visible_tests": [],
        "hidden_tests_ref": f"graders/protected/{data.get('id', 'task')}" if any("test" in c for c in req_checks) else None,
        "probes_ref": f"configs/acceptance_criteria/{data.get('id', 'task').replace('-', '_')}.json" if any("probe" in c for c in req_checks) else None,
        "saved_asset_checks": ["asset_references", "component_wiring"] if any("asset" in c for c in req_checks) else [],
        "performance_checks": [],
        "visual_review": "none",
        "regression_suite_ref": "graders/regression" if "regression" in req_checks else None,
    }

    # Normalize reproducibility
    data["reproducibility"] = {
        "fixed_timestep_seconds": 0.016667,
        "random_seed": 42,
        "tolerance_policy": "documented_tolerances",
        "clean_snapshot_required": True,
    }

    # Normalize provenance
    prov = data.get("provenance") or {}
    if isinstance(prov, dict):
        data["provenance"] = {
            "fixture_origin": prov.get("fixture_origin", "pending"),
            "rights_review": prov.get("rights_review", "pending"),
            "allowed_use_review_status": "pending",
            "notes": prov.get("notes", ""),
        }
    else:
        data["provenance"] = {"fixture_origin": "pending", "rights_review": "pending"}

    if source_path:
        data["raw_source_path"] = str(source_path)

    # Normalize engine scope metadata
    if "engine_scope" not in data:
        data["engine_scope"] = "ENGINE_SPECIFIC"
    if "engines_supported" not in data:
        data["engines_supported"] = data.get("engine_variants", ["unreal", "unity"])
    if "engine_versions" not in data:
        data["engine_versions"] = {}
    if "verification_level" not in data:
        data["verification_level"] = "REAL_ENGINE_VERIFIED"
    if "knowledge_domains" not in data:
        data["knowledge_domains"] = [data.get("category", "gameplay")]
    if "native_execution_required" not in data:
        data["native_execution_required"] = True
    if "source_references" not in data:
        data["source_references"] = []
    if "data_provenance_status" not in data:
        data["data_provenance_status"] = "verified"

    return data


def load_task(file_path: Path | str) -> TaskSpec:
    """Loads and normalizes a YAML task specification file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Task specification file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Task file {path} did not parse into a dictionary: got {type(raw).__name__}")

    normalized = normalize_task_dict(raw, source_path=path)
    return TaskSpec(**normalized)


def load_task_inventory(csv_path: Path | str) -> List[LogicalTask]:
    """Reads TASK_INVENTORY.csv into a list of LogicalTask objects."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Task inventory file not found: {path}")

    tasks: List[LogicalTask] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pilot_val = row.get("pilot", "").strip().lower()
            tasks.append(
                LogicalTask(
                    id=row["id"].strip(),
                    tier=row["tier"].strip(),
                    title=row["title"].strip(),
                    category=row["category"].strip(),
                    engine_pairing=row["engine_pairing"].strip(),
                    primary_grading=row["primary_grading"].strip(),
                    pilot=(pilot_val in ("yes", "true", "1")),
                    notes=row.get("notes", "").strip(),
                )
            )
    return tasks
