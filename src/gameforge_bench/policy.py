"""Security, candidate isolation, and static policy enforcement."""

from __future__ import annotations

import hashlib
import os
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
            if any(part in rel for part in ("Intermediate", "Saved", "DerivedDataCache", "Library", "Temp", ".git")):
                continue
            hashes[rel] = compute_file_hash(full)

    return hashes


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
        # Verify candidate is either inside workspace or a designated scratch folder
        if not c_resolved.is_relative_to(w_resolved) and "scratch" not in str(c_resolved).lower() and "gemini" not in str(c_resolved).lower():
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

    # 3. Check forbidden paths and tampering
    normalized_forbidden = [p.lower().replace("\\", "/") for p in forbidden_paths]
    # Standard mandatory protected directories
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

    # 4. Check allowed edit paths (allowlist enforcement)
    # If allowed_edit_paths contains specific designations, ensure changes fall within them
    if allowed_edit_paths and modified_files:
        for m_file in modified_files:
            m_lower = m_file.lower().replace("\\", "/")
            # Handle generic keywords like 'project gameplay source paths', 'designated content/assets paths'
            is_allowed = False
            for allowed in allowed_edit_paths:
                a_lower = allowed.lower().replace("\\", "/")
                # Check for direct path match or semantic game paths (Source/, Content/, Assets/, Config/)
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
