"""Projects service: game listing, metadata aggregation, thumbnails, and lifecycle."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import time
from typing import Any, Dict, List, Optional, Union

from PySide6.QtCore import QObject, Signal, Slot

from src.gameforge_ide.core.jobs import JobManager, default_job_manager
from src.gameforge_ide.core.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class GameSummary:
    name: str
    title: str
    genre: str
    pitch: str
    project_dir: Path
    uproject_path: Optional[Path] = None
    gds_path: Optional[Path] = None
    revision: int = 1
    updated_at: float = 0.0
    last_run_id: Optional[str] = None
    last_run_status: Optional[str] = None
    last_run_time: Optional[float] = None
    thumbnail_path: Optional[Path] = None
    has_package: bool = False


def find_project_thumbnail(project_dir: Path) -> Optional[Path]:
    """Find newest thumbnail: newest in Saved/GameForge/evidence/**/*.png, else Saved/GameForge/*.png."""
    saved_gf = project_dir / "Saved" / "GameForge"
    if not saved_gf.is_dir():
        return None

    # 1. Look in evidence/**
    evidence_dir = saved_gf / "evidence"
    if evidence_dir.is_dir():
        evidence_pngs = list(evidence_dir.glob("**/*.png"))
        if evidence_pngs:
            evidence_pngs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return evidence_pngs[0]

    # 2. Look in Saved/GameForge/*.png
    root_pngs = list(saved_gf.glob("*.png"))
    if root_pngs:
        root_pngs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return root_pngs[0]

    return None


def check_project_has_package(project_dir: Path, name: str) -> bool:
    """Check if project has a packaged executable."""
    for exe_candidate in (
        project_dir / "Binaries" / "Win64" / f"{name}.exe",
        project_dir / "package_dev" / "Windows" / f"{name}.exe",
        project_dir / "package_ship" / "Windows" / f"{name}.exe",
        project_dir / "Packaged" / "Windows" / f"{name}.exe",
    ):
        if exe_candidate.is_file():
            return True
    return False


