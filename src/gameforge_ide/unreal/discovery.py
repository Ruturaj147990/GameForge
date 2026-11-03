"""Comprehensive, multi-source Unreal Engine discovery and validation subsystem.

Discovers Unreal Engine installations on Windows without hardcoded drive paths:
1. Environment variables (GAMEFORGE_ENGINE_ROOT, UE_ENGINE_PATH, UNREAL_ENGINE_PATH)
2. User settings (%APPDATA%\\GameForge\\settings.json)
3. Epic Games Launcher installation manifests (%ProgramData%\\Epic\\EpicGamesLauncher\\Data\\Manifests\\*.item)
4. Epic Games Launcher installed database (%ProgramData%\\Epic\\UnrealEngineLauncher\\LauncherInstalled.dat)
5. Windows Registry (HKLM and HKCU under SOFTWARE\\EpicGames\\Unreal Engine and SOFTWARE\\Epic Games)
6. Filesystem drive scanning across all active drives (C:, D:, E:, etc.) for standard install roots

Validates each candidate by verifying:
- Engine/Build/Build.version (version triple and changelist)
- Engine/Binaries/Win64/UnrealEditor.exe
- UnrealBuildTool binary (.dll or .exe)
- PythonScriptPlugin remote_execution.py support
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PINNED_VERSION = "5.7"


@dataclass
class DiscoveredEngine:
    root: Path
    version: str
    changelist: int
    source: str
    editor_exe: Path
    ubt_path: Optional[Path]
    has_remote_execution: bool
    is_valid: bool
    is_compatible: bool
    diagnostics: List[str] = field(default_factory=list)

    @property
    def major_minor(self) -> str:
        parts = self.version.split(".")
        return ".".join(parts[:2]) if len(parts) >= 2 else self.version


def parse_engine_version(root: Path) -> Optional[Tuple[str, int, str]]:
    """Read (version_str, changelist, branch_name) from Engine/Build/Build.version."""
    build_version_file = root / "Engine" / "Build" / "Build.version"
    if not build_version_file.is_file():
        return None
    try:
        data = json.loads(build_version_file.read_text(encoding="utf-8"))
        major = data.get("MajorVersion")
        minor = data.get("MinorVersion")
        patch = data.get("PatchVersion", 0)
        cl = int(data.get("Changelist", 0))
        branch = str(data.get("BranchName", ""))
        if major is not None and minor is not None:
            return f"{major}.{minor}.{patch}", cl, branch
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def validate_engine_root(root: Path, source: str, pinned_minor: str = DEFAULT_PINNED_VERSION) -> Optional[DiscoveredEngine]:
    """Validate a candidate Unreal Engine root directory and return a DiscoveredEngine if valid."""
    root = Path(root).resolve()
    if not root.is_dir():
        return None

    ver_info = parse_engine_version(root)
    if ver_info is None:
        return None

    version, changelist, _ = ver_info
    diagnostics: List[str] = []

    # 1. Editor executable
    editor_exe = root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
    editor_found = editor_exe.is_file()
    if not editor_found:
        diagnostics.append(f"UnrealEditor.exe not found at {editor_exe}")

    # 2. UnrealBuildTool
    ubt_candidates = [
        root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.dll",
        root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool.dll",
        root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool.exe",
    ]
    ubt_path: Optional[Path] = None
    for cand in ubt_candidates:
        if cand.is_file():
            ubt_path = cand
            break
    if not ubt_path:
        diagnostics.append("UnrealBuildTool binary not found")

    # 3. Python remote execution
    remote_exec = root / "Engine" / "Plugins" / "Experimental" / "PythonScriptPlugin" / "Content" / "Python" / "remote_execution.py"
    has_remote_exec = remote_exec.is_file()
    if not has_remote_exec:
        diagnostics.append("PythonScriptPlugin remote_execution.py not found")

    is_valid = editor_found and (ubt_path is not None)
    is_compatible = is_valid and version.startswith(pinned_minor)

    if not is_compatible and is_valid:
        diagnostics.append(f"Version {version} differs from target {pinned_minor}.x")

    return DiscoveredEngine(
        root=root,
        version=version,
        changelist=changelist,
        source=source,
        editor_exe=editor_exe,
        ubt_path=ubt_path,
        has_remote_execution=has_remote_exec,
        is_valid=is_valid,
        is_compatible=is_compatible,
        diagnostics=diagnostics,
    )


def scan_manifest_items() -> List[Path]:
    """Scan Epic Games Launcher *.item manifests in %ProgramData%\\Epic\\EpicGamesLauncher\\Data\\Manifests."""
    roots: List[Path] = []
    prog_data = os.environ.get("PROGRAMDATA")
    if not prog_data:
        return roots

    manifest_dir = Path(prog_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not manifest_dir.is_dir():
        return roots

    try:
        for item_file in manifest_dir.glob("*.item"):
            try:
                data = json.loads(item_file.read_text(encoding="utf-8"))
                app_name = str(data.get("AppName", ""))
                location = data.get("InstallLocation")
                if app_name.startswith("UE_") and location:
                    p = Path(location)
                    if p.is_dir() and p not in roots:
                        roots.append(p)
            except Exception:
                pass
    except OSError:
        pass
    return roots


def scan_launcher_installed_dat() -> List[Path]:
    """Scan %ProgramData%\\Epic\\UnrealEngineLauncher\\LauncherInstalled.dat."""
    roots: List[Path] = []
    prog_data = os.environ.get("PROGRAMDATA")
    if not prog_data:
        return roots

    dat_file = Path(prog_data) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    if not dat_file.is_file():
        return roots

    try:
        data = json.loads(dat_file.read_text(encoding="utf-8"))
        for item in data.get("InstallationList", []):
            app_name = str(item.get("AppName", ""))
            location = item.get("InstallLocation")
            if app_name.startswith("UE_") and location:
                p = Path(location)
                if p.is_dir() and p not in roots:
                    roots.append(p)
    except Exception:
        pass
    return roots


def scan_windows_registry() -> List[Path]:
    """Scan Windows Registry keys for Epic Games and Unreal Engine installations."""
    roots: List[Path] = []
    if sys.platform != "win32" or os.environ.get("GAMEFORGE_SKIP_REGISTRY"):
        return roots

    try:
        import winreg

        # HKLM / HKCU paths to probe
        key_specs = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\Unreal Engine"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\EpicGames\Unreal Engine"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Epic Games\Unreal Engine"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Epic Games\Unreal Engine\Builds"),
        ]

        for hive, subkey_path in key_specs:
            try:
                with winreg.OpenKey(hive, subkey_path) as base:
                    num_subkeys, num_values, _ = winreg.QueryInfoKey(base)
                    # Check subkeys
                    for i in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(base, i)
                            with winreg.OpenKey(base, subkey_name) as subkey:
                                try:
                                    dir_val, _ = winreg.QueryValueEx(subkey, "InstalledDirectory")
                                    p = Path(dir_val)
                                    if p.is_dir() and p not in roots:
                                        roots.append(p)
                                except OSError:
                                    pass
                        except OSError:
                            continue
                    # Check values (like in Builds key)
                    for j in range(num_values):
                        try:
                            val_name, val_data, _ = winreg.EnumValue(base, j)
                            if isinstance(val_data, str):
                                p = Path(val_data)
                                if p.is_dir() and (p / "Engine" / "Binaries").is_dir() and p not in roots:
                                    roots.append(p)
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception:
        pass
    return roots


def scan_filesystem_drives() -> List[Path]:
    """Probe standard Unreal Engine paths across all available drive letters."""
    roots: List[Path] = []
    if sys.platform == "win32":
        # Get active drive letters
        import string
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    else:
        drives = ["/opt", "/home"]

    candidate_patterns = [
        "UE/UE_*",
        "Program Files/Epic Games/UE_*",
        "Epic Games/UE_*",
        "UnrealEngine/UE_*",
        "Unreal Engine/UE_*",
    ]

    for drive in drives:
        drive_path = Path(drive)
        for pattern in candidate_patterns:
            try:
                for match in drive_path.glob(pattern):
                    if match.is_dir() and match not in roots:
                        roots.append(match)
            except OSError:
                pass
    return roots


def discover_all_engines(pinned_minor: str = DEFAULT_PINNED_VERSION) -> List[DiscoveredEngine]:
    """Discover all Unreal Engine installations across all detection sources, deduplicated."""
    found: List[DiscoveredEngine] = []
    seen_roots: set = set()

    def add_candidate(path: Optional[Path], source: str) -> None:
        if path is None:
            return
        resolved = Path(path).resolve()
        if resolved in seen_roots:
            return
        eng = validate_engine_root(resolved, source=source, pinned_minor=pinned_minor)
        if eng is not None and eng.is_valid:
            seen_roots.add(resolved)
            found.append(eng)

    # 1. Environment overrides
    for env_key in ("GAMEFORGE_ENGINE_ROOT", "UE_ENGINE_PATH", "UNREAL_ENGINE_PATH"):
        val = os.environ.get(env_key)
        if val:
            add_candidate(Path(val), source=f"env:{env_key}")

    # 2. Epic Launcher Manifest items (*.item)
    for p in scan_manifest_items():
        add_candidate(p, source="epic_manifest_item")

    # 3. Epic Launcher Installed.dat
    for p in scan_launcher_installed_dat():
        add_candidate(p, source="epic_launcher_dat")

    # 4. Windows Registry
    for p in scan_windows_registry():
        add_candidate(p, source="windows_registry")

    # 5. Drive Scanning
    for p in scan_filesystem_drives():
        add_candidate(p, source="drive_scan")

    # Sort: explicit overrides first, then compatible, then highest changelist, then newest version
    def _engine_sort_key(e: DiscoveredEngine) -> Tuple[int, int, int, str]:
        is_explicit = 1 if e.source.startswith("env:") or e.source in ("settings", "test") else 0
        is_comp = 1 if e.is_compatible else 0
        return (is_explicit, is_comp, e.changelist, e.version)

    found.sort(key=_engine_sort_key, reverse=True)
    return found


def get_best_engine(pinned_minor: str = DEFAULT_PINNED_VERSION) -> Optional[DiscoveredEngine]:
    """Return the single best compatible engine, or the highest valid engine if none matches pinned_minor."""
    engines = discover_all_engines(pinned_minor=pinned_minor)
    if not engines:
        return None
    # Prefer compatible engines first
    compatible = [e for e in engines if e.is_compatible]
    if compatible:
        return compatible[0]
    return engines[0]
