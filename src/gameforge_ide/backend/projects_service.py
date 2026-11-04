"""Re-export ProjectsService and helpers from desktop.services.projects_service."""
from ..desktop.services.projects_service import (
    GameSummary,
    find_project_thumbnail,
    check_project_has_package,
    load_runs_index,
    list_games,
    delete_project,
    ProjectsService,
)

__all__ = [
    "GameSummary",
    "find_project_thumbnail",
    "check_project_has_package",
    "load_runs_index",
    "list_games",
    "delete_project",
    "ProjectsService",
]
