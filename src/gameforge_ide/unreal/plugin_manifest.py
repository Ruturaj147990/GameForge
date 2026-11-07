"""Authoritative GameForge Plugin Manifest, Drift Detection, and Synchronization (DEF-309).

Maintains the authoritative plugin specification in src/gameforge_ide/unreal/GameForge/.
Provides:
- Manifest generation with versioning, file hashes, and interface hashes
- Pre-deployment drift detection against target project plugins
- Clean authoritative synchronization (including removal of stale orphaned files)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "plugin_manifest.json"
IGNORED_DIR_NAMES = frozenset({"__pycache__", ".git", "Intermediate", "Saved", ".vs"})

KEY_INTERFACE_FILES = (
    "GameForge.uplugin",
    "Source/GameForgeRuntime/Public/GameForgePlayer.h",
    "Source/GameForgeRuntime/Public/GameForgeScenario.h",
    "Source/GameForgeRuntime/Public/GameForgeRules.h",
    "Source/GameForgeRuntime/Public/GameForgeKitActors.h",
    "Source/GameForgeRuntime/Public/GameForgeGameDefinition.h",
    "Source/GameForgeRuntime/Public/GameForgeAttributes.h",
    "Source/GameForgeRuntime/Public/GameForgeEvents.h",
    "Source/GameForgeRuntime/Public/GameForgeObjectives.h",
    "Source/GameForgeRuntime/Public/GameForgeGuard.h",
)


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 digest of a file in 64KB blocks."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class PluginDriftReport:
    has_drift: bool
    target_exists: bool
    authoritative_version: str
    target_version: Optional[str] = None
    version_mismatch: bool = False
    missing_files: List[str] = field(default_factory=list)
    mismatched_files: List[str] = field(default_factory=list)
    stale_files: List[str] = field(default_factory=list)
    interface_drift: Dict[str, Dict[str, str]] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_authoritative_plugin_root() -> Path:
    """Return the canonical, authoritative GameForge plugin directory."""
    return Path(__file__).resolve().parent / "GameForge"


def extract_plugin_version(plugin_root: Path) -> Tuple[str, str]:
    """Extract (plugin_version, engine_version) from GameForge.uplugin."""
    uplugin_file = plugin_root / "GameForge.uplugin"
    if not uplugin_file.is_file():
        return "1.0.0", "5.7.0"
    try:
        data = json.loads(uplugin_file.read_text(encoding="utf-8", errors="replace"))
        return str(data.get("VersionName", "1.0.0")), str(data.get("EngineVersion", "5.7.0"))
    except Exception:
        return "1.0.0", "5.7.0"


def compute_plugin_manifest(plugin_root: Path) -> Dict[str, Any]:
    """Compute complete plugin manifest with SHA-256 hashes for all tracked files and interfaces."""
    plugin_root = Path(plugin_root).resolve()
    version_name, engine_version = extract_plugin_version(plugin_root)

    files_map: Dict[str, str] = {}
    for item in sorted(plugin_root.rglob("*")):
        if not item.is_file():
            continue
        # Skip ignored directories and the manifest file itself
        if any(part in IGNORED_DIR_NAMES for part in item.parts):
            continue
        if item.name == MANIFEST_FILENAME:
            continue
        rel = item.relative_to(plugin_root).as_posix()
        try:
            files_map[rel] = compute_file_sha256(item)
        except OSError as exc:
            logger.warning("Could not hash %s: %s", item, exc)

    interfaces_map: Dict[str, str] = {}
    for rel_iface in KEY_INTERFACE_FILES:
        if rel_iface in files_map:
            interfaces_map[rel_iface] = files_map[rel_iface]
        else:
            iface_file = plugin_root / rel_iface
            if iface_file.is_file():
                interfaces_map[rel_iface] = compute_file_sha256(iface_file)

    manifest = {
        "manifest_version": 1,
        "plugin_name": "GameForge",
        "plugin_version": version_name,
        "engine_version": engine_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(files_map),
        "files": files_map,
        "interfaces": interfaces_map,
    }
    return manifest


def generate_authoritative_manifest(save_to_disk: bool = True) -> Dict[str, Any]:
    """Generate manifest for the authoritative plugin root and optionally write to disk."""
    auth_root = get_authoritative_plugin_root()
    manifest = compute_plugin_manifest(auth_root)
    if save_to_disk:
        manifest_file = auth_root / MANIFEST_FILENAME
        manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        logger.info("Saved authoritative plugin manifest (%d files) to %s", manifest["total_files"], manifest_file)
    return manifest


def load_plugin_manifest(plugin_dir: Path) -> Optional[Dict[str, Any]]:
    """Load plugin_manifest.json from a plugin directory if it exists."""
    manifest_file = Path(plugin_dir) / MANIFEST_FILENAME
    if not manifest_file.is_file():
        return None
    try:
        return json.loads(manifest_file.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def detect_plugin_drift(
    authoritative_root: Optional[Path] = None,
    target_dir: Optional[Path] = None,
) -> PluginDriftReport:
    """Compare target plugin directory against authoritative source and report any drift.
    
    Checks:
    1. Directory existence
    2. Version equality (from GameForge.uplugin)
    3. Missing files (present in authoritative, absent in target)
    4. Mismatched files (content hash differs)
    5. Stale files (present in target, absent in authoritative - sources of unity build collisions)
    6. Key interface drift (critical headers or ops changed)
    """
    auth_root = Path(authoritative_root or get_authoritative_plugin_root()).resolve()
    target_path = Path(target_dir).resolve() if target_dir else None

    auth_version, _ = extract_plugin_version(auth_root)

    if not target_path or not target_path.is_dir():
        return PluginDriftReport(
            has_drift=True,
            target_exists=False,
            authoritative_version=auth_version,
            target_version=None,
            version_mismatch=True,
            missing_files=[],
            mismatched_files=[],
            stale_files=[],
            interface_drift={},
            summary="Target plugin directory does not exist on disk",
        )

    target_version, _ = extract_plugin_version(target_path)
    version_mismatch = (target_version != auth_version)

    # Compute live file maps
    auth_manifest = compute_plugin_manifest(auth_root)
    auth_files = auth_manifest.get("files", {})
    auth_interfaces = auth_manifest.get("interfaces", {})

    target_files: Dict[str, str] = {}
    for item in sorted(target_path.rglob("*")):
        if not item.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in item.parts):
            continue
        if item.name == MANIFEST_FILENAME:
            continue
        rel = item.relative_to(target_path).as_posix()
        try:
            target_files[rel] = compute_file_sha256(item)
        except OSError:
            pass

    missing_files: List[str] = []
    mismatched_files: List[str] = []
    stale_files: List[str] = []
    interface_drift: Dict[str, Dict[str, str]] = {}

    # Check for missing and mismatched files
    for rel_path, auth_hash in auth_files.items():
        if rel_path not in target_files:
            missing_files.append(rel_path)
        elif target_files[rel_path] != auth_hash:
            mismatched_files.append(rel_path)

    # Check for stale files in target
    for rel_path in target_files:
        if rel_path not in auth_files:
            stale_files.append(rel_path)

    # Check interface hashes
    for iface_rel, auth_hash in auth_interfaces.items():
        target_hash = target_files.get(iface_rel)
        if target_hash != auth_hash:
            interface_drift[iface_rel] = {
                "authoritative": auth_hash,
                "target": target_hash or "MISSING",
            }

    has_drift = bool(version_mismatch or missing_files or mismatched_files or stale_files or interface_drift)

    reasons: List[str] = []
    if version_mismatch:
        reasons.append(f"version mismatch ({target_version} vs {auth_version})")
    if missing_files:
        reasons.append(f"{len(missing_files)} missing file(s)")
    if mismatched_files:
        reasons.append(f"{len(mismatched_files)} modified file(s)")
    if stale_files:
        reasons.append(f"{len(stale_files)} stale/orphaned file(s)")
    if interface_drift:
        reasons.append(f"{len(interface_drift)} interface hash mismatch(es)")

    summary = "; ".join(reasons) if reasons else "Authoritative and target plugins are in sync"

    return PluginDriftReport(
        has_drift=has_drift,
        target_exists=True,
        authoritative_version=auth_version,
        target_version=target_version,
        version_mismatch=version_mismatch,
        missing_files=missing_files,
        mismatched_files=mismatched_files,
        stale_files=stale_files,
        interface_drift=interface_drift,
        summary=summary,
    )


def synchronize_plugin(
    authoritative_root: Optional[Path] = None,
    target_dir: Optional[Path] = None,
    remove_stale: bool = True,
) -> Dict[str, Any]:
    """Cleanly synchronize authoritative plugin into target_dir.
    
    Copies all authoritative files, updates modified files, removes stale orphaned files
    (if remove_stale=True), and writes an updated plugin_manifest.json.
    """
    auth_root = Path(authoritative_root or get_authoritative_plugin_root()).resolve()
    if not auth_root.is_dir():
        raise FileNotFoundError(f"Authoritative plugin source not found at {auth_root}")

    if not target_dir:
        raise ValueError("target_dir must be provided for plugin synchronization")

    target_path = Path(target_dir).resolve()
    target_path.mkdir(parents=True, exist_ok=True)

    auth_manifest = compute_plugin_manifest(auth_root)
    auth_files = auth_manifest.get("files", {})

    copied_files: List[str] = []
    updated_files: List[str] = []
    removed_stale_files: List[str] = []

    # 1. Remove stale files if requested
    if remove_stale and target_path.is_dir():
        for item in list(target_path.rglob("*")):
            if not item.is_file():
                continue
            if any(part in IGNORED_DIR_NAMES for part in item.parts):
                continue
            if item.name == MANIFEST_FILENAME:
                continue
            rel = item.relative_to(target_path).as_posix()
            if rel not in auth_files:
                try:
                    item.unlink()
                    removed_stale_files.append(rel)
                except OSError as exc:
                    logger.warning("Could not remove stale file %s: %s", item, exc)

    # 2. Copy/update authoritative files
    for rel_path, auth_hash in auth_files.items():
        src_file = auth_root / rel_path
        dst_file = target_path / rel_path

        needs_copy = False
        is_update = dst_file.is_file()

        if not dst_file.is_file():
            needs_copy = True
        else:
            try:
                curr_hash = compute_file_sha256(dst_file)
                if curr_hash != auth_hash:
                    needs_copy = True
            except OSError:
                needs_copy = True

        if needs_copy:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            if is_update:
                updated_files.append(rel_path)
            else:
                copied_files.append(rel_path)

    # 3. Write target manifest
    target_manifest = dict(auth_manifest)
    target_manifest["synchronized_at"] = datetime.now(timezone.utc).isoformat()
    target_manifest_file = target_path / MANIFEST_FILENAME
    target_manifest_file.write_text(
        json.dumps(target_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    logger.info(
        "Synchronized GameForge plugin to %s: %d new, %d updated, %d stale removed",
        target_path,
        len(copied_files),
        len(updated_files),
        len(removed_stale_files),
    )

    return {
        "ok": True,
        "target_dir": str(target_path),
        "copied_count": len(copied_files),
        "updated_count": len(updated_files),
        "removed_stale_count": len(removed_stale_files),
        "copied_files": copied_files,
        "updated_files": updated_files,
        "removed_stale_files": removed_stale_files,
        "manifest_path": str(target_manifest_file),
    }
