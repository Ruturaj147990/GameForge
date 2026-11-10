"""Validation layer for GameForge task specifications and task inventory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from .task_loader import TaskSpec, load_task, load_task_inventory


@dataclass
class ValidationIssue:
    severity: str  # "ERROR", "WARNING", "DISCREPANCY"
    source: str
    field_name: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to serializable dictionary."""
        return asdict(self)


@dataclass
class SpecValidationResult:
    is_valid: bool
    total_specs_checked: int = 0
    total_inventory_tasks: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    @property
    def discrepancies(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "DISCREPANCY"]

    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to serializable dictionary."""
        return {
            "is_valid": self.is_valid,
            "total_specs_checked": self.total_specs_checked,
            "total_inventory_tasks": self.total_inventory_tasks,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "discrepancy_count": len(self.discrepancies),
            "issues": [i.to_dict() for i in self.issues],
        }

    def format_summary(self) -> str:
        """Returns formatted textual summary of validation results."""
        lines = [
            f"GameForge Spec Validation: {'PASSED' if self.is_valid else 'FAILED'}",
            f"Inventory Tasks: {self.total_inventory_tasks} | Specs Checked: {self.total_specs_checked}",
            f"Errors: {len(self.errors)} | Warnings: {len(self.warnings)} | Discrepancies: {len(self.discrepancies)}",
        ]
        if self.errors:
            lines.append("\nErrors:")
            for err in self.errors:
                lines.append(f"  [{err.source}] {err.field_name}: {err.message}")
        if self.discrepancies:
            lines.append("\nDiscrepancies:")
            for d in self.discrepancies:
                lines.append(f"  [{d.source}] {d.field_name}: {d.message}")
        return "\n".join(lines)


VALID_TIERS = {"T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"}
VALID_CATEGORIES = {
    "gameplay",
    "editor_authoring",
    "animation",
    "asset_pipeline",
    "project_feature",
    "end_to_end",
    "debug_performance",
}


def validate_inventory_file(inventory_path: Path | str, expected_count: Optional[int] = 30) -> List[ValidationIssue]:
    """Validates TASK_INVENTORY.csv against logical inventory specifications."""
    issues: List[ValidationIssue] = []
    path = Path(inventory_path)
    if not path.is_file():
        issues.append(
            ValidationIssue("ERROR", str(path), "file", f"Inventory file does not exist: {path}")
        )
        return issues

    try:
        tasks = load_task_inventory(path)
    except Exception as exc:
        issues.append(
            ValidationIssue("ERROR", str(path), "parse", f"Failed to parse CSV: {exc}")
        )
        return issues

    if expected_count is not None and len(tasks) != expected_count:
        issues.append(
            ValidationIssue(
                "ERROR",
                str(path),
                "count",
                f"Expected exactly {expected_count} logical tasks in TASK_INVENTORY.csv, found {len(tasks)}",
            )
        )

    seen_ids = set()
    for t in tasks:
        # ID check
        if not t.id:
            issues.append(ValidationIssue("ERROR", str(path), "id", "Encountered empty task ID"))
        elif t.id in seen_ids:
            issues.append(
                ValidationIssue("ERROR", str(path), "id", f"Duplicate task ID found: {t.id}")
            )
        else:
            seen_ids.add(t.id)

        # Tier check
        if t.tier not in VALID_TIERS:
            issues.append(
                ValidationIssue(
                    "ERROR", str(path), f"{t.id}.tier", f"Invalid tier '{t.tier}', expected one of {VALID_TIERS}"
                )
            )

        # Category check
        if t.category not in VALID_CATEGORIES:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    str(path),
                    f"{t.id}.category",
                    f"Invalid category '{t.category}', expected one of {VALID_CATEGORIES}",
                )
            )

        # Title check
        if not t.title or len(t.title) < 3:
            issues.append(
                ValidationIssue(
                    "ERROR", str(path), f"{t.id}.title", f"Task title is missing or too short: '{t.title}'"
                )
            )

    return issues


def validate_single_task_spec(yaml_path: Path | str) -> tuple[Optional[TaskSpec], List[ValidationIssue]]:
    """Validates an individual pilot task YAML file."""
    issues: List[ValidationIssue] = []
    path = Path(yaml_path)

    if not path.is_file():
        issues.append(
            ValidationIssue("ERROR", str(path), "file", f"Task YAML file not found: {path}")
        )
        return None, issues

    try:
        task = load_task(path)
    except ValidationError as val_err:
        for err in val_err.errors():
            loc = ".".join(str(p) for p in err["loc"])
            issues.append(
                ValidationIssue("ERROR", str(path), loc, f"Schema validation error: {err['msg']}")
            )
        return None, issues
    except Exception as exc:
        issues.append(
            ValidationIssue("ERROR", str(path), "parse", f"Failed to load task specification: {exc}")
        )
        return None, issues

    # Validate logical ID format across all valid tiers
    valid_prefixes = tuple(f"{tier}-" for tier in VALID_TIERS)
    if not task.logical_task_id.startswith(valid_prefixes):
        issues.append(
            ValidationIssue(
                "ERROR",
                str(path),
                "logical_task_id",
                f"Logical task ID '{task.logical_task_id}' does not match standard pattern T[1-8]-XXX",
            )
        )

    # Validate limits
    if task.limits.wall_clock_seconds <= 0:
        issues.append(
            ValidationIssue(
                "ERROR", str(path), "limits.wall_clock_seconds", "Wall clock limit must be > 0"
            )
        )

    if task.limits.max_tool_calls <= 0:
        issues.append(
            ValidationIssue(
                "ERROR", str(path), "limits.max_tool_calls", "Max tool calls must be > 0"
            )
        )

    # Validate paths
    if not task.allowed_edit_paths:
        issues.append(
            ValidationIssue(
                "ERROR", str(path), "allowed_edit_paths", "Must specify at least one allowed edit path"
            )
        )

    if not task.forbidden_edits:
        issues.append(
            ValidationIssue(
                "ERROR", str(path), "forbidden_edits", "Must specify protected forbidden paths"
            )
        )

    # Provenance warning (not silent approval)
    if task.provenance.allowed_use_review_status == "pending":
        issues.append(
            ValidationIssue(
                "WARNING",
                str(path),
                "provenance.allowed_use_review_status",
                "Licensing and rights review status is PENDING. Task remains unapproved for external redistribution.",
            )
        )

    return task, issues


def validate_all_specs(workspace_root: Path | str | None = None) -> SpecValidationResult:
    """Validates the logical inventory, all pilot tasks, and cross-checks discrepancies."""
    root = Path(workspace_root) if workspace_root else Path.cwd()
    inventory_path = root / "TASK_INVENTORY.csv"
    pilot_dir = root / "pilot_tasks"

    all_issues: List[ValidationIssue] = []

    # 1. Validate inventory CSV
    inv_issues = validate_inventory_file(inventory_path, expected_count=30)
    all_issues.extend(inv_issues)

    tasks_by_id = {}
    if inventory_path.is_file():
        try:
            for t in load_task_inventory(inventory_path):
                tasks_by_id[t.id] = t
        except Exception:
            pass

    # 2. Validate pilot task YAML files
    pilot_specs: List[TaskSpec] = []
    pilot_files = sorted(pilot_dir.glob("*.yaml")) if pilot_dir.is_dir() else []

    for p in pilot_files:
        spec, spec_issues = validate_single_task_spec(p)
        all_issues.extend(spec_issues)
        if spec:
            pilot_specs.append(spec)

    # 3. Cross-reference inventory and pilot files
    pilot_logical_ids = {s.logical_task_id for s in pilot_specs}
    for spec in pilot_specs:
        inv_entry = tasks_by_id.get(spec.logical_task_id)
        if not inv_entry:
            all_issues.append(
                ValidationIssue(
                    "ERROR",
                    spec.raw_source_path or spec.id,
                    "logical_task_id",
                    f"Pilot task refers to logical ID '{spec.logical_task_id}' which does not exist in TASK_INVENTORY.csv",
                )
            )
        else:
            # Check for inventory flag discrepancy
            if not inv_entry.pilot:
                all_issues.append(
                    ValidationIssue(
                        "DISCREPANCY",
                        "TASK_INVENTORY.csv",
                        f"{inv_entry.id}.pilot",
                        f"Logical task '{inv_entry.id}' is marked pilot='no' in TASK_INVENTORY.csv, but physical pilot specification '{spec.id}.yaml' exists in pilot_tasks/",
                    )
                )

    # Check for inventory tasks marked pilot='yes' that lack a YAML file
    for tid, entry in tasks_by_id.items():
        if entry.pilot and tid not in pilot_logical_ids:
            all_issues.append(
                ValidationIssue(
                    "DISCREPANCY",
                    "TASK_INVENTORY.csv",
                    f"{entry.id}.pilot",
                    f"Logical task '{entry.id}' is marked pilot='yes' in TASK_INVENTORY.csv, but no corresponding pilot YAML was found in pilot_tasks/",
                )
            )

    has_errors = any(i.severity == "ERROR" for i in all_issues)
    return SpecValidationResult(
        is_valid=not has_errors,
        total_specs_checked=len(pilot_files),
        total_inventory_tasks=len(tasks_by_id),
        issues=all_issues,
    )
