"""Canonical project management, identity resolution, and discovery (AD-15, docs/01_ARCHITECTURE.md).

Single source of truth for:
- Distinguishing repository root, user workspace, projects root, and active project directories.
- Discovering GameForge and Unreal Engine projects across configured locations.
- Resolving authoritative project directories for the IDE, agent, tools, and build pipeline.
- Safely opening project and artifact folders in the host operating system file manager.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional, Union

from .settings import get_settings

logger = logging.getLogger(__name__)

# Repository infrastructure directories that are part of the platform source code,
# test fixtures, documentation, or internal build cache, and are NEVER games.
REPO_INFRASTRUCTURE_DIRS = {
    "fixtures", "graders", "reports", "scratch", "tests", "src",
    "docs", "configs", "pipeline", "unreal", "build", "dist",
    ".git", ".gemini", ".github", "node_modules", ".venv",
    "Saved", "Intermediate", "Binaries", "DerivedDataCache", "Plugins",
}


def find_uproject(folder: Union[str, Path]) -> Optional[Path]:
    """Find the first .uproject file in folder, matching folder name first if available, with nested directory support.

    Uses os.path instead of pathlib to avoid Python 3.14 + PySide6 C-runtime ABI collision
    when called from background threads (DEF-134).
    """
    try:
        folder_str = str(folder)
        if not os.path.isdir(folder_str):
            return None

        # Guard: REPO_ROOT and its immediate infrastructure subdirectories are not Unreal projects
        try:
            from .settings import REPO_ROOT
            repo_real = os.path.realpath(str(REPO_ROOT))
            real_folder = os.path.realpath(folder_str)
            if real_folder == repo_real:
                return None
            if os.path.dirname(real_folder) == repo_real:
                if os.path.basename(real_folder) in REPO_INFRASTRUCTURE_DIRS:
                    return None
        except Exception:
            pass

        folder_name = os.path.basename(folder_str.rstrip("/\\"))
        if folder_name in REPO_INFRASTRUCTURE_DIRS:
            return None

        # 1. Exact match <folder_name>.uproject
        exact = os.path.join(folder_str, f"{folder_name}.uproject")
        if os.path.isfile(exact):
            return Path(exact)
        # 2. Any .uproject in the top level of folder
        try:
            top_entries = os.listdir(folder_str)
        except OSError:
            return None
        for entry in top_entries:
            if entry.lower().endswith(".uproject"):
                return Path(os.path.join(folder_str, entry))

        # 3. Search nested directories up to 3 levels deep (for repo/Game/Game.uproject layouts)
        ignore_dirs = {
            "Intermediate", "Saved", "Binaries", ".git", "scratch", "reports",
            "node_modules", ".venv", "Plugins", "fixtures", "graders", "tests",
            "src", "docs", "DerivedDataCache", "Build", ".gemini"
        }
        nested_candidates: List[str] = []
        try:
            for root, dirs, files in os.walk(folder_str):
                # Filter out ignored directories in-place
                dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
                # Calculate depth relative to folder_str
                rel_parts = os.path.relpath(root, folder_str).split(os.sep)
                rel_depth = 0 if rel_parts == ["."] else len(rel_parts)
                if rel_depth > 3:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower().endswith(".uproject"):
                        cand = os.path.join(root, f)
                        stem = os.path.splitext(f)[0]
                        if stem.lower() == folder_name.lower():
                            return Path(cand)
                        nested_candidates.append(cand)
        except OSError:
            pass

        if nested_candidates:
            # Sort by shortest path to prefer shallower project locations
            nested_candidates.sort(key=lambda c: len(c.split(os.sep)))
            return Path(nested_candidates[0])
    except (OSError, PermissionError):
        pass
    return None


def find_gds(folder: Union[str, Path]) -> Optional[Path]:
    """Find game.gds.json or any *.gds.json specification file in folder.

    Uses os.path instead of pathlib to avoid Python 3.14 + PySide6 C-runtime ABI collision
    when called from background threads (DEF-134).
    """
    try:
        folder_str = str(folder)
        if not os.path.isdir(folder_str):
            return None
        gds_file = os.path.join(folder_str, "GameForge", "design", "game.gds.json")
        if os.path.isfile(gds_file):
            return Path(gds_file)
        alt_gds = os.path.join(folder_str, "game.gds.json")
        if os.path.isfile(alt_gds):
            return Path(alt_gds)

        # Check for any *.gds.json in GameForge/design/
        design_dir = os.path.join(folder_str, "GameForge", "design")
        if os.path.isdir(design_dir):
            try:
                for entry in sorted(os.listdir(design_dir)):
                    if entry.endswith(".gds.json") and os.path.isfile(os.path.join(design_dir, entry)):
                        return Path(os.path.join(design_dir, entry))
            except OSError:
                pass

        # Check for any *.gds.json in project root
        try:
            for entry in sorted(os.listdir(folder_str)):
                if entry.endswith(".gds.json") and os.path.isfile(os.path.join(folder_str, entry)):
                    return Path(os.path.join(folder_str, entry))
        except OSError:
            pass
    except (OSError, PermissionError):
        pass
    return None


def is_gameforge_project(folder: Union[str, Path]) -> bool:
    """Check if folder is a GameForge or Unreal Engine project.

    Uses os.path instead of pathlib to avoid Python 3.14 + PySide6 C-runtime ABI collision
    when called from background threads (DEF-134).
    """
    try:
        folder_str = str(folder)
        if not os.path.isdir(folder_str):
            return False

        # Guard: Repository root itself is NEVER a game project
        try:
            from .settings import REPO_ROOT, get_settings
            repo_real = os.path.realpath(str(REPO_ROOT))
            real_folder = os.path.realpath(folder_str)
            if real_folder == repo_real:
                return False
            # Guard: Configured projects_root is NEVER a single game project
            s_root = get_settings().projects_root
            if s_root and real_folder == os.path.realpath(str(s_root)):
                return False
            # Immediate infrastructure subdirectories of REPO_ROOT are platform code/fixtures
            if os.path.dirname(real_folder) == repo_real:
                if os.path.basename(real_folder) in REPO_INFRASTRUCTURE_DIRS:
                    return False
        except Exception:
            pass

        folder_name = os.path.basename(folder_str.rstrip("/\\"))
        if folder_name in REPO_INFRASTRUCTURE_DIRS:
            return False

        # 1. Direct or nested .uproject
        up = find_uproject(folder_str)
        if up is not None:
            return True

        # 2. GDS specification file
        if find_gds(folder_str) is not None:
            return True

        # 3. A .gameforge folder alone is IDE bookkeeping (sessions, tasks, diffs) that every workspace gets; it
        #    made the workspace itself show up as an empty "Unknown" game. Only a folder with Forge runs counts.
        if os.path.isdir(os.path.join(folder_str, "Saved", "GameForge", "runs")):
            return True
    except (OSError, PermissionError):
        pass
    return False


def resolve_project_dir(
    name_or_path: Union[str, Path],
    workspace_dir: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """Authoritatively resolve the on-disk directory for a project name or path.

    Checks candidate paths in priority order:
    1. If name_or_path is an existing directory path.
    2. Under configured projects_root.
    3. Under workspace_dir.
    4. If workspace_dir itself represents this project.
    5. Under developer projects root (E:\\GameForge\\projects).
    6. Under default_workspace / Projects.
    """
    if not name_or_path:
        return None

    raw_path = Path(name_or_path)
    name = raw_path.name
    if name in REPO_INFRASTRUCTURE_DIRS:
        return None

    # 1. Direct path check (must be a valid GameForge or Unreal project)
    if raw_path.is_dir() and is_gameforge_project(raw_path):
        return raw_path.resolve()
    s = get_settings()

    # Candidate roots
    candidate_roots: List[Path] = []

    # Configured projects_root
    if s.projects_root:
        candidate_roots.append(Path(s.projects_root).resolve())

    # Workspace directory
    ws_path = Path(workspace_dir).resolve() if workspace_dir else None
    if ws_path:
        if ws_path.name.lower() == name.lower() and is_gameforge_project(ws_path):
            return ws_path
        candidate_roots.append(ws_path)
        ws_projects = ws_path / "Projects"
        if ws_projects.is_dir():
            candidate_roots.append(ws_projects)

    # Extra projects directory if configured via environment or host profile
    extra_roots = []
    env_extra = os.environ.get("GAMEFORGE_EXTRA_PROJECTS_ROOT")
    if env_extra:
        extra_roots.append(Path(env_extra))
    hp_proj = s.host_profile.get("projects_root") if hasattr(s, "host_profile") and isinstance(s.host_profile, dict) else None
    if hp_proj:
        extra_roots.append(Path(hp_proj))
    if s.artifacts_root:
        extra_roots.append(Path(s.artifacts_root) / "projects")
    if s.validation_root:
        val_proj = Path(s.validation_root).parent / "projects"
        if val_proj.is_dir():
            extra_roots.append(val_proj)
    for extra in extra_roots:
        if extra.is_dir() and extra not in candidate_roots:
            candidate_roots.append(extra)

    # Default workspace projects
    if s.default_workspace:
        def_ws = Path(s.default_workspace).resolve()
        def_proj = def_ws / "Projects"
        if def_proj.is_dir() and def_proj not in candidate_roots:
            candidate_roots.append(def_proj)
        if def_ws.is_dir() and def_ws not in candidate_roots:
            candidate_roots.append(def_ws)

    # Check candidates
    for root in candidate_roots:
        p_dir = root / name
        if p_dir.is_dir() and is_gameforge_project(p_dir):
            return p_dir.resolve()

    # Second pass: directory exists even if .uproject / gds not yet created
    for root in candidate_roots:
        p_dir = root / name
        if p_dir.is_dir():
            return p_dir.resolve()

    # Third pass: check all discovered projects across all roots (exact + case-insensitive)
    all_discovered = list_all_project_dirs(workspace_dir)
    if name in all_discovered:
        return all_discovered[name]
    for d_name, d_path in all_discovered.items():
        if d_name.lower() == name.lower():
            return d_path

    # Fall back to projects_root / name (even if not yet on disk)
    if s.projects_root:
        return (Path(s.projects_root).resolve() / name)

    return None


def list_all_project_dirs(
    workspace_dir: Optional[Union[str, Path]] = None,
    include_workspace_self: bool = True,
) -> Dict[str, Path]:
    """Discover all GameForge and Unreal projects across known project roots.

    Returns an ordered mapping of project_name -> project_dir: Path.

    THREADING SAFETY (DEF-134, DEF-REM-P4B): Decoupled pure filesystem discovery.
    Filesystem scanning operates strictly via string-based os/os.path APIs without
    interacting with QApplication or GUI widgets, enabling safe execution across
    both main and worker threads.
    """
    projects: Dict[str, Path] = {}
    s = get_settings()

    # Build roots_to_scan as plain strings to avoid pathlib ABI issues
    roots_to_scan: List[str] = []

    def _add_root(r: str) -> None:
        """Add root if it's a real directory and not already present."""
        if not r:
            return
        real = os.path.realpath(r)
        if os.path.isdir(real) and real not in roots_to_scan:
            roots_to_scan.append(real)

    if s.projects_root:
        _add_root(str(s.projects_root))

    # Host profile projects root
    hp_proj = s.host_profile.get("projects_root") if hasattr(s, "host_profile") and isinstance(s.host_profile, dict) else None
    if hp_proj:
        _add_root(str(hp_proj))

    # Artifacts root projects subdirectory
    if s.artifacts_root:
        _add_root(os.path.join(str(s.artifacts_root), "projects"))

    # Validation root parent projects
    if s.validation_root:
        val_parent = os.path.dirname(str(s.validation_root))
        _add_root(os.path.join(val_parent, "projects"))

    # Developer host profiles in repository configs
    try:
        from .settings import REPO_ROOT
        cfg_dir = os.path.join(str(REPO_ROOT), "configs", "host_profiles")
        if os.path.isdir(cfg_dir):
            try:
                cfg_entries = os.listdir(cfg_dir)
            except OSError:
                cfg_entries = []
            for cfg_name in cfg_entries:
                if not cfg_name.endswith(".json"):
                    continue
                cfg_file = os.path.join(cfg_dir, cfg_name)
                try:
                    import json
                    with open(cfg_file, encoding="utf-8") as fh:
                        p_data = json.load(fh)
                    p_root = p_data.get("projects_root")
                    if p_root:
                        _add_root(str(p_root))
                except Exception:
                    pass
    except Exception:
        pass

    ws_path_str: Optional[str] = None
    if workspace_dir:
        ws_path_str = os.path.realpath(str(workspace_dir))
        if os.path.isdir(ws_path_str):
            repo_real = None
            try:
                from .settings import REPO_ROOT
                repo_real = os.path.realpath(str(REPO_ROOT))
            except Exception:
                pass

            is_repo_root = (repo_real is not None and ws_path_str == repo_real)
            if not is_repo_root:
                if include_workspace_self and is_gameforge_project(ws_path_str):
                    ws_name = os.path.basename(ws_path_str)
                    projects[ws_name] = Path(ws_path_str)
                _add_root(ws_path_str)

            # Subdirectory scanning for "Projects" / "projects"
            _add_root(os.path.join(ws_path_str, "Projects"))
            _add_root(os.path.join(ws_path_str, "projects"))

    env_extra = os.environ.get("GAMEFORGE_EXTRA_PROJECTS_ROOT")
    if env_extra:
        _add_root(str(env_extra))

    # Default workspace projects
    if s.default_workspace:
        def_ws = os.path.realpath(str(s.default_workspace))
        _add_root(os.path.join(def_ws, "Projects"))

    # User Documents default location
    _add_root(os.path.join(os.path.expanduser("~"), "Documents", "GameForge", "Projects"))

    for root_str in roots_to_scan:
        try:
            for entry_name in sorted(os.listdir(root_str)):
                if entry_name.startswith("."):
                    continue
                entry_path = os.path.join(root_str, entry_name)
                if os.path.isdir(entry_path):
                    if is_gameforge_project(entry_path) and entry_name not in projects:
                        # Use os.path.realpath instead of pathlib.resolve() to avoid ABI crash
                        projects[entry_name] = Path(os.path.realpath(entry_path))
        except OSError:
            pass

    return projects


