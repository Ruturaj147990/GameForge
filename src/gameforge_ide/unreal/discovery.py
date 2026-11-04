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
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PINNED_VERSION = "5.7"

# DEF-134 FIX: Module-level locks for thread-safe engine discovery.
# Python 3.14's Path.glob() / glob.scandir() crashes with Windows access violations
# when called from multiple threads concurrently (or even from a single background
# thread while Qt's main thread iterates allWidgets()). Two complementary guards:
#   1. _DRIVE_SCAN_LOCK   – serialises all drive filesystem scans.
#   2. _DISCOVERY_LOCK    – serialises the entire discover_all_engines() body.
#   3. _discovery_cache   – caches the result so subsequent calls are instant.
_DRIVE_SCAN_LOCK = threading.Lock()
_DISCOVERY_LOCK = threading.Lock()
_discovery_cache: "Optional[List[DiscoveredEngine]]" = None


def invalidate_discovery_cache() -> None:
    """Call when the engine environment changes (e.g. after reset_settings_cache())."""
    global _discovery_cache
    _discovery_cache = None


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
    remote_exec_candidates = [
        root / "Engine" / "Plugins" / "Experimental" / "PythonScriptPlugin" / "Content" / "Python" / "remote_execution.py",
        root / "Engine" / "Plugins" / "Developer" / "PythonScriptPlugin" / "Content" / "Python" / "remote_execution.py",
        root / "Engine" / "Plugins" / "ScriptPlugin" / "Content" / "Python" / "remote_execution.py",
        root / "Engine" / "Plugins" / "PythonScriptPlugin" / "Content" / "Python" / "remote_execution.py",
    ]
    has_remote_exec = any(cand.is_file() for cand in remote_exec_candidates)
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


def _safe_read_json(path: Path, retries: int = 3, delay: float = 0.05) -> Optional[Any]:
    """Read a JSON file safely with UTF-8 BOM stripping and retry loop for locked files."""
    for attempt in range(retries):
        try:
            raw = path.read_text(encoding="utf-8-sig")
            return json.loads(raw)
        except (PermissionError, OSError):
            if attempt < retries - 1:
                import time
                time.sleep(delay * (attempt + 1))
            else:
                pass
        except Exception:
            return None
    return None


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
            data = _safe_read_json(item_file)
            if isinstance(data, dict):
                app_name = str(data.get("AppName", ""))
                location = data.get("InstallLocation")
                if app_name.startswith("UE_") and location:
                    p = Path(location)
                    if p.is_dir() and p not in roots:
                        roots.append(p)
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

    data = _safe_read_json(dat_file)
    if isinstance(data, dict):
        for item in data.get("InstallationList", []):
            app_name = str(item.get("AppName", ""))
            location = item.get("InstallLocation")
            if app_name.startswith("UE_") and location:
                p = Path(location)
                if p.is_dir() and p not in roots:
                    roots.append(p)
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

        # Probe both 64-bit and 32-bit registry views
        access_flags = [winreg.KEY_READ]
        if hasattr(winreg, "KEY_WOW64_64KEY"):
            access_flags.append(winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        if hasattr(winreg, "KEY_WOW64_32KEY"):
            access_flags.append(winreg.KEY_READ | winreg.KEY_WOW64_32KEY)

        for hive, subkey_path in key_specs:
            for access in access_flags:
                try:
                    with winreg.OpenKey(hive, subkey_path, 0, access) as base:
                        num_subkeys, num_values, _ = winreg.QueryInfoKey(base)
                        # Check subkeys
                        for i in range(num_subkeys):
                            try:
                                subkey_name = winreg.EnumKey(base, i)
                                with winreg.OpenKey(base, subkey_name, 0, access) as subkey:
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
    """Probe standard Unreal Engine paths across all available drive letters without modal hangs.
    
    Thread-safe: serialized with _DRIVE_SCAN_LOCK to prevent concurrent glob.scandir()
    calls from multiple threads, which causes Windows access violations on Python 3.14.
    """
    # Only one thread runs the glob scan at a time (DEF-134).
    with _DRIVE_SCAN_LOCK:
        return _scan_filesystem_drives_impl()


def _scan_filesystem_drives_impl() -> List[Path]:
    """Internal implementation of filesystem drive scanning (called under lock).
    
    Uses os.scandir() directly instead of Path.glob() to avoid Python 3.14's
    new glob internals which crash with access violations when called from
    background threads concurrently with Qt widget operations.
    """
    roots: List[Path] = []
    if sys.platform == "win32":
        drives: List[str] = []
        try:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            mask = k32.GetLogicalDrives()
            # Only scan Fixed (3) and RAMDisk (6) drives — skip Remote/Network (4)
            # which can hang or corrupt state when scanned from background threads.
            for i in range(26):
                if (mask >> i) & 1:
                    drive_letter = chr(ord('A') + i)
                    drive_root = f"{drive_letter}:\\"
                    dtype = k32.GetDriveTypeW(drive_root)
                    if dtype in (3, 6):  # Fixed and RAMDisk only (NOT network)
                        drives.append(drive_root)
        except Exception:
            import string
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    else:
        drives = ["/opt", "/home"]

    # Candidate subdirectory structures: (parent_subpath, name_prefix)
    # Using direct os.scandir() instead of Path.glob() to avoid Python 3.14 glob bugs.
    candidate_parents: List[tuple] = [
        ("",),                          # drive root: UE_*, UE5*
        ("UE",),                        # UE/UE_*, UE/UE5*
        ("Program Files", "Epic Games"),
        ("Program Files (x86)", "Epic Games"),
        ("Epic Games",),
        ("Epic Games", "Unreal Engine"),
        ("Unreal",),
        ("UnrealEngine",),
        ("Unreal Engine",),
    ]

    def _check_dir_for_ue(parent: Path) -> None:
        try:
            with os.scandir(parent) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False) and (
                            entry.name.startswith("UE_") or entry.name.startswith("UE5")
                        ):
                            p = Path(entry.path)
                            if p not in roots:
                                roots.append(p)
                    except OSError:
                        pass
        except OSError:
            pass

    for drive in drives:
        drive_path = Path(drive)
        for parts in candidate_parents:
            parent = drive_path.joinpath(*parts)
            _check_dir_for_ue(parent)

    return roots


