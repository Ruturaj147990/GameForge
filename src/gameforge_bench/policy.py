"""Security, candidate isolation, and static policy enforcement."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class PolicyCheckResult:
    passed: bool
    violations: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def compute_file_hash(path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def snapshot_directory_hashes(directory: Path) -> Dict[str, str]:
    """Generates a mapping of relative file paths to SHA-256 hashes."""
    hashes: Dict[str, str] = {}
    if not directory.is_dir():
        return hashes

    for root, _, files in os.walk(directory):
        r_path = Path(root)
        for f in files:
            full = r_path / f
            # Skip transient build/cache artifacts
            rel = full.relative_to(directory).as_posix()
            if any(part in rel for part in ("Binaries", "Intermediate", "Saved", "DerivedDataCache", "Library", "Temp", ".git", "__pycache__")) or rel.endswith(".pyc"):
                continue
            hashes[rel] = compute_file_hash(full)

    return hashes


def compute_snapshot_hash(hashes_or_dir: Dict[str, str] | Path) -> str:
    """Computes a deterministic SHA-256 hash across sorted (rel_path, file_hash) pairs."""
    if isinstance(hashes_or_dir, Path):
        hashes = snapshot_directory_hashes(hashes_or_dir)
    else:
        hashes = hashes_or_dir

    h = hashlib.sha256()
    for rel_path in sorted(hashes.keys()):
        file_hash = hashes[rel_path]
        h.update(f"{rel_path}:{file_hash}\n".encode("utf-8"))
    return f"sha256:{h.hexdigest()}"


def freeze_candidate_snapshot(candidate_dir: Path, frozen_dir: Path) -> Tuple[str, Dict[str, str]]:
    """Creates a frozen, isolated read-only copy of the candidate directory and records its snapshot hash."""
    if frozen_dir.exists():
        shutil.rmtree(frozen_dir, ignore_errors=True)
    frozen_dir.parent.mkdir(parents=True, exist_ok=True)

    # Copy tree preserving files
    shutil.copytree(candidate_dir, frozen_dir, dirs_exist_ok=True)

    inventory = snapshot_directory_hashes(frozen_dir)
    snapshot_id = compute_snapshot_hash(inventory)
    return snapshot_id, inventory


def verify_snapshot_integrity(frozen_dir: Path, expected_snapshot_hash: str) -> bool:
    """Verifies that a frozen snapshot has not been altered."""
    actual_hash = compute_snapshot_hash(frozen_dir)
    return actual_hash == expected_snapshot_hash


def is_path_safe_relative(base_dir: Path, target_path_str: str) -> Tuple[bool, Optional[Path]]:
    """Checks for path traversal and returns normalized resolved path if safe."""
    try:
        base_resolved = base_dir.resolve()
        target = (base_dir / target_path_str).resolve()
        is_safe = target.is_relative_to(base_resolved)
        return is_safe, target if is_safe else None
    except Exception:
        return False, None


def check_candidate_policy(
    workspace_root: Path,
    candidate_dir: Path,
    allowed_edit_paths: List[str],
    forbidden_paths: List[str],
    baseline_hashes: Optional[Dict[str, str]] = None,
) -> PolicyCheckResult:
    """Enforces static edit boundaries and anti-tampering rules on candidate modifications."""
    violations: List[str] = []
    modified_files: List[str] = []

    # 1. Boundary check: candidate_dir must be inside or under workspace_root
    try:
        w_resolved = workspace_root.resolve()
        c_resolved = candidate_dir.resolve()
        if not c_resolved.is_relative_to(w_resolved):
            violations.append(f"Candidate directory escapes workspace boundary: {c_resolved}")
    except Exception as exc:
        violations.append(f"Failed to resolve candidate directory: {exc}")

    current_hashes = snapshot_directory_hashes(candidate_dir)

    # 2. Check for modifications against baseline snapshot
    if baseline_hashes:
        all_keys = set(baseline_hashes.keys()) | set(current_hashes.keys())
        for rel in sorted(all_keys):
            old_h = baseline_hashes.get(rel)
            new_h = current_hashes.get(rel)
            if old_h != new_h:
                modified_files.append(rel)
    else:
        modified_files = list(current_hashes.keys())

    # 3. Check symlinks for path traversal / escape attempts
    for root, dirs, files in os.walk(candidate_dir):
        for entry in dirs + files:
            entry_path = Path(root) / entry
            if entry_path.is_symlink():
                try:
                    resolved_target = entry_path.resolve()
                    if not resolved_target.is_relative_to(candidate_dir.resolve()):
                        violations.append(
                            f"Symlink traversal attack detected: '{entry_path.relative_to(candidate_dir)}' points outside candidate workspace ({resolved_target})"
                        )
                except Exception as exc:
                    violations.append(f"Invalid symlink detected: {exc}")

    # 4. Check forbidden paths and tampering
    normalized_forbidden = [p.lower().replace("\\", "/") for p in forbidden_paths]
    mandatory_protected = [
        "graders",
        "configs/acceptance_criteria",
        "schemas",
        "tests",
        ".git",
    ]

    for m_file in modified_files:
        m_lower = m_file.lower().replace("\\", "/")

        # Check explicit forbidden patterns
        for f_pat in normalized_forbidden:
            if f_pat in m_lower:
                violations.append(f"Tampering detected: modified forbidden path '{m_file}' (matches '{f_pat}')")

        # Check mandatory protected patterns
        for m_pat in mandatory_protected:
            if m_pat in m_lower:
                violations.append(f"Protected security violation: candidate cannot edit '{m_file}'")

        # Anti-tampering: Candidate must never contain fake reports
        if any(tok in m_lower for tok in ("benchmark_report", "run_report", "test_report")) and m_lower.endswith(".json"):
            violations.append(f"Tampering detected: fake report generation attempt in '{m_file}'")

        # Anti-tampering: Hidden test / grader leak check
        if "hidden" in m_lower or "test_health_damage_hidden" in m_lower:
            violations.append(f"Tampering detected: hidden test file in candidate directory '{m_file}'")

    # 5. Check allowed edit paths (allowlist enforcement)
    if allowed_edit_paths and modified_files:
        for m_file in modified_files:
            m_lower = m_file.lower().replace("\\", "/")
            if any(part in m_lower for part in ("binaries/", "intermediate/", "saved/", ".target")):
                continue
            is_allowed = False
            for allowed in allowed_edit_paths:
                a_lower = allowed.lower().replace("\\", "/")
                if a_lower in m_lower:
                    is_allowed = True
                    break
                elif "source" in a_lower and ("source/" in m_lower or ".cpp" in m_lower or ".h" in m_lower or ".cs" in m_lower):
                    is_allowed = True
                    break
                elif "content" in a_lower and ("content/" in m_lower or ".uasset" in m_lower or ".json" in m_lower):
                    is_allowed = True
                    break
                elif "asset" in a_lower and ("assets/" in m_lower or "content/" in m_lower):
                    is_allowed = True
                    break
                elif "config" in a_lower and "config/" in m_lower:
                    is_allowed = True
                    break

            if not is_allowed and not violations:
                violations.append(f"Path allowlist violation: '{m_file}' is not in allowed_edit_paths")

    passed = len(violations) == 0
    return PolicyCheckResult(
        passed=passed,
        violations=violations,
        modified_files=modified_files,
        details={
            "total_files_checked": len(current_hashes),
            "modified_count": len(modified_files),
        },
    )
