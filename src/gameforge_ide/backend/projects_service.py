"""Re-export ProjectsService and helpers from desktop.services.projects_service."""
from __future__ import annotations

try:
    from ..desktop.services.projects_service import (
        GameSummary,
        ProjectsService,
        check_project_has_package,
        delete_project,
        find_project_thumbnail,
        list_games,
        load_runs_index,
    )
except ImportError:
    GameSummary = None  # type: ignore[assignment,misc]
    ProjectsService = None  # type: ignore[assignment,misc]
    check_project_has_package = None  # type: ignore[assignment]
    delete_project = None  # type: ignore[assignment]
    find_project_thumbnail = None  # type: ignore[assignment]
    list_games = None  # type: ignore[assignment]
    load_runs_index = None  # type: ignore[assignment]

__all__ = [
    "GameSummary",
    "find_project_thumbnail",
    "check_project_has_package",
    "load_runs_index",
    "list_games",
    "delete_project",
    "ProjectsService",
]
