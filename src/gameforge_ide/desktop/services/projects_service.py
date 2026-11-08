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

from ...core.jobs import JobManager, default_job_manager
from ...core.settings import get_settings
from ...core.projects import (
    find_uproject,
    find_gds,
    is_gameforge_project,
    resolve_project_dir,
    list_all_project_dirs,
    find_packaged_executable,
    open_folder_in_file_manager,
)

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
        try:
            evidence_pngs = [p for p in evidence_dir.glob("**/*.png") if p.is_file() and p.stat().st_size > 0]
            if evidence_pngs:
                evidence_pngs.sort(key=lambda p: (p.stat().st_mtime if p.exists() else 0.0), reverse=True)
                return evidence_pngs[0]
        except OSError:
            pass

    # 2. Look in Saved/GameForge/*.png
    try:
        root_pngs = [p for p in saved_gf.glob("*.png") if p.is_file() and p.stat().st_size > 0]
        if root_pngs:
            root_pngs.sort(key=lambda p: (p.stat().st_mtime if p.exists() else 0.0), reverse=True)
            return root_pngs[0]
    except OSError:
        pass

    return None


def check_project_has_package(project_dir: Path, name: str) -> bool:
    """Check if project has a packaged executable."""
    return find_packaged_executable(project_dir, name) is not None


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
                        if not isinstance(item, dict):
                            continue
                        rid = item.get("run_id")
                        if rid and rid not in seen_ids:
                            seen_ids.add(rid)
                            runs.append(item)
            except Exception:
                pass

    return runs


