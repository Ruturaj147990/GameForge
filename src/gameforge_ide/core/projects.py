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


def find_uproject(folder: Union[str, Path]) -> Optional[Path]:
    """Find the first .uproject file in folder, matching folder name first if available."""
    p = Path(folder)
    if not p.is_dir():
        return None
    # 1. Exact match <folder_name>.uproject
    exact = p / f"{p.name}.uproject"
    if exact.is_file():
        return exact
    # 2. Any .uproject in the top level of folder
    try:
        candidates = list(p.glob("*.uproject"))
        if candidates:
            return candidates[0]
    except OSError:
        pass
    return None


def find_gds(folder: Union[str, Path]) -> Optional[Path]:
    """Find game.gds.json specification file in folder."""
    p = Path(folder)
    if not p.is_dir():
        return None
    gds_file = p / "GameForge" / "design" / "game.gds.json"
    if gds_file.is_file():
        return gds_file
    alt_gds = p / "game.gds.json"
    if alt_gds.is_file():
        return alt_gds
    return None


def is_gameforge_project(folder: Union[str, Path]) -> bool:
    """Check if folder is a GameForge or Unreal Engine project."""
    p = Path(folder)
    if not p.is_dir():
        return False
    if find_uproject(p) is not None:
        return True
    if find_gds(p) is not None:
        return True
    if (p / ".gameforge" / "project_graph.json").is_file():
        return True
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
    # 1. Direct path check
    if raw_path.is_dir():
        return raw_path.resolve()

    name = raw_path.name
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
    """
    projects: Dict[str, Path] = {}
    s = get_settings()

    roots_to_scan: List[Path] = []
    if s.projects_root and Path(s.projects_root).is_dir():
        roots_to_scan.append(Path(s.projects_root).resolve())

    ws_path = Path(workspace_dir).resolve() if workspace_dir else None
    if ws_path and ws_path.is_dir():
        if include_workspace_self and is_gameforge_project(ws_path):
            projects[ws_path.name] = ws_path
        if ws_path not in roots_to_scan:
            roots_to_scan.append(ws_path)
        ws_proj = ws_path / "Projects"
        if ws_proj.is_dir() and ws_proj not in roots_to_scan:
            roots_to_scan.append(ws_proj)

    env_extra = os.environ.get("GAMEFORGE_EXTRA_PROJECTS_ROOT")
    if env_extra and Path(env_extra).is_dir() and Path(env_extra) not in roots_to_scan:
        roots_to_scan.append(Path(env_extra).resolve())
    if s.validation_root:
        val_proj = Path(s.validation_root).parent / "projects"
        if val_proj.is_dir() and val_proj not in roots_to_scan:
            roots_to_scan.append(val_proj.resolve())

    for root in roots_to_scan:
        try:
            for d in sorted(root.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    if is_gameforge_project(d) and d.name not in projects:
                        projects[d.name] = d.resolve()
        except OSError:
            pass

    return projects


def find_packaged_executable(
    project_dir: Union[str, Path],
    project_name: Optional[str] = None,
) -> Optional[Path]:
    """Find packaged Win64 executable for project."""
    p_dir = Path(project_dir).resolve()
    if not p_dir.is_dir():
        return None

    name = project_name or p_dir.name

    for exe_candidate in (
        p_dir / "Packaged" / "Windows" / f"{name}.exe",
        p_dir / "Packaged" / "WindowsNoEditor" / f"{name}.exe",
        p_dir / "package_dev" / "Windows" / f"{name}.exe",
        p_dir / "package_ship" / "Windows" / f"{name}.exe",
        p_dir / "Binaries" / "Win64" / f"{name}.exe",
    ):
        if exe_candidate.is_file():
            return exe_candidate

    # Search Packaged/Windows/ for any .exe
    pkg_win = p_dir / "Packaged" / "Windows"
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