def discover_all_engines(pinned_minor: str = DEFAULT_PINNED_VERSION, use_cache: bool = True) -> List["DiscoveredEngine"]:
    """Discover all Unreal Engine installations across all detection sources, deduplicated.

    Thread-safety contract (DEF-133/134 fix):
    - Full discovery (manifest scanning, registry reads, drive glob) only runs on the
      MAIN THREAD.  Python 3.14's pathlib.read_text / glob.scandir cause Windows
      access violations when a background thread does file I/O while the main thread
      is concurrently running QApplication.allWidgets() (Python 3.14 + PySide6 ABI).
    - Background threads return an empty list if the cache is not yet warm, or the
      cached result if the main thread has already populated it.
    - Once the main thread populates _discovery_cache, every thread gets the result.
    - When running unit tests (PYTEST_CURRENT_TEST set), caching is bypassed so tests
      can configure different mock engine roots and environment variables safely.
    """
    global _discovery_cache
    is_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if not is_pytest and use_cache and _discovery_cache is not None:
        return _discovery_cache

    with _DISCOVERY_LOCK:
        if not is_pytest and use_cache and _discovery_cache is not None:   # double-checked locking
            return _discovery_cache
            return _discovery_cache

        # Only run expensive filesystem I/O from the main thread to avoid Python 3.14
        # pathlib/glob ABI crashes when Qt C++ and Python file I/O run concurrently.
        if threading.current_thread() is not threading.main_thread():
            # Background thread: return empty list safely. Engine will be None in
            # the resulting Settings object, which is acceptable for CapabilityRegistry
            # (it only needs artifacts_root, not engine info).
            return []

        result = _do_discover_all_engines(pinned_minor)
        _discovery_cache = result
        return result


def _do_discover_all_engines(pinned_minor: str = DEFAULT_PINNED_VERSION) -> List["DiscoveredEngine"]:
    """Internal: performs the actual multi-source engine discovery (called under _DISCOVERY_LOCK)."""
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