def _safe_timestamp(val: Any) -> float:
    """Robust conversion of arbitrary timestamp formats (float, int, or numeric string) to float."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def list_games(
    projects_root: Optional[Union[str, Path]] = None,
    workspace_dir: Optional[Union[str, Path]] = None,
) -> List[GameSummary]:
    """Scan projects_root and workspace for GameForge projects, joining GDS and runs index."""
    if not projects_root:
        s_root = get_settings().projects_root
        if s_root and Path(s_root).is_dir():
            projects_root = s_root

    project_dirs_map: Dict[str, Path] = {}
    if projects_root:
        root = Path(projects_root).resolve()
        if root.is_dir():
            try:
                for d in root.iterdir():
                    if d.is_dir() and not d.name.startswith("."):
                        if is_gameforge_project(d):
                            project_dirs_map[d.name] = d.resolve()
            except OSError:
                pass

    # If workspace_dir is provided and is a valid standalone project (and NOT repo root), include it
    if workspace_dir:
        ws = Path(workspace_dir).resolve()
        if ws.is_dir():
            repo_real = None
            try:
                from ...core.settings import REPO_ROOT
                repo_real = Path(REPO_ROOT).resolve()
            except Exception:
                pass
            p_root_resolved = Path(projects_root).resolve() if projects_root else None
            if ws != repo_real and ws != p_root_resolved:
                if is_gameforge_project(ws):
                    project_dirs_map[ws.name] = ws
                for p_sub in ("Projects", "projects"):
                    ws_proj = ws / p_sub
                    if ws_proj.is_dir():
                        try:
                            for d in ws_proj.iterdir():
                                if d.is_dir() and not d.name.startswith(".") and is_gameforge_project(d):
                                    project_dirs_map[d.name] = d.resolve()
                        except OSError:
                            pass

    # A configured projects_root can be stale, empty, or point at only one
    # storage location. Always consult the canonical multi-root discovery path
    # when the primary scan found nothing; do not let a non-empty setting disable
    # fallback discovery.
    if not project_dirs_map:
        try:
            discovered = list_all_project_dirs(workspace_dir)
            for discovered_name, discovered_path in discovered.items():
                project_dirs_map.setdefault(discovered_name, discovered_path)
        except (OSError, PermissionError) as exc:
            logger.warning("Fallback project discovery failed: %s", exc)

    if not project_dirs_map:
        return []

    p_root = Path(projects_root).resolve() if projects_root else get_settings().projects_root
    runs = load_runs_index(Path(p_root) if p_root else None, Path(workspace_dir).resolve() if workspace_dir else None)
    # Map project directory string to newest run
    runs_by_proj: Dict[str, Dict[str, Any]] = {}
    for r in runs:
        if not isinstance(r, dict):
            continue
        pdir = r.get("project_dir")
        if pdir:
            try:
                norm_pdir = str(Path(pdir).resolve()).lower()
            except Exception:
                continue
            existing = runs_by_proj.get(norm_pdir)
            r_updated = _safe_timestamp(r.get("updated_at"))
            ex_updated = _safe_timestamp(existing.get("updated_at")) if existing else -1.0
            if not existing or r_updated > ex_updated:
                runs_by_proj[norm_pdir] = r

    games: List[GameSummary] = []

    for name, d in project_dirs_map.items():
        uproject_file = find_uproject(d)
        gds_file = find_gds(d)

        # A game exists if either game.gds.json, .uproject, or .gameforge project workspace exists
        if not gds_file and not uproject_file and not (d / ".gameforge").is_dir():
            continue

        title = d.name
        genre = "unknown"
        pitch = ""
        revision = 1
        updated_at = d.stat().st_mtime

        if gds_file and gds_file.is_file():
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
            raw_time = last_run.get("updated_at")
            last_run_time = _safe_timestamp(raw_time) if raw_time is not None else None
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
                uproject_path=uproject_file if (uproject_file and uproject_file.is_file()) else None,
                gds_path=gds_file if (gds_file and gds_file.is_file()) else None,
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


def delete_project(
    project_name: str,
    projects_root: Optional[Union[str, Path]] = None,
    project_dir: Optional[Union[str, Path]] = None,
) -> bool:
    """Delete a project folder after checking that it is not locked in an active editor link.
    
    Handles Windows read-only file attributes (e.g. .git/objects and binaries),
    purges associated runs from runs_index.json, and cleans SQLite project indexes.
    """
    import stat
    import sys

    # 1. Resolve candidate directory first so link checks and path checks have authoritative pdir
    if project_dir:
        pdir = Path(project_dir).resolve()
    else:
        pdir = resolve_project_dir(project_name, projects_root)

    if not pdir or not pdir.is_dir():
        logger.warning(f"Cannot delete project '{project_name}': directory '{pdir}' does not exist.")
        return False

    # Guard against accidental deletion of root, repo root, or current working directory
    resolved_cwd = Path.cwd().resolve()
    resolved_pdir = pdir.resolve()
    if (
        resolved_pdir == resolved_cwd
        or resolved_pdir in resolved_cwd.parents
        or resolved_pdir.parent == resolved_pdir
        or len(resolved_pdir.parts) <= 1
    ):
        raise PermissionError(f"Safety violation: Refusing to delete critical or root directory '{pdir}'.")

    if projects_root and resolved_pdir == Path(projects_root).resolve():
        raise PermissionError(f"Safety violation: Refusing to delete entire projects root '{pdir}'.")

    # 2. Check active Unreal Editor link
    try:
        from ...backend.tools.game_tools import GameTools
        for link in GameTools.all_links():
            link_name = getattr(link, "project_name", "")
            if link_name and (link_name == project_name or link_name == pdir.name):
                raise RuntimeError(
                    f"Cannot delete project '{project_name}': an active Unreal Editor link is connected."
                )
    except ImportError:
        pass

    # 3. Release any child process locks (e.g. terminal shell or subprocesses whose CWD is pdir)
    try:
        import psutil
        curr_proc = psutil.Process()
        norm_pdir = str(pdir.resolve()).lower()
        for child in curr_proc.children(recursive=True):
            try:
                if not child.is_running():
                    continue
                child_cwd = str(Path(child.cwd()).resolve()).lower()
                if child_cwd == norm_pdir or child_cwd.startswith(norm_pdir + os.sep) or child_cwd.startswith(norm_pdir + "/"):
                    logger.info("Terminating child process %d (%s) holding lock on %s", child.pid, child.name(), pdir)
                    child.terminate()
                    child.wait(timeout=1.0)
            except Exception:
                pass
    except Exception as e:
        logger.debug("psutil child process check skipped: %s", e)

    # 4. Pre-emptively clear read-only attributes on all files and subdirectories
    for root, dirs, files in os.walk(pdir):
        for f in files:
            try:
                os.chmod(os.path.join(root, f), stat.S_IWRITE | stat.S_IREAD)
            except Exception:
                pass
        for d in dirs:
            try:
                os.chmod(os.path.join(root, d), stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            except Exception:
                pass

    # 5. Windows read-only file handler for shutil.rmtree
    def _handle_rmtree_error(func, path, exc_info_or_exc):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)
        except Exception as err:
            logger.warning("Could not force-remove %s: %s", path, err)

    # Retry up to 5 times in case of transient locks or NTFS delete latency
    for attempt in range(5):
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(pdir, onexc=_handle_rmtree_error)
            else:
                shutil.rmtree(pdir, onerror=_handle_rmtree_error)
            if not pdir.exists():
                break
        except Exception as err:
            if attempt == 4:
                logger.error("Failed to delete directory %s: %s", pdir, err)
                raise
        time.sleep(0.1 * (attempt + 1))

    if pdir.exists():
        for attempt in range(5):
            try:
                os.rmdir(pdir)
                break
            except OSError:
                time.sleep(0.1 * (attempt + 1))
        if pdir.exists():
            remaining = list(pdir.iterdir())
            if remaining:
                raise OSError(
                    f"Failed to completely delete directory '{pdir}': {len(remaining)} items remain (files may be locked by another process)."
                )

    # 4. Clean up entries from runs_index.json across candidate locations
    try:
        paths_to_clean = []
        if projects_root:
            paths_to_clean.append(Path(projects_root) / ".gameforge" / "runs_index.json")
        s = get_settings()
        if s.projects_root:
            paths_to_clean.append(Path(s.projects_root) / ".gameforge" / "runs_index.json")
        paths_to_clean.append(Path.cwd() / ".gameforge" / "runs_index.json")
        if s.default_workspace:
            paths_to_clean.append(Path(s.default_workspace) / ".gameforge" / "runs_index.json")

        norm_target_pdir = str(pdir.resolve()).lower()
        norm_name = project_name.lower()

        for idx_file in set(paths_to_clean):
            if idx_file.is_file():
                try:
                    data = json.loads(idx_file.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        new_data = []
                        for item in data:
                            if not isinstance(item, dict):
                                continue
                            raw_pdir = item.get("project_dir")
                            item_pdir = str(Path(raw_pdir).resolve()).lower() if raw_pdir else ""
                            item_name = (item.get("project_name") or "").lower()
                            if (item_pdir and item_pdir == norm_target_pdir) or (item_name and item_name == norm_name):
                                continue
                            new_data.append(item)
                        if len(new_data) != len(data):
                            idx_file.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
                except Exception as e:
                    logger.warning("Could not update runs index %s: %s", idx_file, e)
    except Exception as e:
        logger.warning("Error cleaning runs_index for %s: %s", project_name, e)

    # 5. Purge index SQLite database for this project
    try:
        import hashlib
        proj_key = hashlib.sha1(str(pdir.resolve()).encode("utf-8")).hexdigest()
        candidate_ws = [pdir.parent, Path.cwd()]
        s = get_settings()
        if s.default_workspace:
            candidate_ws.append(Path(s.default_workspace))
        for ws in candidate_ws:
            if ws and Path(ws).is_dir():
                idx_db = Path(ws) / ".gameforge" / "index" / f"{proj_key}.db"
                for ext in ["", "-wal", "-shm"]:
                    f = Path(str(idx_db) + ext)
                    if f.is_file():
                        try:
                            f.unlink()
                        except Exception:
                            pass
    except Exception as e:
        logger.warning("Error cleaning index database for %s: %s", project_name, e)

    return True


class ProjectsService(QObject):
    """Qt adapter for querying and mutating projects on background threads."""

    gamesLoaded = Signal(list)
    gameDeleted = Signal(str)
    operationFailed = Signal(str)
    activeProjectChanged = Signal(str, Path)

    def __init__(
        self,
        projects_root: Optional[Union[str, Path]] = None,
        workspace_dir: Optional[Union[str, Path]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        if projects_root:
            self._projects_root = Path(projects_root).resolve()
        else:
            s_root = get_settings().projects_root
            self._projects_root = Path(s_root).resolve() if s_root else None
        self._workspace_dir = Path(workspace_dir).resolve() if workspace_dir else None
        self._job_manager = default_job_manager()
        self._active_project: Optional[str] = None
        self._active_project_dir: Optional[Path] = None

    @property
    def active_project(self) -> Optional[str]:
        return self._active_project

    @property
    def active_project_dir(self) -> Optional[Path]:
        return self._active_project_dir

    def set_active_project(self, project_name: str, project_dir: Optional[Union[str, Path]] = None) -> Path:
        """Set the authoritative active project and resolve its directory."""
        pdir = Path(project_dir).resolve() if project_dir else resolve_project_dir(project_name, self._workspace_dir)
        self._active_project = project_name
        self._active_project_dir = pdir
        if pdir:
            logger.info("ProjectsService active project set to '%s' -> %s", project_name, pdir)
            self.activeProjectChanged.emit(project_name, pdir)
        return pdir

    def list_games_sync(self) -> List[GameSummary]:
        """Synchronously scan and return games list."""
        return list_games(self._projects_root, self._workspace_dir)

    def list_projects(self) -> List[GameSummary]:
        """Alias for list_games_sync conforming to unified service interface."""
        return self.list_games_sync()

    def refresh(self) -> None:
        """Fetch games asynchronously and emit gamesLoaded."""
        def work() -> List[GameSummary]:
            return list_games(self._projects_root, self._workspace_dir)

        def done(handle):
            try:
                import shiboken6
                if not shiboken6.isValid(self):
                    return
            except Exception:
                pass
            try:
                if handle.status == "DONE":
                    res = handle.result()
                    if res is not None:
                        self.gamesLoaded.emit(res)
                elif handle.status == "FAILED":
                    self.operationFailed.emit(str(handle.error))
            except Exception:
                pass

        handle = self._job_manager.submit(work, name="Scan Projects")
        handle.add_done_callback(done)

    def delete_game(self, project_name: str, project_dir: Optional[Union[str, Path]] = None) -> None:
        """Delete a project asynchronously on JobManager."""
        def work() -> bool:
            success = delete_project(project_name, self._projects_root, project_dir=project_dir)
            if not success:
                raise RuntimeError(f"Could not delete project '{project_name}'.")
            return True

        def done(handle):
            try:
                import shiboken6
                if not shiboken6.isValid(self):
                    return
            except Exception:
                pass
            try:
                if handle.status == "DONE" and handle.result():
                    self.gameDeleted.emit(project_name)
                    self.refresh()
                else:
                    err_msg = str(handle.error) if handle.error else f"Could not remove project '{project_name}'."
                    self.operationFailed.emit(err_msg)
            except Exception:
                pass

        handle = self._job_manager.submit(work, name=f"Delete Project {project_name}")
        handle.add_done_callback(done)