def find_packaged_executable(
    project_dir: Union[str, Path],
    project_name: Optional[str] = None,
) -> Optional[Path]:
    """Find packaged Win64 executable for project, supporting nested uprojects and custom package dirs."""
    p_dir = Path(project_dir).resolve()
    if not p_dir.is_dir():
        return None

    name = project_name or p_dir.name
    dirs_to_check = [p_dir]

    up = find_uproject(p_dir)
    if up is not None and up.parent != p_dir:
        dirs_to_check.append(up.parent)

    for target_dir in dirs_to_check:
        target_name = up.stem if (up is not None and target_dir == up.parent) else name
        for exe_candidate in (
            target_dir / "Packaged" / "Windows" / f"{target_name}.exe",
            target_dir / "Packaged" / "WindowsNoEditor" / f"{target_name}.exe",
            target_dir / "package_dev" / "Windows" / f"{target_name}.exe",
            target_dir / "package_ship" / "Windows" / f"{target_name}.exe",
            target_dir / "Packaged" / "Windows" / f"{name}.exe",
        ):
            if exe_candidate.is_file():
                return exe_candidate

        # Search Packaged/Windows/ for any valid game .exe
        for pkg_sub in ("Packaged/Windows", "Packaged/WindowsNoEditor", "package_dev/Windows", "package_ship/Windows"):
            pkg_win = target_dir / pkg_sub
            if pkg_win.is_dir():
                try:
                    for exe in pkg_win.glob("*.exe"):
                        if not exe.name.lower().endswith("crashreportclient.exe"):
                            return exe
                except OSError:
                    pass

    return None


def open_folder_in_file_manager(folder: Union[str, Path]) -> bool:
    """Open folder in Windows Explorer or Linux file manager."""
    target = Path(folder).resolve()
    if not target.is_dir():
        # If given a file path, open its parent folder
        if target.is_file():
            target = target.parent
        else:
            logger.warning("Cannot open in file manager: path does not exist: %s", target)
            return False

    try:
        if sys.platform == "win32":
            os.startfile(str(target))
            return True
        else:
            subprocess.Popen(["xdg-open", str(target)])
            return True
    except Exception as exc:
        logger.error("Failed to open %s in file manager: %s", target, exc)
        return False