def load_runs_index(project_root: Optional[Path] = None, workspace_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Aggregate runs_index.json from workspace and projects root."""
    runs: List[Dict[str, Any]] = []
    seen_ids = set()

    paths_to_check = []
    if workspace_dir:
        paths_to_check.append(Path(workspace_dir) / ".gameforge" / "runs_index.json")
    paths_to_check.append(Path.cwd() / ".gameforge" / "runs_index.json")
    if project_root:
        paths_to_check.append(Path(project_root) / ".gameforge" / "runs_index.json")

    for p in paths_to_check:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        rid = item.get("run_id")
                        if rid and rid not in seen_ids:
                            seen_ids.add(rid)
                            runs.append(item)
            except Exception:
                pass

    return runs


def list_games(
    projects_root: Optional[Union[str, Path]] = None,
    workspace_dir: Optional[Union[str, Path]] = None,
) -> List[GameSummary]:
    """Scan projects_root for GameForge projects, joining GDS and runs index."""
    root_str = projects_root or get_settings().projects_root
    if not root_str:
        return []

    root = Path(root_str).resolve()
    if not root.is_dir():
        return []

    runs = load_runs_index(root, Path(workspace_dir).resolve() if workspace_dir else None)
    # Map project directory string to newest run
    runs_by_proj: Dict[str, Dict[str, Any]] = {}
    for r in runs:
        pdir = r.get("project_dir")
        if pdir:
            norm_pdir = str(Path(pdir).resolve()).lower()
            existing = runs_by_proj.get(norm_pdir)
            if not existing or r.get("updated_at", 0) > existing.get("updated_at", 0):
                runs_by_proj[norm_pdir] = r

    games: List[GameSummary] = []

    try:
        subdirs = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
    except Exception:
        return []

    for d in subdirs:
        uproject_file = d / f"{d.name}.uproject"
        gds_file = d / "GameForge" / "design" / "game.gds.json"

        # A game exists if either game.gds.json or .uproject exists
        if not gds_file.is_file() and not uproject_file.is_file():
            continue

        title = d.name
        genre = "unknown"
        pitch = ""
        revision = 1
        updated_at = d.stat().st_mtime

        if gds_file.is_file():
            try:
                gds_data = json.loads(gds_file.read_text(encoding="utf-8"))
                meta = gds_data.get("meta", {})
                overview = gds_data.get("overview", {})
                title = meta.get("title") or d.name
                genre = overview.get("genre") or "unknown"
                pitch = overview.get("pitch") or ""
                revision = meta.get("revision", 1)
                updated_at = max(updated_at, gds_file.stat().st_mtime)
            except Exception:
                pass

        norm_d = str(d.resolve()).lower()
        last_run = runs_by_proj.get(norm_d)
        last_run_id = None
        last_run_status = None
        last_run_time = None

        if last_run:
            last_run_id = last_run.get("run_id")
            last_run_status = last_run.get("status")
            last_run_time = last_run.get("updated_at")
            if last_run_time and last_run_time > updated_at:
                updated_at = last_run_time

        thumb = find_project_thumbnail(d)
        has_pkg = check_project_has_package(d, d.name)

        games.append(
            GameSummary(
                name=d.name,
                title=title,
                genre=genre,
                pitch=pitch,
                project_dir=d,
                uproject_path=uproject_file if uproject_file.is_file() else None,
                gds_path=gds_file if gds_file.is_file() else None,
                revision=revision,
                updated_at=updated_at,
                last_run_id=last_run_id,
                last_run_status=last_run_status,
                last_run_time=last_run_time,
                thumbnail_path=thumb,
                has_package=has_pkg,
            )
        )

    # Sort descending by updated_at
    games.sort(key=lambda g: g.updated_at, reverse=True)
    return games


def delete_project(project_name: str, projects_root: Optional[Union[str, Path]] = None) -> bool:
    """Delete a project folder after checking that it is not locked in an active editor link."""
    try:
        from src.gameforge_ide.backend.tools.game_tools import GameTools
        for link in GameTools.all_links():
            if getattr(link, "project_name", "") == project_name:
                raise RuntimeError(
                    f"Cannot delete project '{project_name}': an active Unreal Editor link is connected."
                )
    except ImportError:
        pass

    root_str = projects_root or get_settings().projects_root
    if not root_str:
        return False
    pdir = Path(root_str).resolve() / project_name
    if not pdir.is_dir():
        return False

    shutil.rmtree(pdir)
    return True


class ProjectsService(QObject):
    """Qt adapter for querying and mutating projects on background threads."""

    gamesLoaded = Signal(list)
    gameDeleted = Signal(str)
    operationFailed = Signal(str)

    def __init__(
        self,
        projects_root: Optional[Union[str, Path]] = None,
        workspace_dir: Optional[Union[str, Path]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._projects_root = Path(projects_root).resolve() if projects_root else None
        self._workspace_dir = Path(workspace_dir).resolve() if workspace_dir else None
        self._job_manager = default_job_manager()

    def refresh(self) -> None:
        """Fetch games asynchronously and emit gamesLoaded."""
        def work() -> List[GameSummary]:
            return list_games(self._projects_root, self._workspace_dir)

        def done(handle):
            if handle.status == "DONE":
                res = handle.result()
                if res is not None:
                    self.gamesLoaded.emit(res)
            elif handle.status == "FAILED":
                self.operationFailed.emit(str(handle.error))

        handle = self._job_manager.submit(work, name="Scan Projects")
        handle.add_done_callback(done)

    def delete_game(self, project_name: str) -> None:
        """Delete a project asynchronously on JobManager."""
        def work() -> bool:
            return delete_project(project_name, self._projects_root)

        def done(handle):
            if handle.status == "DONE":
                self.gameDeleted.emit(project_name)
                self.refresh()
            elif handle.status == "FAILED":
                self.operationFailed.emit(str(handle.error))

        handle = self._job_manager.submit(work, name=f"Delete Project {project_name}")
        handle.add_done_callback(done)
